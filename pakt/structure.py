"""Content types and their structural requirements, with deterministic structure checks."""

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
    parent: str = ""
    tags: tuple[str, ...] = ()

    @property
    def checkable(self) -> list["Rule"]:
        return [r for r in self.requirements if r.check]

    @property
    def judgment(self) -> list["Rule"]:
        return [r for r in self.requirements if not r.check]


def _result(rule: str, violations: list[str], applicable: bool = True) -> RuleResult:
    return RuleResult(rule, not violations, applicable, tuple(violations))


# ------------------------------------------------------------ helpers

_BULLET = re.compile(r"^\s*[-*+]\s+(.*)$")
_NUMBERED = re.compile(r"^\s*\d+[.)]\s+(.*)$")
_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


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


def section_text(doc: Document, title_words: list[str]) -> list[str]:
    """Bodies of every section whose heading contains any of the words."""
    lines = doc.body.splitlines()
    found = headings(doc)
    out = []
    for n, (lvl, text, idx) in enumerate(found):
        if any(w in text.lower() for w in title_words):
            end = next((j for l2, _, j in found[n + 1:] if l2 <= lvl), len(lines))
            out.append("\n".join(lines[idx + 1:end]))
    return out


def _fences(body: str) -> list[tuple[str, str]]:
    return [(m.group(1).lower(), m.group(2)) for m in re.finditer(r"```([\w+-]*)[^\n]*\n(.*?)```", body, re.S)]


# --------------------------------------------------------------- checks

_DEFAULT_STEP_VERBS = (
    "add", "check", "choose", "clear", "click", "copy", "create", "delete", "drag", "enter", "find", "go",
    "install", "navigate", "open", "paste", "press", "remove", "restart", "run", "save", "select", "set",
    "sign", "tap", "turn", "type",
)


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


def check_allowed_headings(doc: Document, params: dict) -> RuleResult:
    """Section headings must come from the allowed list. Options: every heading required, and in order."""
    allowed = [a.lower() for a in params.get("allowed", [])]
    sections = [text.strip(" :") for lvl, text, _ in headings(doc) if lvl == int(params.get("level", 2))]
    violations = []
    if not sections:
        violations.append(f"no section headings: expected {', '.join(params.get('allowed', []))}")
    known = [s for s in sections if s.lower() in allowed]
    for s in sections:
        if s.lower() not in allowed:
            violations.append(f"unexpected heading: {s}")
    if params.get("required") and sections:
        violations += [f"missing heading: {a}" for a in params.get("allowed", []) if a.lower() not in [k.lower() for k in known]]
    if params.get("ordered"):
        positions = [allowed.index(s.lower()) for s in known]
        for prev, cur, name in zip(positions, positions[1:], known[1:]):
            if cur < prev:
                violations.append(f"heading out of order: {name}")
    return _result("allowed_headings", violations)


def check_section_order(doc: Document, params: dict) -> RuleResult:
    """Required sections, found by heading keywords, by the first numbered list, or by the intro, in order."""
    found = headings(doc)
    lines = doc.body.splitlines()
    first_section = next((i for lvl, _, i in found if lvl >= 2), len(lines))
    title_line = next((i for lvl, _, i in found if lvl == 1), -1)
    intro = any(l.strip() and not l.startswith("#") for l in lines[title_line + 1:first_section])
    first_list = next((i for i, l in enumerate(lines) if _NUMBERED.match(l)), None)
    positions: list[tuple[str, int | None]] = []
    for section in params.get("sections", []):
        pos = None
        if section.get("intro") and intro:
            pos = title_line + 1
        words = [w.lower() for w in section.get("match", [])]
        hit = next((i for lvl, text, i in found if lvl >= 2 and any(w in text.lower() for w in words)), None)
        if hit is not None and (pos is None or hit < pos):
            pos = hit
        if section.get("numbered") and first_list is not None and (pos is None or first_list < pos):
            pos = first_list
        for marker in section.get("markers", []):
            k = doc.body.find(marker)
            if k >= 0:
                line = doc.body.count("\n", 0, k)
                pos = line if pos is None else min(pos, line)
        positions.append((section["name"], pos))
    violations = [f"missing section: {name}" for name, pos in positions if pos is None]
    present = [(name, pos) for name, pos in positions if pos is not None]
    for (_, p1), (name, p2) in zip(present, present[1:]):
        if p2 < p1:
            violations.append(f"section out of order: {name}")
    return _result("section_order", violations)


_SCOPE_SIGNALS = re.compile(
    r"\b(?:v\d+(?:\.\d+)+|version \d|macOS|Windows|Linux|iOS|Android|Ubuntu|Chrome|Safari|Firefox|firmware)\b"
)


