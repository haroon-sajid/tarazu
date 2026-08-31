"""A minimal text-only chat client for Qwen on Model Studio (OpenAI-compatible).

Used for one thing: rephrasing facts the module has already computed. It is
deliberately not shared with `extraction/` — each AI-using module owns its own
client so either can be extracted into a service without dragging the other
along, and so a change to how one module talks to the model cannot quietly
change the other.

Client data is sent for inference only: no training, no retention, no
feedback loop (reliability rule 6). The request carries the computed facts and
the question, never the documents themselves.
"""

from __future__ import annotations

import json
import logging

import httpx

from app.modules.assistant.settings import AssistantSettings, get_settings

__all__ = ["AssistantModelError", "QwenChatClient"]

logger = logging.getLogger(__name__)


class AssistantModelError(RuntimeError):
    """The model could not be reached or did not answer usably."""


class QwenChatClient:
    """Send one chat completion and return the text. One retry on transport errors."""

    def __init__(
        self,
        settings: AssistantSettings | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(self.settings.request_timeout_seconds, connect=10.0)
        )

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> QwenChatClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def complete_text(self, messages: list[dict], temperature: float = 0.2) -> str:
        if not self.settings.api_key:
            raise AssistantModelError("no ASSISTANT_QWEN_API_KEY (or DASHSCOPE_API_KEY) is set")
        payload = {
            "model": self.settings.model,
            "messages": messages,
            "temperature": temperature,
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.api_key}",
            "Content-Type": "application/json",
        }
        last_error: Exception | None = None
        for attempt in (1, 2):
            try:
                response = self._http.post(
                    self.settings.chat_completions_url, json=payload, headers=headers
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                logger.warning("Assistant model attempt %s failed: %s", attempt, error)
                continue
            if response.status_code >= 400:
                raise AssistantModelError(
                    f"HTTP {response.status_code} from the model: {response.text[:300]}"
                )
            try:
                body = response.json()
                content = body["choices"][0]["message"]["content"]
            except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
                raise AssistantModelError(
                    f"unexpected response shape from the model: {response.text[:300]!r}"
                ) from error
            if not isinstance(content, str) or not content.strip():
                raise AssistantModelError("the model returned an empty answer")
            return content.strip()
        raise AssistantModelError(f"the model did not respond: {last_error}")
