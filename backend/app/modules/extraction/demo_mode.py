"""`DEMO_MODE`: serve cached extractions instead of calling Qwen.

On demo day, on venue wifi, one of these will happen: the API is slow, the quota
is spent, or the network drops. With `DEMO_MODE=true` the extraction path never
touches the network — it replays a cached `ExtractionResult`, through the same
schema and into the same downstream code, in milliseconds instead of tens of
seconds.

Two other things this buys: the frontend can be developed without burning API
credits, and the demo video records at a watchable pace.

Cache lookup order for a document:

1. `sample-data/fixtures/extraction-cache/<document_id>.json` — a real cached
   extraction for that exact document. Populate this by running the live path
   once over the frozen sample data and saving what came back.
2. `sample-data/fixtures/extraction-result.json` — the checked-in template, with
   the requested document's identity written over it.

Say this out loud if a judge asks. "Demo mode replays cached extractions of our
sample data so the demo does not depend on venue wifi — here is the same flow
against the live API" is a stronger answer than a stalled progress bar.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from app.shared.schemas import DocumentType, ExtractionResult

__all__ = ["CACHE_DIR", "FIXTURES_DIR", "cached_extraction"]

logger = logging.getLogger(__name__)

#: demo_mode.py -> extraction -> modules -> app -> backend -> repo root
FIXTURES_DIR = Path(__file__).resolve().parents[4] / "sample-data" / "fixtures"
CACHE_DIR = FIXTURES_DIR / "extraction-cache"
TEMPLATE = FIXTURES_DIR / "extraction-result.json"


def cached_extraction(
    document_id: str,
    document_type: DocumentType,
    filename: str,
) -> ExtractionResult:
    """Return a cached `ExtractionResult` for this document.

    Raises:
        FileNotFoundError: Neither a per-document cache nor the template exists.
    """
    exact = CACHE_DIR / f"{document_id}.json"
    if exact.is_file():
        logger.info("DEMO_MODE: serving cached extraction for %s", document_id)
        return ExtractionResult.model_validate(json.loads(exact.read_text("utf-8")))

    if not TEMPLATE.is_file():
        raise FileNotFoundError(
            f"DEMO_MODE is on but there is no cached extraction for {document_id} "
            f"and no template at {TEMPLATE}"
        )

    logger.info(
        "DEMO_MODE: no cache for %s, replaying the template with its identity", document_id
    )
    payload = json.loads(TEMPLATE.read_text("utf-8"))
    payload["document_id"] = document_id
    payload["document_type"] = document_type.value
    payload["filename"] = filename
    for field in payload.get("fields", []):
        # Provenance must point at the document being asked about, or the
        # evidence viewer would open the wrong file.
        field["source"]["document_id"] = document_id
    return ExtractionResult.model_validate(payload)
