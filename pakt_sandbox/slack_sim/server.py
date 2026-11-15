"""A local HTTP server that mimics the Slack Web API.

Point a connector at it with SLACK_API_BASE=http://127.0.0.1:8765/api and any
token from the fixture. Slack-style behavior covered: bearer auth, scopes,
form or JSON bodies, cursor pagination, threads, and rate limits.

Admin endpoints under /_sim/ reset state and inject faults. Real Slack has no
such endpoints, so keep them out of connector code.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .store import SlackError, Workspace

SCOPES = {
    "auth.test": None,
    "conversations.list": "channels:read",
    "conversations.info": "channels:read",
    "conversations.history": "channels:history",
    "conversations.replies": "channels:history",
    "conversations.create": "channels:manage",
    "users.list": "users:read",
    "users.info": "users:read",
    "chat.postMessage": "chat:write",
    "chat.update": "chat:write",
    "reactions.add": "reactions:write",
}


VIEWER = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Slack sim</title>
<style>
:root{color-scheme:light dark;--bg:#fff;--fg:#1d1c1d;--mut:#616061;--line:#ddd}
@media(prefers-color-scheme:dark){:root{--bg:#1a1d21;--fg:#d1d2d3;--mut:#9a9b9c;--line:#363a3f}}
body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.4 system-ui,sans-serif}
header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:8px;flex-wrap:wrap}
button{font:inherit;padding:2px 10px;border:1px solid var(--line);border-radius:12px;background:none;color:inherit;cursor:pointer}
button[aria-pressed=true]{background:var(--fg);color:var(--bg)}
main{padding:8px 16px;max-width:760px}
.m{padding:6px 0}.t{margin-left:28px;border-left:2px solid var(--line);padding-left:10px}
.u{font-weight:700}.c,.ts{color:var(--mut);font-size:12px;margin-left:6px}
.x{white-space:pre-wrap}
</style>
<header id="tabs"></header><main id="feed"></main>
<script>
let sel = "all";
async function load(){
  const r = await (await fetch("/_sim/feed")).json();
  const names = [...new Set(r.messages.map(m => m.channel))].sort();
  tabs.replaceChildren(...["all", ...names].map(n => {
    const b = document.createElement("button");
    b.textContent = n === "all" ? "all" : "#" + n;
    b.setAttribute("aria-pressed", n === sel);
    b.onclick = () => { sel = n; load(); };
    return b;
  }));
  const rows = r.messages.filter(m => sel === "all" || m.channel === sel).map(m => {
    const d = document.createElement("div");
    d.className = "m" + (m.thread_ts && m.thread_ts !== m.ts ? " t" : "");
    const u = document.createElement("span"); u.className = "u"; u.textContent = m.user;
    const c = document.createElement("span"); c.className = "c"; c.textContent = "#" + m.channel;
    const ts = document.createElement("span"); ts.className = "ts";
    ts.textContent = new Date(parseFloat(m.ts) * 1000).toLocaleTimeString();
    const x = document.createElement("div"); x.className = "x"; x.textContent = m.text;
    d.append(u, c, ts, x);
    return d;
  });
  const atBottom = innerHeight + scrollY >= document.body.scrollHeight - 40;
  feed.replaceChildren(...rows);
  if (atBottom) scrollTo(0, document.body.scrollHeight);
}
load(); setInterval(load, 2000);
</script>"""


