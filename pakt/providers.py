"""Model providers (Gemini, Groq, Anthropic), per-role model selection, and fallback between providers.

Gemini and Groq use their REST APIs through the standard library, so they add no dependencies.
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import ssl
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from .llm import AnthropicClient, CachedClient, CacheMiss, CacheOnlyClient, Completion, LLMClient

log = logging.getLogger("pakt.providers")

ROLES = ("generator", "judge", "review")
PLACEHOLDER_KEYS = {"", "your-api-key-here"}
RETRYABLE_STATUS = {408, 429, 500, 502, 503, 504, 529}
USER_AGENT = "pakt"


class ProviderError(RuntimeError):
    """A failed provider call. `retryable` decides whether the fallback chain may try the next provider."""

    def __init__(self, provider: str, message: str, *, status: int | None = None, retryable: bool = False):
        super().__init__(f"{provider}: {message}")
        self.provider = provider
        self.status = status
        self.retryable = retryable


class AllProvidersFailed(RuntimeError):
    pass


# ------------------------------------------------------------ provider registry


@dataclass(frozen=True)
class ProviderInfo:
    name: str
    key_env: str
    models: dict[str, str]


PROVIDERS: dict[str, ProviderInfo] = {
    "gemini": ProviderInfo("gemini", "GEMINI_API_KEY", {
        "generator": "gemini-3.6-flash", "judge": "gemini-3.6-flash", "review": "gemini-3.6-flash",
    }),
    "groq": ProviderInfo("groq", "GROQ_API_KEY", {
        "generator": "openai/gpt-oss-120b", "judge": "openai/gpt-oss-120b", "review": "openai/gpt-oss-120b",
    }),
    "anthropic": ProviderInfo("anthropic", "ANTHROPIC_API_KEY", {
        "generator": "claude-haiku-4-5-20251001", "judge": "claude-sonnet-5-5", "review": "claude-sonnet-5-5",
    }),
}
DEFAULT_ORDER = ("gemini", "groq", "anthropic")

# Before providers existed, these variables named Claude models. They still override the anthropic models only.
LEGACY_MODEL_ENV = {"generator": "PAKT_GENERATOR_MODEL", "judge": "PAKT_JUDGE_MODEL", "review": "PAKT_REVIEW_MODEL"}


def model_env(provider: str, role: str) -> str:
    return f"PAKT_{provider.upper()}_{role.upper()}_MODEL"


def api_key(provider: str) -> str | None:
    value = os.environ.get(PROVIDERS[provider].key_env, "").strip()
    return None if value in PLACEHOLDER_KEYS else value


@dataclass
class ProviderSettings:
    """The provider order, each provider's model per role, and shared retry settings."""

    order: list[str] = field(default_factory=lambda: list(DEFAULT_ORDER))
    models: dict[str, dict[str, str]] = field(default_factory=lambda: {p: dict(i.models) for p, i in PROVIDERS.items()})
    options: dict[str, dict] = field(default_factory=dict)
    max_retries: int = 2
    timeout: float = 120.0
    order_origin: str = "default"

    def model(self, provider: str, role: str) -> str:
        return self.models[provider][role]

    def available(self) -> list[str]:
        """Providers in order that have an API key. The others are skipped."""
        return [p for p in self.order if api_key(p)]

    def primary(self, role: str) -> tuple[str, str]:
        """The provider and model that serve a role first: the first one with a key, else the first in order."""
        provider = (self.available() or self.order)[0]
        return provider, self.model(provider, role)

    def describe(self, role: str) -> str:
        parts = []
        for p in self.order:
            note = "" if api_key(p) else ", no key: skipped"
            parts.append(f"{p} ({self.model(p, role)}{note})")
        return " -> ".join(parts)


def _parse_order(value, origin: str) -> list[str]:
    items = value.split(",") if isinstance(value, str) else list(value)
    order = [str(i).strip().lower() for i in items if str(i).strip()]
    unknown = [p for p in order if p not in PROVIDERS]
    if unknown:
        raise ValueError(f"{origin}: unknown provider(s) {unknown}. Known: {', '.join(PROVIDERS)}")
    if not order:
        raise ValueError(f"{origin}: the provider order is empty")
    return list(dict.fromkeys(order))


