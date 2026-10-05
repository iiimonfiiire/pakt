import pytest

from pakt_evals.prompts import build_user_message, discover_variants, extract_rewrite, load_prompt


def test_repo_variants_load_and_ask_for_rewrite_tags(cfg):
    variants = discover_variants(cfg.prompts_dir)
    assert list(variants) == ["v1", "v2", "v3", "v4"]
    for v in variants.values():
        assert v.hypothesis and "<rewrite>" in v.body
        assert not v.body.startswith("---")


def test_judge_prompt_loads(cfg):
    judge = load_prompt(cfg.judge_prompt)
    assert '"meaning"' in judge.body and '"readability"' in judge.body


def test_front_matter_required(tmp_path):
    p = tmp_path / "v9.md"
    p.write_text("no header here\n")
    with pytest.raises(ValueError, match="front matter"):
        load_prompt(p)
    p.write_text("---\nid: v9\nname: x\n---\nbody\n")
    with pytest.raises(ValueError, match="hypothesis"):
        load_prompt(p)


def test_sha_changes_with_body(tmp_path):
    p = tmp_path / "v9.md"
    p.write_text("---\nid: v9\nname: x\nhypothesis: y\n---\nbody one\n")
    first = load_prompt(p).sha
    p.write_text("---\nid: v9\nname: x\nhypothesis: y\n---\nbody two\n")
    assert load_prompt(p).sha != first


def test_extract_rewrite():
    assert extract_rewrite("<facts>a</facts>\n<rewrite>\nClean.\n</rewrite>") == ("Clean.", True)
    assert extract_rewrite("<rewrite>draft</rewrite> <rewrite>final</rewrite>") == ("final", True)
    assert extract_rewrite("  no tags  ") == ("no tags", False)


def test_build_user_message():
    assert build_user_message("api_doc", " text \n") == '<snippet type="api_doc">\ntext\n</snippet>'
