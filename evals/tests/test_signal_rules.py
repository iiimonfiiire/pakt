"""Checks added for the October 2026 Signal revision, plus the heuristic fixes."""

import pytest

from pakt import rules as r
from pakt.structure import load_content_types
from pakt.styleguide import get_guide

from .conftest import REPO_ROOT

GUIDE = get_guide("signal", REPO_ROOT)
TYPES = load_content_types(GUIDE, REPO_ROOT)


@pytest.mark.parametrize("text, ok", [
    ("Click **Save** to keep your changes.", True),
    ("We recommend that you save often.", False),
    ("Our API returns JSON.", False),
    ("I think this works.", False),
    ("Check the I/O settings.", True),
    ("Run `we --help` first.", True),
])
def test_first_person(text, ok):
    assert r.check_first_person(text).passed is ok


def test_semicolons_scope():
    assert not r.check_semicolons("Intro; fine here.\n\n1. Open **Settings**; then click **Save**.\n", "steps").passed
    assert r.check_semicolons("Intro; fine here.\n\n1. Open **Settings**.\n", "steps").passed
    assert not r.check_semicolons("Saved; try again.", "all").passed
    assert not r.check_semicolons("No steps here; none.", "steps").applicable
    assert r.check_semicolons("Use `a; b` and &amp; entities.", "all").passed


@pytest.mark.parametrize("text, ok", [
    ("See [the rate limit guide](https://example.com).", True),
    ("Limits apply.[^1]", False),
    ("Limits apply (Smith, 2024).", False),
    ("Limits apply (Smith et al., 2023).", False),
    ("Write `[^1]` literally.", True),
])
def test_citations(text, ok):
    assert r.check_citations(text).passed is ok


def test_footnotes_allowed_for_print():
    assert r.check_citations("Limits apply.[^1]", footnotes="allowed").passed


@pytest.mark.parametrize("text, ok", [
    ("Send a POST request, or a GET request, to the API.", True),
    ("IMPORTANT: back up first.", False),
    ("Do NOT delete the key.", False),
    ("Use the REST API over HTTPS.", True),
])
def test_all_caps(text, ok):
    assert r.check_all_caps(text).passed is ok


@pytest.mark.parametrize("text, kind, ok, applicable", [
    ("Save changes", "button", True, True),
    ("Save Changes", "button", False, True),
    ("Account Settings", "nav", True, False),
    ("Delete This Notebook?", "title", False, True),
    ("Export", "button", True, True),
    ("Anything Goes Here", None, True, False),
])
def test_ui_case(text, kind, ok, applicable):
    res = r.check_ui_case(text, kind, ["button", "label", "tooltip", "title"])
    assert res.passed is ok and res.applicable is applicable


def test_heading_case_skips_proper_nouns_used_in_prose():
    text = "# Portable Agentic Knowledge Toolkit\n\nThe Portable Agentic Knowledge Toolkit checks docs."
    assert r.check_heading_case(text).passed
    assert not r.check_heading_case("# Export Your Notes Today\n\nExport notes.").passed


@pytest.mark.parametrize("text, ok", [
    ("The key name decides the kind of string.", True),
    ("The sync is kind of slow.", False),
    ("It seems sort of broken.", False),
])
def test_hedging_kind_of(text, ok):
    assert r.check_hedging(text).passed is ok


@pytest.mark.parametrize("text, ok", [
    ("Each one is a fact, with a rule ID and a line number.", True),
    ("Pick the guide, from a file or a link.", True),
    ("Export to CSV, JSON and XML.", False),
])
def test_oxford_comma_prepositional_tails(text, ok):
    assert r.check_oxford_comma(text).passed is ok


# ------------------------------------------------------- per-type resolution

def _rule(type_id, rule_id):
    return next((x for x in GUIDE.rules_for(TYPES[type_id]) if x.id == rule_id), None)


@pytest.mark.parametrize("type_id, words", [
    ("ui_microcopy", 12), ("kb_task", 20), ("api_doc", 20), ("kb_concept", 28), ("concept_guide", 28), ("general", 20),
])
def test_sentence_cap_by_type(type_id, words):
    assert _rule(type_id, "sentence_length").params["max_words"] == words


def test_contractions_only_allowed_in_microcopy():
    assert _rule("ui_microcopy", "contractions") is None
    assert _rule("release_note", "contractions") is not None


@pytest.mark.parametrize("type_id, allowed", [
    ("release_note", True), ("post_mortem", True), ("gtm_brief", True),
    ("kb_task", False), ("api_doc", False), ("kb_concept", False), ("ui_microcopy", False), ("general", False),
])
def test_first_person_by_type(type_id, allowed):
    assert (_rule(type_id, "first_person") is None) is allowed


def test_semicolon_scope_by_type():
    assert _rule("ui_microcopy", "semicolons").params["scope"] == "all"
    assert _rule("kb_task", "semicolons").params["scope"] == "steps"


def test_overrides_cannot_name_unknown_checks(tmp_path):
    from pakt.config import ConfigError
    from pakt.styleguide import load_guide

    (tmp_path / "guide.md").write_text("# G\n")
    (tmp_path / "rules.toml").write_text(
        '[guide]\nid = "g"\nname = "G"\ndocument = "guide.md"\n\n[[rules]]\nid = "a"\nsummary = "x"\n'
        'check = "contractions"\n[rules.by_type.ui_microcopy]\ncheck = "nope"\n'
    )
    with pytest.raises(ConfigError, match="unknown check"):
        load_guide(tmp_path)


def test_by_type_can_turn_a_judgment_rule_into_a_check(tmp_path):
    from pakt.styleguide import load_guide

    (tmp_path / "guide.md").write_text("# G\n")
    (tmp_path / "rules.toml").write_text(
        '[guide]\nid = "g2"\nname = "G"\ndocument = "guide.md"\n\n[[rules]]\nid = "a"\nsummary = "x"\n'
        '[rules.by_type.procedural]\ncheck = "semicolons"\nseverity = "error"\n'
    )
    guide = load_guide(tmp_path)
    assert guide.rules_for(TYPES["kb_task"])[0].kind == "check"
    assert guide.rules_for(TYPES["kb_concept"])[0].kind == "judgment"
