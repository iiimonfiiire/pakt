"""Configuration loading: config.toml for settings, .env for secrets and overrides."""

from __future__ import annotations

import os
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .rules import RuleSettings

PLACEHOLDER_KEYS = {"", "your-api-key-here"}


class ConfigError(RuntimeError):
    pass


@dataclass
class Config:
    root: Path
    generator_model: str
    judge_model: str
    gen_max_tokens: int = 1500
    gen_temperature: float | None = 0.0
    concurrency: int = 4
    judge_max_tokens: int = 800
    judge_temperature: float | None = 0.0
    judge_prompt: Path = Path("prompts/judge/v1.md")
    judge_pass_threshold: int = 4
    rules: RuleSettings = field(default_factory=RuleSettings)
    pricing: dict[str, tuple[float, float]] = field(default_factory=dict)
    testset: Path = Path("evals/data/testset.jsonl")
    spot_check: Path = Path("evals/data/judge_spot_check.jsonl")
    prompts_dir: Path = Path("prompts")
    cache_dir: Path = Path("evals/.cache")
    results_dir: Path = Path("evals/results")

    def price(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        if model not in self.pricing:
            return None
        per_in, per_out = self.pricing[model]
        return (input_tokens * per_in + output_tokens * per_out) / 1_000_000


def find_root(start: Path | None = None) -> Path:
    env_root = os.environ.get("PAKT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config.toml").is_file() and (candidate / "prompts").is_dir():
            return candidate
    raise ConfigError("Cannot find config.toml. Run from inside the PAKT repo or set PAKT_ROOT.")


def _load_dotenv(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.is_file():
        return
    mode = env_path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print("warning: .env is readable by other users. Run: chmod 600 .env", file=sys.stderr)
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)


def _optional_float(value) -> float | None:
    return None if value in (None, "") else float(value)


def load_config(root: Path | None = None) -> Config:
    root = root or find_root()
    _load_dotenv(root)
    with open(root / "config.toml", "rb") as fh:
        data = tomllib.load(fh)

    models = data.get("models", {})
    gen = data.get("generation", {})
    judge = data.get("judge", {})
    rules = data.get("rules", {})
    paths = data.get("paths", {})
    pricing = {
        model: (float(p["input"]), float(p["output"]))
        for model, p in data.get("pricing", {}).items()
    }

    def path(key: str, default: str) -> Path:
        return root / paths.get(key, default)

    return Config(
        root=root,
        generator_model=os.environ.get("PAKT_GENERATOR_MODEL") or models["generator"],
        judge_model=os.environ.get("PAKT_JUDGE_MODEL") or models["judge"],
        gen_max_tokens=int(gen.get("max_tokens", 1500)),
        gen_temperature=_optional_float(gen.get("temperature", 0.0)),
        concurrency=max(1, int(gen.get("concurrency", 4))),
        judge_max_tokens=int(judge.get("max_tokens", 800)),
        judge_temperature=_optional_float(judge.get("temperature", 0.0)),
        judge_prompt=root / judge.get("prompt", "prompts/judge/v1.md"),
        judge_pass_threshold=int(judge.get("pass_threshold", 4)),
        rules=RuleSettings(
            max_sentence_words=int(rules.get("max_sentence_words", 22)),
            max_agentless_passives=int(rules.get("max_agentless_passives", 1)),
        ),
        pricing=pricing,
        testset=path("testset", "evals/data/testset.jsonl"),
        spot_check=path("spot_check", "evals/data/judge_spot_check.jsonl"),
        prompts_dir=path("prompts_dir", "prompts"),
        cache_dir=path("cache_dir", "evals/.cache"),
        results_dir=path("results_dir", "evals/results"),
    )


def require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key in PLACEHOLDER_KEYS:
        raise ConfigError(
            "no API key found: set ANTHROPIC_API_KEY in .env "
            "(copy .env.example to .env, then run chmod 600 .env)."
        )
    return key
