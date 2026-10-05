---
name: review-kb-article
description: Review a knowledge base article, help-center page, how-to guide, tutorial, or troubleshooting page against the team's active style guide (Signal by default) and KB structure conventions, and return a scored report with line-level findings and fixes. Use whenever someone asks to review, check, grade, edit, QA, or proofread a KB article, help doc, guide, or support article, even if they never mention a style guide.
---

# Review a KB article

Produce one scored report for one KB article, guide, or troubleshooting page. The report follows `reference/review-report.md` at the PAKT root.

## 1. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The `guide.md` of the active guide.
- **The judgment rules** – The output of `pakt guide --rules --kind judgment --json`.
- **The KB conventions** – The `kb_article` entry in the output of `pakt types --json`.

## 2. Run the deterministic pass

```bash
pakt review <file> --type kb_article --json
```

Keep every finding from this output. Each one is a fact that carries a rule ID and a line number.

## 3. Run the judgment pass

Read the article as its reader would: someone in the middle of a task who wants the answer fast. Check every judgment rule from the guide and every KB requirement without a `check`. These questions help:

- **Outcome first** – Does the first sentence say what the reader will achieve or learn?
- **Prerequisites** – Does anything block the first step, such as a role, a plan, or a setting, without a mention before the steps?
- **Steps** – Does each numbered step hold one action, with the UI element that the reader acts on?
- **Confirmation** – After the last step, can the reader tell that it worked?
- **Troubleshooting shape** – On a troubleshooting page, are the symptom, the cause, the fix, and the confirmation all present?
- **Terms** – Does one concept keep one name from start to finish?

## 4. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. Offer to apply the fixes, but change the file only when the person asks.
