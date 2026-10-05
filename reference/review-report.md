# Review report format

All four PAKT reviewer skills return the same report. The `pakt review` command writes the same shape, so a report from a skill and a report from the CLI compare directly.

## Scoring

Score four criteria from 1 to 10. The anchors for each level live in `prompts/review/v1.md` at the PAKT root. Read them before you score, and apply them strictly: 7 is solid professional work, and 9 or 10 is rare.

- **Style compliance** – How closely the text follows the active guide. Never score it above the `style_compliance` value from `pakt review`, because that value already counts the deterministic findings.
- **Technical clarity** – Whether every step, term, value, and behavior is accurate, specific, and unambiguous.
- **Structure** – Whether the text follows the conventions of its content type. Never score it above the `structure` value from `pakt review`.
- **Scannability** – Headings, lists, short sentences, front-loaded key facts, and correct Markdown.

## Verdict

- **Fail** – Any criterion scores 4 or lower.
- **Pass** – Every criterion scores 7 or higher, and no finding has error severity.
- **Revise** – Everything else.

## Template

Use this template. Keep the findings in document order.

```markdown
# Review: <file>

- **Verdict** – <pass, revise, or fail>
- **Score** – <total>/40
- **Content type** – <content type ID>
- **Style guide** – <guide name and version>

<One sentence that states the main problem, or why the text passes.>

## Scores

| Criterion | Score |
|---|---|
| Style compliance | <n>/10 |
| Technical clarity | <n>/10 |
| Structure | <n>/10 |
| Scannability | <n>/10 |

## Findings

- **<rule ID>** (<severity>, line <n>, <check, structure, or judgment>) – <what is wrong>
  - Quote: `<exact quote>`
  - Fix: <the rewritten text, or the concrete change>
```

## Finding rules

- **One finding per problem** – Report each occurrence once. Group repeats of the same rule on one line into one finding.
- **Rewrite, do not describe** – A fix shows the corrected text whenever the change fits on one line.
- **Most impactful first** – Within a line, list errors first, then warnings, then suggestions.
- **No padding** – Report only real problems. A clean section gets no finding.
