"""In-memory Slack workspace used by the simulator."""

from __future__ import annotations

import copy
import itertools
import json
import threading
import time
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "workspace.json"


class SlackError(Exception):
    """A Slack API error. `code` is the value of the `error` field."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class Workspace:
    def __init__(self, data: dict):
        self._lock = threading.RLock()
        self._seq = itertools.count(1)
        self.team = data["team"]
        self.users = {u["id"]: u for u in data["users"]}
        self.tokens = dict(data["tokens"])  # token -> {"user": id, "scopes": [...]}
        self.channels: dict[str, dict] = {}
        self.messages: dict[str, list[dict]] = {}
        self._seed_time = time.time()
        for ch in data["channels"]:
            self._add_channel(ch["id"], ch["name"], ch.get("topic", ""))
            for m in ch.get("messages", []):
                self._seed_message(ch["id"], m)

    @classmethod
    def from_fixture(cls, path: Path | str = FIXTURE) -> "Workspace":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def _add_channel(self, cid: str, name: str, topic: str = "") -> None:
        self.channels[cid] = {
            "id": cid, "name": name, "is_channel": True, "is_private": False,
            "is_member": True, "topic": {"value": topic},
        }
        self.messages[cid] = []

    def _ts(self, epoch: float | None = None) -> str:
        """A Slack timestamp: unique per message, so it doubles as the message ID."""
        when = time.time() if epoch is None else epoch
        return f"{int(when)}.{next(self._seq):06d}"

    def _seed_message(self, cid: str, m: dict, parent_ts: str | None = None) -> None:
        epoch = self._seed_time - m.get("hours_ago", 0) * 3600
        msg = {"type": "message", "user": m["user"], "text": m["text"], "ts": self._ts(epoch)}
        if "files" in m:
            msg["files"] = copy.deepcopy(m["files"])
        if parent_ts:
            msg["thread_ts"] = parent_ts
        self.messages[cid].append(msg)
        replies = m.get("replies", [])
        if replies:
            msg["thread_ts"] = msg["ts"]
            for r in replies:
                self._seed_message(cid, r, parent_ts=msg["ts"])
            self._refresh_thread(cid, msg["ts"])

    def _refresh_thread(self, cid: str, thread_ts: str) -> None:
        parent = self._find(cid, thread_ts)
        kids = [x for x in self.messages[cid] if x.get("thread_ts") == thread_ts and x["ts"] != thread_ts]
        parent["reply_count"] = len(kids)
        parent["latest_reply"] = kids[-1]["ts"] if kids else None

    def _find(self, cid: str, ts: str) -> dict:
        for m in self.messages[cid]:
            if m["ts"] == ts:
                return m
        raise SlackError("message_not_found")

    def _channel(self, cid: str) -> dict:
        if cid not in self.channels:
            raise SlackError("channel_not_found")
        return self.channels[cid]

    # --- API operations ---

    def auth(self, token: str | None) -> dict:
        if not token or token not in self.tokens:
            raise SlackError("invalid_auth")
        return self.tokens[token]

    def history(self, cid, limit=100, cursor=None, oldest=None, latest=None) -> dict:
        with self._lock:
            self._channel(cid)
            top = [m for m in self.messages[cid] if m.get("thread_ts", m["ts"]) == m["ts"]]
            if oldest:
                top = [m for m in top if float(m["ts"]) > float(oldest)]
            if latest:
                top = [m for m in top if float(m["ts"]) < float(latest)]
            top.sort(key=lambda m: float(m["ts"]), reverse=True)
            start = int(cursor) if cursor else 0
            page = top[start:start + limit]
            more = start + limit < len(top)
            return {
                "messages": copy.deepcopy(page),
                "has_more": more,
                "response_metadata": {"next_cursor": str(start + limit) if more else ""},
            }

    def replies(self, cid: str, ts: str) -> dict:
        with self._lock:
            self._channel(cid)
            parent = self._find(cid, ts)
            thread = [m for m in self.messages[cid] if m.get("thread_ts") == ts]
            thread = thread or [parent]
            thread.sort(key=lambda m: float(m["ts"]))
            return {"messages": copy.deepcopy(thread), "has_more": False}

    def post(self, cid: str, text: str, user: str, thread_ts: str | None = None,
             username: str | None = None) -> dict:
        with self._lock:
            self._channel(cid)
            if not text:
                raise SlackError("no_text")
            msg = {"type": "message", "user": user, "text": text, "ts": self._ts()}
            if username:
                msg["username"] = username
                msg["bot_id"] = "B0SIM0001"
            if thread_ts:
                self._find(cid, thread_ts)
                msg["thread_ts"] = thread_ts
            self.messages[cid].append(msg)
            if thread_ts:
                self._refresh_thread(cid, thread_ts)
            return copy.deepcopy(msg)

    def update(self, cid: str, ts: str, text: str) -> dict:
        with self._lock:
            self._channel(cid)
            m = self._find(cid, ts)
            m["text"] = text
            m["edited"] = {"ts": self._ts()}
            return copy.deepcopy(m)

    def react(self, cid: str, ts: str, name: str, user: str) -> None:
        with self._lock:
            self._channel(cid)
            m = self._find(cid, ts)
            reactions = m.setdefault("reactions", [])
            for r in reactions:
                if r["name"] == name:
                    if user in r["users"]:
                        raise SlackError("already_reacted")
                    r["users"].append(user)
                    r["count"] += 1
                    return
            reactions.append({"name": name, "users": [user], "count": 1})

    def create_channel(self, name: str) -> dict:
        with self._lock:
            if any(c["name"] == name for c in self.channels.values()):
                raise SlackError("name_taken")
            cid = f"C{next(self._seq):08d}"
            self._add_channel(cid, name)
            return copy.deepcopy(self.channels[cid])
