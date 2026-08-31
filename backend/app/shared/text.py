"""Deterministic text normalisation shared by the deterministic modules.

`matching/` and `rules/` both need to decide whether two party names refer to
the same business — "Gulberg Traders (Pvt) Ltd" in the ledger, "IBFT GULBERG
TRADERS PVT LTD" on the statement. Neither module may import the other's
internals, so the one normaliser they share lives here, beside the schemas
that cross the same boundary.

Pure string work, no I/O, no model. The same input always produces the same
output, which is what lets a match or a flag be reproduced from the report.
"""

from __future__ import annotations

import re

__all__ = ["normalise_party_name", "normalise_reference"]

#: Legal-form suffixes and filler that say nothing about *which* business a
#: name refers to. Stripping them is what makes "Karachi Packaging Co." and
#: "KARACHI PACKAGING CO" compare as the same party.
_STOP_TOKENS = frozenset(
    {
        "pvt", "private", "ltd", "limited", "llc", "inc", "incorporated",
        "co", "company", "corp", "corporation", "plc", "the", "and",
        "mr", "mrs", "ms", "m/s", "ms.", "messrs",
    }
)

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def normalise_party_name(name: str | None) -> str:
    """Lower-case a party name and drop punctuation and legal-form suffixes.

    "Hussain Brothers & Sons" and "IBFT HUSSAIN BROTHERS AND SONS" both reduce
    to a token sequence containing "hussain brothers sons"; the bank narration's
    extra tokens are left for a token-set comparison to ignore.
    """
    if not name:
        return ""
    lowered = name.lower().replace("&", " and ")
    tokens = [token for token in _NON_ALNUM.split(lowered) if token]
    kept = [token for token in tokens if token not in _STOP_TOKENS]
    return " ".join(kept)


def normalise_reference(reference: str | None) -> str:
    """Reduce an invoice or voucher number to its alphanumerics, upper-cased.

    "INV-2026-0087", "inv 2026/0087", and "INV20260087" all become
    "INV20260087", so a ledger description can be searched for the invoice it
    names without caring how the client typed the separators.
    """
    if not reference:
        return ""
    return re.sub(r"[^A-Z0-9]+", "", reference.upper())
