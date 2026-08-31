"""Module-local configuration for `assistant/`, read from the environment.

Variable names are listed in `.env.example`. Nothing is hardcoded except safe
defaults, and no value is ever logged.

The one setting that changes behaviour: **whether a model is used at all.**
The assistant's answers are computed and worded deterministically; a model,
when configured, only rephrases the computed facts into more natural prose,
and its output is checked against those facts before it is used. With no API
key, or with `DEMO_MODE=true`, the deterministic wording is the answer.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["AssistantSettings", "get_settings", "reset_settings_cache"]

DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_MODEL = "qwen-plus"

_TRUE = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in _TRUE


def _number(name: str, default: float) -> float:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class AssistantSettings:
    api_key: str | None
    base_url: str
    model: str
    demo_mode: bool
    #: `ASSISTANT_MODEL_PHRASING=false` keeps the deterministic wording even
    #: when a key is present — useful when comparing the two side by side.
    phrasing_enabled: bool
    request_timeout_seconds: float

    @property
    def uses_model(self) -> bool:
        return bool(self.api_key) and not self.demo_mode and self.phrasing_enabled

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


@lru_cache(maxsize=1)
def get_settings() -> AssistantSettings:
    return AssistantSettings(
        api_key=(os.getenv("ASSISTANT_QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or None),
        base_url=os.getenv("ASSISTANT_QWEN_API_BASE_URL") or DEFAULT_BASE_URL,
        model=os.getenv("ASSISTANT_QWEN_MODEL") or DEFAULT_MODEL,
        demo_mode=_flag("DEMO_MODE", False),
        phrasing_enabled=_flag("ASSISTANT_MODEL_PHRASING", True),
        request_timeout_seconds=_number("ASSISTANT_REQUEST_TIMEOUT_SECONDS", 30.0),
    )


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()
