import json
import shutil
import subprocess
from pathlib import Path

import pytest

from pakt import vale
from pakt.document import parse_document
from pakt.review import NO_PROSE, build_review_prompt, review
from pakt.sources import parse_spec
from pakt.structure import load_content_types
from pakt.styleguide import resolve

from .conftest import FIXTURES, REPO_ROOT

DOC = "# Export\n\nYou cannot export a locked notebook.\n\nWe ship exports every day!\n"
ALERTS = (FIXTURES / "vale" / "google_alerts.json").read_text()


@pytest.fixture
def fake_vale(monkeypatch, tmp_path):
    """Pretend Vale is installed and replay recorded JSON output."""
    calls = []

    def run(args, cwd):
        calls.append(args)
        if args[-1] == "sync":
            (Path(cwd) / "styles" / "Google").mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(args, 0, "", "")
        return subprocess.CompletedProcess(args, 1, ALERTS, "")

    monkeypatch.setenv("PAKT_VALE", "/opt/fake/vale")
    monkeypatch.setenv("PAKT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(vale, "_run", run)
    return calls


def _guide(spec="vale:Google", **extra):
    return resolve(parse_spec({"source": spec, **extra}, REPO_ROOT, REPO_ROOT))


def test_vale_spec_parsing():
    spec = parse_spec("vale:Google@v0.6.1")
    assert (spec.kind, spec.target, spec.ref, spec.pinned) == ("vale", "Google", "v0.6.1", True)
    assert not parse_spec("vale:Microsoft").pinned


def test_missing_vale_gives_an_install_hint(monkeypatch):
    monkeypatch.delenv("PAKT_VALE", raising=False)
    monkeypatch.setattr(shutil, "which", lambda name: None)
    with pytest.raises(vale.ValeError, match="brew install vale"):
        vale.find_vale()


def test_config_pins_a_release_zip(fake_vale):
    pinned = _guide("vale:Google@v0.6.1")
    assert vale.package_ref(pinned) == "https://github.com/errata-ai/Google/releases/download/v0.6.1/Google.zip"
    url = "https://example.com/packages/Google.zip"
    assert vale.package_ref(_guide(f"vale:Google@{url}")) == url
    ini = vale.write_config(_guide()).read_text()
    assert "Packages = Google" in ini and "BasedOnStyles = Vale, Google" in ini


def test_alerts_map_to_findings():
    alerts = json.loads(ALERTS)["input.md"]
    findings = vale.to_findings(alerts, DOC)
    assert [(f.rule, f.severity, f.line) for f in findings] == [
        ("Google.Contractions", "suggestion", 3), ("Google.We", "warning", 5), ("Google.Exclamation", "error", 5),
    ]
    assert findings[0].quote == "cannot" and findings[0].fix == "Write 'can't'."
    assert findings[1].quote == "We", "the quote falls back to the span when Match is empty"
    assert findings[2].fix == "Delete it." and all(f.source == "vale" for f in findings)


def test_review_uses_vale_as_the_deterministic_layer(fake_vale):
    guide = _guide("vale:Google@v0.6.1")
    types = load_content_types(guide, REPO_ROOT)
    assert guide.engine == "vale" and not guide.rules and not types["release_note"].requirements
    report = review(parse_document(DOC, Path("page.md")), guide, types["general"])
    assert {f.rule for f in report.findings} == {"Google.Contractions", "Google.We", "Google.Exclamation"}
    assert report.scores["style_compliance"] < 10 and report.verdict != "pass"
    assert any("No guide prose" in n for n in report.notes)
    assert sum(args[-1] == "sync" for args in fake_vale) == 1
    review(parse_document(DOC, Path("page.md")), guide, types["general"])
    assert sum(args[-1] == "sync" for args in fake_vale) == 1, "a pinned package syncs once"


def test_vale_guide_with_prose_and_local_requirements(fake_vale, tmp_path):
    (tmp_path / "google.md").write_text("# Google developer style guide\n\nUse second person.\n")
    (tmp_path / "reqs.toml").write_text(
        '[[content_types.api_doc.requirements]]\nid = "api_endpoint"\nsummary = "Show the method and path."\n'
        'severity = "error"\ncheck = "endpoint_signature"\n'
    )
    guide = resolve(parse_spec({"source": "vale:Google", "prose": "google.md", "requirements": "reqs.toml"}, tmp_path))
    types = load_content_types(guide, REPO_ROOT)
    assert [r.id for r in types["api_doc"].requirements] == ["api_endpoint"]
    system = build_review_prompt("{{guide_text}}", guide, types["api_doc"])
    assert "Google developer style guide" in system
    assert NO_PROSE in build_review_prompt("{{guide_text}}", _guide(), types["api_doc"])


def test_vale_failure_is_reported(monkeypatch, fake_vale):
    monkeypatch.setattr(vale, "_run", lambda args, cwd: subprocess.CompletedProcess(args, 2, "", "E100 [loadINI] bad"))
    with pytest.raises(vale.ValeError, match="sync failed"):
        vale.sync(_guide("vale:Google"))


@pytest.mark.skipif(not shutil.which("vale"), reason="Vale is not installed")
def test_real_vale_integration(tmp_path, monkeypatch):
    monkeypatch.setenv("PAKT_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("PAKT_VALE", raising=False)
    try:
        alerts = vale.lint(_guide("vale:Google"), DOC)
    except vale.ValeError as exc:
        pytest.skip(f"vale sync needs network: {exc}")
    assert any(a["Check"].startswith("Google.") for a in alerts)
