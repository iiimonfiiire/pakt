"""LLM-as-judge: a second model scores meaning preservation and readability."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field

from .llm import Completion, LLMClient

SCORE_FIELDS = ("meaning", "readability")


@dataclass
class Judgment:
    meaning: int | None = None
    readability: int | None = None
    missing_facts: list[str] = field(default_factory=list)
    added_facts: list[str] = field(default_factory=list)
    rationale: str = ""
    parse_ok: bool = False
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_judge_message(source: str, candidate: str) -> str:
    return (
        "<source>\n" + source.strip() + "\n</source>\n\n"
        "<candidate>\n" + candidate.strip() + "\n</candidate>"
    )


def _extract_json_object(raw: str) -> str | None:
    fenced = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.S)
    if fenced:
        return fenced.group(1)
    start, end = raw.find("{"), raw.rfind("}")
    if start == -1 or end <= start:
        return None
    return raw[start : end + 1]


def parse_judgment(raw: str) -> Judgment:
    blob = _extract_json_object(raw)
    if blob is None:
        return Judgment(error="no JSON object in judge response")
    try:
        data = json.loads(blob)
    except json.JSONDecodeError as exc:
        return Judgment(error=f"invalid JSON: {exc.msg}")
    if not isinstance(data, dict):
        return Judgment(error="judge JSON is not an object")

    j = Judgment(
        missing_facts=[str(x) for x in data.get("missing_facts", []) or []],
        added_facts=[str(x) for x in data.get("added_facts", []) or []],
        rationale=str(data.get("rationale", "")),
    )
    problems = []
    for name in SCORE_FIELDS:
        value = data.get(name)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or int(value) != value:
            problems.append(f"{name} is not an integer")
        elif not 1 <= value <= 5:
            problems.append(f"{name} out of range 1-5")
        else:
            setattr(j, name, int(value))
    j.parse_ok = not problems
    j.error = "; ".join(problems)
    return j


def judge(
    client: LLMClient,
    *,
    model: str,
    rubric: str,
    source: str,
    candidate: str,
    max_tokens: int,
    temperature: float | None,
) -> tuple[Judgment, Completion]:
    completion = client.complete(
        model=model,
        system=rubric,
        user=build_judge_message(source, candidate),
        max_tokens=max_tokens,
        temperature=temperature,
    )
    return parse_judgment(completion.text), completion