def check_environment_section(doc: Document, params: dict) -> RuleResult:
    """When the text names versions, operating systems, or platforms, an environment or scope section must exist."""
    signals = _SCOPE_SIGNALS.findall(mask_code(doc.body))
    if not signals:
        return _result("environment_section", [], applicable=False)
    words = [w.lower() for w in params.get("match", ["environment", "scope", "applies to", "affected versions"])]
    ok = any(lvl >= 2 and any(w in text.lower() for w in words) for lvl, text, _ in headings(doc))
    return _result("environment_section", [] if ok else [f"names {signals[0]} but has no environment or scope section"])


def check_no_procedures(doc: Document, params: dict) -> RuleResult:
    steps = [m.group(1) for line in mask_code(doc.body).splitlines() if (m := _NUMBERED.match(line))]
    return _result("no_procedures", [f"procedure step in a concept guide: {_clip(steps[0], 60)}"] if steps else [])


_DATE = re.compile(
    r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2} (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{4}\b"
    r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \d{1,2},? \d{4}\b"
)
_MIGRATION = re.compile(r"\]\(|migrat|replace|switch to|instead|move to|upgrade to", re.I)


def _callouts(body: str, label: str) -> list[str]:
    blocks, current = [], None
    for line in body.splitlines():
        if line.startswith(f"> **{label}:**"):
            current = [line]
            blocks.append(current)
        elif current is not None and line.startswith(">"):
            current.append(line)
        else:
            current = None
    return ["\n".join(b) for b in blocks]


def check_deprecation_callout(doc: Document, params: dict) -> RuleResult:
    """Every deprecation sits in a Warning callout that states an end-of-life date and a migration path."""
    sections = section_text(doc, [w.lower() for w in params.get("section", ["deprecation"])])
    if not sections:
        return _result("deprecation_callout", [], applicable=False)
    body = "\n".join(sections)
    prose = [l for l in body.splitlines() if l.strip() and not l.startswith(">") and not l.strip().startswith("<!--")]
    no_change = re.compile(params.get("empty", r"^no (?:changes|deprecations|removals)\b"), re.I)
    prose = [l for l in prose if not no_change.match(l.strip())]
    callouts = _callouts(body, "Warning")
    violations = []
    if prose and not callouts:
        violations.append(f"deprecation outside a Warning callout: {_clip(prose[0].lstrip('-* '), 60)}")
    for block in callouts:
        first = _clip(block.splitlines()[0].replace("> **Warning:**", "").strip(), 50)
        if not _DATE.search(block):
            violations.append(f"Warning callout has no end-of-life date: {first}")
        if not _MIGRATION.search(block):
            violations.append(f"Warning callout has no migration path: {first}")
    return _result("deprecation_callout", violations)


_WE_BUILT = re.compile(
    r"\bwe(?:'ve| have)? (?:added|built|implemented|introduced|shipped|released|refactored|created|developed|rewrote|migrated)\b",
    re.I,
)


def check_engineering_framing(doc: Document, params: dict) -> RuleResult:
    found = [m.group(0) for m in _WE_BUILT.finditer(mask_code(doc.body))]
    return _result("engineering_framing", [f"engineering framing: {f}" for f in found])


_WHY = re.compile(r"\b(?:because|due to|since|as a result of)\b", re.I)


def check_error_no_why(doc: Document, params: dict) -> RuleResult:
    errors = [s for s in doc.strings if s.kind == "error"]
    violations = [f"error explains why: {s.text}" for s in errors if _WHY.search(s.text)]
    return _result("error_no_why", violations, applicable=bool(errors))


_METHODS = "GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS"
_ENDPOINT = re.compile(rf"\b(?:{_METHODS})\s+/\S*")
_LOWER_ENDPOINT = re.compile(rf"(?<![\w/-])(?:{_METHODS.lower()}|{_METHODS.title()})\s+/[\w{{}}/.:-]*")


def check_endpoint_signature(doc: Document, params: dict) -> RuleResult:
    violations = [f"HTTP method not in uppercase: {m.group(0)}" for m in _LOWER_ENDPOINT.finditer(doc.body)]
    if not _ENDPOINT.search(doc.body):
        violations.append("no uppercase method and path, such as GET /v1/items/{id}")
    return _result("endpoint_signature", violations)


