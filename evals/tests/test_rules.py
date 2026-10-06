import pytest

from pakt.styleguide import default_guide
from pakt_evals import rules as r
from pakt_evals.runner import content_type_for, load_testset


# ------------------------------------------------------------ sentence split

def test_split_keeps_abbreviations_and_versions_together():
    text = "Use a small value (e.g., 3) in v2.4.1 of the app. Then restart it."
    assert r.split_sentences(text) == [
        "Use a small value (e.g., 3) in v2.4.1 of the app.",
        "Then restart it.",
    ]


def test_split_treats_list_items_and_headings_as_units():
    text = "## Set up\n\n- Install the app\n- Sign in\n\nThis is prose."
    assert r.split_sentences(text) == ["Set up", "Install the app", "Sign in", "This is prose."]


def test_split_joins_hard_wrapped_lines():
    text = "This sentence wraps\nacross two lines. Second one."
    assert r.split_sentences(text) == ["This sentence wraps across two lines.", "Second one."]


def test_code_is_masked():
    text = "Run `git commit -m \"it's done\" --amend` now.\n\n```\ndon't -- touch\n```"
    masked = r.mask_code(text)
    assert "it's" not in masked and "don't" not in masked


def test_word_count_ignores_punctuation_and_counts_code_as_one():
    assert r.count_words(r.mask_code("Run `make build --verbose`, then wait—briefly.")) == 5


# ----------------------------------------------------------------- per rule

def test_sentence_length():
    short = "Click Save to keep your changes."
    long = " ".join(["word"] * 23) + "."
    assert r.check_sentence_length(short).passed
    res = r.check_sentence_length(long, max_words=22)
    assert not res.passed and res.violations[0].startswith("23 words")
    assert r.check_sentence_length(" ".join(["word"] * 22) + ".", max_words=22).passed


@pytest.mark.parametrize("text, ok", [
    ("The fix worked—barely.", True),
    ("The fix worked — barely.", False),
    ("The fix worked— barely.", False),
    ("The fix worked -- barely.", False),
    ("The fix worked - barely.", False),
    ("A—b—c is a parenthetical pair.", False),
    ("- **Term** - description", True),
    ("Use the `--force` flag.", True),
    ("A well-known issue.", True),
])
def test_em_dash(text, ok):
    assert r.check_em_dash(text).passed is ok


@pytest.mark.parametrize("text, ok", [
    ("Do not delete it.", True),
    ("Don't delete it.", False),
    ("It’s ready.", False),
    ("You'll see a prompt.", False),
    ("They're synced.", False),
    ("The user's settings are saved.", True),
    ("Run `don't-panic`.", True),
])
def test_contractions(text, ok):
    assert r.check_contractions(text).passed is ok


@pytest.mark.parametrize("text, ok", [
    ("Export to CSV, JSON, and XML.", True),
    ("Export to CSV, JSON and XML.", False),
    ("Pick red, green, blue or black.", False),
    ("Formats are .png, .jpg & .svg.", False),
    ("When the job fails, retries and alerts start.", True),
    ("If it fails, logs and metrics are kept.", True),
    ("Click Save, then close and reopen the file.", True),
    ("Logs and metrics are kept.", True),
    ("Choose a size, between S and M.", True),
    ("It may be too big, or unsupported (e.g., `.exe` or `.bat`).", True),
    ("It failed, and logs or traces are missing.", True),
    ("Use a word, such as `if` or `when`.", True),
])
def test_oxford_comma(text, ok):
    assert r.check_oxford_comma(text).passed is ok


@pytest.mark.parametrize("text, ok", [
    ("As mentioned above, guests cannot export.", False),
    ("The latter is faster.", False),
    ("Choose the second option.", False),
    ("Repeat the previous step.", False),
    ("The first step is to install the CLI.", True),
    ("See the next section for details.", True),
])
def test_back_references(text, ok):
    assert r.check_back_references(text).passed is ok


@pytest.mark.parametrize("text, ok", [
    ("Sure! Here is the rewrite.\n\nClick Save.", False),
    ("Here's the rewritten text: Click Save.", False),
    ("In this article, you learn to export.", False),
    ("We're super excited to ship 3.8.", False),
    ("Oops! The upload failed.", False),
    ("Click Save.\n\nLet me know if you need changes.", False),
    ("Click Save. Here is why: it keeps your work.", True),
    ("Export your notes from Settings.", True),
])
def test_preamble(text, ok):
    assert r.check_preamble(text).passed is ok


def test_filler():
    assert not r.check_filler("Please note that the link expires.").passed
    assert not r.check_filler("Open Settings in order to export.").passed
    assert r.check_filler("Open Settings to export.").passed


def test_hedging():
    assert not r.check_hedging("This is perhaps the best option.").passed
    assert not r.check_hedging("You might want to restart.").passed
    assert r.check_hedging("The file may exceed the limit.").passed


