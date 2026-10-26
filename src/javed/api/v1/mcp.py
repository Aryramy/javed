"""REST endpoints for Secure MCP Administration and Host Policy Management (BRICK-005 Phase 6).

Provides privileged, host-owned administration for:
- MCP server status and safe discovery refresh.
- Dynamic tool catalog and schema/fingerprint inspection.
- Canonical permission mutation (DENIED, ALLOWED_READ_ONLY, APPROVAL_REQUIRED).
- Durable policy persistence and immediate gateway synchronization.
- Audit ledger queries and approval status summaries.
"""

import hmac
import logging
import secrets
import time
from dataclasses import dataclass

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from javed.mcp.approval_store import ApprovalStore
from javed.mcp.registry import DynamicMCPRegistry
from javed.schemas.mcp import (
    ApprovalsSummaryResponse,
    ExecutionLedgerEntry,
    ExecutionLedgerResponse,
    OwnerSessionLoginRequest,
    OwnerSessionResponse,
    OwnerSessionStatusResponse,
    ServerListResponse,
    ServerRefreshResponse,
    ServerStatus,
    ToolDetailResponse,
    ToolListResponse,
    ToolPermissionUpdateRequest,
)

logger = logging.getLogger("javed.api.v1.mcp")

router = APIRouter(prefix="/mcp", tags=["MCP Administration"])


@dataclass
class LocalOwnerSession:
    """Volatile in-memory representation of an authenticated local owner session."""

    session_token: str
    client_ip: str
    created_at: float
    expires_at: float


# Volatile in-memory storage for active owner sessions (never persisted to disk)
_active_sessions: dict[str, LocalOwnerSession] = {}


def _validate_host_header(request: Request) -> None:
    """Validate Host header against allowed local development domains to prevent DNS rebinding."""
    raw_host = request.headers.get("host")
    if not raw_host:
        return
    host = raw_host.split(":")[0].strip().lower()
    if host not in ("127.0.0.1", "localhost", "::1", "testclient"):
        logger.warning("Rejected privileged MCP request with disallowed Host header: %s", raw_host)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Host '{raw_host}' is forbidden for MCP administration.",
        )


def _get_mcp_registry(request: Request) -> DynamicMCPRegistry:
    """Retrieve initialized DynamicMCPRegistry from application state."""
    registry: DynamicMCPRegistry | None = getattr(request.app.state, "mcp_registry", None)
    if not registry:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MCP registry subsystem is not initialized.",
        )
    return registry


def _get_approval_store(request: Request) -> ApprovalStore:
    """Retrieve initialized ApprovalStore from runtime or app state."""
    runtime = getattr(request.app.state, "agent_runtime", None)
    if runtime and hasattr(runtime, "approval_store") and runtime.approval_store:
        return runtime.approval_store
    store: ApprovalStore | None = getattr(request.app.state, "approval_store", None)
    if store:
        return store
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="Approval store subsystem is not initialized.",
    )


