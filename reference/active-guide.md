# Load the active style guide

Every PAKT skill works against one style guide: the active guide. Signal is the default, and a team can point PAKT at its own guide or at a public one. A skill reads the guide at run time and never copies its rules. A skill therefore cannot drift from the guide.

## Find the PAKT root

The PAKT root is the folder that holds `content-types.toml` and `prompts/`. When a skill loads, Claude Code shows the skill's base folder. The PAKT root sits two folders above it.

## Ask the CLI

Run this command from the folder that holds the docs:

```bash
pakt guide show --json
```

The output names the guide, its source, whether the source is pinned, the prose file, and the rules pack. PAKT fetches a remote guide into its cache on first use. Read both files from the paths in the output.

Rules change by content type, so add `--rules --type <type>` to list the effective rules for one type. Add `--kind judgment` to list only the rules that need judgment.

If the shell reports that `pakt` is missing, install it once:

```bash
pip install -e <PAKT root>
```

If the fetch fails, tell the person what the error says. A 404 usually means a private repo, so suggest a local clone as the source.

## What a guide holds

- **Prose** – The full guide, written for people. Read all of it before you judge any text. A guide may have no prose, such as a Vale package without a `prose` setting. Then say so in the report, and judge only clarity, structure, and scannability.
- **Rules pack** – Every rule with its ID, severity, summary, and section. A rule with a `check` runs deterministically. A rule without one needs judgment.
- **Vale rules** – A `vale:` source has no rules pack. Vale produces its deterministic findings, and each rule ID is a Vale check name, such as `Google.Contractions`.

## Read the content type

`content-types.toml` at the PAKT root defines the content types and subtypes. The guide supplies their requirements. Run `pakt types --json` to get the merged list. A guide without requirements leaves only the style rules, plus any local requirements file that `.pakt.toml` names.

## Rules for every skill

- **Cite rule IDs** – Name the rule ID from the guide or from `pakt types` in every finding. Never invent an ID.
- **Quote exactly** – Quote the text word for word, so the author can find it.
- **Trust the checks** – Treat the deterministic findings from `pakt` as facts. Spend your own attention on the judgment rules.
- **Name the guide** – Put the guide name, its version, and its source at the top of every report.
