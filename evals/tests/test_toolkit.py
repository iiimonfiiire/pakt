import json
from datetime import date
from pathlib import Path

import pytest

from pakt import audit as audit_mod
from pakt import gaps as gaps_mod
from pakt import release_notes as rn
from pakt.document import parse_document
from pakt.structure import load_content_types
from pakt.styleguide import get_guide
from pakt.terminology import Banned, Glossary, Term, check_terms, defined_acronyms, load_glossary, suggest_glossary

from .conftest import REPO_ROOT

GUIDE = get_guide("signal", REPO_ROOT)
TYPES = load_content_types(GUIDE, REPO_ROOT)
GLOSSARY = Glossary(
    terms=[Term("sign in", ("log in", "login")), Term("workspace", ("work space",))],
    banned=[Banned("simply", "it implies the task is easy")],
)


def _doc(text, name="page.md"):
    return parse_document(text, Path(name))


# ------------------------------------------------------------ terminology

def test_variant_inconsistency_and_banned_terms():
    doc = _doc("# Access\n\nSign in to your workspace.\nIf the login fails, simply log in again.\n")
    rules = [(f.rule, f.line) for f in check_terms(doc, GLOSSARY)]
    assert ("glossary_variant", 4) in rules
    assert rules.count(("glossary_variant", 4)) == 2
    assert ("glossary_inconsistent", 4) in rules
    assert ("glossary_banned", 4) in rules


def test_consistent_variant_use_is_flagged_once_per_hit_but_not_inconsistent():
    findings = check_terms(_doc("Log in. Then log in again."), GLOSSARY)
    assert {f.rule for f in findings} == {"glossary_variant"}


def test_undefined_jargon():
    doc = _doc("Turn on SCIM for the workspace. Use single sign-on (SSO) and the API. Run `RBAC` checks.")
    rules = {f.quote: f.rule for f in check_terms(doc, GLOSSARY)}
    assert rules == {"SCIM": "glossary_undefined"}
    assert defined_acronyms("Role-based access control (RBAC) and DLP (data loss prevention)") == {"RBAC", "DLP"}


def test_load_glossary(tmp_path):
    path = tmp_path / "g.toml"
    path.write_text('[[terms]]\npreferred = "sign in"\nvariants = ["log in"]\n\n[[banned]]\nterm = "just"\n\n[jargon]\nallow = ["SCIM"]\n')
    g = load_glossary(path)
    assert g.terms[0].variants == ("log in",) and g.banned[0].term == "just" and "SCIM" in g.allow
    path.write_text('[[terms]]\nvariants = ["x"]\n')
    with pytest.raises(Exception, match="preferred"):
        load_glossary(path)


def test_suggest_glossary_lists_families_and_acronyms():
    draft = suggest_glossary([_doc("Log in, then sign in. Configure SCIM. SCIM syncs users.")])
    assert 'preferred = "sign in"' in draft and "log in (1)" in draft
    assert 'preferred = "SCIM"' in draft and "seen 2 time(s)" in draft
    assert "Review every entry" in draft


# ------------------------------------------------------------------- gaps

SOURCES = [
    gaps_mod.SourceItem("SUP-1", "support", "Error E4012 when syncing", "Sync fails with E4012."),
    gaps_mod.SourceItem("SUP-2", "support", "Sync fails with E4012", "Same E4012 on desktop."),
    gaps_mod.SourceItem("SUP-3", "support", "Where is **Export as PDF**?", ""),
    gaps_mod.SourceItem("CHG-1", "changelog", "Cursor pagination", "`GET /v2/notes` takes a `cursor` parameter.", "2026-03-01"),
    gaps_mod.SourceItem("CHG-2", "changelog", "Rate limits changed", "`Retry-After` is now in seconds.", "2026-04-01"),
    gaps_mod.SourceItem("SUP-4", "support", "Archiving a workspace", "Can admins archive it?"),
]
DOCS = {
    "kb/export.md": _doc("# Export\n\nUse **Export as PDF** to share notes.\n"),
    "api/notes.md": _doc("---\nlast_reviewed: 2026-01-10\n---\n# Notes\n\n`GET /v2/notes` lists notes.\n"),
    "api/limits.md": _doc("---\nupdated: 2026-02-01\n---\n# Limits\n\nWait for `Retry-After` milliseconds.\n"),
}


def test_find_gaps_cites_every_source_and_flags_inference():
    found = gaps_mod.find_gaps(SOURCES, DOCS)
    by_status = {(g.status, g.topic): g for g in found}
    e4012 = by_status[("missing", "Error E4012 when syncing")]
    assert [s["id"] for s in e4012.sources] == ["SUP-1", "SUP-2"] and not e4012.inferred
    partial = by_status[("partial", "Cursor pagination")]
    assert partial.missing_terms == ["cursor"] and partial.found_in == ["api/notes.md"]
    stale = by_status[("stale", "Rate limits changed")]
    assert stale.inferred and stale.found_in == ["api/limits.md"]
    archive = by_status[("missing", "Archiving a workspace")]
    assert archive.inferred and "keywords" in archive.basis.lower()
    assert all(g.sources for g in found)
    assert not any(g.topic.startswith("Where is") for g in found)


def test_gap_report_marks_basis():
    md = gaps_mod.render_markdown(gaps_mod.find_gaps(SOURCES, DOCS), len(SOURCES), len(DOCS))
    assert "**Basis** – Inferred." in md and "**Basis** – Matched." in md and "`SUP-1`" in md


