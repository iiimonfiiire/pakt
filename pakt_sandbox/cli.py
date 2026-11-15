"""`pakt-sandbox`: run the Slack simulator, or seed any Slack API target.

  pakt-sandbox slack serve [--port 8765]
  pakt-sandbox slack seed            # seeds SLACK_API_BASE with SLACK_BOT_TOKEN

The seeder uses only the Web API, so it fills the simulator and a real
sandbox workspace the same way.
"""

from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

from .slack_sim.server import serve
from .slack_sim.store import FIXTURE

DEFAULT_BASE = "http://127.0.0.1:8765/api"


def call(base: str, token: str, method: str, **params) -> dict:
    """One Web API call. Waits and retries once on a 429."""
    for attempt in (1, 2):
        req = urllib.request.Request(
            f"{base.rstrip('/')}/{method}",
            data=json.dumps(params).encode(),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt == 1:
                time.sleep(int(e.headers.get("Retry-After", "1")))
                continue
            raise
    raise RuntimeError("unreachable")


def seed(base: str, token: str, fixture: Path = FIXTURE) -> int:
    """Post the fixture's channels and messages. Returns the message count."""
    data = json.loads(fixture.read_text(encoding="utf-8"))
    existing = {c["name"]: c["id"] for c in call(base, token, "conversations.list")["channels"]}
    posted = 0
    for ch in data["channels"]:
        cid = existing.get(ch["name"])
        if cid is None:
            res = call(base, token, "conversations.create", name=ch["name"])
            if not res.get("ok"):
                raise SystemExit(f"cannot create #{ch['name']}: {res.get('error')}")
            cid = res["channel"]["id"]
        for m in ch["messages"]:
            res = call(base, token, "chat.postMessage", channel=cid, text=m["text"])
            posted += 1
            for r in m.get("replies", []):
                call(base, token, "chat.postMessage", channel=cid, text=r["text"], thread_ts=res["ts"])
                posted += 1
    return posted


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="pakt-sandbox")
    sub = parser.add_subparsers(dest="target", required=True)
    slack = sub.add_parser("slack").add_subparsers(dest="action", required=True)
    s = slack.add_parser("serve", help="run the local Slack simulator")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    slack.add_parser("seed", help="post the fixture to SLACK_API_BASE")
    o = slack.add_parser("office", help="let AI coworker bots chat in the simulator")
    o.add_argument("--turns", type=int, default=None, help="stop after N turns (default: run until Ctrl-C)")
    o.add_argument("--interval", type=float, default=5.0, help="seconds between turns")
    o.add_argument("--model", default=os.environ.get("OLLAMA_MODEL", "llama3.2:1b"))
    o.add_argument("--ollama", default=os.environ.get("OLLAMA_BASE", "http://127.0.0.1:11434"))
    o.add_argument("--seed", type=int, default=None)
    args = parser.parse_args(argv)

    if args.action == "office":
        from .office.backends import OllamaBackend
        from .office.runner import Office

        base = os.environ.get("SLACK_API_BASE", DEFAULT_BASE)
        office = Office(base, OllamaBackend(args.ollama, args.model), seed=args.seed)
        try:
            office.run(args.turns, args.interval)
        except KeyboardInterrupt:
            pass
    elif args.action == "serve":
        server = serve(args.host, args.port)
        print(f"Slack simulator on http://{args.host}:{args.port}/api  (token: xoxb-sim-bot)")
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.server_close()
    else:
        base = os.environ.get("SLACK_API_BASE", DEFAULT_BASE)
        token = os.environ.get("SLACK_BOT_TOKEN", "xoxb-sim-bot")
        print(f"Seeded {seed(base, token)} messages into {base}")
