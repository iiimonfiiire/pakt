"""Model access behind a small interface, plus an on-disk response cache."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Protocol


@dataclass
class Completion:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False
    provider: str = ""


class LLMClient(Protocol):
    def complete(
        self, *, model: str, system: str, user: str, max_tokens: int, temperature: float | None
    ) -> Completion: ...


class AnthropicClient:
    provider = "anthropic"

    def __init__(self, api_key: str, max_retries: int = 4, timeout: float | None = None):
        import anthropic

        kwargs = {"api_key": api_key, "max_retries": max_retries}
        if timeout is not None:
            kwargs["timeout"] = timeout
        self._client = anthropic.Anthropic(**kwargs)

    def complete(self, *, model, system, user, max_tokens, temperature):
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        if temperature is not None:
            kwargs["temperature"] = temperature
        start = time.perf_counter()
        response = self._client.messages.create(**kwargs)
        latency = (time.perf_counter() - start) * 1000
        text = "".join(getattr(block, "text", "") for block in response.content)
        return Completion(
            text=text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            latency_ms=round(latency, 1),
            provider=self.provider,
        )


class CacheMiss(RuntimeError):
    pass


class CacheOnlyClient:
    """Stand-in for a live client that never calls the API. Pairs with CachedClient."""

    def complete(self, *, model, system, user, max_tokens, temperature):
        raise CacheMiss("no cached response for this request (cache-only mode)")


def cache_key(**request) -> str:
    payload = json.dumps(request, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode()).hexdigest()


class CachedClient:
    """Cache keyed on the full request, so any prompt or model change is a new entry.

    The provider is part of both the folder and the key, so answers from different providers never mix.
    It defaults to the inner client's `provider` attribute.
    """

    def __init__(self, inner: LLMClient, cache_dir: Path, namespace: str, provider: str | None = None):
        self.inner = inner
        self.provider = provider if provider is not None else getattr(inner, "provider", "")
        self.dir = cache_dir / namespace / self.provider if self.provider else cache_dir / namespace

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def _key(self, **request) -> str:
        if self.provider:
            request["provider"] = self.provider
        return cache_key(**request)

    def lookup(self, *, model, system, user, max_tokens, temperature) -> Completion | None:
        """Return the cached response for this request, or None. Never calls the inner client."""
        key = self._key(model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        path = self._path(key)
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["cached"] = True
        data.setdefault("provider", self.provider)
        return Completion(**data)

    def complete(self, *, model, system, user, max_tokens, temperature):
        hit = self.lookup(model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        if hit is not None:
            return hit
        result = self.inner.complete(
            model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
        if not result.provider:
            result.provider = self.provider
        path = self._path(self._key(model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature))
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({**asdict(result), "cached": False}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return result


def extract_json_object(raw: str) -> str | None:
    """Return the first JSON object in a model response, fenced or bare."""
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        return fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    return raw[start : end + 1]