def test_load_sources_validates(tmp_path):
    p = tmp_path / "s.jsonl"
    p.write_text(json.dumps({"id": "A", "title": "x"}) + "\n" + json.dumps({"id": "A", "title": "y"}) + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        gaps_mod.load_sources([p])
    c = tmp_path / "s.csv"
    c.write_text("id,kind,title,body\nT-1,ticket,Login loop,Users see E77\n")
    assert gaps_mod.load_sources([c])[0].kind == "ticket"


# ---------------------------------------------------------- release notes

COMMITS = """a1b2c3d feat(export): add Markdown export
b2c3d4e fix(sync): stop duplicate notes
c3d4e5f perf: load large notebooks faster
d4e5f6a feat(api)!: remove the /v1/notes endpoint
e5f6a7b chore(ci): bump runner image
f6a7b8c Update onboarding copy
"""


def test_parse_commits():
    changes = rn.parse_commits(COMMITS)
    assert [c.type for c in changes] == ["feat", "fix", "perf", "feat", "chore", "other"]
    assert changes[3].breaking and changes[4].internal and changes[0].source == "a1b2c3d"


def test_draft_groups_changes_and_keeps_sources():
    text = rn.draft(rn.parse_commits(COMMITS), "Fernbook", "2.5", TYPES["release_note"])
    assert "status: draft" in text and rn.DRAFT_BANNER in text
    headings = [line[3:] for line in text.splitlines() if line.startswith("## ")]
    assert headings == [
        "New features", "Improvements", "Bug fixes", "Security updates", "API and developer changes",
        "Deprecations and removals",
    ]
    assert "> **Warning:** Remove the /v1/notes endpoint. <!-- source: d4e5f6a -->" in text
    assert all(f"> - **{field}** – TODO" in text for field in rn.DEPRECATION_FIELDS)
    assert text.count(rn.NO_CHANGES) == 2
    assert "Left out as internal" in text and "bump runner image" in text
    assert "TODO: Move each of these changes" in text


def test_draft_uses_the_guide_section_names():
    plain = load_content_types(get_guide("plainspoken", REPO_ROOT), REPO_ROOT)["release_note"]
    text = rn.draft(rn.parse_commits("feat: add tags\nfix: stop crash\nfeat(security): rotate keys\n"), "Fernbook", "2.5", plain)
    assert "## Added" in text and "## Fixed" in text and "## New" not in text and "## Changed" not in text
    assert "TODO: Move each of these changes" in text and "Rotate keys." in text


def test_changes_map_to_slots():
    changes = rn.parse_commits("feat(api): add cursors\nfix(sdk): retry\nfeat(security): rotate keys\nperf: faster\n")
    assert [c.slot for c in changes] == ["api", "api", "security", "improved"]


def test_parse_items(tmp_path):
    p = tmp_path / "prs.jsonl"
    p.write_text(
        json.dumps({"id": "PR-12", "title": "Add tags", "labels": ["feature"]}) + "\n"
        + json.dumps({"id": "PR-13", "title": "Drop v1 API", "labels": ["breaking"]}) + "\n"
    )
    changes = rn.parse_items(p)
    assert changes[0].type == "feature" and changes[1].breaking


def test_approval_gate():
    draft = rn.draft(rn.parse_commits("feat: add tags\n"), "Fernbook", "2.5", TYPES["release_note"])
    with pytest.raises(rn.ApprovalError, match="name"):
        rn.approve(draft, " ")
    with pytest.raises(rn.ApprovalError, match="not a PAKT release-notes draft"):
        rn.approve("# Notes\n", "lead")
    with_todo = rn.draft(rn.parse_commits("feat!: drop v1\n"), "Fernbook", "2.5", TYPES["release_note"])
    with pytest.raises(rn.ApprovalError, match="TODO"):
        rn.approve(with_todo, "lead")
    approved = rn.approve(draft, "docs-lead", date(2026, 10, 1))
    assert "status: approved" in approved and "approved_by: docs-lead" in approved
    assert "approved_on: 2026-10-01" in approved
    assert "<!--" not in approved and "Draft for human review" not in approved


# ------------------------------------------------------------------ audit

def test_audit_ranks_worst_first_and_counts_rules(tmp_path):
    (tmp_path / "kb").mkdir()
    (tmp_path / "kb" / "good.md").write_text(
        "# Export notes\n\nExport your notes to share them.\n\n## Before you begin\n\nYou need the Editor role.\n\n"
        "## Steps\n\n1. Open **Settings**.\n2. Click **Export**.\n\n## Verify the export\n\nThe file appears in your downloads.\n"
    )
    (tmp_path / "kb" / "bad.md").write_text("# Export Your Notes Now\n\nIt's simple. You'll love it, and it's fast.\n\n- Open Settings.\n- Click Export.\n")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "x.md").write_text("Don't scan me.\n")
    entries = audit_mod.audit(tmp_path, GUIDE, TYPES, ["**/*.md"], glossary=GLOSSARY)
    assert [e.path for e in entries] == ["kb/bad.md", "kb/good.md"]
    assert entries[0].report.verdict == "fail" and entries[1].report.verdict == "pass"
    counts = {r["rule"]: r for r in audit_mod.rule_counts(entries)}
    assert counts["contractions"]["findings"] == 3 and counts["contractions"]["files"] == 1
    md = audit_mod.render_markdown(entries, GUIDE, "docs")
    assert md.index("kb/bad.md") < md.index("kb/good.md") and "## Findings per rule" in md
    data = audit_mod.to_dict(entries, GUIDE)
    assert data["summary"]["verdicts"] == {"pass": 1, "revise": 0, "fail": 1}
