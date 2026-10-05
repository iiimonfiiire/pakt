import pytest

from pakt_evals import cli
from pakt_evals.config import ConfigError, require_api_key

from .conftest import REPO_ROOT


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt_evals.config._load_dotenv", lambda root: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)


@pytest.mark.parametrize("value", [None, "", "your-api-key-here"])
def test_missing_key_message(monkeypatch, value):
    if value is not None:
        monkeypatch.setenv("ANTHROPIC_API_KEY", value)
    with pytest.raises(ConfigError, match="set ANTHROPIC_API_KEY in .env"):
        require_api_key()


def test_run_without_key_fails_cleanly(capsys):
    assert cli.main(["run", "--limit", "1", "--variants", "v1"]) == 2
    assert "set ANTHROPIC_API_KEY in .env" in capsys.readouterr().err


def test_dry_run_needs_no_key(capsys):
    assert cli.main(["run", "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "Dry run: no API calls made." in out and "est_cost_usd" in out


def test_unknown_variant(capsys):
    assert cli.main(["run", "--dry-run", "--variants", "v99"]) == 2
    assert "unknown variant" in capsys.readouterr().err


def test_offline_score_writes_report(tmp_path, capsys):
    out = tmp_path / "report"
    code = cli.main(["score", "--outputs", str(REPO_ROOT / "evals/data/sample_outputs.jsonl"), "--out", str(out)])
    assert code == 0
    report = (out / "report.md").read_text()
    assert "fixture-good" in report and "fixture-bad" in report


def test_lint_flags_and_passes(tmp_path, capsys):
    bad, good = tmp_path / "bad.md", tmp_path / "good.md"
    bad.write_text("We're excited — really excited — to ship this.\n")
    good.write_text("Click **Save** to keep your changes.\n")
    assert cli.main(["lint", str(bad)]) == 1
    assert cli.main(["lint", str(good)]) == 0


def test_judge_check_dry_run(capsys):
    assert cli.main(["judge-check", "--dry-run"]) == 0
    assert "hand-labeled" in capsys.readouterr().out


def test_cache_only_run_without_key_reports_misses(tmp_path, monkeypatch, capsys):
    real_load = cli.load_config

    def load_with_empty_cache():
        cfg = real_load()
        cfg.cache_dir = tmp_path / "cache"
        return cfg

    monkeypatch.setattr(cli, "load_config", load_with_empty_cache)
    code = cli.main(["run", "--cache-only", "--no-judge", "--variants", "v1", "--ids", "kb-01", "--out", str(tmp_path / "r")])
    assert code == 1
    assert "CacheMiss" in (tmp_path / "r" / "items.jsonl").read_text()