def _tables(body: str) -> list[tuple[list[str], list[list[str]]]]:
    lines = body.splitlines()
    out = []
    i = 0
    while i < len(lines) - 1:
        if lines[i].lstrip().startswith("|") and re.match(r"^\s*\|?\s*:?-{3,}", lines[i + 1]):
            header = [c.strip().strip("*`").lower() for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append([c.strip() for c in lines[j].strip().strip("|").split("|")])
                j += 1
            out.append((header, rows))
            i = j
        else:
            i += 1
    return out


def check_params_table(doc: Document, params: dict) -> RuleResult:
    columns = [c.lower() for c in params.get("columns", ["parameter", "type", "required or optional", "description"])]
    tables = _tables(doc.body)
    if any(header == columns for header, _ in tables):
        return _result("params_table", [])
    if tables:
        header = tables[0][0]
        return _result("params_table", [f"parameter table columns are {', '.join(header)}, expected {', '.join(columns)}"])
    return _result("params_table", [f"no parameter table with columns {', '.join(columns)}"])


def check_required_marker(doc: Document, params: dict) -> RuleResult:
    """Required parameters carry an explicit badge or an asterisk, never a bare yes or no."""
    violations, applicable = [], False
    for header, rows in _tables(doc.body):
        col = next((i for i, h in enumerate(header) if "required" in h), None)
        if col is None:
            continue
        applicable = True
        for row in rows:
            if col >= len(row):
                continue
            value = row[col].strip("*` ").lower()
            if value in ("yes", "no", "true", "false", "y", "n", "x", ""):
                violations.append(f"required flag is not explicit for {row[0].strip('`* ')}: {row[col]}")
    return _result("required_marker", violations, applicable)


def check_response_schemas(doc: Document, params: dict) -> RuleResult:
    json_blocks = [code for lang, code in _fences(doc.body) if lang == "json"]
    error = [c for c in json_blocks if re.search(r'"(?:error|errors|code|message)"\s*:', c)]
    success = [c for c in json_blocks if c not in error]
    violations = []
    if not success:
        violations.append("no JSON success response schema")
    if not error:
        violations.append("no JSON error response schema")
    return _result("response_schemas", violations)


_LANGS = {"python", "py", "javascript", "js", "typescript", "ts", "go", "ruby", "java", "csharp", "cs", "php", "node", "kotlin", "swift", "rust"}


def check_code_samples(doc: Document, params: dict) -> RuleResult:
    fences = _fences(doc.body)
    curl = any("curl " in code for _, code in fences)
    other = any(lang in _LANGS for lang, _ in fences)
    violations = ([] if curl else ["no cURL sample"]) + ([] if other else ["no sample in a programming language"])
    return _result("code_samples", violations)


_BEARER = re.compile(r"Bearer\s+(?!<[A-Z0-9_]+>)([^\s\"'`]+)")


def check_masked_tokens(doc: Document, params: dict) -> RuleResult:
    found = [m.group(0) for m in _BEARER.finditer(doc.body)]
    return _result("masked_tokens", [f"unmasked token, write Bearer <TOKEN>: {f}" for f in found], applicable=bool(found) or "Bearer" in doc.body)


_STEP_VERB = re.compile(r"^\s*\d+[.)]\s+\**(\w+)", re.M)


def check_step_verbs(doc: Document, params: dict) -> RuleResult:
    banned = {v.lower(): use for v, use in params.get("banned", {}).items()}
    violations = []
    for m in _STEP_VERB.finditer(mask_code(doc.body)):
        verb = m.group(1).lower()
        if verb in banned:
            violations.append(f"UI verb '{m.group(1)}' is not in the verb mapping (use '{banned[verb]}'): {m.group(1)}")
    return _result("step_verbs", violations)


def check_codename_line(doc: Document, params: dict) -> RuleResult:
    """A codename may appear only in one metadata line at the top, and nowhere else."""
    label = params.get("label", "Internal codename:")
    lines = doc.body.splitlines()
    meta = [i for i, l in enumerate(lines) if label.lower() in l.lower()]
    if not meta:
        mentions = [l for l in lines if re.search(r"\bcodename\b", l, re.I)]
        return _result("codename_line", [f"codename outside the metadata line: {_clip(mentions[0], 60)}"] if mentions else [])
    violations = []
    content_before = [l for l in lines[: meta[0]] if l.strip() and not l.startswith("# ")]
    if content_before or len(meta) > 1:
        violations.append(f"codename line is not a single line at the top: {_clip(lines[meta[0]], 60)}")
    name = lines[meta[0]].split(":", 1)[1].strip().strip("*_.` ")
    if name:
        for i, line in enumerate(lines):
            if i != meta[0] and name.lower() in line.lower():
                violations.append(f"codename used outside the metadata line: {_clip(line.strip(), 60)}")
    return _result("codename_line", violations)


StructureFn = Callable[[Document, dict], RuleResult]

STRUCTURE_CHECKS: dict[str, StructureFn] = {
    "steps_numbered": check_steps_numbered,
    "allowed_headings": check_allowed_headings,
    "section_order": check_section_order,
    "environment_section": check_environment_section,
    "no_procedures": check_no_procedures,
    "deprecation_callout": check_deprecation_callout,
    "engineering_framing": check_engineering_framing,
    "error_no_why": check_error_no_why,
    "endpoint_signature": check_endpoint_signature,
    "params_table": check_params_table,
    "required_marker": check_required_marker,
    "response_schemas": check_response_schemas,
    "code_samples": check_code_samples,
    "masked_tokens": check_masked_tokens,
    "step_verbs": check_step_verbs,
    "codename_line": check_codename_line,
}


def apply_requirement(rule: "Rule", doc: Document) -> RuleResult:
    res = STRUCTURE_CHECKS[rule.check](doc, dict(rule.params))
    return RuleResult(rule.id, res.passed, res.applicable, res.violations)


# --------------------------------------------------------- content types

def load_content_types(guide: "StyleGuide | None" = None, root: Path | None = None) -> dict[str, ContentType]:
    """Load the type definitions, then attach the guide's requirements. A subtype inherits its parent's."""
    from .styleguide import _parse_rule

    path = (root or package_root()) / CONTENT_TYPES_FILE
    if not path.is_file():
        raise ConfigError(f"missing {CONTENT_TYPES_FILE} in {path.parent}")
    data = read_toml(path)
    from_guide = guide.content_types if guide else {}
    types = {}
    for type_id, table in data.items():
        parent = table.get("parent", "")
        reqs: list = [_parse_rule(raw, path, STRUCTURE_CHECKS) for raw in table.get("requirements", [])]
        for source in ([parent] if parent else []) + [type_id]:
            for req in from_guide.get(source, []):
                reqs = [r for r in reqs if r.id != req.id] + [req]
        types[type_id] = ContentType(
            id=type_id, name=table.get("name", type_id), description=table.get("description", ""),
            path_hints=tuple(table.get("path_hints", [])), requirements=tuple(reqs),
            parent=parent, tags=tuple(table.get("tags", [])),
        )
    for t in types.values():
        if t.parent and t.parent not in types:
            raise ConfigError(f"{path}: {t.id} names unknown parent {t.parent!r}")
    return types


def _glob_match(rel: str, pattern: str) -> bool:
    return fnmatch.fnmatch(rel, pattern) or (pattern.startswith("**/") and fnmatch.fnmatch(rel, pattern[3:]))


def refine_type(doc: Document, types: dict[str, ContentType], type_id: str) -> str:
    """Pick a subtype from the content when the chosen type has subtypes, such as kb_article."""
    children = {t.id for t in types.values() if t.parent == type_id}
    if not children:
        return type_id
    body = mask_code(doc.body).lower()
    titles = " ".join(text.lower() for _, text, _ in headings(doc))
    first = next((text.lower() for lvl, text, _ in headings(doc) if lvl == 1), "")

    def pick(candidate: str) -> str | None:
        return candidate if candidate in children else None

    if any(w in titles for w in ("symptom", "resolution")) or ("cause" in titles and "fix" in titles):
        return pick("kb_troubleshooting") or type_id
    if "learning objective" in body or "by the end of this tutorial" in body or "tutorial" in first:
        return pick("tutorial") or type_id
    if "quickstart" in first or "quick start" in first:
        return pick("quickstart") or type_id
    if "walkthrough" in first or "tour" in first:
        return pick("walkthrough") or type_id
    has_steps = any(_NUMBERED.match(line) for line in doc.body.splitlines())
    if has_steps or not check_steps_numbered(doc, {}).passed:
        return pick("kb_task") or type_id
    return pick("kb_concept") or type_id


def detect_type(
    doc: Document,
    types: dict[str, ContentType],
    rel_path: str | None = None,
    type_map: dict[str, str] | None = None,
) -> str:
    """Pick a content type: front matter, then project globs, then path hints, then content."""
    for key in ("pakt_type", "content_type"):
        if doc.meta.get(key) in types:
            return refine_type(doc, types, doc.meta[key])
    rel = rel_path or (doc.path.as_posix() if doc.path else "")
    for pattern, type_id in (type_map or {}).items():
        if rel and _glob_match(rel, pattern) and type_id in types:
            return refine_type(doc, types, type_id)
    if rel.lower().endswith(".json") and "ui_microcopy" in types:
        return "ui_microcopy"
    ordered = sorted(types.values(), key=lambda t: not t.parent)
    for part in reversed(PurePosixPath(rel.lower()).parts):
        words = {part, part.rsplit(".", 1)[0], *re.split(r"[-_.\s]+", part)}
        for ctype in ordered:
            if any(h in words for h in ctype.path_hints):
                return refine_type(doc, types, ctype.id)
    if _ENDPOINT.search(doc.body) and "api_doc" in types:
        return "api_doc"
    titles = {text.lower() for _, text, _ in headings(doc)}
    if {"new features", "bug fixes"} & titles and "release_note" in types:
        return "release_note"
    if "value proposition" in titles and "gtm_brief" in types:
        return "gtm_brief"
    return "general" if "general" in types else next(iter(types))
