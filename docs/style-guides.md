# Plug in your own style guide

PAKT works with any style guide, and it holds no copy of one. It reads each guide from its source at run time. Signal is the default. This walkthrough shows how a team points PAKT at its own guide, and how PAKT decides which guide is active.

## What a guide is

A guide has two parts. They can live in a folder, in a Git repo, or behind a URL.

- **Prose** – The guide written for people, usually one Markdown file. The skills read all of it before they judge any text.
- **Rules pack** – The same guide as data, in a TOML file named `rules.toml` or `<name>.rules.toml`. Every rule has an ID, a severity, a section, and a one-line summary.

The two parts describe one guide, so keep them in step. When you change a rule in the prose, change its entry in the pack in the same commit. The Signal repo enforces this with a CI check that compares each section citation and the version with its prose.

No skill copies a rule into its own instructions. Every skill reads the active guide at run time, so a change to the guide reaches every skill at once.

## The rules pack

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
- **`summary`** – One line that a reviewer can apply. The full reasoning belongs in the prose.
- **`section`** – The heading in the prose that the rule comes from, such as `6. Voice and grammar > Sentence length`.
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

Each guide supplies the requirements for each type in its own rules pack. A requirement cites its guide section, like any rule. A subtype inherits the requirements of its parent and can replace them by ID:

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

## Guide sources

Point PAKT at a guide with a `[styleguide]` table in `.pakt.toml`, or with `--guide` on any command. Each source form has its own keys:

- **GitHub repo** – `source = "github:owner/repo@ref"`, or a `https://github.com/owner/repo/tree/<ref>` URL. Set `rules` to the pack path inside the repo. PAKT reads the prose path from the pack's `document` key.
- **Local folder** – `source = "style/house"`, relative to the project file. The folder holds the prose and the pack.
- **Prose URL** – `source = "https://..."`, with `rules` set to a local path or a URL. Add `sha256` to pin the prose.
- **Vale package** – `source = "vale:Google"`. Pin it with a release, as in `vale:Google@v0.6.1`, or with a zip URL. Add `prose` for the judgment layer, and `requirements` for content-type requirements.

Every form also accepts `prose`, to override the pack's prose path, and `requirements`, to add a requirements-only TOML file. That file holds `[content_types.<type>]` tables in the same format as a pack.

### Pins and the cache

PAKT stores fetched files in a cache folder. It uses `PAKT_CACHE_DIR` when set, then `$XDG_CACHE_HOME/pakt`, then `~/.cache/pakt`. The cache key is the source and its ref.

- **Pinned** – A commit SHA, a version tag, a `sha256` value, or a Vale release. PAKT fetches a pinned source once and never again, so it works offline afterward.
- **Unpinned** – A branch such as `main`, or a URL without `sha256`. PAKT refetches on every load, falls back to the cache when offline, and warns that results are not reproducible.
- **Offline** – Set `PAKT_OFFLINE=1` to forbid network access. PAKT then uses only the cache.

`pakt guide fetch` downloads the active guide and refreshes it even when pinned. `pakt guide show` prints the source, the pin state, and the cached paths. A private repo returns a 404 to an anonymous fetch. Clone it, and use the local folder as the source instead.

### Vale packages

A Vale source hands the deterministic layer to Vale. PAKT writes a `.vale.ini` in its cache, runs `vale sync` once per package, and runs `vale --output=JSON` on each file. Each alert becomes a finding:

- **Rule ID** – The Vale check name, such as `Google.Contractions`.
- **Severity** – Vale's `error`, `warning`, and `suggestion` map one to one.
- **Quote** – The matched text, or the line span when Vale reports no match.
- **Fix** – The replacement that Vale suggests, or a link to the rule.

Install Vale separately. PAKT names the install command when Vale is missing. Without `prose`, the judgment layer runs with the Vale findings alone. Each report then notes that the guide has no prose.

## Defaults that a guide can change

- **Release-note headings** – The Signal pack sets `required = true` on `rn_sections`, so every release note needs all six headings. The drafter writes "No changes in this release." under each empty one. Drop `required` to allow a shorter set.
- **Footnotes** – The `citations` check flags footnote markers, because Signal deprecates them for the web. Set `params = { footnotes = "allowed" }` on the rule, or on one content type through `by_type`, for print output.

## Create a guide

1. Copy the closest existing guide into your docs repository:

   ```bash
   pakt new-guide style/house --from signal
   ```

   The command copies the prose to `guide.md` and the pack to `rules.toml`.

2. Replace `style/house/guide.md` with your guide's text.
3. Edit `style/house/rules.toml`. Delete each rule that your guide does not have. Change thresholds to match your guide. Add judgment rules for the rest.
4. Point the project at the new guide in `.pakt.toml`:

   ```toml
   [styleguide]
   source = "style/house"
   ```

5. Check the result with `pakt guide --rules`. PAKT validates the rules file on load and names any unknown check, unknown severity, or duplicate ID.

The `pakt-setup` skill walks a team through these steps as an interview.

## How PAKT picks the active guide

PAKT checks four places in order, and the first match wins:

1. **Command option** – The `--guide` option on any `pakt` command. It takes any source string.
2. **Project file** – The `[styleguide]` table in the nearest `.pakt.toml`, searching from the current folder upward.
3. **PAKT config** – The `[styleguide]` table in `config.toml` at the PAKT root.
4. **Default** – Signal from its public repo, pinned to one commit.

Run `pakt guide show` to see which guide is active and which of these places chose it. The name `signal` works anywhere a source goes, as a short form of the default.

## The second example guide

Plainspoken lives in `styleguides/plainspoken/`, the only guide that PAKT bundles. It allows contractions, raises the sentence limit, bans three words through `banned_terms`, and renames the release-note sections. The test suite runs one text through both guides. It checks that the findings differ exactly as the two rules files predict.
