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
