import json
import shutil

import pytest

from pakt import cli

from .conftest import REPO_ROOT

BAD_KB = "# Export Your Notes\n\nIt's easy.\n\n- Open Settings.\n- Click Export.\n"


@pytest.fixture(autouse=True)
def isolated(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt.config._load_dotenv", lambda root: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_guide_reports_default_and_project_choice(tmp_path, capsys):
    assert cli.main(["guide", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "signal"
    (tmp_path / ".pakt.toml").write_text('[styleguide]\nname = "plainspoken"\n')
    assert cli.main(["guide"]) == 0
    out = capsys.readouterr().out
    assert "Plainspoken" in out and ".pakt.toml" in out
    assert cli.main(["guide", "--guide", "signal", "--rules", "--kind", "judgment"]) == 0
    out = capsys.readouterr().out
    assert "one_term_per_concept" in out and "sentence_length [" not in out


def test_types_lists_requirements(capsys):
    assert cli.main(["types", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert set(data) == {"kb_article", "release_note", "ui_microcopy", "api_doc", "general"}


def test_lint_prints_line_numbers(tmp_path, capsys):
    (tmp_path / "a.md").write_text("Fine line.\n\nDon't do this.\n")
    assert cli.main(["lint", "a.md"]) == 1
    assert "a.md:3: contractions" in capsys.readouterr().out
    (tmp_path / "b.md").write_text("Click **Save** to keep your changes.\n")
    assert cli.main(["lint", "b.md"]) == 0


def test_review_detects_type_and_writes_json(tmp_path, capsys):
    (tmp_path / "kb").mkdir()
    (tmp_path / "kb" / "export.md").write_text(BAD_KB)
    code = cli.main(["review", "kb/export.md", "--json", "--out", "r.json"])
    data = json.loads((tmp_path / "r.json").read_text())
    assert data["content_type"] == "kb_article" and data["verdict"] == "fail" and code == 1
    rules = {f["rule"] for f in data["findings"]}
    assert {"heading_case", "contractions", "kb_numbered_steps"} <= rules


def test_review_with_another_guide_changes_findings(tmp_path, capsys):
    (tmp_path / "page.md").write_text("You'll utilize the tool.\n")
    cli.main(["review", "page.md", "--json"])
    signal = {f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]}
    cli.main(["review", "page.md", "--json", "--guide", "plainspoken"])
    plain = {f["rule"] for f in json.loads(capsys.readouterr().out)["findings"]}
    assert "contractions" in signal and "plain_words" not in signal
    assert "plain_words" in plain and "contractions" not in plain


def test_review_adds_glossary_findings_to_the_verdict(tmp_path, capsys):
    (tmp_path / "page.md").write_text("Sign in, then simply open **Settings**.\n")
    (tmp_path / "g.toml").write_text('[[banned]]\nterm = "simply"\n')
    cli.main(["review", "page.md", "--json"])
    assert json.loads(capsys.readouterr().out)["verdict"] == "pass"
    cli.main(["review", "page.md", "--json", "--glossary", "g.toml"])
    data = json.loads(capsys.readouterr().out)
    assert data["verdict"] == "revise" and data["findings"][0]["rule"] == "glossary_banned"


def test_review_model_needs_a_key(tmp_path, capsys):
    (tmp_path / "page.md").write_text("Fine.\n")
    assert cli.main(["review", "page.md", "--model"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err


def test_review_unknown_type(tmp_path, capsys):
    (tmp_path / "page.md").write_text("Fine.\n")
    assert cli.main(["review", "page.md", "--type", "poem"]) == 2


def test_audit_uses_project_type_map_and_fail_on(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "one.md").write_text(BAD_KB)
    (tmp_path / "docs" / "two.md").write_text("Click **Save** to keep your changes.\n")
    (tmp_path / ".pakt.toml").write_text('[content]\ninclude = ["**/*.md"]\n\n[content.types]\n"docs/one.md" = "kb_article"\n')
    assert cli.main(["audit", "docs", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert [f["path"] for f in data["files"]] == ["docs/one.md", "docs/two.md"]
    assert data["files"][0]["content_type"] == "kb_article"
    assert cli.main(["audit", "docs", "--fail-on", "fail"]) == 1


def test_terms_suggest_and_check(tmp_path, capsys):
    (tmp_path / "a.md").write_text("Log in first. Then sign in again.\n")
    assert cli.main(["terms", "--suggest", ".", "--out", "glossary.toml"]) == 0
    assert 'preferred = "sign in"' in (tmp_path / "glossary.toml").read_text()
    assert cli.main(["terms", "a.md", "--glossary", "glossary.toml"]) == 1
    assert "glossary_inconsistent" in capsys.readouterr().out
    assert cli.main(["terms", "a.md"]) == 2


def test_gaps_command(tmp_path, capsys):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "sync.md").write_text("# Sync\n\nSync runs every minute.\n")
    (tmp_path / "items.jsonl").write_text(json.dumps({"id": "SUP-9", "title": "Error E4012", "body": "E4012 on sync"}) + "\n")
    assert cli.main(["gaps", "--sources", "items.jsonl", "--docs", "docs"]) == 0
    out = capsys.readouterr().out
    assert "`SUP-9`" in out and "E4012" in out


def test_release_notes_draft_then_human_gate(tmp_path, capsys):
    (tmp_path / "commits.txt").write_text("a1b2c3d feat: add tags\nb2c3d4e fix: stop the sync crash\n")
    assert cli.main(["release-notes", "draft", "--commits", "commits.txt", "--product", "Fernbook", "--version", "2.5", "--out", "rn.md"]) == 0
    assert "must review it" in capsys.readouterr().out
    assert cli.main(["release-notes", "approve", "rn.md", "--approved-by", "docs-lead"]) == 0
    text = (tmp_path / "rn.md").read_text()
    assert "status: approved" in text and "approved_by: docs-lead" in text
    assert cli.main(["release-notes", "approve", "rn.md", "--approved-by", "docs-lead"]) == 1


def test_release_notes_approve_blocks_error_findings(tmp_path, capsys):
    (tmp_path / "commits.txt").write_text("feat: add tags\n")
    cli.main(["release-notes", "draft", "--commits", "commits.txt", "--product", "Fernbook", "--version", "2.5", "--out", "rn.md"])
    text = (tmp_path / "rn.md").read_text().replace("Add tags.", "You can't miss the new tags.")
    (tmp_path / "rn.md").write_text(text)
    assert cli.main(["release-notes", "approve", "rn.md", "--approved-by", "lead"]) == 1
    assert "contractions" in capsys.readouterr().err
    assert cli.main(["release-notes", "approve", "rn.md", "--approved-by", "lead", "--force", "--out", "final.md"]) == 0


def test_init_and_new_guide(tmp_path, capsys):
    assert cli.main(["init", "--guide", "style/house", "--glossary", "glossary.toml"]) == 0
    text = (tmp_path / ".pakt.toml").read_text()
    assert 'path = "style/house"' in text and 'path = "glossary.toml"' in text
    assert cli.main(["init"]) == 1
    assert cli.main(["new-guide", "style/house", "--from", "plainspoken"]) == 0
    assert (tmp_path / "style" / "house" / "rules.toml").is_file()
    capsys.readouterr()
    assert cli.main(["guide", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["id"] == "plainspoken"


def test_custom_guide_folder_with_its_own_threshold(tmp_path, capsys):
    shutil.copytree(REPO_ROOT / "styleguides" / "signal", tmp_path / "house")
    rules = (tmp_path / "house" / "rules.toml").read_text().replace("max_words = 22", "max_words = 5")
    (tmp_path / "house" / "rules.toml").write_text(rules)
    (tmp_path / "page.md").write_text("This sentence has exactly seven words.\n")
    assert cli.main(["lint", "page.md"]) == 0
    assert cli.main(["lint", "page.md", "--guide", "house"]) == 1
