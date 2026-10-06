"""Pluggable style guides: guide prose plus a machine-readable rules pack, from any source."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from pathlib import Path

from .config import ConfigError, package_root, read_toml
from .sources import DEFAULT_SOURCE, GuideSpec, bundled_guides, fetch_files, find_pack, parse_spec

SEVERITIES = ("error", "warning", "suggestion")
DEFAULT_GUIDE = "signal"


@dataclass(frozen=True)
class Rule:
    id: str
    summary: str
    severity: str = "warning"
    section: str = ""
    fix: str = ""
    check: str | None = None
    params: dict = field(default_factory=dict, hash=False, compare=False)
    by_type: dict = field(default_factory=dict, hash=False, compare=False)

    @property
    def kind(self) -> str:
        return "check" if self.check else "judgment"

    def for_type(self, keys: list[str]) -> "Rule | None":
        """Apply the first matching by_type override. Returns None when the rule is off for the type."""
        override = next((self.by_type[k] for k in keys if k in self.by_type), None)
        if override is None:
            return self
        if override.get("enabled", True) is False:
            return None
        check = override["check"] if "check" in override else self.check
        return replace(
            self, severity=override.get("severity", self.severity), summary=override.get("summary", self.summary),
            check=check or None, params={**self.params, **override.get("params", {})}, by_type={},
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "severity": self.severity, "section": self.section,
            "summary": self.summary, "fix": self.fix, "check": self.check, "params": dict(self.params),
            "by_type": dict(self.by_type),
        }


@dataclass(frozen=True)
class StyleGuide:
    id: str
    name: str
    version: str
    directory: Path | None
    document: Path | None
    rules: tuple[Rule, ...]
    description: str = ""
    content_types: dict = field(default_factory=dict, hash=False, compare=False)
    origin: str = "default"
    rules_file: Path | None = None
    source: str = ""
    pinned: bool = True
    engine: str = "pakt"
    vale_package: str = ""
    vale_ref: str = ""

    @property
    def checkable(self) -> list[Rule]:
        return [r for r in self.rules if r.check]

    @property
    def judgment(self) -> list[Rule]:
        return [r for r in self.rules if not r.check]

    def rules_for(self, ctype=None) -> list[Rule]:
        """The effective rules for a content type: by_type matches the type ID, then its parent, then its tags."""
        if ctype is None:
            return list(self.rules)
        keys = [ctype.id, *([ctype.parent] if ctype.parent else []), *ctype.tags]
        return [r for rule in self.rules if (r := rule.for_type(keys)) is not None]

    def checkable_for(self, ctype=None) -> list[Rule]:
        return [r for r in self.rules_for(ctype) if r.check]

    def judgment_for(self, ctype=None) -> list[Rule]:
        return [r for r in self.rules_for(ctype) if not r.check]

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}".strip()

    @property
    def has_prose(self) -> bool:
        return self.document is not None and self.document.is_file()

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def text(self) -> str:
        return self.document.read_text(encoding="utf-8") if self.has_prose else ""

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.name, "version": self.version, "origin": self.origin,
            "source": self.source, "pinned": self.pinned, "engine": self.engine,
            "document": str(self.document) if self.document else "",
            "rules_file": str(self.rules_file) if self.rules_file else "",
            "rules": {"total": len(self.rules), "check": len(self.checkable), "judgment": len(self.judgment)},
        }


def load_pack(pack: Path, prose: Path | None = None, origin: str = "path", source: str = "", pinned: bool = True) -> StyleGuide:
    """Load a rules pack. The prose comes from `prose`, or from the pack's [guide] document."""
    from .rules import CHECKS
    from .structure import STRUCTURE_CHECKS

    pack = Path(pack).resolve()
    data = read_toml(pack)
    meta = data.get("guide", {})
    for key in ("id", "name"):
        if not meta.get(key):
            raise ConfigError(f"{pack}: [guide] needs '{key}'")
    if prose is None and meta.get("document"):
        prose = pack.parent / meta["document"]
    if prose is not None and not Path(prose).is_file():
        raise ConfigError(f"{pack}: guide document {str(prose)!r} not found")

    rules: list[Rule] = []
    for raw in data.get("rules", []):
        rule = _parse_rule(raw, pack, CHECKS)
        if any(r.id == rule.id for r in rules):
            raise ConfigError(f"{pack}: duplicate rule id {rule.id!r}")
        rules.append(rule)
    if not rules:
        raise ConfigError(f"{pack}: no rules defined")

    return StyleGuide(
        id=meta["id"], name=meta["name"], version=str(meta.get("version", "")), directory=pack.parent,
        document=Path(prose) if prose else None, rules=tuple(rules), description=meta.get("description", ""),
        content_types=_content_types(data, pack, STRUCTURE_CHECKS), origin=origin, rules_file=pack,
        source=source or str(pack.parent), pinned=pinned,
    )


