---
name: docs-gap-finder
description: Find missing or stale documentation by comparing tickets, support questions, changelogs, and release notes against the existing docs, and list every gap with a citation to the source item that revealed it. Use whenever someone asks what docs are missing, what to write next, where the docs fall short, which support questions have no article, or whether the docs cover a release.
---

# Find docs gaps

List the topics that the docs miss or that a change made stale. The hard rule: **every gap cites the source item that revealed it, and anything inferred carries an Inferred label.** Never smooth a guess into a confident claim. "Not confirmed" is a valid and frequent result.

## 1. Gather the sources

Ask for each source that is missing, in one round:

- **Docs** – The folder that holds the published docs.
- **Source items** – Support tickets, community questions, changelog entries, or release notes. `pakt gaps` reads JSONL or CSV with the fields `id`, `title`, `kind`, `body`, `date`, and `url`. Every item needs at least an `id` and a `title`.
- **Time window** – The period to cover, such as the last quarter.

Convert pasted or exported items to JSONL first. Keep the original ID of every item, so each citation leads back to it.

## 2. Run the candidate pass

```bash
pakt gaps --sources tickets.jsonl changelog.jsonl --docs <docs folder> --json
```

Each candidate has one of three statuses:

- **Missing** – No doc mentions the literal names in the item, such as a UI label, an error code, or an endpoint.
- **Partial** – Some literal names appear in the docs, and some appear nowhere.
- **Stale** – Every related doc was last updated before the change shipped. This status rests on dates, so it is always inferred.

A candidate built from title keywords alone also counts as inferred, because the item named nothing literal.

## 3. Confirm each candidate

Open the related docs, and search for synonyms of each missing term. For every candidate, decide one of these outcomes:

- **Confirmed gap** – The docs do not answer the question. Cite the source item and the docs you checked.
- **Covered** – A doc answers it under other words. Name the doc and the heading, and drop the gap.
- **Unconfirmed** – You cannot tell. Keep the gap, and label it **Inferred**.

Merge candidates that describe one topic, and keep every source citation in the merged gap.

## 4. Write the report

For each gap, give these fields:

- **Topic** – The missing or stale topic in a few words.
- **Status** – Missing, partial, or stale.
- **Sources** – Every source item ID, with its title, its date, and its link.
- **Evidence** – The literal names that no doc mentions, or the doc dates.
- **Basis** – Matched or Inferred, with one sentence of reasoning.
- **Suggested doc** – The content type and a working title.

Rank the gaps by the number of source items behind each one. End the report with a section called **Not verified**. List every inferred gap and every unconfirmed claim there, so the person can check them in one place.
