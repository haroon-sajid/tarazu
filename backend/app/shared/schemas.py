"""Tarazu — AI Audit Assistant: the shared data contracts.

This module is the single definition of every value that crosses a module
boundary. `extraction/`, `matching/`, `rules/`, `assistant/`, and `reports/` all
accept and return the models defined here, and nothing else.

Two invariants are enforced structurally rather than by convention, because they
are the product:

1. **Provenance is required** (reliability rule 3). Every AI-extracted value
   carries a `Provenance` naming the document and the exact location inside it.
   A `Provenance` that points nowhere fails validation.
2. **Extraction confidence and match strength are separate fields with separate
   types** (reliability rules 2 and 4). `ExtractedField.extraction_confidence`
   says how sure the vision model is that it read a value correctly.
   `MatchResult.match_strength` says how well two rows line up, and is computed
   by deterministic pandas with no AI involvement. There is deliberately no
   field named `confidence` anywhere in this file — collapsing the two would
   imply the AI scores the matches, which it never does.

See CLAUDE.md for the seven reliability rules and the module rules.
"""

from __future__ import annotations

from datetime import date as Date
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = [
    "ActorType",
    "Anomaly",
    "ApiKeyRecord",
    "ApiKeyScope",
    "AssistantAnswer",
    "AssistantCitation",
    "AssistantFact",
    "AssistantIntent",
    "AssistantLanguage",
    "AuditAction",
    "AuditReadiness",
    "AuditRecord",
    "BankTransaction",
    "BenfordDigit",
    "BenfordResult",
    "BoundingBox",
    "CaseRecord",
    "CaseStatus",
    "Confidence",
    "ConfidenceBreakdown",
    "CustomerSummary",
    "DashboardSummary",
    "DecisionBreakdown",
    "DocumentType",
    "ExtractedField",
    "ExtractedRow",
    "ExtractionResult",
    "FieldDisagreement",
    "Flag",
    "Invoice",
    "LedgerEntry",
    "MatchResult",
    "MONETARY_FIELD_NAMES",
    "MatchStatus",
    "MatchStrength",
    "MonthlyRevenue",
    "NextBestAction",
    "OrgRole",
    "Organization",
    "OrganizationMember",
    "OrgInvitation",
    "ProductRevenue",
    "Provenance",
    "ReadinessComponent",
    "RegionSummary",
    "ReportFormat",
    "ReportRecord",
    "ReviewDecision",
    "ReviewItem",
    "SalesAnalyticsResult",
    "SalesRecord",
    "SecondOpinion",
    "SeverityBreakdown",
    "Severity",
    "StatusBreakdown",
    "UserProfile",
    "VerificationOutcome",
]


# --------------------------------------------------------------------------- #
# Base
# --------------------------------------------------------------------------- #


class TarazuModel(BaseModel):
    """Base for every shared schema.

    `extra="forbid"` is deliberate: an unexpected key is almost always a
    contract drift between the backend, the frontend, and the fixtures, and it
    should fail loudly at the boundary rather than be silently dropped.
    """

    model_config = ConfigDict(extra="forbid")


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #


class Confidence(str, Enum):
    """How sure the AI is that it read a value correctly. AI output only."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchStrength(str, Enum):
    """How well two rows line up. Computed by deterministic code, never by AI.

    Intentionally a separate type from `Confidence` even though the values
    coincide, so the two can never be assigned to one another by accident.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class MatchStatus(str, Enum):
    MATCHED = "matched"
    PARTIAL = "partial"
    UNMATCHED = "unmatched"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DocumentType(str, Enum):
    BANK_STATEMENT = "bank_statement"
    INVOICE = "invoice"
    LEDGER = "ledger"
    #: A sales data export (Excel or CSV). Structured already, so it is read
    #: by pandas — the same no-AI path as the ledger — and feeds `analytics/`.
    SALES_DATA = "sales_data"


