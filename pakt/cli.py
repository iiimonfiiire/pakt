"""Command-line entry point: pakt."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from . import audit as audit_mod
from . import gaps as gaps_mod
from . import release_notes as rn
from .config import PROJECT_FILE, ConfigError, Settings, _load_dotenv, find_root, load_settings, require_api_key, resolve_guide
from .document import load_document, parse_document
from .review import load_template, review, verdict_for
from .structure import detect_type, load_content_types, refine_type
from .sources import bundled_guides
from .styleguide import get_guide
from .terminology import check_terms, load_glossary, suggest_glossary


def _emit(text: str, out: str | None) -> None:
    if out:
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_text(text, encoding="utf-8")
        print(f"Wrote {out}")
    else:
        print(text, end="" if text.endswith("\n") else "\n")


def _settings(args) -> Settings:
    return load_settings(Path.cwd(), getattr(args, "guide", None))


def _rel(path: Path, settings: Settings) -> str:
    anchor = settings.project_file.parent if settings.project_file else Path.cwd()
    try:
        return path.resolve().relative_to(anchor.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def cmd_guide(args) -> int:
    if args.action == "fetch":
        root = find_root()
        _load_dotenv(root)
        g = resolve_guide(root, Path.cwd(), args.guide, refresh=True)
        print(f"Fetched {g.label} from {g.source}")
        if g.engine == "vale":
            from . import vale

            print(f"  synced Vale package into {vale.sync(g)}")
        return 0
    s = _settings(args)
    g = s.guide
    ctype = None
    if args.type:
        types = load_content_types(g, s.root)
        if args.type not in types:
            raise ConfigError(f"unknown content type {args.type!r}. Known: {', '.join(types)}")
        ctype = types[args.type]
    rules = [r for r in g.rules_for(ctype) if not args.kind or r.kind == args.kind]
    if args.json:
        payload = g.summary()
        if args.rules:
            payload["content_type"] = args.type or ""
            payload["rule_list"] = [r.to_dict() for r in rules]
        print(json.dumps(payload, indent=2))
        return 0
    print(f"Active style guide: {g.label} ({g.id})")
    print(f"  selected by: {g.origin}")
    print(f"  source:      {g.source} ({'pinned' if g.pinned else 'not pinned'})")
    print(f"  engine:      {'Vale, for the deterministic layer' if g.engine == 'vale' else 'PAKT rules pack'}")
    print(f"  prose:       {g.document if g.has_prose else 'none configured'}")
    if g.rules_file:
        print(f"  rules pack:  {g.rules_file}")
    print(f"  rule count:  {len(g.checkable)} deterministic, {len(g.judgment)} judgment")
    if args.rules:
        if args.type:
            print(f"  effective rules for: {args.type}")
        for r in rules:
            print(f"  - {r.id} [{r.kind}, {r.severity}] {r.summary}")
    print(f"Bundled guides: {', '.join(bundled_guides(s.root))}")
    return 0


def cmd_types(args) -> int:
    s = _settings(args)
    types = load_content_types(s.guide, s.root)
    if args.json:
        print(json.dumps({
            t.id: {
                "name": t.name, "description": t.description, "parent": t.parent, "tags": list(t.tags),
                "requirements": [r.to_dict() for r in t.requirements],
            }
            for t in types.values()
        }, indent=2))
        return 0
    for t in types.values():
        parent = f" (subtype of {t.parent})" if t.parent else ""
        print(f"{t.id}: {t.name}{parent}")
        for r in t.requirements:
            print(f"  - {r.id} [{r.kind}, {r.severity}] {r.summary}")
    return 0


def cmd_lint(args) -> int:
    s = _settings(args)
    types = load_content_types(s.guide, s.root)
    if args.type and args.type not in types:
        raise ConfigError(f"unknown content type {args.type!r}. Known: {', '.join(types)}")
    failures = 0
    rows = []
    for name in args.files:
        doc = load_document(Path(name))
        type_id = refine_type(doc, types, args.type) if args.type else "general"
        report = review(doc, s.guide, types[type_id])
        for f in report.findings:
            failures += 1
            rows.append({"file": name, **f.to_dict()})
            if not args.json:
                print(f"{name}:{f.line or '?'}: {f.rule}: {f.message}")
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(f"{failures} finding(s)" if failures else "clean")
    return 1 if failures else 0


def _client(s: Settings, cache_only: bool = False):
    from .llm import AnthropicClient, CachedClient, CacheOnlyClient

    inner = CacheOnlyClient() if cache_only else AnthropicClient(require_api_key())
    return CachedClient(inner, s.root / "evals" / ".cache", "reviews")


def cmd_review(args) -> int:
    s = _settings(args)
    types = load_content_types(s.guide, s.root)
    path = Path(args.file)
    doc = load_document(path)
    type_id = args.type or detect_type(doc, types, _rel(path, s), s.type_map)
    if type_id not in types:
        raise ConfigError(f"unknown content type {type_id!r}. Known: {', '.join(types)}")
    type_id = refine_type(doc, types, type_id)
    kwargs = {}
    if args.model:
        kwargs = dict(
            client=_client(s, args.cache_only), model=s.review_model, template=load_template(s.review_prompt),
            max_tokens=s.review_max_tokens, temperature=s.review_temperature,
        )
    report = review(doc, s.guide, types[type_id], **kwargs)
    report.path = _rel(path, s)
    glossary_path = Path(args.glossary) if args.glossary else s.glossary
    if glossary_path:
        report.findings += check_terms(doc, load_glossary(glossary_path))
        report.verdict = verdict_for(report.scores, report.findings)
    _emit(json.dumps(report.to_dict(), indent=2) + "\n" if args.json else report.to_markdown(), args.out)
    return 1 if report.verdict == "fail" else 0


def cmd_audit(args) -> int:
    s = _settings(args)
    types = load_content_types(s.guide, s.root)
    base = Path(args.path)
    glossary_path = Path(args.glossary) if args.glossary else s.glossary
    glossary = load_glossary(glossary_path) if glossary_path else None
    entries = audit_mod.audit(
        base, s.guide, types, args.include or s.include, s.exclude, s.type_map, glossary,
        s.project_file.parent if s.project_file else None,
    )
    if args.json:
        _emit(json.dumps(audit_mod.to_dict(entries, s.guide), indent=2) + "\n", args.out)
    else:
        _emit(audit_mod.render_markdown(entries, s.guide, args.path, args.limit), args.out)
    worst = {"fail": ("fail",), "revise": ("fail", "revise"), "never": ()}[args.fail_on]
    return 1 if any(e.report.verdict in worst for e in entries) else 0


def cmd_terms(args) -> int:
    s = _settings(args)
    if args.suggest:
        files = audit_mod.collect_files(Path(args.suggest), s.include, s.exclude)
        _emit(suggest_glossary([load_document(f) for f in files]), args.out)
        return 0
    glossary_path = Path(args.glossary) if args.glossary else s.glossary
    if not glossary_path:
        raise ConfigError("no glossary: pass --glossary FILE, or set [glossary] path in .pakt.toml")
    if not args.files:
        raise ConfigError("name one or more files to check, or use --suggest DIR")
    glossary = load_glossary(glossary_path)
    rows = []
    for name in args.files:
        for f in check_terms(load_document(Path(name)), glossary):
            rows.append({"file": name, **f.to_dict()})
    if args.json:
        _emit(json.dumps(rows, indent=2) + "\n", args.out)
    else:
        text = "\n".join(f"{r['file']}:{r['line'] or '?'}: {r['rule']}: {r['message']}" for r in rows)
        _emit((text + "\n" if text else "") + (f"{len(rows)} finding(s)\n" if rows else "clean\n"), args.out)
    return 1 if any(r["severity"] == "error" for r in rows) else 0


def cmd_gaps(args) -> int:
    s = _settings(args)
    items = gaps_mod.load_sources([Path(p) for p in args.sources])
    base = Path(args.docs)
    files = audit_mod.collect_files(base, s.include, s.exclude)
    docs = {f.relative_to(base).as_posix() if base.is_dir() else f.name: load_document(f) for f in files}
    found = gaps_mod.find_gaps(items, docs)
    if args.json:
        _emit(json.dumps([g.to_dict() for g in found], indent=2) + "\n", args.out)
    else:
        _emit(gaps_mod.render_markdown(found, len(items), len(docs)), args.out)
    return 0


def cmd_rn_draft(args) -> int:
    s = _settings(args)
    changes = []
    if args.commits:
        changes += rn.parse_commits(Path(args.commits).read_text(encoding="utf-8"))
    if args.items:
        changes += rn.parse_items(Path(args.items))
    if not changes:
        raise ConfigError("no input: pass --commits FILE, --items FILE, or both")
    ctype = load_content_types(s.guide, s.root)["release_note"]
    _emit(rn.draft(changes, args.product, args.version, ctype), args.out)
    if args.out:
        print("This is a draft. A person must review it and run `pakt release-notes approve` before it ships.")
    return 0


def cmd_rn_approve(args) -> int:
    s = _settings(args)
    path = Path(args.file)
    text = path.read_text(encoding="utf-8")
    try:
        approved = rn.approve(text, args.approved_by)
    except rn.ApprovalError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    types = load_content_types(s.guide, s.root)
    report = review(parse_document(approved, path), s.guide, types["release_note"])
    errors = [f for f in report.findings if f.severity == "error"]
    if errors and not args.force:
        for f in errors:
            print(f"{path}:{f.line or '?'}: {f.rule}: {f.message}", file=sys.stderr)
        print("error: fix the error findings first, or pass --force to approve anyway", file=sys.stderr)
        return 1
    _emit(approved, args.out or str(path))
    return 0


def cmd_init(args) -> int:
    target = Path.cwd() / PROJECT_FILE
    if target.exists() and not args.force:
        print(f"error: {PROJECT_FILE} already exists. Pass --force to overwrite.", file=sys.stderr)
        return 1
    lines = ["[styleguide]"]
    lines += [f'source = "{args.guide}"'] if args.guide else ["# No source set: PAKT uses Signal, pinned in its config.toml.", '# source = "signal"']
    lines.append("")
    if args.glossary:
        lines += ["[glossary]", f'path = "{args.glossary}"', ""]
    lines += [
        "[content]", 'include = ["**/*.md", "**/*.mdx"]', "exclude = []", "",
        "[content.types]", '# "docs/release-notes/**" = "release_note"', '# "docs/api/**" = "api_doc"',
        '# "src/locales/*.json" = "ui_microcopy"', "",
    ]
    target.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {target}")
    return 0


def cmd_new_guide(args) -> int:
    if args.source:
        g = get_guide(args.source, find_root(), Path.cwd())
    else:
        g = _settings(args).guide
    if g.rules_file is None:
        print(f"error: {g.label} has no rules pack to copy. Write rules.toml by hand.", file=sys.stderr)
        return 1
    dest = Path(args.dir)
    if dest.exists() and any(dest.iterdir()):
        print(f"error: {dest} is not empty", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    text = g.rules_file.read_text(encoding="utf-8")
    if g.has_prose:
        shutil.copyfile(g.document, dest / "guide.md")
        text = re.sub(r'(?m)^document = "[^"]*"', 'document = "guide.md"', text, count=1)
    (dest / "rules.toml").write_text(text, encoding="utf-8")
    print(f"Copied {g.label} to {dest}. Edit guide.md and rules.toml, then set [styleguide] source in {PROJECT_FILE}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="pakt", description="Review, audit, and draft docs against a pluggable style guide.")
    sub = p.add_subparsers(dest="command", required=True)

    def add(name: str, fn, help_text: str) -> argparse.ArgumentParser:
        sp = sub.add_parser(name, help=help_text)
        sp.add_argument("--guide", help="style guide name or folder (overrides .pakt.toml and config.toml)")
        sp.set_defaults(fn=fn)
        return sp

    g = add("guide", cmd_guide, "show the active style guide, or fetch it into the cache")
    g.add_argument("action", nargs="?", choices=["show", "fetch"], default="show",
                   help="show (default), or fetch: download the guide and refresh unpinned sources")
    g.add_argument("--rules", action="store_true", help="list the rules")
    g.add_argument("--kind", choices=["check", "judgment"])
    g.add_argument("--type", help="show the effective rules for one content type")
    g.add_argument("--json", action="store_true")

    t = add("types", cmd_types, "list content types and their structural requirements")
    t.add_argument("--json", action="store_true")

    lint = add("lint", cmd_lint, "run the deterministic style checks on files")
    lint.add_argument("files", nargs="+")
    lint.add_argument("--type", help="apply the rules and requirements of one content type (default: general)")
    lint.add_argument("--json", action="store_true")

    r = add("review", cmd_review, "score one file against the guide and its content type")
    r.add_argument("file")
    r.add_argument("--type", help="a content type ID from `pakt types` (default: detect)")
    r.add_argument("--model", action="store_true", help="add model judgment (needs ANTHROPIC_API_KEY)")
    r.add_argument("--cache-only", action="store_true", help="with --model, use cached responses only")
    r.add_argument("--glossary", help="also check terminology against this glossary")
    r.add_argument("--json", action="store_true")
    r.add_argument("--out")

    a = add("audit", cmd_audit, "review every file in a folder and rank them worst-first")
    a.add_argument("path", nargs="?", default=".")
    a.add_argument("--include", action="append", help="glob to include (repeatable)")
    a.add_argument("--glossary")
    a.add_argument("--limit", type=int, default=50, help="files to list in the report (0 for all)")
    a.add_argument("--fail-on", choices=["fail", "revise", "never"], default="never")
    a.add_argument("--json", action="store_true")
    a.add_argument("--out")

    tm = add("terms", cmd_terms, "check terminology against a glossary, or draft a glossary")
    tm.add_argument("files", nargs="*")
    tm.add_argument("--glossary")
    tm.add_argument("--suggest", metavar="DIR", help="draft a glossary from the docs in DIR")
    tm.add_argument("--json", action="store_true")
    tm.add_argument("--out")

    gp = add("gaps", cmd_gaps, "list doc gaps revealed by tickets, support questions, and changelogs")
    gp.add_argument("--sources", nargs="+", required=True, help="JSONL or CSV files of source items")
    gp.add_argument("--docs", default=".", help="docs folder")
    gp.add_argument("--json", action="store_true")
    gp.add_argument("--out")

    rn_parser = sub.add_parser("release-notes", help="draft release notes, then approve them after human review")
    rn_sub = rn_parser.add_subparsers(dest="rn_command", required=True)
    d = rn_sub.add_parser("draft", help="turn commits, pull requests, or tickets into a draft")
    d.add_argument("--commits", help="text file, one conventional commit per line")
    d.add_argument("--items", help="JSONL of pull requests or tickets")
    d.add_argument("--product", required=True)
    d.add_argument("--version", required=True)
    d.add_argument("--guide")
    d.add_argument("--out")
    d.set_defaults(fn=cmd_rn_draft)
    ap = rn_sub.add_parser("approve", help="the human gate: approve a reviewed draft")
    ap.add_argument("file")
    ap.add_argument("--approved-by", required=True, help="name or handle of the person who approved it")
    ap.add_argument("--force", action="store_true", help="approve despite error findings")
    ap.add_argument("--guide")
    ap.add_argument("--out", help="write here instead of overwriting the draft")
    ap.set_defaults(fn=cmd_rn_approve)

    i = sub.add_parser("init", help=f"write a {PROJECT_FILE} for this project")
    i.add_argument("--guide", help="bundled guide name or folder path")
    i.add_argument("--glossary", help="path to the glossary file")
    i.add_argument("--force", action="store_true")
    i.set_defaults(fn=cmd_init)

    ng = add("new-guide", cmd_new_guide, "copy a guide into a folder as the start of a custom guide")
    ng.add_argument("dir")
    ng.add_argument("--from", dest="source", help="guide to copy (default: the active guide)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (ConfigError, ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
