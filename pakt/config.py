"""Settings: config.toml in the PAKT root, an optional .pakt.toml per project, and .env for secrets."""

from __future__ import annotations

import os
import stat
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .styleguide import StyleGuide

PLACEHOLDER_KEYS = {"", "your-api-key-here"}
PROJECT_FILE = ".pakt.toml"


class ConfigError(RuntimeError):
    pass


def package_root() -> Path:
    return Path(__file__).resolve().parents[1]


def find_root(start: Path | None = None) -> Path:
    """Locate the PAKT root: PAKT_ROOT, then a parent of `start`, then the installed package."""
    env_root = os.environ.get("PAKT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / "config.toml").is_file() and (candidate / "styleguides").is_dir():
            return candidate
    fallback = package_root()
    if (fallback / "config.toml").is_file() and (fallback / "styleguides").is_dir():
        return fallback
    raise ConfigError("Cannot find the PAKT root (config.toml and styleguides/). Set PAKT_ROOT.")


def _load_dotenv(root: Path) -> None:
    env_path = root / ".env"
    if not env_path.is_file():
        return
    mode = env_path.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        print("warning: .env is readable by other users. Run: chmod 600 .env", file=sys.stderr)
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)


def require_api_key() -> str:
    key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if key in PLACEHOLDER_KEYS:
        raise ConfigError(
            "no API key found: set ANTHROPIC_API_KEY in .env "
            "(copy .env.example to .env, then run chmod 600 .env)."
        )
    return key


def read_toml(path: Path) -> dict:
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def find_project_file(start: Path | None = None) -> Path | None:
    here = (start or Path.cwd()).resolve()
    for candidate in (here, *here.parents):
        if (candidate / PROJECT_FILE).is_file():
            return candidate / PROJECT_FILE
    return None


@dataclass
class Settings:
    root: Path
    guide: "StyleGuide"
    project_file: Path | None = None
    glossary: Path | None = None
    include: list[str] = field(default_factory=lambda: ["**/*.md", "**/*.mdx", "**/*.txt"])
    exclude: list[str] = field(default_factory=list)
    type_map: dict[str, str] = field(default_factory=dict)
    review_model: str = "claude-sonnet-5-5"
    review_max_tokens: int = 2000
    review_temperature: float | None = 0.0
    review_prompt: Path = Path("prompts/review/v1.md")


def resolve_guide(root: Path, start: Path | None = None, override: str | None = None) -> "StyleGuide":
    """Pick the active guide: --guide, then .pakt.toml, then config.toml, then the bundled default."""
    from .styleguide import DEFAULT_GUIDE, get_guide

    if override:
        return get_guide(override, root, Path.cwd(), origin=f"--guide {override}")
    project = find_project_file(start)
    if project:
        table = read_toml(project).get("styleguide", {})
        choice = table.get("path") or table.get("name")
        if choice:
            return get_guide(choice, root, project.parent, origin=f"{project}")
    cfg = root / "config.toml"
    if cfg.is_file():
        active = read_toml(cfg).get("styleguide", {}).get("active")
        if active:
            return get_guide(active, root, root, origin="config.toml")
    return get_guide(DEFAULT_GUIDE, root, origin="default")


def load_settings(start: Path | None = None, guide_override: str | None = None, root: Path | None = None) -> Settings:
    root = root or find_root(start)
    _load_dotenv(root)
    data = read_toml(root / "config.toml") if (root / "config.toml").is_file() else {}
    review = data.get("review", {})
    settings = Settings(
        root=root,
        guide=resolve_guide(root, start, guide_override),
        review_model=os.environ.get("PAKT_REVIEW_MODEL") or review.get("model", "claude-sonnet-5-5"),
        review_max_tokens=int(review.get("max_tokens", 2000)),
        review_temperature=None if review.get("temperature", 0.0) in (None, "") else float(review.get("temperature", 0.0)),
        review_prompt=root / review.get("prompt", "prompts/review/v1.md"),
    )
    project = find_project_file(start)
    if project:
        settings.project_file = project
        pdata = read_toml(project)
        glossary = pdata.get("glossary", {}).get("path")
        if glossary:
            settings.glossary = (project.parent / glossary).resolve()
        content = pdata.get("content", {})
        settings.include = list(content.get("include", settings.include))
        settings.exclude = list(content.get("exclude", settings.exclude))
        settings.type_map = dict(content.get("types", {}))
    return settings
