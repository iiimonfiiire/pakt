"""Aggregate item results into per-variant metrics and render the report."""

from __future__ import annotations

import json
import math
from pathlib import Path
from statistics import mean

from .rules import STYLE_RULES, RuleSettings, run_rules
from .runner import ItemResult, TestItem

RULE_NAMES = [*STYLE_RULES, "key_terms"]


def _rate(passed: int, total: int) -> float | None:
    return None if total == 0 else passed / total


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def _num(value: float | None, digits: int = 2) -> str:
    return "n/a" if value is None else f"{value:.{digits}f}"


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile, so the value is always one that was observed."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, math.ceil(q / 100 * len(ordered)))
    return ordered[rank - 1]


def summarize_variant(results: list[ItemResult], pass_threshold: int) -> dict:
    ok = [r for r in results if not r.error]
    per_rule = {}
    for name in RULE_NAMES:
        applicable = [r for r in ok for rr in r.rules if rr["rule"] == name and rr["applicable"]]
        passed = [r for r in ok for rr in r.rules if rr["rule"] == name and rr["applicable"] and rr["passed"]]
        per_rule[name] = {"passed": len(passed), "applicable": len(applicable), "rate": _rate(len(passed), len(applicable))}

    judged = [r.judge for r in ok if r.judge and r.judge.get("parse_ok")]
    meaning = [j["meaning"] for j in judged]
    readability = [j["readability"] for j in judged]
    judge_pass = [m for m in meaning if m >= pass_threshold]
    latencies = [r.gen_latency_ms for r in ok if r.gen_latency_ms > 0]
    costs = [r.cost_usd for r in results]

    return {
        "items": len(results),
        "errors": len(results) - len(ok),
        "format_ok_rate": _rate(sum(r.format_ok for r in ok), len(ok)),
        "all_style_rules_pass_rate": _rate(sum(not r.failed_style_rules for r in ok), len(ok)),
        "mean_style_violations": round(mean(len(r.failed_style_rules) for r in ok), 2) if ok else None,
        "rules": per_rule,
        "judged": len(judged),
        "judge_parse_failures": sum(1 for r in ok if r.judge and not r.judge.get("parse_ok")),
        "meaning_mean": round(mean(meaning), 2) if meaning else None,
        "readability_mean": round(mean(readability), 2) if readability else None,
        "meaning_pass_rate": _rate(len(judge_pass), len(meaning)),
        "mean_sentence_words": round(mean(r.stats.get("mean_words", 0) for r in ok), 2) if ok else None,
        "gen_latency_mean_ms": round(mean(latencies), 1) if latencies else None,
        "gen_latency_p95_ms": percentile(latencies, 95),
        "gen_tokens": {
            "input": sum(r.gen_input_tokens for r in results),
            "output": sum(r.gen_output_tokens for r in results),
        },
        "judge_tokens": {
            "input": sum(r.judge_input_tokens for r in results),
            "output": sum(r.judge_output_tokens for r in results),
        },
        "cost_usd": None if any(c is None for c in costs) else round(sum(costs), 4),
        "cache_hits": sum(r.gen_cached for r in results),
    }


def summarize(results: list[ItemResult], pass_threshold: int = 4) -> dict[str, dict]:
    variants = sorted({r.variant for r in results})
    return {v: summarize_variant([r for r in results if r.variant == v], pass_threshold) for v in variants}


def baseline(items: list[TestItem], settings: RuleSettings) -> dict[str, dict]:
    """Rule pass rates on the untouched source snippets: the floor every variant should beat."""
    per_rule = {name: [0, 0] for name in STYLE_RULES}
    all_pass = 0
    for item in items:
        results = [r for r in run_rules(item.source, (), settings) if r.rule != "key_terms"]
        for r in results:
            if r.applicable:
                per_rule[r.rule][1] += 1
                per_rule[r.rule][0] += r.passed
        all_pass += all(r.passed for r in results)
    out = {name: {"passed": p, "applicable": n, "rate": _rate(p, n)} for name, (p, n) in per_rule.items()}
    out["_all_style_rules"] = {"passed": all_pass, "applicable": len(items), "rate": _rate(all_pass, len(items))}
    return out


def badness(r: ItemResult) -> float:
    """Ranking score for the worst-failures section. Meaning loss weighs most."""
    if r.error:
        return 100.0
    score = float(len(r.failed_style_rules))
    if not r.key_terms_ok:
        score += 2
    if r.judge and r.judge.get("parse_ok"):
        score += (5 - r.judge["meaning"]) * 2 + (5 - r.judge["readability"])
    return score


def worst_failures(results: list[ItemResult], k: int = 5) -> list[ItemResult]:
    ranked = sorted(results, key=lambda r: (-badness(r), r.variant, r.item_id))
    return [r for r in ranked[:k] if badness(r) > 0]


def _cell(text: str, width: int = 0) -> str:
    text = " ".join(text.split()).replace("|", "\\|")
    if width and len(text) > width:
        text = text[: width - 3] + "..."
    return text


