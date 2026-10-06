---
name: review-api-docs
description: Review API documentation, such as an endpoint reference page, authentication guide, or SDK reference, against the team's active style guide (Signal by default) and API reference conventions, and return a scored report with line-level findings and fixes. Use whenever someone asks to review, check, QA, or improve API docs, an endpoint page, a REST reference, or developer documentation, even if they never mention a style guide.
---

# Review API docs

Produce one scored report for one API reference page. The report follows `reference/review-report.md` at the PAKT root.

## 1. Load the guide and the conventions

Follow `reference/active-guide.md` at the PAKT root. Then read these files in full:

- **The guide** – The prose of the active guide, at the path that `pakt guide show` reports.
- **The effective rules** – The output of `pakt guide --rules --type api_doc --json`.
- **The API conventions** – The `api_doc` entry in the output of `pakt types --json`.

## 2. Run the deterministic pass

```bash
pakt review <file> --type api_doc --json
```

Keep every finding from this output. Each one is a fact that carries a rule ID and a line number.

## 3. Run the judgment pass

Read the page as a developer who must make a working call on the first try. Check every judgment rule from the guide and every API requirement without a `check`. These questions help:

- **Authentication** – Does the page say which credential the call needs, and where it goes?
- **Parameters** – Does the table give a type, a required flag, a default, and a range for every parameter?
- **Responses** – Does the page name every field of the success response?
- **Errors** – Does each error code come with its cause and the fix?
- **Example** – Would the example run as written, with only a key swapped in?
- **Literals** – Is every field name, header, path, and value in backticks?

When the page links to an OpenAPI file, compare the two, and report every mismatch as a technical clarity problem.

## 4. Score and report

Score the four criteria with the anchors in `prompts/review/v1.md`. Respect the caps from `reference/review-report.md`, and fill in its template. Offer to apply the fixes, but change the file only when the person asks.
