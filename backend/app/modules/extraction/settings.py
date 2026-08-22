"""Module-local configuration for `extraction/`, read from the environment.

Nothing here is hardcoded except safe defaults. Variable names are listed in
`.env.example`. Settings are read lazily so tests can set environment variables
without re-importing the module.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

__all__ = ["ExtractionSettings", "get_settings", "reset_settings_cache"]

#: Alibaba Cloud Model Studio, OpenAI-compatible mode. Use the `dashscope-intl`
#: host for accounts registered outside mainland China; swap to
#: `https://dashscope.aliyuncs.com/compatible-mode/v1` for a Beijing account.
DEFAULT_BASE_URL = "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
DEFAULT_VL_MODEL = "qwen-vl-max"

_TRUE = frozenset({"1", "true", "yes", "on"})


def _flag(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
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
class ExtractionSettings:
    api_key: str | None
    base_url: str
    vl_model: str
    second_opinion_model: str
    #: Verify any field whose confidence is at or below this level.
    verify_at_or_below: str
    demo_mode: bool
    page_image_dpi: int
    request_timeout_seconds: float
    #: Attempts per request, including the first. 3 means two retries.
    max_attempts: int
    #: Seconds before the first retry. Doubles each attempt.
    backoff_base_seconds: float

    @property
    def chat_completions_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "No Qwen API key. Set DASHSCOPE_API_KEY (or EXTRACTION_QWEN_API_KEY) "
                "in your .env, or set DEMO_MODE=true to serve cached extractions."
            )
        return self.api_key


@lru_cache(maxsize=1)
def get_settings() -> ExtractionSettings:
    """Read the extraction settings from the environment, once per process."""
    # DASHSCOPE_API_KEY is the name Alibaba's own tooling uses, so it is the one
    # people already have exported. EXTRACTION_QWEN_API_KEY is this repo's
    # per-module convention and wins if both are set.
    api_key = os.getenv("EXTRACTION_QWEN_API_KEY") or os.getenv("DASHSCOPE_API_KEY")
    vl_model = os.getenv("EXTRACTION_QWEN_VL_MODEL") or DEFAULT_VL_MODEL
    return ExtractionSettings(
        api_key=api_key or None,
        base_url=os.getenv("EXTRACTION_QWEN_API_BASE_URL") or DEFAULT_BASE_URL,
        vl_model=vl_model,
        second_opinion_model=os.getenv("EXTRACTION_SECOND_OPINION_MODEL") or vl_model,
        verify_at_or_below=(
            os.getenv("EXTRACTION_CONFIDENCE_THRESHOLD") or "low"
        ).strip().lower(),
        demo_mode=_flag("DEMO_MODE"),
        page_image_dpi=int(_number("EXTRACTION_PAGE_IMAGE_DPI", 200)),
        request_timeout_seconds=_number("EXTRACTION_REQUEST_TIMEOUT_SECONDS", 90.0),
        max_attempts=int(_number("EXTRACTION_MAX_ATTEMPTS", 3)),
        backoff_base_seconds=_number("EXTRACTION_BACKOFF_BASE_SECONDS", 1.0),
    )


def reset_settings_cache() -> None:
    """Drop the cached settings. For tests that change the environment."""
    get_settings.cache_clear()
