"""REST and SSE endpoints for Human-in-the-Loop Approvals (BRICK-005 Phase 5)."""

import logging
from collections.abc import AsyncIterator

from fastapi import APIRouter, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse

from javed.agent.runtime import AgentRuntimeManager
from javed.mcp.approval_store import redact_sensitive_value
from javed.schemas.agent import AgentStreamEvent, validate_thread_id
from javed.schemas.approval import (
    ApprovalDecisionRequest,
    ApprovalListResponse,
    ApprovalRecord,
    ApprovalResponse,
)

logger = logging.getLogger("javed.api.v1.approvals")

router = APIRouter(prefix="/agent/approvals", tags=["Agent Approvals"])


def _get_agent_runtime(request: Request) -> AgentRuntimeManager:
    """Retrieve initialized AgentRuntimeManager from app state."""
    agent_runtime: AgentRuntimeManager | None = getattr(
        request.app.state,
        "agent_runtime",
        None,
    )
    if not agent_runtime:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Agent runtime is not initialized.",
        )
    return agent_runtime


def _verify_origin(request: Request, origin: str | None = Header(None)) -> None:
    """Verify Origin and Sec-Fetch-Site headers to protect against cross-origin attacks."""
    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site requests are not permitted for approval operations.",
        )
    if origin is None:
        origin = request.headers.get("origin")
    if origin is not None:
        settings = getattr(request.app.state, "settings", None)
        if settings and origin not in settings.allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Origin '{origin}' is not authorized for approval operations.",
            )


def _sanitize_record(record: ApprovalRecord) -> ApprovalRecord:
    """Return a copy of the approval record with sensitive argument values redacted."""
    return record.model_copy(update={"arguments": redact_sensitive_value(record.arguments)})


@router.get(
    "/pending",
    response_model=ApprovalListResponse,
    summary="List currently pending tool call approvals",
)
async def list_pending_approvals(
    request: Request,
    thread_id: str | None = None,
) -> ApprovalListResponse:
    """Retrieve all tool calls currently halted and awaiting human review."""
    runtime = _get_agent_runtime(request)
    if thread_id:
        try:
            thread_id = validate_thread_id(thread_id)
        except ValueError as ve:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid thread_id: {ve!s}",
            ) from ve

    records = await runtime.approval_store.get_pending_approvals(thread_id=thread_id)
    sanitized = [_sanitize_record(r) for r in records]
    return ApprovalListResponse(approvals=sanitized, total=len(sanitized))


@router.get(
    "/thread/{thread_id}",
    response_model=ApprovalListResponse,
    summary="List all tool call approvals for a specific thread",
)
async def list_thread_approvals(
    thread_id: str,
    request: Request,
) -> ApprovalListResponse:
    """Retrieve all approval records (pending, approved, rejected, cancelled) for a thread."""
    try:
        validated_id = validate_thread_id(thread_id)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid thread_id: {ve!s}",
        ) from ve

    runtime = _get_agent_runtime(request)
    records = await runtime.approval_store.get_thread_approvals(validated_id)
    sanitized = [_sanitize_record(r) for r in records]
    return ApprovalListResponse(approvals=sanitized, total=len(sanitized))


@router.get(
    "/{approval_id}",
    response_model=ApprovalResponse,
    summary="Retrieve single approval record by ID",
)
async def get_approval(
    approval_id: str,
    request: Request,
) -> ApprovalResponse:
    """Retrieve details, status, and telemetry for a specific approval record."""
    runtime = _get_agent_runtime(request)
    rec = await runtime.approval_store.get_approval(approval_id)
    if not rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Approval record '{approval_id}' not found.",
        )
    return ApprovalResponse(approval=_sanitize_record(rec), message="Approval record retrieved.")


@router.post(
    "/{approval_id}/decision",
    response_model=ApprovalResponse,
    summary="Record human decision (approve or reject) without resuming execution",
)
async def submit_decision(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    origin: str | None = Header(None),
) -> ApprovalResponse:
    """Record an approve or reject decision for a pending approval."""
    _verify_origin(request, origin)
    try:
        thread_id = validate_thread_id(payload.thread_id)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid thread_id: {ve!s}",
        ) from ve

    runtime = _get_agent_runtime(request)

    try:
        updated = await runtime.approval_store.record_decision(
            approval_id=approval_id,
            decision=payload.decision,
            expected_thread_id=thread_id,
            decider="human_user",
            reason=payload.reason,
        )
        return ApprovalResponse(
            approval=_sanitize_record(updated),
            message=f"Approval successfully transitioned to '{updated.status}'.",
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke)) from ke
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe)) from pe
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve)) from ve


@router.post(
    "/{approval_id}/resume",
    summary="Submit decision and stream resumed agent execution via Server-Sent Events",
    response_class=StreamingResponse,
)
async def resume_agent_stream(
    approval_id: str,
    payload: ApprovalDecisionRequest,
    request: Request,
    origin: str | None = Header(None),
) -> StreamingResponse:
    """Submit approve/reject decision and stream the resulting agent execution via SSE."""
    _verify_origin(request, origin)
    try:
        thread_id = validate_thread_id(payload.thread_id)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid thread_id: {ve!s}",
        ) from ve

    runtime = _get_agent_runtime(request)

    async def event_generator() -> AsyncIterator[str]:
        try:
            async for event in runtime.resume_agent(
                thread_id=thread_id,
                approval_id=approval_id,
                decision=payload.decision,
                reason=payload.reason,
            ):
                if await request.is_disconnected():
                    logger.info(
                        "Client disconnected during resumed agent stream for thread %s",
                        thread_id,
                    )
                    break
                yield f"event: {event.event}\ndata: {event.model_dump_json()}\n\n"
        except Exception as e:
            logger.exception("Error during resumed stream for approval %s: %s", approval_id, e)
            err_event = AgentStreamEvent(
                event="run_failed",
                data={
                    "thread_id": thread_id,
                    "approval_id": approval_id,
                    "error": str(e),
                },
            )
            yield f"event: run_failed\ndata: {err_event.model_dump_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/{approval_id}/cancel",
    response_model=ApprovalResponse,
    summary="Cancel a pending approval",
)
async def cancel_approval(
    approval_id: str,
    request: Request,
    payload: dict[str, str],
    origin: str | None = Header(None),
) -> ApprovalResponse:
    """Cancel a pending approval invocation."""
    _verify_origin(request, origin)
    thread_id_raw = payload.get("thread_id", "")
    try:
        thread_id = validate_thread_id(thread_id_raw)
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid thread_id: {ve!s}",
        ) from ve

    runtime = _get_agent_runtime(request)
    try:
        updated = await runtime.approval_store.cancel_approval(
            approval_id=approval_id,
            expected_thread_id=thread_id,
        )
        return ApprovalResponse(
            approval=updated,
            message="Approval successfully cancelled.",
        )
    except KeyError as ke:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(ke)) from ke
    except PermissionError as pe:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(pe)) from pe
    except ValueError as ve:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(ve)) from ve
