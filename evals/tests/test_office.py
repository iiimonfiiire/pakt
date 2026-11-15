import json
import threading
import urllib.request

import pytest

from pakt_sandbox.cli import call
from pakt_sandbox.office.backends import ScriptedBackend
from pakt_sandbox.office.runner import Office, clean
from pakt_sandbox.slack_sim.server import serve


@pytest.fixture()
def base():
    server = serve("127.0.0.1", 0)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    server.server_close()


def feed(base):
    return json.load(urllib.request.urlopen(f"{base}/_sim/feed"))["messages"]


def test_clean_strips_prefix_quotes_and_passes():
    assert clean('riley: "Ship it!"', "riley") == "Ship it!"
    assert clean("**sam**: Fixed in 2.3.", "sam") == "Fixed in 2.3."
    assert clean("jo: sam: Echoed names.", "sam") == "Echoed names."
    assert clean("docs-feedback\n\njo: Channel echo.", "jo") == "Channel echo."
    assert clean("Hello\n\nthere", "jo") == "Hello\n\nthere"
    assert clean("PASS", "jo") is None
    assert clean("   ", "jo") is None
    assert len(clean("x" * 1000, "kit")) == 400


def test_turns_post_as_different_coworkers(base):
    office = Office(f"{base}/api", ScriptedBackend(["Looks good to me.", "Can we add a link?"]),
                    seed=1, log=lambda *_: None)
    before = len(feed(base))
    office.run(turns=6, interval=0)
    new = feed(base)[before:]
    assert len(new) == 6
    speakers = [m["user"] for m in new]
    assert all(a != b for a, b in zip(speakers, speakers[1:]))  # never the same bot twice in a row


def test_pass_posts_nothing(base):
    office = Office(f"{base}/api", ScriptedBackend(["PASS"]), seed=1, log=lambda *_: None)
    before = len(feed(base))
    office.run(turns=3, interval=0)
    assert len(feed(base)) == before


def test_prompt_includes_channel_history(base):
    backend = ScriptedBackend(["ok"])
    Office(f"{base}/api", backend, seed=2, log=lambda *_: None).turn()
    assert "Recent messages, oldest first" in backend.prompts[0]


def test_backend_failure_does_not_stop_the_run(base):
    class Flaky:
        n = 0

        def chat(self, system, prompt):
            Flaky.n += 1
            if Flaky.n == 1:
                raise TimeoutError("slow model")
            return "back online"

    logs = []
    before = len(feed(base))
    Office(f"{base}/api", Flaky(), seed=3, log=logs.append).run(turns=3, interval=0)
    assert any("turn failed" in line for line in logs)
    assert len(feed(base)) == before + 2


def test_bot_tokens_cannot_create_channels(base):
    res = call(f"{base}/api", "xoxb-sim-riley", "conversations.create", name="x")
    assert res["error"] == "missing_scope"


def test_viewer_page_served(base):
    html = urllib.request.urlopen(f"{base}/").read().decode()
    assert "/_sim/feed" in html


def test_cli_reads_token_from_dotenv(tmp_path, monkeypatch):
    from pakt_sandbox import cli

    (tmp_path / ".env").write_text("SLACK_BOT_TOKEN=xoxb-from-file\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)
    seen = {}

    class Stop(Exception):
        pass

    class FakeOffice:
        def __init__(self, base, backend, seed=None, token=None):
            seen["token"] = token

        def run(self, turns, interval):
            raise Stop

    monkeypatch.setattr("pakt_sandbox.office.runner.Office", FakeOffice)
    with pytest.raises(Stop):
        cli.main(["slack", "office", "--single-token"])
    assert seen["token"] == "xoxb-from-file"
    monkeypatch.delenv("SLACK_BOT_TOKEN", raising=False)  # load_dotenv set it for the process


def test_clean_strips_role_in_display_prefix():
    assert clean("Riley (PM): Ship it.", "sam") == "Ship it."


def test_single_token_mode_posts_with_display_names(base):
    office = Office(f"{base}/api", ScriptedBackend(["Noted."]), seed=1, log=lambda *_: None,
                    token="xoxb-sim-bot")
    before = len(feed(base))
    office.run(turns=4, interval=0)
    new = feed(base)[before:]
    assert len(new) == 4
    assert {m["user"] for m in new} <= {"Riley (PM)", "Sam (Eng)", "Jo (Support)", "Kit (Docs)"}


def test_single_token_prompt_shows_display_names(base):
    backend = ScriptedBackend(["Noted."])
    office = Office(f"{base}/api", backend, seed=1, log=lambda *_: None, token="xoxb-sim-bot")
    office.run(turns=12, interval=0)
    assert any(f"({role}):" in p for p in backend.prompts for role in ("PM", "Eng", "Support", "Docs"))


def test_username_ignored_without_customize_scope(base):
    def post(token, **kw):
        return call(f"{base}/api", token, "chat.postMessage", **kw)

    plain = post("xoxb-sim-riley", channel="C0GEN0001", text="hi", username="Impostor")
    assert "username" not in plain["message"]
    custom = post("xoxb-sim-bot", channel="C0GEN0001", text="hi", username="Custom")
    assert custom["message"]["username"] == "Custom"


def test_not_in_channel_joins_then_retries(monkeypatch):
    from pakt_sandbox.office import runner

    seen = []

    def fake(base, token, method, **params):
        seen.append(method)
        if seen.count("conversations.history") == 1 and method == "conversations.history":
            return {"ok": False, "error": "not_in_channel"}
        return {"ok": True, "messages": []}

    monkeypatch.setattr(runner, "call", fake)
    office = Office("http://x/api", ScriptedBackend(["x"]), token="t", log=lambda *_: None)
    office._call(office.personas[0], "conversations.history", channel="C1")
    assert seen == ["conversations.history", "conversations.join", "conversations.history"]