class ReviewDecision(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActorType(str, Enum):
    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"


class CaseStatus(str, Enum):
    """Where a case is in the pipeline."""

    UPLOADED = "uploaded"
    EXTRACTING = "extracting"
    #: Legacy. Cases uploaded before `matching/` and `rules/` existed were
    #: parked here; the pipeline no longer produces it, and the value stays so
    #: those rows still read. Re-upload such a case to process it.
    AWAITING_MATCHING = "awaiting_matching"
    READY_FOR_REVIEW = "ready_for_review"
    FAILED = "failed"


class AuditAction(str, Enum):
    CASE_CREATED = "case_created"
    #: A person corrected the engagement's editable facts (name, period).
    #: `detail` lists exactly what changed.
    CASE_UPDATED = "case_updated"
    #: A person removed the engagement. The working data went with it; this
    #: trail is append-only and outlives the case — including this record.
    CASE_DELETED = "case_deleted"
    DOCUMENT_UPLOADED = "document_uploaded"
    EXTRACTION_COMPLETED = "extraction_completed"
    SECOND_OPINION_COMPLETED = "second_opinion_completed"
    MATCHING_COMPLETED = "matching_completed"
    FLAG_RAISED = "flag_raised"
    ITEM_APPROVED = "item_approved"
    ITEM_REJECTED = "item_rejected"
    REPORT_GENERATED = "report_generated"
    #: A person asked the assistant something. `detail` carries the question.
    ASSISTANT_QUESTION_ASKED = "assistant_question_asked"
    #: The assistant answered. `actor_id` names what composed the answer —
    #: the deterministic composer, or the model that phrased it.
    ASSISTANT_ANSWERED = "assistant_answered"
    #: Deterministic sales analytics ran over one or more SALES_DATA documents.
    #: `actor_id` names who ran it — a person, an integration, or
    #: `analytics.service` when the pipeline ran it on upload.
    SALES_ANALYTICS_RUN = "sales_analytics_run"


class ReportFormat(str, Enum):
    PDF = "pdf"
    EXCEL = "excel"


class AssistantLanguage(str, Enum):
    ENGLISH = "en"
    URDU = "ur"


class AssistantIntent(str, Enum):
    """What the assistant understood the question to be asking for.

    The intent is decided by the module's deterministic planner and drives
    which deterministic query runs. It is recorded on the answer so a reader
    can see *how* the answer was produced, not only what it says.

    The first block reads the case's review queue — its results as a whole
    (`matches`, `flags`, `totals`…), one thing in it (`item`: a review item,
    ledger row, bank line, invoice, or flag named by its identifier), or one
    source of evidence (`invoices`, `bank`, `ledger`). The second block reads
    the rest of the engagement's persisted record — documents, extractions,
    decisions, reports, the trail, the case itself, and every case in the
    organization — read-only, through the same org-scoped repository the
    routes use. The last block neither reads nor computes: `concept` is
    answered from the reviewed glossary shipped in `concepts.py`, the same
    standing `help` has.
    """

    SUMMARY = "summary"
    MATCHES = "matches"
    UNMATCHED = "unmatched"
    MISSING_EVIDENCE = "missing_evidence"
    FLAGS = "flags"
    RULE = "rule"
    DUPLICATES = "duplicates"
    PARTY = "party"
    ITEM = "item"
    INVOICES = "invoices"
    BANK = "bank"
    LEDGER = "ledger"
    CONFIDENCE = "confidence"
    TOTALS = "totals"
    TOP_VENDORS = "top_vendors"
    LARGEST = "largest"
    COMPARE_MONTHS = "compare_months"
    SEARCH_AMOUNT = "search_amount"
    SEARCH_DATE = "search_date"
    BENFORD = "benford"
    CASE_INFO = "case_info"
    CASES = "cases"
    DOCUMENTS = "documents"
    EXTRACTIONS = "extractions"
    DECISIONS = "decisions"
    REPORTS = "reports"
    HISTORY = "history"
    CONCEPT = "concept"
    HELP = "help"
    UNSUPPORTED = "unsupported"
    UNKNOWN = "unknown"


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #

BoundingBox = Annotated[
    list[float],
    Field(
        min_length=4,
        max_length=4,
        description="Normalised [x0, y0, x1, y1] in 0..1 page space, origin top-left.",
    ),
]

#: A raw value as the vision model read it, before typing and normalisation.
RawValue = str | int | float | bool | None


class Provenance(TarazuModel):
    """Where a value came from: reliability rule 3, made structural.

    Two locator styles, because Tarazu reads two kinds of source:

    - **Documents** (bank statement PDFs, invoice PDFs and photos) locate by
      `page`, narrowed by `bbox` and/or `text_snippet`. This is what the
      evidence viewer highlights.
    - **Spreadsheets** (the ledger, read by pandas with no AI involved) locate
      by `row_number`.

    A `Provenance` must carry at least one locator, and page-based provenance
    must narrow to a region or a snippet — otherwise it cannot be shown to a
    human, which is the only reason it exists.
    """

    document_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    row_number: int | None = Field(default=None, ge=1)
    bbox: BoundingBox | None = None
    text_snippet: str | None = Field(default=None, min_length=1)

    @field_validator("bbox")
    @classmethod
    def _bbox_is_normalised(cls, value: list[float] | None) -> list[float] | None:
        if value is None:
            return value
        for name, coordinate in zip(("x0", "y0", "x1", "y1"), value):
            if not 0.0 <= coordinate <= 1.0:
                raise ValueError(
                    f"bbox {name}={coordinate} is outside the normalised 0..1 range"
                )
        x0, y0, x1, y1 = value
        if x1 <= x0 or y1 <= y0:
            raise ValueError("bbox must satisfy x0 < x1 and y0 < y1")
        return value

    @model_validator(mode="after")
    def _has_usable_locator(self) -> Provenance:
        if self.page is None and self.row_number is None:
            raise ValueError(
                "provenance needs a locator: page (documents) or row_number (spreadsheets)"
            )
        if self.page is not None and self.bbox is None and self.text_snippet is None:
            raise ValueError(
                "page provenance needs a bbox or a text_snippet so a human can be shown "
                "where the value came from"
            )
        return self


class ExtractedField(TarazuModel):
    """One value read out of a source document, with where it was read from.

    `value` is the raw reading. Typed and normalised values live on the row
    models below (`LedgerEntry.amount` and friends), which is where the
    deterministic modules read them from.

    Most fields come from the vision model, where `extraction_confidence`
    reflects genuine uncertainty. Spreadsheet cells read straight out of the
    ledger by pandas are also recorded here, always as `high`: there is no
    reading uncertainty when no model was involved.
    """

    field: str = Field(min_length=1)
    value: RawValue = None
    extraction_confidence: Confidence
    source: Provenance
    unreadable: bool = Field(
        default=False,
        description="Set when the model could not read the field. Never fabricate a value.",
    )

    @model_validator(mode="after")
    def _value_matches_readability(self) -> ExtractedField:
        if self.unreadable and self.value is not None:
            raise ValueError("an unreadable field must not carry a value")
        if not self.unreadable and self.value is None:
            raise ValueError(
                "a readable field must carry a value; set unreadable=true instead of emitting null"
            )
        return self


# --------------------------------------------------------------------------- #
# Rows
# --------------------------------------------------------------------------- #

Currency = Annotated[str, Field(pattern=r"^[A-Z]{3}$")]


class LedgerEntry(TarazuModel):
    """A row of the client's ledger (Excel or CSV).

    The ledger is already structured, so pandas reads it directly and no AI
    touches it. Its provenance is therefore a spreadsheet row, not a page region.
    """

    ledger_row_id: str = Field(min_length=1)
    date: Date
    amount: Decimal
    party_name: str = Field(min_length=1)
    description: str | None = None
    account_code: str | None = None
    currency: Currency = "PKR"
    source: Provenance


class BankTransaction(TarazuModel):
    """A transaction read out of the bank statement PDF."""

    bank_row_id: str = Field(min_length=1)
    date: Date
    amount: Decimal
    description: str = Field(min_length=1)
    balance: Decimal | None = None
    currency: Currency = "PKR"
    source: Provenance


class Invoice(TarazuModel):
    """An invoice read out of a PDF or a photo."""

    invoice_id: str = Field(min_length=1)
    invoice_number: str = Field(min_length=1)
    date: Date
    amount: Decimal
    party_name: str = Field(min_length=1)
    currency: Currency = "PKR"
    source: Provenance


# --------------------------------------------------------------------------- #
# Extraction output
# --------------------------------------------------------------------------- #


class FieldDisagreement(TarazuModel):
    """One field where the verification pass read something different."""

    field: str = Field(min_length=1)
    first_reading: RawValue = None
    second_reading: RawValue = None


class SecondOpinion(TarazuModel):
    """The result of re-reading an extraction to check it.

    The verifier reports agreement or disagreement. It deliberately has no field
    for a resolved value: when the two passes disagree, a human decides. Nothing
    in this schema lets the AI pick a winner.
    """

    ran: bool
    model: str = Field(min_length=1)
    agrees: bool
    disagreements: list[FieldDisagreement] = Field(default_factory=list)

    @model_validator(mode="after")
    def _disagreements_match_verdict(self) -> SecondOpinion:
        if self.agrees and self.disagreements:
            raise ValueError("a second opinion that agrees must list no disagreements")
        if not self.agrees and not self.disagreements:
            raise ValueError("a second opinion that disagrees must say which fields differ")
        return self


#: Field names that carry money. A disagreement on one of these always escalates.
MONETARY_FIELD_NAMES = frozenset(
    {"amount", "balance", "total", "subtotal", "tax", "grand_total", "net_amount"}
)


class VerificationOutcome(TarazuModel):
    """What the verification pass concluded about one page's extraction.

    The verifier reports agreement per field and nothing more. It has no way to
    record a winner: when the two readings differ on a monetary field, the only
    outcome the schema permits is escalation to a human.
    """

    second_opinion: SecondOpinion
    needs_human_review: bool

    @model_validator(mode="after")
    def _monetary_disagreement_escalates(self) -> VerificationOutcome:
        monetary = [
            disagreement.field
            for disagreement in self.second_opinion.disagreements
            if disagreement.field in MONETARY_FIELD_NAMES
        ]
        if monetary and not self.needs_human_review:
            raise ValueError(
                f"the two passes disagree on monetary field(s) {monetary}; "
                "needs_human_review must be true - the AI never picks a winner"
            )
        return self


class ExtractedRow(TarazuModel):
    """One repeating record inside a document: a line on a bank statement.

    An invoice carries its values once, at document level, so it uses
    `ExtractionResult.fields`. A statement carries dozens of transactions, so
    each becomes a row with its own fields and its own provenance.
    """

    row_id: str = Field(min_length=1)
    page: int = Field(ge=1)
    fields: list[ExtractedField] = Field(min_length=1)


class ExtractionResult(TarazuModel):
    """Everything the vision model read out of one document."""

    document_id: str = Field(min_length=1)
    document_type: DocumentType
    filename: str = Field(min_length=1)
    page_count: int = Field(ge=1)
    extracted_at: datetime
    model: str = Field(min_length=1)
    #: Document-level values (an invoice's total, its number, its party).
    fields: list[ExtractedField] = Field(default_factory=list)
    #: Repeating records (a statement's transactions). Empty for invoices.
    rows: list[ExtractedRow] = Field(default_factory=list)
    second_opinion: SecondOpinion | None = None
    needs_human_review: bool = False

    @model_validator(mode="after")
    def _something_was_read(self) -> ExtractionResult:
        if not self.fields and not self.rows:
            raise ValueError(
                "an extraction result must carry document-level fields or rows"
            )
        return self

    @model_validator(mode="after")
    def _disagreement_escalates(self) -> ExtractionResult:
        if (
            self.second_opinion is not None
            and not self.second_opinion.agrees
            and not self.needs_human_review
        ):
            raise ValueError(
                "a second opinion that disagrees must set needs_human_review; "
                "disagreement is never resolved by the AI"
            )
        return self


# --------------------------------------------------------------------------- #
# Deterministic output: matching and rules
# --------------------------------------------------------------------------- #


class MatchResult(TarazuModel):
    """One ledger row reconciled against the bank statement and the invoices.

    Produced by `modules/matching/` with pandas only. `match_strength` is a
    deterministic score, not an AI confidence — see the module docstring.
    """

    ledger_row_id: str = Field(min_length=1)
    bank_row_id: str | None = None
    invoice_id: str | None = None
    status: MatchStatus
    match_strength: MatchStrength
    reason: str = Field(
        min_length=1,
        description="Plain English, shown verbatim to the auditor.",
    )
    rule_id: str = Field(
        min_length=1,
        description="The deterministic rule that produced this result, e.g. 'exact-amount-exact-date'.",
    )

    @model_validator(mode="after")
    def _counterpart_matches_status(self) -> MatchResult:
        has_counterpart = bool(self.bank_row_id or self.invoice_id)
        if self.status is MatchStatus.UNMATCHED and has_counterpart:
            raise ValueError(
                "an unmatched result must not reference a bank row or an invoice"
            )
        if self.status is not MatchStatus.UNMATCHED and not has_counterpart:
            raise ValueError(
                f"a {self.status.value} result must reference a bank row or an invoice"
            )
        return self


class Flag(TarazuModel):
    """A red flag raised by `modules/rules/`. A suggestion, never a verdict."""

    flag_id: str = Field(min_length=1)
    rule_id: str = Field(min_length=1)
    severity: Severity
    explanation: str = Field(min_length=1)
    source_row_id: str = Field(min_length=1)
    related_row_ids: list[str] = Field(
        default_factory=list,
        description="Other rows involved, for rules that span rows (duplicates, structuring).",
    )
    source: Provenance | None = None


# --------------------------------------------------------------------------- #
# Sales analytics
#
# `modules/analytics/` is deterministic pandas, exactly like `matching/` and
# `rules/`: a sales export is already structured, so no model reads it and no
# model scores it. Every figure below is a sum or a count over the rows that
# were read, and the anomalies are rule findings — suggestions a human weighs,
# never verdicts.
# --------------------------------------------------------------------------- #


class SalesRecord(TarazuModel):
    """One sale row read out of a SALES_DATA export (Excel or CSV).

    Pandas reads it, the same no-AI path as the ledger, so its provenance is a
    spreadsheet row. `region` is optional because sales exports vary in what
    they carry; a record without one simply does not appear in
    `SalesAnalyticsResult.sales_by_region`.
    """

    sales_row_id: str = Field(min_length=1)
    date: Date
    amount: Decimal
    customer_name: str = Field(min_length=1)
    product: str = Field(min_length=1)
    region: str | None = None
    currency: Currency = "PKR"
    source: Provenance


#: A calendar month, `YYYY-MM`, the grain of `MonthlyRevenue`.
Month = Annotated[str, Field(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")]


class MonthlyRevenue(TarazuModel):
    """Revenue for one calendar month. Months are unique and ascending."""

    month: Month
    revenue: Decimal
    transaction_count: int = Field(ge=0)


class ProductRevenue(TarazuModel):
    """One product's revenue over the whole period, highest revenue first.

    `share` is percent of total revenue, rounded to two decimals. When total
    revenue is zero or negative it is 0.0 rather than a meaningless ratio.
    """

    product: str = Field(min_length=1)
    revenue: Decimal
    transaction_count: int = Field(ge=0)
    share: float


class CustomerSummary(TarazuModel):
    """One customer's revenue over the whole period. The top five, ranked."""

    customer_name: str = Field(min_length=1)
    revenue: Decimal
    transaction_count: int = Field(ge=0)
    share: float


class RegionSummary(TarazuModel):
    """One region's revenue over the whole period.

    Only records that carry a region are counted, so the region shares sum to
    less than the whole when some rows have none.
    """

    region: str = Field(min_length=1)
    revenue: Decimal
    transaction_count: int = Field(ge=0)
    share: float


class Anomaly(TarazuModel):
    """A pattern in the sales data worth a human's attention.

    Like a `Flag`, a suggestion and never a verdict. `kind` is one of the
    module's rule ids: `negative-amount`, `duplicate-transaction`,
    `revenue-spike`, `large-transaction`. Row-level anomalies name their row in
    `source_row_id` (and, for duplicates, the whole group in
    `related_row_ids`); month-level ones name the month instead.
    """

    anomaly_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    explanation: str = Field(min_length=1)
    source_row_id: str | None = None
    related_row_ids: list[str] = Field(default_factory=list)
    #: Set for month-level anomalies (`revenue-spike`); None for row-level ones.
    month: Month | None = None
    source: Provenance | None = None


class SalesAnalyticsResult(TarazuModel):
    """The whole sales-analytics readout for one case. Pure arithmetic, no AI.

    The breakdowns partition the records two ways — by month and by product —
    so each of those sums back to `total_revenue` and `record_count`, and the
    validators below hold the model to that. Regions cover only the records
    that carry one. `top_customers` is at most five, ranked by revenue.
    """

    record_count: int = Field(ge=0)
    period_start: Date | None = None
    period_end: Date | None = None
    total_revenue: Decimal
    monthly_revenue: list[MonthlyRevenue] = Field(default_factory=list)
    revenue_by_product: list[ProductRevenue] = Field(default_factory=list)
    top_customers: list[CustomerSummary] = Field(default_factory=list, max_length=5)
    sales_by_region: list[RegionSummary] = Field(default_factory=list)
    anomalies: list[Anomaly] = Field(default_factory=list)
    #: The documents the records were read from, so the readout names its
    #: sources. Derived from the records' provenance, sorted for determinism.
    document_ids: list[str] = Field(default_factory=list)
    generated_at: datetime

    @model_validator(mode="after")
    def _period_is_sane(self) -> SalesAnalyticsResult:
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end cannot precede period_start")
        return self

    @model_validator(mode="after")
    def _months_partition_the_records(self) -> SalesAnalyticsResult:
        months = [entry.month for entry in self.monthly_revenue]
        if months != sorted(set(months)):
            raise ValueError(
                "monthly_revenue must be one entry per month, ascending, no repeats"
            )
        revenue = sum((entry.revenue for entry in self.monthly_revenue), Decimal(0))
        if revenue != self.total_revenue:
            raise ValueError(
                f"monthly_revenue sums to {revenue}, but total_revenue is "
                f"{self.total_revenue}"
            )
        counted = sum(entry.transaction_count for entry in self.monthly_revenue)
        if counted != self.record_count:
            raise ValueError(
                f"monthly_revenue counts {counted} transactions, but record_count "
                f"is {self.record_count}"
            )
        return self

    @model_validator(mode="after")
    def _products_partition_the_records(self) -> SalesAnalyticsResult:
        products = [entry.product for entry in self.revenue_by_product]
        if len(set(products)) != len(products):
            raise ValueError("revenue_by_product must list each product once")
        revenue = sum((entry.revenue for entry in self.revenue_by_product), Decimal(0))
        if revenue != self.total_revenue:
            raise ValueError(
                f"revenue_by_product sums to {revenue}, but total_revenue is "
                f"{self.total_revenue}"
            )
        counted = sum(entry.transaction_count for entry in self.revenue_by_product)
        if counted != self.record_count:
            raise ValueError(
                f"revenue_by_product counts {counted} transactions, but "
                f"record_count is {self.record_count}"
            )
        return self

    @model_validator(mode="after")
    def _breakdowns_are_ranked_and_share_holds(self) -> SalesAnalyticsResult:
        """Ranking is part of the contract, and every share must follow.

        The ranked lists are what a chart renders; letting them arrive in an
        arbitrary order would make two results over the same records differ.
        The share check recomputes each percentage from the revenue it sits
        beside, so a number that does not follow from its own arithmetic is
        rejected rather than displayed.
        """
        total = self.total_revenue
        for name, summaries in (
            ("revenue_by_product", self.revenue_by_product),
            ("top_customers", self.top_customers),
            ("sales_by_region", self.sales_by_region),
        ):
            revenues = [summary.revenue for summary in summaries]
            if any(a < b for a, b in zip(revenues, revenues[1:])):
                raise ValueError(f"{name} must be ordered by revenue, highest first")
            for summary in summaries:
                expected = (
                    float(Decimal(100) * summary.revenue / total) if total > 0 else 0.0
                )
                if abs(summary.share - expected) > 0.01:
                    raise ValueError(
                        f"{name}: share {summary.share} does not follow from revenue "
                        f"{summary.revenue} of total {total}"
                    )
        regions = sum(
            entry.transaction_count for entry in self.sales_by_region
        )
        if regions > self.record_count:
            raise ValueError(
                f"sales_by_region counts {regions} transactions, more than the "
                f"{self.record_count} records analysed"
            )
        return self


# --------------------------------------------------------------------------- #
# Audit trail
# --------------------------------------------------------------------------- #


class AuditRecord(TarazuModel):
    """One append-only entry in the immutable audit trail (reliability rule 5).

    `frozen=True` stops this object being mutated in Python. The real guarantee
    is at the database: UPDATE and DELETE are revoked on the `audit_trail` table.
    Never add code that updates or deletes an audit record.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    audit_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    actor_type: ActorType
    actor_id: str = Field(min_length=1)
    action: AuditAction
    item_id: str | None = None
    detail: str | None = None
    occurred_at: datetime


# --------------------------------------------------------------------------- #
# The review screen
# --------------------------------------------------------------------------- #


class ReviewItem(TarazuModel):
    """One row of the human review screen: the unit a human approves or rejects.

    Carries both confidence fields side by side on purpose. `extraction_confidence`
    is the AI's, rolled up as the weakest reading behind this item.
    `match.match_strength` is deterministic. The UI shows them as two columns.
    """

    review_item_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    ledger_entry: LedgerEntry
    bank_transaction: BankTransaction | None = None
    invoice: Invoice | None = None
    match: MatchResult
    flags: list[Flag] = Field(default_factory=list)
    extraction_confidence: Confidence
    evidence: list[ExtractedField] = Field(default_factory=list)
    decision: ReviewDecision = ReviewDecision.PENDING
    decided_by: str | None = None
    decided_at: datetime | None = None
    rejection_reason: str | None = None

    @model_validator(mode="after")
    def _references_line_up(self) -> ReviewItem:
        if self.match.ledger_row_id != self.ledger_entry.ledger_row_id:
            raise ValueError("match.ledger_row_id does not match the attached ledger entry")
        if self.bank_transaction is not None:
            if self.match.bank_row_id != self.bank_transaction.bank_row_id:
                raise ValueError(
                    "match.bank_row_id does not match the attached bank transaction"
                )
        elif self.match.bank_row_id is not None:
            raise ValueError("match references a bank row that is not attached")
        if self.invoice is not None:
            if self.match.invoice_id != self.invoice.invoice_id:
                raise ValueError("match.invoice_id does not match the attached invoice")
        elif self.match.invoice_id is not None:
            raise ValueError("match references an invoice that is not attached")
        return self

    @model_validator(mode="after")
    def _decision_is_complete(self) -> ReviewItem:
        """Reliability rule 1: a decision exists only when a human made it."""
        decided = self.decision is not ReviewDecision.PENDING
        if decided and (self.decided_by is None or self.decided_at is None):
            raise ValueError(
                f"a {self.decision.value} item must record who decided it and when"
            )
        if not decided and (self.decided_by is not None or self.decided_at is not None):
            raise ValueError("a pending item must not record a decider")
        if self.decision is ReviewDecision.REJECTED and not self.rejection_reason:
            raise ValueError("a rejected item must record a rejection reason")
        if self.decision is not ReviewDecision.REJECTED and self.rejection_reason:
            raise ValueError("only a rejected item may carry a rejection reason")
        return self


# --------------------------------------------------------------------------- #
# Reports
# --------------------------------------------------------------------------- #


class ReportRecord(TarazuModel):
    """One generated report: the deliverable, and the record that it was made.

    Immutable once written, like the audit trail: a report is evidence of what
    the firm delivered on a date, and the stores refuse UPDATE and DELETE on
    the table. Regenerating produces a new record; it never rewrites one. The
    bytes live in document storage at the two paths, and their digests are
    kept here so a file handed to a client can be shown to be the one made.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    report_id: str = Field(min_length=1)
    case_id: str = Field(min_length=1)
    generated_by: str = Field(min_length=1)
    generated_at: datetime
    pdf_path: str = Field(min_length=1)
    excel_path: str = Field(min_length=1)
    pdf_sha256: str = Field(min_length=64, max_length=64)
    excel_sha256: str = Field(min_length=64, max_length=64)
    #: Counts at the moment of generation, so the history reads on its own.
    item_count: int = Field(ge=0)
    approved_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    pending_count: int = Field(ge=0)
    flag_count: int = Field(ge=0)
    audit_record_count: int = Field(ge=0)

    @model_validator(mode="after")
    def _decisions_add_up(self) -> ReportRecord:
        if self.approved_count + self.rejected_count + self.pending_count != self.item_count:
            raise ValueError("approved + rejected + pending must equal item_count")
        return self


# --------------------------------------------------------------------------- #
# The assistant
# --------------------------------------------------------------------------- #


class AssistantCitation(TarazuModel):
    """One place in the uploaded documents that an answer rests on."""

    document_id: str = Field(min_length=1)
    page: int | None = Field(default=None, ge=1)
    row_number: int | None = Field(default=None, ge=1)
    text_snippet: str | None = None
    #: The review item the citation belongs to, so the UI can link to it.
    review_item_id: str | None = None


class AssistantFact(TarazuModel):
    """One computed figure the answer was written from, shown beside it.

    Every number in an answer comes from one of these, and each of these was
    counted or summed by deterministic code over persisted results. The list
    is what lets a reader check the prose against the arithmetic.
    """

    label: str = Field(min_length=1)
    value: str = Field(min_length=1)


class AssistantAnswer(TarazuModel):
    """An answer from the assistant. Reliability rules 4 and 7, structurally.

    `answer_confidence` is the module's own confidence that the answer is a
    faithful readout of the case data — `high` for a direct readout, `medium`
    where interpretation was involved (a fuzzy party match, a small Benford
    sample), `low` for a refusal. It is deliberately not called `confidence`;
    see the module docstring for why that name is reserved.

    `grounded` is false when the question could not be answered from the
    uploaded documents. The text then says so, and cites nothing.
    """

    question: str = Field(min_length=1)
    language: AssistantLanguage
    intent: AssistantIntent
    text: str = Field(min_length=1)
    answer_confidence: Confidence
    grounded: bool
    citations: list[AssistantCitation] = Field(default_factory=list)
    facts: list[AssistantFact] = Field(default_factory=list)
    #: What produced the wording: "deterministic" or the model that phrased
    #: the computed facts. Never the thing that produced a number.
    composed_by: str = Field(min_length=1)

    @model_validator(mode="after")
    def _ungrounded_answers_cite_nothing(self) -> AssistantAnswer:
        if not self.grounded and self.citations:
            raise ValueError("an answer that is not grounded must not cite a document")
        return self


# --------------------------------------------------------------------------- #
# Tenancy
#
# A tenant is one accounting firm. Every tenant-owned row carries the `org_id`
# of the firm it belongs to, and nothing is ever read or written without one.
# --------------------------------------------------------------------------- #


class OrgRole(str, Enum):
    """What a member may do inside their own organization.

    Both roles see and decide on the same cases; `OWNER` is the identity that
    created the organization and the one a future member-management screen will
    check. Neither role reaches across an organization boundary.
    """

    OWNER = "owner"
    MEMBER = "member"


class Organization(TarazuModel):
    """One tenant: an accounting firm. The unit every row is scoped to."""

    org_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    created_at: datetime


class OrganizationMember(TarazuModel):
    """One user's membership of one organization.

    This is the only thing that grants access to a firm's data: a request is
    scoped by resolving the caller's `user_id` to a membership, never by any
    org id the client sends.
    """

    org_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    role: OrgRole = OrgRole.MEMBER
    created_at: datetime


class OrgInvitation(TarazuModel):
    """An open door into one organization, cut by its owner.

    The `code` is the credential: whoever presents it at signup joins
    `org_id` with `role` instead of founding a new firm. Single use —
    `accepted_at` closes the door — and revocable by deleting the row.
    `email` records who it was meant for; the code is what admits.
    """

    invite_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    email: str = Field(min_length=3, max_length=200)
    role: OrgRole = OrgRole.MEMBER
    code: str = Field(min_length=6)
    created_by: str = Field(min_length=1)
    created_at: datetime
    accepted_at: datetime | None = None
    accepted_by: str | None = None


# --------------------------------------------------------------------------- #
# API keys
#
# How an organization's own tooling — n8n, Zapier, a script — reaches Tarazu
# without a person signing in. A key belongs to one organization and reaches
# nothing outside it, exactly like the person who created it.
# --------------------------------------------------------------------------- #


class ApiKeyScope(str, Enum):
    """What a key may do. Least privilege: `READ` is the default on creation.

    Deliberately two coarse scopes rather than one per route. A scope the caller
    cannot reason about is a scope they will grant by accident.
    """

    #: Every GET: the review queue, the dashboard, an item's audit trail.
    READ = "read"
    #: Upload, approve, reject. Never key management — see `ApiKeyRecord`.
    WRITE = "write"


class ApiKeyRecord(TarazuModel):
    """One API key, as stored. **Never returned to a client as-is.**

    `key_hash` is in this model because the store needs it and because looking a
    key up *is* hashing it. It must not leave the backend: the API serves
    `ApiKeySummary` instead, which has no hash and no way to grow one, and the
    Postgres column privileges refuse `select (key_hash)` to every browser-facing
    role.

    The raw key exists exactly twice: in the response to the call that created
    it, and in the customer's own secret store. It is never written to the
    database and never logged.

    Revoking and deleting are different acts: `revoked_at` makes a key stop
    working while the row stays answerable; deletion removes the row for good
    and is confirmed as such in the UI.
    """

    key_id: str = Field(min_length=1)
    org_id: str = Field(min_length=1)
    #: The person accountable for what this key does. Cases it opens are created
    #: by them, and decisions it records are attributed to them.
    created_by: str = Field(min_length=1)
    #: A label the auditor chose, like "n8n integration".
    name: str = Field(min_length=1, max_length=100)
    #: The displayable, non-secret head of the key: `trz_live_` plus its first
    #: eight random characters. Enough to tell two keys apart in the UI and in
    #: the audit trail; nowhere near enough to reconstruct one.
    key_prefix: str = Field(min_length=1)
    #: SHA-256 of the raw key, hex. A key is 128 bits of `secrets` randomness,
    #: so there is nothing to brute-force and no reason for a slow KDF here.
    key_hash: str = Field(min_length=64, max_length=64)
    scopes: list[ApiKeyScope] = Field(min_length=1)
    last_used_at: datetime | None = None
    revoked_at: datetime | None = None
    created_at: datetime

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def allows(self, scope: ApiKeyScope) -> bool:
        return scope in self.scopes

    @field_validator("scopes")
    @classmethod
    def _unique_scopes(cls, scopes: list[ApiKeyScope]) -> list[ApiKeyScope]:
        """Deduplicate, and order them the same way every time they are stored."""
        return [scope for scope in ApiKeyScope if scope in set(scopes)]


class UserProfile(TarazuModel):
    """A person's editable profile, as stored. Keyed by user, not organization.

    Identity (email, password) lives in the identity store; this is the
    presentational layer on top — a display name, a picture, contact details.
    Nothing here participates in authentication or authorization, and none of
    it appears in the audit trail, which names users by id.

    `avatar` is a `data:image/...` URL, size-capped at the API boundary, so
    the picture works identically on both backing stores without a file
    storage dependency.
    """

    user_id: str = Field(min_length=1)
    full_name: str | None = None
    job_title: str | None = None
    phone: str | None = None
    avatar: str | None = None
    # -- personal (all optional, all cosmetic) ------------------------------ #
    gender: str | None = None
    date_of_birth: Date | None = None
    location: str | None = None
    # -- professional -------------------------------------------------------- #
    #: Practicing license or institute membership number (ICAP, ACCA, ...).
    license_number: str | None = None
    # -- preferences --------------------------------------------------------- #
    #: Preferred language for explanations: "en" or "ur".
    language: str | None = None
    notify_case_ready: bool = True
    notify_high_severity: bool = True
    notify_weekly_digest: bool = False
    updated_at: datetime | None = None


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #


class CaseRecord(TarazuModel):
    """One audit engagement: the documents, results, and decisions for a client."""

    case_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    period_start: Date | None = None
    period_end: Date | None = None
    status: CaseStatus = CaseStatus.UPLOADED
    created_by: str = Field(min_length=1)
    created_at: datetime
    #: Set when the pipeline could not finish, so the UI can say why.
    status_detail: str | None = None


class StatusBreakdown(TarazuModel):
    matched: int = Field(ge=0)
    partial: int = Field(ge=0)
    unmatched: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.matched + self.partial + self.unmatched


class DecisionBreakdown(TarazuModel):
    pending: int = Field(ge=0)
    approved: int = Field(ge=0)
    rejected: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.pending + self.approved + self.rejected


class ConfidenceBreakdown(TarazuModel):
    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.high + self.medium + self.low


class SeverityBreakdown(TarazuModel):
    high: int = Field(ge=0)
    medium: int = Field(ge=0)
    low: int = Field(ge=0)

    @property
    def total(self) -> int:
        return self.high + self.medium + self.low


class ReadinessComponent(TarazuModel):
    """One contributor to the audit-readiness score, with the counts behind it.

    The counts travel with the percentage so the UI can show "8 of 10 matched"
    rather than a bare number nobody can check.
    """

    percent: float = Field(ge=0.0, le=100.0)
    count: int = Field(ge=0)
    total: int = Field(ge=0)

    @classmethod
    def of(cls, count: int, total: int) -> ReadinessComponent:
        """Build a component, treating "nothing to do" as fully ready.

        A case with no flags scores 100 on flags-reviewed: there is nothing
        outstanding. Scoring it 0 would punish a clean ledger.
        """
        percent = 100.0 if total == 0 else round(100.0 * count / total, 1)
        return cls(percent=percent, count=count, total=total)

    @model_validator(mode="after")
    def _percent_matches_the_counts(self) -> ReadinessComponent:
        if self.count > self.total:
            raise ValueError(f"count {self.count} exceeds total {self.total}")
        expected = 100.0 if self.total == 0 else 100.0 * self.count / self.total
        if abs(self.percent - expected) > 0.05:
            raise ValueError(
                f"percent {self.percent} does not follow from {self.count}/{self.total}"
            )
        return self


class AuditReadiness(TarazuModel):
    """How ready this case is to be signed off, and why.

    Counted from persisted deterministic results. No part of this is estimated,
    weighted by a model, or influenced by an AI output.
    """

    score: int = Field(ge=0, le=100)
    #: Ledger rows with a confirmed counterpart.
    matched: ReadinessComponent
    #: Flags sitting on an item a human has already decided.
    flags_reviewed: ReadinessComponent
    #: Rows with no blank field and no unreadable extraction behind them.
    completeness: ReadinessComponent


class NextBestAction(TarazuModel):
    """One outstanding flag, reworded as something an auditor can go and do."""

    action: str = Field(min_length=1)
    severity: Severity
    rule_id: str = Field(min_length=1)
    #: So the UI can link the action straight to the row it is about.
    review_item_id: str = Field(min_length=1)
    party_name: str = Field(min_length=1)


class BenfordDigit(TarazuModel):
    digit: int = Field(ge=1, le=9)
    observed_count: int = Field(ge=0)
    observed_frequency: float = Field(ge=0.0, le=1.0)
    expected_frequency: float = Field(ge=0.0, le=1.0)
    deviation: float


class BenfordResult(TarazuModel):
    """First-digit distribution of the ledger amounts. Pure arithmetic, no AI."""

    sample_size: int = Field(ge=0)
    digits: list[BenfordDigit] = Field(min_length=9, max_length=9)
    chi_square: float = Field(ge=0.0)
    degrees_of_freedom: int = 8
    deviates_significantly: bool

    @model_validator(mode="after")
    def _digits_are_one_to_nine(self) -> BenfordResult:
        if [digit.digit for digit in self.digits] != list(range(1, 10)):
            raise ValueError("digits must be exactly 1..9, in order")
        counted = sum(digit.observed_count for digit in self.digits)
        if counted != self.sample_size:
            raise ValueError(
                f"observed counts sum to {counted}, but sample_size is {self.sample_size}"
            )
        return self


class DashboardSummary(TarazuModel):
    """The dashboard payload. Every number here is counted, never estimated by AI."""

    case_id: str = Field(min_length=1)
    client_name: str = Field(min_length=1)
    #: The span the ledger actually covers. Null until there is a ledger to span.
    period_start: Date | None = None
    period_end: Date | None = None
    total_review_items: int = Field(ge=0)
    match_status: StatusBreakdown
    decisions: DecisionBreakdown
    extraction_confidence: ConfidenceBreakdown
    flagged_item_count: int = Field(ge=0)
    total_flags: int = Field(ge=0)
    flags_by_severity: SeverityBreakdown
    benford: BenfordResult | None = None
    audit_readiness_score: AuditReadiness
    #: A one-line, computed statement of what the numbers above amount to.
    data_confidence: str = Field(min_length=1)
    #: Outstanding flags reworded as work, most severe first. At most five.
    next_best_actions: list[NextBestAction] = Field(default_factory=list, max_length=5)
    estimated_hours_saved: float = Field(ge=0.0)
    #: The sales-analytics readout when a SALES_DATA document was uploaded.
    #: None until the pipeline or a manual run has produced one.
    sales_analytics: SalesAnalyticsResult | None = None

    @model_validator(mode="after")
    def _breakdowns_add_up(self) -> DashboardSummary:
        for name, breakdown in (
            ("match_status", self.match_status),
            ("decisions", self.decisions),
            ("extraction_confidence", self.extraction_confidence),
        ):
            if breakdown.total != self.total_review_items:
                raise ValueError(
                    f"{name} sums to {breakdown.total}, but total_review_items is "
                    f"{self.total_review_items}"
                )
        if self.flags_by_severity.total != self.total_flags:
            raise ValueError(
                f"flags_by_severity sums to {self.flags_by_severity.total}, but "
                f"total_flags is {self.total_flags}"
            )
        if self.flagged_item_count > self.total_review_items:
            raise ValueError("flagged_item_count cannot exceed total_review_items")
        if (
            self.period_start is not None
            and self.period_end is not None
            and self.period_end < self.period_start
        ):
            raise ValueError("period_end cannot precede period_start")
        return self
