"""Deterministic style checks derived from the Signal style guide.

Every check takes plain text (usually Markdown) and returns a RuleResult.
Code blocks, inline code, and URLs are masked first, so literal identifiers
never trigger prose rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Iterable


@dataclass(frozen=True)
class RuleResult:
    rule: str
    passed: bool
    applicable: bool = True
    violations: tuple[str, ...] = ()


@dataclass(frozen=True)
class RuleSettings:
    max_sentence_words: int = 22
    max_agentless_passives: int = 1


def _result(rule: str, violations: list[str], applicable: bool = True) -> RuleResult:
    return RuleResult(rule, not violations, applicable, tuple(violations))


def _clip(text: str, width: int = 70) -> str:
    text = " ".join(text.split())
    return text if len(text) <= width else text[: width - 3] + "..."


# ---------------------------------------------------------------- text prep

_FENCE = re.compile(r"```.*?```", re.S)
_INLINE_CODE = re.compile(r"`[^`\n]+`")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)\s]+\)")
_URL = re.compile(r"https?://\S+")
_LIST_MARKER = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING = re.compile(r"^\s*#{1,6}\s+")
_BLOCKQUOTE = re.compile(r"^\s*>\s?")


_YAML_FRONT_MATTER = re.compile(r"\A---\n.*?\n---\n", re.S)


def strip_front_matter(text: str) -> str:
    return _YAML_FRONT_MATTER.sub("", text, count=1)


def mask_code(text: str) -> str:
    """Replace code and URLs with neutral one-word tokens."""
    text = _FENCE.sub("\n", text)
    text = _INLINE_CODE.sub("CODE", text)
    text = _MD_LINK.sub(r"\1", text)
    return _URL.sub("URL", text)


def text_units(text: str) -> list[str]:
    """Group Markdown into prose units: paragraphs, list items, and headings.

    Hard-wrapped paragraph lines are joined, so one sentence that spans two
    lines still counts as one sentence.
    """
    units: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            units.append(" ".join(current))
            current.clear()

    for raw in mask_code(text).splitlines():
        line = raw.rstrip()
        if not line.strip():
            flush()
            continue
        if line.lstrip().startswith("|"):
            flush()
            continue
        starts_unit = bool(
            _HEADING.match(line) or _LIST_MARKER.match(line) or _BLOCKQUOTE.match(line)
        )
        if starts_unit:
            flush()
            line = _HEADING.sub("", line)
            line = _BLOCKQUOTE.sub("", line)
            line = _LIST_MARKER.sub("", line)
        current.append(line.strip())
        if _HEADING.match(raw):
            flush()
    flush()
    return [u for u in units if u]


_PROTECTED = ("e.g.", "i.e.", "vs.", "approx.", "Dr.", "Mr.", "Ms.", "Mrs.", "No.")
_PLACEHOLDER = "․"
_BOUNDARY = re.compile(r"([.!?][\"')\]”’*_]*)\s+(?=[\"'(\[“‘*_]*[A-Z0-9])")
_WORD = re.compile(r"[A-Za-z0-9][\w'’./-]*")


def split_sentences(text: str) -> list[str]:
    sentences: list[str] = []
    for unit in text_units(text):
        protected = unit
        for abbr in _PROTECTED:
            protected = protected.replace(abbr, abbr.replace(".", _PLACEHOLDER))
        parts = _BOUNDARY.split(protected)
        # re.split with one group yields [text, sep, text, sep, ...]; reattach each separator.
        merged = [parts[i] + (parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)]
        for part in merged:
            restored = part.replace(_PLACEHOLDER, ".").strip()
            if count_words(restored):
                sentences.append(restored)
    return sentences


def count_words(sentence: str) -> int:
    return len(_WORD.findall(sentence))


# ------------------------------------------------------------------- checks


def check_sentence_length(text: str, max_words: int = 22) -> RuleResult:
    violations = []
    for sentence in split_sentences(text):
        n = count_words(sentence)
        if n > max_words:
            violations.append(f"{n} words: {_clip(sentence)}")
    return _result("sentence_length", violations)


_BOLD_LEADIN_PREFIX = re.compile(r"^\s*\*\*[^*]+\*\*\s*$")


def check_em_dash(text: str) -> RuleResult:
    """Em dashes take no surrounding spaces, and one per sentence at most.

    Signal reserves the em dash for a mid-sentence tone shift. Whether a dash
    marks a real tone shift needs judgment, so this check covers only the
    mechanical part: spacing, double-hyphen stand-ins, and stacked dashes.
    """
    violations = []
    for unit in text_units(text):
        for m in re.finditer(r"\s—|—\s", unit):
            violations.append(f"spaced em dash: {_clip(unit[max(0, m.start() - 30): m.end() + 30])}")
        for m in re.finditer(r"\s--\s|\w--\w", unit):
            violations.append(f"double hyphen as dash: {_clip(unit[max(0, m.start() - 30): m.end() + 30])}")
        for m in re.finditer(r"\s-\s", unit):
            if _BOLD_LEADIN_PREFIX.match(unit[: m.start()]):
                continue
            violations.append(f"spaced hyphen as dash: {_clip(unit[max(0, m.start() - 30): m.end() + 30])}")
    for sentence in split_sentences(text):
        if sentence.count("—") >= 2:
            violations.append(f"multiple em dashes in one sentence: {_clip(sentence)}")
    return _result("em_dash", violations)


_APOS = "['’]"
_CONTRACTION = re.compile(
    rf"\b(?:\w+n{_APOS}t"
    rf"|(?:i|you|we|they|he|she|it|that|there|here|what|who|where|how|let){_APOS}(?:s|re|ve|ll|d|m)"
    rf"|\w+{_APOS}(?:re|ve|ll))\b",
    re.I,
)


def check_contractions(text: str) -> RuleResult:
    found = [m.group(0) for m in _CONTRACTION.finditer(mask_code(text))]
    return _result("contractions", [f"contraction: {w}" for w in found])


_LIST_TAIL = re.compile(r",\s+((?:[\w./-]+\s+){0,3}?[\w./-]+)\s+(?:and|or|&)\s+[\w./-]+", re.I)
_CLAUSE_OPENERS = {
    "if", "when", "after", "before", "because", "although", "though", "once", "while",
    "since", "unless", "until", "to", "for", "in", "on", "by", "as", "however", "then",
    "also", "first", "next", "finally", "otherwise", "instead", "now", "today", "here",
    "with", "without", "from", "during", "at", "yes", "no", "note", "where", "whether",
}
_TAIL_EXCLUDED = {
    "then", "so", "but", "which", "that", "who", "where", "when", "while", "because",
    "between", "both", "either", "neither", "whether", "if", "and", "or", "such",
}


def check_oxford_comma(text: str) -> RuleResult:
    """Flag 'A, B and C' lists that skip the serial comma.

    Heuristic. A single comma followed by 'X and Y' is ambiguous: it may be a
    list or an introductory clause. The check flags it only when the segment
    before the comma does not open with a clause word such as 'if' or 'when'.
    Two or more commas before the conjunction count as a list outright.
    """
    violations = []
    for sentence in split_sentences(text):
        for m in _LIST_TAIL.finditer(sentence):
            tail_first = m.group(1).split()[0].lower()
            if tail_first in _TAIL_EXCLUDED:
                continue
            segments = sentence[: m.start()].split(",")
            previous = segments[-1].strip()
            if not previous or previous.lower().endswith(("e.g.", "i.e.")):
                continue
            first_word = previous.split()[0].lower().strip("*_\"'(")
            is_long_list = len(segments) >= 2 and len(previous.split()) <= 3
            if is_long_list or first_word not in _CLAUSE_OPENERS:
                violations.append(f"missing serial comma: {_clip(m.group(0), 50)}")
    return _result("oxford_comma", violations)


_BACK_REFERENCE = re.compile(
    r"\bas (?:mentioned|noted|described|stated|discussed|explained|shown|outlined)"
    r"(?: (?:above|earlier|previously|before))?\b"
    r"|\b(?:mentioned|described|noted|discussed|explained|shown) (?:above|earlier|previously)\b"
    r"|\bpreviously (?:mentioned|described|noted|discussed)\b"
    r"|\bsee above\b|\bthe above\b|\babove-mentioned\b|\baforementioned\b"
    r"|\bthe (?:former|latter)\b"
    r"|\bthe (?:first|second|third|other) option\b"
    r"|\bthe previous (?:step|section|option|paragraph|example)\b"
    r"|\bas we (?:saw|discussed|mentioned)\b",
    re.I,
)


def check_back_references(text: str) -> RuleResult:
    found = [m.group(0) for m in _BACK_REFERENCE.finditer(mask_code(text))]
    return _result("back_reference", [f"back-reference: {p}" for p in found])


_OPENING_CHATTER = re.compile(
    r"^\s*(?:"
    r"(?:sure|certainly|of course|absolutely|great question|okay|ok|oops|whoops|uh oh|welcome aboard)\b"
    rf"|here(?:\s+is|\s+are|{_APOS}s)\b"
    r"|below\s+(?:is|are)\b"
    rf"|i(?:\s+have|{_APOS}ve)\s+(?:rewritten|revised|updated|edited|reworked)\b"
    r"|in\s+this\s+(?:article|guide|section|document|post|page)\b"
    r"|this\s+(?:article|guide|document|page|post)\s+(?:will|explains|describes|covers|shows)\b"
    r"|(?:we\s+are|we're|we’re)\s+(?:(?:so|super|very|really|truly)\s+)?(?:excited|thrilled|pleased|happy|delighted)\b"
    r")",
    re.I,
)
_CLOSING_CHATTER = re.compile(
    r"let me know if|hope this helps|feel free to (?:ask|reach out)|happy to help"
    r"|if you have any (?:other )?questions",
    re.I,
)


def check_preamble(text: str) -> RuleResult:
    """Flag assistant chatter and throat-clearing openers or closers."""
    units = text_units(text)
    violations = []
    if units and _OPENING_CHATTER.match(units[0]):
        violations.append(f"preamble: {_clip(units[0], 60)}")
    if units and _CLOSING_CHATTER.search(units[-1]):
        violations.append(f"closing chatter: {_clip(units[-1], 60)}")
    return _result("preamble", violations)


_FILLER = re.compile(
    r"\bplease (?:note|be aware) that\b|\bit (?:is|’s|'s) (?:important|worth) (?:to note|noting)\b"
    r"|\bit should be noted\b|\bneedless to say\b|\bin order to\b"
    r"|\bat this point in time\b|\bbasically\b|\bas a matter of fact\b",
    re.I,
)


def check_filler(text: str) -> RuleResult:
    found = [m.group(0) for m in _FILLER.finditer(mask_code(text))]
    return _result("filler", [f"filler: {p}" for p in found])


_HEDGES = re.compile(
    r"\b(?:perhaps|maybe|probably|possibly|arguably|somewhat|ideally)\b"
    r"|\bit (?:could|can|might) be argued\b|\bit might be a good idea\b"
    r"|\bgenerally considered\b|\byou (?:might|may) want to\b|\bsort of\b|\bkind of\b",
    re.I,
)


def check_hedging(text: str) -> RuleResult:
    """Signal asks for blunt directness: name the conclusion, skip the softeners."""
    found = [m.group(0) for m in _HEDGES.finditer(mask_code(text))]
    return _result("hedging", [f"hedge: {h}" for h in found])


_THIRD_PERSON_READER = re.compile(
    r"\b(?:the|a|each) (?:user|developer|customer|reader|admin|administrator)s? "
    r"(?:should|must|can|needs? to|has to|will need to|clicks?|selects?|enters?|opens?|types?)\b"
    r"|\bby (?:the|a) (?:user|developer|reader)s?\b",
    re.I,
)


def check_second_person(text: str) -> RuleResult:
    """Instructions address the reader as 'you', not 'the user'."""
    found = [m.group(0) for m in _THIRD_PERSON_READER.finditer(mask_code(text))]
    return _result("second_person", [f"third-person reader: {f}" for f in found])


_IRREGULAR_PARTICIPLES = (
    "begun bound broken built chosen done drawn driven forgotten found frozen given held "
    "hidden kept known left lost made meant overwritten paid put read rewritten run seen "
    "sent set shown shut sold spent split stolen taken thrown told undone withdrawn written"
).split()
_ADJECTIVAL = {"based", "located", "interested", "supposed", "tired", "concerned",
               "advanced", "detailed", "experienced", "limited", "related", "red"}
_PASSIVE = re.compile(
    r"\b(?:am|is|are|was|were|be|been|being)\s+(?:not\s+)?(?:\w+ly\s+)?"
    rf"(\w{{2,}}ed|{'|'.join(_IRREGULAR_PARTICIPLES)})\b"
    r"(\s+by\s+(?!default\b|up\b|name\b|date\b|size\b|\w+ing\b)\w+)?",
    re.I,
)


def find_passives(text: str) -> list[tuple[str, bool]]:
    """Return (phrase, has_agent) pairs for likely passive constructions."""
    hits = []
    for m in _PASSIVE.finditer(mask_code(text)):
        if m.group(1).lower() in _ADJECTIVAL:
            continue
        hits.append((m.group(0), m.group(2) is not None))
    return hits


def check_passive_voice(text: str, max_agentless: int = 1) -> RuleResult:
    """Signal allows passive voice only when the actor is unknown or irrelevant.

    A passive with a 'by' phrase names its actor, so active voice was
    possible: always a violation. Agentless passives get a small allowance.
    """
    hits = find_passives(text)
    with_agent = [p for p, agent in hits if agent]
    agentless = [p for p, agent in hits if not agent]
    violations = [f"passive with named actor: {p}" for p in with_agent]
    if len(agentless) > max_agentless:
        violations += [f"agentless passive: {p}" for p in agentless]
    return _result("passive_voice", violations)


def check_ampersand(text: str) -> RuleResult:
    masked = re.sub(r"&[a-z]+;|&#\d+;", "", mask_code(text))
    count = masked.count("&")
    return _result("ampersand", ["ampersand used for 'and'"] * count)


_LEADIN = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\*\*([^*]+)\*\*(.*)$")


def check_bold_leadin(text: str) -> RuleResult:
    """A bolded lead-in term in a bullet takes an en dash, never a colon or period."""
    violations = []
    applicable = False
    for line in mask_code(text).splitlines():
        m = _LEADIN.match(line)
        if not m:
            continue
        term, rest = m.group(1), m.group(2)
        if term.rstrip().endswith((":", ".")):
            applicable = True
            violations.append(f"lead-in punctuated inside bold: **{term}**")
            continue
        if re.match(r"\s*[:.\-—]", rest):
            applicable = True
            violations.append(f"lead-in not followed by en dash: **{term}**{rest[:3]}")
        elif rest.startswith(" – "):
            applicable = True
    return _result("bold_leadin", violations, applicable)


_LATIN = re.compile(r"\b(?:e\.g|i\.e)(?:\.(?!,)|(?![.,]))|\b(?:eg|ie)\b,", re.I)


def check_latin_abbreviations(text: str) -> RuleResult:
    masked = mask_code(text)
    found = [m.group(0) for m in _LATIN.finditer(masked)]
    applicable = bool(re.search(r"\b(?:e\.?g|i\.?e)\b", masked, re.I))
    return _result("latin_abbrev", [f"e.g./i.e. without trailing comma: {w}" for w in found], applicable)


_CLICK_HERE = re.compile(r"\bclick here\b|\[(?:here|this link|link|read more|more)\]\(", re.I)


def check_link_text(text: str) -> RuleResult:
    without_code = _INLINE_CODE.sub("CODE", _FENCE.sub("\n", text))
    found = [m.group(0) for m in _CLICK_HERE.finditer(without_code)]
    return _result("link_text", [f"generic link text: {f}" for f in found])


def check_key_terms(text: str, must_keep: Iterable[str]) -> RuleResult:
    """Meaning proxy: literal identifiers from the source must survive verbatim."""
    terms = list(must_keep)
    lowered = text.lower()
    missing = [t for t in terms if t.lower() not in lowered]
    return _result("key_terms", [f"missing: {t}" for t in missing], applicable=bool(terms))


# ----------------------------------------------------------------- registry

STYLE_RULES: dict[str, Callable[[str, RuleSettings], RuleResult]] = {
    "sentence_length": lambda t, s: check_sentence_length(t, s.max_sentence_words),
    "em_dash": lambda t, s: check_em_dash(t),
    "contractions": lambda t, s: check_contractions(t),
    "oxford_comma": lambda t, s: check_oxford_comma(t),
    "back_reference": lambda t, s: check_back_references(t),
    "preamble": lambda t, s: check_preamble(t),
    "filler": lambda t, s: check_filler(t),
    "passive_voice": lambda t, s: check_passive_voice(t, s.max_agentless_passives),
    "hedging": lambda t, s: check_hedging(t),
    "second_person": lambda t, s: check_second_person(t),
    "ampersand": lambda t, s: check_ampersand(t),
    "bold_leadin": lambda t, s: check_bold_leadin(t),
    "latin_abbrev": lambda t, s: check_latin_abbreviations(t),
    "link_text": lambda t, s: check_link_text(t),
}


def run_rules(
    text: str,
    must_keep: Iterable[str] = (),
    settings: RuleSettings | None = None,
) -> list[RuleResult]:
    settings = settings or RuleSettings()
    results = [fn(text, settings) for fn in STYLE_RULES.values()]
    results.append(check_key_terms(text, must_keep))
    return results


def sentence_stats(text: str) -> dict[str, float]:
    lengths = [count_words(s) for s in split_sentences(text)]
    if not lengths:
        return {"sentences": 0, "mean_words": 0.0, "max_words": 0}
    return {
        "sentences": len(lengths),
        "mean_words": round(sum(lengths) / len(lengths), 2),
        "max_words": max(lengths),
    }


__all__ = [
    "RuleResult", "RuleSettings", "STYLE_RULES", "run_rules", "split_sentences",
    "count_words", "sentence_stats", "strip_front_matter", "find_passives", "mask_code", "text_units",
    "check_sentence_length", "check_em_dash", "check_contractions", "check_oxford_comma",
    "check_back_references", "check_preamble", "check_filler", "check_passive_voice",
    "check_hedging", "check_second_person", "check_ampersand", "check_bold_leadin", "check_latin_abbreviations",
    "check_link_text", "check_key_terms",
]
