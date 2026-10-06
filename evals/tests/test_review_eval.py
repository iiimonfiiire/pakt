import json

import pytest

from pakt.review import load_template
from pakt.structure import load_content_types
from pakt_evals import cli
from pakt_evals.review_eval import (
    ReviewItem,
    label_space,
    load_predictions,
    load_reviewer_sets,
    predict,
    run_predictions,
    score,
)

from .conftest import REPO_ROOT


@pytest.fixture
def setup(cfg):
    types = load_content_types(cfg.guide, cfg.root)
    return cfg, types, load_reviewer_sets(cfg.reviewer_dir, cfg.guide, types)


def test_reviewer_sets_are_balanced_and_valid(setup):
    _, _, items = setup
    cfg, types, _ = setup
    by_family = {}
    for item in items:
        family = types[item.content_type].parent or item.content_type
        by_family.setdefault(family, []).append(item)
    assert set(by_family) == {"kb_article", "release_note", "ui_microcopy", "api_doc", "gtm_brief"}
    for family_items in by_family.values():
        assert len(family_items) >= 6
        assert sum(1 for i in family_items if not i.violations) >= 2
    kb_types = {i.content_type for i in by_family["kb_article"]}
    assert {"kb_task", "kb_concept", "kb_troubleshooting", "walkthrough", "concept_guide", "tutorial", "quickstart"} <= kb_types


def test_sets_label_both_kinds_of_rule(setup):
    cfg, types, items = setup
    kinds = {label_space(cfg.guide, types[i.content_type])[v] for i in items for v in i.violations}
    assert kinds == {"check", "judgment"}


def test_checks_find_exactly_the_labeled_check_rules(setup):
    """The labels double as a regression test: every check-kind label must fire, and nothing else."""
    cfg, types, items = setup
    for item in items:
        space = label_space(cfg.guide, types[item.content_type])
        expected = {v for v in item.violations if space[v] == "check"}
        assert predict(item, cfg.guide, types) == expected, item.id


@pytest.mark.parametrize("record, message", [
    ({"id": "a", "content_type": "kb_article"}, "missing 'text'"),
    ({"id": "a", "content_type": "poem", "text": "x"}, "unknown content type"),
    ({"id": "a", "content_type": "kb_article", "text": "x", "violations": ["api_endpoint"]}, "not in the signal guide"),
    ({"id": "a", "content_type": "ui_microcopy", "text": "x", "violations": ["contractions"]}, "not in the signal guide"),
])
def test_set_validation(tmp_path, cfg, record, message):
    (tmp_path / "x.jsonl").write_text(json.dumps(record) + "\n")
    with pytest.raises(ValueError, match=message):
        load_reviewer_sets(tmp_path, cfg.guide, load_content_types(cfg.guide, cfg.root))


def test_score_counts_pairs(cfg):
    types = load_content_types(cfg.guide, cfg.root)
    items = [
        ReviewItem("a", "kb_article", "x", ("contractions", "numerals")),
        ReviewItem("b", "kb_article", "x", ()),
        ReviewItem("c", "api_doc", "x", ("api_spec_alignment",)),
    ]
    preds = {"a": {"contractions", "hedging", "not_a_rule"}, "b": {"filler"}}
    m = score(items, preds, cfg.guide, types)
    assert (m["overall"]["tp"], m["overall"]["fp"], m["overall"]["fn"]) == (1, 2, 2)
    assert m["overall"]["precision"] == pytest.approx(1 / 3) and m["overall"]["recall"] == pytest.approx(1 / 3)
    assert m["by_kind"]["judgment"]["fn"] == 2
    assert m["per_rule"]["contractions"]["recall"] == 1.0
    assert m["clean_items_flagged"] == 1 and m["predicted_items"] == 2
    assert {d["id"] for d in m["disagreements"]} == {"a", "b", "c"}


def test_load_predictions_accepts_rules_or_reports(tmp_path):
    p = tmp_path / "p.jsonl"
    p.write_text(
        json.dumps({"id": "a", "rules": ["x"]}) + "\n"
        + json.dumps({"id": "b", "findings": [{"rule": "y"}, {"rule": "z"}]}) + "\n"
    )
    assert load_predictions(p) == {"a": {"x"}, "b": {"y", "z"}}


def test_oracle_model_reaches_full_recall(setup, fake_client_factory):
    """A fake model that reports exactly the judgment labels proves the model path end to end."""
    cfg, types, items = setup
    by_text = {i.text.strip(): i for i in items}

    def respond(system, user):
        body = user.split("<document", 1)[1].split(">", 1)[1].split("</document>", 1)[0].strip()
        item = next(i for t, i in by_text.items() if body in t or t.endswith(body))
        space = label_space(cfg.guide, types[item.content_type])
        findings = [{"rule": v, "quote": "", "fix": "x"} for v in item.violations if space[v] == "judgment"]
        scores = {c: 7 for c in ("style_compliance", "technical_clarity", "structure", "scannability")}
        return json.dumps({"scores": scores, "summary": "ok", "findings": findings})

    client = fake_client_factory(respond)
    preds, errors = run_predictions(
        items, cfg.guide, types, client, model="m", template=load_template(cfg.review_prompt),
    )
    assert not errors and len(client.calls) == len(items)
    m = score(items, preds, cfg.guide, types)
    assert m["overall"]["precision"] == 1.0 and m["overall"]["recall"] == 1.0


# ------------------------------------------------------------------- CLI

@pytest.fixture
def isolated(monkeypatch):
    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt_evals.config._load_dotenv", lambda root: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


def test_cli_checks_mode(isolated, tmp_path, capsys):
    assert cli.main(["review-eval", "--out", str(tmp_path / "r")]) == 0
    summary = json.loads((tmp_path / "r" / "summary.json").read_text())
    assert summary["metrics"]["by_kind"]["check"]["precision"] == 1.0
    assert summary["metrics"]["by_kind"]["judgment"]["recall"] == 0.0
    assert "## By rule kind" in (tmp_path / "r" / "report.md").read_text()


def test_cli_canned_predictions(isolated, tmp_path, capsys):
    path = REPO_ROOT / "evals/data/reviewer/sample_predictions.jsonl"
    assert cli.main(["review-eval", "--predictions", str(path), "--out", str(tmp_path / "r")]) == 0
    assert "canned predictions" in capsys.readouterr().out


def test_cli_model_mode_dry_run_and_missing_key(isolated, capsys):
    assert cli.main(["review-eval", "--mode", "model", "--dry-run", "--types", "api_doc"]) == 0
    assert "Plan: 8 review call(s)" in capsys.readouterr().out
    assert cli.main(["review-eval", "--mode", "model", "--ids", "kb-r01"]) == 2
    assert "ANTHROPIC_API_KEY" in capsys.readouterr().err
