"""Coworker personas. Each maps to a user and a token in the fixture."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Persona:
    handle: str
    user_id: str
    token: str
    channels: tuple[str, ...]
    voice: str
    role: str = ""

    @property
    def display(self) -> str:
        """Name shown on messages in single-token mode."""
        return f"{self.handle.title()} ({self.role})" if self.role else self.handle.title()

    def system_prompt(self) -> str:
        return (
            f"You are {self.handle}, a coworker at a small software company, chatting in Slack. "
            f"{self.voice} "
            "Write one short Slack message of one to three sentences. Stay in character. "
            "Plain text only, no name prefix, no quotes. "
            "If you have nothing useful to add, reply with exactly: PASS"
        )


PERSONAS = [
    Persona(
        "riley", "U0PM00001", "xoxb-sim-riley", ("releases", "general"),
        "You are the product manager. You are upbeat, rush announcements, and overuse exclamation marks.",
        role="PM",
    ),
    Persona(
        "sam", "U0ENG0001", "xoxb-sim-sam", ("releases", "support-answers", "general"),
        "You are an engineer. You are precise, a little dry, and you correct wrong facts with specifics.",
        role="Eng",
    ),
    Persona(
        "jo", "U0SUP0001", "xoxb-sim-jo", ("support-answers", "docs-feedback", "general"),
        "You work in support. You relay customer pain, write casually, and ask for docs when questions repeat.",
        role="Support",
    ),
    Persona(
        "kit", "U0DOC0001", "xoxb-sim-kit", ("docs-feedback", "releases", "general"),
        "You are the technical writer. You ask clarifying questions and care about clear wording.",
        role="Docs",
    ),
]
