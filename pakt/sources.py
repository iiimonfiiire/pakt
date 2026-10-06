"""Guide sources: where a style guide's prose and rules pack come from, and the local cache.

A guide is a source plus a pin. Supported sources:

- a local folder, or a bundled guide name
- a GitHub repo at a ref, fetched as raw files over HTTPS: github:owner/repo@ref
- a plain URL to the prose, with a separate rules pack path or URL
- a Vale package: vale:Package or vale:Package@<zip URL>
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path

from .config import ConfigError, package_root, read_toml

DEFAULT_SOURCE = {
    "source": "github:iiimonfiiire/signal-style-guide@v2026.10.06",
    "rules": "signal.rules.toml",
}
ALIASES = {"signal": DEFAULT_SOURCE}
RAW_GITHUB = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
TIMEOUT = 20

_GITHUB_SPEC = re.compile(r"^github:(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?P<sub>(?:/[^@#]+)?)(?:@(?P<ref>[^#]+))?(?:#(?P<rules>.+))?$")
_GITHUB_URL = re.compile(
    r"^https://github\.com/(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+?)(?:\.git)?"
    r"(?:(?:/tree|/blob)/(?P<ref>[^/#]+)(?P<sub>(?:/[^#]+)?))?(?:@(?P<ref2>[^#]+))?(?:#(?P<rules>.+))?/?$"
)
_SHA = re.compile(r"^[0-9a-f]{7,40}$")
_TAG = re.compile(r"^v?\d+(?:\.\d+)+(?:[-+.][\w.]+)?$")
_warned: set[str] = set()


class GuideSourceError(ConfigError):
    pass


@dataclass(frozen=True)
class GuideSpec:
    kind: str
    target: str
    ref: str = ""
    rules: str = ""
    prose: str = ""
    requirements: str = ""
    sha256: str = ""
    subdir: str = ""
    base: str = ""

    @property
    def pinned(self) -> bool:
        if self.kind == "github":
            return bool(_SHA.match(self.ref) or _TAG.match(self.ref))
        if self.kind == "url":
            return bool(self.sha256)
        if self.kind == "vale":
            return bool(self.ref)
        return True

    @property
    def label(self) -> str:
        if self.kind == "github":
            return f"github:{self.target}{self.subdir and '/' + self.subdir}@{self.ref}"
        if self.kind == "vale":
            return f"vale:{self.target}" + (f"@{self.ref}" if self.ref else "")
        return self.target


def warn(message: str) -> None:
    if message not in _warned:
        _warned.add(message)
        print(f"warning: {message}", file=sys.stderr)


def cache_root() -> Path:
    if os.environ.get("PAKT_CACHE_DIR"):
        return Path(os.environ["PAKT_CACHE_DIR"]).expanduser()
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base).expanduser() / "pakt"


def offline() -> bool:
    return os.environ.get("PAKT_OFFLINE", "").strip() not in ("", "0", "false")


def bundled_guides(root: Path | None = None) -> dict[str, Path]:
    base = (root or package_root()) / "styleguides"
    return {p.parent.name: p.parent for p in sorted(base.glob("*/rules.toml"))}


# ------------------------------------------------------------------ parsing

def parse_spec(value, base: Path | None = None, root: Path | None = None) -> GuideSpec:
    """Parse a source string, or a [styleguide] table with source, rules, prose, requirements, and sha256."""
    table = dict(value) if isinstance(value, dict) else {"source": value}
    source = str(table.get("source") or table.get("path") or table.get("name") or "").strip()
    if not source:
        raise GuideSourceError("a style guide source is empty")
    if source in ALIASES and source not in bundled_guides(root):
        return parse_spec({**ALIASES[source], **{k: v for k, v in table.items() if k not in ("source", "name", "path")}}, base, root)
    extra = dict(
        rules=str(table.get("rules", "")), prose=str(table.get("prose", "")),
        requirements=str(table.get("requirements", "")), sha256=str(table.get("sha256", "")),
        base=str(base) if base else "",
    )
    if source.startswith("vale:"):
        package, _, ref = source[5:].partition("@")
        if not package:
            raise GuideSourceError(f"{source!r}: name a Vale package, such as vale:Google")
        return GuideSpec("vale", package, ref, **extra)
    m = _GITHUB_SPEC.match(source)
    if m:
        return _github(m["owner"], m["repo"], m["ref"], m["sub"], m["rules"], extra)
    m = _GITHUB_URL.match(source)
    if m:
        return _github(m["owner"], m["repo"], m["ref"] or m["ref2"], m["sub"], m["rules"], extra)
    if source.startswith(("https://", "http://")):
        if not extra["rules"]:
            raise GuideSourceError(f"{source!r}: a URL guide needs a rules pack. Set rules = \"<path or URL>\".")
        return GuideSpec("url", source, **extra)
    if source in bundled_guides(root):
        return GuideSpec("bundled", source, **extra)
    return GuideSpec("local", source, **extra)


def _github(owner, repo, ref, sub, rules, extra) -> GuideSpec:
    if rules and not extra["rules"]:
        extra["rules"] = rules
    if not ref:
        ref = "main"
    return GuideSpec("github", f"{owner}/{repo}", ref, subdir=(sub or "").strip("/"), **extra)


# ---------------------------------------------------------------- fetching

def _fetch(url: str) -> bytes:
    """Download one file over HTTPS. Tests replace this function."""
    request = urllib.request.Request(url, headers={"User-Agent": "pakt"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return response.read()


_real_fetch = _fetch


def _download(url: str, dest: Path, hint: str) -> None:
    try:
        data = _fetch(url)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403, 404):
            raise GuideSourceError(
                f"{url} returned {exc.code}. The file is missing, or the repo is private. {hint}"
            ) from exc
        raise GuideSourceError(f"{url} returned {exc.code}: {exc.reason}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise _NetworkError(str(getattr(exc, "reason", exc))) from exc
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)


class _NetworkError(Exception):
    pass


def _cache_dir(spec: GuideSpec) -> Path:
    if spec.kind == "github":
        owner, repo = spec.target.split("/", 1)
        ref = re.sub(r"[^\w.-]+", "_", spec.ref)
        sub = hashlib.sha256(spec.subdir.encode()).hexdigest()[:8] if spec.subdir else ""
        return cache_root() / "github" / f"{owner}__{repo}" / (ref + (f"__{sub}" if sub else ""))
    key = hashlib.sha256(f"{spec.kind}|{spec.target}|{spec.ref}|{spec.rules}".encode()).hexdigest()[:16]
    return cache_root() / spec.kind / key


def _materialize(files: dict[str, str], dest_dir: Path, spec: GuideSpec, refresh: bool) -> None:
    """Make sure every file is in the cache. files maps a cache-relative path to its URL."""
    missing = {rel: url for rel, url in files.items() if not (dest_dir / rel).is_file()}
    want = files if (refresh or not spec.pinned) else missing
    if not want:
        return
    hint = "Clone or download the guide, then use its local folder as the source."
    if offline():
        if missing:
            raise GuideSourceError(f"{spec.label} is not cached and PAKT_OFFLINE is set. Run `pakt guide fetch` online first.")
        return
    try:
        for rel, url in want.items():
            _download(url, dest_dir / rel, hint)
    except _NetworkError as exc:
        if missing:
            raise GuideSourceError(
                f"cannot reach {spec.label} ({exc}) and no cached copy exists. "
                "Run `pakt guide fetch` when online, or use a local folder as the source."
            ) from exc
        warn(f"cannot reach {spec.label} ({exc}). Using the cached copy.")
    (dest_dir / "source.json").write_text(json.dumps({"source": spec.label, "files": files}, indent=2) + "\n")


def _rules_name(spec: GuideSpec) -> str:
    return spec.rules or "rules.toml"


def _join(*parts: str) -> str:
    return "/".join(p.strip("/") for p in parts if p)


def _prose_from_pack(pack: Path) -> str:
    data = read_toml(pack)
    return str(data.get("guide", {}).get("document", ""))


def fetch_files(spec: GuideSpec, refresh: bool = False) -> tuple[Path, Path | None]:
    """Fetch or locate the rules pack and the prose. Returns (rules pack path, prose path or None)."""
    if spec.kind in ("bundled", "local"):
        return _local_files(spec)
    dest = _cache_dir(spec)
    if spec.kind == "github":
        if not spec.pinned:
            warn(f"{spec.label} is not pinned to a commit or tag. Results are not reproducible.")
        owner, repo = spec.target.split("/", 1)
        url = lambda path: RAW_GITHUB.format(owner=owner, repo=repo, ref=spec.ref, path=_join(spec.subdir, path))
        rules = _rules_name(spec)
        _materialize({"rules/" + rules: url(rules)}, dest, spec, refresh)
        pack = dest / "rules" / rules
        prose = spec.prose or _prose_from_pack(pack)
        prose_path = None
        if prose.startswith(("https://", "http://")):
            prose_path = _fetch_url(prose, spec, refresh)
        elif prose:
            prose_rel = _join(str(Path(rules).parent) if "/" in rules else "", prose)
            _materialize({"rules/" + prose_rel: url(prose_rel)}, dest, spec, refresh)
            prose_path = dest / "rules" / prose_rel
        return pack, prose_path
    if spec.kind == "url":
        if not spec.pinned:
            warn(f"{spec.label} has no sha256 pin. Results are not reproducible.")
        prose_path = _fetch_url(spec.target, spec, refresh)
        if spec.sha256 and hashlib.sha256(prose_path.read_bytes()).hexdigest() != spec.sha256:
            raise GuideSourceError(f"{spec.target} does not match its sha256 pin. The guide changed upstream.")
        return _rules_file(spec, refresh), prose_path
    raise GuideSourceError(f"{spec.label}: a Vale source has no rules pack")


def _fetch_url(url: str, spec: GuideSpec, refresh: bool) -> Path:
    dest = cache_root() / "url" / hashlib.sha256(url.encode()).hexdigest()[:16]
    name = re.sub(r"[^\w.-]+", "_", url.rstrip("/").rsplit("/", 1)[-1]) or "guide"
    _materialize({name: url}, dest, spec, refresh)
    return dest / name


def _rules_file(spec: GuideSpec, refresh: bool) -> Path:
    if spec.rules.startswith(("https://", "http://")):
        return _fetch_url(spec.rules, spec, refresh)
    path = Path(spec.rules).expanduser()
    if not path.is_absolute() and spec.base:
        path = Path(spec.base) / path
    if not path.is_file():
        raise GuideSourceError(f"rules pack {path} not found")
    return path


def find_pack(folder: Path) -> Path | None:
    if (folder / "rules.toml").is_file():
        return folder / "rules.toml"
    packs = sorted(folder.glob("*.rules.toml"))
    return packs[0] if len(packs) == 1 else None


def _local_files(spec: GuideSpec) -> tuple[Path, Path | None]:
    if spec.kind == "bundled":
        folder = bundled_guides()[spec.target] if spec.target in bundled_guides() else None
    else:
        folder = Path(spec.target).expanduser()
        if not folder.is_absolute() and spec.base:
            folder = Path(spec.base) / folder
    if folder is None or not folder.is_dir():
        names = ", ".join(bundled_guides()) or "none"
        raise GuideSourceError(
            f"unknown style guide {spec.target!r}. Use a bundled name ({names}), signal, a folder with a rules pack, "
            "github:owner/repo@ref, a URL, or vale:Package."
        )
    pack = folder / spec.rules if spec.rules else find_pack(folder)
    if pack is None or not pack.is_file():
        raise GuideSourceError(f"{folder} holds no rules pack. Add rules.toml, or one <name>.rules.toml file.")
    prose = spec.prose or _prose_from_pack(pack)
    if prose.startswith(("https://", "http://")):
        return pack, _fetch_url(prose, spec, False)
    return pack, (pack.parent / prose) if prose else None


def describe(spec: GuideSpec) -> dict:
    return {"source": spec.label, "kind": spec.kind, "pinned": spec.pinned,
            "cache": str(_cache_dir(spec)) if spec.kind in ("github", "url", "vale") else ""}


def with_base(spec: GuideSpec, base: Path) -> GuideSpec:
    return replace(spec, base=str(base))
