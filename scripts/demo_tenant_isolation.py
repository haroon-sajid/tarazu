"""Two firms, one database, end to end: prove neither can see the other.

Runs the real app over the real local store — SQLite plus a directory of files,
no network, no mocks, no dependency overrides. Two auditors sign themselves up,
each opens a case, and then each one tries every route that could hand them the
other's data.

Run it from the repo root::

    python scripts/demo_tenant_isolation.py

By default it drives the app in-process, against a throwaway database under
`.local/demo-tenant-isolation/`, so there is nothing to start first. To run it
against a server you have already started, point it at one::

    uvicorn app.main:app --app-dir backend
    TARAZU_BASE_URL=http://localhost:8000 python scripts/demo_tenant_isolation.py

Every cross-tenant attempt must come back `404`, and none of them may mention
anything belonging to the other firm. A `403` would be a failure too: it would
confirm that the case exists, which is itself a disclosure.
"""

from __future__ import annotations

import io
import os
import shutil
import sys
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

WORKSPACE = REPO_ROOT / ".local" / "demo-tenant-isolation"


class Failure(AssertionError):
    """An isolation check did not hold. The demo stops here."""


# --------------------------------------------------------------------------- #
# Documents. Real files, so the real pipeline runs over them.
# --------------------------------------------------------------------------- #


def a_pdf(text: str) -> bytes:
    import pymupdf

    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 120), text, fontsize=16)
    data = document.tobytes()
    document.close()
    return data


def a_ledger(party: str, amount: int) -> bytes:
    import pandas as pd

    buffer = io.BytesIO()
    pd.DataFrame(
        {
            "Date": ["02/06/2026", "10/06/2026"],
            "Party Name": [party, "Al-Habib Stationers"],
            "Amount": [amount, 45_900],
            "Particulars": ["Yarn purchase", "Office supplies"],
        }
    ).to_excel(buffer, index=False)
    return buffer.getvalue()


# --------------------------------------------------------------------------- #
# Output
# --------------------------------------------------------------------------- #

CHECKS = {"passed": 0}


def heading(text: str) -> None:
    print(f"\n{text}\n{'-' * len(text)}")


def check(description: str, condition: bool, evidence: str = "") -> None:
    if not condition:
        raise Failure(f"{description}{f' — {evidence}' if evidence else ''}")
    CHECKS["passed"] += 1
    print(f"  ok   {description}" + (f"  [{evidence}]" if evidence else ""))


def note(text: str) -> None:
    print(f"       {text}")


def _anonymise(text: str, *identifiers: str) -> str:
    """Blank out the ids the caller supplied, so only the rest is compared."""
    for identifier in identifiers:
        text = text.replace(identifier, "<id>")
    return text


# --------------------------------------------------------------------------- #
# The demo
# --------------------------------------------------------------------------- #


class Firm:
    """One accounting firm: its auditor, its token, and its case."""

    def __init__(self, client, label: str, email: str, organization: str) -> None:
        self.client = client
        self.label = label
        self.email = email
        self.organization = organization
        self.password = "a-long-enough-password"
        self.token = ""
        self.org_id = ""
        self.user_id = ""
        self.case_id = ""

    @property
    def auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def sign_up(self) -> None:
        response = self.client.post(
            "/v1/auth/signup",
            json={
                "email": self.email,
                "password": self.password,
                "organization_name": self.organization,
            },
        )
        check(f"{self.label} signs up", response.status_code == 201, str(response.status_code))
        body = response.json()
        self.org_id, self.user_id = body["org_id"], body["user_id"]
        check(f"{self.label} owns {self.organization}", body["role"] == "owner", self.org_id)

    def sign_in(self) -> None:
        response = self.client.post(
            "/v1/auth/login", json={"email": self.email, "password": self.password}
        )
        check(f"{self.label} signs in", response.status_code == 200, str(response.status_code))
        self.token = response.json()["access_token"]

    def upload(self, client_name: str, party: str, amount: int) -> None:
        response = self.client.post(
            "/v1/upload",
            files=[
                ("bank_statement", ("statement.pdf", io.BytesIO(a_pdf("STATEMENT")))),
                ("ledger", ("ledger.xlsx", io.BytesIO(a_ledger(party, amount)))),
                ("invoices", ("invoice.pdf", io.BytesIO(a_pdf("INVOICE")))),
            ],
            data={"client_name": client_name},
            headers=self.auth,
        )
        check(
            f"{self.label} uploads a case for {client_name}",
            response.status_code == 201,
            f"{response.status_code} {response.text[:120]}",
        )
        self.case_id = response.json()["case_id"]

    def get(self, path: str, **params):
        return self.client.get(path, params=params or None, headers=self.auth)

    def post(self, path: str, json=None):
        return self.client.post(path, json=json or {}, headers=self.auth)


