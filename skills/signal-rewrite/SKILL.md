---
name: signal-rewrite
description: Rewrite a messy documentation snippet, such as a KB article, release note, UI string, API doc, or error message, so it follows the team's active style guide (Signal by default) while keeping every fact. Use when asked to clean up, tighten, fix the style of, or "Signal-ify" docs text.
---

# Rewrite to the active guide

Rewrite the text that the person gives you so it follows the active style guide. Keep every fact, number, identifier, UI label, and constraint. Add nothing.

## 1. Load the guide

Follow `reference/active-guide.md` at the PAKT root, and read the active guide in full. Every style decision comes from that guide. When Signal is active, `prompts/v3-few-shot.md` at the PAKT root shows three worked examples of a messy input and its rewrite.

## 2. Rewrite

- **Keep the shape** – An error message stays an error message, and a UI string stays short. A release note keeps its version and sections.
- **Keep the facts** – Before you write, list every fact in the source. After you write, check that each one survived unchanged.
- **Ask about gaps** – When a sentence is ambiguous, ask instead of guessing.

## 3. Check the result

Save the rewrite to a file, and run `pakt lint <file>`. Fix every finding, then run the command again until it reports `clean`.

## Output

Return only the rewritten text. Explain the changes only when the person asks.
