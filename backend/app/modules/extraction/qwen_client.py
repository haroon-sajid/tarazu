"""HTTP client for Qwen VL on Alibaba Cloud Model Studio (OpenAI-compatible mode).

Responsibilities, and nothing beyond them: build the request, survive timeouts
and rate limits, and hand back parsed JSON. It knows nothing about invoices,
confidence, or provenance — that mapping lives in `service.py`.

Two retry loops, deliberately separate because they fail for different reasons:

- **Transport retries** (`max_attempts`, exponential backoff) for timeouts,
  429s, and 5xx. The request was fine; the network or the quota was not.
- **One parse repair.** The call succeeded but the body was not valid JSON, so
  the model is shown its own output and asked to reply again. Exactly once — a
  model that cannot produce JSON twice will not manage it on the fifth try, and
  a demo does not have the seconds to spare.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Any

import httpx

from app.modules.extraction.prompts import repair_messages
from app.modules.extraction.settings import ExtractionSettings, get_settings

__all__ = [
    "QwenError",
    "QwenResponseError",
    "QwenTransportError",
    "QwenVisionClient",
]

logger = logging.getLogger(__name__)

#: Statuses worth retrying: rate limit, and anything the server blames on itself.
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
#: Never wait longer than this on a Retry-After, or a demo stalls on stage.
_MAX_RETRY_AFTER_SECONDS = 20.0


class QwenError(RuntimeError):
    """Any failure talking to Qwen."""


class QwenTransportError(QwenError):
    """The request never came back cleanly, after every retry."""


class QwenResponseError(QwenError):
    """The request came back, but the body was not usable JSON."""


def _strip_json(raw: str) -> str:
    """Pull the JSON object out of a reply that may be wrapped in prose or fences."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
        text = text.strip()
        if text.lower().startswith("json"):
            text = text[4:].lstrip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise QwenResponseError(f"no JSON object found in the reply: {raw[:200]!r}")
    return text[start : end + 1]


class QwenVisionClient:
    """A thin, retrying JSON client for the chat-completions endpoint.

    Args:
        settings: Module settings. Defaults to the environment.
        http_client: An `httpx.Client` to use. Injecting one is how the tests
            mount a `MockTransport`; leave it unset in production and the client
            builds its own.
        sleep: Injected so tests do not actually wait out the backoff.
    """

    def __init__(
        self,
        settings: ExtractionSettings | None = None,
        http_client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.settings = settings or get_settings()
        self._sleep = sleep
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(
            timeout=httpx.Timeout(
                self.settings.request_timeout_seconds, connect=10.0
            )
        )

    # -- lifecycle ---------------------------------------------------------- #

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def __enter__(self) -> QwenVisionClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # -- public ------------------------------------------------------------- #

    def complete_json(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Send a chat completion and return the parsed JSON object.

        Retries transport failures with exponential backoff, then repairs a
        single unparseable reply.

        Raises:
            QwenTransportError: Every attempt failed.
            QwenResponseError: Both the reply and its repair were unparseable.
        """
        model = model or self.settings.vl_model
        content = self._post(messages, model, temperature)
        try:
            return json.loads(_strip_json(content))
        except (QwenResponseError, json.JSONDecodeError) as error:
            # Python clears the `except` name on exit, so keep the text.
            parse_error = str(error)
            logger.warning("Qwen reply was not valid JSON, asking for a repair: %s", error)

        repaired = self._post(
            repair_messages(messages, content, parse_error), model, temperature
        )
        try:
            return json.loads(_strip_json(repaired))
        except (QwenResponseError, json.JSONDecodeError) as error:
            raise QwenResponseError(
                f"Qwen returned unparseable JSON twice: {error}"
            ) from error

    # -- internals ---------------------------------------------------------- #

    def _post(self, messages: list[dict], model: str, temperature: float) -> str:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            # Client data is sent for inference only. No training, no retention,
            # no feedback loop (reliability rule 6).
            "stream": False,
        }
        headers = {
            "Authorization": f"Bearer {self.settings.require_api_key()}",
            "Content-Type": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self.settings.max_attempts + 1):
            try:
                response = self._http.post(
                    self.settings.chat_completions_url, json=payload, headers=headers
                )
            except (httpx.TimeoutException, httpx.TransportError) as error:
                last_error = error
                self._wait(attempt, None, f"{type(error).__name__}: {error}")
                continue

            if response.status_code in _RETRYABLE_STATUSES:
                last_error = QwenTransportError(
                    f"HTTP {response.status_code} from Qwen: {response.text[:200]}"
                )
                self._wait(
                    attempt,
                    response.headers.get("retry-after"),
                    f"HTTP {response.status_code}",
                )
                continue

            if response.status_code >= 400:
                # 401, 403, 413, 422: retrying will not help. Fail loudly.
                raise QwenError(
                    f"HTTP {response.status_code} from Qwen: {response.text[:500]}"
                )

            return self._content(response)

        raise QwenTransportError(
            f"Qwen did not respond after {self.settings.max_attempts} attempts: {last_error}"
        )

    def _wait(self, attempt: int, retry_after: str | None, reason: str) -> None:
        """Back off before the next attempt, unless this was the last one."""
        if attempt >= self.settings.max_attempts:
            return
        delay = self.settings.backoff_base_seconds * (2 ** (attempt - 1))
        if retry_after:
            try:
                delay = min(float(retry_after), _MAX_RETRY_AFTER_SECONDS)
            except ValueError:
                pass  # A date-formatted Retry-After; the exponential delay stands.
        logger.warning(
            "Qwen attempt %s/%s failed (%s). Retrying in %.1fs.",
            attempt,
            self.settings.max_attempts,
            reason,
            delay,
        )
        self._sleep(delay)

    @staticmethod
    def _content(response: httpx.Response) -> str:
        try:
            body = response.json()
            return body["choices"][0]["message"]["content"]
        except (json.JSONDecodeError, KeyError, IndexError, TypeError) as error:
            raise QwenResponseError(
                f"unexpected response shape from Qwen: {response.text[:300]!r}"
            ) from error
