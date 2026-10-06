"""The bundled Signal guide stays in step with its upstream copy and with rules.toml."""

import importlib.util
import os
import re
import tomllib
from pathlib import Path

import pytest

from .conftest import REPO_ROOT

spec = importlib.util.spec_from_file_location("sync_signal", REPO_ROOT / "tools" / "sync_signal.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)

GUIDE_DIR = REPO_ROOT / "styleguides" / "signal"
UPSTREAM = """<div>
  <img src="./assets/logo.svg" width="150" alt="Logo" />
</div>

# Signal Manual of Style

*For clear, concise, and easy-to-scan writing.*

* **Author:** Jane Example
* **Last revision:** 6 Oct 2026
---

Body text.

## 1. Core identity and register

- **Baseline** – A rule.
"""


def test_transform_strips_logo_and_author():
    out = sync.transform(UPSTREAM)
    assert "<div>" not in out and "Jane Example" not in out and "Author" not in out
    assert out.startswith("# Signal Manual of Style\n")
    assert "- **Last revision** – 6 Oct 2026\n\n---\n" in out
    assert sync.revision_date(out) == "2026-10-06"


def test_transform_refuses_a_surviving_author_line():
    with pytest.raises(sync.SyncError, match="author"):
        sync.transform(UPSTREAM.replace("* **Author:** Jane Example", "Written by the author Jane Example."))


def test_set_version():
    assert sync.set_version('[guide]\nversion = "2026-09-23"\n', "2026-10-06") == '[guide]\nversion = "2026-10-06"\n'


def test_rules_version_matches_guide_revision():
    guide = (GUIDE_DIR / "guide.md").read_text()
    rules = tomllib.loads((GUIDE_DIR / "rules.toml").read_text())
    assert rules["guide"]["version"] == sync.revision_date(guide)


def test_bundled_guide_has_no_author_or_logo():
    guide = (GUIDE_DIR / "guide.md").read_text()
    assert "<img" not in guide and not re.search(r"\*\*Author", guide)


@pytest.mark.skipif(not os.environ.get("SIGNAL_SOURCE"), reason="set SIGNAL_SOURCE to compare with the upstream guide")
def test_bundled_guide_matches_a_fresh_sync():
    upstream = Path(os.environ["SIGNAL_SOURCE"]).expanduser()
    if not upstream.is_file():
        pytest.skip(f"{upstream} not found")
    assert (GUIDE_DIR / "guide.md").read_text() == sync.transform(upstream.read_text())


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
