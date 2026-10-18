"""Provider clients, provider selection, fallback, and cache separation. Every HTTP call is faked."""

import json
import logging
import ssl
import urllib.error

import pytest

from pakt.llm import CachedClient, CacheMiss, Completion
from pakt.providers import (
    AllProvidersFailed,
    FallbackClient,
    GeminiClient,
    GroqClient,
    NoProviderKey,
    ProviderError,
    Route,
    build_client,
    is_retryable,
    load_provider_settings,
)

REQ = dict(model="m", system="Be brief.", user="Say hi.", max_tokens=50, temperature=0.0)


class FakeTransport:
    """Replays (status, headers, body) tuples or raises exceptions, and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, request, timeout):
        self.requests.append(request)
        nxt = self.responses.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        status, headers, body = nxt
        return status, headers, json.dumps(body).encode() if isinstance(body, (dict, list)) else body


def gemini_ok(text="hi", model="gemini-test-001"):
    return (200, {}, {
        "candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]}, "finishReason": "STOP"}],
        "usageMetadata": {"promptTokenCount": 12, "candidatesTokenCount": 3, "thoughtsTokenCount": 5},
        "modelVersion": model,
    })


def groq_ok(text="hi", model="openai/gpt-oss-120b"):
    return (200, {}, {
        "model": model,
        "choices": [{"message": {"role": "assistant", "content": text}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 4},
    })


def body_of(request):
    return json.loads(request.data)


def no_sleep(_):
    pass


# ------------------------------------------------------------ Gemini


def test_gemini_request_shape_and_key_in_header():
    t = FakeTransport(gemini_ok())
    c = GeminiClient(api_key="k-123", transport=t, sleep=no_sleep)
    c.complete(**{**REQ, "model": "gemini-x"})
    [req] = t.requests
    assert req.full_url == "https://generativelanguage.googleapis.com/v1beta/models/gemini-x:generateContent"
    assert "k-123" not in req.full_url
    assert req.get_header("X-goog-api-key") == "k-123"
    assert req.get_method() == "POST"
    body = body_of(req)
    assert body["systemInstruction"] == {"parts": [{"text": "Be brief."}]}
    assert body["contents"] == [{"role": "user", "parts": [{"text": "Say hi."}]}]
    assert body["generationConfig"] == {"maxOutputTokens": 50, "temperature": 0.0}


def test_gemini_omits_unset_temperature_and_strips_models_prefix():
    c = GeminiClient(api_key="k", thinking_budget=0)
    url, _, payload = c.build_request(**{**REQ, "model": "models/gemini-x", "temperature": None, "system": ""})
    assert url.endswith("/models/gemini-x:generateContent")
    assert "temperature" not in payload["generationConfig"]
    assert payload["generationConfig"]["thinkingConfig"] == {"thinkingBudget": 0}
    assert "systemInstruction" not in payload


def test_gemini_parses_text_usage_and_answering_model():
    c = GeminiClient(api_key="k", transport=FakeTransport(gemini_ok("hello")), sleep=no_sleep)
    out = c.complete(**{**REQ, "model": "gemini-alias"})
    assert out.text == "hello"
    assert out.model == "gemini-test-001" and out.provider == "gemini"
    assert (out.input_tokens, out.output_tokens) == (12, 8)


def test_gemini_empty_answer_at_token_limit_fails_loudly():
    body = {"candidates": [{"content": {"parts": []}, "finishReason": "MAX_TOKENS"}], "usageMetadata": {}}
    c = GeminiClient(api_key="k", transport=FakeTransport((200, {}, body)), sleep=no_sleep)
    with pytest.raises(ProviderError, match="MAX_TOKENS.*thinking_budget") as info:
        c.complete(**REQ)
    assert not info.value.retryable


def test_gemini_blocked_prompt_is_not_retryable():
    c = GeminiClient(api_key="k", transport=FakeTransport((200, {}, {"promptFeedback": {"blockReason": "SAFETY"}})))
    with pytest.raises(ProviderError, match="SAFETY") as info:
        c.complete(**REQ)
    assert not info.value.retryable


# ------------------------------------------------------------ Groq


def test_groq_request_shape():
    t = FakeTransport(groq_ok())
    c = GroqClient(api_key="g-456", transport=t, sleep=no_sleep, reasoning_effort="low")
    c.complete(**{**REQ, "model": "openai/gpt-oss-120b"})
    [req] = t.requests
    assert req.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert req.get_header("Authorization") == "Bearer g-456"
    assert req.get_header("User-agent") == "pakt"
    body = body_of(req)
    assert body["model"] == "openai/gpt-oss-120b"
    assert body["messages"] == [{"role": "system", "content": "Be brief."}, {"role": "user", "content": "Say hi."}]
    assert body["max_completion_tokens"] == 50 and body["temperature"] == 0.0
    assert body["reasoning_effort"] == "low"


def test_groq_parses_text_usage_and_model():
    c = GroqClient(api_key="g", transport=FakeTransport(groq_ok("yo", model="served-model")), sleep=no_sleep)
    out = c.complete(**REQ)
    assert (out.text, out.model, out.provider) == ("yo", "served-model", "groq")
    assert (out.input_tokens, out.output_tokens) == (20, 4)


def test_groq_omits_unset_temperature_and_system():
    _, _, payload = GroqClient(api_key="g").build_request(**{**REQ, "temperature": None, "system": ""})
    assert "temperature" not in payload and "reasoning_effort" not in payload
    assert payload["messages"] == [{"role": "user", "content": "Say hi."}]


def test_groq_empty_answer_at_length_fails_loudly():
    body = {"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
    c = GroqClient(api_key="g", transport=FakeTransport((200, {}, body)))
    with pytest.raises(ProviderError, match="reasoning_effort"):
        c.complete(**REQ)


# ------------------------------------------------------------ retries inside one provider


def test_retries_server_errors_then_succeeds():
    sleeps = []
    t = FakeTransport((503, {}, {"error": {"message": "overloaded"}}), groq_ok("ok"))
    out = GroqClient(api_key="g", transport=t, sleep=sleeps.append).complete(**REQ)
    assert out.text == "ok" and len(t.requests) == 2 and len(sleeps) == 1


def test_honors_retry_after_header_and_gemini_retry_delay():
    sleeps = []
    t = FakeTransport((429, {"Retry-After": "3"}, b""), (429, {}, {"error": {"details": [{"retryDelay": "7s"}]}}), gemini_ok())
    GeminiClient(api_key="k", transport=t, sleep=sleeps.append).complete(**REQ)
    assert sleeps == [3.0, 7.0]


def test_long_retry_after_gives_up_on_the_provider_at_once():
    t = FakeTransport((429, {"retry-after": "600"}, {"error": {"message": "quota"}}))
    c = GroqClient(api_key="g", transport=t, sleep=no_sleep, max_retries=3)
    with pytest.raises(ProviderError, match="HTTP 429") as info:
        c.complete(**REQ)
    assert info.value.retryable and len(t.requests) == 1


def test_timeouts_exhaust_retries_as_retryable():
    t = FakeTransport(TimeoutError("slow"), urllib.error.URLError("reset"), TimeoutError("slow"))
    with pytest.raises(ProviderError, match="network error") as info:
        GroqClient(api_key="g", transport=t, sleep=no_sleep, max_retries=2).complete(**REQ)
    assert info.value.retryable and len(t.requests) == 3


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_do_not_retry(status):
    t = FakeTransport((status, {}, {"error": {"message": "nope"}}))
    with pytest.raises(ProviderError, match=f"HTTP {status}: nope") as info:
        GeminiClient(api_key="k", transport=t, sleep=no_sleep).complete(**REQ)
    assert not info.value.retryable and len(t.requests) == 1


def test_tls_errors_are_not_retryable():
    t = FakeTransport(urllib.error.URLError(ssl.SSLCertVerificationError("bad cert")))
    with pytest.raises(ProviderError, match="TLS") as info:
        GroqClient(api_key="g", transport=t, sleep=no_sleep).complete(**REQ)
    assert not info.value.retryable


def test_anthropic_style_errors_are_classified():
    RateLimitError = type("RateLimitError", (Exception,), {})
    APIStatusError = type("APIStatusError", (Exception,), {})
    bad_request = APIStatusError("bad")
    bad_request.status_code = 400
    overloaded = APIStatusError("busy")
    overloaded.status_code = 529
    assert is_retryable(RateLimitError("slow down"))
    assert is_retryable(overloaded)
    assert not is_retryable(bad_request)
    assert not is_retryable(CacheMiss("miss"))
    assert not is_retryable(ValueError("bug"))


# ------------------------------------------------------------ settings and provider selection


def test_settings_defaults_and_config_tables():
    s = load_provider_settings({
        "providers": {"order": ["groq", "gemini"], "groq": {"judge": "groq-judge", "reasoning_effort": "low"}},
    })
    assert s.order == ["groq", "gemini"] and s.order_origin == "config.toml"
    assert s.model("groq", "judge") == "groq-judge"
    assert s.model("groq", "review") == "openai/gpt-oss-120b"
    assert s.model("gemini", "review") == "gemini-3.6-flash"
    assert s.options["groq"] == {"reasoning_effort": "low"}


def test_env_overrides_order_and_models(monkeypatch):
    monkeypatch.setenv("PAKT_PROVIDERS", " Anthropic , groq,groq")
    monkeypatch.setenv("PAKT_GEMINI_REVIEW_MODEL", "gemini-env")
    monkeypatch.setenv("PAKT_REVIEW_MODEL", "claude-env")
    s = load_provider_settings({"providers": {"order": ["gemini"]}})
    assert s.order == ["anthropic", "groq"] and s.order_origin == "PAKT_PROVIDERS"
    assert s.model("gemini", "review") == "gemini-env"
    # The pre-provider variables named Claude models, so they still apply to anthropic only.
    assert s.model("anthropic", "review") == "claude-env"
    assert s.model("groq", "review") == "openai/gpt-oss-120b"


def test_legacy_model_tables_apply_to_anthropic():
    s = load_provider_settings({"models": {"generator": "claude-old"}, "review": {"model": "claude-rev"}})
    assert s.model("anthropic", "generator") == "claude-old"
    assert s.model("anthropic", "review") == "claude-rev"
    assert s.model("gemini", "generator") == "gemini-3.6-flash"


def test_unknown_provider_is_an_error(monkeypatch):
    monkeypatch.setenv("PAKT_PROVIDERS", "gemini,openai")
    with pytest.raises(ValueError, match="unknown provider"):
        load_provider_settings({})


def _factory(clients):
    return lambda provider, key, settings: clients[provider]


def test_providers_without_keys_are_skipped(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("GEMINI_API_KEY", "your-api-key-here")
    s = load_provider_settings({})
    chain = build_client(s, "judge", factory=_factory({"groq": object()}))
    assert [r.provider for r in chain.routes] == ["groq"]
    assert chain.primary.model == "openai/gpt-oss-120b"
    assert s.primary("judge") == ("groq", "openai/gpt-oss-120b")
    assert "gemini (gemini-3.6-flash, no key: skipped)" in s.describe("judge")


def test_no_keys_at_all_names_every_key():
    with pytest.raises(NoProviderKey, match="GEMINI_API_KEY, GROQ_API_KEY, ANTHROPIC_API_KEY"):
        build_client(load_provider_settings({}), "review")


def test_cache_only_chain_needs_no_key(tmp_path):
    chain = build_client(load_provider_settings({}), "review", tmp_path, "reviews", cache_only=True)
    assert [r.provider for r in chain.routes] == ["gemini", "groq", "anthropic"]
    with pytest.raises(CacheMiss):
        chain.complete(**REQ)


# ------------------------------------------------------------ fallback


class Scripted:
    """A provider client that replays results or exceptions."""

    def __init__(self, provider, *outcomes):
        self.provider = provider
        self.outcomes = list(outcomes)
        self.calls = []

    def complete(self, *, model, system, user, max_tokens, temperature):
        self.calls.append(model)
        nxt = self.outcomes.pop(0)
        if isinstance(nxt, BaseException):
            raise nxt
        return Completion(text=nxt, model=model, provider=self.provider, input_tokens=1, output_tokens=1)


def chain_of(*clients, models=None):
    models = models or {}
    return FallbackClient([Route(c.provider, models.get(c.provider, f"{c.provider}-model"), c) for c in clients], "judge")


@pytest.mark.parametrize("failure", [
    ProviderError("gemini", "HTTP 429: quota", status=429, retryable=True),
    ProviderError("gemini", "HTTP 503: busy", status=503, retryable=True),
    ProviderError("gemini", "network error: timed out", retryable=True),
    TimeoutError("read timed out"),
])
def test_transient_failures_fall_back(failure, caplog):
    gemini, groq = Scripted("gemini", failure), Scripted("groq", "from groq")
    chain = chain_of(gemini, groq)
    with caplog.at_level(logging.INFO, logger="pakt.providers"):
        out = chain.complete(**REQ)
    assert out.text == "from groq" and out.provider == "groq" and out.model == "groq-model"
    assert gemini.calls == ["gemini-model"] and groq.calls == ["groq-model"]
    assert chain.fallbacks == 1 and chain.served == {"groq/groq-model": 1}
    assert "falling back to groq" in caplog.text and "judge served by groq" in caplog.text


@pytest.mark.parametrize("status", [400, 401, 403, 404])
def test_client_errors_do_not_fall_back(status):
    gemini = Scripted("gemini", ProviderError("gemini", f"HTTP {status}", status=status, retryable=False))
    groq = Scripted("groq", "never")
    with pytest.raises(ProviderError, match=f"HTTP {status}"):
        chain_of(gemini, groq).complete(**REQ)
    assert groq.calls == []


def test_every_provider_failing_raises_with_each_reason():
    chain = chain_of(
        Scripted("gemini", ProviderError("gemini", "HTTP 429", retryable=True)),
        Scripted("groq", ProviderError("groq", "HTTP 503", retryable=True)),
    )
    with pytest.raises(AllProvidersFailed, match="gemini: HTTP 429.*groq: HTTP 503"):
        chain.complete(**REQ)


def test_chain_ignores_the_requested_model_and_uses_each_route_model():
    gemini = Scripted("gemini", "ok")
    chain_of(gemini, models={"gemini": "gemini-judge"}).complete(**{**REQ, "model": "claude-sonnet-5-5"})
    assert gemini.calls == ["gemini-judge"]


def test_fallback_through_real_http_clients():
    gemini = GeminiClient(api_key="k", transport=FakeTransport((429, {}, b"{}"), (429, {}, b"{}")), sleep=no_sleep, max_retries=1)
    groq = GroqClient(api_key="g", transport=FakeTransport(groq_ok("rescued")), sleep=no_sleep)
    out = FallbackClient([Route("gemini", "gm", gemini), Route("groq", "gq", groq)]).complete(**REQ)
    assert out.text == "rescued" and out.provider == "groq"


# ------------------------------------------------------------ cache separation


def test_cache_entries_are_separated_by_provider(tmp_path):
    a = CachedClient(Scripted("gemini", "from gemini"), tmp_path, "judgments")
    b = CachedClient(Scripted("groq", "from groq"), tmp_path, "judgments")
    assert a.complete(**REQ).text == "from gemini"
    assert b.lookup(**REQ) is None
    assert b.complete(**REQ).text == "from groq"
    assert a.lookup(**REQ).text == "from gemini"
    assert (tmp_path / "judgments" / "gemini").is_dir() and (tmp_path / "judgments" / "groq").is_dir()
    hit = b.lookup(**REQ)
    assert hit.cached and hit.provider == "groq"


def test_fallback_answer_is_cached_under_the_provider_that_served(tmp_path):
    gemini = Scripted("gemini", ProviderError("gemini", "HTTP 429", retryable=True))
    groq = Scripted("groq", "from groq")
    chain = FallbackClient([
        Route("gemini", "gm", CachedClient(gemini, tmp_path, "judgments")),
        Route("groq", "gq", CachedClient(groq, tmp_path, "judgments")),
    ])
    first = chain.complete(**REQ)
    assert not first.cached and first.provider == "groq"
    assert not (tmp_path / "judgments" / "gemini").exists()
    # A rerun reuses the groq answer from the cache and calls nobody.
    second = chain.complete(**REQ)
    assert second.cached and second.provider == "groq" and second.text == "from groq"
    assert gemini.calls == ["gm"] and groq.calls == ["gq"]
    # A cache-only chain finds the same answer without any key.
    cache_only = build_client(load_provider_settings({}), "judge", tmp_path, "judgments", cache_only=True)
    cache_only.routes = [Route(r.provider, {"gemini": "gm", "groq": "gq"}.get(r.provider, r.model), r.client) for r in cache_only.routes]
    assert cache_only.complete(**REQ).text == "from groq"


# ------------------------------------------------------------ provenance in results and reports


class Canned:
    def __init__(self, provider, text="{}", fail=None):
        self.provider, self.text, self.fail = provider, text, fail

    def complete(self, *, model, system, user, max_tokens, temperature):
        if self.fail:
            raise self.fail
        return Completion(text=self.text, model=f"{model}-served", provider=self.provider, input_tokens=5, output_tokens=5)


@pytest.fixture
def gemini_down_groq_up(monkeypatch, tmp_path):
    from .conftest import REPO_ROOT

    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt.config._load_dotenv", lambda root: None)
    monkeypatch.setattr("pakt_evals.config._load_dotenv", lambda root: None)
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    clients = {
        "gemini": Canned("gemini", fail=ProviderError("gemini", "HTTP 429", status=429, retryable=True)),
        "groq": Canned("groq", "<rewrite>Fine.</rewrite>"),
    }
    monkeypatch.setattr("pakt.providers.make_client", lambda provider, key, settings: clients[provider])
    return tmp_path


def _with_cache(monkeypatch, cli_mod, cache_dir):
    real = cli_mod.load_config

    def load():
        cfg = real()
        cfg.cache_dir = cache_dir
        return cfg

    monkeypatch.setattr(cli_mod, "load_config", load)


def test_eval_run_records_provider_and_model(gemini_down_groq_up, monkeypatch, capsys):
    from pakt_evals import cli as eval_cli

    tmp = gemini_down_groq_up
    _with_cache(monkeypatch, eval_cli, tmp / "cache")
    code = eval_cli.main(["run", "--no-judge", "--variants", "v1", "--ids", "kb-01", "--out", str(tmp / "r")])
    assert code == 0
    [item] = [json.loads(l) for l in (tmp / "r" / "items.jsonl").read_text().splitlines()]
    assert item["gen_provider"] == "groq" and item["gen_model"] == "openai/gpt-oss-120b-served"
    meta = json.loads((tmp / "r" / "summary.json").read_text())["meta"]
    assert meta["generator"] == "groq/openai/gpt-oss-120b-served x1"
    assert meta["provider order"].startswith("gemini, groq, anthropic")
    report = (tmp / "r" / "report.md").read_text()
    assert "groq/openai/gpt-oss-120b-served" in report
    assert "falling back to groq" in capsys.readouterr().err


def test_review_eval_records_provider_and_model(gemini_down_groq_up, monkeypatch):
    from pakt_evals import cli as eval_cli

    tmp = gemini_down_groq_up
    _with_cache(monkeypatch, eval_cli, tmp / "cache")
    assert eval_cli.main(["review-eval", "--mode", "model", "--ids", "kb-r01", "--out", str(tmp / "r")]) == 0
    meta = json.loads((tmp / "r" / "summary.json").read_text())["meta"]
    assert meta["review model"] == "groq/openai/gpt-oss-120b-served x1"
    assert "groq/openai/gpt-oss-120b-served" in (tmp / "r" / "report.md").read_text()


def test_pakt_review_report_names_provider_and_model(gemini_down_groq_up, monkeypatch, capsys):
    from pakt import cli as pakt_cli

    tmp = gemini_down_groq_up
    monkeypatch.chdir(tmp)
    monkeypatch.setattr(pakt_cli, "model_client", lambda providers, role, cache_dir, ns, cache_only=False:
                        build_client(providers, role, tmp / "cache", ns, cache_only=cache_only))
    (tmp / "page.md").write_text("Fine.\n")
    pakt_cli.main(["review", "page.md", "--model", "--json"])
    data = json.loads(capsys.readouterr().out)
    assert data["provider"] == "groq" and data["model"] == "openai/gpt-oss-120b-served"


def test_pakt_review_bad_key_fails_loudly_without_fallback(monkeypatch, tmp_path, capsys):
    from pakt import cli as pakt_cli

    from .conftest import REPO_ROOT

    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt.config._load_dotenv", lambda root: None)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GEMINI_API_KEY", "bad")
    monkeypatch.setenv("GROQ_API_KEY", "fake")
    groq = Canned("groq")
    clients = {"gemini": Canned("gemini", fail=ProviderError("gemini", "HTTP 400: API key not valid", status=400)), "groq": groq}
    monkeypatch.setattr("pakt.providers.make_client", lambda provider, key, settings: clients[provider])
    monkeypatch.setattr(pakt_cli, "model_client", lambda providers, role, cache_dir, ns, cache_only=False:
                        build_client(providers, role, tmp_path / "cache", ns))
    (tmp_path / "page.md").write_text("Fine.\n")
    assert pakt_cli.main(["review", "page.md", "--model"]) == 2
    assert "API key not valid" in capsys.readouterr().err
