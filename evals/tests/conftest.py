from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"

# Serve the pinned default guide from a fixture copy in a private cache, so no test touches the network.
os.environ["PAKT_CACHE_DIR"] = tempfile.mkdtemp(prefix="pakt-test-cache-")

from pakt import sources  # noqa: E402

_default = sources.parse_spec(sources.DEFAULT_SOURCE)
shutil.copytree(FIXTURES / "signal", sources._cache_dir(_default) / "rules")


def _no_network(url: str) -> bytes:
    raise AssertionError(f"tests must not fetch {url}. Use the fake_remote fixture.")


sources._fetch = _no_network

from pakt_evals.config import load_config  # noqa: E402
from pakt_evals.llm import Completion  # noqa: E402


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr("pakt_evals.config._load_dotenv", lambda root: None)
    monkeypatch.delenv("PAKT_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("PAKT_JUDGE_MODEL", raising=False)
    return load_config(REPO_ROOT)


@pytest.fixture
def fake_remote(monkeypatch, tmp_path):
    """A fake web: a dict from URL to bytes. Unknown URLs raise a 404. Each test gets an empty cache."""
    import urllib.error

    files: dict[str, bytes] = {}
    calls: list[str] = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        if url not in files:
            raise urllib.error.HTTPError(url, 404, "Not Found", None, None)
        return files[url]

    monkeypatch.setattr(sources, "_fetch", fetch)
    monkeypatch.setenv("PAKT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("PAKT_OFFLINE", raising=False)
    files_calls = type("FakeRemote", (), {"files": files, "calls": calls})
    return files_calls


class FakeClient:
    """Deterministic stand-in for the API. Records every call."""

    def __init__(self, respond):
        self.respond = respond
        self.calls: list[dict] = []

    def complete(self, *, model, system, user, max_tokens, temperature):
        self.calls.append(dict(model=model, system=system, user=user))
        return Completion(text=self.respond(system, user), model=model, input_tokens=100, output_tokens=50, latency_ms=10.0)


@pytest.fixture
def fake_client_factory():
    return FakeClient
