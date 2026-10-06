---
name: review-release-notes
description: Review release notes, a changelog, or a what's-new page against the team's active style guide (Signal by default) and release-note conventions, and return a scored report with line-level findings and fixes. Use whenever someone asks to review, check, QA, tighten, or proofread release notes, a changelog entry, or a version announcement, even if they never mention a style guide.
---

# Review release notes

Produce one scored report for one set of release notes. The report follows `reference/review-report.md` at the PAKT root.

## 1. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The `guide.md` of the active guide.
- **The effective rules** – The output of `pakt guide --rules --type release_note --json`. Release notes use a corporate voice, so some rules differ from other content types.
- **The release-note conventions** – The `release_note` entry in the output of `pakt types --json`. The active guide can rename the section headings, so take them from this output.

## 2. Run the deterministic pass

```bash
pakt review <file> --type release_note --json
```

Keep every finding from this output. Each one is a fact that carries a rule ID and a line number.

## 3. Run the judgment pass

Read the notes as a customer who skims them before an upgrade. Check every judgment rule from the guide and every release-note requirement without a `check`. These questions help:

- **Capability first** – Does each line name the new capability, not the work that the team did?
- **Internal noise** – Does any line describe a refactor, a test, or a build step that stays invisible to readers?
- **Deprecations** – Does each deprecation callout name the feature, the end-of-life date, the impact, the reason, and the migration path?
- **Placement** – Does each change sit under the right heading?
- **Precision** – Does each line name the feature, the version, and the limit or value that changed?

## 4. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. Offer to apply the fixes, but change the file only when the person asks.
