# Plug in your own style guide

PAKT works with any style guide. Signal is the default. This walkthrough shows how a team swaps in its own guide, and how PAKT decides which guide is active.

## What a guide is

A guide is a folder with two files:

- **`guide.md`** – The guide in prose, written for people. The skills read all of it before they judge any text.
- **`rules.toml`** – The same guide as data. Every rule has an ID, a severity, a section, and a one-line summary.

The two files describe one guide, so keep them in step. When you change a rule in `guide.md`, change its entry in `rules.toml` in the same commit.

No skill copies a rule into its own instructions. Every skill reads the active guide at run time, so a change to the guide reaches every skill at once.

## The rules file

```toml
[guide]
id = "house"
name = "House style"
version = "2026-10"
document = "guide.md"

[[rules]]
id = "sentence_length"
section = "Voice"
severity = "error"
summary = "Keep sentences under 25 words."
fix = "Split the sentence."
check = "sentence_length"
params = { max_words = 24 }

[[rules]]
id = "plain_words"
severity = "error"
summary = "Never write 'utilize' or 'leverage'."
check = "banned_terms"
params = { terms = { "utilize" = "use", "leverage" = "use" } }

[[rules]]
id = "numerals"
severity = "suggestion"
summary = "Use numerals for every number."
```

Each field has one job:

- **`id`** – The rule ID that every finding cites. Keep it stable, because reports and labeled test sets refer to it.
- **`severity`** – One of `error`, `warning`, or `suggestion`. Severity drives the score and the verdict.
- **`summary`** – One line that a reviewer can apply. The full reasoning belongs in `guide.md`.
- **`fix`** – Optional. A generic fix that the CLI attaches to deterministic findings.
- **`check`** – Optional. The name of a deterministic check. A rule without a check needs judgment from Claude or a person.
- **`params`** – Optional. Settings for the check, such as a word limit or a list of banned terms.

## Deterministic checks

These checks exist. A guide can use any of them, under any rule ID, with its own parameters:

- **`sentence_length`** – Sentences over `max_words` words.
- **`contractions`** – Forms such as `don't` and `it's`.
- **`oxford_comma`** – Lists of three or more without the serial comma.
- **`em_dash`** – Spaced dashes, double hyphens, and stacked dashes.
- **`back_reference`** – Phrases such as `as mentioned above` and `the latter`.
- **`preamble`** – Throat-clearing openers and chatty closers.
- **`filler`** – Empty phrases such as `please note that`.
- **`passive_voice`** – Passives with a named actor, plus agentless passives over `max_agentless`.
- **`hedging`** – Softeners such as `perhaps` and `probably`.
- **`second_person`** – Instructions aimed at `the user` instead of `you`.
- **`ampersand`** – Any ampersand in prose.
- **`bold_leadin`** – A bold bullet lead-in followed by a colon or a period.
- **`latin_abbrev`** – `e.g.` or `i.e.` without a following comma.
- **`link_text`** – Generic link text such as `click here`.
- **`heading_case`** – Headings in Title Case. Words that the prose capitalizes mid-sentence count as names.
- **`banned_terms`** – Whole-word matches of the terms in `params.terms`.
- **`first_person`** – The pronouns `we`, `our`, and `I`.
- **`semicolons`** – Semicolons in prose. With `scope = "steps"`, only numbered steps count.
- **`citations`** – Inline parenthetical citations, plus footnote markers unless `footnotes = "allowed"`.
- **`all_caps`** – All-caps emphasis words such as `IMPORTANT`. Acronyms and HTTP methods pass.
- **`ui_case`** – Title Case in UI strings of the kinds in `params.kinds`. Navigation items pass.

Every check masks code blocks, inline code, and URLs first, so literal identifiers never trigger a prose rule.

## Rules that change by content type

A rule can behave differently for one content type. Add a `by_type` table under the rule:

```toml
[[rules]]
id = "sentence_length"
severity = "error"
summary = "Cap sentences by content type."
check = "sentence_length"
params = { max_words = 20 }
[rules.by_type.ui_microcopy]
params = { max_words = 12 }
[rules.by_type.conceptual]
params = { max_words = 28 }
```

An override can change `params`, `severity`, `summary`, or `check`. It can also set `enabled = false` to turn the rule off. Set `check = ""` to make a deterministic rule a judgment rule for that type.

The key of a `by_type` table names a content type, a parent type, or a tag. PAKT tries the exact type first, then the parent, then each tag. Run `pakt guide --rules --type <type>` to see the result for one type.

## Content types

The file `content-types.toml` defines the content types, their path hints, and their tags, such as `procedural`. A subtype also names its parent. The file holds no requirements.

Each guide supplies the requirements for each type in its own `rules.toml`. A requirement cites its guide section, like any rule. A subtype inherits the requirements of its parent and can replace them by ID:

```toml
[[content_types.release_note.requirements]]
id = "rn_sections"
section = "Release notes"
severity = "error"
summary = "Group changes under Added, Changed, Fixed, and Removed."
check = "allowed_headings"
params = { allowed = ["Added", "Changed", "Fixed", "Removed"], ordered = true }
```

The release-notes drafter reads the section names from this requirement. A renamed section therefore reaches the drafts too.

## Create a guide

1. Copy the closest bundled guide into your docs repository:

   ```bash
   pakt new-guide style/house --from signal
   ```

2. Replace `style/house/guide.md` with your guide's text.
3. Edit `style/house/rules.toml`. Delete each rule that your guide does not have. Change thresholds to match your guide. Add judgment rules for the rest.
4. Point the project at the new guide in `.pakt.toml`:

   ```toml
   [styleguide]
   path = "style/house"
   ```

5. Check the result with `pakt guide --rules`. PAKT validates the rules file on load and names any unknown check, unknown severity, or duplicate ID.

The `pakt-setup` skill walks a team through these steps as an interview.

## How PAKT picks the active guide

PAKT checks four places in order, and the first match wins:

1. **Command option** – The `--guide` option on any `pakt` command. It takes a bundled name or a folder path.
2. **Project file** – The `[styleguide]` table in the nearest `.pakt.toml`, searching from the current folder upward. Use `name` for a bundled guide, or `path` for a folder relative to the project file.
3. **PAKT config** – The `[styleguide] active` value in `config.toml` at the PAKT root.
4. **Default** – The bundled Signal guide.

Run `pakt guide` to see which guide is active and which of these places chose it.

## The second example guide

Plainspoken lives in `styleguides/plainspoken/`. It allows contractions, raises the sentence limit, bans three words through `banned_terms`, and renames the release-note sections. The test suite runs one text through both guides. It checks that the findings differ exactly as the two rules files predict.
