import json
import threading
import urllib.error
import urllib.request

import pytest

from pakt_sandbox.cli import call, seed
from pakt_sandbox.slack_sim.server import serve

TOKEN = "xoxb-sim-bot"


@pytest.fixture()
def base():
    server = serve("127.0.0.1", 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    root = f"http://127.0.0.1:{server.server_address[1]}"
    yield root
    server.shutdown()
    server.server_close()


def api(base, method, token=TOKEN, **params):
    return call(f"{base}/api", token, method, **params)


def admin(base, action, **params):
    req = urllib.request.Request(
        f"{base}/_sim/{action}", data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"},
    )
    return json.load(urllib.request.urlopen(req))


def channel_id(base, name):
    chans = api(base, "conversations.list")["channels"]
    return next(c["id"] for c in chans if c["name"] == name)


def test_auth_test_and_bad_token(base):
    assert api(base, "auth.test")["user"] == "pakt-bot"
    assert api(base, "auth.test", token="nope") == {"ok": False, "error": "invalid_auth"}


def test_missing_scope(base):
    res = api(base, "chat.postMessage", token="xoxb-sim-readonly", channel="C0REL0001", text="x")
    assert res["error"] == "missing_scope"
    assert res["needed"] == "chat:write"


def test_history_newest_first_and_paginates(base):
    cid = channel_id(base, "support-answers")
    page1 = api(base, "conversations.history", channel=cid, limit=2)
    assert len(page1["messages"]) == 2
    assert page1["has_more"] is True
    stamps = [float(m["ts"]) for m in page1["messages"]]
    assert stamps == sorted(stamps, reverse=True)
    page2 = api(base, "conversations.history", channel=cid, limit=2,
                cursor=page1["response_metadata"]["next_cursor"])
    assert len(page2["messages"]) == 1
    assert page2["has_more"] is False


def test_history_hides_thread_replies_but_replies_returns_them(base):
    cid = channel_id(base, "releases")
    top = api(base, "conversations.history", channel=cid)["messages"]
    assert all(m.get("thread_ts", m["ts"]) == m["ts"] for m in top)
    parent = next(m for m in top if m.get("reply_count"))
    assert parent["reply_count"] == 2
    thread = api(base, "conversations.replies", channel=cid, ts=parent["ts"])["messages"]
    assert len(thread) == 3
    assert thread[0]["ts"] == parent["ts"]


def test_post_update_react_roundtrip(base):
    cid = channel_id(base, "general")
    posted = api(base, "chat.postMessage", channel=cid, text="PAKT review: 8/10")
    ts = posted["ts"]
    api(base, "chat.update", channel=cid, ts=ts, text="PAKT review: 9/10")
    assert api(base, "reactions.add", channel=cid, timestamp=ts, name="white_check_mark")["ok"]
    again = api(base, "reactions.add", channel=cid, timestamp=ts, name="white_check_mark")
    assert again["error"] == "already_reacted"
    msg = api(base, "conversations.history", channel=cid)["messages"][0]
    assert msg["text"] == "PAKT review: 9/10"
    assert msg["reactions"][0]["count"] == 1


def test_errors_match_slack_codes(base):
    assert api(base, "conversations.history", channel="C404")["error"] == "channel_not_found"
    assert api(base, "chat.postMessage", channel="C0GEN0001", text="")["error"] == "no_text"
    assert api(base, "nope.method")["error"] == "unknown_method"


def test_rate_limit_fault_sets_retry_after(base):
    admin(base, "fault", method="conversations.history", mode="rate_limit", count=1, retry_after=7)
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(urllib.request.Request(
            f"{base}/api/conversations.history", data=b"{}",
            headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        ))
    assert info.value.code == 429
    assert info.value.headers["Retry-After"] == "7"
    assert api(base, "conversations.history", channel="C0REL0001")["ok"]


def test_reset_restores_fixture(base):
    api(base, "chat.postMessage", channel="C0GEN0001", text="temp")
    admin(base, "reset")
    assert api(base, "conversations.history", channel="C0GEN0001")["messages"] == []


def test_seed_fills_a_fresh_channel(base):
    api(base, "conversations.create", name="extra")
    assert seed(f"{base}/api", TOKEN) > 0
    assert api(base, "conversations.create", name="extra")["error"] == "name_taken"
