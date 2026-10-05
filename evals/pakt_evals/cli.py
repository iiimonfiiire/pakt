"""Command-line entry point: pakt-eval."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from pakt.llm import AnthropicClient, CachedClient, CacheOnlyClient
from pakt.review import load_template
from pakt.rules import run_rules, strip_front_matter
from pakt.structure import load_content_types

from . import review_eval
from .config import Config, ConfigError, load_config, require_api_key
from .judge import judge
from .prompts import discover_variants, load_prompt
from .report import baseline, render_markdown, summarize, worst_failures, write_run
from .runner import estimate_cost, load_testset, run_eval, score_canned_outputs


def _select_variants(cfg: Config, wanted: str | None):
    available = discover_variants(cfg.prompts_dir)
    if not wanted:
        return list(available.values())
    ids = [w.strip() for w in wanted.split(",") if w.strip()]
    unknown = [i for i in ids if i not in available]
    if unknown:
        raise ConfigError(f"unknown variant(s): {', '.join(unknown)}. Available: {', '.join(available)}")
    return [available[i] for i in ids]


def _select_items(cfg: Config, ids: str | None, limit: int | None):
    items = load_testset(cfg.testset)
    if ids:
        wanted = {i.strip() for i in ids.split(",")}
        items = [it for it in items if it.id in wanted]
    return items[:limit] if limit else items


def _clients(cfg: Config, cache_only: bool):
    inner = CacheOnlyClient() if cache_only else AnthropicClient(require_api_key())
    return (
        CachedClient(inner, cfg.cache_dir, "generations"),
        CachedClient(inner, cfg.cache_dir, "judgments"),
    )


def _run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def cmd_variants(cfg: Config, args) -> int:
    for v in discover_variants(cfg.prompts_dir).values():
        print(f"{v.id}  {v.name}  [{v.sha}]\n    hypothesis: {v.hypothesis}")
    return 0


def cmd_run(cfg: Config, args) -> int:
    variants = _select_variants(cfg, args.variants)
    items = _select_items(cfg, args.ids, args.limit)
    rubric = None if args.no_judge else load_prompt(cfg.judge_prompt).body
    estimate = estimate_cost(cfg, variants, items, rubric)

    print(f"Plan: {len(variants)} variant(s) x {len(items)} item(s)")
    print(f"  generator: {cfg.generator_model}")
    print(f"  judge:     {'disabled' if rubric is None else cfg.judge_model}")
    print(f"  estimate:  {json.dumps(estimate)}")
    print("  (estimate ignores the cache; cached requests cost nothing)")
    if args.dry_run:
        print("Dry run: no API calls made.")
        return 0

    gen_client, judge_client = _clients(cfg, args.cache_only)
    done = 0

    def progress(res) -> None:
        nonlocal done
        done += 1
        flag = "cache" if res.gen_cached else "live"
        status = "ERROR " + res.error if res.error else f"{len(res.failed_style_rules)} rule fail(s)"
        print(f"  [{done}/{len(variants) * len(items)}] {res.variant} {res.item_id} ({flag}): {status}", flush=True)

    results = run_eval(cfg, variants, items, gen_client, None if rubric is None else judge_client, rubric, progress)
    summary = summarize(results, cfg.judge_pass_threshold)
    base = baseline(items, cfg.guide)
    run_id = args.run_id or _run_id()
    meta = {
        "run_id": run_id,
        "generator": cfg.generator_model,
        "judge": "disabled" if rubric is None else cfg.judge_model,
        "variants": ", ".join(f"{v.id} [{v.sha}]" for v in variants),
        "items": str(len(items)),
        "judge prompt": "disabled" if rubric is None else f"{cfg.judge_prompt.name} [{load_prompt(cfg.judge_prompt).sha}]",
    }
    md = render_markdown(summary, base, worst_failures(results), meta, {i.id: i.source for i in items})
    out_dir = Path(args.out) if args.out else cfg.results_dir / run_id
    write_run(out_dir, results, summary, md, meta, base)
    print(f"\nWrote {out_dir / 'report.md'}")
    errors = sum(s["errors"] for s in summary.values())
    if errors:
        print(f"warning: {errors} item(s) errored; see items.jsonl", file=sys.stderr)
    return 1 if errors == len(results) else 0


def cmd_score(cfg: Config, args) -> int:
    items = load_testset(cfg.testset)
    results = score_canned_outputs(cfg, Path(args.outputs), items)
    summary = summarize(results, cfg.judge_pass_threshold)
    base = baseline(items, cfg.guide)
    run_id = args.run_id or f"offline-{_run_id()}"
    meta = {
        "run_id": run_id,
        "mode": "offline rule scoring of canned outputs (no model calls, no judge)",
        "outputs": Path(args.outputs).name,
    }
    md = render_markdown(summary, base, worst_failures(results), meta, {i.id: i.source for i in items})
    out_dir = Path(args.out) if args.out else cfg.results_dir / "scratch" / run_id
    write_run(out_dir, results, summary, md, meta, base)
    print(md)
    print(f"Wrote {out_dir / 'report.md'}")
    return 0


def cmd_lint(cfg: Config, args) -> int:
    failures = 0
    for name in args.files:
        text = strip_front_matter(Path(name).read_text(encoding="utf-8"))
        for r in run_rules(text, (), cfg.guide):
            if r.rule == "key_terms" or r.passed:
                continue
            failures += 1
            for v in r.violations:
                print(f"{name}: {r.rule}: {v}")
    print(f"{failures} rule failure(s)" if failures else "clean")
    return 1 if failures else 0


def cmd_judge_check(cfg: Config, args) -> int:
    """Compare judge scores with hand labels on the spot-check set."""
    rubric_file = load_prompt(cfg.judge_prompt)
    rows = [json.loads(l) for l in cfg.spot_check.read_text(encoding="utf-8").splitlines() if l.strip()]
    print(f"Spot check: {len(rows)} hand-labeled pair(s), judge {cfg.judge_model}")
    if args.dry_run:
        print("Dry run: no API calls made.")
        return 0
    _, judge_client = _clients(cfg, args.cache_only)
    exact = within_one = n = 0
    for row in rows:
        judgment, _ = judge(
            judge_client, model=cfg.judge_model, rubric=rubric_file.body, source=row["source"],
            candidate=row["candidate"], max_tokens=cfg.judge_max_tokens, temperature=cfg.judge_temperature,
        )
        if not judgment.parse_ok:
            print(f"  {row['id']}: parse failure ({judgment.error})")
            continue
        for dim in ("meaning", "readability"):
            human, model = row["human"][dim], getattr(judgment, dim)
            n += 1
            exact += human == model
            within_one += abs(human - model) <= 1
            mark = "" if abs(human - model) <= 1 else "  <-- disagreement"
            print(f"  {row['id']} {dim}: human {human}, judge {model}{mark}")
    if n:
        print(f"Exact agreement: {exact}/{n} ({exact / n:.0%}); within one point: {within_one}/{n} ({within_one / n:.0%})")
    return 0


def cmd_review_eval(cfg: Config, args) -> int:
    """Measure reviewer precision and recall on the labeled reviewer sets."""
    types = load_content_types(cfg.guide, cfg.root)
    items = review_eval.load_reviewer_sets(cfg.reviewer_dir, cfg.guide, types)
    if args.types:
        wanted = {t.strip() for t in args.types.split(",")}
        items = [i for i in items if i.content_type in wanted]
    if args.ids:
        wanted = {i.strip() for i in args.ids.split(",")}
        items = [i for i in items if i.id in wanted]
    errors: list[str] = []
    if args.predictions:
        mode = f"canned predictions from {Path(args.predictions).name} (no model calls)"
        predictions = review_eval.load_predictions(Path(args.predictions))
    elif args.mode == "checks":
        mode = "deterministic checks only (no model calls)"
        predictions, errors = review_eval.run_predictions(items, cfg.guide, types)
    else:
        mode = f"checks plus model review ({cfg.review_model})"
        print(f"Plan: {len(items)} review call(s) with {cfg.review_model}")
        print("  (cached requests cost nothing)")
        if args.dry_run:
            print("Dry run: no API calls made.")
            return 0
        inner = CacheOnlyClient() if args.cache_only else AnthropicClient(require_api_key())
        client = CachedClient(inner, cfg.cache_dir, "reviews")
        predictions, errors = review_eval.run_predictions(
            items, cfg.guide, types, client,
            progress=lambda item_id, n: print(f"  [{n}/{len(items)}] {item_id}", flush=True),
            model=cfg.review_model, template=load_template(cfg.review_prompt),
            max_tokens=cfg.review_max_tokens, temperature=0.0,
        )
    metrics = review_eval.score(items, predictions, cfg.guide, types)
    metrics["errors"] = errors
    run_id = args.run_id or f"review-{args.mode if not args.predictions else 'canned'}-{_run_id()}"
    meta = {
        "run_id": run_id,
        "mode": mode,
        "style guide": cfg.guide.label,
        "review prompt": f"{cfg.review_prompt.name} [{load_prompt(cfg.review_prompt).sha}]",
        "items": str(len(items)),
    }
    md = review_eval.render_markdown(metrics, meta)
    live = args.mode == "model" and not args.predictions
    out_dir = Path(args.out) if args.out else (cfg.results_dir / run_id if live else cfg.results_dir / "scratch" / run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report.md").write_text(md, encoding="utf-8")
    payload = {"meta": meta, "metrics": metrics, "predictions": {k: sorted(v) for k, v in predictions.items()}}
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(md)
    print(f"Wrote {out_dir / 'report.md'}")
    for e in errors:
        print(f"warning: {e}", file=sys.stderr)
    return 1 if errors and len(errors) == len(items) else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pakt-eval", description="Measure the PAKT rewriter prompts and reviewers.")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("variants", help="list prompt variants and their hypotheses")

    run = sub.add_parser("run", help="generate, score, judge, and report")
    run.add_argument("--variants", help="comma-separated ids, e.g. v1,v3 (default: all)")
    run.add_argument("--ids", help="comma-separated test item ids")
    run.add_argument("--limit", type=int, help="first N items only")
    run.add_argument("--no-judge", action="store_true", help="skip LLM-as-judge scoring")
    run.add_argument("--dry-run", action="store_true", help="print the plan and cost estimate, call nothing")
    run.add_argument("--cache-only", action="store_true", help="use cached responses only, never call the API")
    run.add_argument("--run-id", help="name for the results folder")
    run.add_argument("--out", help="output directory (default: evals/results/<run-id>)")

    score = sub.add_parser("score", help="offline: rule-check canned outputs, no API key needed")
    score.add_argument("--outputs", required=True, help="JSONL of {item_id, variant, output}")
    score.add_argument("--run-id")
    score.add_argument("--out", help="output directory (default: evals/results/scratch/<run-id>)")

    lint = sub.add_parser("lint", help="run the Signal rule checks on any text or Markdown file")
    lint.add_argument("files", nargs="+")

    jc = sub.add_parser("judge-check", help="measure judge agreement with hand labels")
    jc.add_argument("--dry-run", action="store_true")
    jc.add_argument("--cache-only", action="store_true")

    re_ = sub.add_parser("review-eval", help="measure reviewer precision and recall on labeled documents")
    re_.add_argument("--mode", choices=["checks", "model"], default="checks",
                     help="checks: offline, deterministic only; model: checks plus a model review")
    re_.add_argument("--predictions", help="score a JSONL of canned predictions instead of running a reviewer")
    re_.add_argument("--types", help="comma-separated content types")
    re_.add_argument("--ids", help="comma-separated item ids")
    re_.add_argument("--dry-run", action="store_true")
    re_.add_argument("--cache-only", action="store_true")
    re_.add_argument("--run-id")
    re_.add_argument("--out")
    return p


COMMANDS = {
    "variants": cmd_variants,
    "run": cmd_run,
    "score": cmd_score,
    "lint": cmd_lint,
    "judge-check": cmd_judge_check,
    "review-eval": cmd_review_eval,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        cfg = load_config()
        return COMMANDS[args.command](cfg, args)
    except ConfigError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
