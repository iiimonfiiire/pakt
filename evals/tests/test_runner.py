import json

import pytest

from pakt_evals.llm import CachedClient, CacheOnlyClient, cache_key
from pakt_evals.prompts import discover_variants
from pakt_evals.runner import TestItem, estimate_cost, load_testset, run_eval, score_canned_outputs

ITEM = TestItem(id="t-1", category="api_doc", source="Requests must be authenticated with a 401 code.", must_keep=("401",))
JUDGE_JSON = '{"missing_facts": [], "added_facts": [], "rationale": "ok", "meaning": 5, "readability": 4}'


def test_repo_testset_is_valid(cfg):
    items = load_testset(cfg.testset)
    assert 20 <= len(items) <= 30
    assert {i.category for i in items} == {"kb_article", "release_note", "ui_microcopy", "api_doc", "error_message"}
    assert all(i.must_keep and i.failure_modes for i in items)


@pytest.mark.parametrize("record, message", [
    ({"id": "a", "category": "api_doc"}, "missing 'source'"),
    ({"id": "a", "category": "poem", "source": "x"}, "unknown category"),
    ({"id": "a", "category": "api_doc", "source": "x", "must_keep": ["zzz"]}, "must_keep terms not in source"),
])
def test_testset_validation(tmp_path, record, message):
    p = tmp_path / "t.jsonl"
    p.write_text(json.dumps(record) + "\n")
    with pytest.raises(ValueError, match=message):
        load_testset(p)


def test_duplicate_ids_rejected(tmp_path):
    p = tmp_path / "t.jsonl"
    rec = json.dumps({"id": "a", "category": "api_doc", "source": "x"})
    p.write_text(rec + "\n" + rec + "\n")
    with pytest.raises(ValueError, match="duplicate"):
        load_testset(p)


def _respond(system, user):
    return JUDGE_JSON if "<candidate>" in user else "<rewrite>Authenticate every request. Invalid tokens get `401`.</rewrite>"


def test_run_eval_end_to_end_with_fake_client(cfg, fake_client_factory):
    variants = list(discover_variants(cfg.prompts_dir).values())[:2]
    client = fake_client_factory(_respond)
    results = run_eval(cfg, variants, [ITEM], client, client, rubric="RUBRIC")
    assert [r.variant for r in results] == ["v1", "v2"]
    r = results[0]
    assert r.format_ok and r.key_terms_ok and not r.error
    assert r.judge["meaning"] == 5
    assert all(c["model"] in (cfg.generator_model, cfg.judge_model) for c in client.calls)
    expected = cfg.price(cfg.generator_model, 100, 50) + cfg.price(cfg.judge_model, 100, 50)
    assert r.cost_usd == pytest.approx(expected)


def test_generation_error_is_captured_not_raised(cfg):
    class Boom:
        def complete(self, **kw):
            raise TimeoutError("slow")

    variant = discover_variants(cfg.prompts_dir)["v1"]
    [r] = run_eval(cfg, [variant], [ITEM], Boom())
    assert "TimeoutError" in r.error


def test_cache_hit_skips_the_inner_client(tmp_path, fake_client_factory):
    inner = fake_client_factory(lambda s, u: "hello")
    cached = CachedClient(inner, tmp_path, "generations")
    kwargs = dict(model="m", system="s", user="u", max_tokens=10, temperature=0.0)
    first = cached.complete(**kwargs)
    second = cached.complete(**kwargs)
    assert len(inner.calls) == 1
    assert not first.cached and second.cached
    assert second.text == "hello" and second.input_tokens == 100
    cached.complete(**{**kwargs, "system": "changed"})
    assert len(inner.calls) == 2


def test_cache_key_is_order_independent():
    assert cache_key(a=1, b=2) == cache_key(b=2, a=1)


def test_cache_only_mode_errors_on_miss(cfg, tmp_path):
    client = CachedClient(CacheOnlyClient(), tmp_path, "generations")
    variant = discover_variants(cfg.prompts_dir)["v1"]
    [r] = run_eval(cfg, [variant], [ITEM], client)
    assert "CacheMiss" in r.error


def test_score_canned_outputs(cfg, tmp_path):
    p = tmp_path / "out.jsonl"
    p.write_text(json.dumps({"item_id": "err-01", "variant": "x", "output": "Oops, it didn't save."}) + "\n")
    [r] = score_canned_outputs(cfg, p, load_testset(cfg.testset))
    assert not r.format_ok
    assert {"contractions", "preamble"} <= set(r.failed_style_rules)
    assert not r.key_terms_ok


def test_estimate_cost_is_positive_and_counts_calls(cfg):
    variants = list(discover_variants(cfg.prompts_dir).values())
    est = estimate_cost(cfg, variants, [ITEM, ITEM], rubric="R" * 400)
    assert est["generation_calls"] == est["judge_calls"] == 8
    assert est["est_cost_usd"] > 0
    assert estimate_cost(cfg, variants, [ITEM], rubric=None)["judge_calls"] == 0
