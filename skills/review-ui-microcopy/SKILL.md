---
name: review-ui-microcopy
description: Review UX microcopy, such as button labels, error messages, empty states, tooltips, toasts, placeholders, and dialog text, against the team's active style guide (Signal by default) and microcopy conventions, and return a scored report with string-level findings and rewrites. Use whenever someone asks to review, check, or improve UI strings, UI text, error messages, a locale or i18n JSON file, or product copy, even if they never mention a style guide.
---

# Review UX microcopy

Produce one scored report for one set of UI strings. The report follows `reference/review-report.md` at the PAKT root.

## Input formats

`pakt` reads two formats:

- **String files** – A JSON file of keys and strings, such as `en.json`. The key name decides the string type. A key that contains `button` holds a button label, and a key that contains `error` holds an error.
- **Kind lines** – A Markdown or text file with one string per line, written as `kind: text`. The kinds are `nav`, `button`, `label`, `title`, `placeholder`, `tooltip`, `toast`, `error`, `empty_state`, and `body`. Use `nav` for top-level navigation items and `title` for modal titles.

When the person pastes strings into the chat, save them in the kind-line format first.

## 1. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The `guide.md` of the active guide.
- **The effective rules** – The output of `pakt guide --rules --type ui_microcopy --json`. Several rules differ for microcopy, such as the sentence cap and contractions.
- **The microcopy conventions** – The `ui_microcopy` entry in the output of `pakt types --json`.

## 2. Run the deterministic pass

```bash
pakt review <file> --type ui_microcopy --json
```

The command checks each string on its own. Keep every finding. Each one is a fact that carries a rule ID and a line number.

## 3. Run the judgment pass

Read each string where it appears in the product, not as prose. Check every judgment rule from the guide and every microcopy requirement without a `check`. These questions help:

- **Errors** – Does each error say what happened and what to do next?
- **Buttons** – Does each button start with a verb that names the result of the click?
- **Tooltips** – Does each tooltip add something that the label does not already say?
- **Consistency** – Does one action keep one name across every string?

## 4. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. For every finding, give the full rewritten string as the fix.