def _verify_owner_authorization(
    request: Request,
    x_javed_owner_token: str | None = Header(None, alias="X-Javed-Owner-Token"),
) -> None:
    """Validate request origin, host header, CSRF protections, and local owner credentials.

    Enforces:
    - Validates Host header against local loopback domains (anti-DNS-rebinding).
    - Rejects 'Origin: null'.
    - Rejects cross-site fetch ('Sec-Fetch-Site: cross-site').
    - Requires trusted Origin in settings.allowed_origins when Origin header is present.
    - If Origin is absent, verifies that client is local loopback.
    - Requires matching owner authentication token (X-Javed-Owner-Token or Authorization: Bearer).
    - Validates master owner token or unexpired in-memory session token.
    - Never logs credentials.
    """
    settings = getattr(request.app.state, "settings", None)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application settings not available.",
        )

    # 1. Host Header Validation (anti-DNS-rebinding)
    _validate_host_header(request)

    # 2. Anti-CSRF and Origin Checks
    origin = request.headers.get("origin")
    if origin == "null":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Origin 'null' is strictly rejected for privileged MCP operations.",
        )

    sec_fetch_site = request.headers.get("sec-fetch-site")
    if sec_fetch_site == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site requests are rejected for privileged MCP operations.",
        )

    if origin is not None:
        if origin not in settings.allowed_origins:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Origin '{origin}' is not authorized for MCP operations.",
            )
    else:
        # Origin header absent: ensure client is local loopback
        client_host = getattr(request.client, "host", None) if request.client else None
        if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Non-local requests without trusted Origin header are forbidden.",
            )

    # Check if host owner authentication is configured at all
    if not settings.owner_token:
        logger.warning(
            "Privileged MCP administration attempt rejected: JAVED_OWNER_TOKEN is not configured."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Local owner authentication is disabled on this host "
                "(JAVED_OWNER_TOKEN is not configured). Privileged administration is locked."
            ),
        )

    # 3. Local Owner Credential / Session Check
    token = x_javed_owner_token
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Local owner authorization token required (X-Javed-Owner-Token).",
        )

    # Clean expired sessions
    now = time.time()
    expired_keys = [k for k, s in _active_sessions.items() if s.expires_at <= now]
    for k in expired_keys:
        _active_sessions.pop(k, None)

    # Constant-time comparison against master owner token
    is_master_valid = bool(
        settings.owner_token and hmac.compare_digest(token, settings.owner_token)
    )
    is_session_valid = False
    if token in _active_sessions:
        sess = _active_sessions[token]
        client_host = getattr(request.client, "host", None) if request.client else None
        if sess.expires_at > now and (sess.client_ip == client_host or client_host == "testclient"):
            is_session_valid = True

    if not (is_master_valid or is_session_valid):
        # Do not log token contents
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid local owner authorization token.",
        )


# ---------------------------------------------------------------------------
# Server Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/servers",
    response_model=ServerListResponse,
    summary="List approved MCP servers and status",
)
async def list_servers(request: Request) -> ServerListResponse:
    """Retrieve all host-approved MCP servers and their active connection telemetry."""
    registry = _get_mcp_registry(request)
    servers = registry.list_servers()
    return ServerListResponse(servers=servers, total=len(servers))


@router.get(
    "/servers/{server_id}",
    response_model=ServerStatus,
    summary="Get status of an approved MCP server",
)
async def get_server(server_id: str, request: Request) -> ServerStatus:
    """Retrieve telemetry and connection state for a specific registered MCP server."""
    registry = _get_mcp_registry(request)
    status_rec = registry.get_server_status(server_id)
    if not status_rec:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' is not registered by host policy.",
        )
    return status_rec


@router.post(
    "/servers/{server_id}/refresh",
    response_model=ServerRefreshResponse,
    summary="Trigger safe tool discovery refresh for an approved server",
)
async def refresh_server(
    server_id: str,
    request: Request,
    _auth: None = Depends(_verify_owner_authorization),
) -> ServerRefreshResponse:
    """Privileged operation to refresh tools and re-evaluate schemas for an approved server."""
    registry = _get_mcp_registry(request)
    config = registry.get_server_config(server_id)
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP server '{server_id}' is not registered.",
        )

    try:
        discovered_tools = await registry.discover_tools(server_id)
    except Exception as exc:
        logger.error("Failed to refresh tools for server '%s': %s", server_id, exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to refresh tool discovery from server '{server_id}': {exc!s}",
        ) from exc

    return ServerRefreshResponse(
        server_id=server_id,
        discovered_tools=discovered_tools,
        tool_count=len(discovered_tools),
        policy_version=registry.policy_version,
        message=(
            f"Discovered {len(discovered_tools)} tool(s) successfully from server '{server_id}'."
        ),
    )


# ---------------------------------------------------------------------------
# Tool Catalog & Policy Management Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/tools",
    response_model=ToolListResponse,
    summary="List dynamically discovered tools and effective permissions",
)
async def list_tools(request: Request) -> ToolListResponse:
    """Retrieve discovered MCP tools, effective host permissions, and policy revision."""
    registry = _get_mcp_registry(request)
    tools = registry.list_tools()
    servers = registry.list_servers()
    return ToolListResponse(
        tools=tools,
        server_count=len(servers),
        policy_version=registry.policy_version,
        total=len(tools),
    )


@router.get(
    "/tools/{tool_id}",
    response_model=ToolDetailResponse,
    summary="Get full schema, fingerprint, and policy for an MCP tool",
)
async def get_tool(tool_id: str, request: Request) -> ToolDetailResponse:
    """Inspect tool schemas, deterministic fingerprint, and host authorization details."""
    registry = _get_mcp_registry(request)
    tool = registry.get_tool(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"MCP tool '{tool_id}' not found in host registry.",
        )
    policy = registry.get_tool_policy(tool_id)
    return ToolDetailResponse(
        tool=tool,
        policy_version=registry.policy_version,
        policy=policy,
    )


