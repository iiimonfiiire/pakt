"""Text backends for the office bots."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Protocol


class Backend(Protocol):
    def chat(self, system: str, prompt: str) -> str: ...


class OllamaBackend:
    """Talks to an Ollama server. Works with any model it has pulled."""

    def __init__(self, base: str = "http://127.0.0.1:11434", model: str = "llama3.2:1b",
                 timeout: int = 300, max_tokens: int = 100):
        self.base, self.model, self.timeout, self.max_tokens = base.rstrip("/"), model, timeout, max_tokens

    def chat(self, system: str, prompt: str) -> str:
        body = {
            "model": self.model, "stream": False, "keep_alive": "30m",
            "options": {"num_predict": self.max_tokens, "temperature": 0.9},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        req = urllib.request.Request(
            f"{self.base}/api/chat", data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.load(resp)["message"]["content"]
        except urllib.error.URLError as e:
            raise ConnectionError(f"cannot reach Ollama at {self.base}: {e.reason}") from e


class ScriptedBackend:
    """Replays fixed lines. For tests and offline demos."""

    def __init__(self, lines: list[str]):
        self.lines = list(lines)
        self.i = 0
        self.prompts: list[str] = []

    def chat(self, system: str, prompt: str) -> str:
        self.prompts.append(prompt)
        line = self.lines[self.i % len(self.lines)]
        self.i += 1
        return line