def run(client) -> int:
    a = Firm(client, "Firm A", f"partner-{uuid4().hex[:6]}@sethi-audit.pk", "Sethi Audit Associates")
    b = Firm(client, "Firm B", f"partner-{uuid4().hex[:6]}@karachi-audit.pk", "Karachi Audit LLP")

    heading("1. Two firms sign themselves up")
    for firm in (a, b):
        firm.sign_up()
        firm.sign_in()
    check("the two organizations are different", a.org_id != b.org_id, f"{a.org_id[:8]} vs {b.org_id[:8]}")

    heading("2. Each opens a case in the same database")
    a.upload("Sethi Textiles (Pvt) Ltd", "Gulberg Traders (Pvt) Ltd", 284_000)
    b.upload("Karachi Metals Ltd", "Korangi Steel Works", 913_000)
    check("the two cases are different", a.case_id != b.case_id, f"{a.case_id} vs {b.case_id}")

    heading("3. Each sees its own queue, and only its own")
    queues = {}
    for firm in (a, b):
        response = firm.get("/v1/review-items")
        check(f"{firm.label} lists its queue", response.status_code == 200)
        body = response.json()
        queues[firm.label] = body
        check(
            f"{firm.label}'s queue is its own case",
            body["case_id"] == firm.case_id,
            body["case_id"],
        )
        check(
            f"{firm.label}'s items all belong to that case",
            {item["case_id"] for item in body["items"]} == {firm.case_id},
        )

    heading("4. Firm B goes looking for Firm A's data")
    a_item = queues["Firm A"]["items"][0]["review_item_id"]
    #: A case and an item that have never existed anywhere. Every attempt below
    #: is made twice — once against A's real row, once against the fiction — and
    #: the two answers have to be indistinguishable. Echoing back the id the
    #: caller itself supplied is not a disclosure; answering differently is.
    ghost_case = "CASE-000000never"
    ghost_item = f"{ghost_case}-RI-0001"

    attempts = [
        (
            "the review queue",
            lambda case, item: b.get("/v1/review-items", case_id=case),
        ),
        ("the dashboard", lambda case, item: b.get("/v1/dashboard", case_id=case)),
        ("approve", lambda case, item: b.post(f"/v1/review-items/{item}/approve")),
        (
            "reject",
            lambda case, item: b.post(
                f"/v1/review-items/{item}/reject", {"reason": "not mine"}
            ),
        ),
        (
            "the item's audit trail",
            lambda case, item: b.get(f"/v1/review-items/{item}/audit"),
        ),
    ]
    for description, attempt in attempts:
        real = attempt(a.case_id, a_item)
        ghost = attempt(ghost_case, ghost_item)

        check(
            f"B on A's {description} is 404, not 403",
            real.status_code == 404,
            str(real.status_code),
        )
        check(
            f"B on A's {description} answers as it does for a case that never existed",
            real.status_code == ghost.status_code
            and _anonymise(real.text, a.case_id, a_item)
            == _anonymise(ghost.text, ghost_case, ghost_item),
        )
        leaks = [
            token
            for token in ("Sethi", "Gulberg", a.org_id, a.user_id)
            if token and token in real.text
        ]
        check(f"B on A's {description} leaks none of A's data", not leaks, ", ".join(leaks) or "clean")

    heading("5. A's data is untouched by the attempts")
    after = a.get("/v1/review-items").json()
    check(
        "A's queue is unchanged",
        after["total"] == queues["Firm A"]["total"],
        f"{after['total']} items",
    )
    pending = [item for item in after["items"] if item["decision"] == "pending"]
    check("A's item is still pending", any(item["review_item_id"] == a_item for item in pending))

    heading("6. A decides its own item, and only A can read the trail")
    decided = a.post(f"/v1/review-items/{a_item}/approve", {"note": "Vouched."})
    check("A approves its own item", decided.status_code == 200, str(decided.status_code))
    trail = a.get(f"/v1/review-items/{a_item}/audit")
    check("A reads the trail it just wrote", trail.status_code == 200)
    check("the trail records the approval", trail.json()[-1]["action"] == "item_approved")
    check(
        "B still cannot read that trail",
        b.get(f"/v1/review-items/{a_item}/audit").status_code == 404,
    )

    heading("7. Dashboards count only their own firm's work")
    for firm, expected in ((a, "Sethi Textiles (Pvt) Ltd"), (b, "Karachi Metals Ltd")):
        body = firm.get("/v1/dashboard").json()
        check(f"{firm.label}'s dashboard is its own client", body["client_name"] == expected)
        check(
            f"{firm.label}'s totals count its own queue",
            body["total_review_items"] == len(firm.get("/v1/review-items").json()["items"]),
        )

    print(f"\n{CHECKS['passed']} checks passed. Neither firm could reach the other's data.")
    return 0


