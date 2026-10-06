import hashlib
import os
import socket
import tomllib
import urllib.error

import pytest

from pakt import cli, sources
from pakt.config import resolve_guide
from pakt.sources import GuideSourceError, parse_spec
from pakt.styleguide import resolve

from .conftest import FIXTURES, REPO_ROOT

SHA = "0123456789abcdef0123456789abcdef01234567"
PACK = (FIXTURES / "signal" / "signal.rules.toml").read_bytes()
PROSE = (FIXTURES / "signal" / "SIGNAL.md").read_bytes()
RAW = "https://raw.githubusercontent.com/acme/house-style/{ref}/{path}"


def _serve(remote, ref=SHA, sub=""):
    prefix = f"{sub}/" if sub else ""
    remote.files[RAW.format(ref=ref, path=prefix + "house.rules.toml")] = PACK
    remote.files[RAW.format(ref=ref, path=prefix + "SIGNAL.md")] = PROSE


@pytest.mark.parametrize("value, kind, target, ref, rules", [
    ("github:acme/house-style@v1.2.0", "github", "acme/house-style", "v1.2.0", ""),
    ("github:acme/house-style@main#pack/rules.toml", "github", "acme/house-style", "main", "pack/rules.toml"),
    (f"https://github.com/acme/house-style/tree/{SHA}", "github", "acme/house-style", SHA, ""),
    ("https://github.com/acme/house-style", "github", "acme/house-style", "main", ""),
    ("vale:Microsoft", "vale", "Microsoft", "", ""),
    ("plainspoken", "bundled", "plainspoken", "", ""),
    ("style/house", "local", "style/house", "", ""),
])
def test_parse_spec(value, kind, target, ref, rules):
    spec = parse_spec(value)
    assert (spec.kind, spec.target, spec.ref, spec.rules) == (kind, target, ref, rules)


def test_pinning():
    assert parse_spec(f"github:acme/x@{SHA}").pinned and parse_spec("github:acme/x@v2.0").pinned
    assert not parse_spec("github:acme/x@main").pinned
    assert not parse_spec({"source": "https://example.com/guide.md", "rules": "r.toml"}).pinned
    assert parse_spec({"source": "https://example.com/guide.md", "rules": "r.toml", "sha256": "ab"}).pinned


def test_url_source_needs_a_rules_pack():
    with pytest.raises(GuideSourceError, match="needs a rules pack"):
        parse_spec("https://example.com/guide.md")


def test_signal_alias_and_config_default_agree():
    config = tomllib.loads((REPO_ROOT / "config.toml").read_text())["styleguide"]
    assert config == sources.DEFAULT_SOURCE
    assert parse_spec("signal") == parse_spec(sources.DEFAULT_SOURCE)
    assert parse_spec("signal").pinned


def test_github_pinned_fetches_once_then_works_offline(fake_remote):
    _serve(fake_remote)
    spec = parse_spec({"source": f"github:acme/house-style@{SHA}", "rules": "house.rules.toml"})
    guide = resolve(spec)
    assert guide.id == "signal" and guide.has_prose and guide.pinned
    assert len(fake_remote.calls) == 2
    resolve(spec)
    assert len(fake_remote.calls) == 2, "a pinned ref never refetches"
    os.environ["PAKT_OFFLINE"] = "1"
    try:
        assert resolve(spec).rules
    finally:
        del os.environ["PAKT_OFFLINE"]


def test_github_subfolder(fake_remote):
    _serve(fake_remote, sub="guides/style")
    guide = resolve(parse_spec({"source": f"https://github.com/acme/house-style/tree/{SHA}/guides/style", "rules": "house.rules.toml"}))
    assert guide.rules and guide.has_prose


def test_unpinned_ref_warns_and_refetches(fake_remote, capsys):
    _serve(fake_remote, ref="main")
    spec = parse_spec({"source": "github:acme/house-style@main", "rules": "house.rules.toml"})
    sources._warned.clear()
    resolve(spec)
    resolve(spec)
    assert len(fake_remote.calls) == 4
    assert "not pinned" in capsys.readouterr().err


def test_missing_file_suggests_a_local_path(fake_remote):
    spec = parse_spec({"source": f"github:acme/private-style@{SHA}", "rules": "rules.toml"})
    with pytest.raises(GuideSourceError, match="private.*local folder"):
        resolve(spec)


