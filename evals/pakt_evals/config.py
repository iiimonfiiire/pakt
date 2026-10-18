"""Eval configuration: config.toml for settings, .env for secrets and overrides."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from pakt.config import PLACEHOLDER_KEYS, ConfigError, _load_dotenv, model_client, provider_settings, require_api_key  # noqa: F401
from pakt.config import find_root as _find_root
from pakt.providers import ProviderSettings
from pakt.styleguide import StyleGuide, default_guide, default_source, get_guide


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
    guide: StyleGuide = field(default_factory=default_guide)
    pricing: dict[str, tuple[float, float]] = field(default_factory=dict)
    testset: Path = Path("evals/data/testset.jsonl")
    spot_check: Path = Path("evals/data/judge_spot_check.jsonl")
    reviewer_dir: Path = Path("evals/data/reviewer")
    prompts_dir: Path = Path("prompts")
    cache_dir: Path = Path("evals/.cache")
    results_dir: Path = Path("evals/results")
    review_model: str = "claude-sonnet-5-5"
    review_max_tokens: int = 2000
    review_prompt: Path = Path("prompts/review/v1.md")
    providers: ProviderSettings = field(default_factory=ProviderSettings)
    generator_provider: str = "anthropic"
    judge_provider: str = "anthropic"
    review_provider: str = "anthropic"

    def price(self, model: str, input_tokens: int, output_tokens: int) -> float | None:
        if model not in self.pricing:
            return None
        per_in, per_out = self.pricing[model]
        return (input_tokens * per_in + output_tokens * per_out) / 1_000_000


def find_root(start: Path | None = None) -> Path:
    return _find_root(start)


def _optional_float(value) -> float | None:
    return None if value in (None, "") else float(value)


def load_config(root: Path | None = None) -> Config:
    root = root or find_root()
    _load_dotenv(root)
    with open(root / "config.toml", "rb") as fh:
        data = tomllib.load(fh)

    providers = provider_settings(data)
    (gen_provider, gen_model), (judge_provider, judge_model), (review_provider, review_model) = (
        providers.primary(role) for role in ("generator", "judge", "review")
    )
    gen = data.get("generation", {})
    judge = data.get("judge", {})
    review = data.get("review", {})
    paths = data.get("paths", {})
    pricing = {
        model: (float(p["input"]), float(p["output"]))
        for model, p in data.get("pricing", {}).items()
    }

    def path(key: str, default: str) -> Path:
        return root / paths.get(key, default)

    return Config(
        root=root,
        generator_model=gen_model,
        judge_model=judge_model,
        gen_max_tokens=int(gen.get("max_tokens", 1500)),
        gen_temperature=_optional_float(gen.get("temperature", 0.0)),
        concurrency=max(1, int(gen.get("concurrency", 4))),
        judge_max_tokens=int(judge.get("max_tokens", 800)),
        judge_temperature=_optional_float(judge.get("temperature", 0.0)),
        judge_prompt=root / judge.get("prompt", "prompts/judge/v1.md"),
        judge_pass_threshold=int(judge.get("pass_threshold", 4)),
        guide=get_guide(default_source(root), root, root, origin="config.toml"),
        pricing=pricing,
        testset=path("testset", "evals/data/testset.jsonl"),
        spot_check=path("spot_check", "evals/data/judge_spot_check.jsonl"),
        reviewer_dir=path("reviewer_dir", "evals/data/reviewer"),
        prompts_dir=path("prompts_dir", "prompts"),
        cache_dir=path("cache_dir", "evals/.cache"),
        results_dir=path("results_dir", "evals/results"),
        review_model=review_model,
        review_max_tokens=int(review.get("max_tokens", 2000)),
        review_prompt=root / review.get("prompt", "prompts/review/v1.md"),
        providers=providers,
        generator_provider=gen_provider,
        judge_provider=judge_provider,
        review_provider=review_provider,
    )