def _content_types(data: dict, source: Path, registry: dict) -> dict:
    return {
        ctype: [_parse_rule(raw, source, registry) for raw in table.get("requirements", [])]
        for ctype, table in data.get("content_types", {}).items()
    }


def load_requirements(path: Path) -> dict:
    """Read a requirements-only file: [content_types.<type>] tables, as in a rules pack."""
    from .structure import STRUCTURE_CHECKS

    if not path.is_file():
        raise ConfigError(f"requirements file {path} not found")
    return _content_types(read_toml(path), path, STRUCTURE_CHECKS)


def load_guide(directory: Path, origin: str = "path") -> StyleGuide:
    directory = Path(directory)
    pack = find_pack(directory)
    if pack is None:
        raise ConfigError(f"style guide folder {directory} has no rules pack (rules.toml or <name>.rules.toml)")
    return load_pack(pack, origin=origin)


def _parse_rule(raw: dict, source: Path, registry: dict) -> Rule:
    if not raw.get("id") or not raw.get("summary"):
        raise ConfigError(f"{source}: every rule needs 'id' and 'summary'")
    severity = raw.get("severity", "warning")
    if severity not in SEVERITIES:
        raise ConfigError(f"{source}: rule {raw['id']!r} has unknown severity {severity!r}")
    check = raw.get("check")
    if check and check not in registry:
        raise ConfigError(f"{source}: rule {raw['id']!r} names unknown check {check!r}. Known: {', '.join(registry)}")
    by_type = dict(raw.get("by_type", {}))
    for key, override in by_type.items():
        if override.get("severity", severity) not in SEVERITIES:
            raise ConfigError(f"{source}: rule {raw['id']!r} has unknown severity for {key!r}")
        if override.get("check") and override["check"] not in registry:
            raise ConfigError(f"{source}: rule {raw['id']!r} names unknown check {override['check']!r} for {key!r}")
    return Rule(
        id=raw["id"], summary=raw["summary"], severity=severity, section=raw.get("section", ""),
        fix=raw.get("fix", ""), check=check, params=dict(raw.get("params", {})), by_type=by_type,
    )


def resolve(spec: GuideSpec, origin: str = "", refresh: bool = False) -> StyleGuide:
    """Turn a guide source into a loaded guide, fetching and caching remote files as needed."""
    origin = origin or spec.label
    if spec.kind == "vale":
        guide = _vale_guide(spec, origin, refresh)
    else:
        pack, prose = fetch_files(spec, refresh)
        guide = load_pack(pack, prose, origin, spec.label, spec.pinned)
    if spec.requirements:
        path = Path(spec.requirements).expanduser()
        if not path.is_absolute() and spec.base:
            path = Path(spec.base) / path
        guide = replace(guide, content_types={**guide.content_types, **load_requirements(path)})
    return guide


def _vale_guide(spec: GuideSpec, origin: str, refresh: bool) -> StyleGuide:
    from .sources import _fetch_url

    prose = None
    if spec.prose.startswith(("https://", "http://")):
        prose = _fetch_url(spec.prose, spec, refresh)
    elif spec.prose:
        prose = Path(spec.prose).expanduser()
        if not prose.is_absolute() and spec.base:
            prose = Path(spec.base) / prose
        if not prose.is_file():
            raise ConfigError(f"guide prose {prose} not found")
    return StyleGuide(
        id=f"vale-{spec.target.lower()}", name=f"{spec.target} (Vale)", version=spec.ref or "latest",
        directory=None, document=prose, rules=(), description=f"Vale package {spec.target}", origin=origin,
        source=spec.label, pinned=spec.pinned, engine="vale", vale_package=spec.target, vale_ref=spec.ref,
    )


_CACHE: dict[str, StyleGuide] = {}


def get_guide(value, root: Path | None = None, relative_to: Path | None = None, origin: str = "") -> StyleGuide:
    """Load a guide from a source string or a [styleguide] table, once per process."""
    spec = parse_spec(value, relative_to, root)
    key = json.dumps([spec.__dict__, origin], sort_keys=True, default=str)
    if key not in _CACHE:
        _CACHE[key] = resolve(spec, origin)
    return _CACHE[key]


def default_source(root: Path | None = None) -> dict:
    """The [styleguide] table in config.toml, or Signal from its public repo when none is set."""
    cfg = (root or package_root()) / "config.toml"
    table = read_toml(cfg).get("styleguide", {}) if cfg.is_file() else {}
    return table if (table.get("source") or table.get("name") or table.get("path")) else dict(DEFAULT_SOURCE)


def default_guide() -> StyleGuide:
    return get_guide(default_source(), package_root(), package_root(), origin="default")


__all__ = ["Rule", "StyleGuide", "bundled_guides", "default_guide", "get_guide", "load_guide", "load_pack", "resolve"]
