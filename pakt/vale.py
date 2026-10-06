"""Vale as the deterministic layer for public style guides, such as vale:Google or vale:Microsoft.

Vale is an optional external binary. PAKT writes a .vale.ini in its cache, runs `vale sync`
once per package, then runs `vale --output=JSON` and maps each alert to a PAKT finding.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from .config import ConfigError
from .sources import cache_root

if TYPE_CHECKING:
    from .review import Finding
    from .styleguide import StyleGuide

INSTALL_HINT = (
    "Vale is not installed. Install it with `brew install vale` on macOS, or follow "
    "https://vale.sh/docs/install for other systems. Set PAKT_VALE to use a binary outside PATH."
)
RELEASE_ZIP = "https://github.com/errata-ai/{package}/releases/download/{ref}/{package}.zip"
SEVERITY = {"error": "error", "warning": "warning", "suggestion": "suggestion"}


class ValeError(ConfigError):
    pass


def find_vale() -> str:
    binary = os.environ.get("PAKT_VALE") or shutil.which("vale")
    if not binary:
        raise ValeError(INSTALL_HINT)
    return binary


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    """Run Vale. Tests replace this function with recorded output."""
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)


def package_ref(guide: "StyleGuide") -> str:
    """What goes in the Packages key: the package name, or a release zip URL when pinned."""
    ref = guide.vale_ref
    if not ref:
        return guide.vale_package
    if ref.startswith(("https://", "http://")):
        return ref
    return RELEASE_ZIP.format(package=guide.vale_package, ref=ref)


def workdir(guide: "StyleGuide") -> Path:
    key = hashlib.sha256(package_ref(guide).encode()).hexdigest()[:12]
    return cache_root() / "vale" / f"{guide.vale_package}-{key}"


def write_config(guide: "StyleGuide") -> Path:
    folder = workdir(guide)
    (folder / "styles").mkdir(parents=True, exist_ok=True)
    ini = folder / ".vale.ini"
    ini.write_text(
        "StylesPath = styles\n"
        "MinAlertLevel = suggestion\n"
        f"Packages = {package_ref(guide)}\n\n"
        "[*]\n"
        f"BasedOnStyles = Vale, {guide.vale_package}\n",
        encoding="utf-8",
    )
    return ini


def sync(guide: "StyleGuide") -> Path:
    """Download the package once. A pinned package never syncs again."""
    binary = find_vale()
    ini = write_config(guide)
    folder = ini.parent
    marker = folder / ".synced"
    if marker.is_file() and guide.pinned:
        return folder
    result = _run([binary, "--config", str(ini), "sync"], folder)
    if result.returncode != 0:
        raise ValeError(f"vale sync failed for {package_ref(guide)}: {(result.stderr or result.stdout).strip()}")
    marker.write_text(package_ref(guide) + "\n", encoding="utf-8")
    return folder


def lint(guide: "StyleGuide", text: str, suffix: str = ".md") -> list[dict]:
    """Run Vale on text and return its alerts, in file order."""
    folder = sync(guide)
    target = folder / f"input{suffix}"
    target.write_text(text, encoding="utf-8")
    result = _run([find_vale(), "--config", str(folder / ".vale.ini"), "--output=JSON", str(target)], folder)
    if result.returncode not in (0, 1):
        raise ValeError(f"vale failed: {(result.stderr or result.stdout).strip()}")
    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ValeError(f"vale returned output that is not JSON: {exc.msg}") from exc
    if isinstance(data, dict) and "Code" in data and "Text" in data:
        raise ValeError(f"vale error {data['Code']}: {data['Text']}")
    alerts = [a for file_alerts in data.values() for a in file_alerts] if isinstance(data, dict) else []
    return sorted(alerts, key=lambda a: (a.get("Line", 0), (a.get("Span") or [0])[0]))


def _fix(alert: dict) -> str:
    action = alert.get("Action") or {}
    params = [p for p in action.get("Params") or [] if p]
    if action.get("Name") == "replace" and params:
        return f"Write '{params[0]}'."
    if action.get("Name") == "remove":
        return "Delete it."
    return f"See {alert['Link']}." if alert.get("Link") else ""


def to_findings(alerts: list[dict], text: str, line_map: dict[int, int] | None = None) -> list["Finding"]:
    """Map Vale alerts to findings: the rule ID is the Vale check name, and the quote comes from the span."""
    from .review import Finding

    lines = text.splitlines()
    out = []
    for a in alerts:
        line = int(a.get("Line") or 0)
        quote = a.get("Match") or ""
        span = a.get("Span") or []
        if not quote and len(span) == 2 and 0 < line <= len(lines):
            quote = lines[line - 1][span[0] - 1: span[1]]
        out.append(Finding(
            rule=a.get("Check", "Vale"), severity=SEVERITY.get(str(a.get("Severity", "")).lower(), "warning"),
            message=a.get("Message", ""), quote=quote,
            line=(line_map or {}).get(line, line) or None, fix=_fix(a), source="vale",
        ))
    return out
