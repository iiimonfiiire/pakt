from __future__ import annotations

from pathlib import Path

import pytest

from pakt_evals.config import load_config
from pakt_evals.llm import Completion

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def cfg(monkeypatch):
    monkeypatch.setattr("pakt_evals.config._load_dotenv", lambda root: None)
    monkeypatch.delenv("PAKT_GENERATOR_MODEL", raising=False)
    monkeypatch.delenv("PAKT_JUDGE_MODEL", raising=False)
    return load_config(REPO_ROOT)


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