class SimState:
    """The workspace plus the faults queued against it."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.workspace = Workspace.from_fixture()
        self.faults: list[dict] = []
        self.calls: list[dict] = []

    def reset(self) -> None:
        with self.lock:
            self.workspace = Workspace.from_fixture()
            self.faults = []
            self.calls = []

    def take_fault(self, method: str) -> dict | None:
        with self.lock:
            for f in self.faults:
                if f["method"] in (method, "*") and f["count"] > 0:
                    f["count"] -= 1
                    return f
        return None


def make_handler(state: SimState):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):  # quiet by default
            pass

        def _send(self, status: int, body: dict, headers: dict | None = None) -> None:
            raw = json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            for k, v in (headers or {}).items():
                self.send_header(k, v)
            self.end_headers()
            self.wfile.write(raw)

        def _params(self) -> dict:
            parsed = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            length = int(self.headers.get("Content-Length") or 0)
            if length:
                body = self.rfile.read(length).decode()
                if "json" in (self.headers.get("Content-Type") or ""):
                    params.update(json.loads(body or "{}"))
                else:
                    params.update({k: v[0] for k, v in parse_qs(body).items()})
            return params

        def do_GET(self):
            self._handle()

        def do_POST(self):
            self._handle()

        def _handle(self) -> None:
            path = urlparse(self.path).path
            params = self._params()
            if path == "/":
                raw = VIEWER.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if path.startswith("/_sim/"):
                return self._admin(path[len("/_sim/"):], params)
            if not path.startswith("/api/"):
                return self._send(404, {"ok": False, "error": "unknown_method"})
            method = path[len("/api/"):]
            if method not in SCOPES:
                return self._send(200, {"ok": False, "error": "unknown_method"})
            state.calls.append({"method": method, "params": params})

            fault = state.take_fault(method)
            if fault:
                if fault["mode"] == "rate_limit":
                    return self._send(
                        429, {"ok": False, "error": "ratelimited"},
                        {"Retry-After": str(fault.get("retry_after", 1))},
                    )
                if fault["mode"] == "server_error":
                    return self._send(500, {"ok": False, "error": "internal_error"})

            auth = self.headers.get("Authorization", "")
            token = auth[7:] if auth.startswith("Bearer ") else params.get("token")
            ws = state.workspace
            try:
                grant = ws.auth(token)
                need = SCOPES[method]
                if need and need not in grant["scopes"]:
                    return self._send(200, {"ok": False, "error": "missing_scope", "needed": need,
                                            "provided": ",".join(grant["scopes"])})
                self._send(200, {"ok": True, **self._dispatch(ws, method, params, grant)})
            except SlackError as e:
                self._send(200, {"ok": False, "error": e.code})

        def _dispatch(self, ws: Workspace, method: str, p: dict, grant: dict) -> dict:
            me = grant["user"]
            if method == "auth.test":
                return {"url": f"https://{ws.team['domain']}.slack.com/", "team": ws.team["name"],
                        "team_id": ws.team["id"], "user": ws.users[me]["name"], "user_id": me,
                        "bot_id": "B0SIM0001"}
            if method == "conversations.list":
                chans = sorted(ws.channels.values(), key=lambda c: c["name"])
                return self._page(chans, "channels", p)
            if method == "conversations.info":
                if p.get("channel") not in ws.channels:
                    raise SlackError("channel_not_found")
                return {"channel": ws.channels[p["channel"]]}
            if method == "conversations.history":
                return ws.history(p.get("channel", ""), int(p.get("limit", 100)), p.get("cursor"),
                                  p.get("oldest"), p.get("latest"))
            if method == "conversations.replies":
                return ws.replies(p.get("channel", ""), p.get("ts", ""))
            if method == "conversations.create":
                return {"channel": ws.create_channel(p.get("name", ""))}
            if method == "users.list":
                return self._page(list(ws.users.values()), "members", p)
            if method == "users.info":
                if p.get("user") not in ws.users:
                    raise SlackError("user_not_found")
                return {"user": ws.users[p["user"]]}
            if method == "chat.postMessage":
                msg = ws.post(p.get("channel", ""), p.get("text", ""), me, p.get("thread_ts"))
                return {"channel": p["channel"], "ts": msg["ts"], "message": msg}
            if method == "chat.update":
                msg = ws.update(p.get("channel", ""), p.get("ts", ""), p.get("text", ""))
                return {"channel": p["channel"], "ts": msg["ts"], "text": msg["text"]}
            if method == "reactions.add":
                ws.react(p.get("channel", ""), p.get("timestamp", ""), p.get("name", ""), me)
                return {}
            raise SlackError("unknown_method")

        @staticmethod
        def _page(items: list, key: str, p: dict) -> dict:
            limit = int(p.get("limit", 100))
            start = int(p.get("cursor") or 0)
            more = start + limit < len(items)
            return {key: items[start:start + limit],
                    "response_metadata": {"next_cursor": str(start + limit) if more else ""}}

        def _admin(self, action: str, p: dict) -> None:
            if action == "reset":
                state.reset()
                return self._send(200, {"ok": True})
            if action == "fault":
                state.faults.append({"method": p.get("method", "*"), "mode": p.get("mode", "rate_limit"),
                                     "count": int(p.get("count", 1)),
                                     "retry_after": int(p.get("retry_after", 1))})
                return self._send(200, {"ok": True})
            if action == "feed":
                ws = state.workspace
                out = []
                for cid, ch in ws.channels.items():
                    for m in ws.messages[cid]:
                        who = ws.users.get(m["user"], {})
                        out.append({"channel": ch["name"], "ts": m["ts"], "thread_ts": m.get("thread_ts"),
                                    "user": who.get("real_name", m["user"]), "text": m["text"]})
                out.sort(key=lambda m: float(m["ts"]))
                return self._send(200, {"ok": True, "messages": out})
            if action == "calls":
                return self._send(200, {"ok": True, "calls": state.calls})
            self._send(404, {"ok": False, "error": "unknown_admin_action"})

    return Handler


def serve(host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    """Build the server. The caller runs serve_forever() or a thread."""
    return ThreadingHTTPServer((host, port), make_handler(SimState()))