def load_provider_settings(data: dict) -> ProviderSettings:
    """Read [providers] from config.toml data, then apply environment overrides.

    Model precedence per provider and role: PAKT_<PROVIDER>_<ROLE>_MODEL, then [providers.<name>] in
    config.toml, then the built-in default. For anthropic only, PAKT_<ROLE>_MODEL and the legacy
    [models] and [review] model keys still apply.
    """
    table = data.get("providers", {})
    settings = ProviderSettings(
        max_retries=max(0, int(table.get("max_retries", 2))),
        timeout=float(table.get("timeout", 120)),
    )
    if "order" in table:
        settings.order, settings.order_origin = _parse_order(table["order"], "config.toml [providers] order"), "config.toml"
    env_order = os.environ.get("PAKT_PROVIDERS", "").strip()
    if env_order:
        settings.order, settings.order_origin = _parse_order(env_order, "PAKT_PROVIDERS"), "PAKT_PROVIDERS"

    legacy = {
        "generator": data.get("models", {}).get("generator"),
        "judge": data.get("models", {}).get("judge"),
        "review": data.get("review", {}).get("model"),
    }
    for name in PROVIDERS:
        ptable = table.get(name, {})
        settings.options[name] = {k: v for k, v in ptable.items() if k not in ROLES}
        for role in ROLES:
            value = ptable.get(role)
            if name == "anthropic":
                value = os.environ.get(LEGACY_MODEL_ENV[role]) or value or legacy[role]
            value = os.environ.get(model_env(name, role)) or value
            if value:
                settings.models[name][role] = str(value)
    return settings


# ------------------------------------------------------------ HTTP with retries

Transport = Callable[[urllib.request.Request, float], tuple[int, dict, bytes]]


