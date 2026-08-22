"""Shared data contracts for the whole app.

`schemas.py` holds the domain models that cross module boundaries; `api.py`
holds the HTTP request and response envelopes. Import from the submodules
directly (`from app.shared.schemas import MatchResult`) so it stays obvious
which layer a type belongs to.
"""