def render_markdown(
    summary: dict[str, dict],
    base: dict[str, dict] | None,
    worst: list[ItemResult],
    meta: dict,
    sources: dict[str, str] | None = None,
) -> str:
    variants = list(summary)
    lines = [f"# Eval report: {meta.get('run_id', 'unnamed run')}", ""]
    lines += [f"- **{k}** – {v}" for k, v in meta.items() if k != "run_id"]
    lines += ["", "## Headline", ""]

    head = ["Metric", *variants]
    lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]

    def row(label: str, fn) -> None:
        lines.append("| " + " | ".join([label, *(fn(summary[v]) for v in variants)]) + " |")

    row("Items (errors)", lambda s: f"{s['items']} ({s['errors']})")
    row("All style rules pass", lambda s: _pct(s["all_style_rules_pass_rate"]))
    row("Mean style violations per item", lambda s: _num(s["mean_style_violations"]))
    row("Key terms kept", lambda s: _pct(s["rules"]["key_terms"]["rate"]))
    row("Judge: meaning (1-5)", lambda s: _num(s["meaning_mean"]))
    row("Judge: meaning pass rate", lambda s: _pct(s["meaning_pass_rate"]))
    row("Judge: readability (1-5)", lambda s: _num(s["readability_mean"]))
    row("Judge parse failures", lambda s: str(s["judge_parse_failures"]))
    row("Output format OK", lambda s: _pct(s["format_ok_rate"]))
    row("Mean words per sentence", lambda s: _num(s["mean_sentence_words"]))
    row("Generation latency mean (ms)", lambda s: _num(s["gen_latency_mean_ms"], 0))
    row("Generation latency p95 (ms)", lambda s: _num(s["gen_latency_p95_ms"], 0))
    row("Tokens in/out (generation)", lambda s: f"{s['gen_tokens']['input']}/{s['gen_tokens']['output']}")
    row("Tokens in/out (judge)", lambda s: f"{s['judge_tokens']['input']}/{s['judge_tokens']['output']}")
    row("Cost (USD, as first incurred)", lambda s: _num(s["cost_usd"], 4))
    row("Generation cache hits", lambda s: str(s["cache_hits"]))

    lines += ["", "## Pass rate per rule", ""]
    head = ["Rule", *([("source baseline")] if base else []), *variants]
    lines += ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for name in RULE_NAMES:
        cells = [f"`{name}`"]
        if base:
            b = base.get(name)
            cells.append(f"{_pct(b['rate'])} ({b['applicable']})" if b else "n/a")
        for v in variants:
            r = summary[v]["rules"][name]
            cells.append(f"{_pct(r['rate'])} ({r['applicable']})")
        lines.append("| " + " | ".join(cells) + " |")
    lines += ["", "Each cell shows the pass rate, then the number of items the rule applied to."]

    lines += ["", "## Worst failures", ""]
    if not worst:
        lines.append("No failures to show.")
    for r in worst:
        lines += [f"### `{r.variant}` on `{r.item_id}` ({r.category})", ""]
        if r.error:
            lines += [f"- **Error** – {r.error}", ""]
            continue
        if r.failed_style_rules:
            lines.append(f"- **Failed rules** – {', '.join(r.failed_style_rules)}")
        if not r.key_terms_ok:
            missing = [v for rr in r.rules if rr["rule"] == "key_terms" for v in rr["violations"]]
            lines.append(f"- **Key terms** – {'; '.join(missing)}")
        if r.judge and r.judge.get("parse_ok"):
            lines.append(f"- **Judge** – meaning {r.judge['meaning']}, readability {r.judge['readability']}")
            if r.judge.get("missing_facts"):
                lines.append(f"- **Judge: missing facts** – {_cell('; '.join(r.judge['missing_facts']))}")
            if r.judge.get("added_facts"):
                lines.append(f"- **Judge: added facts** – {_cell('; '.join(r.judge['added_facts']))}")
        details = [v for rr in r.rules if not rr["passed"] and rr["rule"] != "key_terms" for v in rr["violations"]]
        for v in details[:6]:
            lines.append(f"  - {_cell(v)}")
        if sources and r.item_id in sources:
            lines += ["", "Source:", "", "```text", sources[r.item_id].strip(), "```"]
        lines += ["", "Output:", "", "```text", r.output.strip(), "```", ""]
    return "\n".join(lines).rstrip() + "\n"


def write_run(
    out_dir: Path,
    results: list[ItemResult],
    summary: dict,
    report_md: str,
    meta: dict,
    base: dict | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "items.jsonl", "w", encoding="utf-8") as fh:
        for r in results:
            fh.write(json.dumps(r.to_dict(), ensure_ascii=False) + "\n")
    payload = {"meta": meta, "variants": summary, "source_baseline": base}
    (out_dir / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "report.md").write_text(report_md, encoding="utf-8")
