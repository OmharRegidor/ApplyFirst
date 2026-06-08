"""LLM provider seam. V1 ships Gemini (free tier) via plain HTTP.

V2 can add a paid ClaudeProvider behind the same protocol with no engine change.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import httpx

_GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


@runtime_checkable
class LLMProvider(Protocol):
    name: str

    def generate(self, system: str, user: str) -> str:
        """Return the model's response text (expected to be JSON)."""
        ...


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str = "gemini-2.0-flash", timeout: float = 60.0) -> None:
        self.api_key = api_key
        self.model = model
        self._client = httpx.Client(timeout=timeout)

    def generate(self, system: str, user: str) -> str:
        url = _GEMINI_ENDPOINT.format(model=self.model)
        body = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0.4},
        }
        resp = self._client.post(url, params={"key": self.api_key}, json=body)
        resp.raise_for_status()
        data = resp.json()
        # candidates[0].content.parts[0].text
        return data["candidates"][0]["content"]["parts"][0]["text"]

    def close(self) -> None:
        self._client.close()
