from pakt_evals.report import badness, baseline, percentile, render_markdown, summarize, worst_failures, write_run
from pakt_evals.rules import RuleSettings
from pakt_evals.runner import ItemResult, TestItem


def _rules(failed=(), key_ok=True):
    names = ["sentence_length", "contractions", "key_terms"]
    out = []
    for n in names:
        passed = key_ok if n == "key_terms" else n not in failed
        out.append({"rule": n, "passed": passed, "applicable": True, "violations": [] if passed else [f"{n} issue"]})
    return out


def _result(variant, item, failed=(), meaning=5, readability=5, key_ok=True, cost=0.01, latency=100.0):
    return ItemResult(
        item_id=item, category="api_doc", variant=variant, output="text", format_ok=True,
        rules=_rules(failed, key_ok), stats={"mean_words": 10},
        judge={"meaning": meaning, "readability": readability, "parse_ok": True, "missing_facts": [], "added_facts": []},
        cost_usd=cost, gen_latency_ms=latency,
    )


def test_percentile_nearest_rank():
    assert percentile([], 95) is None
    assert percentile([5.0], 95) == 5.0
    assert percentile(list(map(float, range(1, 21))), 95) == 19.0
    assert percentile([1.0, 2.0, 3.0, 4.0], 50) == 2.0


def test_summarize_rates_and_means():
    results = [
        _result("v1", "a"),
        _result("v1", "b", failed=("contractions",), meaning=3, readability=4, key_ok=False),
        _result("v2", "a", latency=300.0),
    ]
    s = summarize(results, pass_threshold=4)
    v1 = s["v1"]
    assert v1["all_style_rules_pass_rate"] == 0.5
    assert v1["rules"]["contractions"] == {"passed": 1, "applicable": 2, "rate": 0.5}
    assert v1["rules"]["key_terms"]["rate"] == 0.5
    assert v1["meaning_mean"] == 4.0 and v1["meaning_pass_rate"] == 0.5
    assert v1["cost_usd"] == 0.02
    assert s["v2"]["gen_latency_mean_ms"] == 300.0


def test_errors_excluded_from_rates_but_counted():
    bad = ItemResult(item_id="c", category="api_doc", variant="v1", error="generation failed")
    s = summarize([_result("v1", "a"), bad])["v1"]
    assert s["errors"] == 1 and s["all_style_rules_pass_rate"] == 1.0


def test_unknown_cost_propagates_as_none():
    assert summarize([_result("v1", "a", cost=None)])["v1"]["cost_usd"] is None


def test_worst_failures_ranks_meaning_loss_above_style():
    style_only = _result("v1", "style", failed=("contractions", "sentence_length"))
    meaning_loss = _result("v1", "meaning", meaning=2)
    clean = _result("v1", "clean")
    assert badness(meaning_loss) > badness(style_only) > badness(clean) == 0
    assert [r.item_id for r in worst_failures([clean, style_only, meaning_loss])] == ["meaning", "style"]


def test_baseline_on_sources():
    items = [TestItem("a", "api_doc", "Don't do it."), TestItem("b", "api_doc", "Do it.")]
    base = baseline(items, RuleSettings())
    assert base["contractions"]["rate"] == 0.5
    assert base["_all_style_rules"]["passed"] == 1


def test_render_and_write(tmp_path):
    results = [_result("v1", "a"), _result("v2", "a", failed=("contractions",))]
    md = render_markdown(summarize(results), None, worst_failures(results), {"run_id": "r1", "generator": "g"})
    assert md.startswith("# Eval report: r1")
    assert "| Metric | v1 | v2 |" in md and "## Worst failures" in md
    assert "`v2` on `a`" in md
    write_run(tmp_path / "out", results, summarize(results), md, {"run_id": "r1"})
    assert (tmp_path / "out" / "items.jsonl").read_text().count("\n") == 2
    assert (tmp_path / "out" / "summary.json").is_file()
