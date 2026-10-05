"""Content types and their structural conventions, with deterministic structure checks."""

from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Callable

from .config import ConfigError, package_root, read_toml
from .document import Document
from .rules import RuleResult, _clip, mask_code

if TYPE_CHECKING:
    from .styleguide import Rule, StyleGuide

CONTENT_TYPES_FILE = "content-types.toml"


@dataclass(frozen=True)
class ContentType:
    id: str
    name: str
    description: str
    path_hints: tuple[str, ...]
    requirements: tuple["Rule", ...]

    @property
    def checkable(self) -> list["Rule"]:
        return [r for r in self.requirements if r.check]

    @property
    def judgment(self) -> list["Rule"]:
        return [r for r in self.requirements if not r.check]


def _result(rule: str, violations: list[str], applicable: bool = True) -> RuleResult:
    return RuleResult(rule, not violations, applicable, tuple(violations))


# --------------------------------------------------------------- checks

_DEFAULT_STEP_VERBS = (
    "add", "check", "choose", "clear", "click", "copy", "create", "delete", "drag", "enter", "find", "go",
    "install", "navigate", "open", "paste", "press", "remove", "restart", "run", "save", "select", "set",
    "sign", "tap", "turn", "type",
)
_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def check_steps_numbered(doc: Document, params: dict) -> RuleResult:
    verbs = {v.lower() for v in params.get("verbs", _DEFAULT_STEP_VERBS)}
    lines = mask_code(doc.body).splitlines()
    bullets = [m.group(1) for line in lines if (m := _BULLET.match(line))]
    numbered = any(_NUMBERED.match(line) for line in lines)
    steps = []
    for item in bullets:
        first = re.sub(r"^[*_]+", "", item).split(" ", 1)[0].strip("*_,.").lower()
        if first in verbs:
            steps.append(item)
    violations = [f"unnumbered step: {_clip(s, 60)}" for s in steps] if len(steps) >= 2 else []
    return _result("steps_numbered", violations, applicable=bool(bullets) or numbered)


def headings(doc: Document) -> list[tuple[int, str, int]]:
    """Return (level, text, line index in body) for every Markdown heading outside code."""
    out = []
    in_fence = False
    for i, line in enumerate(doc.body.splitlines()):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        m = None if in_fence else _HEADING.match(line)
        if m:
            out.append((len(m.group(1)), m.group(2).strip(), i))
    return out


def check_allowed_headings(doc: Document, params: dict) -> RuleResult:
    allowed = {a.lower() for a in params.get("allowed", [])}
    sections = [(lvl, text) for lvl, text, _ in headings(doc) if lvl >= 2]
    violations = []
    if not sections:
        violations.append(f"no section headings: expected {', '.join(params.get('allowed', []))}")
    for _, text in sections:
        if text.strip(" :").lower() not in allowed:
            violations.append(f"unexpected heading: {text}")
    return _result("allowed_headings", violations)


_VERSION = re.compile(r"\bv?\d+\.\d+(?:\.\d+)?\b")


def check_title_has_version(doc: Document, params: dict) -> RuleResult:
    first = next((line for line in doc.body.splitlines() if line.strip()), "")
    ok = bool(_VERSION.search(first))
    return _result("title_has_version", [] if ok else [f"no version number in title: {_clip(first, 60)}"])


def section_text(doc: Document, title: str) -> str | None:
    lines = doc.body.splitlines()
    found = headings(doc)
    for n, (lvl, text, idx) in enumerate(found):
        if text.strip(" :").lower() == title.lower():
            end = next((j for l2, _, j in found[n + 1:] if l2 <= lvl), len(lines))
            return "\n".join(lines[idx + 1:end])
    return None


def check_section_mentions(doc: Document, params: dict) -> RuleResult:
    body = section_text(doc, params.get("section", ""))
    if body is None:
        return _result("section_mentions", [], applicable=False)
    keywords = [k.lower() for k in params.get("keywords", [])]
    ok = any(k in body.lower() for k in keywords)
    return _result("section_mentions", [] if ok else [f"{params.get('section')} section has no migration note: {params.get('section')}"])


_COMMIT_PREFIX = re.compile(r"^\s*(?:[-*]\s+)?((?:feat|fix|chore|refactor|test|tests|ci|build|docs|perf|style)(?:\([^)]*\))?!?:)", re.I)


def check_no_commit_prefixes(doc: Document, params: dict) -> RuleResult:
    found = [m.group(1) for line in doc.body.splitlines() if (m := _COMMIT_PREFIX.match(line))]
    return _result("no_commit_prefixes", [f"commit prefix left in: {f}" for f in found])


def check_string_length(doc: Document, params: dict) -> RuleResult:
    limits = {k: int(v) for k, v in params.get("limits", {}).items()}
    violations = []
    for s in doc.strings:
        limit = limits.get(s.kind)
        if limit and len(s.text) > limit:
            violations.append(f"{s.kind} is {len(s.text)} characters, limit {limit}: {s.text}")
    return _result("string_length", violations, applicable=bool(doc.strings))


def check_button_punctuation(doc: Document, params: dict) -> RuleResult:
    buttons = [s for s in doc.strings if s.kind == "button"]
    violations = [f"button ends with punctuation: {s.text}" for s in buttons if s.text.rstrip().endswith((".", "!"))]
    return _result("button_punctuation", violations, applicable=bool(buttons))


