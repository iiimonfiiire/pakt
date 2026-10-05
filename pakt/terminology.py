"""Terminology: a product glossary of preferred terms, banned variants, and definitions."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .config import ConfigError, read_toml
from .document import Document
from .review import Finding
from .rules import mask_code

COMMON_ACRONYMS = {
    "API", "APIs", "CLI", "CSV", "CSS", "FAQ", "GB", "HTML", "HTTP", "HTTPS", "ID", "IDs", "JSON", "KB", "MB",
    "OK", "PDF", "PNG", "JPG", "SDK", "SQL", "SSO", "TB", "UI", "URL", "URLs", "USB", "UTC", "UX", "XML", "YAML",
}

# Common variant families. A suggestion run proposes one glossary entry per family it sees.
VARIANT_FAMILIES: list[tuple[str, list[str]]] = [
    ("sign in", ["log in", "login", "log on", "logon", "signin"]),
    ("sign out", ["log out", "logout", "log off", "signout"]),
    ("email", ["e-mail"]),
    ("website", ["web site"]),
    ("checkbox", ["check box", "tick box"]),
    ("drop-down list", ["dropdown", "drop down", "pull-down", "pulldown"]),
    ("username", ["user name"]),
    ("dialog", ["dialog box", "dialogue"]),
    ("two-factor authentication", ["2FA", "two factor authentication", "2-factor authentication"]),
    ("API key", ["api-key", "apikey"]),
    ("workspace", ["work space"]),
    ("filename", ["file name"]),
]


@dataclass(frozen=True)
class Term:
    preferred: str
    variants: tuple[str, ...] = ()
    definition: str = ""
    case_sensitive: bool = False


@dataclass(frozen=True)
class Banned:
    term: str
    reason: str = ""
    replacement: str = ""


@dataclass
class Glossary:
    terms: list[Term] = field(default_factory=list)
    banned: list[Banned] = field(default_factory=list)
    allow: set[str] = field(default_factory=set)
    path: Path | None = None

    @property
    def known(self) -> set[str]:
        words = {t.preferred for t in self.terms} | {v for t in self.terms for v in t.variants}
        return words | {b.term for b in self.banned} | self.allow | COMMON_ACRONYMS


def load_glossary(path: Path) -> Glossary:
    if not path.is_file():
        raise ConfigError(f"glossary not found: {path}")
    data = read_toml(path)
    terms = []
    for raw in data.get("terms", []):
        if not raw.get("preferred"):
            raise ConfigError(f"{path}: every [[terms]] entry needs 'preferred'")
        terms.append(Term(
            preferred=raw["preferred"], variants=tuple(raw.get("variants", [])),
            definition=raw.get("definition", ""), case_sensitive=bool(raw.get("case_sensitive", False)),
        ))
    banned = [Banned(b["term"], b.get("reason", ""), b.get("replacement", "")) for b in data.get("banned", []) if b.get("term")]
    allow = set(data.get("jargon", {}).get("allow", []))
    return Glossary(terms, banned, allow, path)


def _pattern(term: str, case_sensitive: bool) -> re.Pattern:
    body = r"[\s-]+".join(re.escape(part) for part in term.split())
    return re.compile(rf"(?<![\w-]){body}(?![\w-])", 0 if case_sensitive else re.I)


def _occurrences(text: str, term: str, case_sensitive: bool = False) -> list[str]:
    return [m.group(0) for m in _pattern(term, case_sensitive).finditer(text)]


_ACRONYM = re.compile(r"\b[A-Z][A-Z0-9]{1,5}s?\b")


def defined_acronyms(text: str) -> set[str]:
    """Acronyms the text expands, as in 'single sign-on (SSO)' or 'SSO (single sign-on)'."""
    found = set(re.findall(r"\(([A-Z][A-Z0-9]{1,5})s?\)", text))
    found |= set(re.findall(r"\b([A-Z][A-Z0-9]{1,5})\s+\((?:[a-z][\w-]*\s){1,6}", text))
    return found


def check_terms(doc: Document, glossary: Glossary) -> list[Finding]:
    text = mask_code(doc.body)
    findings: list[Finding] = []
    for term in glossary.terms:
        preferred_hits = _occurrences(text, term.preferred, term.case_sensitive)
        variant_hits: Counter = Counter()
        for variant in term.variants:
            for hit in _occurrences(text, variant, term.case_sensitive):
                variant_hits[variant] += 1
                findings.append(Finding(
                    rule="glossary_variant", severity="warning",
                    message=f"'{hit}' is a variant of the preferred term '{term.preferred}'",
                    quote=hit, line=doc.line_of(hit), fix=f"Write '{term.preferred}'.", source="glossary",
                ))
        used = (1 if preferred_hits else 0) + len(variant_hits)
        if used >= 2:
            parts = ([f"'{term.preferred}' ({len(preferred_hits)})"] if preferred_hits else [])
            parts += [f"'{v}' ({n})" for v, n in variant_hits.items()]
            first = next(iter(variant_hits))
            findings.append(Finding(
                rule="glossary_inconsistent", severity="error",
                message=f"one concept, several terms: {', '.join(parts)}",
                quote=first, line=doc.line_of(first), fix=f"Use '{term.preferred}' throughout.", source="glossary",
            ))
    for banned in glossary.banned:
        for hit in _occurrences(text, banned.term):
            reason = f": {banned.reason}" if banned.reason else ""
            findings.append(Finding(
                rule="glossary_banned", severity="error", message=f"banned term '{hit}'{reason}",
                quote=hit, line=doc.line_of(hit),
                fix=f"Write '{banned.replacement}'." if banned.replacement else "Remove or rephrase.", source="glossary",
            ))
    known, defined, seen = glossary.known, defined_acronyms(text), set()
    for m in _ACRONYM.finditer(text):
        word = m.group(0)
        base = word[:-1] if word.endswith("s") and word[:-1].isupper() else word
        if base in seen or word in known or base in known or base in defined or base in ("CODE", "URL"):
            continue
        seen.add(base)
        findings.append(Finding(
            rule="glossary_undefined", severity="suggestion",
            message=f"'{base}' is not in the glossary and is not spelled out in this document",
            quote=word, line=doc.line_of(word),
            fix=f"Spell out '{base}' on first use, or add it to the glossary.", source="glossary",
        ))
    return findings


# ------------------------------------------------------------ suggestions

def suggest_glossary(docs: list[Document]) -> str:
    """Draft a glossary from a corpus: variant families in use, and acronyms with their counts."""
    texts = [mask_code(d.body) for d in docs]
    corpus = "\n".join(texts)
    lines = [
        "# Draft glossary from `pakt terms --suggest`. Review every entry before you use it.",
        "# Pick the preferred term for each concept, delete entries you do not need, and add definitions.",
        "",
    ]
    for preferred, variants in VARIANT_FAMILIES:
        counts = {t: len(_occurrences(corpus, t)) for t in [preferred, *variants]}
        used = {t: n for t, n in counts.items() if n}
        if not used:
            continue
        usage = ", ".join(f"{t} ({n})" for t, n in used.items())
        lines += [
            "[[terms]]",
            f'preferred = "{preferred}"',
            "variants = [" + ", ".join(f'"{v}"' for v in variants) + "]",
            'definition = ""',
            f"# seen in the docs: {usage}",
            "",
        ]
    acronyms = Counter(
        m.group(0) for m in _ACRONYM.finditer(corpus) if m.group(0) not in COMMON_ACRONYMS | {"CODE", "URL"}
    )
    defined = defined_acronyms(corpus)
    for word, n in acronyms.most_common(25):
        note = "spelled out somewhere" if word in defined else "never spelled out"
        lines += ["[[terms]]", f'preferred = "{word}"', 'definition = ""', f"# acronym seen {n} time(s), {note}", ""]
    lines += ["[jargon]", "allow = []", ""]
    return "\n".join(lines)