def in_process_client():
    """The real app over a throwaway local store, driven in this process."""
    shutil.rmtree(WORKSPACE, ignore_errors=True)
    WORKSPACE.mkdir(parents=True, exist_ok=True)
    os.environ["LOCAL_DATABASE_PATH"] = str(WORKSPACE / "tarazu.db")
    os.environ["LOCAL_STORAGE_PATH"] = str(WORKSPACE / "documents")
    # Ignore any `.env`, and any Supabase credentials already exported. This
    # demo proves a property of the code, and it must not reach a real project
    # to do it — nor depend on one being configured.
    os.environ["TARAZU_DOTENV"] = "0"
    os.environ.pop("SUPABASE_URL", None)
    os.environ.pop("SUPABASE_SERVICE_ROLE_KEY", None)
    # Cached extractions rather than live Qwen calls: this demo is about
    # tenancy, and it must not need an API key or a network to prove it.
    os.environ["DEMO_MODE"] = "true"
    # Authentication stays fully on. The two firms present real tokens.
    os.environ["AUTH_ALLOW_DEV_USER"] = "false"

    from fastapi.testclient import TestClient

    from app.api.deps import reset_backends
    from app.core.config import reset_settings_cache
    from app.main import app

    reset_settings_cache()
    reset_backends()
    print(f"Local store: {WORKSPACE}")
    return TestClient(app)


def live_client(base_url: str):
    import httpx

    print(f"Live server: {base_url}")
    return httpx.Client(base_url=base_url, timeout=120.0)


def main() -> int:
    base_url = os.getenv("TARAZU_BASE_URL")
    client = live_client(base_url) if base_url else in_process_client()

    # `matching/` and `rules/` are Dev-D's and still raise NotImplementedError,
    # so a case would park at `awaiting_matching` with an empty queue and there
    # would be nothing to try to read across the boundary. In-process, stand-ins
    # are installed here — in the test suite, not in the application — exactly
    # as `backend/tests/conftest.py` does it. Against a live server the server
    # decides, so this is skipped and the demo needs those two functions to
    # exist.
    if not base_url:
        install_module_stand_ins()

    try:
        with client:
            return run(client)
    except Failure as failure:
        print(f"\nISOLATION FAILED: {failure}", file=sys.stderr)
        return 1


def install_module_stand_ins() -> None:
    from app.modules.matching import service as matching
    from app.modules.rules import service as rules
    from app.shared.schemas import Flag, MatchResult, MatchStatus, MatchStrength, Severity

    if getattr(matching.run_matching, "__module__", "") != matching.__name__:
        return

    def run_matching(ledger, bank, invoices):
        return [
            MatchResult(
                ledger_row_id=entry.ledger_row_id,
                status=MatchStatus.UNMATCHED,
                match_strength=MatchStrength.LOW,
                reason="Stand-in used by the tenancy demo; no real matching was performed.",
                rule_id="demo-stub",
            )
            for entry in ledger
        ]

    def evaluate_flags(ledger, matches, config):
        return [
            Flag(
                flag_id=f"FLG-{index:04d}",
                rule_id="round-number",
                severity=Severity.LOW,
                explanation=f"{entry.amount} is a round figure.",
                source_row_id=entry.ledger_row_id,
            )
            for index, entry in enumerate(ledger)
            if entry.amount % 1000 == 0
        ]

    matching.run_matching = run_matching
    rules.evaluate_flags = evaluate_flags
    note("matching/ and rules/ are not implemented yet; demo stand-ins installed.")


if __name__ == "__main__":
    raise SystemExit(main())
