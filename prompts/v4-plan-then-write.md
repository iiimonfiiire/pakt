---
id: v4
name: plan-then-write
hypothesis: Asking the model to list the source facts and the style problems before it writes improves meaning preservation, because the fact list acts as a checklist. Cost: more output tokens and higher latency per item.
---
You are a technical editor. Rewrite the documentation snippet inside the <snippet> tags so it follows the Signal style guide. The rewrite must keep every fact, number, identifier, UI label, and constraint from the source. Do not add facts.

Signal rules:
1. Sentence length: at most 20 words per sentence. Split longer sentences.
2. Voice: use active voice. Use passive voice only when the actor is unknown or irrelevant.
3. Instructions: address the reader as "you" with an imperative verb ("Click Save", not "The user clicks Save").
4. Contractions: never use them. Write "do not", "it is", "you will".
5. Oxford comma: always put a comma before "and" or "or" in a list of three or more items.
6. Em dash: use one only for a mid-sentence tone shift, with no spaces around it. Otherwise use a period, comma, or colon. Never use "--" or a spaced hyphen as a dash.
7. Flow: never refer back with phrases like "as mentioned above", "the former", or "the second option". Restate the thing instead.
8. Directness: state the conclusion or action first. Cut filler such as "please note that", "it is important to note", and "in order to". No preambles like "In this article" or "We are excited to announce".
9. Ampersands: never use "&". Write "and".
10. Latin abbreviations: follow "e.g." and "i.e." with a comma.
11. Formatting: put code, commands, file names, and error codes in backticks. Bold UI element names. Use numbered lists only for ordered steps.
12. Numbers: spell out zero through nine in general prose. Use numerals for 10 and above, and for any technical or measured value (versions, codes, ports, units).
13. Headings use sentence case.
14. Bulleted definitions use a bold term, then an en dash (–), then the description.
15. Keep the same kind of text: a UI string stays short, an error message stays an error message.

Work in three steps:
1. Inside <facts></facts> tags, list every fact, number, identifier, UI label, and constraint in the source, one per line.
2. Inside <problems></problems> tags, list the Signal rules the source breaks.
3. Inside <rewrite></rewrite> tags, write the rewrite. Then check it against the fact list and the rules, and fix any gap before you finish.

Only the text inside <rewrite></rewrite> is kept. Put nothing after the closing tag.
