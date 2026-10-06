"""The Claude Code plugin: manifest, skills, and the rule that docs follow the guide they enforce."""

import json
import re
import tomllib

import pytest

from pakt.document import load_document, split_front_matter
from pakt.review import review
from pakt.structure import load_content_types
from pakt.styleguide import get_guide

from .conftest import REPO_ROOT

SKILLS = sorted(p.parent.name for p in (REPO_ROOT / "skills").glob("*/SKILL.md"))
EXPECTED = {
    "review-kb-article", "review-release-notes", "review-ui-microcopy", "review-api-docs", "review-gtm-brief",
    "content-audit", "release-notes-drafter", "terminology-check", "docs-gap-finder",
    "pakt-setup", "signal-rewrite",
}


def test_plugin_manifests():
    plugin = json.loads((REPO_ROOT / ".claude-plugin/plugin.json").read_text())
    market = json.loads((REPO_ROOT / ".claude-plugin/marketplace.json").read_text())
    assert plugin["name"] == "pakt" and plugin["description"]
    assert market["plugins"][0]["name"] == "pakt" and market["plugins"][0]["source"] == "./"


def test_skill_catalog_is_complete():
    assert set(SKILLS) == EXPECTED


@pytest.mark.parametrize("name", SKILLS)
def test_skill_front_matter(name):
    meta, body, _ = split_front_matter((REPO_ROOT / "skills" / name / "SKILL.md").read_text())
    assert meta.get("name") == name
    description = meta.get("description", "")
    assert 80 <= len(description) <= 1024
    assert ": " not in description and " #" not in description, "keep the description a plain YAML scalar"
    assert body.lstrip().startswith("# ")


@pytest.mark.parametrize("name", SKILLS)
def test_skill_references_exist(name):
    text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text()
    for ref in re.findall(r"`((?:reference|prompts|docs|styleguides)/[\w./-]+\.md)`", text):
        assert (REPO_ROOT / ref).is_file(), ref


@pytest.mark.parametrize("name", SKILLS)
def test_skills_never_copy_guide_rules(name):
    """Skills read the active guide at run time. Copied rules would drift from the guide."""
    text = (REPO_ROOT / "skills" / name / "SKILL.md").read_text().lower()
    packs = [REPO_ROOT / "evals/tests/fixtures/signal/signal.rules.toml", REPO_ROOT / "styleguides/plainspoken/rules.toml"]
    for pack in packs:
        rules = tomllib.loads(pack.read_text())["rules"]
        for rule in rules:
            assert rule["summary"].lower().rstrip(".") not in text, rule["id"]
    assert not re.search(r"\b2[0-5] words\b", text)
    assert "oxford comma" not in text and "em dash" not in text


SHOWCASE = sorted(
    [REPO_ROOT / "README.md", *(REPO_ROOT / "docs").glob("*.md"), *(REPO_ROOT / "reference").glob("*.md"),
     *(REPO_ROOT / "skills").glob("*/SKILL.md")],
)


@pytest.mark.parametrize("path", SHOWCASE, ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_docs_follow_signal(path):
    """The repo is its own showcase: every doc and skill passes the deterministic Signal checks."""
    guide = get_guide("signal", REPO_ROOT)
    general = load_content_types(guide, REPO_ROOT)["general"]
    report = review(load_document(path), guide, general)
    assert not report.findings, [f"{f.line}: {f.rule}: {f.message}" for f in report.findings]
