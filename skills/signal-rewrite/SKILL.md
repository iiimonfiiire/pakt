---
name: signal-rewrite
description: Rewrite a messy documentation snippet (KB article, release note, UI string, API doc, or error message) into Signal style while keeping its meaning. Use when asked to clean up, tighten, or "Signal-ify" docs text.
---

# Signal rewrite

Rewrite the snippet the user gives you so it follows the Signal style guide. Keep every fact, number, identifier, UI label, and constraint. Add nothing.

## Rules

The canonical prompt lives in `prompts/v3-few-shot.md` in the PAKT repo, and it holds the full rule list and worked examples. The short version follows.

- **Sentences** – 20 words or fewer. Split anything longer.
- **Voice** – Active voice. Use passive voice only when the actor is unknown.
- **Reader** – Address the reader as "you" with an imperative verb.
- **Contractions** – Never. Write "do not" and "it is".
- **Lists in prose** – Always use the Oxford comma.
- **Em dash** – Only for a mid-sentence tone shift, with no spaces around it.
- **Flow** – No back-references such as `as mentioned above` or `the latter`.
- **Directness** – Conclusion or action first. No preambles, filler, or hedging.
- **Symbols** – No ampersands. Follow `e.g.` and `i.e.` with a comma.
- **Formatting** – Code, commands, and error codes in backticks. UI labels in bold. Numbered lists only for ordered steps.
- **Shape** – Keep the content type. An error message stays an error message.

## Output

Return only the rewritten snippet. Do not explain the changes unless the user asks.

After the rewrite, you can check it with the PAKT rule checker: `pakt-eval lint <file>`.
