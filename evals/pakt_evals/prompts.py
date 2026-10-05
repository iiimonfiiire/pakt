"""Versioned prompt files: a small front-matter header plus the system prompt body."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PromptFile:
    id: str
    name: str
    hypothesis: str
    body: str
    path: Path

    @property
    def sha(self) -> str:
        return hashlib.sha256(self.body.encode()).hexdigest()[:12]


_FRONT_MATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)


def load_prompt(path: Path) -> PromptFile:
    text = path.read_text(encoding="utf-8")
    m = _FRONT_MATTER.match(text)
    if not m:
        raise ValueError(f"{path.name}: missing front matter (--- id/name/hypothesis ---)")
    meta: dict[str, str] = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    for required in ("id", "name", "hypothesis"):
        if required not in meta:
            raise ValueError(f"{path.name}: front matter needs '{required}'")
    return PromptFile(meta["id"], meta["name"], meta["hypothesis"], text[m.end():].strip() + "\n", path)


def discover_variants(prompts_dir: Path) -> dict[str, PromptFile]:
    variants = {}
    for path in sorted(prompts_dir.glob("v*.md")):
        prompt = load_prompt(path)
        if prompt.id in variants:
            raise ValueError(f"duplicate prompt id {prompt.id!r} in {path.name}")
        variants[prompt.id] = prompt
    return variants


def build_user_message(category: str, source: str) -> str:
    return f'<snippet type="{category}">\n{source.strip()}\n</snippet>'


_REWRITE = re.compile(r"<rewrite>\s*(.*?)\s*</rewrite>", re.S)


def extract_rewrite(response: str) -> tuple[str, bool]:
    """Return (rewrite, format_ok). Falls back to the whole response when tags are missing."""
    matches = _REWRITE.findall(response)
    if matches:
        return matches[-1].strip(), True
    return response.strip(), False