def urllib_transport(request: urllib.request.Request, timeout: float) -> tuple[int, dict, bytes]:
    """POST with urllib. Returns (status, headers, body) for any HTTP status, and raises on network errors."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers.items()), response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers.items()) if exc.headers else {}, exc.read() or b""


def _retry_after(headers: dict, body: bytes) -> float | None:
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return float(v)
            except ValueError:
                return None
    match = re.search(rb'"retryDelay"\s*:\s*"([\d.]+)s"', body or b"")
    return float(match.group(1)) if match else None


def _error_message(body: bytes) -> str:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError):
        return body[:300].decode("utf-8", "replace").strip()
    err = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(err, dict):
        return str(err.get("message") or err.get("status") or err)[:300]
    return str(err)[:300]


@dataclass
class HTTPProvider:
    """Shared POST, retry, and error mapping for the REST providers."""

    provider = ""
    api_key: str = ""
    max_retries: int = 2
    timeout: float = 120.0
    transport: Transport = urllib_transport
    sleep: Callable[[float], None] = time.sleep
    max_backoff: float = 30.0

    def _post(self, url: str, headers: dict, payload: dict) -> dict:
        body = json.dumps(payload).encode()
        headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT, **headers}
        attempts = self.max_retries + 1
        last: ProviderError | None = None
        for attempt in range(1, attempts + 1):
            request = urllib.request.Request(url, data=body, headers=headers, method="POST")
            try:
                status, resp_headers, resp_body = self.transport(request, self.timeout)
            except (TimeoutError, urllib.error.URLError, ConnectionError, OSError) as exc:
                reason = getattr(exc, "reason", exc)
                if isinstance(reason, ssl.SSLError) or isinstance(exc, ssl.SSLError):
                    # A certificate problem is a setup problem, not a transient one.
                    raise ProviderError(self.provider, f"TLS error: {reason}") from exc
                last = ProviderError(self.provider, f"network error: {type(exc).__name__}: {reason}", retryable=True)
                wait = None
            else:
                if 200 <= status < 300:
                    try:
                        return json.loads(resp_body)
                    except ValueError as exc:
                        raise ProviderError(self.provider, f"invalid JSON in response: {exc}") from exc
                retryable = status in RETRYABLE_STATUS
                last = ProviderError(
                    self.provider, f"HTTP {status}: {_error_message(resp_body)}", status=status, retryable=retryable
                )
                if not retryable:
                    raise last
                wait = _retry_after(resp_headers, resp_body)
            if attempt == attempts:
                break
            if wait is not None and wait > self.max_backoff:
                log.info("%s asks to wait %.0fs, longer than the %.0fs cap; giving up on it", self.provider, wait, self.max_backoff)
                break
            delay = wait if wait is not None else min(self.max_backoff, 2 ** (attempt - 1) + random.uniform(0, 0.5))
            log.info("%s attempt %d/%d failed (%s); retrying in %.1fs", self.provider, attempt, attempts, last, delay)
            self.sleep(delay)
        assert last is not None
        raise last


@dataclass
class GeminiClient(HTTPProvider):
    """Google Gemini through the generateContent REST endpoint."""

    provider = "gemini"
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    thinking_budget: int | None = None

    def build_request(self, *, model, system, user, max_tokens, temperature) -> tuple[str, dict, dict]:
        config: dict = {"maxOutputTokens": max_tokens}
        if temperature is not None:
            config["temperature"] = temperature
        if self.thinking_budget is not None:
            config["thinkingConfig"] = {"thinkingBudget": self.thinking_budget}
        payload = {"contents": [{"role": "user", "parts": [{"text": user}]}], "generationConfig": config}
        if system:
            payload["systemInstruction"] = {"parts": [{"text": system}]}
        # The key goes in a header, not the URL, so it never lands in a log line or an error message.
        model = model.removeprefix("models/")
        return f"{self.base_url}/models/{model}:generateContent", {"x-goog-api-key": self.api_key}, payload

    def parse_response(self, data: dict, model: str, latency_ms: float) -> Completion:
        candidates = data.get("candidates") or []
        if not candidates:
            reason = (data.get("promptFeedback") or {}).get("blockReason", "no candidates")
            raise ProviderError(self.provider, f"no answer returned ({reason})")
        cand = candidates[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        finish = cand.get("finishReason", "")
        if not text.strip():
            hint = " Raise max_tokens, or set [providers.gemini] thinking_budget." if finish == "MAX_TOKENS" else ""
            raise ProviderError(self.provider, f"empty answer (finishReason {finish or 'unknown'}).{hint}")
        usage = data.get("usageMetadata") or {}
        return Completion(
            text=text,
            model=data.get("modelVersion") or model,
            input_tokens=int(usage.get("promptTokenCount", 0)),
            output_tokens=int(usage.get("candidatesTokenCount", 0)) + int(usage.get("thoughtsTokenCount", 0)),
            latency_ms=round(latency_ms, 1),
            provider=self.provider,
        )

    def complete(self, *, model, system, user, max_tokens, temperature):
        url, headers, payload = self.build_request(
            model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
        start = time.perf_counter()
        data = self._post(url, headers, payload)
        return self.parse_response(data, model, (time.perf_counter() - start) * 1000)


@dataclass
class GroqClient(HTTPProvider):
    """Groq through its OpenAI-compatible chat completions endpoint."""

    provider = "groq"
    base_url: str = "https://api.groq.com/openai/v1"
    reasoning_effort: str | None = None

    def build_request(self, *, model, system, user, max_tokens, temperature) -> tuple[str, dict, dict]:
        messages = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": user}]
        payload: dict = {"model": model, "messages": messages, "max_completion_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = temperature
        if self.reasoning_effort:
            payload["reasoning_effort"] = self.reasoning_effort
        return f"{self.base_url}/chat/completions", {"Authorization": f"Bearer {self.api_key}"}, payload

    def parse_response(self, data: dict, model: str, latency_ms: float) -> Completion:
        choices = data.get("choices") or []
        if not choices:
            raise ProviderError(self.provider, "no answer returned (no choices)")
        choice = choices[0]
        text = (choice.get("message") or {}).get("content") or ""
        if not text.strip():
            finish = choice.get("finish_reason") or "unknown"
            hint = " Raise max_tokens, or set [providers.groq] reasoning_effort." if finish == "length" else ""
            raise ProviderError(self.provider, f"empty answer (finish_reason {finish}).{hint}")
        usage = data.get("usage") or {}
        return Completion(
            text=text,
            model=data.get("model") or model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
            latency_ms=round(latency_ms, 1),
            provider=self.provider,
        )

    def complete(self, *, model, system, user, max_tokens, temperature):
        url, headers, payload = self.build_request(
            model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
        start = time.perf_counter()
        data = self._post(url, headers, payload)
        return self.parse_response(data, model, (time.perf_counter() - start) * 1000)


# ------------------------------------------------------------ fallback


def is_retryable(exc: BaseException) -> bool:
    """True when a failure is transient (rate limit, server error, timeout, network), so another provider may help."""
    if isinstance(exc, CacheMiss):
        return False
    if isinstance(exc, ProviderError):
        return exc.retryable
    if isinstance(exc, (TimeoutError, ConnectionError, urllib.error.URLError)):
        return True
    # The anthropic SDK raises its own types after its own retries. Match them by name and status.
    name = type(exc).__name__
    if name in {"APITimeoutError", "APIConnectionError", "RateLimitError", "InternalServerError", "OverloadedError"}:
        return True
    status = getattr(exc, "status_code", None)
    return isinstance(status, int) and status in RETRYABLE_STATUS


@dataclass
class Route:
    provider: str
    model: str
    client: LLMClient


class FallbackClient:
    """Serve one role from a list of providers, in order.

    Each route carries its own model for the role, so the `model` argument of `complete` is ignored.
    A cached answer from any route wins first. Then each route is called live in order. A transient
    failure, after that provider's own retries, moves to the next route. Any other failure raises at once.
    """

    def __init__(self, routes: list[Route], role: str = ""):
        if not routes:
            raise ValueError("no provider routes")
        self.routes = routes
        self.role = role
        self.served: Counter[str] = Counter()
        self.fallbacks = 0
        self._lock = threading.Lock()

    @property
    def primary(self) -> Route:
        return self.routes[0]

    def _record(self, result: Completion, route: Route) -> Completion:
        with self._lock:
            self.served[f"{result.provider or route.provider}/{result.model}"] += 1
        return result

    def complete(self, *, model, system, user, max_tokens, temperature):
        request = dict(system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        label = self.role or "request"
        for route in self.routes:
            lookup = getattr(route.client, "lookup", None)
            hit = lookup(model=route.model, **request) if lookup else None
            if hit is not None:
                log.debug("%s served from the %s cache (%s)", label, route.provider, hit.model)
                return self._record(hit, route)
        failures: list[str] = []
        for i, route in enumerate(self.routes):
            try:
                result = route.client.complete(model=route.model, **request)
            except Exception as exc:
                if not is_retryable(exc):
                    raise
                failures.append(f"{route.provider}: {exc}")
                if i + 1 == len(self.routes):
                    raise AllProvidersFailed(f"every provider failed for {label}: " + "; ".join(failures)) from exc
                nxt = self.routes[i + 1]
                with self._lock:
                    self.fallbacks += 1
                log.warning("%s failed for %s (%s); falling back to %s (%s)", route.provider, label, exc, nxt.provider, nxt.model)
                continue
            log.info("%s served by %s (%s)", label, route.provider, result.model)
            return self._record(result, route)
        raise AssertionError("unreachable")


def make_client(provider: str, key: str, settings: ProviderSettings) -> LLMClient:
    opts = settings.options.get(provider, {})
    if provider == "gemini":
        budget = opts.get("thinking_budget")
        return GeminiClient(
            api_key=key, max_retries=settings.max_retries, timeout=settings.timeout,
            thinking_budget=None if budget is None else int(budget),
        )
    if provider == "groq":
        return GroqClient(
            api_key=key, max_retries=settings.max_retries, timeout=settings.timeout,
            reasoning_effort=opts.get("reasoning_effort") or None,
        )
    if provider == "anthropic":
        return AnthropicClient(key, max_retries=settings.max_retries, timeout=settings.timeout)
    raise ValueError(f"unknown provider {provider!r}")


class NoProviderKey(RuntimeError):
    pass


def missing_key_message(settings: ProviderSettings) -> str:
    keys = ", ".join(PROVIDERS[p].key_env for p in settings.order)
    return (
        f"no API key found for any provider in the order ({', '.join(settings.order)}): set one of {keys} in .env "
        "(copy .env.example to .env, then run chmod 600 .env)."
    )


def build_client(
    settings: ProviderSettings,
    role: str,
    cache_dir: Path | None = None,
    namespace: str = "",
    cache_only: bool = False,
    factory: Callable[[str, str, ProviderSettings], LLMClient] | None = None,
) -> FallbackClient:
    """Build the fallback chain for one role. Providers without a key are skipped.

    With `cache_only`, every provider in the order joins the chain, no key is needed, and nothing is called.
    """
    routes: list[Route] = []
    for provider in settings.order:
        model = settings.model(provider, role)
        if cache_only:
            inner: LLMClient = CacheOnlyClient()
        else:
            key = api_key(provider)
            if not key:
                log.debug("skipping %s: %s is not set", provider, PROVIDERS[provider].key_env)
                continue
            inner = (factory or make_client)(provider, key, settings)
        client = CachedClient(inner, cache_dir, namespace, provider=provider) if cache_dir is not None else inner
        routes.append(Route(provider, model, client))
    if not routes:
        raise NoProviderKey(missing_key_message(settings))
    return FallbackClient(routes, role)


class _StderrHandler(logging.StreamHandler):
    """Writes to whatever sys.stderr is at emit time, so a swapped stream never goes stale."""

    @property
    def stream(self):
        return sys.stderr

    @stream.setter
    def stream(self, value):
        pass


def configure_logging(default: str = "INFO") -> None:
    """Send PAKT log lines to stderr. PAKT_LOG_LEVEL overrides the level, for example WARNING or DEBUG."""
    logger = logging.getLogger("pakt")
    level = os.environ.get("PAKT_LOG_LEVEL", default).upper()
    logger.setLevel(getattr(logging, level, logging.INFO))
    if not any(isinstance(h, _StderrHandler) for h in logger.handlers):
        handler = _StderrHandler()
        handler.setFormatter(logging.Formatter("pakt: %(message)s"))
        logger.addHandler(handler)
