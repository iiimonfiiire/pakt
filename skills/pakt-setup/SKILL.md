---
name: pakt-setup
description: Set up PAKT for a docs team by interviewing them first. Chooses Signal, another bundled guide, or the team's own style guide, maps content types, seeds a product glossary, and writes the project's .pakt.toml file. Use whenever someone wants to set up, onboard, configure, or install PAKT for a team or repository, bring their own style guide, or change which style guide PAKT uses.
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
2. **Style guide** – Pick one option:
   - Signal, the default guide.
   - Another bundled guide. Run `pakt guide` to list them.
   - The team's own guide in a file or at a link.
3. **House rules** – For a custom guide, ask about the rules that change checks. Examples include the sentence length limit, contractions, banned words, and release-note section names.
4. **Terminology** – Whether the team already keeps a glossary or term list.
5. **Gates** – Who approves release notes, and whether audits should fail a CI build.

## 2. Bring in a custom guide

Skip this step when the team picks a bundled guide.

1. Copy the closest bundled guide as a starting point: `pakt new-guide style/<name> --from signal`.
2. Replace `guide.md` with the team's guide text.
3. Edit `rules.toml` to match it. For each rule, keep the `check` and set its `params` when a deterministic check fits. Delete the `check` when the rule needs judgment, and delete the rule when the team's guide does not have it.
4. Run `pakt guide --guide style/<name> --rules` and read the list back to the team.

The full walkthrough lives in `docs/style-guides.md` at the PAKT root.

## 3. Write the configuration

Run `pakt init --guide <name or path>` in the repository root. Then edit `.pakt.toml`:

- **`[content] include`** – The file patterns that count as docs.
- **`[content.types]`** – A path pattern for each content type that the interview mapped.
- **`[glossary] path`** – The glossary file, once it exists.

## 4. Seed the glossary

Hand over to the `terminology-check` skill to build the first glossary from the team's docs.

## 5. Prove it works

1. Run `pakt guide`, and confirm that it names the chosen guide and `.pakt.toml` as the source.
2. Run `pakt audit <docs folder> --limit 10`, and walk the team through the top of the report.
3. Explain the next skills to use: the five reviewer skills, `content-audit`, `release-notes-drafter`, and `docs-gap-finder`.
