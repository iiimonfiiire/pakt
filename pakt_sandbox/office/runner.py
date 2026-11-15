"""Turn loop: coworker bots read a channel and reply through the Slack Web API."""

from __future__ import annotations

import random
import re
import time

from ..cli import call
from .backends import Backend
from .personas import PERSONAS, Persona

MAX_CHARS = 400
CONTEXT = 8


def clean(raw: str, handle: str) -> str | None:
    """Strip model habits. Returns None when the bot passes or says nothing."""
    text = raw.strip()
    names = "|".join(re.escape(n) for n in {handle, *(p.handle for p in PERSONAS)})
    text = re.sub(rf"^(?:#?[\w-]+\n+)?(?:(?:\*\*)?(?:{names})(?:\*\*)?\s*:\s*)+", "", text, flags=re.I)
    text = text.strip().strip('"').strip()
    if not text or text.upper().startswith("PASS"):
        return None
    return text[:MAX_CHARS]


class Office:
    def __init__(self, base: str, backend: Backend, personas: list[Persona] | None = None,
                 seed: int | None = None, log=print):
        self.base, self.backend, self.log = base, backend, log
        self.personas = personas or PERSONAS
        self.rng = random.Random(seed)
        self.last_speaker: str | None = None
        self.names: dict[str, str] = {}

    def _call(self, p: Persona, method: str, **params) -> dict:
        res = call(self.base, p.token, method, **params)
        if not res.get("ok"):
            raise RuntimeError(f"{method} failed for {p.handle}: {res.get('error')}")
        return res

    def _name(self, p: Persona, user_id: str) -> str:
        if not self.names:
            for u in self._call(p, "users.list")["members"]:
                self.names[u["id"]] = u["name"].split(".")[0]
        return self.names.get(user_id, user_id)

    def _pick(self) -> Persona:
        pool = [p for p in self.personas if p.handle != self.last_speaker] or self.personas
        return self.rng.choice(pool)

    def turn(self) -> dict | None:
        """Run one bot turn. Returns the posted message, or None on a pass."""
        p = self._pick()
        channels = {c["name"]: c["id"] for c in self._call(p, "conversations.list")["channels"]}
        name = self.rng.choice([c for c in p.channels if c in channels])
        cid = channels[name]
        recent = self._call(p, "conversations.history", channel=cid, limit=CONTEXT)["messages"]
        recent.reverse()  # oldest first
        target = recent[-1] if recent else None
        if target:
            lines = [f"{self._name(p, m['user'])}: {m['text']}" for m in recent]
            prompt = (
                f"Channel #{name}. Recent messages, oldest first:\n" + "\n".join(lines)
                + f"\n\nWrite your next message as {p.handle}."
            )
        else:
            prompt = f"Channel #{name} is empty. Start a conversation as {p.handle}."
        text = clean(self.backend.chat(p.system_prompt(), prompt), p.handle)
        self.last_speaker = p.handle
        if text is None:
            self.log(f"[#{name}] {p.handle}: (pass)")
            return None
        params = {"channel": cid, "text": text}
        if target and (target.get("reply_count") or self.rng.random() < 0.3):
            params["thread_ts"] = target["thread_ts"] if "thread_ts" in target else target["ts"]
        msg = self._call(p, "chat.postMessage", **params)["message"]
        self.log(f"[#{name}] {p.handle}: {text}")
        return msg

    def run(self, turns: int | None = None, interval: float = 5.0) -> None:
        n = 0
        while turns is None or n < turns:
            try:
                self.turn()
            except Exception as e:  # keep the office alive through slow or failed model calls
                self.log(f"turn failed: {e}")
            n += 1
            if turns is None or n < turns:
                time.sleep(interval)
