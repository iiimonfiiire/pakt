"""Pluggable style guides: a prose guide.md plus a machine-readable rules.toml."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from .config import ConfigError, package_root

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

    @property
    def kind(self) -> str:
        return "check" if self.check else "judgment"

    def to_dict(self) -> dict:
        return {
            "id": self.id, "kind": self.kind, "severity": self.severity, "section": self.section,
            "summary": self.summary, "fix": self.fix, "check": self.check, "params": dict(self.params),
        }


@dataclass(frozen=True)
class StyleGuide:
    id: str
    name: str
    version: str
    directory: Path
    document: Path
    rules: tuple[Rule, ...]
    description: str = ""
    content_types: dict = field(default_factory=dict, hash=False, compare=False)
    origin: str = "default"

    @property
    def checkable(self) -> list[Rule]:
        return [r for r in self.rules if r.check]

    @property
    def judgment(self) -> list[Rule]:
        return [r for r in self.rules if not r.check]

    @property
    def label(self) -> str:
        return f"{self.name} {self.version}"

    def rule(self, rule_id: str) -> Rule | None:
        return next((r for r in self.rules if r.id == rule_id), None)

    def text(self) -> str:
        return self.document.read_text(encoding="utf-8")

    def summary(self) -> dict:
        return {
            "id": self.id, "name": self.name, "version": self.version, "origin": self.origin,
            "directory": str(self.directory), "document": str(self.document),
            "rules_file": str(self.directory / "rules.toml"),
            "rules": {"total": len(self.rules), "check": len(self.checkable), "judgment": len(self.judgment)},
        }


def load_guide(directory: Path, origin: str = "path") -> StyleGuide:
    from .rules import CHECKS
    from .structure import STRUCTURE_CHECKS

    directory = Path(directory).resolve()
    rules_path = directory / "rules.toml"
    if not rules_path.is_file():
        raise ConfigError(f"style guide folder {directory} has no rules.toml")
    with open(rules_path, "rb") as fh:
        data = tomllib.load(fh)
    meta = data.get("guide", {})
    for key in ("id", "name", "document"):
        if not meta.get(key):
            raise ConfigError(f"{rules_path}: [guide] needs '{key}'")
    document = directory / meta["document"]
    if not document.is_file():
        raise ConfigError(f"{rules_path}: guide document {meta['document']!r} not found")

    rules: list[Rule] = []
    for raw in data.get("rules", []):
        rule = _parse_rule(raw, rules_path, CHECKS)
        if any(r.id == rule.id for r in rules):
            raise ConfigError(f"{rules_path}: duplicate rule id {rule.id!r}")
        rules.append(rule)
    if not rules:
        raise ConfigError(f"{rules_path}: no rules defined")

    content_types = {}
    for ctype, table in data.get("content_types", {}).items():
        reqs = [_parse_rule(raw, rules_path, STRUCTURE_CHECKS) for raw in table.get("requirements", [])]
        content_types[ctype] = reqs

    return StyleGuide(
        id=meta["id"], name=meta["name"], version=str(meta.get("version", "")), directory=directory,
        document=document, rules=tuple(rules), description=meta.get("description", ""),
        content_types=content_types, origin=origin,
    )


def _parse_rule(raw: dict, source: Path, registry: dict) -> Rule:
    if not raw.get("id") or not raw.get("summary"):
        raise ConfigError(f"{source}: every rule needs 'id' and 'summary'")
    severity = raw.get("severity", "warning")
    if severity not in SEVERITIES:
        raise ConfigError(f"{source}: rule {raw['id']!r} has unknown severity {severity!r}")
    check = raw.get("check")
    if check and check not in registry:
        raise ConfigError(f"{source}: rule {raw['id']!r} names unknown check {check!r}. Known: {', '.join(registry)}")
    return Rule(
        id=raw["id"], summary=raw["summary"], severity=severity, section=raw.get("section", ""),
        fix=raw.get("fix", ""), check=check, params=dict(raw.get("params", {})),
    )


def bundled_guides(root: Path | None = None) -> dict[str, Path]:
    base = (root or package_root()) / "styleguides"
    return {p.parent.name: p.parent for p in sorted(base.glob("*/rules.toml"))}


def guide_dir(name_or_path: str, root: Path | None = None, relative_to: Path | None = None) -> Path:
    """Resolve a bundled guide name, or a folder path, to a guide directory."""
    bundled = bundled_guides(root)
    if name_or_path in bundled:
        return bundled[name_or_path]
    candidate = Path(name_or_path).expanduser()
    if not candidate.is_absolute() and relative_to is not None:
        candidate = relative_to / candidate
    if (candidate / "rules.toml").is_file():
        return candidate
    raise ConfigError(
        f"unknown style guide {name_or_path!r}. Use a bundled name ({', '.join(bundled) or 'none'}) "
        "or a folder that holds guide.md and rules.toml."
    )


@lru_cache(maxsize=8)
def _load_cached(directory: str, origin: str) -> StyleGuide:
    return load_guide(Path(directory), origin)


def default_guide() -> StyleGuide:
    return _load_cached(str(guide_dir(DEFAULT_GUIDE)), "default")


def get_guide(name_or_path: str, root: Path | None = None, relative_to: Path | None = None, origin: str = "") -> StyleGuide:
    directory = guide_dir(name_or_path, root, relative_to)
    return _load_cached(str(directory.resolve()), origin or name_or_path)