def test_network_failure_without_cache(fake_remote, monkeypatch):
    def down(url):
        raise urllib.error.URLError("no route to host")

    monkeypatch.setattr(sources, "_fetch", down)
    with pytest.raises(GuideSourceError, match="no cached copy"):
        resolve(parse_spec({"source": f"github:acme/house-style@{SHA}", "rules": "house.rules.toml"}))


def test_network_failure_falls_back_to_cache_for_unpinned(fake_remote, monkeypatch, capsys):
    _serve(fake_remote, ref="main")
    spec = parse_spec({"source": "github:acme/house-style@main", "rules": "house.rules.toml"})
    resolve(spec)
    monkeypatch.setattr(sources, "_fetch", lambda url: (_ for _ in ()).throw(urllib.error.URLError("offline")))
    sources._warned.clear()
    assert resolve(spec).rules
    assert "Using the cached copy" in capsys.readouterr().err


def test_offline_without_cache(fake_remote, monkeypatch):
    monkeypatch.setenv("PAKT_OFFLINE", "1")
    with pytest.raises(GuideSourceError, match="PAKT_OFFLINE"):
        resolve(parse_spec({"source": f"github:acme/house-style@{SHA}", "rules": "house.rules.toml"}))


def test_url_source_with_sha256_pin(fake_remote, tmp_path):
    fake_remote.files["https://example.com/style/guide.md"] = PROSE
    pack = tmp_path / "house.rules.toml"
    pack.write_bytes(PACK)
    table = {"source": "https://example.com/style/guide.md", "rules": "house.rules.toml",
             "sha256": hashlib.sha256(PROSE).hexdigest()}
    guide = resolve(parse_spec(table, tmp_path))
    assert guide.has_prose and guide.pinned
    fake_remote.files["https://example.com/other.md"] = b"changed"
    bad = parse_spec({**table, "source": "https://example.com/other.md"}, tmp_path)
    with pytest.raises(GuideSourceError, match="sha256"):
        resolve(bad)


def test_local_folder_with_named_pack(tmp_path):
    (tmp_path / "house").mkdir()
    (tmp_path / "house" / "house.rules.toml").write_bytes(PACK)
    (tmp_path / "house" / "SIGNAL.md").write_bytes(PROSE)
    guide = resolve(parse_spec("house", tmp_path))
    assert guide.rules_file.name == "house.rules.toml" and guide.has_prose


def test_project_file_selects_a_remote_source(fake_remote, tmp_path, monkeypatch):
    _serve(fake_remote)
    (tmp_path / ".pakt.toml").write_text(f'[styleguide]\nsource = "github:acme/house-style@{SHA}"\nrules = "house.rules.toml"\n')
    guide = resolve_guide(REPO_ROOT, tmp_path)
    assert guide.source == f"github:acme/house-style@{SHA}"


def test_guide_fetch_and_show(fake_remote, tmp_path, monkeypatch, capsys):
    _serve(fake_remote)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PAKT_ROOT", str(REPO_ROOT))
    monkeypatch.setattr("pakt.config._load_dotenv", lambda root: None)
    (tmp_path / ".pakt.toml").write_text(f'[styleguide]\nsource = "github:acme/house-style@{SHA}"\nrules = "house.rules.toml"\n')
    assert cli.main(["guide", "fetch"]) == 0
    assert "Fetched" in capsys.readouterr().out and len(fake_remote.calls) == 2
    assert cli.main(["guide", "fetch"]) == 0
    assert len(fake_remote.calls) == 4, "fetch refreshes even a pinned source"
    assert cli.main(["guide", "show"]) == 0
    out = capsys.readouterr().out
    assert "pinned" in out and "house.rules.toml" in out


def _online() -> bool:
    try:
        socket.create_connection(("raw.githubusercontent.com", 443), timeout=3).close()
        return True
    except OSError:
        return False


@pytest.mark.skipif(
    os.environ.get("PAKT_NETWORK_TESTS") != "1" or os.environ.get("PAKT_OFFLINE"),
    reason="set PAKT_NETWORK_TESTS=1 to fetch the pinned default guide",
)
def test_pinned_default_is_reachable(tmp_path, monkeypatch):
    if not _online():
        pytest.skip("no network")
    monkeypatch.setenv("PAKT_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(sources, "_fetch", sources.__dict__["_real_fetch"])
    guide = resolve(parse_spec(sources.DEFAULT_SOURCE))
    assert guide.id == "signal" and guide.has_prose
    assert guide.rules_file.read_bytes() == PACK, "the test fixture must match the pinned pack"
