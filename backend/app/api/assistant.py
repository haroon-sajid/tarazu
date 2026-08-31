"""`POST /v1/assistant/chat` — Ask Tarazu, about one engagement.

The route loads what the question may be about, records the question, hands
it to `assistant.service`, records the answer, and returns both the answer
and the trail entry. Two trail entries per exchange, so "what was the
assistant asked, and what did it say" is answerable for every case, forever.

Grounding is the module's job and the route does not weaken it. The module
receives the case's persisted results and — for questions about the wider
record — a `WorkspaceContext` built here from the same org-scoped repository
every route uses, read-only: the case's documents and what the vision model
read from them (the extractions carry the provenance; a document's bytes
never leave the document store), its reports, its audit trail, and one
overview row per engagement in the organization. Nothing from outside the
organization reaches the module.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import Principal, get_repository, require_read, resolve_case_id
from app.core.audit import record_action, record_actor_action
from app.core.repository import CaseRepository
from app.modules.assistant import service as assistant
from app.shared.api import AssistantChatRequest, AssistantChatResponse
from app.shared.schemas import ActorType, AuditAction, ReviewDecision

__all__ = ["router"]

router = APIRouter(tags=["assistant"])
logger = logging.getLogger(__name__)

#: The trail keeps the question and the gist of the answer, not a transcript.
_DETAIL_LIMIT = 500


def _workspace(repository: CaseRepository, org_id: str, case_id: str) -> assistant.WorkspaceContext:
    """The rest of the engagement's record: org-scoped, read-only, no bytes.

    Every read goes through the same repository the routes use, so the
    scoping rules — not this function — decide what is visible. The trail
    is loaded before the question is recorded, so a history answer
    describes what happened up to the question, never the question itself.
    """
    overviews = []
    for case_record in repository.list_cases(org_id):
        case_items = repository.list_review_items(org_id, case_record.case_id)
        overviews.append(
            assistant.CaseOverview(
                case=case_record,
                total_items=len(case_items),
                pending=sum(1 for item in case_items if item.decision is ReviewDecision.PENDING),
                approved=sum(1 for item in case_items if item.decision is ReviewDecision.APPROVED),
                rejected=sum(1 for item in case_items if item.decision is ReviewDecision.REJECTED),
                flags=sum(len(item.flags) for item in case_items),
            )
        )
    return assistant.WorkspaceContext(
        documents=repository.list_documents(org_id, case_id),
        extractions=repository.list_extractions(org_id, case_id),
        reports=repository.list_reports(org_id, case_id),
        trail=repository.list_audit(org_id, case_id),
        cases=overviews,
        active_case_id=case_id,
    )


@router.post(
    "/assistant/chat",
    response_model=AssistantChatResponse,
    summary="Ask a question about an engagement, answered only from what it recorded",
)
async def chat(
    body: AssistantChatRequest,
    principal: Principal = Depends(require_read),
    repository: CaseRepository = Depends(get_repository),
) -> AssistantChatResponse:
    case_id = resolve_case_id(repository, principal, body.case_id)
    case = repository.get_case(principal.org_id, case_id)
    assert case is not None  # resolve_case_id has just confirmed it
    items = repository.list_review_items(principal.org_id, case_id)
    benford = repository.get_benford(principal.org_id, case_id)
    context = _workspace(repository, principal.org_id, case_id)

    record_actor_action(
        repository, principal.org_id, case_id, principal.actor,
        AuditAction.ASSISTANT_QUESTION_ASKED,
        detail=body.question[:_DETAIL_LIMIT],
    )

    answer = assistant.answer_question(
        body.question, case=case, items=items, benford=benford,
        context=context, language=body.language,
    )

    deterministic = answer.composed_by == assistant.DETERMINISTIC_COMPOSER
    record = record_action(
        repository, principal.org_id, case_id,
        ActorType.SYSTEM if deterministic else ActorType.AI,
        answer.composed_by,
        AuditAction.ASSISTANT_ANSWERED,
        detail=(
            f"{answer.intent.value}, {'grounded' if answer.grounded else 'refused'}, "
            f"{answer.answer_confidence.value} confidence, {len(answer.citations)} citation(s): "
            f"{answer.text[:_DETAIL_LIMIT]}"
        ),
    )
    return AssistantChatResponse(case_id=case_id, answer=answer, audit_record=record)
