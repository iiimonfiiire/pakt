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

EMPTY = "No changes in this release."
RELEASE = f"""# Fernbook 2.4 release notes

## New features

- You can now export notes to PDF, Markdown, and HTML.

## Improvements

{EMPTY}

## Bug fixes

{EMPTY}

## Security updates

{EMPTY}

## API and developer changes

{EMPTY}

## Deprecations and removals

> **Warning:** The `/v1/notes` endpoint stops working on 2026-12-01. Switch to `/v2/notes` instead.
"""

FENCE = "```"
GOOD_API = f"""# Get a note

`GET /v2/notes/{{id}}`

| Parameter | Type | Required or optional | Description |
|---|---|---|---|
| `id` | string | Required | The note ID. |

{FENCE}bash
curl -H "Authorization: Bearer <TOKEN>" https://api.example.com/v2/notes/n_1
{FENCE}

{FENCE}python
client.notes.get("n_1")
{FENCE}

{FENCE}json
{{"id": "n_1", "title": "Plan"}}
{FENCE}

{FENCE}json
{{"error": {{"code": "not_found", "message": "No note has this ID."}}}}
{FENCE}
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
    ("help/export.md", "# Export", "kb_concept"),
    ("help/export.md", "# Export\n\n1. Open **Settings**.\n", "kb_task"),
    ("help/sync.md", "# Sync stops\n\n## Symptom\n\nx\n\n## Resolution\n\ny\n", "kb_troubleshooting"),
    ("kb/troubleshooting/sync.md", "# Sync", "kb_troubleshooting"),
    ("learn/tutorials/first.md", "# Build a board", "tutorial"),
    ("docs/getting-started.md", "# Start", "quickstart"),
    ("gtm/launch-brief.md", "# Launch", "gtm_brief"),
    ("incidents/2026-05.md", "# Outage", "post_mortem"),
    ("src/locales/en.json", "{}", "ui_microcopy"),
    ("notes.md", "---\npakt_type: api_doc\n---\n# x", "api_doc"),
    ("notes.md", "---\npakt_type: kb_article\n---\n# x\n\nBy the end of this tutorial, you will know.", "tutorial"),
    ("misc/page.md", "Call `GET /v1/items` to list items.", "api_doc"),
    ("misc/page.md", "Some prose.", "general"),
])
def test_detect_type(name, text, expected):
    assert detect_type(_doc(text, name), TYPES, name) == expected


def test_project_type_map_wins_over_path_hints():
    doc = _doc("# Page", "docs/kb/limits.md")
    assert detect_type(doc, TYPES, "docs/kb/limits.md", {"docs/kb/limits.md": "api_doc"}) == "api_doc"


def test_subtypes_inherit_parent_requirements_and_tags():
    task = TYPES["kb_task"]
    assert task.parent == "kb_article" and "procedural" in task.tags
    assert {"kb_numbered_steps", "kb_task_sections"} <= {r.id for r in task.requirements}
    assert not TYPES["post_mortem"].requirements


def _structure_failures(text, type_id, name=None):
    report = review(_doc(text, name), GUIDE, TYPES[type_id])
    return {f.rule for f in report.findings if f.source == "structure"}


def test_release_note_structure_passes_when_conventions_are_met():
    assert _structure_failures(RELEASE, "release_note") == set()


def test_release_note_structure_failures():
    text = "# Release notes\n\n## What is new\n\n- We added export.\n\n## Deprecations and removals\n\n- We removed the old endpoint.\n"
    assert _structure_failures(text, "release_note") == {"rn_sections", "rn_engineering_framing", "rn_deprecation_callout"}


def test_release_note_headings_out_of_order():
    text = RELEASE.replace("## New features", "## Temp").replace("## Bug fixes", "## New features").replace("## Temp", "## Bug fixes")
    report = review(_doc(text), GUIDE, TYPES["release_note"])
    assert any("out of order" in f.message for f in report.findings)


@pytest.mark.parametrize("callout, problem", [
    ("> **Warning:** The `/v1/notes` endpoint goes away. Switch to `/v2/notes`.", "end-of-life date"),
    ("> **Warning:** The `/v1/notes` endpoint stops working on 1 Dec 2026.", "migration path"),
])
def test_deprecation_callout_fields(callout, problem):
    text = RELEASE.replace(RELEASE.splitlines()[-1], callout)
    report = review(_doc(text), GUIDE, TYPES["release_note"])
    assert any(problem in f.message for f in report.findings if f.rule == "rn_deprecation_callout")


def test_kb_steps_must_be_numbered():
    bullets = "# Export notes\n\nExport notes to share them.\n\n- Open **Settings**.\n- Click **Export**.\n"
    assert _structure_failures(bullets, "kb_article") == {"kb_numbered_steps"}


def test_kb_task_sections_in_order():
    good = (
        "# Export notes\n\nExport notes to share them.\n\n## Before you begin\n\nYou need the Editor role.\n\n"
        "## Steps\n\n1. Open **Settings**.\n2. Click **Export**.\n\n## Verify the export\n\nThe file appears in your downloads.\n"
    )
    assert _structure_failures(good, "kb_task") == set()
    swapped = good.replace("## Before you begin\n\nYou need the Editor role.\n\n", "") + "\n## Prerequisites\n\nEditor role.\n"
    report = review(_doc(swapped), GUIDE, TYPES["kb_task"])
    assert any("out of order: Procedure" in f.message for f in report.findings)


def test_troubleshooting_needs_environment_when_versions_matter():
    text = "# Sync stops\n\n## Symptom\n\nSync stops on macOS 15.\n\n## Cause\n\nA proxy.\n\n## Resolution\n\nTurn it off.\n"
    assert _structure_failures(text, "kb_troubleshooting") == {"ts_environment"}
    fixed = text.replace("## Symptom", "## Environment\n\nmacOS 15 and later.\n\n## Symptom")
    assert _structure_failures(fixed, "kb_troubleshooting") == set()


def test_learning_content():
    assert _structure_failures("# Sync models\n\n1. Open the app.\n", "concept_guide") == {"learn_no_procedures"}
    tutorial = (
        "# Build a board\n\nBy the end of this tutorial, you will be able to build a board.\n\n"
        "## Concepts\n\nA board holds cards.\n\n## Steps\n\n1. Click **New board**.\n\n## Check your work\n\nThe board shows.\n"
    )
    assert _structure_failures(tutorial, "tutorial") == set()


def test_walkthrough_verbs():
    text = "# Tour\n\n1. Press **Start**.\n2. Type your name in the **Name** field.\n3. Click **Next**.\n"
    report = review(_doc(text), GUIDE, TYPES["walkthrough"])
    assert sum(f.rule == "walk_ui_verbs" for f in report.findings) == 2


def test_api_doc_structure():
    assert _structure_failures(GOOD_API, "api_doc") == set()
    bad = (
        "# Get a note\n\nCall `get /v2/notes/{id}` with Bearer abc123.\n\n"
        "| Name | Type | Required | Description |\n|---|---|---|---|\n| id | string | Yes | The ID. |\n"
    )
    assert _structure_failures(bad, "api_doc") == {
        "api_endpoint", "api_params_table", "api_required_marker", "api_code_samples", "api_masked_tokens",
        "api_response_schemas",
    }


def test_gtm_brief_structure():
    good = (
        "# Fernbook Boards launch brief\n\nInternal codename: Project Kite\n\n## Target persona and pain point\n\nx\n\n"
        "## Value proposition\n\nx\n\n## Technical capabilities and scope\n\nx\n\n"
        "## Known limitations and edge cases\n\nx\n\n## Competitive differentiators\n\nx\n"
    )
    assert _structure_failures(good, "gtm_brief") == set()
    leaked = good.replace("## Value proposition\n\nx", "## Value proposition\n\nProject Kite saves time.")
    assert _structure_failures(leaked, "gtm_brief") == {"gtm_codename"}
    swapped = good.replace("## Value proposition", "## Temp").replace("## Competitive differentiators", "## Value proposition")
    assert "gtm_sections" in _structure_failures(swapped.replace("## Temp", "## Competitive differentiators"), "gtm_brief")


def test_microcopy_checks_each_string_with_its_line():
    text = (
        "button: Save Changes\nerror: Oops! The upload failed because the file is too big; try again.\n"
        "nav: Account Settings\ntooltip: Choose the folder where every exported note lands after you finish the export\n"
        "toast: You're all set\n"
    )
    report = review(_doc(text, "strings/ui.md"), GUIDE, TYPES["ui_microcopy"])
    by_rule = {(f.rule, f.line) for f in report.findings}
    assert ("ui_case", 1) in by_rule and ("ui_case", 3) not in by_rule
    assert {("semicolons", 2), ("preamble", 2), ("ui_error_no_why", 2)} <= by_rule
    assert ("sentence_length", 4) in by_rule
    assert not any(rule == "contractions" for rule, _ in by_rule)


def test_style_rules_change_by_type():
    first_person = "We built this tool so our team ships faster."
    kb = review(_doc(first_person), GUIDE, TYPES["kb_task"])
    rn = review(_doc(first_person), GUIDE, TYPES["release_note"])
    assert "first_person" in {f.rule for f in kb.findings}
    assert "first_person" not in {f.rule for f in rn.findings}
    long = " ".join(["word"] * 24) + "."
    assert "sentence_length" in {f.rule for f in review(_doc(long), GUIDE, TYPES["kb_task"]).findings}
    assert "sentence_length" not in {f.rule for f in review(_doc(long), GUIDE, TYPES["kb_concept"]).findings}


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
            {"rule": "rn_capability_first", "quote": "export notes to PDF", "fix": "Say why it matters."},
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
    assert [f.rule for f in parsed.findings] == ["rn_capability_first"]
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
    assert "Signal Manual of Style" in system and "rn_capability_first" in system and "{{" not in system
    assert "<deterministic_findings>" in client.calls[0]["user"]
