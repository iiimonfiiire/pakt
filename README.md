# PAKT

**Portable Agentic Knowledge Toolkit.** PAKT checks that every piece of product knowledge content follows one style guide. That covers KB articles and guides, release notes, UX microcopy, and API documentation.

PAKT ships as a Claude Code plugin with ten skills for documentation teams, technical writers, and knowledge managers. A command-line tool, `pakt`, runs the deterministic checks that the skills build on. An eval harness, `pakt-eval`, measures how accurate the reviewers and the rewriter are.

The default style guide is Signal, a guide for clear, concise, and easy-to-scan writing. A team can swap in its own guide without touching any skill.

## Skill catalog

| Skill | What it does |
|---|---|
| `review-kb-article` | Scores a KB article, guide, or troubleshooting page against the guide and KB conventions. |
| `review-release-notes` | Scores release notes or a changelog against the guide and release-note conventions. |
| `review-ui-microcopy` | Scores UI strings, such as buttons, errors, empty states, and tooltips, string by string. |
| `review-api-docs` | Scores an API reference page against the guide and API conventions. |
| `content-audit` | Scores every file in a docs folder, ranks them worst-first, and counts findings per rule. |
| `release-notes-drafter` | Turns commits, pull requests, or tickets into a draft that a person must approve. |
| `terminology-check` | Builds a product glossary and flags variant terms, banned words, and undefined jargon. |
| `docs-gap-finder` | Finds missing or stale topics from tickets and changelogs, and cites the source of every gap. |
| `pakt-setup` | Interviews a team, then picks or builds its style guide and writes its configuration. |
| `signal-rewrite` | Rewrites a messy snippet to follow the active guide without changing its facts. |

Every reviewer returns the same report: a score from 1 to 10 for each of four criteria, a verdict, and line-level findings. Each finding carries a quote, a rule ID, and a fix. For the format, see [the review report reference](reference/review-report.md).

## How the reviewers work

Each review has two layers:

- **Deterministic checks** – Regex and structure checks that run offline in milliseconds. Examples include sentence length, contractions, heading case, and a release note's sections.
- **Judgment** – Rules that a regex cannot judge, such as one term per concept. Claude applies them inside the skills, or through `pakt review --model`.

The rules file of the active guide decides which rules exist, which layer runs each one, and the threshold of every check.

## Install

You need Python 3.11 or later and Claude Code.

