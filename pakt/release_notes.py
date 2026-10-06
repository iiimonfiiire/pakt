"""Release-notes drafter: raw commits, pull requests, and tickets in; a draft for human review out."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from .document import split_front_matter
from .structure import ContentType

DRAFT_BANNER = (
    "> **Warning:** Draft for human review. Rewrite each line for the reader, fill every TODO, "
    "then run `pakt release-notes approve`. Do not publish this draft as is."
)
TODO = "TODO"
INTERNAL_TYPES = {"chore", "test", "tests", "ci", "build", "docs", "style", "refactor", "revert"}
SLOT_BY_TYPE = {
    "feat": "new", "feature": "new", "perf": "improved", "improvement": "improved", "enhancement": "improved",
    "fix": "fixed", "bug": "fixed", "security": "security", "sec": "security", "deprecate": "deprecated",
    "deprecation": "deprecated", "remove": "deprecated", "removal": "deprecated", "breaking": "deprecated",
}
API_SCOPES = {"api", "sdk", "cli", "webhook", "webhooks", "graphql", "rest"}
DEFAULT_SLOTS = {
    "new": "New features", "improved": "Improvements", "fixed": "Bug fixes", "security": "Security updates",
    "api": "API and developer changes", "deprecated": "Deprecations and removals",
}
NO_CHANGES = "No changes in this release."
DEPRECATION_FIELDS = ("Feature name", "End-of-life date", "Impact or reason", "Migration path")

_HASH = re.compile(r"^([0-9a-f]{7,40})\s+(.*)$")
_CONVENTIONAL = re.compile(r"^(?P<type>\w+)(?:\((?P<scope>[^)]*)\))?(?P<bang>!)?:\s*(?P<summary>.+)$")


@dataclass(frozen=True)
class Change:
    source: str
    type: str
    summary: str
    scope: str = ""
    breaking: bool = False

    @property
    def internal(self) -> bool:
        return self.type in INTERNAL_TYPES and not self.breaking

    @property
    def slot(self) -> str | None:
        if self.breaking:
            return "deprecated"
        if self.type in ("feat", "feature", "perf", "fix") and self.scope.lower() in API_SCOPES:
            return "api"
        if self.scope.lower() == "security":
            return "security"
        return SLOT_BY_TYPE.get(self.type)


def parse_commits(text: str) -> list[Change]:
    """Parse one commit per line, optionally prefixed by a hash, in conventional-commit form."""
    changes = []
    for n, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        source = f"line {n}"
        m = _HASH.match(line)
        if m:
            source, line = m.group(1)[:7], m.group(2)
        breaking = "BREAKING CHANGE" in line
        line = line.replace("BREAKING CHANGE:", "").strip()
        c = _CONVENTIONAL.match(line)
        if c:
            changes.append(Change(
                source=source, type=c["type"].lower(), summary=c["summary"].strip(), scope=c["scope"] or "",
                breaking=breaking or bool(c["bang"]),
            ))
        else:
            changes.append(Change(source=source, type="other", summary=line, breaking=breaking))
    return changes


def parse_items(path: Path) -> list[Change]:
    """Parse pull requests or tickets from JSONL: {id, title, type?, labels?, breaking?}."""
    changes = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        if not row.get("id") or not row.get("title"):
            raise ValueError(f"{path.name}:{n}: every item needs 'id' and 'title'")
        labels = {str(label).lower() for label in row.get("labels", [])}
        kind = str(row.get("type") or "").lower()
        if not kind:
            order = ("breaking", "deprecation", "security", "bug", "feature", "enhancement", "chore")
            kind = next((k for k in order if k in labels), "other")
        scope = "api" if labels & API_SCOPES else ""
        changes.append(Change(
            source=str(row["id"]), type=kind, summary=str(row["title"]).strip(), scope=scope,
            breaking=bool(row.get("breaking")) or "breaking" in labels or kind == "breaking",
        ))
    return changes


def sections(ctype: ContentType | None) -> tuple[list[str], dict[str, str], bool]:
    """The guide's release-note headings, the slot each change kind maps to, and whether every heading is required."""
    req = None if ctype is None else next((r for r in ctype.requirements if r.check == "allowed_headings"), None)
    if req is None or not req.params.get("allowed"):
        return list(DEFAULT_SLOTS.values()), dict(DEFAULT_SLOTS), True
    return list(req.params["allowed"]), dict(req.params.get("slots", {})), bool(req.params.get("required"))


def _sentence(text: str) -> str:
    text = text.strip()
    text = text[0].upper() + text[1:] if text else text
    return text if text.endswith((".", "!", "?")) else text + "."


def draft(changes: list[Change], product: str, version: str, ctype: ContentType | None = None) -> str:
    groups, slots, required = sections(ctype)
    buckets: dict[str, list[Change]] = {g: [] for g in groups}
    unsorted: list[Change] = []
    for change in changes:
        if change.internal:
            continue
        heading = slots.get(change.slot or "")
        if heading in buckets:
            buckets[heading].append(change)
        else:
            unsorted.append(change)
    deprecated_heading = slots.get("deprecated")
    lines = [
        "---", "status: draft", "pakt_type: release_note", "generated_by: pakt release-notes", "---",
        f"# {product} {version} release notes", "", DRAFT_BANNER, "",
    ]
    for name in groups:
        if not buckets[name] and not required:
            continue
        lines += [f"## {name}", ""]
        if not buckets[name]:
            lines.append(NO_CHANGES)
        for c in buckets[name]:
            if name == deprecated_heading:
                lines.append(f"> **Warning:** {_sentence(c.summary)} <!-- source: {c.source} -->")
                lines += [f"> - **{field}** – {TODO}" for field in DEPRECATION_FIELDS]
                lines.append("")
            else:
                lines.append(f"- {_sentence(c.summary)} <!-- source: {c.source} -->")
        lines.append("")
    if unsorted:
        lines += [f"{TODO}: Move each of these changes under a heading, or delete it.", ""]
        lines += [f"- {_sentence(c.summary)} <!-- source: {c.source} -->" for c in unsorted]
        lines.append("")
    internal = [c for c in changes if c.internal]
    if internal:
        lines += ["<!-- Left out as internal. Check that none of these affect readers:"]
        lines += [f"- {c.type}: {c.summary} (source: {c.source})" for c in internal]
        lines += ["-->", ""]
    return "\n".join(lines).rstrip() + "\n"


class ApprovalError(RuntimeError):
    pass


def approve(text: str, approved_by: str, on: date | None = None) -> str:
    """The human gate: strip the draft markers and record who approved the notes."""
    if not approved_by.strip():
        raise ApprovalError("approval needs the name of the person who approved the notes")
    meta, body, _ = split_front_matter(text)
    if meta.get("status") != "draft":
        raise ApprovalError("this file is not a PAKT release-notes draft (front matter status: draft)")
    body = body.replace(DRAFT_BANNER + "\n\n", "").replace(DRAFT_BANNER, "")
    body = re.sub(r"[ \t]*<!--.*?-->", "", body, flags=re.S)
    if TODO in body:
        raise ApprovalError("the draft still has TODO markers. Fill or delete them first.")
    body = re.sub(r"\n{3,}", "\n\n", body).strip() + "\n"
    meta.pop("generated_by", None)
    meta["status"] = "approved"
    meta["approved_by"] = approved_by.strip()
    meta["approved_on"] = (on or date.today()).isoformat()
    front = "\n".join(f"{k}: {v}" for k, v in meta.items())
    return f"---\n{front}\n---\n{body}"
