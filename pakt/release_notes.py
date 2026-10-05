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
GROUP_INDEX = {"feat": 0, "feature": 0, "perf": 1, "improvement": 1, "enhancement": 1, "fix": 2, "bug": 2, "breaking": 3}
DEFAULT_GROUPS = ["New", "Improved", "Fixed", "Breaking"]

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
            kind = next((k for k in ("breaking", "bug", "feature", "enhancement", "chore") if k in labels), "other")
        changes.append(Change(
            source=str(row["id"]), type=kind, summary=str(row["title"]).strip(),
            breaking=bool(row.get("breaking")) or "breaking" in labels or kind == "breaking",
        ))
    return changes


def group_names(ctype: ContentType | None) -> list[str]:
    if ctype is not None:
        req = next((r for r in ctype.requirements if r.check == "allowed_headings"), None)
        if req and req.params.get("allowed"):
            return list(req.params["allowed"])
    return list(DEFAULT_GROUPS)


def _sentence(text: str) -> str:
    text = text.strip()
    text = text[0].upper() + text[1:] if text else text
    return text if text.endswith((".", "!", "?")) else text + "."


def draft(changes: list[Change], product: str, version: str, ctype: ContentType | None = None) -> str:
    groups = group_names(ctype)
    buckets: dict[str, list[Change]] = {g: [] for g in groups}
    unsorted: list[Change] = []
    for change in changes:
        if change.internal:
            continue
        index = 3 if change.breaking else GROUP_INDEX.get(change.type)
        if index is None or index >= len(groups):
            unsorted.append(change)
        else:
            buckets[groups[index]].append(change)
    lines = [
        "---", "status: draft", "pakt_type: release_note", "generated_by: pakt release-notes", "---",
        f"# {product} {version} release notes", "", DRAFT_BANNER, "",
    ]
    for name in groups:
        if not buckets[name]:
            continue
        lines += [f"## {name}", ""]
        for c in buckets[name]:
            lines.append(f"- {_sentence(c.summary)} <!-- source: {c.source} -->")
            if c.breaking:
                lines.append(f"  {TODO}: Say what readers must change to keep working.")
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
