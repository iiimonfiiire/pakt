# Load the active style guide

Every PAKT skill works against one style guide: the active guide. Signal is the default, and a team can swap in its own. A skill reads the guide at run time and never copies its rules. A skill therefore cannot drift from the guide.

## Find the PAKT root

The PAKT root is the folder that holds `styleguides/`, `content-types.toml`, and `prompts/`. When a skill loads, Claude Code shows the skill's base folder. The PAKT root sits two folders above it.

## Ask the CLI first

Run this command from the folder that holds the docs:

```bash
pakt guide --json
```

The output names the guide, the guide document, the rules file, and the setting that chose them. Rules change by content type, so add `--type <type>` to list the effective rules for one type. Add `--kind judgment` to list only the rules that need judgment.

If the shell reports that `pakt` is missing, install it once:

```bash
pip install -e <PAKT root>
```

## Resolve the guide by hand

Use this order when you cannot run the CLI. The first match wins.

1. **Command option** – A `--guide` value that the person gives you.
2. **Project file** – A `.pakt.toml` file in the current folder or any parent folder. Its `[styleguide]` table holds either `name`, a bundled guide, or `path`, a folder relative to the project file.
3. **PAKT config** – The `[styleguide] active` value in `config.toml` at the PAKT root.
4. **Default** – The bundled `signal` guide.

A bundled guide lives in `styleguides/<name>/` under the PAKT root. Every guide folder holds two files:

- **`guide.md`** – The full guide in prose. Read all of it before you judge any text.
- **`rules.toml`** – Every rule with its ID, severity, and summary. A rule with a `check` runs deterministically. A rule without one needs judgment.

## Read the content type

Structural conventions for each content type live in `content-types.toml` at the PAKT root. A guide can replace a requirement by ID under `[content_types.<type>]` in its own `rules.toml`. Run `pakt types --json` to get the merged list.

## Rules for every skill

- **Cite rule IDs** – Name the rule ID from `rules.toml` or `content-types.toml` in every finding. Never invent an ID.
- **Quote exactly** – Quote the text word for word, so the author can find it.
- **Trust the checks** – Treat the deterministic findings from `pakt` as facts. Spend your own attention on the judgment rules.
- **Name the guide** – Put the guide name and version at the top of every report.
