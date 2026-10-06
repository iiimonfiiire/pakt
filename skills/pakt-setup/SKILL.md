---
name: pakt-setup
description: Set up PAKT for a docs team by interviewing them first. Picks the style guide (Signal by default, a public guide through a Vale package, or the team's own guide imported into a rules pack), maps content types, seeds a product glossary, and writes the project's .pakt.toml file. Use whenever someone wants to set up, onboard, configure, or install PAKT for a team or repository, bring their own style guide, or change which style guide PAKT uses.
---

# Set up PAKT for a team

Interview the team before you change any file. Then write the configuration and prove that it works on their own docs.

## Interview rules

- **Ask, do not assume** – Use multiple-choice questions wherever there is a real choice. Ask an open question only when no option list fits.
- **Skip the known** – Read the repository, any existing `.pakt.toml`, and any style guide in it first. Ask only what you cannot infer.
- **Bundle questions** – Group related questions. Keep the interview to five rounds at most.
- **Confirm before writing** – Summarize what you understood, and wait for a yes before you create files.

## 1. Interview

Cover these topics:

1. **Content** – Which content types the team writes, and where each type lives in the repository. Run `pakt types` to list them, including the KB subtypes.
2. **Style guide** – Pick one of three paths:
   - **Signal** – The default. PAKT fetches it from its public repo, pinned to one commit. Nothing to configure.
   - **Public guide** – A guide with a Vale package, such as Google or Microsoft. Vale must be installed.
   - **Own guide** – The company's guide, from a file or a URL. PAKT needs a rules pack for it, which step 3 drafts.
3. **Terminology** – Whether the team already keeps a glossary or term list.
4. **Gates** – Who approves release notes, and whether audits should fail a CI build.

## 2. Path: a public guide through Vale

Skip this step unless the team picked a public guide.

1. Check for Vale with `vale --version`. If it is missing, give the install hint from the error, and stop until Vale works.
2. Pick the package and a release to pin, such as `vale:Google@v0.6.1`. The Vale package list names each package and its releases.
3. Ask for a URL or a file with the guide prose, and set it as `prose`. Without prose, reviews still run, but the judgment layer has no guide text.
4. A Vale package holds no content-type requirements. Ask whether the team wants any. If so, write a requirements file with `[content_types.<type>]` tables, and set it as `requirements`.

## 3. Path: import the team's own guide

Skip this step unless the team picked its own guide. The guide prose stays the source of truth. The rules pack only points into it.

1. Get the guide as a file or a URL. Read all of it.
2. Draft a rules pack. Start from `pakt new-guide style/<name> --from signal` for the format, then rewrite every rule from the team's guide:
   - **IDs** – One stable rule ID per rule in the guide.
   - **Sections** – Cite the exact heading in the team's guide for every rule.
   - **Severity** – Map each rule to error, warning, or suggestion, and ask when the guide is unclear.
   - **Checks** – Add a `check` with `params` only where the guide states a hard number or a fixed list. Every other rule stays a judgment rule.
   - **Nothing extra** – Never add a rule that the guide does not state.
3. Show the drafted pack to the team, rule by rule. Change it until a person approves it. Never save an unapproved pack as the active guide.
4. Save the approved pack next to the guide in its own repo, or in the docs repo, such as `style/<name>/rules.toml`.
5. Run `pakt guide show --guide <source> --rules` and read the result back to the team.

The full format lives in `docs/style-guides.md` at the PAKT root.

## 4. Write the configuration

Run `pakt init` in the repository root, with `--guide <source>` for any path except Signal. Then edit `.pakt.toml`:

- **`[styleguide]`** – The `source`, plus `rules`, `prose`, or `requirements` when the path needs them. Pin a remote source to a tag or a commit.
- **`[content] include`** – The file patterns that count as docs.
- **`[content.types]`** – A path pattern for each content type that the interview mapped.
- **`[glossary] path`** – The glossary file, once it exists.

## 5. Seed the glossary

Hand over to the `terminology-check` skill to build the first glossary from the team's docs.

## 6. Prove it works

1. Run `pakt guide fetch`, then `pakt guide show`. Confirm the source, the pin, and `.pakt.toml` as the setting that chose them.
2. Run `pakt audit <docs folder> --limit 10`, and walk the team through the top of the report.
3. Explain the next skills to use: the five reviewer skills, `content-audit`, `release-notes-drafter`, and `docs-gap-finder`.
