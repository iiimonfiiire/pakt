---
name: review-kb-article
description: Review a knowledge base article against the team's active style guide (Signal by default) and the structure of its subtype, and return a scored report with line-level findings and fixes. Covers task-based guides, conceptual articles, troubleshooting guides, product walkthroughs, concept guides, tutorials, and quickstarts. Use whenever someone asks to review, check, grade, edit, QA, or proofread a KB article, help doc, how-to, tutorial, quickstart, or support article, even if they never mention a style guide.
---

# Review a KB article

Produce one scored report for one KB article. The report follows `reference/review-report.md` at the PAKT root.

## 1. Identify the subtype

Every KB article belongs to one subtype, and each subtype has its own structure:

- **`kb_task`** – A task-based guide built around one goal and a procedure.
- **`kb_concept`** – A conceptual article that explains how something works.
- **`kb_troubleshooting`** – A troubleshooting guide for one problem.
- **`walkthrough`** – A product walkthrough that guides the reader through the UI.
- **`concept_guide`** – Learning content with theory and mental models only.
- **`tutorial`** – Learning content with an end-to-end, outcome-focused path.
- **`quickstart`** – Learning content with the fastest path to a result.

`pakt review` detects the subtype from front matter, the project's `.pakt.toml`, the path, and the content. Read the `content_type` field in its output. When the detected subtype looks wrong, say so, and rerun with `--type <subtype>`.

## 2. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The prose of the active guide, at the path that `pakt guide show` reports.
- **The effective rules** – The output of `pakt guide --rules --type <subtype> --json`. Sentence caps and other rules change by subtype.
- **The subtype conventions** – The entry for the subtype in the output of `pakt types --json`. A subtype inherits the requirements of `kb_article`.

## 3. Run the deterministic pass

```bash
pakt review <file> --json
```

Keep every finding from this output. Each one is a fact that carries a rule ID and a line number.

## 4. Run the judgment pass

Read the article as its reader would: someone in the middle of a task who wants the answer fast. Check every judgment rule for the subtype and every requirement without a `check`. These questions help:

- **Order** – Do the sections follow the order that the subtype requires, with nothing out of place?
- **Steps** – In a walkthrough, does each step match one UI state change, with closely coupled actions combined?
- **Verbs** – Does each step use the right verb for its interaction type?
- **Learning** – Does a tutorial open with measurable objectives? Does a concept guide stay free of steps? Does a quickstart skip theory?
- **Scope** – In a troubleshooting guide, does the fix depend on a version or a platform that the guide never names?
- **Terms** – Does one concept keep one name from start to finish?

## 5. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. Name the subtype in the report. Offer to apply the fixes, but change the file only when the person asks.
