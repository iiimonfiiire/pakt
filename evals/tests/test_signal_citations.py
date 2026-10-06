"""Every Signal rule and requirement cites a section of the Signal guide."""

import re
import tomllib

import pytest

from .conftest import REPO_ROOT

GUIDE_DIR = REPO_ROOT / "styleguides" / "signal"


def test_bundled_guide_has_no_author_or_logo():
    guide = (GUIDE_DIR / "guide.md").read_text()
    assert "<img" not in guide and not re.search(r"\*\*Author", guide)


def _guide_headings() -> tuple[set[str], set[str]]:
    text = (GUIDE_DIR / "guide.md").read_text()
    h2 = {m.group(1).strip() for m in re.finditer(r"^## (.+)$", text, re.M)}
    sub = {m.group(1).strip() for m in re.finditer(r"^### (.+)$", text, re.M)}
    sub |= {m.group(1).strip() for m in re.finditer(r"^\s*-\s+\*\*([^*]+)\*\*", text, re.M)}
    return h2, sub


def _all_signal_rules():
    data = tomllib.loads((GUIDE_DIR / "rules.toml").read_text())
    rules = list(data["rules"])
    for table in data.get("content_types", {}).values():
        rules += table.get("requirements", [])
    return rules


@pytest.mark.parametrize("rule", _all_signal_rules(), ids=lambda r: r["id"])
def test_every_rule_cites_a_guide_section(rule):
    h2, sub = _guide_headings()
    parts = [p.strip() for p in rule.get("section", "").split(">")]
    assert parts[0] in h2, f"{rule['id']}: section {parts[0]!r} is not a guide heading"
    if len(parts) > 1:
        assert parts[1] in sub, f"{rule['id']}: {parts[1]!r} is not a heading or lead-in under {parts[0]}"


def test_by_type_keys_name_known_types_or_tags():
    types = tomllib.loads((REPO_ROOT / "content-types.toml").read_text())
    keys = set(types) | {tag for t in types.values() for tag in t.get("tags", [])}
    data = tomllib.loads((GUIDE_DIR / "rules.toml").read_text())
    for rule in data["rules"]:
        assert set(rule.get("by_type", {})) <= keys, rule["id"]
    assert set(data["content_types"]) <= set(types)
