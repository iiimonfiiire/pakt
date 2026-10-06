"""Copy the upstream Signal guide into styleguides/signal/guide.md.

The upstream file carries a logo block and an author line. Both are stripped, so
nothing identifying lands in PAKT. Pass the upstream path with --source, or set
SIGNAL_SOURCE. Use --check to fail when the bundled copy has drifted.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "styleguides" / "signal" / "guide.md"
RULES = ROOT / "styleguides" / "signal" / "rules.toml"

_LOGO = re.compile(r"\A\s*<div>.*?</div>\s*", re.S)
_AUTHOR = re.compile(r"^[ \t]*[-*]\s+\*\*Author:?\*\*.*\n", re.M)
_REVISION_UPSTREAM = re.compile(r"^[ \t]*[-*]\s+\*\*Last revision:?\*\*:?\s*(.+?)\s*$", re.M)
_REVISION_BUNDLED = re.compile(r"^- \*\*Last revision\*\* – (.+?)\s*$", re.M)


class SyncError(RuntimeError):
    pass


def transform(upstream: str) -> str:
    """Strip the logo and the author line, and normalize the revision line to a Signal bullet."""
    text = upstream.replace("\r\n", "\n")
    text = _LOGO.sub("", text, count=1)
    text = _AUTHOR.sub("", text)
    text = _REVISION_UPSTREAM.sub(lambda m: f"- **Last revision** – {m.group(1)}\n", text, count=1)
    text = re.sub(r"(- \*\*Last revision\*\* – .+\n)\n*---", r"\1\n---", text, count=1)
    if re.search(r"\bauthor\b", text.split("## ", 1)[0], re.I):
        raise SyncError("an author line survived the sync. Refusing to write it.")
    return text.rstrip() + "\n"


def revision_date(guide_text: str) -> str:
    """Return the guide's revision date as YYYY-MM-DD."""
    m = _REVISION_BUNDLED.search(guide_text) or _REVISION_UPSTREAM.search(guide_text)
    if not m:
        raise SyncError("no 'Last revision' line in the guide")
    raw = m.group(1).strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            continue
    raise SyncError(f"cannot parse the revision date {raw!r}")


def set_version(rules_text: str, version: str) -> str:
    return re.sub(r'(?m)^version = "[^"]*"', f'version = "{version}"', rules_text, count=1)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--source", default=os.environ.get("SIGNAL_SOURCE"), help="upstream SIGNAL.md (or set SIGNAL_SOURCE)")
    p.add_argument("--check", action="store_true", help="report drift and exit 1 instead of writing")
    args = p.parse_args(argv)
    if not args.source:
        print("error: pass --source or set SIGNAL_SOURCE", file=sys.stderr)
        return 2
    source = Path(args.source).expanduser()
    if not source.is_file():
        print(f"error: {source} not found", file=sys.stderr)
        return 2
    synced = transform(source.read_text(encoding="utf-8"))
    version = revision_date(synced)
    rules = RULES.read_text(encoding="utf-8")
    if args.check:
        drift = []
        if DEST.read_text(encoding="utf-8") != synced:
            drift.append("guide.md differs from the upstream guide")
        if set_version(rules, version) != rules:
            drift.append(f"rules.toml version is not {version}")
        for d in drift:
            print(f"drift: {d}")
        return 1 if drift else 0
    DEST.write_text(synced, encoding="utf-8")
    RULES.write_text(set_version(rules, version), encoding="utf-8")
    print(f"Synced guide.md (revision {version}). Review rules.toml for rule changes.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