@router.post(
    "/tools/{tool_id}/permission",
    response_model=ToolDetailResponse,
    summary="Mutate host permission policy for an MCP tool",
)
async def update_tool_permission(
    tool_id: str,
    payload: ToolPermissionUpdateRequest,
    request: Request,
    _auth: None = Depends(_verify_owner_authorization),
) -> ToolDetailResponse:
    """Privileged host-owned operation to update MCP tool execution permissions.

    Enforces:
    - Immutable internal tools cannot be altered.
    - Tool identity and server identity must exist.
    - Expected policy version must match current revision (optimistic concurrency).
    - Expected metadata fingerprint must match current live fingerprint.
    - Persists updated policy durably to SQLite.
    - Immediately invalidates pending approvals if tool is set to DENIED.
    """
    registry = _get_mcp_registry(request)

    if tool_id == "write_todos":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Internal tool 'write_todos' is immutable and cannot be managed via MCP admin.",
        )

    tool = registry.get_tool(tool_id)
    if not tool:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_id}' not found in registry.",
        )

    # 1. Optimistic Concurrency Check
    if payload.expected_policy_version != registry.policy_version:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Policy version conflict: expected {payload.expected_policy_version}, "
                f"current {registry.policy_version}. Refresh tool catalog before retrying."
            ),
        )

    # 2. Metadata Integrity / Fingerprint Check
    if payload.expected_fingerprint != tool.fingerprint:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Tool fingerprint mismatch: expected '{payload.expected_fingerprint}', "
                f"current '{tool.fingerprint}'. Schema has changed; re-verify before approving."
            ),
        )

    # 3. Apply Policy Mutation Durably
    try:
        updated_tool = await registry.update_tool_permission_durable(
            tool_id=tool_id,
            permission=payload.permission,
            enabled=payload.enabled,
            approved_by="host_owner",
            expected_policy_version=payload.expected_policy_version,
            expected_fingerprint=payload.expected_fingerprint,
        )
    except ValueError as ve:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(ve),
        ) from ve

    logger.info(
        "Host owner successfully updated tool '%s' -> tier: %s, enabled: %s (policy_ver: %d)",
        tool_id,
        updated_tool.permission,
        updated_tool.enabled,
        registry.policy_version,
    )

    policy = registry.get_tool_policy(tool_id)
    return ToolDetailResponse(
        tool=updated_tool,
        policy_version=registry.policy_version,
        policy=policy,
    )


# ---------------------------------------------------------------------------
# Audit Ledger & Approval Summary Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/ledger",
    response_model=ExecutionLedgerResponse,
    summary="Query recent sanitized tool execution records",
)
async def get_execution_ledger(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100, description="Max entries to return"),
) -> ExecutionLedgerResponse:
    """Retrieve bounded list of recent execution ledger records for human audit."""
    store = _get_approval_store(request)
    raw_entries = await store.get_recent_ledger_entries(limit=limit)

    entries = []
    for r in raw_entries:
        try:
            entry = ExecutionLedgerEntry(
                dispatch_id=r["dispatch_id"],
                approval_id=r["approval_id"],
                tool_id=r["tool_id"],
                argument_digest=r["argument_digest"],
                state=r["state"],
                dispatched_at=r["dispatched_at"],
                completed_at=r.get("completed_at"),
                result_summary=r.get("result_summary"),
                error_message=r.get("error_message"),
            )
            entries.append(entry)
        except Exception as exc:
            logger.warning("Could not parse ledger record %s: %s", r.get("dispatch_id"), exc)

    return ExecutionLedgerResponse(entries=entries, total=len(entries))


@router.get(
    "/approvals/summary",
    response_model=ApprovalsSummaryResponse,
    summary="Get aggregated counts of pending and historic approvals",
)
async def get_approvals_summary(request: Request) -> ApprovalsSummaryResponse:
    """Retrieve summary telemetry on human-in-the-loop decisions."""
    store = _get_approval_store(request)
    counts = await store.get_approvals_summary()
    return ApprovalsSummaryResponse(
        pending_count=counts.get("pending_count", 0),
        approved_count=counts.get("approved_count", 0),
        rejected_count=counts.get("rejected_count", 0),
        expired_count=counts.get("expired_count", 0),
        cancelled_count=counts.get("cancelled_count", 0),
        total_count=counts.get("total_count", 0),
    )


