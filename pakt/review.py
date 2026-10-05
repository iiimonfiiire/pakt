"""Content reviews: deterministic checks plus optional model judgment, merged into one scored report."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .document import Document, parse_ui_strings, quote_from_violation, split_front_matter
from .llm import LLMClient, extract_json_object
from .rules import apply_rule
from .structure import ContentType, apply_requirement
from .styleguide import Rule, StyleGuide

CRITERIA = ("style_compliance", "technical_clarity", "structure", "scannability")
LABELS = {
    "style_compliance": "Style compliance",
    "technical_clarity": "Technical clarity",
    "structure": "Structure",
    "scannability": "Scannability",
}
PENALTY = {"error": 1.5, "warning": 1.0, "suggestion": 0.5}
PER_RULE_CAP = 3.0
SEVERITY_ORDER = {"error": 0, "warning": 1, "suggestion": 2}
VERDICT_ORDER = {"fail": 0, "revise": 1, "pass": 2}

_CONTRACTIONS = {
    "don't": "do not", "doesn't": "does not", "didn't": "did not", "can't": "cannot", "won't": "will not",
    "isn't": "is not", "aren't": "are not", "wasn't": "was not", "weren't": "were not", "it's": "it is",
    "you'll": "you will", "you're": "you are", "you've": "you have", "we're": "we are", "we'll": "we will",
    "they're": "they are", "that's": "that is", "there's": "there is", "let's": "let us", "i'm": "I am",
    "shouldn't": "should not", "couldn't": "could not", "wouldn't": "would not", "hasn't": "has not",
    "haven't": "have not", "we've": "we have", "what's": "what is",
}


@dataclass
class Finding:
    rule: str
    severity: str
    message: str
    quote: str = ""
    line: int | None = None
    fix: str = ""
    source: str = "check"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ReviewReport:
    path: str
    content_type: str
    guide: str
    scores: dict[str, int | None]
    verdict: str
    findings: list[Finding] = field(default_factory=list)
    summary: str = ""
    mode: str = "checks"
    notes: list[str] = field(default_factory=list)

    @property
    def scored(self) -> dict[str, int]:
        return {k: v for k, v in self.scores.items() if v is not None}

    @property
    def total(self) -> int:
        return sum(self.scored.values())

    @property
    def max_total(self) -> int:
        return 10 * len(self.scored)

    def rule_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for f in self.findings:
            counts[f.rule] = counts.get(f.rule, 0) + 1
        return counts

    def to_dict(self) -> dict:
        return {
            "path": self.path, "content_type": self.content_type, "guide": self.guide, "mode": self.mode,
            "scores": self.scores, "total": self.total, "max_total": self.max_total, "verdict": self.verdict,
            "summary": self.summary, "findings": [f.to_dict() for f in self.findings], "notes": self.notes,
        }

    def to_markdown(self) -> str:
        lines = [f"# Review: {self.path}", ""]
        lines += [
            f"- **Verdict** – {self.verdict}",
            f"- **Score** – {self.total}/{self.max_total}",
            f"- **Content type** – {self.content_type}",
            f"- **Style guide** – {self.guide}",
            f"- **Mode** – {self.mode}",
        ]
        if self.summary:
            lines += ["", self.summary]
        lines += ["", "## Scores", "", "| Criterion | Score |", "|---|---|"]
        for c in CRITERIA:
            value = self.scores.get(c)
            lines.append(f"| {LABELS[c]} | {'not scored' if value is None else f'{value}/10'} |")
        lines += ["", "## Findings", ""]
        if not self.findings:
            lines.append("No findings.")
        for f in self.findings:
            where = f"line {f.line}" if f.line else "line unknown"
            lines.append(f"- **{f.rule}** ({f.severity}, {where}, {f.source}) – {f.message}")
            if f.quote:
                lines.append(f"  - Quote: `{_tick(f.quote)}`")
            if f.fix:
                lines.append(f"  - Fix: {f.fix}")
        if self.notes:
            lines += ["", "## Notes", ""] + [f"- {n}" for n in self.notes]
        return "\n".join(lines) + "\n"


def _tick(text: str) -> str:
    return " ".join(text.split()).replace("`", "'")


def _fix_for(rule: Rule, quote: str) -> str:
    key = quote.lower().replace("’", "'")
    if rule.check == "contractions" and key in _CONTRACTIONS:
        expanded = _CONTRACTIONS[key]
        return f"Write '{expanded[0].upper() + expanded[1:] if quote[:1].isupper() else expanded}'."
    if rule.check == "banned_terms":
        use = rule.params.get("terms", {}).get(quote.lower()) if isinstance(rule.params.get("terms"), dict) else None
        if use:
            return f"Write '{use}'."
    return rule.fix


def _findings_from(results, rules_by_id: dict[str, Rule], doc: Document, source: str, line: int | None = None):
    out = []
    for res in results:
        if res.passed or not res.applicable:
            continue
        rule = rules_by_id[res.rule]
        for violation in res.violations:
            quote = quote_from_violation(violation)
            out.append(Finding(
                rule=rule.id, severity=rule.severity, message=violation, quote=quote,
                line=line if line is not None else doc.line_of(quote), fix=_fix_for(rule, quote), source=source,
            ))
    return out


def deterministic_findings(doc: Document, guide: StyleGuide, ctype: ContentType) -> tuple[list[Finding], list]:
    """Run the guide's checks and the content type's structural checks. Returns (findings, structure results)."""
    rules_by_id = {r.id: r for r in guide.checkable}
    findings: list[Finding] = []
    if ctype.id == "ui_microcopy":
        doc.strings = doc.strings or parse_ui_strings(doc)
        for s in doc.strings:
            results = [apply_rule(r, s.text) for r in guide.checkable]
            findings += _findings_from(results, rules_by_id, doc, "check", line=s.line)
    else:
        findings += _findings_from([apply_rule(r, doc.body) for r in guide.checkable], rules_by_id, doc, "check")
    structure_results = [apply_requirement(r, doc) for r in ctype.checkable]
    req_by_id = {r.id: r for r in ctype.checkable}
    findings += _findings_from(structure_results, req_by_id, doc, "structure")
    if ctype.id == "ui_microcopy":
        by_text = {s.text: s.line for s in doc.strings}
        for f in findings:
            if f.source == "structure" and f.line is None:
                f.line = next((ln for text, ln in by_text.items() if text and text in f.message), None)
    return findings, structure_results


def style_score(findings: list[Finding]) -> int:
    per_rule: dict[str, float] = {}
    for f in findings:
        if f.source in ("check", "model-style"):
            per_rule[f.rule] = min(PER_RULE_CAP, per_rule.get(f.rule, 0.0) + PENALTY[f.severity])
    return clamp(10 - sum(per_rule.values()))


def structure_score(results, requirements: dict[str, Rule]) -> int | None:
    applicable = [r for r in results if r.applicable]
    if not applicable:
        return None
    weight = {"error": 3, "warning": 2, "suggestion": 1}
    total = sum(weight[requirements[r.rule].severity] for r in applicable)
    lost = sum(weight[requirements[r.rule].severity] for r in applicable if not r.passed)
    return clamp(10 * (total - lost) / total)


def clamp(value) -> int:
    return max(1, min(10, int(round(float(value)))))


def verdict_for(scores: dict[str, int | None], findings: list[Finding]) -> str:
    present = [v for v in scores.values() if v is not None]
    if any(v <= 4 for v in present):
        return "fail"
    if all(v >= 7 for v in present) and not any(f.severity == "error" for f in findings):
        return "pass"
    return "revise"


def sort_findings(findings: list[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda f: (f.line or 10**9, SEVERITY_ORDER[f.severity], f.rule))


# ------------------------------------------------------------ model layer

def build_review_prompt(template: str, guide: StyleGuide, ctype: ContentType) -> str:
    rules = "\n".join(f"- {r.id} ({r.severity}): {r.summary}" for r in guide.judgment)
    reqs = "\n".join(f"- {r.id} ({r.severity}): {r.summary}" for r in ctype.requirements) or "- none"
    return (
        template.replace("{{guide_name}}", guide.label)
        .replace("{{guide_text}}", guide.text().strip())
        .replace("{{judgment_rules}}", rules or "- none")
        .replace("{{content_type}}", ctype.name)
        .replace("{{requirements}}", reqs)
    )


def build_review_message(doc: Document, ctype: ContentType, findings: list[Finding]) -> str:
    known = "\n".join(f"- {f.rule}: {f.message}" for f in findings) or "- none"
    return (
        f'<document type="{ctype.id}">\n{doc.body.strip()}\n</document>\n\n'
        f"<deterministic_findings>\n{known}\n</deterministic_findings>"
    )


@dataclass
class ModelReview:
    scores: dict[str, int] = field(default_factory=dict)
    summary: str = ""
    findings: list[Finding] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    parse_ok: bool = False
    error: str = ""


def parse_model_review(raw: str, doc: Document, rules: dict[str, Rule]) -> ModelReview:
    """Validate a model's JSON review: clamp scores, keep only known rules and quotes found in the text."""
    blob = extract_json_object(raw)
    if blob is None:
        return ModelReview(error="no JSON object in model response")
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        return ModelReview(error=f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        return ModelReview(error="model JSON is not an object")
    out = ModelReview(summary=str(data.get("summary", "")).strip())
    raw_scores = data.get("scores") or {}
    problems = []
    for c in CRITERIA:
        try:
            out.scores[c] = clamp(raw_scores[c])
        except (KeyError, TypeError, ValueError):
            problems.append(f"missing or invalid score for {c}")
    for item in data.get("findings") or []:
        if not isinstance(item, dict):
            continue
        rule_id, quote = str(item.get("rule", "")).strip(), str(item.get("quote", "")).strip()
        rule = rules.get(rule_id)
        if rule is None:
            out.dropped.append(f"unknown rule {rule_id!r}")
            continue
        line = doc.line_of(quote) if quote else None
        if quote and line is None:
            out.dropped.append(f"{rule_id}: quote not found in the document")
            continue
        out.findings.append(Finding(
            rule=rule.id, severity=rule.severity, message=rule.summary, quote=quote, line=line,
            fix=str(item.get("fix", "")).strip(), source="model",
        ))
    out.parse_ok = not problems
    out.error = "; ".join(problems)
    return out


def review(
    doc: Document,
    guide: StyleGuide,
    ctype: ContentType,
    *,
    client: LLMClient | None = None,
    model: str = "",
    template: str = "",
    max_tokens: int = 2000,
    temperature: float | None = 0.0,
) -> ReviewReport:
    findings, structure_results = deterministic_findings(doc, guide, ctype)
    scores: dict[str, int | None] = {c: None for c in CRITERIA}
    scores["style_compliance"] = style_score(findings)
    scores["structure"] = structure_score(structure_results, {r.id: r for r in ctype.checkable})
    report = ReviewReport(path=doc.name, content_type=ctype.id, guide=guide.label, scores=scores, verdict="")

    if client is None:
        report.notes.append(
            "Deterministic checks only. Judgment rules, technical clarity, and scannability need a model: "
            "run the matching PAKT reviewer skill, or pass --model."
        )
    else:
        report.mode = "checks+model"
        judgment = {r.id: r for r in [*guide.judgment, *ctype.judgment]}
        completion = client.complete(
            model=model, system=build_review_prompt(template, guide, ctype),
            user=build_review_message(doc, ctype, findings), max_tokens=max_tokens, temperature=temperature,
        )
        parsed = parse_model_review(completion.text, doc, judgment)
        if parsed.error:
            report.notes.append(f"Model review problem: {parsed.error}")
        for c, value in parsed.scores.items():
            current = scores.get(c)
            scores[c] = value if current is None else min(current, value)
        findings += parsed.findings
        report.summary = parsed.summary
        report.notes += [f"Dropped model finding: {d}" for d in parsed.dropped]

    report.findings = sort_findings(findings)
    report.verdict = verdict_for(scores, report.findings)
    return report


def load_template(path) -> str:
    """Read a prompt file and drop its front matter header."""
    _, body, _ = split_front_matter(Path(path).read_text(encoding="utf-8"))
    return body.strip() + "\n"
