"""`/v1/insights` and `/v1/compare` — the firm across all of its cases.

The dashboard answers "how is this engagement going". A firm runs many at once,
and the questions worth asking at that level are different ones: which parties
keep arriving in the review queue, which rules are doing the work, and whether
this period looks like the last one. These two routes answer those.

**Nothing here is modelled, scored, or estimated** (reliability rule 2). Every
figure is a count or a `Decimal` sum over review items that `matching/` and
`rules/` already produced and that a human is already deciding on — the same
numbers `GET /v1/dashboard` shows, grouped by party, by rule, by month, and by
firm instead of by case. There is no AI import in this file and no route to one.

**Both routes are reads, and behave like reads.** They write nothing: no case
row, no queue, and no audit record — for the same reason `GET /v1/dashboard`
writes none. Reading your own firm's numbers is not an auditable act, and a
trail padded with page views is a trail nobody reads. Everything that *decides*
something is logged; nothing here decides anything.

The aggregate is assembled with one queue read per case, exactly as
`GET /v1/cases` builds its list counts. At engagement scale — tens of cases,
not thousands — that is simpler and safer than a bespoke aggregate query
written twice, once per store; revisit only if a real firm's insights screen
ever gets slow.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Iterable
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dashboard import MINUTES_SAVED_PER_ITEM
from app.api.deps import Principal, get_repository, require_read
from app.core.repository import CaseRepository
from app.shared.api import (
    CaseSummary,
    CompareResponse,
    InsightsResponse,
    MonthlyPoint,
    PeriodDelta,
    RuleFrequency,
    VendorAttention,
)
from app.shared.schemas import (
    CaseRecord,
    MatchStatus,
    ReviewDecision,
    ReviewItem,
    Severity,
)
from app.shared.text import normalise_party_name

__all__ = ["router"]

router = APIRouter(tags=["insights"])

#: How many parties the attention list carries. A panel, not an export.
MAX_VENDORS = 20

#: Two years of trend. Older months are still in the data; they are simply not
#: what a firm looks at on this screen.
MAX_MONTHS = 24

#: What counts as movement worth the reader's eye: more than a quarter either
#: way. Deliberately a named `Decimal` rather than an inlined `0.25` — the
#: threshold is arguable, and something arguable should be arguable in review
#: rather than buried in an expression. Decimal because it is multiplied by
#: money, and money never touches a float here.
NOTABLE_SWING = Decimal("0.25")

#: Most serious first. Used to break a tie when one rule has fired at two
#: different severities equally often.
_SEVERITY_ORDER = (Severity.HIGH, Severity.MEDIUM, Severity.LOW)


# --------------------------------------------------------------------------- #
# Shared helpers
# --------------------------------------------------------------------------- #


def _money(amount: Decimal) -> str:
    """Group and fix to two places, the way `reports/content.py` does.

    Without the currency code: `VendorAttention` carries `currency` in its own
    field, so putting it in the number too would say it twice.
    """
    return f"{amount:,.2f}"


def _by_frequency(counts: Counter[str]) -> list[str]:
    """Keys, most frequent first, ties broken alphabetically.

    The alphabetical tie-break is not cosmetic: two rules that fired the same
    number of times must come back in the same order on every request, or the
    screen reshuffles itself between refreshes for no reason a reader can see.
    """
    return [key for key, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]


def _dominant_currency(items: Iterable[ReviewItem], default: str = "PKR") -> str:
    """The currency most of these ledger rows are in.

    A client's ledger is in one currency, so in practice this is *the*
    currency. It is computed rather than assumed because "in practice" is not
    a guarantee, and the alternative — labelling a total with whichever
    currency happened to sort first — would be a number that lies quietly.
    """
    counts = Counter(item.ledger_entry.currency for item in items)
    if not counts:
        return default
    return min(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0]


def _total_in(items: Iterable[ReviewItem], currency: str) -> Decimal:
    """Sum the amounts **in one currency**, leaving the rest out.

    Rows in another currency are excluded from the total rather than added to
    it. Adding rupees to dollars produces a number that is simply false, and a
    total covering the firm's main ledger currency is worth more than one that
    silently mixes two. The item and flag counts beside it still cover every
    row, which is why the two can differ for a party that trades in both.
    """
    return sum(
        (
            item.ledger_entry.amount
            for item in items
            if item.ledger_entry.currency == currency
        ),
        Decimal("0"),
    )


def _party_key(name: str) -> str:
    """Compare party names the way `matching/` and `rules/` already do.

    "Gulberg Traders (Pvt) Ltd" and "GULBERG TRADERS" are one business, and a
    "new vendor this period" list that says otherwise is worse than no list.
    A name made entirely of legal-form tokens normalises to nothing, so it
    falls back to the case-folded original rather than colliding with every
    other such name.
    """
    return normalise_party_name(name) or name.strip().casefold()


def _is_big_swing(left: Decimal | int, right: Decimal | int) -> bool:
    """More than `NOTABLE_SWING` of the earlier figure, in either direction.

    Appearing from nothing counts; staying at nothing does not.
    """
    if left == 0:
        return right > 0
    return abs(right - left) > NOTABLE_SWING * left


# --------------------------------------------------------------------------- #
# GET /v1/insights
# --------------------------------------------------------------------------- #


def _vendor_attention(items: list[ReviewItem]) -> list[VendorAttention]:
    """Every party in the firm's ledgers, with what the rules said about it.

    **This is attention, not risk.** There is no score here and there will not
    be one: Tarazu flags what needs review and never claims to detect fraud, so
    what this returns is a count of flags and the names of the rules that
    raised them — evidence an auditor can go and check, rather than a verdict
    dressed up as a number. A party with no flags at all still appears, with a
    `flag_count` of zero; hiding the quiet ones would turn a breakdown into an
    accusation list.

    Ordered by flag count, then by amount, then by name — the last two only so
    that equal parties come back in a stable order.
    """
    by_party: dict[str, list[ReviewItem]] = defaultdict(list)
    for item in items:
        by_party[item.ledger_entry.party_name].append(item)

    rows: list[tuple[int, Decimal, str, VendorAttention]] = []
    for party_name, party_items in by_party.items():
        flags = [flag for item in party_items for flag in item.flags]
        currency = _dominant_currency(party_items)
        total = _total_in(party_items, currency)
        rows.append(
            (
                len(flags),
                total,
                party_name,
                VendorAttention(
                    party_name=party_name,
                    flag_count=len(flags),
                    high=sum(1 for flag in flags if flag.severity is Severity.HIGH),
                    medium=sum(1 for flag in flags if flag.severity is Severity.MEDIUM),
                    low=sum(1 for flag in flags if flag.severity is Severity.LOW),
                    rules=_by_frequency(Counter(flag.rule_id for flag in flags)),
                    case_count=len({item.case_id for item in party_items}),
                    item_count=len(party_items),
                    total_amount=_money(total),
                    currency=currency,
                ),
            )
        )

    rows.sort(key=lambda row: (-row[0], -row[1], row[2]))
    return [vendor for *_, vendor in rows[:MAX_VENDORS]]


def _rule_frequency(items: list[ReviewItem]) -> list[RuleFrequency]:
    """Which rules are doing the work, and how much of it has been looked at.

    `reviewed` counts flags sitting on an item somebody has already approved or
    rejected. The gap between it and `count` is the outstanding queue for that
    rule — which is the number a partner actually wants, because a rule firing
    two hundred times that nobody has read is a different problem from one
    firing twice.
    """
    counts: Counter[str] = Counter()
    severities: dict[str, Counter[Severity]] = defaultdict(Counter)
    reviewed: Counter[str] = Counter()

    for item in items:
        decided = item.decision is not ReviewDecision.PENDING
        for flag in item.flags:
            counts[flag.rule_id] += 1
            severities[flag.rule_id][flag.severity] += 1
            if decided:
                reviewed[flag.rule_id] += 1

    return [
        RuleFrequency(
            rule_id=rule_id,
            count=counts[rule_id],
            severity=_rule_severity(severities[rule_id]),
            reviewed=reviewed[rule_id],
        )
        for rule_id in _by_frequency(counts)
    ]


def _rule_severity(severities: Counter[Severity]) -> Severity:
    """The severity this rule fires at: the most common one it has used.

    A rule normally has exactly one. Where a client's thresholds have made it
    fire at two, a tie resolves to the more serious of them — understating a
    severity is the worse of the two mistakes to make on this screen.
    """
    return min(
        severities.items(),
        key=lambda kv: (-kv[1], _SEVERITY_ORDER.index(kv[0])),
    )[0]


def _monthly(items: list[ReviewItem]) -> list[MonthlyPoint]:
    """Activity by ledger month, oldest first, the last two years of it.

    Bucketed on the ledger date rather than on when the case was uploaded: a
    firm processing March in May is looking at March, and a trend line keyed to
    upload dates would show its own working habits instead of the client's.
    """
    currency = _dominant_currency(items)
    buckets: dict[str, list[ReviewItem]] = defaultdict(list)
    for item in items:
        entry_date = item.ledger_entry.date
        buckets[f"{entry_date.year:04d}-{entry_date.month:02d}"].append(item)

    points = [
        MonthlyPoint(
            month=month,
            item_count=len(month_items),
            flag_count=sum(len(item.flags) for item in month_items),
            total_amount=_money(_total_in(month_items, currency)),
            currency=currency,
        )
        for month, month_items in sorted(buckets.items())
    ]
    return points[-MAX_MONTHS:]


@router.get(
    "/insights",
    response_model=InsightsResponse,
    summary="Firm-wide insights across every case",
)
async def get_insights(
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> InsightsResponse:
    """The whole firm's work, counted: parties, rules, months, and totals.

    Scoped like every other read. Another firm's cases are not filtered out of
    these figures — they were never in the query, because every repository call
    below is made with the caller's `org_id`.

    A firm with no cases yet gets a valid response full of zeros rather than a
    `404`. "You have nothing yet" is an answer this screen can render; an error
    is not, and a brand-new firm looking at its own empty dashboard has done
    nothing wrong.
    """
    org_id = principal.org_id
    cases = repository.list_cases(org_id)

    items: list[ReviewItem] = []
    open_evidence_requests = 0
    for case in cases:
        items.extend(repository.list_review_items(org_id, case.case_id))
        open_evidence_requests += sum(
            1
            for request in repository.list_evidence_requests(org_id, case.case_id)
            if not request.status.is_closed
        )

    flags = [flag for item in items for flag in item.flags]
    unreviewed_flags = sum(
        len(item.flags) for item in items if item.decision is ReviewDecision.PENDING
    )

    return InsightsResponse(
        # Every engagement, including ones still processing and ones that
        # failed: this is how many pieces of work the firm has, not how many
        # finished.
        case_count=len(cases),
        client_count=_client_count(repository, org_id, cases),
        total_review_items=len(items),
        pending_items=sum(
            1 for item in items if item.decision is ReviewDecision.PENDING
        ),
        total_flags=len(flags),
        unreviewed_flags=unreviewed_flags,
        open_evidence_requests=open_evidence_requests,
        # The dashboard's own estimate, applied to every case at once. Imported
        # rather than restated so there is exactly one number in the product
        # that answers "how long would this have taken by hand", and changing
        # it changes both screens together.
        estimated_hours_saved=round(len(items) * MINUTES_SAVED_PER_ITEM / 60, 1),
        vendors=_vendor_attention(items),
        rules=_rule_frequency(items),
        months=_monthly(items),
    )


def _client_count(
    repository: CaseRepository, org_id: str, cases: list[CaseRecord]
) -> int:
    """How many businesses this firm audits.

    Two sources, because a firm partway through Phase 1 has both: registered
    clients (ADR 0005) and one-off cases that name a business without pointing
    at a client row. Counted over normalised names so that registering a client
    the firm already ran a case for does not make it two businesses overnight.
    """
    names = {_party_key(client.name) for client in repository.list_clients(org_id)}
    names.update(_party_key(case.client_name) for case in cases)
    return len(names)


# --------------------------------------------------------------------------- #
# GET /v1/compare
# --------------------------------------------------------------------------- #


def _summary(case: CaseRecord, items: list[ReviewItem]) -> CaseSummary:
    """One side of the comparison, counted from the persisted queue.

    The same three counts `GET /v1/cases` puts on a list row, deliberately: the
    number an auditor reads here and the number they read on the case list have
    to be the same number. If the two ever disagree, `api/cases.py::_summary`
    is the original and this is the copy. It takes the queue rather than
    reading it, because the route has already read it to build the deltas.
    """
    return CaseSummary(
        case_id=case.case_id,
        client_name=case.client_name,
        client_id=case.client_id,
        period_start=case.period_start,
        period_end=case.period_end,
        status=case.status,
        status_detail=case.status_detail,
        created_by=case.created_by,
        created_at=case.created_at,
        total_review_items=len(items),
        pending_items=sum(
            1 for item in items if item.decision is ReviewDecision.PENDING
        ),
        flagged_items=sum(1 for item in items if item.flags),
    )


def _case_or_404(repository: CaseRepository, org_id: str, case_id: str) -> CaseRecord:
    """Resolve one side, inside the caller's organization.

    Another firm's case is a `404`, indistinguishable from one that never
    existed — the lookup is filtered by `org_id`, so this code cannot tell the
    two apart either, and therefore cannot leak the difference.
    """
    case = repository.get_case(org_id, case_id)
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No case with id {case_id!r}.",
        )
    return case


def _count_delta(
    label: str, left: int, right: int, *, watch_increase: bool = False
) -> PeriodDelta:
    """One counted measure, both sides, and the movement between them.

    `change` is left empty when the count did not move — "+0" is not a change,
    it is noise in a column the reader is scanning for changes.

    `notable` marks the rows worth stopping on: any rise in a measure where a
    rise is itself the news (`watch_increase` — the flag counts), or any
    movement of more than `NOTABLE_SWING` in either direction. Both directions,
    because a period with far fewer entries than the last one is as much a
    question for the client as one with far more.
    """
    difference = right - left
    return PeriodDelta(
        label=label,
        left=str(left),
        right=str(right),
        change=f"{difference:+d}" if difference else "",
        notable=(watch_increase and difference > 0) or _is_big_swing(left, right),
    )


def _amount_delta(
    left_items: list[ReviewItem], right_items: list[ReviewItem]
) -> PeriodDelta:
    """Total ledger value, as a percentage movement.

    A percentage rather than a difference: "+12.5%" is the sentence an auditor
    would say out loud, and the absolute figures are right there on either side
    of it. It is left empty in the two cases where it would mean nothing — a
    period that started at zero, and two periods kept in different currencies,
    where the movement would be an exchange rate rather than a business.
    """
    left_currency = _dominant_currency(left_items)
    right_currency = _dominant_currency(right_items)
    left_total = _total_in(left_items, left_currency)
    right_total = _total_in(right_items, right_currency)

    change = ""
    notable = False
    if left_currency == right_currency:
        notable = _is_big_swing(left_total, right_total)
        if left_total > 0:
            percent = round((right_total - left_total) / left_total * 100, 1)
            change = f"{percent:+.1f}%" if percent else ""

    return PeriodDelta(
        label="Total ledger amount",
        left=f"{left_currency} {_money(left_total)}",
        right=f"{right_currency} {_money(right_total)}",
        change=change,
        notable=notable,
    )


def _deltas(
    left_items: list[ReviewItem], right_items: list[ReviewItem]
) -> list[PeriodDelta]:
    """Every measure the two periods have in common, in reading order."""

    def matched(items: list[ReviewItem], match_status: MatchStatus) -> int:
        return sum(1 for item in items if item.match.status is match_status)

    def pending(items: list[ReviewItem]) -> int:
        return sum(1 for item in items if item.decision is ReviewDecision.PENDING)

    def flags(items: list[ReviewItem], severity: Severity | None = None) -> int:
        return sum(
            1
            for item in items
            for flag in item.flags
            if severity is None or flag.severity is severity
        )

    return [
        _count_delta("Review items", len(left_items), len(right_items)),
        _count_delta(
            "Matched",
            matched(left_items, MatchStatus.MATCHED),
            matched(right_items, MatchStatus.MATCHED),
        ),
        _count_delta(
            "Partial matches",
            matched(left_items, MatchStatus.PARTIAL),
            matched(right_items, MatchStatus.PARTIAL),
        ),
        _count_delta(
            "Unmatched",
            matched(left_items, MatchStatus.UNMATCHED),
            matched(right_items, MatchStatus.UNMATCHED),
        ),
        _count_delta("Pending decisions", pending(left_items), pending(right_items)),
        # A flag that was not there last period is the point of the screen, so
        # any rise in either flag row is notable however small it is.
        _count_delta(
            "Flags raised", flags(left_items), flags(right_items), watch_increase=True
        ),
        _count_delta(
            "High-severity flags",
            flags(left_items, Severity.HIGH),
            flags(right_items, Severity.HIGH),
            watch_increase=True,
        ),
        _amount_delta(left_items, right_items),
    ]


def _party_diff(
    left_items: list[ReviewItem], right_items: list[ReviewItem]
) -> tuple[list[str], list[str]]:
    """Parties in one period and not the other, both ways round.

    Compared on the normalised name and reported with the name as the ledger
    actually spells it, taken from the period the party appears in. A supplier
    who arrived this period and one who stopped being paid are both worth a
    question, and neither shows up in any count.
    """
    left_names = {
        _party_key(item.ledger_entry.party_name): item.ledger_entry.party_name
        for item in left_items
    }
    right_names = {
        _party_key(item.ledger_entry.party_name): item.ledger_entry.party_name
        for item in right_items
    }
    new = sorted(right_names[key] for key in right_names.keys() - left_names.keys())
    dropped = sorted(left_names[key] for key in left_names.keys() - right_names.keys())
    return new, dropped


@router.get(
    "/compare",
    response_model=CompareResponse,
    summary="Compare two periods side by side",
)
async def compare_periods(
    left: str = Query(..., description="The earlier period's case id."),
    right: str = Query(..., description="The period to compare it against."),
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> CompareResponse:
    """Two engagements, measure by measure, plus who came and who went.

    Reading one period against the last is how an auditor actually forms an
    expectation, so the comparison is a first-class route rather than something
    the frontend assembles out of two dashboards.

    Both ids are resolved inside the caller's organization and both are `404`
    when they are not there — including when they are perfectly real and belong
    to another firm.

    Nothing here judges the movement. `notable` says "look at this"; what the
    difference *means* is the auditor's to decide, and there is no wording on
    this route that pretends otherwise.
    """
    org_id = principal.org_id
    left_case = _case_or_404(repository, org_id, left)
    right_case = _case_or_404(repository, org_id, right)

    left_items = repository.list_review_items(org_id, left_case.case_id)
    right_items = repository.list_review_items(org_id, right_case.case_id)
    new_parties, dropped_parties = _party_diff(left_items, right_items)

    return CompareResponse(
        left=_summary(left_case, left_items),
        right=_summary(right_case, right_items),
        deltas=_deltas(left_items, right_items),
        new_parties=new_parties,
        dropped_parties=dropped_parties,
    )
