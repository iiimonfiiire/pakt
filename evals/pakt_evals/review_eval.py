"""Reviewer evals: precision and recall of rule-violation findings on hand-labeled documents."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pakt.document import parse_document
from pakt.llm import LLMClient
from pakt.review import review
from pakt.structure import ContentType
from pakt.styleguide import StyleGuide


@dataclass(frozen=True)
class ReviewItem:
    __test__ = False

    id: str
    content_type: str
    text: str
    violations: tuple[str, ...] = ()
    path: str = ""
    notes: str = ""


def label_space(guide: StyleGuide, ctype: ContentType) -> dict[str, str]:
    """Every rule ID a reviewer can report for this content type, mapped to its kind."""
    space = {r.id: r.kind for r in guide.rules}
    space.update({r.id: r.kind for r in ctype.requirements})
    return space


def load_reviewer_sets(directory: Path, guide: StyleGuide, types: dict[str, ContentType]) -> list[ReviewItem]:
    items: list[ReviewItem] = []
    seen: set[str] = set()
    for path in sorted(directory.glob("*.jsonl")):
        if path.name.startswith("sample_"):
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            data = json.loads(line)
            where = f"{path.name}:{lineno}"
            for key in ("id", "content_type", "text"):
                if not data.get(key):
                    raise ValueError(f"{where}: missing '{key}'")
            if data["content_type"] not in types:
                raise ValueError(f"{where}: unknown content type {data['content_type']!r}")
            if data["id"] in seen:
                raise ValueError(f"{where}: duplicate id {data['id']!r}")
            space = label_space(guide, types[data["content_type"]])
            unknown = [v for v in data.get("violations", []) if v not in space]
            if unknown:
                raise ValueError(f"{where}: rule IDs not in the {guide.id} guide or the content type: {unknown}")
            seen.add(data["id"])
            items.append(ReviewItem(
                id=data["id"], content_type=data["content_type"], text=data["text"],
                violations=tuple(data.get("violations", [])), path=data.get("path", ""), notes=data.get("notes", ""),
            ))
    return items


def predict(
    item: ReviewItem,
    guide: StyleGuide,
    types: dict[str, ContentType],
    client: LLMClient | None = None,
    **model_kwargs,
) -> set[str]:
    """Run the reviewer on one item and return the rule IDs it reported."""
    ctype = types[item.content_type]
    doc = parse_document(item.text, Path(item.path) if item.path else None)
    report = review(doc, guide, ctype, client=client, **model_kwargs)
    space = label_space(guide, ctype)
    return {f.rule for f in report.findings if f.rule in space}


def load_predictions(path: Path) -> dict[str, set[str]]:
    """Read canned predictions: JSONL of {"id": ..., "rules": [...]}, or full review reports with findings."""
    out: dict[str, set[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        rules = rec.get("rules")
        if rules is None:
            rules = [f["rule"] for f in rec.get("findings", [])]
        out[rec["id"]] = set(rules)
    return out


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = None
    if precision is not None and recall is not None and precision + recall:
        f1 = 2 * precision * recall / (precision + recall)
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def score(
    items: list[ReviewItem],
    predictions: dict[str, set[str]],
    guide: StyleGuide,
    types: dict[str, ContentType],
) -> dict:
    """Score predictions as (item, rule ID) pairs. Items without a prediction count as reporting nothing."""
    per_rule: dict[str, list[int]] = {}
    kinds: dict[str, str] = {}
    by_type: dict[str, list[int]] = {}
    by_kind: dict[str, list[int]] = {"check": [0, 0, 0], "judgment": [0, 0, 0]}
    clean_items = clean_flagged = 0
    misses: list[dict] = []
    for item in items:
        space = label_space(guide, types[item.content_type])
        gold = set(item.violations)
        pred = predictions.get(item.id, set()) & set(space)
        if not gold:
            clean_items += 1
            clean_flagged += bool(pred)
        for rule in gold | pred:
            kinds[rule] = space[rule]
            counts = per_rule.setdefault(rule, [0, 0, 0])
            tbucket = by_type.setdefault(item.content_type, [0, 0, 0])
            idx = 0 if rule in gold and rule in pred else (1 if rule in pred else 2)
            for bucket in (counts, tbucket, by_kind[space[rule]]):
                bucket[idx] += 1
        if gold != pred:
            misses.append({"id": item.id, "missed": sorted(gold - pred), "extra": sorted(pred - gold)})
    total = [sum(c[i] for c in per_rule.values()) for i in range(3)]
    return {
        "items": len(items),
        "predicted_items": sum(1 for i in items if i.id in predictions),
        "overall": _prf(*total),
        "by_kind": {k: _prf(*v) for k, v in by_kind.items()},
        "by_type": {t: _prf(*v) for t, v in sorted(by_type.items())},
        "per_rule": {r: {**_prf(*v), "kind": kinds[r]} for r, v in sorted(per_rule.items())},
        "clean_items": clean_items,
        "clean_items_flagged": clean_flagged,
        "disagreements": misses,
    }


def _pct(value: float | None) -> str:
    return "n/a" if value is None else f"{value * 100:.0f}%"


def render_markdown(metrics: dict, meta: dict) -> str:
    lines = [f"# Reviewer eval: {meta.get('run_id', 'unnamed run')}", ""]
    lines += [f"- **{k}** – {v}" for k, v in meta.items() if k != "run_id"]
    o = metrics["overall"]
    lines += [
        "", "## Headline", "",
        "| Metric | Value |", "|---|---|",
        f"| Items (with predictions) | {metrics['items']} ({metrics['predicted_items']}) |",
        f"| Precision | {_pct(o['precision'])} |",
        f"| Recall | {_pct(o['recall'])} |",
        f"| F1 | {_pct(o['f1'])} |",
        f"| True positives, false positives, false negatives | {o['tp']}, {o['fp']}, {o['fn']} |",
        f"| Clean items with any finding | {metrics['clean_items_flagged']} of {metrics['clean_items']} |",
        "", "## By rule kind", "",
        "Deterministic checks cover `check` rules. Only a model or a person can find `judgment` rules.", "",
        "| Kind | Precision | Recall | F1 | TP | FP | FN |", "|---|---|---|---|---|---|---|",
    ]
    for kind, m in metrics["by_kind"].items():
        lines.append(f"| {kind} | {_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['f1'])} | {m['tp']} | {m['fp']} | {m['fn']} |")
    lines += ["", "## By content type", "", "| Content type | Precision | Recall | F1 |", "|---|---|---|---|"]
    for t, m in metrics["by_type"].items():
        lines.append(f"| {t} | {_pct(m['precision'])} | {_pct(m['recall'])} | {_pct(m['f1'])} |")
    lines += ["", "## Per rule", "", "| Rule | Kind | Precision | Recall | TP | FP | FN |", "|---|---|---|---|---|---|---|"]
    for rule, m in metrics["per_rule"].items():
        lines.append(f"| `{rule}` | {m['kind']} | {_pct(m['precision'])} | {_pct(m['recall'])} | {m['tp']} | {m['fp']} | {m['fn']} |")
    lines += ["", "## Disagreements with the labels", ""]
    if not metrics["disagreements"]:
        lines.append("None.")
    for d in metrics["disagreements"]:
        parts = []
        if d["missed"]:
            parts.append("missed " + ", ".join(f"`{r}`" for r in d["missed"]))
        if d["extra"]:
            parts.append("extra " + ", ".join(f"`{r}`" for r in d["extra"]))
        lines.append(f"- **{d['id']}** – {'; '.join(parts)}")
    return "\n".join(lines).rstrip() + "\n"


def run_predictions(
    items: list[ReviewItem],
    guide: StyleGuide,
    types: dict[str, ContentType],
    client: LLMClient | None = None,
    progress: Callable[[str, int], None] | None = None,
    **model_kwargs,
) -> tuple[dict[str, set[str]], list[str]]:
    predictions: dict[str, set[str]] = {}
    errors: list[str] = []
    for n, item in enumerate(items, 1):
        try:
            predictions[item.id] = predict(item, guide, types, client, **model_kwargs)
        except Exception as exc:  # one failed call should not sink the whole run
            errors.append(f"{item.id}: {type(exc).__name__}: {exc}")
        if progress:
            progress(item.id, n)
    return predictions, errors
