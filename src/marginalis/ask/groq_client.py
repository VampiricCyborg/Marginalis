"""Minimal Groq chat-completions client (OpenAI-compatible) with retry-after backoff on 429."""

from __future__ import annotations

import logging
import os
import time

import requests
from dotenv import load_dotenv

log = logging.getLogger(__name__)

URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-120b"
MAX_ATTEMPTS = 5
MAX_WAIT_S = 90.0


class GroqError(RuntimeError):
    pass


def _retry_after(resp: requests.Response, attempt: int) -> float:
    """Seconds to wait: Groq's retry-after header when present, else exponential backoff."""
    header = resp.headers.get("retry-after")
    try:
        wait = float(header) if header is not None else 2.0 * 2 ** attempt
    except ValueError:
        wait = 2.0 * 2 ** attempt
    return min(max(wait, 0.5), MAX_WAIT_S)


class GroqClient:
    def __init__(self, api_key: str | None = None, model: str | None = None,
                 session: requests.Session | None = None, sleep=time.sleep):
        load_dotenv()
        self.api_key = (api_key or os.environ.get("GROQ_API_KEY", "")).strip()
        if not self.api_key:
            raise GroqError("GROQ_API_KEY is not set")
        self.model = model or os.environ.get("GROQ_MODEL", DEFAULT_MODEL)
        self.session = session or requests.Session()
        self.sleep = sleep

    def chat(self, messages: list[dict], tools: list[dict] | None = None, max_tokens: int = 900) -> dict:
        body = {"model": self.model, "messages": messages, "temperature": 0,
                "max_tokens": max_tokens, "reasoning_effort": "low"}
        if tools:
            body["tools"] = tools
            body["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        for attempt in range(MAX_ATTEMPTS):
            resp = self.session.post(URL, json=body, headers=headers, timeout=120)
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]
            if resp.status_code == 429 or resp.status_code >= 500:
                wait = _retry_after(resp, attempt)
                log.warning("Groq HTTP %d; waiting %.1fs (attempt %d)", resp.status_code, wait, attempt + 1)
                self.sleep(wait)
                continue
            raise GroqError(f"Groq HTTP {resp.status_code}: {resp.text[:300]}")
        raise GroqError(f"Groq still failing after {MAX_ATTEMPTS} attempts")
