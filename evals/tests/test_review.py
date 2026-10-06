import json
from pathlib import Path

import pytest

from pakt.document import locate, parse_document, parse_ui_strings, quote_from_violation, split_front_matter
from pakt.review import (
    CRITERIA,
    Finding,
    load_template,
    parse_model_review,
    review,
    style_score,
    verdict_for,
)
from pakt.structure import detect_type, load_content_types
from pakt.styleguide import get_guide

from .conftest import REPO_ROOT

GUIDE = get_guide("signal", REPO_ROOT)
TYPES = load_content_types(GUIDE, REPO_ROOT)

RELEASE = """# Fernbook 2.4 release notes

## New

- Export notes to PDF, Markdown, and HTML.

## Breaking

- We removed the `/v1/notes` endpoint. To keep working, switch to `/v2/notes`.
"""


def _doc(text, name=None):
    return parse_document(text, Path(name) if name else None)


# ------------------------------------------------------------- documents

def test_front_matter_offsets_line_numbers():
    meta, body, start = split_front_matter("---\ntitle: x\nupdated: 2026-01-01\n---\nBody line.\n")
    assert meta == {"title": "x", "updated": "2026-01-01"} and body == "Body line.\n" and start == 5
    doc = _doc("---\ntitle: x\n---\nFirst.\nDon't do it.\n")
    assert doc.line_of("Don't") == 5


@pytest.mark.parametrize("violation, quote", [
    ("contraction: don't", "don't"),
    ("23 words: A very long sentence that was cl...", "A very long sentence that was"),
    ("banned term: utilize (use 'use')", "utilize"),
    ("no fenced code example", "no fenced code example"),
])
def test_quote_from_violation(violation, quote):
    assert quote_from_violation(violation) == quote


def test_locate_ignores_whitespace_and_code_placeholders():
    text = "Intro.\n\nRun the\ncommand `x --y` and wait it out.\n"
    assert locate(text, "Run the command") == 3
    assert locate(text, "CODE and wait it out") == 4
    assert locate(text, "absent words") is None


def test_ui_strings_from_lines_and_json(tmp_path):
    doc = _doc("# Export dialog\n\nbutton: Export notes\nerror: The export failed. Try again.\nA plain string\n")
    strings = parse_ui_strings(doc)
    assert [(s.kind, s.line) for s in strings] == [("button", 3), ("error", 4), ("body", 5)]
    path = tmp_path / "en.json"
    path.write_text(json.dumps({"export": {"button": "Export", "error_failed": "It failed."}}, indent=2))
    strings = parse_ui_strings(parse_document(path.read_text(), path))
    assert {s.key: s.kind for s in strings} == {"export.button": "button", "export.error_failed": "error"}
    assert all(s.line for s in strings)


# ------------------------------------------------------------- structure

@pytest.mark.parametrize("name, text, expected", [
    ("docs/release-notes/2-4.md", "# Notes", "release_note"),
    ("docs/api/list.md", "# List", "api_doc"),
    ("help/export.md", "# Export", "kb_article"),
    ("src/locales/en.json", "{}", "ui_microcopy"),
    ("notes.md", "---\npakt_type: api_doc\n---\n# x", "api_doc"),
    ("misc/page.md", "Call `GET /v1/items` to list items.", "api_doc"),
    ("misc/page.md", "Some prose.", "general"),
])
def test_detect_type(name, text, expected):
    assert detect_type(_doc(text, name), TYPES, name) == expected


def test_project_type_map_wins_over_path_hints():
    doc = _doc("# Page", "docs/kb/limits.md")
    assert detect_type(doc, TYPES, "docs/kb/limits.md", {"docs/kb/limits.md": "api_doc"}) == "api_doc"


def _structure_failures(text, type_id, name=None):
    report = review(_doc(text, name), GUIDE, TYPES[type_id])
    return {f.rule for f in report.findings if f.source == "structure"}


def test_release_note_structure_passes_when_conventions_are_met():
    assert _structure_failures(RELEASE, "release_note") == set()


def test_release_note_structure_failures():
    text = "# Release notes\n\n## What is new\n\n- feat: add export\n\n## Breaking\n\n- We removed the old endpoint.\n"
    assert _structure_failures(text, "release_note") == {
        "rn_version_title", "rn_sections", "rn_no_commit_prefixes", "rn_breaking_migration",
    }


def test_kb_steps_must_be_numbered():
    bullets = "# Export notes\n\nExport notes to share them.\n\n- Open **Settings**.\n- Click **Export**.\n"
    numbered = "# Export notes\n\nExport notes to share them.\n\n1. Open **Settings**.\n2. Click **Export**.\n"
    assert _structure_failures(bullets, "kb_article") == {"kb_numbered_steps"}
    assert _structure_failures(numbered, "kb_article") == set()


