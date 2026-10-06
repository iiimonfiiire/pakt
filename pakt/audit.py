"""Content audit: review every file in a docs folder and rank them worst-first."""

from __future__ import annotations

import fnmatch
from dataclasses import dataclass
from pathlib import Path

from .document import load_document
from .review import VERDICT_ORDER, ReviewReport, review, verdict_for
from .structure import ContentType, detect_type
from .styleguide import StyleGuide
from .terminology import Glossary, check_terms

SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".claude", "site", "build", "dist"}


@dataclass
class AuditEntry:
    path: str
    report: ReviewReport

    @property
    def ratio(self) -> float:
        return self.report.total / self.report.max_total if self.report.max_total else 1.0

    @property
    def errors(self) -> int:
        return sum(f.severity == "error" for f in self.report.findings)


def _matches(rel: str, patterns: list[str]) -> bool:
    return any(fnmatch.fnmatch(rel, p) or (p.startswith("**/") and fnmatch.fnmatch(rel, p[3:])) for p in patterns)


def collect_files(base: Path, include: list[str], exclude: list[str]) -> list[Path]:
    if base.is_file():
        return [base]
    out = []
    for path in sorted(base.rglob("*")):
        rel_parts = path.relative_to(base).parts
        if not path.is_file() or any(p in SKIP_DIRS for p in rel_parts[:-1]):
            continue
        rel = path.relative_to(base).as_posix()
        if _matches(rel, include) and not _matches(rel, exclude):
            out.append(path)
    return out


def audit(
    base: Path,
    guide: StyleGuide,
    types: dict[str, ContentType],
    include: list[str],
    exclude: list[str] | None = None,
    type_map: dict[str, str] | None = None,
    glossary: Glossary | None = None,
    project_root: Path | None = None,
) -> list[AuditEntry]:
    entries = []
    anchor = project_root or (base if base.is_dir() else base.parent)
    for path in collect_files(base, include, exclude or []):
        doc = load_document(path)
        try:
            rel = path.resolve().relative_to(anchor.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        ctype = types[detect_type(doc, types, rel, type_map)]
        report = review(doc, guide, ctype)
        report.path = rel
        if glossary is not None:
            report.findings += check_terms(doc, glossary)
            report.verdict = verdict_for(report.scores, report.findings)
        entries.append(AuditEntry(rel, report))
    return rank(entries)


def rank(entries: list[AuditEntry]) -> list[AuditEntry]:
    return sorted(entries, key=lambda e: (VERDICT_ORDER[e.report.verdict], e.ratio, -e.errors, -len(e.report.findings), e.path))


def rule_counts(entries: list[AuditEntry]) -> list[dict]:
    counts: dict[str, dict] = {}
    for e in entries:
        for f in e.report.findings:
            row = counts.setdefault(f.rule, {"rule": f.rule, "severity": f.severity, "findings": 0, "files": set()})
            row["findings"] += 1
            row["files"].add(e.path)
    rows = [{**r, "files": len(r["files"])} for r in counts.values()]
    return sorted(rows, key=lambda r: (-r["findings"], r["rule"]))


def summary(entries: list[AuditEntry]) -> dict:
    verdicts = {"pass": 0, "revise": 0, "fail": 0}
    for e in entries:
        verdicts[e.report.verdict] += 1
    return {"files": len(entries), "verdicts": verdicts, "findings": sum(len(e.report.findings) for e in entries)}


def to_dict(entries: list[AuditEntry], guide: StyleGuide) -> dict:
    return {
        "guide": guide.label,
        "summary": summary(entries),
        "rules": rule_counts(entries),
        "files": [e.report.to_dict() for e in entries],
    }


def render_markdown(entries: list[AuditEntry], guide: StyleGuide, base: str, limit: int = 0) -> str:
    s = summary(entries)
    lines = [
        f"# Content audit: {base}", "",
        f"- **Style guide** – {guide.label}",
        f"- **Files** – {s['files']}",
        f"- **Verdicts** – {s['verdicts']['fail']} fail, {s['verdicts']['revise']} revise, {s['verdicts']['pass']} pass",
        f"- **Findings** – {s['findings']}",
        "- **Mode** – deterministic checks only. Judgment rules need the content-audit skill or a model review.",
        "", "## Files, worst first", "",
        "| File | Type | Verdict | Score | Errors | Findings |", "|---|---|---|---|---|---|",
    ]
    shown = entries[:limit] if limit else entries
    for e in shown:
        r = e.report
        lines.append(f"| `{e.path}` | {r.content_type} | {r.verdict} | {r.total}/{r.max_total} | {e.errors} | {len(r.findings)} |")
    if limit and len(entries) > limit:
        lines += ["", f"{len(entries) - limit} more file(s) not shown. Use --limit 0 to list all."]
    lines += ["", "## Findings per rule", "", "| Rule | Severity | Findings | Files |", "|---|---|---|---|"]
    for row in rule_counts(entries):
        lines.append(f"| `{row['rule']}` | {row['severity']} | {row['findings']} | {row['files']} |")
    worst = [e for e in shown if e.report.findings][:5]
    if worst:
        lines += ["", "## Top findings in the worst files", ""]
        for e in worst:
            lines += [f"### `{e.path}`", ""]
            for f in e.report.findings[:5]:
                where = f"line {f.line}" if f.line else "line unknown"
                lines.append(f"- **{f.rule}** ({f.severity}, {where}) – {f.message}")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
