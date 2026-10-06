---
name: release-notes-drafter
description: Draft style-compliant release notes from raw inputs such as commits, a git range, pull requests, tickets, or engineer notes, using the team's active style guide (Signal by default) and its release-note sections. Always produces a draft for human approval, never final notes. Use whenever someone asks to write, draft, generate, or prepare release notes, a changelog, or a what's-new post for a version.
---

# Draft release notes

Turn raw engineering inputs into a release-notes draft that a person reviews and approves. A draft is never final. Only the person who owns the release approves it.

## 1. Gather the inputs

Ask for anything that is missing, in one round:

- **Product and version** – The product name and the version number.
- **Commits** – A git range, such as `v2.4.0..v2.5.0`. Export it with `git log --format='%h %s' <range> > commits.txt`.
- **Pull requests or tickets** – A JSONL file with one item per line: `id`, `title`, and optionally `type`, `labels`, and `breaking`.
- **Engineer notes** – Free text about behavior, limits, or migration steps. Treat these notes as the only source for facts that the commits do not state.
- **Audience** – Who reads the notes, such as admins, developers, or every user.

## 2. Load the guide

Follow `reference/active-guide.md` at the PAKT root. The release-note sections come from the `release_note` content type, so the active guide can rename them.

## 3. Build the skeleton

```bash
pakt release-notes draft --commits commits.txt --items prs.jsonl --product <name> --version <version> --out release-notes-<version>.md
```

The skeleton uses the release-note headings of the active guide, in order, and keeps a source comment on every line. Internal changes wait in a comment block. Every breaking change or removal lands in a deprecation callout with a `TODO` for each required field.

## 4. Rewrite every line

Rewrite each line for the reader, following the active guide:

- **Facts only from the inputs** – Never invent a feature, a number, a limit, or a migration step. When a line needs a fact that no input states, keep the `TODO` and add a question for the person.
- **Capability first** – Name the new capability, not the work that the team did.
- **Deprecations** – Fill each field of the deprecation callout from the inputs only.
- **Sources stay** – Keep each `<!-- source: ... -->` comment on its line, so the person can trace every claim.
- **Internal changes** – Check the internal block. Move a change into the notes only when its effect shows up for readers.

Then run `pakt review release-notes-<version>.md --type release_note` and fix every finding that you can fix from the inputs.

## 5. Hand over the draft

Present the draft with three parts:

1. **The draft itself** – Labeled as a draft.
2. **Open questions** – Every remaining `TODO`, as a direct question.
3. **Traceability** – Any line whose source you could not confirm.

Stop there. Do not approve, publish, commit, or push the notes.

## 6. The human gate

The approval step removes the draft markers and records who approved the notes:

```bash
pakt release-notes approve release-notes-<version>.md --approved-by <name>
```

Run it only after the person says, in this conversation, that they approve this draft. Use the name or handle exactly as they give it. The command refuses a draft with any `TODO` left, or with error findings from the review.
