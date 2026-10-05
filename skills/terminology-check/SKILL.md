---
name: terminology-check
description: Build and enforce a product glossary of preferred terms, banned variants, and definitions. Flags inconsistent terms, undefined jargon or acronyms, and banned words in docs and UI text. Use whenever someone asks about terminology, word choice consistency, a glossary or term base, "sign in vs log in" style questions, banned words, or jargon in their docs, even if they never say glossary.
---

# Terminology check

Keep one name for each concept across a product's docs and UI. The glossary is a TOML file that the team owns, and `pakt terms` enforces it.

## Glossary format

```toml
[[terms]]
preferred = "sign in"
variants = ["log in", "login", "log on"]
definition = "Open a session with your account."

[[banned]]
term = "simply"
reason = "It implies that the task is easy."
replacement = ""

[jargon]
allow = ["SCIM"]
```

- **`terms`** – One entry per concept. Every variant counts as a finding wherever it appears.
- **`banned`** – Words to remove everywhere. Each entry has a reason and an optional replacement.
- **`jargon.allow`** – Acronyms that the audience knows, so the check skips them.

Point `.pakt.toml` at the file with `[glossary] path = "glossary.toml"`.

## Build a glossary

1. Run `pakt terms --suggest <docs folder> --out glossary.toml`. The draft lists common variant families that the docs use, with counts, and every acronym with its count.
2. Ask the person to pick the preferred term for each family. Offer the choices as multiple choice, and show the counts, because the most common term is not always the right one.
3. Ask for a one-line definition of each product-specific term. Leave a definition empty rather than guess it.
4. Ask which acronyms the audience knows. Put those in `jargon.allow`.
5. Save the file, and add the glossary path to `.pakt.toml`.

## Enforce the glossary

1. Load the guide as `reference/active-guide.md` at the PAKT root describes, because the guide may set its own terminology rule.
2. Run `pakt terms <files> --json`. Each finding has a rule ID: `glossary_variant`, `glossary_inconsistent`, `glossary_banned`, or `glossary_undefined`.
3. Read the files for problems that the glossary cannot catch yet. Look for two words that name one concept, such as "workspace" and "project", when neither is in the glossary. Report each one as a candidate glossary entry, and label it **Inferred**, because the glossary does not confirm it.

## Report

List findings per file in document order, with the line, the quote, and the fix. End with a section called **Candidate glossary entries** that holds every inferred term pair. Change the docs or the glossary only when the person asks.
