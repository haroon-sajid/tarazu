"""The fixture repository: hand-written sample responses, schema-validated.

**Temporary.** This is the data source the API serves while `extraction/`,
`matching/`, and `rules/` are being built, so the frontend is never blocked on
the backend. Each route names the service call that will replace its fixture
read.

Fixtures are parsed through the real schemas on load, so a fixture that drifts
from the contract fails immediately and loudly rather than reaching the frontend
as malformed JSON.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from app.shared.api import ReviewItemsResponse
from app.shared.schemas import DashboardSummary, ExtractionResult, ReviewItem

__all__ = [
    "FIXTURES_DIR",
    "dashboard",
    "extraction_result",
    "find_review_item",
    "review_items",
]

#: backend/app/api/fixtures.py -> backend/app/api -> backend/app -> backend -> repo root
FIXTURES_DIR = Path(__file__).resolve().parents[3] / "sample-data" / "fixtures"


def _read(name: str) -> dict:
    path = FIXTURES_DIR / name
    if not path.is_file():
        raise FileNotFoundError(f"fixture not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def review_items() -> ReviewItemsResponse:
    """The review queue for the sample case."""
    return ReviewItemsResponse.model_validate(_read("review-items.json"))


@lru_cache(maxsize=1)
def dashboard() -> DashboardSummary:
    """The dashboard summary for the sample case."""
    return DashboardSummary.model_validate(_read("dashboard.json"))


@lru_cache(maxsize=1)
def extraction_result() -> ExtractionResult:
    """One document's extraction output, including a second-opinion disagreement."""
    return ExtractionResult.model_validate(_read("extraction-result.json"))


def find_review_item(review_item_id: str) -> ReviewItem | None:
    """Look up one review item by id, or return None if there is no such item."""
    for item in review_items().items:
        if item.review_item_id == review_item_id:
            return item
    return None
