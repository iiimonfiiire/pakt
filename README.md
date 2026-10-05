# PAKT: Portable Agentic Knowledge Toolkit

PAKT is a toolkit for documentation and knowledge teams. It centers on the [Signal style guide](https://github.com/iiimonfiiire/signal-style-guide), a style guide for clear, concise, and easy-to-scan writing.

The main part is a prompt-evaluation harness. It answers one question with numbers: which prompt rewrites messy docs into Signal style best, without changing what the docs say?

## What is inside

- **Signal rewriter** – Versioned prompts that rewrite a messy snippet into Signal style, plus a thin Claude Code skill in `skills/signal-rewrite/`.
- **Test set** – 25 hand-written messy snippets across five content types, each tagged with the style failures it contains.
- **Rule checks** – Small, unit-tested Python functions that test a text against the checkable Signal rules.
- **LLM-as-judge** – A second model scores each rewrite for meaning preservation and readability against a written rubric.
- **Runner and report** – A CLI that runs every prompt variant on every snippet, caches responses on disk, and writes a comparison report.

To learn how the harness works and why, read [the eval harness walkthrough](docs/eval-harness.md). For short definitions of the terms, see [the glossary](docs/glossary.md).

## Quickstart

You need Python 3.11 or later.

1. Create and activate a virtual environment.

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   ```

2. Install the package with its test dependencies.

   ```bash
   pip install -e ".[dev]"
   ```

3. Run the unit tests. They run offline and need no API key.

   ```bash
   pytest
   ```

4. Score the bundled sample outputs offline. This mode makes no model calls.

   ```bash
   pakt-eval score --outputs evals/data/sample_outputs.jsonl
   ```

5. Add your API key. Copy the example file, then restrict its permissions.

   ```bash
   cp .env.example .env
   chmod 600 .env
   ```

   Then set `ANTHROPIC_API_KEY` in `.env`. Git ignores the file. Never commit it.

6. Preview the full run and its estimated cost. A dry run calls nothing.

   ```bash
   pakt-eval run --dry-run
   ```

7. Run the eval. Start small, then run everything.

   ```bash
   pakt-eval run --variants v1,v2 --limit 3
   pakt-eval run
   ```

   The report lands in `evals/results/<run-id>/report.md`.

## Commands

- **`pakt-eval variants`** – List the prompt variants and the hypothesis behind each one.
- **`pakt-eval run`** – Generate, check, judge, and report. Useful flags: `--dry-run`, `--variants`, `--ids`, `--limit`, `--no-judge`, and `--cache-only`.
- **`pakt-eval score --outputs FILE`** – Rule-check a JSONL file of existing outputs. No API key needed.
- **`pakt-eval judge-check`** – Compare judge scores with hand labels on a small spot-check set.
- **`pakt-eval lint FILE...`** – Run the Signal rule checks on any text or Markdown file.

## Configuration

Settings live in `config.toml`: models, token limits, concurrency, rule thresholds, prices, and paths. The defaults use `claude-haiku-4-5-20251001` as the generator and `claude-sonnet-5-5` as the judge.

To override a model without editing the file, set `PAKT_GENERATOR_MODEL` or `PAKT_JUDGE_MODEL` in `.env`. Secrets belong in `.env` only.

> **Note:** The prices in `config.toml` are for cost reporting only. Check them against current published pricing before you quote a cost.

## Repository layout

```text
.
├── config.toml                 models, limits, prices, and paths
├── .env.example                placeholder for the API key
├── prompts/
│   ├── v1-zero-shot.md         rewrite prompt variants, one file each
│   ├── v2-rules.md
│   ├── v3-few-shot.md
│   ├── v4-plan-then-write.md
│   └── judge/v1.md             judge rubric
├── skills/signal-rewrite/      Claude Code skill
├── evals/
│   ├── data/
│   │   ├── testset.jsonl       the 25 test snippets
│   │   ├── judge_spot_check.jsonl
│   │   └── sample_outputs.jsonl
│   ├── tools/build_testset.py  source of truth for testset.jsonl
│   ├── pakt_evals/             harness package
│   │   ├── rules.py            deterministic Signal checks
│   │   ├── judge.py            LLM-as-judge call and JSON parsing
│   │   ├── llm.py              API client and disk cache
│   │   ├── prompts.py          prompt file loading
│   │   ├── runner.py           test set loading and the eval loop
│   │   ├── report.py           metrics and the Markdown report
│   │   └── cli.py              the pakt-eval command
│   ├── tests/                  pytest suite, fully offline
│   └── results/                committed reports from real runs
└── docs/
    ├── eval-harness.md         plain-language walkthrough
    └── glossary.md
```

## Status

The harness, tests, and docs are complete. The repo holds no results from a real model run yet, so `evals/results/` is empty. Run `pakt-eval run` with a key to produce the first one.
