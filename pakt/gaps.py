"""Docs gap finder: compare tickets, support questions, and changelogs with the docs that exist."""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .document import Document

STOPWORDS = set(
    "about after again also because before being between both cannot could does doing during each from have "
    "having into just more most other over same should some such than that their them then there these they "
    "this those through under until very what when where which while will with would your yours able unable "
    "error issue problem please help when doesnt dont cant wont using user users customer customers question "
    "questions how why anyone someone something possible".split()
)


@dataclass(frozen=True)
class SourceItem:
    id: str
    kind: str
    title: str
    body: str = ""
    date: str = ""
    url: str = ""

    def ref(self) -> dict:
        return {"id": self.id, "kind": self.kind, "title": self.title, "date": self.date, "url": self.url}


@dataclass
class Gap:
    status: str
    topic: str
    sources: list[dict]
    terms: list[str]
    missing_terms: list[str]
    found_in: list[str] = field(default_factory=list)
    inferred: bool = False
    basis: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def load_sources(paths: list[Path]) -> list[SourceItem]:
    items: list[SourceItem] = []
    for path in paths:
        if path.suffix.lower() == ".csv":
            with open(path, newline="", encoding="utf-8") as fh:
                rows = list(csv.DictReader(fh))
        else:
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        for n, row in enumerate(rows, 1):
            if not row.get("id") or not row.get("title"):
                raise ValueError(f"{path.name}:{n}: every source item needs 'id' and 'title'")
            items.append(SourceItem(
                id=str(row["id"]), kind=str(row.get("kind") or "ticket"), title=str(row["title"]),
                body=str(row.get("body") or ""), date=str(row.get("date") or ""), url=str(row.get("url") or ""),
            ))
    seen: set[str] = set()
    for item in items:
        if item.id in seen:
            raise ValueError(f"duplicate source id {item.id!r}")
        seen.add(item.id)
    return items


_EXPLICIT = [
    re.compile(r"`([^`\n]{2,60})`"),
    re.compile(r"\*\*([^*\n]{2,60})\*\*"),
    re.compile(r"[\"“]([^\"”\n]{2,60})[\"”]"),
    re.compile(r"\b([A-Z]{2,}-\d{2,}|E\d{3,}|ERR_[A-Z_]+)\b"),
    re.compile(r"\b((?:GET|POST|PUT|PATCH|DELETE)\s+/[\w/{}:.-]+)"),
]


def explicit_terms(item: SourceItem) -> list[str]:
    """Literal names a doc would have to mention: code, bold UI labels, quoted strings, and error codes."""
    text = f"{item.title}\n{item.body}"
    terms: list[str] = []
    for pattern in _EXPLICIT:
        for m in pattern.finditer(text):
            term = m.group(1).strip()
            if term and term.lower() not in (t.lower() for t in terms) and term != item.id:
                terms.append(term)
    return terms


def keyword_terms(item: SourceItem) -> list[str]:
    words = re.findall(r"[A-Za-z][A-Za-z-]{3,}", item.title)
    return [w for w in dict.fromkeys(w.lower() for w in words) if w not in STOPWORDS][:4]


def _doc_date(doc: Document) -> str:
    for key in ("last_reviewed", "updated", "last_updated", "date"):
        if doc.meta.get(key):
            return doc.meta[key]
    return ""


def find_gaps(items: list[SourceItem], docs: dict[str, Document]) -> list[Gap]:
    corpus = {rel: doc.body.lower() for rel, doc in docs.items()}
    gaps: dict[tuple, Gap] = {}
    for item in items:
        terms = explicit_terms(item)
        inferred = not terms
        if inferred:
            terms = keyword_terms(item)
        if not terms:
            continue
        found_in = sorted(rel for rel, text in corpus.items() if any(t.lower() in text for t in terms))
        missing = [t for t in terms if not any(t.lower() in text for text in corpus.values())]
        if inferred:
            hits = sorted(rel for rel, text in corpus.items() if all(t in text for t in terms))
            status = "missing" if not hits else ""
            found_in = hits
            basis = "Title keywords only, because the source item names nothing literal. No doc mentions them all."
            missing = [t for t in terms if not any(t in text for text in corpus.values())] if not hits else []
        elif len(missing) == len(terms):
            status, basis = "missing", "No doc mentions any literal name from the source item."
        elif missing:
            status, basis = "partial", "Some literal names from the source item appear in no doc."
        else:
            status, basis = "", ""
        if not status and item.date and item.kind in ("changelog", "release", "commit", "pr"):
            older = [rel for rel in found_in if _doc_date(docs[rel]) and _doc_date(docs[rel]) < item.date]
            if older and len(older) == len(found_in):
                status, inferred = "stale", True
                basis = "Inferred: every doc that covers this topic was last updated before the change shipped."
        if not status:
            continue
        key = (status, tuple(sorted(t.lower() for t in missing)) or tuple(found_in))
        gap = gaps.get(key)
        if gap is None:
            gaps[key] = Gap(status, item.title, [item.ref()], terms, missing, found_in, inferred, basis)
        else:
            gap.sources.append(item.ref())
            gap.inferred = gap.inferred and inferred
    order = {"missing": 0, "stale": 1, "partial": 2}
    return sorted(gaps.values(), key=lambda g: (order[g.status], g.inferred, -len(g.sources), g.topic))


def render_markdown(gaps: list[Gap], n_items: int, n_docs: int) -> str:
    lines = [
        "# Docs gap candidates", "",
        f"- **Source items** – {n_items}",
        f"- **Docs scanned** – {n_docs}",
        f"- **Candidates** – {len(gaps)}",
        "",
        "Every candidate cites the source items that revealed it. A candidate marked **Inferred** rests on "
        "keywords or dates, not on a literal match. Confirm it before you act on it.",
        "",
    ]
    if not gaps:
        lines.append("No gap candidates found.")
    for g in gaps:
        label = "Inferred" if g.inferred else "Matched"
        lines += [f"## {g.status.capitalize()}: {g.topic}", ""]
        lines.append(f"- **Basis** – {label}. {g.basis}")
        for s in g.sources:
            where = f" ({s['url']})" if s.get("url") else ""
            date = f", {s['date']}" if s.get("date") else ""
            lines.append(f"- **Source** – {s['kind']} `{s['id']}`{date}: {s['title']}{where}")
        if g.missing_terms:
            lines.append(f"- **Not found in any doc** – {', '.join(f'`{t}`' for t in g.missing_terms)}")
        if g.found_in:
            lines.append(f"- **Related docs** – {', '.join(f'`{p}`' for p in g.found_in)}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
