"""Model access behind a small interface, plus an on-disk response cache."""

from __future__ import annotations

import hashlib
import json
import os
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


class LLMClient(Protocol):
    def complete(
        self, *, model: str, system: str, user: str, max_tokens: int, temperature: float | None
    ) -> Completion: ...


class AnthropicClient:
    def __init__(self, api_key: str, max_retries: int = 4):
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key, max_retries=max_retries)

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
    """Cache keyed on the full request, so any prompt or model change is a new entry."""

    def __init__(self, inner: LLMClient, cache_dir: Path, namespace: str):
        self.inner = inner
        self.dir = cache_dir / namespace

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def complete(self, *, model, system, user, max_tokens, temperature):
        key = cache_key(model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature)
        path = self._path(key)
        if path.is_file():
            data = json.loads(path.read_text(encoding="utf-8"))
            data["cached"] = True
            return Completion(**data)
        result = self.inner.complete(
            model=model, system=system, user=user, max_tokens=max_tokens, temperature=temperature
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump({**asdict(result), "cached": False}, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        return result
