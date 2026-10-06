---
name: review-gtm-brief
description: Review a GTM brief, launch brief, or product handoff brief for sales, support, and marketing against the team's active style guide (Signal by default) and its brief structure, and return a scored report with line-level findings and fixes. Use whenever someone asks to review, check, or tighten a launch brief, enablement brief, positioning doc, or product handoff, even if they never mention a style guide.
---

# Review a GTM brief

Produce one scored report for one go-to-market or product handoff brief. The report follows `reference/review-report.md` at the PAKT root.

## 1. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The `guide.md` of the active guide.
- **The effective rules** – The output of `pakt guide --rules --type gtm_brief --json`. A brief uses a corporate voice, so some rules differ from other content types.
- **The brief conventions** – The `gtm_brief` entry in the output of `pakt types --json`.

## 2. Run the deterministic pass

```bash
pakt review <file> --type gtm_brief --json
```

Keep every finding from this output. Each one is a fact that carries a rule ID and a line number.

## 3. Run the judgment pass

Read the brief as a sales or support lead who must explain the launch tomorrow. Check every judgment rule for this type and every brief requirement without a `check`. These questions help:

- **Persona** – Does the opening section name one specific persona and one concrete pain point?
- **Value** – Does the value proposition state an outcome for that persona, not a feature list?
- **Scope** – Can a reader tell exactly what ships, on which platforms, and what does not?
- **Limits** – Are the known limitations and edge cases specific enough to answer a customer question?
- **Branding** – Does every header and body sentence use the official product and feature names?

## 4. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. Offer to apply the fixes, but change the file only when the person asks.