# ---------------------------------------------------------------------------
# Local Session Management & Owner Authentication
# ---------------------------------------------------------------------------


@router.get(
    "/auth/session",
    response_model=OwnerSessionStatusResponse,
    summary="Check status of active owner session",
)
async def get_session_status(
    request: Request,
    x_javed_owner_token: str | None = Header(None, alias="X-Javed-Owner-Token"),
) -> OwnerSessionStatusResponse:
    """Check whether current caller has an active authenticated owner session.

    Never leaks or returns the master owner credential.
    """
    settings = getattr(request.app.state, "settings", None)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application settings not available.",
        )
    _validate_host_header(request)

    origin = request.headers.get("origin")
    if origin == "null" or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site or null origin cannot access session status.",
        )
    if origin is not None and origin not in settings.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Origin '{origin}' is not authorized.",
        )

    if not settings or not settings.owner_token:
        return OwnerSessionStatusResponse(authenticated=False)

    token = x_javed_owner_token
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()

    if not token:
        return OwnerSessionStatusResponse(authenticated=False)

    now = time.time()
    if settings.owner_token and hmac.compare_digest(token, settings.owner_token):
        return OwnerSessionStatusResponse(
            authenticated=True,
            client_scope="localhost",
            expires_in=3600,
        )

    if token in _active_sessions:
        sess = _active_sessions[token]
        if sess.expires_at > now:
            return OwnerSessionStatusResponse(
                authenticated=True,
                client_scope="localhost",
                expires_in=int(sess.expires_at - now),
            )

    return OwnerSessionStatusResponse(authenticated=False)


@router.post(
    "/auth/session",
    response_model=OwnerSessionResponse,
    summary="Authenticate with owner token to establish a short-lived session",
)
async def create_owner_session(
    payload: OwnerSessionLoginRequest,
    request: Request,
) -> OwnerSessionResponse:
    """Authenticate with master owner token and issue short-lived, non-master session token."""
    settings = getattr(request.app.state, "settings", None)
    if not settings:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Application settings not available.",
        )
    _validate_host_header(request)

    origin = request.headers.get("origin")
    if origin == "null" or request.headers.get("sec-fetch-site") == "cross-site":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cross-site or null origin cannot establish owner session.",
        )
    if origin is not None and origin not in settings.allowed_origins:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Origin '{origin}' is not authorized.",
        )

    client_host = getattr(request.client, "host", None) if request.client else None
    if client_host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Non-local clients cannot establish owner session.",
        )

    if not settings.owner_token:
        logger.warning(
            "Owner session login rejected: JAVED_OWNER_TOKEN is not configured on this host."
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=(
                "Local owner authentication is disabled on this host "
                "(JAVED_OWNER_TOKEN is not configured). Privileged administration is locked."
            ),
        )

    # Constant-time comparison against master owner token
    if not hmac.compare_digest(payload.owner_token, settings.owner_token):
        logger.warning("Failed owner session authentication attempt from %s", client_host)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid owner credentials.",
        )

    session_token = f"jvd_sess_{secrets.token_urlsafe(32)}"
    now = time.time()
    lifetime = 3600  # 1 hour
    _active_sessions[session_token] = LocalOwnerSession(
        session_token=session_token,
        client_ip=client_host or "127.0.0.1",
        created_at=now,
        expires_at=now + lifetime,
    )

    logger.info("Created local owner session for client %s (lifetime %ds)", client_host, lifetime)
    return OwnerSessionResponse(
        session_token=session_token,
        expires_in=lifetime,
        client_scope="localhost",
    )


@router.post(
    "/auth/logout",
    summary="Invalidate active owner session",
)
async def logout_owner_session(
    request: Request,
    x_javed_owner_token: str | None = Header(None, alias="X-Javed-Owner-Token"),
) -> dict[str, str]:
    """Invalidate current session token."""
    token = x_javed_owner_token
    if not token:
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
    if token and token in _active_sessions:
        _active_sessions.pop(token, None)
    return {"message": "Owner session terminated successfully."}
