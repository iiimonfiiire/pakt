# Model providers

PAKT calls a model for the judgment layer of a review, for rewrites, and for the meaning judge. It can use three providers: Gemini, Groq, and Anthropic. This page explains how PAKT picks one, when it falls back to another, and how results record which model answered.

## Pick your providers

Put at least one API key in `.env`:

- **`GEMINI_API_KEY`** – A Google AI Studio key. The free tier works.
- **`GROQ_API_KEY`** – A Groq key. The free tier works.
- **`ANTHROPIC_API_KEY`** – An Anthropic key.

PAKT tries the providers in the order that `[providers] order` sets in `config.toml`. The default order is Gemini, then Groq, then Anthropic. A provider without a key drops out of the order. With only a Groq key, Groq serves every call.

To change the order for one run, set `PAKT_PROVIDERS`:

```bash
PAKT_PROVIDERS=groq,anthropic pakt review docs/kb/export.md --model
```

> **Warning:** Google may use inputs to the free Gemini tier to improve its models. Do not send confidential documents through a free-tier key, such as internal docs from an employer. Use a paid key, or another provider, for that content.

## Models per role

Each provider has one model for each of three roles:

- **`generator`** – Writes the rewrites in `pakt-eval run`.
- **`judge`** – Scores meaning and readability in `pakt-eval run` and `pakt-eval judge-check`.
- **`review`** – Runs the judgment layer in `pakt review --model` and `pakt-eval review-eval --mode model`.

Set them in `config.toml`:

```toml
[providers.gemini]
generator = "gemini-3.6-flash"
judge = "gemini-3.6-flash"
review = "gemini-3.6-flash"
```

To override one model, set `PAKT_<PROVIDER>_<ROLE>_MODEL` in `.env`, such as `PAKT_GROQ_JUDGE_MODEL`. The older `PAKT_GENERATOR_MODEL`, `PAKT_JUDGE_MODEL`, and `PAKT_REVIEW_MODEL` still work. They name Claude models, so they apply to Anthropic only.

> **Note:** Model IDs change often. Check each ID against the current model list of its provider before a real run. An unknown ID fails with an HTTP 404 error, and PAKT does not fall back.

## Fallback

Each provider first retries its own failures. The retry count and the timeout come from `max_retries` and `timeout` in `[providers]`. A provider that asks PAKT to wait longer than 30 seconds gets no more retries.

After the retries, the failure type decides what happens next:

- **Transient failure** – A rate limit (HTTP 429), a server error (HTTP 5xx), a timeout, or a lost connection. PAKT moves to the next provider in the order, with that provider's model for the same role.
- **Any other failure** – A bad key, a bad request, an unknown model, a blocked prompt, or an empty answer. PAKT stops and prints the error. A fallback here would hide a setup problem, so PAKT never takes one.

When every provider fails, PAKT stops and lists the reason from each one.

PAKT logs every fallback on stderr. The `pakt` CLI also logs which provider served each call. Set `PAKT_LOG_LEVEL` to `WARNING` for fallbacks only, or to `INFO` to see every call.

### Token limits on reasoning models

Some models think before they answer, such as recent Gemini Flash models and `openai/gpt-oss-120b`. Their thinking tokens count against `max_tokens`. When the thinking uses the whole limit, the answer comes back empty, and PAKT stops with an error. To fix it, raise `max_tokens` for the role, or cap the thinking:

- **Gemini** – Set `thinking_budget` in `[providers.gemini]`.
- **Groq** – Set `reasoning_effort` to `low` in `[providers.groq]`.

## The cache

PAKT caches every model response on disk. The provider is part of both the cache folder and the cache key, such as `evals/.cache/judgments/groq/`. A Gemini answer therefore never stands in for a Groq or Claude answer.

On a rerun, PAKT checks the cache of every provider in the chain before it calls any of them. Say a request fell back to Groq once. The next run reads the Groq answer from the cache, with no new call. With `--cache-only`, every provider in the order joins the chain, PAKT needs no key, and it makes no calls.

## What the results record

Every result names the provider and the model that answered:

- **`pakt review`** – The report shows a model line, and the JSON output has `provider` and `model` fields.
- **`pakt-eval run`** – Each line of `items.jsonl` has `gen_provider`, `gen_model`, `judge_provider`, and `judge_model`. The report header counts the answers from each provider and model, and shows the provider order.
- **`pakt-eval review-eval`** – The report header and `summary.json` count the answers from each provider and model.

A run that fell back partway shows more than one model in its header. Compare two runs only when their headers match.

## Cost

The prices in `config.toml` cover the Claude models only. A model without a price shows its cost as n/a, which includes every Gemini and Groq model. The free tiers cost nothing, but they have rate limits, and long runs can reach them.
