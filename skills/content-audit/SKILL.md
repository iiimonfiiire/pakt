---
name: content-audit
description: Audit a whole docs folder or repository against the team's active style guide (Signal by default). Scores every file, ranks the files worst-first, counts findings per rule, and deep-reviews the worst files. Use whenever someone asks for a docs audit, a content inventory, a style compliance report, a docs health check, or "which docs need the most work", even if they name only a folder.
---

# Content audit

Score every file in a docs folder, then rank them so a team knows where to start. The audit has two layers: a fast deterministic pass over every file, and a judgment pass over the worst ones.

## 1. Agree on the scope

Confirm three things before you scan, and skip any that the person already answered:

- **Folder** – Which folder or repository to scan.
- **Files** – Which file patterns count as docs. The default is Markdown, MDX, and text files. A `.pakt.toml` file can set `[content] include`, `exclude`, and a `[content.types]` map from path patterns to content types.
- **Depth** – How many of the worst files get a judgment review. The default is five.

## 2. Load the guide

Follow `reference/active-guide.md` at the PAKT root. Name the guide and its version at the top of the report.

## 3. Run the deterministic pass

```bash
pakt audit <folder> --json --limit 0
```

Add `--glossary <file>` when the project has a glossary. The output holds a review of every file, with its detected content type, plus the finding count for each rule. Spot-check five detected content types. When a type looks wrong, suggest a `[content.types]` entry for `.pakt.toml`.

## 4. Run the judgment pass on the worst files

Take the worst files in the ranked list, up to the agreed depth. Review each one with the matching reviewer skill: `review-kb-article`, `review-release-notes`, `review-ui-microcopy`, or `review-api-docs`. For a file of type `general`, apply only the judgment rules of the guide.

## 5. Write the report

Save the report as `pakt-audit-<date>.md` in the folder that the person picks. Use this structure:

1. **Summary** – Files scanned, the verdict counts, and the three rules with the most findings.
2. **Files, worst first** – A table with the file, the content type, the verdict, the score, and the finding count.
3. **Findings per rule** – A table with the rule ID, the severity, the finding count, and the number of files affected.
4. **Deep reviews** – One full review report for each of the worst files.
5. **Next steps** – Fixes that clear the most findings at once, such as a glossary entry or a search-and-replace across files.

Mark every number that comes from the deterministic pass as such. Judgment scores apply only to the files that got a deep review.