def check_error_exclamation(doc: Document, params: dict) -> RuleResult:
    errors = [s for s in doc.strings if s.kind == "error"]
    violations = [f"exclamation mark in error: {s.text}" for s in errors if "!" in s.text]
    return _result("error_exclamation", violations, applicable=bool(errors))


_ENDPOINT = re.compile(r"\b(?:GET|POST|PUT|PATCH|DELETE|HEAD)\s+/\S*")


def check_endpoint_signature(doc: Document, params: dict) -> RuleResult:
    ok = bool(_ENDPOINT.search(doc.body))
    return _result("endpoint_signature", [] if ok else ["no method and path, such as GET /v1/items"])


def _table_headers(body: str) -> list[list[str]]:
    lines = body.splitlines()
    out = []
    for i in range(len(lines) - 1):
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            out.append([c.strip().strip("*`").lower() for c in lines[i].strip().strip("|").split("|")])
    return out


def check_params_table(doc: Document, params: dict) -> RuleResult:
    columns = [c.lower() for c in params.get("columns", ["name", "type", "required", "description"])]
    tables = _table_headers(doc.body)
    if any(all(c in header for c in columns) for header in tables):
        return _result("params_table", [])
    if tables:
        missing = sorted({c for c in columns if not any(c in h for h in tables)})
        return _result("params_table", [f"parameter table lacks columns: {', '.join(missing) or ', '.join(columns)}"])
    return _result("params_table", [f"no parameter table with columns {', '.join(columns)}"])


def check_error_codes(doc: Document, params: dict) -> RuleResult:
    ok = bool(re.search(r"\b[45]\d\d\b", doc.body))
    return _result("error_codes", [] if ok else ["no error response, such as a 4xx or 5xx status code"])


def check_code_example(doc: Document, params: dict) -> RuleResult:
    ok = "```" in doc.body
    return _result("code_example", [] if ok else ["no fenced code example"])


StructureFn = Callable[[Document, dict], RuleResult]

STRUCTURE_CHECKS: dict[str, StructureFn] = {
    "steps_numbered": check_steps_numbered,
    "allowed_headings": check_allowed_headings,
    "title_has_version": check_title_has_version,
    "section_mentions": check_section_mentions,
    "no_commit_prefixes": check_no_commit_prefixes,
    "string_length": check_string_length,
    "button_punctuation": check_button_punctuation,
    "error_exclamation": check_error_exclamation,
    "endpoint_signature": check_endpoint_signature,
    "params_table": check_params_table,
    "error_codes": check_error_codes,
    "code_example": check_code_example,
}


def apply_requirement(rule: "Rule", doc: Document) -> RuleResult:
    res = STRUCTURE_CHECKS[rule.check](doc, dict(rule.params))
    return RuleResult(rule.id, res.passed, res.applicable, res.violations)


# --------------------------------------------------------- content types

def load_content_types(guide: "StyleGuide | None" = None, root: Path | None = None) -> dict[str, ContentType]:
    """Load the bundled content types, then let the guide replace or add requirements by ID."""
    from .styleguide import _parse_rule

    path = (root or package_root()) / CONTENT_TYPES_FILE
    if not path.is_file():
        raise ConfigError(f"missing {CONTENT_TYPES_FILE} in {path.parent}")
    data = read_toml(path)
    types = {}
    for type_id, table in data.items():
        reqs = [_parse_rule(raw, path, STRUCTURE_CHECKS) for raw in table.get("requirements", [])]
        overrides = (guide.content_types if guide else {}).get(type_id, [])
        for override in overrides:
            reqs = [r for r in reqs if r.id != override.id] + [override]
        types[type_id] = ContentType(
            id=type_id, name=table.get("name", type_id), description=table.get("description", ""),
            path_hints=tuple(table.get("path_hints", [])), requirements=tuple(reqs),
        )
    return types


def _glob_match(rel: str, pattern: str) -> bool:
    return fnmatch.fnmatch(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:]))


def detect_type(
    doc: Document,
    types: dict[str, ContentType],
    rel_path: str | None = None,
    type_map: dict[str, str] | None = None,
) -> str:
    """Pick a content type: front matter, then project globs, then path hints, then content."""
    for key in ("pakt_type", "content_type"):
        if doc.meta.get(key) in types:
            return doc.meta[key]
    rel = rel_path or (doc.path.as_posix() if doc.path else "")
    for pattern, type_id in (type_map or {}).items():
        if rel and _glob_match(rel, pattern) and type_id in types:
            return type_id
    if rel.lower().endswith(".json") and "ui_microcopy" in types:
        return "ui_microcopy"
    parts = {p for part in PurePosixPath(rel.lower()).parts for p in re.split(r"[-_.\s]+", part)} | {
        part for part in PurePosixPath(rel.lower()).parts
    }
    for type_id, ctype in types.items():
        if any(h in parts for h in ctype.path_hints):
            return type_id
    if _ENDPOINT.search(doc.body) and "api_doc" in types:
        return "api_doc"
    if check_title_has_version(doc, {}).passed and len(headings(doc)) >= 2 and "release_note" in types:
        return "release_note"
    return "general" if "general" in types else next(iter(types))
