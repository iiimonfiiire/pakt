# Signal Manual of Style

*For clear, concise, and easy-to-scan writing.*

- **Last revision** – 23 Sep 2026

---

Signal is a style guide for UX writing, technical writing, and knowledge management work. It follows the Chicago Manual of Style's Notes-Bibliography tradition, adapted with modern technical layout conventions. Every rule below is the actual standard applied to any prose written under it.

## 1. Core identity and register

- **Baseline** – Follow the Chicago Manual of Style's Notes-Bibliography system, updated with modern technical layout sensibilities.
- **Formality** – Keep writing professional-polished: formal but human, in first-person voice, without slang or colloquialisms.
- **Humor** – Leave it out. Writing stays strictly substantive, with no jokes, asides, or rhetorical flourishes.
- **Directness** – Be blunt. State the conclusion first, name problems plainly, and minimize hedging language like "it could be argued" or "perhaps."

## 2. Punctuation and syntax

- **Oxford comma** – Use it every time; it is a must, with no exceptions, because ambiguity must be eliminated.
- **Semicolons** – Use them for genuine syntactic need, such as joining two independent clauses, never as decoration or a substitute for a period.
- **Em dash** – Reserve it for a mid-sentence tone shift only, and never add spaces around it. Correct: "the fix worked—barely." Incorrect: "the fix worked — barely."
- **En dash** – Use it after every bolded lead-in term that opens a bullet. A fragment or a full sentence may follow (see [Formatting and visual hierarchy](#9-formatting-and-visual-hierarchy)).
- **Ampersands** – Never use an ampersand in technical writing, not even in a title or heading, and spell out "and" instead. UX writing allows one narrow exception. An ampersand may appear in a title only as a deliberate branding choice, never as a default shorthand for "and."
- **Latin abbreviations** – Use "e.g." to introduce an example and "i.e." to restate something more precisely, never interchangeably. Follow each one with a comma: "large values (e.g., 10 or more)."

## 3. Attribution and citations

- **Footnotes** – Use numerical footnotes or endnotes for every sourced claim.
- **Inline citations** – Never use an intrusive inline parenthetical citation, such as `(Author, Year)`. Keep the main prose uninterrupted.

## 4. Numerals

- **Small numbers** – Spell out zero through nine as words in general prose.
- **Large numbers** – Use numerals for 10 and above.
- **Technical values** – Use numerals regardless of magnitude for any technical or measured value.
  - **Identifiers and addresses** – Port numbers, error and status codes, version numbers (port 8, error 4, v2).
  - **Severity and scoring** – Severity levels, CVSS scores, priority tiers (severity 3, CVSS 7).
  - **Steps and counts** – Step numbers referenced in prose, counts of technical objects (step 3, 5 open ports).
  - **Units of measurement** – Duration, size, or quantity with a unit attached (3 seconds, 4 GB, 2 retries).

## 5. Terminology

- **One term per concept** – Pick a single preferred term for each concept per document or project, and use it consistently. Never alternate between synonyms for the same thing.
- **Example** – Once a document picks "sign in" over "log in," or "user" over "customer," hold that choice for the rest of the document.

## 6. Voice and grammar

- **Voice** – Use active voice almost always. Switch to passive voice only when the actor is genuinely unknown or irrelevant to the point being made.
- **Second person** – Address the reader directly as "you" in any instructional sentence, not only numbered procedures. Pair it with an imperative verb: "Click Save," not "The user clicks Save."
- **Contractions** – Avoid them; always expand instead. Write "do not," not "don't," and "it is," not "it's."
- **Forbidden words** – Keep no fixed ban list. Default to plain, precise language over jargon or filler, and use a simpler word whenever it says the same thing.
- **Sentence length** – Cap every sentence at 20 to 22 words, and split anything longer.
- **Flow** – State things in the order the reader needs them, and never use a back-reference like "as mentioned above" or "the second option."
- **Sentence structure** – Default to full sentences in prose, paragraphs, user stories, and instructions. The one flexible case is a definition-style bullet, which pairs a bolded term with an en dash. What follows may be a fragment or a full sentence (see [Formatting and visual hierarchy](#9-formatting-and-visual-hierarchy)).

## 7. Technical conventions

- **Acronyms** – Spell out a technical term or acronym on first use. The one exception is a clearly expert or insider audience, where the acronym alone is fine.
- **Monospace** – Render code, commands, filenames, and other literal technical identifiers in backticks, with no exceptions.
- **UI elements** – Bold the name of a button, field, or menu path when referencing it in running text. Write "Click **Save**," not "Click Save" or "Click 'Save.'"
- **Security identifiers** – Use the full, canonical form every time. Write the complete CVE ID, never shortened (CVE-2024-12345). Pair a CVSS score with its version (CVSS v3.1: 7.5). Capitalize a severity tier as a proper noun (Critical, High, Medium, Low).
- **Emphasis** – Use bold and italics deliberately, not interchangeably.
  - **Bold** – A key term or defined concept that must survive a scan of the page.
  - *Italics* – Reserved for rare, genuine emphasis, a tone shift, or a foreign or technical term on first mention.

## 8. Capitalization

- **Titles and headings** – Always use sentence case: capitalize only the first word and any proper nouns, never Title Case.
- **Code-style casing** – Reserve `camelCase`, `PascalCase`, and `snake_case` for code identifiers only, such as variables, functions, and filenames. Never use them for prose headings or titles.
- **All caps** – Avoid it for emphasis. Use bold instead (see [Technical conventions](#7-technical-conventions)).

## 9. Formatting and visual hierarchy

- **Structure** – Use clear section headers and a logical hierarchy for high scannability, and avoid a dense wall of uninterrupted narrative text.
- **Lists** – Three formats, chosen by what the content actually is.
  - **Numbered lists** – Reserved strictly for sequences or ordered steps.
  - **Bulleted lists** – Everything else, regardless of length.
  - **Definition-style bullets** – A bolded lead-in term, an en dash, and the description that follows, either a fragment or a full sentence. Example: `**Severity** – The level of seriousness of an issue. Severity is measured by...`
- **Blockquotes and callouts** – Two distinct formats, not interchangeable.
  - **Blockquotes** (`>`) – Direct quotations only.
  - **Callouts** (`> **Note:**`, `> **Warning:**`) – Asides, caveats, or warnings that need to stand apart from the main flow.
- **Tables** – Use them only for genuinely tabular or numeric data, such as specs, datasets, or structured comparisons of hard values. Qualitative comparisons stay in prose or in bullets.
- **Hyperlinks** – Write descriptive link text that names the destination, and paraphrase freely to fit the sentence. Never use generic text like "click here."

## 10. Quick-reference checklist

- [ ] Oxford comma used throughout, with no exceptions
- [ ] Citations are numerical footnotes, not inline parentheticals
- [ ] Numbers zero through nine spelled out; 10 and above as numerals
- [ ] Technical or measured values (identifiers, severity, steps, units) stay numerals even under 10
- [ ] No ampersands in technical writing; UX titles get a branding exception only
- [ ] "e.g." and "i.e." used correctly, never interchangeably, each followed by a comma
- [ ] One preferred term per concept, held consistently within a document
- [ ] Titles and headings in sentence case, never Title Case or ALL CAPS
- [ ] `camelCase`, `PascalCase`, and `snake_case` reserved for code identifiers only
- [ ] Active voice, except where the actor is genuinely unknown
- [ ] Second-person imperative for any instructional sentence
- [ ] No contractions
- [ ] Sentences at 20 to 22 words or fewer; forward-flowing, with no back-references
- [ ] Full sentences by default; fragments only in definition-style bullets
- [ ] Bold lead-in bullets use an en dash, never a period, before the content
- [ ] Acronyms spelled out on first use for non-expert audiences
- [ ] All code, commands, and filenames in monospace
- [ ] UI element names bolded in running text
- [ ] Security identifiers in full canonical form (CVE ID, versioned CVSS score, capitalized severity tier)
- [ ] Bold for key terms; italics used sparingly
- [ ] Numbered lists only for sequences; bullets otherwise
- [ ] Blockquotes for quotes; callouts for asides and warnings
- [ ] Tables only for genuinely tabular or numeric data
- [ ] Hyperlink text is descriptive, never "click here"
- [ ] No humor; conclusion-first, blunt directness
