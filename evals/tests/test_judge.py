from pakt_evals.judge import build_judge_message, parse_judgment


def test_parse_valid_json():
    raw = '{"missing_facts": ["30 days"], "added_facts": [], "rationale": "Drops the window.", "meaning": 3, "readability": 5}'
    j = parse_judgment(raw)
    assert j.parse_ok and (j.meaning, j.readability) == (3, 5)
    assert j.missing_facts == ["30 days"]


def test_parse_fenced_and_surrounded_json():
    raw = 'Here you go:\n```json\n{"meaning": 4, "readability": 4}\n```\nThanks.'
    j = parse_judgment(raw)
    assert j.parse_ok and j.meaning == 4


def test_parse_rejects_out_of_range_and_non_integer():
    assert not parse_judgment('{"meaning": 6, "readability": 3}').parse_ok
    assert not parse_judgment('{"meaning": 3.5, "readability": 3}').parse_ok
    assert not parse_judgment('{"meaning": true, "readability": 3}').parse_ok
    j = parse_judgment('{"meaning": "4", "readability": 3}')
    assert not j.parse_ok and j.readability == 3 and "meaning" in j.error


def test_parse_accepts_integral_float():
    assert parse_judgment('{"meaning": 4.0, "readability": 5}').meaning == 4


def test_parse_failures_carry_an_error():
    assert parse_judgment("no json at all").error
    assert "invalid JSON" in parse_judgment("{not json}").error
    assert parse_judgment("[1, 2]").error


def test_judge_message_is_blind_to_variant():
    msg = build_judge_message("src", "cand")
    assert msg == "<source>\nsrc\n</source>\n\n<candidate>\ncand\n</candidate>"
