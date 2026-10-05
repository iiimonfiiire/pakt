# Glossary

Short definitions of the terms used in PAKT and its docs, in alphabetical order.

- **Anchor** – A written description of what one score level looks like in a rubric. Anchors make a score mean the same thing on every item.
- **Baseline** – The score of a reference point that a change must beat. In PAKT, the source baseline is how often the untouched messy snippets pass each rule.
- **Cache** – Saved model responses on disk. A repeated request reads the saved response instead of calling the API again.
- **Chain-of-thought** – A prompting technique that asks the model to reason step by step before it answers. The PAKT variant v4 uses a planning form of it.
- **Deterministic check** – A scorer that always gives the same result for the same input, such as a regex rule. It needs no model call.
- **Eval** – A repeatable test for a prompt or model. It runs fixed inputs, scores every output the same way, and compares the scores.
- **Few-shot prompting** – Including a small number of worked examples in the prompt to show the model what a good answer looks like.
- **Format compliance** – Whether an output follows the required structure. In PAKT, the rewrite must sit inside `<rewrite>` tags.
- **Golden set** – A test set where every input has a reference answer that a human approved. PAKT's test set has no reference answers, so it is not a golden set.
- **Hallucination** – Content that a model states as fact without support from its input. The judge reports these as `added_facts`.
- **Hypothesis** – A prediction, written before a run, about what a prompt change will do. A run can then confirm it or prove it wrong.
- **Latency** – The time a model call takes from request to response.
- **Leakage** – Test items appearing in the prompt or training data. Leakage inflates scores, because the model has seen the answers.
- **LLM-as-judge** – Using a language model to score another model's output against a rubric. It handles qualities that rules cannot, such as meaning, but it has biases.
- **Pass rate** – The share of items that pass a check, given as a percentage.
- **Pointwise scoring** – Scoring each output alone on a fixed scale. The alternative is pairwise scoring, which asks a judge to pick the better of two outputs.
- **Prompt variant** – One version of a prompt under test. PAKT keeps each variant in its own file under `prompts/`.
- **Regression** – A change that makes a result worse than it was before. Evals exist largely to catch regressions before users do.
- **Rubric** – The written scoring guide a judge follows. It names the dimensions, the scale, and an anchor for each level.
- **Self-preference bias** – A judge model's tendency to rate its own outputs, or outputs like its own, higher than others.
- **Spot check** – A small, hand-labeled sample used to test whether a judge agrees with human judgment.
- **Temperature** – A setting that controls output randomness. PAKT uses 0 to make runs as repeatable as possible.
- **Test set** – The fixed collection of inputs an eval runs on. PAKT's test set holds 25 messy documentation snippets.
- **Token** – The unit a model reads and writes, roughly four characters of English text. API cost is billed per token.
- **Zero-shot prompting** – Asking a model to do a task with instructions only, without examples.
