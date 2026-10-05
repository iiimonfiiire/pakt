# The eval harness, explained

This walkthrough explains what the PAKT eval harness does and why it works the way it does. It assumes no prior experience with evals. Each section stands alone, so you can jump to the part you need.

## What an eval is

An eval is a repeatable test for a prompt. You run a prompt on a fixed set of inputs, score every output the same way, and compare the scores.

Evals replace gut feel. Without one, a prompt change looks better because the one example you tried looks better. With one, you see the effect across every input, including the ones the change broke.

This harness tests one task: rewriting a messy documentation snippet into [Signal style](https://github.com/iiimonfiiire/signal-style-guide). A good rewrite must do two things at once:

- **Follow the style** – Short sentences, active voice, no contractions, the Oxford comma, and the other Signal rules.
- **Keep the meaning** – Every fact, number, identifier, and constraint survives. Nothing new appears.

These two goals pull against each other. The easiest way to shorten a sentence is to drop a fact. The harness therefore scores both goals and reports them side by side.

## How a run works

One run follows five steps for every prompt variant and every test snippet.

1. **Generate** – Send the snippet to the generator model with the variant's prompt. The model returns a rewrite inside `<rewrite>` tags.
2. **Extract** – Pull the text out of the tags. A response without tags counts as a format failure, and the whole response gets scored.
3. **Check rules** – Run the deterministic rule checks on the rewrite.
4. **Judge** – Send the source and the rewrite to a second model, which scores meaning and readability.
5. **Report** – Combine every score into one report per run.

Steps 1 and 4 call the API, and the harness caches both on disk. For details, see [Caching, cost, and latency](#caching-cost-and-latency).

## The test set

The test set lives in `evals/data/testset.jsonl`, with one JSON record per line. The script `evals/tools/build_testset.py` generates the file and is the source of truth, so edit the script and rerun it.

There are 25 snippets, five per content type:

- **KB articles** – Help-center how-to text.
- **Release notes** – Version announcements and change lists.
- **UI microcopy** – Dialogs, form errors, and onboarding text.
- **API docs** – Authentication, pagination, rate limits, and similar reference text.
- **Error messages** – What a user sees when something fails.

All product names are fictional. The toolkit author wrote every snippet by hand to contain specific failures. These include long sentences, passive voice, back-references, spaced em dashes, and missing Oxford commas. Others are contractions, filler, preambles, and hedging.

Each record has five fields:

- **`id`** – A stable name such as `kb-01`.
- **`category`** – One of the five content types.
- **`source`** – The messy snippet.
- **`failure_modes`** – The rule names the source breaks. A unit test confirms the rule checks flag exactly these rules on each source.
- **`must_keep`** – Literal strings that must survive the rewrite, such as `401`, `Retry-After`, or `30 days`.

> **Note:** This test set is not a golden set. It has no reference rewrites, so no output gets compared against a "correct" answer. The judge and the rule checks score each output on its own terms.

### Why 25 items is enough to start, and its limits

Twenty-five items cost cents to run and are easy to read in full. That makes them good for spotting large differences between prompts.

They are too few for small differences. With 25 items, one item is 4 percentage points of pass rate. A gap of one or two items between variants is noise, not a finding. To detect smaller effects, grow the test set before you trust the result.

## The prompt variants

Each variant is a Markdown file in `prompts/`. A short header holds an `id`, a `name`, and a `hypothesis`. Everything after the header is the system prompt. The report records a short hash of each prompt, so you always know which version produced a result.

Every variant asks for the same output format, which keeps extraction and scoring identical across variants.

- **v1, zero-shot** – A two-sentence instruction that names the Signal style but gives no rules. Hypothesis: the model's generic idea of clear writing drifts from Signal, especially on contractions, dashes, and sentence length. This variant sets the floor.
- **v2, distilled rules** – Fifteen explicit, checkable rules taken from the Signal guide. Hypothesis: naming the rules closes most rule failures, and meaning stays level because no examples push the model toward a template.
- **v3, few-shot plus rules** – The v2 rules plus three worked examples of a messy input and a clean rewrite. Hypothesis: examples teach register and structure that rules describe poorly. Risk: the model copies example structure onto snippets where it does not fit.
- **v4, plan then write** – The v2 rules plus a three-step process: list the facts, list the rule problems, then write. Hypothesis: the fact list works as a checklist and improves meaning preservation. Cost: more output tokens and higher latency.

Two design choices matter for a fair comparison:

- **No leakage** – The few-shot examples in v3 are not in the test set. A prompt that contains test answers scores well for the wrong reason.
- **Rule margin** – The prompts ask for 20 words per sentence at most, while the check allows 22. The gap matches the Signal guide's own range of 20 to 22 words.

## The scorers

The harness uses two kinds of scorer. Rule checks are cheap, exact, and narrow. The judge is expensive, flexible, and noisy. Each covers the other's blind spots.

### Rule checks

The rule checks live in `evals/pakt_evals/rules.py`. Each check is a small function that takes text and returns a pass or fail with a list of violations. Before any check runs, the harness masks code blocks, inline code, and URLs. A literal command such as `git commit --amend` then never triggers a prose rule.

- **`sentence_length`** – Fails any sentence over 22 words. Limit: sentence splitting is heuristic and can misjudge unusual abbreviations.
- **`em_dash`** – Fails a spaced em dash. It also fails hyphens that stand in for a dash, and two em dashes in one sentence. Limit: the check cannot tell whether a single dash marks a real tone shift.
- **`contractions`** – Fails forms such as `don't`, `it's`, and `you'll`. Limit: it skips the ambiguous `'s` on nouns, because that is usually a possessive.
- **`oxford_comma`** – Fails lists such as `A, B and C`. Limit: one comma before `and` can start a list or end an introductory clause. The check skips segments that open with a clause word such as `if` or `when`, and it can still misfire.
- **`back_reference`** – Fails phrases such as `as mentioned above`, `the latter`, and `the previous step`.
- **`preamble`** – Fails assistant chatter and throat-clearing at the start or end, such as `Sure!` or `In this article`.
- **`filler`** – Fails empty phrases such as `please note that` and `in order to`.
- **`passive_voice`** – Signal allows passive voice only when the actor is unknown. A passive with a `by` phrase names its actor, so it always fails. Agentless passives get an allowance of one. Limit: the check matches a form of `be` plus a past participle, so it misses some passives and flags some adjectives.
- **`hedging`** – Fails softeners such as `perhaps`, `probably`, and `you might want to`. It deliberately allows `may`, which often states a real possibility.
- **`second_person`** – Fails instructions aimed at `the user` or `the developer` instead of `you`.
- **`ampersand`** – Fails any `&` in prose.
- **`bold_leadin`** – Fails a bold bullet lead-in followed by a colon or period instead of an en dash. It applies only when such a bullet exists.
- **`latin_abbrev`** – Fails `e.g.` or `i.e.` without a following comma. It applies only when one appears.
- **`link_text`** – Fails generic link text such as `click here`.
- **`key_terms`** – Fails when any `must_keep` string is missing from the output. This check is a cheap meaning signal, not a style rule.

Some Signal rules have no check, because a regex cannot judge them well. These include sentence case in headings, one term per concept, numeral style, and conclusion-first ordering. The judge's readability score covers some of this ground.

> **Warning:** A rule check proves only that a pattern is absent. A rewrite can pass every check and still be bad writing, or wrong.

### LLM-as-judge

The judge is a second model that reads the source and the rewrite, then returns a JSON object. The rubric lives in `prompts/judge/v1.md`.

The judge does three things in a fixed order:

1. Lists `missing_facts`, which are facts in the source that the rewrite dropped or changed.
2. Lists `added_facts`, which are claims in the rewrite that the source does not support.
3. Scores `meaning` and `readability` from 1 to 5, with a short rationale.

The fact lists come before the scores on purpose. Writing out the evidence first makes the score depend on that evidence, instead of on a first impression.

Each score level has an anchor, a written description of what that level looks like. For example, a meaning score of 3 means "one fact that matters is missing, changed, or added." Anchors make a 3 mean the same thing on every item.

The harness counts a rewrite as a meaning pass when its meaning score is 4 or higher. You can change this threshold in `config.toml`.

### Judge bias and how the harness limits it

LLM judges have known biases. The harness does not remove them. It reduces them and makes them visible.

- **Self-preference** – A model tends to rate its own writing higher. The judge is a different, larger model than the generator. Both come from the same vendor, so some shared taste remains.
- **Length bias** – Judges often reward longer answers. The rubric tells the judge not to reward length, and the readability anchors reward short, direct text.
- **Label bias** – A judge that knows which prompt produced an output may favor one. The judge sees only the source and the rewrite, never the variant name.
- **Drift and noise** – The judge runs at temperature 0 with a fixed rubric file. The report records the rubric hash, so a changed rubric is visible.
- **Unknown accuracy** – Nobody knows how often the judge is right until someone checks. The command `pakt-eval judge-check` runs the judge on eight hand-labeled pairs and reports how often it agrees with the labels.

The spot-check pairs live in `evals/data/judge_spot_check.jsonl`. They cover clear cases: a clean rewrite, a dropped fact, an invented fact, and a contradiction. Others cover a changed number and faithful but wordy text. The toolkit author wrote the labels. Relabel them yourself before you rely on the agreement number, because a judge can only agree with labels that are right.

Eight pairs are a smoke test, not a validation. A judge that fails them does not work. A judge that passes them still needs a larger check before you trust small score differences.

## Caching, cost, and latency

Every API response gets saved under `evals/.cache/`. The cache key is a hash of the full request: model, system prompt, user message, token limit, and temperature.

- **Reruns are free** – An identical request reads from disk and costs nothing.
- **Edits are safe** – Change one word in a prompt, and only that prompt's requests miss the cache.
- **Rescoring is free too** – Changing a rule check needs no new model calls. Run `pakt-eval run --cache-only` to rescore cached outputs without an API key.

The report shows cost as first incurred, so a fully cached rerun still reports what the original calls cost. Latency is the time each live call took, saved with the cached response.

Before a paid run, `pakt-eval run --dry-run` prints the number of calls and an estimated cost. The estimate assumes about four characters per token. For the full run of four variants and 25 items, the estimate is about 0.57 USD.

## How to read the report

Each run writes three files to `evals/results/<run-id>/`:

- **`report.md`** – The human-readable comparison.
- **`summary.json`** – The same metrics in machine-readable form.
- **`items.jsonl`** – One record per variant and item, with the output, every rule result, and the judge's response.

The report has four parts.

1. **Run details** – Models, prompt hashes, and the item count. Use them to tell runs apart.
2. **Headline** – One column per variant. The rows cover rule pass rates, the key-term pass rate, and judge scores. Further rows show format compliance, latency, tokens, and cost.
3. **Pass rate per rule** – One row per rule. The first column is the source baseline: how often the untouched messy snippets pass. Each cell also shows how many items the rule applied to.
4. **Worst failures** – The five worst variant and item pairs, with the source, the output, and the reasons.

Read the report in this order:

1. **Check meaning first** – A variant with great style scores and a low meaning pass rate is rewriting the facts away. That is a regression, not a win.
2. **Compare against the baseline** – A rule that the sources already pass 90 percent of the time cannot show much improvement.
3. **Look at the worst failures** – Averages hide patterns. The worst items show whether a failure is a rule problem, a prompt problem, or a broken check.
4. **Weigh cost and latency last** – A small quality gain may not justify double the tokens.

The worst-failure ranking scores each item as follows:

- **Meaning** – Two points per point lost below 5.
- **Readability** – One point per point lost below 5.
- **Style** – One point per failed style rule.
- **Key terms** – Two points if any `must_keep` string is missing.

The highest totals appear first. Meaning loss weighs most, because a wrong rewrite does more harm than an awkward one.

## How to add a test case

1. Open `evals/tools/build_testset.py`.
2. Add a record with a new `id`, a `category`, the `source` text, its `failure_modes`, and its `must_keep` strings.
3. Run `python evals/tools/build_testset.py` to regenerate the JSONL file.
4. Run `pytest`. The test suite checks that every `must_keep` string appears in the source. It also checks that the rule checks flag exactly the listed `failure_modes`.

If the rule checks disagree with your labels, decide which side is wrong. Fix the label if the source truly has the extra problem. Fix the check if it misfired, and add a unit test for the case.

## How to add a prompt variant

1. Copy an existing file in `prompts/`, such as `v2-rules.md`, to a new name such as `v5-short-rules.md`.
2. Give it a new `id`, a `name`, and a one-sentence `hypothesis`. Write the hypothesis before you run anything, so the result can prove it wrong.
3. Keep the `<rewrite>` output format, so extraction works.
4. Preview the run with `pakt-eval run --variants v2,v5 --dry-run`.
5. Run it and compare with `pakt-eval run --variants v2,v5`.

Change one thing per variant. If v5 changes both the rules and the examples, you cannot tell which change caused the result.

## Results

No real run has happened yet, so this section has no results. When a run exists, its report in `evals/results/` is the record. Summarize the headline numbers here and link to that report.
