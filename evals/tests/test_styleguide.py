import shutil

import pytest

from pakt.config import ConfigError, resolve_guide
from pakt.rules import run_rules
from pakt.structure import load_content_types
from pakt.styleguide import bundled_guides, get_guide, load_guide

from .conftest import REPO_ROOT


def _failed(text, guide):
    return {r.rule for r in run_rules(text, (), guide) if not r.passed}


def test_only_the_example_guide_is_bundled():
    assert set(bundled_guides(REPO_ROOT)) == {"plainspoken"}
    for name in ("plainspoken", "signal"):
        guide = get_guide(name, REPO_ROOT)
        assert guide.checkable and guide.has_prose


def test_signal_resolves_to_the_pinned_default():
    guide = get_guide("signal", REPO_ROOT)
    assert guide.source.startswith("github:iiimonfiiire/signal-style-guide@") and guide.pinned


def test_signal_guide_shape():
    guide = get_guide("signal", REPO_ROOT)
    assert guide.id == "signal"
    assert guide.rule("sentence_length").params == {"max_words": 20}
    assert guide.rule("one_term_per_concept").kind == "judgment"
    assert {r.severity for r in guide.rules} <= {"error", "warning", "suggestion"}


def test_swapping_the_guide_changes_the_verdict():
    signal, plain = get_guide("signal", REPO_ROOT), get_guide("plainspoken", REPO_ROOT)
    text = "You'll utilize the export tool in order to save your notes."
    assert {"contractions", "filler"} <= _failed(text, signal)
    assert "plain_words" not in _failed(text, signal)
    failed = _failed(text, plain)
    assert "plain_words" in failed and "contractions" not in failed


def test_threshold_comes_from_the_rules_file():
    text = " ".join(["word"] * 23) + "."
    assert "sentence_length" in _failed(text, get_guide("signal", REPO_ROOT))
    assert "sentence_length" not in _failed(text, get_guide("plainspoken", REPO_ROOT))


def test_each_guide_supplies_its_own_content_type_requirements():
    signal = load_content_types(get_guide("signal", REPO_ROOT), REPO_ROOT)
    plain = load_content_types(get_guide("plainspoken", REPO_ROOT), REPO_ROOT)
    allowed = lambda ct: next(r for r in ct.requirements if r.id == "rn_sections").params["allowed"]
    assert allowed(signal["release_note"]) == [
        "New features", "Improvements", "Bug fixes", "Security updates", "API and developer changes",
        "Deprecations and removals",
    ]
    assert allowed(plain["release_note"]) == ["Added", "Changed", "Fixed", "Removed"]
    assert [r.id for r in plain["release_note"].requirements] == ["rn_sections"]
    assert not plain["api_doc"].requirements and signal["api_doc"].requirements


def _write_guide(folder, rules):
    folder.mkdir(parents=True)
    (folder / "guide.md").write_text("# Test guide\n")
    (folder / "rules.toml").write_text('[guide]\nid = "t"\nname = "T"\ndocument = "guide.md"\n\n' + rules)


@pytest.mark.parametrize("rules, message", [
    ('[[rules]]\nid = "a"\nsummary = "x"\ncheck = "nope"\n', "unknown check"),
    ('[[rules]]\nid = "a"\nsummary = "x"\nseverity = "fatal"\n', "unknown severity"),
    ('[[rules]]\nid = "a"\nsummary = "x"\n\n[[rules]]\nid = "a"\nsummary = "y"\n', "duplicate rule id"),
    ('[[rules]]\nid = "a"\n', "needs 'id' and 'summary'"),
    ("", "no rules defined"),
])
def test_invalid_guides_are_rejected(tmp_path, rules, message):
    _write_guide(tmp_path / "g", rules)
    with pytest.raises(ConfigError, match=message):
        load_guide(tmp_path / "g")


def test_resolution_order(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert resolve_guide(REPO_ROOT, tmp_path).id == "signal"

    project = tmp_path / "docs-repo"
    shutil.copytree(REPO_ROOT / "styleguides" / "plainspoken", project / "style" / "house")
    (project / ".pakt.toml").write_text('[styleguide]\npath = "style/house"\n')
    nested = project / "docs" / "kb"
    nested.mkdir(parents=True)
    guide = resolve_guide(REPO_ROOT, nested)
    assert guide.id == "plainspoken" and str(project / ".pakt.toml") in guide.origin

    (project / ".pakt.toml").write_text('[styleguide]\nname = "signal"\n')
    assert resolve_guide(REPO_ROOT, nested).id == "signal"
    assert resolve_guide(REPO_ROOT, nested, override="plainspoken").id == "plainspoken"


def test_unknown_guide_name(tmp_path):
    with pytest.raises(ConfigError, match="unknown style guide"):
        get_guide("no-such-guide", REPO_ROOT, tmp_path)