1. Clone this repository, then install the CLI from the clone.

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -e ".[dev]"
   ```

2. Add the plugin in Claude Code. Use the local path of your clone, or the repository's Git URL.

   ```text
   /plugin marketplace add ./pakt
   /plugin install pakt@pakt
   ```

3. Run the tests. They run offline and need no API key.

   ```bash
   pytest
   ```

To use the CLI outside the clone, set `PAKT_ROOT` to the clone's path.

## Quickstart

Run these commands from the folder that holds your docs:

```bash
pakt init                                   # write a .pakt.toml that picks the guide
pakt guide                                  # show the active guide and where the choice came from
pakt review docs/kb/export.md               # score one file
pakt audit docs                             # score every file, worst first
pakt terms --suggest docs --out glossary.toml
pakt gaps --sources tickets.jsonl --docs docs
pakt release-notes draft --commits commits.txt --product Fernbook --version 2.5 --out notes.md
```

In Claude Code, ask in plain words, such as "review this release note" or "audit the docs folder." The matching skill loads on its own.

## Swap the style guide

A style guide is a folder with two files:

- **`guide.md`** – The full guide in prose. The skills read it at run time.
- **`rules.toml`** – Every rule with an ID, a severity, and a summary. A rule with a `check` runs deterministically, with thresholds such as `max_words`.

To use another guide, set it in the project's `.pakt.toml` file:

```toml
[styleguide]
path = "style/house-guide"
```

PAKT bundles two guides. Signal is the default. Plainspoken is a minimal second guide that exists to prove the swap works. To build your own guide, see [the style guide walkthrough](docs/style-guides.md), or run the `pakt-setup` skill.

## Commands

### `pakt`

- **`pakt guide`** – Show the active guide. Add `--rules` to list its rules.
- **`pakt types`** – List the content types and their structural requirements.
- **`pakt lint FILE...`** – Run the deterministic checks and print one line per finding.
- **`pakt review FILE`** – Score one file. Useful flags: `--type`, `--json`, `--glossary`, and `--model`.
- **`pakt audit [DIR]`** – Score every file and rank them worst-first. Add `--fail-on fail` to fail a CI build.
- **`pakt terms FILE...`** – Check terminology against a glossary. Use `--suggest DIR` to draft a glossary.
- **`pakt gaps`** – List gap candidates from tickets, support questions, or changelogs.
- **`pakt release-notes draft`** – Build a release-notes draft from commits or tickets.
- **`pakt release-notes approve`** – The human gate. It needs `--approved-by` and refuses a draft with open TODO markers.
- **`pakt init`** – Write a `.pakt.toml` file for the current project.
- **`pakt new-guide DIR`** – Copy a guide into a folder as the start of a custom guide.

### `pakt-eval`

- **`pakt-eval review-eval`** – Measure reviewer precision and recall on labeled documents.
- **`pakt-eval run`** – Compare rewrite prompt variants. Add `--dry-run` to preview the cost.
- **`pakt-eval score --outputs FILE`** – Rule-check a file of existing rewrites offline.
- **`pakt-eval judge-check`** – Compare the meaning judge with hand labels.
- **`pakt-eval variants`** – List the rewrite prompt variants and their hypotheses.
- **`pakt-eval lint FILE...`** – Run the deterministic checks.

## The eval layer

A reviewer is only useful when its findings are right. The eval harness measures that with two test sets:

- **Reviewer sets** – 32 short documents, eight per content type, with hand-labeled rule violations. `pakt-eval review-eval` reports precision, recall, and F1 by rule, by rule kind, and by content type.
- **Rewrite set** – 25 messy snippets. `pakt-eval run` compares four rewrite prompts on style and meaning, with a second model as the judge.

Every test runs offline with fake model clients. For the walkthrough, see [the eval harness guide](docs/eval-harness.md). For the terms, see [the glossary](docs/glossary.md).

## Configuration

- **`config.toml`** – The default guide, models, token limits, prices, and paths.
- **`.pakt.toml`** – Per project: the guide, the glossary, file patterns, and content-type paths.
- **`.env`** – The API key and model overrides. Copy `.env.example`, then run `chmod 600 .env`. Git ignores the file.

> **Note:** The prices in `config.toml` serve cost estimates only. Check them against current published pricing before you quote a cost.

## Repository layout

```text
.
├── .claude-plugin/             plugin manifest and marketplace entry
├── skills/                     ten skills, one folder each
├── reference/                  shared instructions that the skills read
├── styleguides/
│   ├── signal/                 default guide: guide.md and rules.toml
│   └── plainspoken/            minimal second guide
├── content-types.toml          structural conventions per content type
├── pakt/                       the pakt package and CLI
├── prompts/                    rewrite variants, the judge rubric, and the review rubric
├── evals/
│   ├── data/                   rewrite set, judge spot checks, and reviewer sets
│   ├── tools/                  builders for the test sets
│   ├── pakt_evals/             the pakt-eval harness
│   ├── tests/                  pytest suite, fully offline
│   └── results/                reports from real runs
└── docs/                       walkthroughs and the glossary
```

## Status

- **Toolkit** – The CLI, the ten skills, and the pluggable guides work, and the tests cover them.
- **Results** – No real model run exists yet, so `evals/results/` holds no reports. The deterministic layer finds every check-kind label in the reviewer sets. The judgment layer still needs a measured run.
- **Next** – Run `pakt-eval review-eval --mode model` with a key, then review the labels with a second writer.
