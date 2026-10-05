"""Run prompt variants across the test set, then score every output."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from pakt.llm import LLMClient
from pakt.rules import run_rules, sentence_stats
from pakt.styleguide import StyleGuide

from .config import Config
from .judge import Judgment, judge
from .prompts import PromptFile, build_user_message, extract_rewrite

CATEGORIES = {"kb_article", "release_note", "ui_microcopy", "api_doc", "error_message"}


@dataclass(frozen=True)
class TestItem:
    __test__ = False  # keeps pytest from collecting this dataclass as a test class

    id: str
    category: str
    source: str
    failure_modes: tuple[str, ...] = ()
    must_keep: tuple[str, ...] = ()


def load_testset(path: Path) -> list[TestItem]:
    items: list[TestItem] = []
    seen: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        data = json.loads(line)
        for key in ("id", "category", "source"):
            if not data.get(key):
                raise ValueError(f"{path.name}:{lineno}: missing '{key}'")
        if data["category"] not in CATEGORIES:
            raise ValueError(f"{path.name}:{lineno}: unknown category {data['category']!r}")
        if data["id"] in seen:
            raise ValueError(f"{path.name}:{lineno}: duplicate id {data['id']!r}")
        missing = [t for t in data.get("must_keep", []) if t.lower() not in data["source"].lower()]
        if missing:
            raise ValueError(f"{path.name}:{lineno}: must_keep terms not in source: {missing}")
        seen.add(data["id"])
        items.append(
            TestItem(
                id=data["id"],
                category=data["category"],
                source=data["source"],
                failure_modes=tuple(data.get("failure_modes", [])),
                must_keep=tuple(data.get("must_keep", [])),
            )
        )
    return items


@dataclass
class ItemResult:
    item_id: str
    category: str
    variant: str
    output: str = ""
    format_ok: bool = False
    rules: list[dict] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    judge: dict | None = None
    gen_model: str = ""
    gen_input_tokens: int = 0
    gen_output_tokens: int = 0
    gen_latency_ms: float = 0.0
    gen_cached: bool = False
    judge_model: str = ""
    judge_input_tokens: int = 0
    judge_output_tokens: int = 0
    judge_cached: bool = False
    cost_usd: float | None = 0.0
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def failed_style_rules(self) -> list[str]:
        return [r["rule"] for r in self.rules if r["rule"] != "key_terms" and not r["passed"]]

    @property
    def key_terms_ok(self) -> bool:
        return all(r["passed"] for r in self.rules if r["rule"] == "key_terms")


def score_text(text: str, item: TestItem, guide: StyleGuide) -> tuple[list[dict], dict]:
    results = run_rules(text, item.must_keep, guide)
    return [asdict(r) | {"violations": list(r.violations)} for r in results], sentence_stats(text)


def _add_cost(total: float | None, part: float | None) -> float | None:
    return None if total is None or part is None else total + part


def evaluate_one(
    cfg: Config,
    variant: PromptFile,
    item: TestItem,
    gen_client: LLMClient,
    judge_client: LLMClient | None,
    rubric: str | None,
) -> ItemResult:
    result = ItemResult(item_id=item.id, category=item.category, variant=variant.id)
    try:
        completion = gen_client.complete(
            model=cfg.generator_model,
            system=variant.body,
            user=build_user_message(item.category, item.source),
            max_tokens=cfg.gen_max_tokens,
            temperature=cfg.gen_temperature,
        )
    except Exception as exc:  # one failed call should not sink the whole run
        result.error = f"generation failed: {type(exc).__name__}: {exc}"
        return result

    result.gen_model = completion.model
    result.gen_input_tokens = completion.input_tokens
    result.gen_output_tokens = completion.output_tokens
    result.gen_latency_ms = completion.latency_ms
    result.gen_cached = completion.cached
    result.cost_usd = cfg.price(cfg.generator_model, completion.input_tokens, completion.output_tokens)
    result.output, result.format_ok = extract_rewrite(completion.text)
    result.rules, result.stats = score_text(result.output, item, cfg.guide)

    if judge_client is None or rubric is None:
        return result
    try:
        judgment, jc = judge(
            judge_client,
            model=cfg.judge_model,
            rubric=rubric,
            source=item.source,
            candidate=result.output,
            max_tokens=cfg.judge_max_tokens,
            temperature=cfg.judge_temperature,
        )
    except Exception as exc:
        result.judge = Judgment(error=f"judge failed: {type(exc).__name__}: {exc}").to_dict()
        return result
    result.judge = judgment.to_dict()
    result.judge_model = jc.model
    result.judge_input_tokens = jc.input_tokens
    result.judge_output_tokens = jc.output_tokens
    result.judge_cached = jc.cached
    result.cost_usd = _add_cost(result.cost_usd, cfg.price(cfg.judge_model, jc.input_tokens, jc.output_tokens))
    return result


def run_eval(
    cfg: Config,
    variants: Iterable[PromptFile],
    items: list[TestItem],
    gen_client: LLMClient,
    judge_client: LLMClient | None = None,
    rubric: str | None = None,
    progress: Callable[[ItemResult], None] | None = None,
) -> list[ItemResult]:
    tasks = [(v, item) for v in variants for item in items]
    results: list[ItemResult] = []
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as pool:
        futures = [
            pool.submit(evaluate_one, cfg, v, item, gen_client, judge_client, rubric) for v, item in tasks
        ]
        for future in as_completed(futures):
            res = future.result()
            results.append(res)
            if progress:
                progress(res)
    order = {(v.id, item.id): i for i, (v, item) in enumerate(tasks)}
    return sorted(results, key=lambda r: order[(r.variant, r.item_id)])


def score_canned_outputs(cfg: Config, outputs_path: Path, items: list[TestItem]) -> list[ItemResult]:
    """Offline mode: rule-check a JSONL of {item_id, variant, output} records. No API calls."""
    by_id = {item.id: item for item in items}
    results = []
    for lineno, line in enumerate(outputs_path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        rec = json.loads(line)
        item = by_id.get(rec["item_id"])
        if item is None:
            raise ValueError(f"{outputs_path.name}:{lineno}: unknown item_id {rec['item_id']!r}")
        output, format_ok = extract_rewrite(rec["output"])
        rules, stats = score_text(output, item, cfg.guide)
        results.append(
            ItemResult(
                item_id=item.id, category=item.category, variant=rec["variant"],
                output=output, format_ok=format_ok, rules=rules, stats=stats, cost_usd=None,
            )
        )
    return results


CHARS_PER_TOKEN = 4.0


def estimate_cost(
    cfg: Config, variants: list[PromptFile], items: list[TestItem], rubric: str | None
) -> dict:
    """Rough pre-run estimate. Assumes ~4 characters per token and a rewrite near source length."""

    def tok(text: str) -> float:
        return len(text) / CHARS_PER_TOKEN

    gen_in = gen_out = judge_in = judge_out = 0.0
    for v in variants:
        overhead = 1.6 if "plan" in v.name else 1.0
        for item in items:
            src = tok(build_user_message(item.category, item.source))
            gen_in += tok(v.body) + src
            gen_out += (src * 1.1 + 20) * overhead
            if rubric:
                judge_in += tok(rubric) + src * 2.1
                judge_out += 180
    gen_cost = cfg.price(cfg.generator_model, int(gen_in), int(gen_out))
    judge_cost = cfg.price(cfg.judge_model, int(judge_in), int(judge_out)) if rubric else 0.0
    total = None if gen_cost is None or judge_cost is None else gen_cost + judge_cost
    calls = len(variants) * len(items)
    return {
        "generation_calls": calls,
        "judge_calls": calls if rubric else 0,
        "est_generation_tokens": {"input": int(gen_in), "output": int(gen_out)},
        "est_judge_tokens": {"input": int(judge_in), "output": int(judge_out)},
        "est_cost_usd": None if total is None else round(total, 4),
    }