def test_second_person():
    assert not r.check_second_person("The user clicks Save.").passed
    assert not r.check_second_person("The developer should send a key.").passed
    assert r.check_second_person("Click Save.").passed
    assert r.check_second_person("The user list loads.").passed


def test_passive_voice_named_actor_always_fails():
    res = r.check_passive_voice("The file is uploaded by the client.", max_agentless=5)
    assert not res.passed and "named actor" in res.violations[0]


def test_passive_voice_allowance_for_agentless():
    one = "Your changes were not saved."
    two = "Your changes were not saved. The file was deleted."
    assert r.check_passive_voice(one, max_agentless=1).passed
    assert not r.check_passive_voice(two, max_agentless=1).passed


@pytest.mark.parametrize("text, hits", [
    ("The setting is enabled by default.", [("is enabled", False)]),
    ("Results are sorted by name.", [("are sorted", False)]),
    ("It was written by the team.", [("was written by the", True)]),
    ("The office is located in town.", []),
    ("We fixed the bug.", []),
    ("The key is not shown again.", [("is not shown", False)]),
])
def test_find_passives(text, hits):
    assert r.find_passives(text) == hits


def test_ampersand_ignores_code_and_entities():
    assert not r.check_ampersand("Contacts & companies").passed
    assert r.check_ampersand("Run `a && b` safely.").passed
    assert r.check_ampersand("Use &amp; in HTML.").passed


def test_bold_leadin():
    good = "- **Severity** – How serious an issue is."
    assert r.check_bold_leadin(good).passed and r.check_bold_leadin(good).applicable
    assert not r.check_bold_leadin("- **Severity:** How serious.").passed
    assert not r.check_bold_leadin("- **Severity**: How serious.").passed
    assert not r.check_bold_leadin("- **Severity** — How serious.").passed
    assert not r.check_bold_leadin("Plain prose.").applicable


@pytest.mark.parametrize("text, ok", [
    ("Use a format (e.g., PNG).", True),
    ("Use a format (e.g. PNG).", False),
    ("Use one value, i.e. the max.", False),
    ("Use one value (i.e., the max).", True),
])
def test_latin_abbreviations(text, ok):
    assert r.check_latin_abbreviations(text).passed is ok


def test_link_text():
    assert not r.check_link_text("For a template, [click here](https://example.com).").passed
    assert r.check_link_text("Download the [CSV import template](https://example.com).").passed
    assert r.check_link_text("The check flags `click here` and similar text.").passed


def test_strip_front_matter():
    assert r.strip_front_matter("---\nname: x\n---\nBody.") == "Body."
    assert r.strip_front_matter("Body --- text.") == "Body --- text."


def test_key_terms_case_insensitive_and_not_applicable_when_empty():
    assert r.check_key_terms("Returns `401`.", ["401"]).passed
    res = r.check_key_terms("Returns an error.", ["401", "Bearer"])
    assert not res.passed and len(res.violations) == 2
    assert not r.check_key_terms("anything", []).applicable


def test_run_rules_covers_every_guide_rule_once():
    guide = default_guide()
    names = [res.rule for res in r.run_rules("Click Save.", ["Save"])]
    assert names == [*(rule.id for rule in guide.checkable), "key_terms"]
    assert all(res.passed for res in r.run_rules("Click Save.", ["Save"]))


@pytest.mark.parametrize("text, ok, applicable", [
    ("## Set up single sign-on", True, True),
    ("## Set Up Single Sign-On", False, True),
    ("# Configure the API token", True, True),
    ("## Export Your Notes From Fernbook", False, True),
    ("Plain prose only.", True, False),
])
def test_heading_case(text, ok, applicable):
    res = r.check_heading_case(text)
    assert res.passed is ok and res.applicable is applicable


def test_banned_terms():
    res = r.check_banned_terms("Utilize the API in order to sync.", {"utilize": "use", "in order to": "to"})
    assert not res.passed and len(res.violations) == 2
    assert "(use 'use')" in res.violations[0]
    assert r.check_banned_terms("Run `utilize --help`.", ["utilize"]).passed
    assert not r.check_banned_terms("Anything.", {}).applicable


def test_sentence_stats():
    assert r.sentence_stats("One two three. Four five.") == {"sentences": 2, "mean_words": 2.5, "max_words": 3}
    assert r.sentence_stats("") == {"sentences": 0, "mean_words": 0.0, "max_words": 0}


def test_planted_failure_modes_are_detected_on_sources(cfg):
    """Every failure mode labeled on a test item must trip the matching rule on its source."""
    for item in load_testset(cfg.testset):
        ctype = content_type_for(cfg.guide, item.category)
        failed = {res.rule for res in r.run_rules(item.source, item.must_keep, cfg.guide, ctype) if not res.passed}
        assert set(item.failure_modes) == failed, item.id
