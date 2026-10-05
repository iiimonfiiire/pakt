"""Documents under review: front matter, body, UI strings, and line lookup for findings."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


@dataclass(frozen=True)
class UIString:
    kind: str
    key: str
    text: str
    line: int | None = None


@dataclass
class Document:
    raw: str
    body: str
    body_line: int = 1
    meta: dict = field(default_factory=dict)
    path: Path | None = None
    strings: list[UIString] = field(default_factory=list)

    @property
    def name(self) -> str:
        return str(self.path) if self.path else "<text>"

    def line_of(self, quote: str) -> int | None:
        line = locate(self.body, quote)
        return None if line is None else line + self.body_line - 1


def split_front_matter(text: str) -> tuple[dict, str, int]:
    """Return (meta, body, line number where the body starts)."""
    m = _FRONT_MATTER.match(text)
    if not m:
        return {}, text, 1
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip().strip("'\"")
    return meta, text[m.end():], m.group(0).count("\n") + 1


def load_document(path: Path) -> Document:
    return parse_document(path.read_text(encoding="utf-8"), path)


def parse_document(text: str, path: Path | None = None) -> Document:
    text = text.replace("\r\n", "\n")
    if path is not None and path.suffix.lower() == ".json":
        return Document(raw=text, body=text, path=path)
    meta, body, start = split_front_matter(text)
    return Document(raw=text, body=body, body_line=start, meta=meta, path=path)


# ------------------------------------------------------------- UI strings

UI_KINDS = {
    "button": ("button", "btn", "cta", "action"),
    "error": ("error", "err", "failure", "invalid"),
    "tooltip": ("tooltip", "hint", "help"),
    "empty_state": ("empty", "empty_state", "emptystate", "zero"),
    "toast": ("toast", "snackbar", "notification", "success"),
    "placeholder": ("placeholder",),
    "title": ("title", "heading", "header"),
    "label": ("label", "field"),
    "body": ("body", "description", "message", "text"),
}
_KIND_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?([A-Za-z][A-Za-z _-]{1,30}?)(?:\*\*)?\s*:\s+(.+?)\s*$")


def kind_for(name: str) -> str | None:
    lowered = name.lower().replace("-", "_").replace(" ", "_")
    if lowered in UI_KINDS:
        return lowered
    parts = re.split(r"[._\s]+", lowered)
    for kind, hints in UI_KINDS.items():
        if any(h in parts or lowered.endswith(h) for h in hints):
            return kind
    return None


def parse_ui_strings(doc: Document) -> list[UIString]:
    """Read UI strings from a JSON string file or from `kind: text` lines."""
    if doc.path is not None and doc.path.suffix.lower() == ".json":
        data = json.loads(doc.raw)
        out = []
        for key, value in _flatten(data):
            line = _json_line(doc.raw, key.rsplit(".", 1)[-1])
            out.append(UIString(kind_for(key) or "body", key, value, line))
        return out
    out = []
    for offset, raw_line in enumerate(doc.body.splitlines()):
        line = raw_line.strip()
        if not line or line.startswith(("#", "<!--", "|")):
            continue
        m = _KIND_LINE.match(line)
        kind = kind_for(m.group(1)) if m else None
        text = m.group(2) if m and kind else re.sub(r"^[-*]\s+", "", line)
        text = text.strip().strip("\"'“”")
        out.append(UIString(kind or "body", m.group(1).strip() if m and kind else "", text, doc.body_line + offset))
    return out


def _flatten(data, prefix: str = ""):
    if isinstance(data, dict):
        for key, value in data.items():
            yield from _flatten(value, f"{prefix}.{key}" if prefix else str(key))
    elif isinstance(data, str):
        yield prefix, data


def _json_line(raw: str, key: str) -> int | None:
    m = re.search(rf'"{re.escape(key)}"\s*:', raw)
    return None if not m else raw.count("\n", 0, m.start()) + 1


# ----------------------------------------------------------- line lookup

_PLACEHOLDER_TOKENS = re.compile(r"\bCODE\b|\bURL\b")


def quote_from_violation(violation: str) -> str:
    """Pull the quoted text out of a rule violation such as 'contraction: don't'."""
    quote = violation.split(": ", 1)[1] if ": " in violation else violation
    quote = re.sub(r" \(use '[^']*'\)$", "", quote)
    return quote[:-3] if quote.endswith("...") else quote


def locate(text: str, quote: str) -> int | None:
    """Find the 1-based line where `quote` starts, ignoring whitespace differences."""
    fragments = [f.strip(" .,;:") for f in _PLACEHOLDER_TOKENS.split(quote)]
    fragment = max(fragments, key=len, default="")
    if len(fragment) < 2:
        return None
    chars: list[str] = []
    positions: list[int] = []
    previous_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if previous_space:
                continue
            chars.append(" ")
            previous_space = True
        else:
            chars.append(ch)
            previous_space = False
        positions.append(i)
    haystack = "".join(chars).lower()
    needle = " ".join(fragment.split()).lower()
    k = haystack.find(needle)
    if k < 0:
        return None
    return text.count("\n", 0, positions[k]) + 1