def test_api_doc_structure():
    good = (
        "# List items\n\n`GET /v1/items`\n\n| Name | Type | Required | Description |\n|---|---|---|---|\n"
        "| `limit` | integer | No | Page size. |\n\nA bad token returns `401`.\n\n```bash\ncurl x\n```\n"
    )
    assert _structure_failures(good, "api_doc") == set()
    assert _structure_failures("# List items\n\nLists the items.\n", "api_doc") == {
        "api_endpoint", "api_params_table", "api_error_response", "api_example",
    }


def test_microcopy_checks_each_string_with_its_line():
    text = "button: Save changes.\nerror: Oops! That didn't work!\nbutton: " + "Export every note now please" + "\n"
    report = review(_doc(text, "strings/ui.md"), GUIDE, TYPES["ui_microcopy"])
    by_rule = {(f.rule, f.line) for f in report.findings}
    assert ("ui_button_punctuation", 1) in by_rule
    assert ("ui_error_no_exclamation", 2) in by_rule
    assert ("contractions", 2) in by_rule and ("preamble", 2) in by_rule
    assert ("ui_length", 3) in by_rule


# ---------------------------------------------------------------- scores

def test_style_score_caps_each_rule():
    many = [Finding("contractions", "error", "x", source="check") for _ in range(10)]
    assert style_score(many) == 7
    assert style_score([]) == 10


@pytest.mark.parametrize("scores, severities, verdict", [
    ({"a": 8, "b": 9}, [], "pass"),
    ({"a": 8, "b": None}, ["warning"], "pass"),
    ({"a": 8, "b": 9}, ["error"], "revise"),
    ({"a": 6, "b": 9}, [], "revise"),
    ({"a": 4, "b": 9}, [], "fail"),
])
def test_verdict(scores, severities, verdict):
    findings = [Finding("r", s, "m") for s in severities]
    assert verdict_for(scores, findings) == verdict


def test_offline_review_report_shape():
    report = review(_doc(RELEASE, "rn.md"), GUIDE, TYPES["release_note"])
    data = report.to_dict()
    assert data["mode"] == "checks" and data["verdict"] == "pass"
    assert data["scores"]["technical_clarity"] is None and data["max_total"] == 20
    assert "not scored" in report.to_markdown()


# ----------------------------------------------------------- model layer

def _model_json(**overrides):
    payload = {
        "scores": {"style_compliance": 7, "technical_clarity": 12, "structure": "6", "scannability": 0},
        "summary": "Clear but thin.",
        "findings": [
            {"rule": "rn_user_impact", "quote": "Export notes to PDF", "fix": "Say why it matters."},
            {"rule": "made_up_rule", "quote": "Export", "fix": "x"},
            {"rule": "numerals", "quote": "a quote that is not there", "fix": "x"},
        ],
    }
    payload.update(overrides)
    return "Here you go:\n```json\n" + json.dumps(payload) + "\n```"


def test_parse_model_review_clamps_and_filters():
    rules = {r.id: r for r in [*GUIDE.judgment, *TYPES["release_note"].judgment]}
    parsed = parse_model_review(_model_json(), _doc(RELEASE), rules)
    assert parsed.parse_ok
    assert parsed.scores == {"style_compliance": 7, "technical_clarity": 10, "structure": 6, "scannability": 1}
    assert [f.rule for f in parsed.findings] == ["rn_user_impact"]
    assert parsed.findings[0].line == 5 and parsed.findings[0].severity == "warning"
    assert len(parsed.dropped) == 2


def test_parse_model_review_errors():
    rules = {}
    assert parse_model_review("no json here", _doc("x"), rules).error
    bad = parse_model_review('{"scores": {"style_compliance": "high"}}', _doc("x"), rules)
    assert not bad.parse_ok and "technical_clarity" in bad.error


def test_review_with_fake_model(fake_client_factory):
    client = fake_client_factory(lambda system, user: _model_json())
    template = load_template(REPO_ROOT / "prompts/review/v1.md")
    report = review(_doc(RELEASE, "rn.md"), GUIDE, TYPES["release_note"], client=client, model="m", template=template)
    assert report.mode == "checks+model"
    assert all(report.scores[c] is not None for c in CRITERIA)
    assert report.scores["scannability"] == 1 and report.verdict == "fail"
    system = client.calls[0]["system"]
    assert "Signal Manual of Style" in system and "rn_user_impact" in system and "{{" not in system
    assert "<deterministic_findings>" in client.calls[0]["user"]
