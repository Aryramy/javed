"""Durable SQLite storage and Execution Ledger for Human-in-the-Loop Approvals (BRICK-005 Phase 5).

Provides:
- Atomic status transitions (pending -> approved/rejected/cancelled).
- Durable execution ledger preventing duplicate transport dispatch.
- Full process restart recovery from disk.
- Complete isolation from LangGraph checkpointer tables.
"""

import json
import logging
import os
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

import aiosqlite

from javed.schemas.approval import (
    ApprovalRecord,
    ApprovalStatus,
)

logger = logging.getLogger("javed.mcp.approval_store")

SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    "password",
    "secret",
    "token",
    "api_key",
    "apikey",
    "key",
    "auth",
    "credential",
    "private_key",
    "access_token",
    "refresh_token",
    "bearer",
)


def redact_sensitive_value(value: Any) -> Any:
    """Recursively redact sensitive field values from dictionaries and lists for audit/logging."""
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for k, v in value.items():
            k_lower = str(k).lower()
            if any(p in k_lower for p in SENSITIVE_KEY_PATTERNS):
                redacted[k] = "[REDACTED]"
            else:
                redacted[k] = redact_sensitive_value(v)
        return redacted
    elif isinstance(value, list):
        return [redact_sensitive_value(item) for item in value]
    elif isinstance(value, str):
        val_lower = value.lower()
        if (
            value.startswith("sk-or-")
            or value.startswith("jvd_sess_")
            or "bearer " in val_lower
            or "basic " in val_lower
        ):
            return "[REDACTED]"
        return value
    return value

CREATE_PENDING_APPROVALS_TABLE = """
CREATE TABLE IF NOT EXISTS pending_approvals (
    approval_id TEXT PRIMARY KEY,
    interrupt_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    server_id TEXT NOT NULL,
    tool_id TEXT NOT NULL,
    tool_call_id TEXT NOT NULL,
    arguments_json TEXT NOT NULL,
    argument_digest TEXT NOT NULL,
    tool_fingerprint TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT,
    status TEXT NOT NULL,
    decision_at TEXT,
    decision_by TEXT,
    rejection_reason TEXT,
    dispatch_status TEXT NOT NULL,
    dispatched_at TEXT,
    completed_at TEXT,
    result_summary TEXT,
    error_message TEXT
);
"""

CREATE_PENDING_APPROVALS_INDICES = """
CREATE INDEX IF NOT EXISTS idx_approvals_thread_status ON pending_approvals(thread_id, status);
CREATE INDEX IF NOT EXISTS idx_approvals_tool_digest ON pending_approvals(tool_id, argument_digest);
CREATE INDEX IF NOT EXISTS idx_approvals_interrupt ON pending_approvals(interrupt_id);
"""

CREATE_EXECUTION_LEDGER_TABLE = """
CREATE TABLE IF NOT EXISTS execution_ledger (
    dispatch_id TEXT PRIMARY KEY,
    approval_id TEXT NOT NULL UNIQUE,
    tool_id TEXT NOT NULL,
    argument_digest TEXT NOT NULL,
    state TEXT NOT NULL,
    dispatched_at TEXT NOT NULL,
    completed_at TEXT,
    result_summary TEXT,
    error_message TEXT
);
"""

CREATE_HOST_TOOL_POLICIES_TABLE = """
CREATE TABLE IF NOT EXISTS host_tool_policies (
    tool_id TEXT PRIMARY KEY,
    server_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    enabled INTEGER NOT NULL,
    approved_fingerprint TEXT NOT NULL,
    policy_version INTEGER NOT NULL,
    updated_at TEXT NOT NULL,
    updated_by TEXT NOT NULL
);
"""

CREATE_POLICY_METADATA_TABLE = """
CREATE TABLE IF NOT EXISTS policy_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def _parse_row(row: aiosqlite.Row) -> ApprovalRecord:
    """Convert an aiosqlite Row to an ApprovalRecord."""
    args_json = row["arguments_json"]
    try:
        arguments = json.loads(args_json) if args_json else {}
    except Exception:
        arguments = {}

    def _parse_dt(val: str | None) -> datetime | None:
        if not val:
            return None
        try:
            return datetime.fromisoformat(val)
        except Exception:
            return None

    return ApprovalRecord(
        approval_id=row["approval_id"],
        interrupt_id=row["interrupt_id"],
        run_id=row["run_id"],
        thread_id=row["thread_id"],
        server_id=row["server_id"],
        tool_id=row["tool_id"],
        tool_call_id=row["tool_call_id"],
        arguments=arguments,
        argument_digest=row["argument_digest"],
        tool_fingerprint=row["tool_fingerprint"],
        policy_version=int(row["policy_version"]),
        created_at=datetime.fromisoformat(row["created_at"]),
        expires_at=_parse_dt(row["expires_at"]),
        status=row["status"],
        decision_at=_parse_dt(row["decision_at"]),
        decision_by=row["decision_by"],
        rejection_reason=row["rejection_reason"],
        dispatch_status=row["dispatch_status"],
        dispatched_at=_parse_dt(row["dispatched_at"]),
        completed_at=_parse_dt(row["completed_at"]),
        result_summary=row["result_summary"],
        error_message=row["error_message"],
    )


class ApprovalStore:
    """Manages persistent SQLite storage of pending approvals and the duplicate-dispatch ledger."""

    def __init__(self, db_path: str = "data/approvals.db") -> None:
        self.db_path = db_path
        self._is_initialized = False

    async def initialize(self) -> None:
        """Create tables and indices if they do not exist."""
        if self._is_initialized:
            return

        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("PRAGMA journal_mode = WAL;")
            await db.execute("PRAGMA busy_timeout = 5000;")
            await db.execute(CREATE_PENDING_APPROVALS_TABLE)
            await db.executescript(CREATE_PENDING_APPROVALS_INDICES)
            await db.execute(CREATE_EXECUTION_LEDGER_TABLE)
            await db.execute(CREATE_HOST_TOOL_POLICIES_TABLE)
            await db.execute(CREATE_POLICY_METADATA_TABLE)
            await db.commit()

        self._is_initialized = True
        logger.info("ApprovalStore initialized at %s", self.db_path)

    async def create_approval(self, record: ApprovalRecord) -> ApprovalRecord:
        """Save a new pending approval record durably."""
        await self.initialize()

        args_str = json.dumps(record.arguments, sort_keys=True)
        created_str = record.created_at.isoformat()
        expires_str = record.expires_at.isoformat() if record.expires_at else None

        decision_str = record.decision_at.isoformat() if record.decision_at else None
        dispatched_str = record.dispatched_at.isoformat() if record.dispatched_at else None
        completed_str = record.completed_at.isoformat() if record.completed_at else None

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            # Check if this approval_id already exists
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (record.approval_id,),
            ) as cursor:
                existing = await cursor.fetchone()
                if existing:
                    return _parse_row(existing)

            await db.execute(
                """
                INSERT INTO pending_approvals (
                    approval_id, interrupt_id, run_id, thread_id, server_id,
                    tool_id, tool_call_id, arguments_json, argument_digest,
                    tool_fingerprint, policy_version, created_at, expires_at,
                    status, dispatch_status, decision_at, decision_by,
                    rejection_reason, dispatched_at, completed_at,
                    result_summary, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.approval_id,
                    record.interrupt_id,
                    record.run_id,
                    record.thread_id,
                    record.server_id,
                    record.tool_id,
                    record.tool_call_id,
                    args_str,
                    record.argument_digest,
                    record.tool_fingerprint,
                    record.policy_version,
                    created_str,
                    expires_str,
                    record.status,
                    record.dispatch_status,
                    decision_str,
                    record.decision_by,
                    record.rejection_reason,
                    dispatched_str,
                    completed_str,
                    record.result_summary,
                    record.error_message,
                ),
            )
            await db.commit()

        logger.info(
            "Created durable pending approval: %s for tool '%s' (thread: %s)",
            record.approval_id,
            record.tool_id,
            record.thread_id,
        )
        return record

    async def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        """Fetch an approval record by ID."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None
                return _parse_row(row)

    async def get_pending_approvals(self, thread_id: str | None = None) -> list[ApprovalRecord]:
        """List all approvals currently in 'pending' status, optionally filtered by thread_id."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if thread_id is not None:
                query = (
                    "SELECT * FROM pending_approvals "
                    "WHERE thread_id = ? AND status = 'pending' "
                    "ORDER BY created_at ASC"
                )
                params: tuple[Any, ...] = (thread_id,)
            else:
                query = (
                    "SELECT * FROM pending_approvals "
                    "WHERE status = 'pending' "
                    "ORDER BY created_at ASC"
                )
                params = ()

            async with db.execute(query, params) as cursor:
                rows = await cursor.fetchall()
                return [_parse_row(r) for r in rows]

    async def get_thread_approvals(self, thread_id: str) -> list[ApprovalRecord]:
        """Fetch all approval records associated with a specific conversation thread."""
        await self.initialize()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            query = "SELECT * FROM pending_approvals WHERE thread_id = ? ORDER BY created_at ASC"
            async with db.execute(query, (thread_id,)) as cursor:
                rows = await cursor.fetchall()
                return [_parse_row(r) for r in rows]

    async def record_decision(
        self,
        approval_id: str,
        decision: Literal["approve", "reject"],
        expected_thread_id: str,
        decider: str = "human_user",
        reason: str | None = None,
    ) -> ApprovalRecord:
        """Atomically transition a pending approval to approved or rejected.

        Enforces:
        - Must exist in DB.
        - Must belong to expected_thread_id.
        - Must be in 'pending' status (prevents duplicate or stale decisions).
        """
        await self.initialize()

        target_status: ApprovalStatus = "approved" if decision == "approve" else "rejected"
        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row

            # Fetch current state first to provide precise error messages
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise KeyError(f"Approval '{approval_id}' not found.")
                existing = _parse_row(row)

            if existing.thread_id != expected_thread_id:
                raise PermissionError(
                    f"Wrong thread ID. Approval belongs to thread '{existing.thread_id}', "
                    f"not '{expected_thread_id}'."
                )

            if existing.status != "pending":
                raise ValueError(
                    f"Approval '{approval_id}' cannot be modified; "
                    f"current status is '{existing.status}'."
                )

            if existing.expires_at and datetime.now(UTC) > existing.expires_at:
                await db.execute(
                    "UPDATE pending_approvals SET status = 'expired' WHERE approval_id = ?",
                    (approval_id,),
                )
                await db.commit()
                raise ValueError(f"Approval '{approval_id}' has expired and cannot be decided.")

            # Atomic transition
            cursor = await db.execute(
                """
                UPDATE pending_approvals
                SET status = ?, decision_at = ?, decision_by = ?, rejection_reason = ?
                WHERE approval_id = ? AND status = 'pending' AND thread_id = ?
                """,
                (target_status, now_str, decider, reason, approval_id, expected_thread_id),
            )
            await db.commit()

            if cursor.rowcount == 0:
                raise ValueError(
                    f"Concurrent modification: Approval '{approval_id}' status changed."
                )

            # Return updated record
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as fetch_cur:
                updated_row = await fetch_cur.fetchone()
                assert updated_row is not None
                return _parse_row(updated_row)

    async def cancel_approval(self, approval_id: str, expected_thread_id: str) -> ApprovalRecord:
        """Atomically mark a pending approval as cancelled."""
        await self.initialize()

        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    raise KeyError(f"Approval '{approval_id}' not found.")
                existing = _parse_row(row)

            if existing.thread_id != expected_thread_id:
                raise PermissionError(
                    f"Wrong thread ID. Approval belongs to thread '{existing.thread_id}', "
                    f"not '{expected_thread_id}'."
                )

            if existing.status != "pending":
                raise ValueError(
                    f"Approval '{approval_id}' cannot be cancelled; "
                    f"current status is '{existing.status}'."
                )

            cursor = await db.execute(
                """
                UPDATE pending_approvals
                SET status = 'cancelled', decision_at = ?, decision_by = 'user_cancellation'
                WHERE approval_id = ? AND status = 'pending' AND thread_id = ?
                """,
                (now_str, approval_id, expected_thread_id),
            )
            await db.commit()

            if cursor.rowcount == 0:
                raise ValueError(f"Approval '{approval_id}' status changed concurrently.")

            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as fetch_cur:
                updated_row = await fetch_cur.fetchone()
                assert updated_row is not None
                return _parse_row(updated_row)

    # -----------------------------------------------------------------------
    # Durable Execution Ledger (Duplicate Dispatch Protection)
    # -----------------------------------------------------------------------

    async def start_dispatch(
        self,
        approval_id: str,
        tool_id: str,
        argument_digest: str,
    ) -> bool:
        """Reserve execution in the durable ledger atomically.

        Returns:
            True if reservation succeeded and tool can be dispatched.
            False if tool was already dispatched, in-flight, or completed.
        """
        await self.initialize()

        now_str = datetime.now(UTC).isoformat()
        dispatch_id = f"disp_{uuid.uuid4().hex[:12]}"

        async with aiosqlite.connect(self.db_path) as db:
            # 1. Check approval record status
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM pending_approvals WHERE approval_id = ?",
                (approval_id,),
            ) as cursor:
                row = await cursor.fetchone()
                if not row:
                    logger.warning("start_dispatch: Approval '%s' not found.", approval_id)
                    return False
                record = _parse_row(row)

            if record.status != "approved":
                logger.warning(
                    "start_dispatch: Approval '%s' is not in 'approved' status (got %s).",
                    approval_id,
                    record.status,
                )
                return False

            if record.dispatch_status != "not_dispatched":
                logger.warning(
                    "start_dispatch: Duplicate dispatch attempt blocked for '%s'. Status: %s",
                    approval_id,
                    record.dispatch_status,
                )
                return False

            # 2. Insert into execution_ledger and update pending_approvals in a transaction
            try:
                await db.execute("BEGIN IMMEDIATE;")
                await db.execute(
                    """
                    INSERT INTO execution_ledger (
                        dispatch_id, approval_id, tool_id, argument_digest, state, dispatched_at
                    ) VALUES (?, ?, ?, ?, 'in_flight', ?)
                    """,
                    (dispatch_id, approval_id, tool_id, argument_digest, now_str),
                )
                up_cursor = await db.execute(
                    """
                    UPDATE pending_approvals
                    SET dispatch_status = 'in_flight', dispatched_at = ?
                    WHERE approval_id = ? AND dispatch_status = 'not_dispatched'
                    """,
                    (now_str, approval_id),
                )
                if up_cursor.rowcount == 0:
                    await db.execute("ROLLBACK;")
                    return False

                await db.commit()
                return True
            except Exception as exc:
                logger.warning(
                    "start_dispatch: Failed to reserve ledger entry for '%s': %s", approval_id, exc
                )
                try:
                    await db.execute("ROLLBACK;")
                except Exception:
                    pass
                return False

    async def complete_dispatch(
        self,
        approval_id: str,
        result_summary: str,
    ) -> None:
        """Mark transport dispatch as successfully completed."""
        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE execution_ledger
                SET state = 'completed', completed_at = ?, result_summary = ?
                WHERE approval_id = ?
                """,
                (now_str, result_summary[:500], approval_id),
            )
            await db.execute(
                """
                UPDATE pending_approvals
                SET dispatch_status = 'completed', completed_at = ?, result_summary = ?
                WHERE approval_id = ?
                """,
                (now_str, result_summary[:500], approval_id),
            )
            await db.commit()

    async def fail_dispatch(
        self,
        approval_id: str,
        error_message: str,
    ) -> None:
        """Mark transport dispatch as failed."""
        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE execution_ledger
                SET state = 'failed', completed_at = ?, error_message = ?
                WHERE approval_id = ?
                """,
                (now_str, error_message[:500], approval_id),
            )
            await db.execute(
                """
                UPDATE pending_approvals
                SET dispatch_status = 'failed', completed_at = ?, error_message = ?
                WHERE approval_id = ?
                """,
                (now_str, error_message[:500], approval_id),
            )
            await db.commit()

    async def mark_uncertain(
        self,
        approval_id: str,
        reason: str,
    ) -> None:
        """Mark transport dispatch outcome as UNCERTAIN after unexpected error or crash."""
        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                UPDATE execution_ledger
                SET state = 'uncertain', completed_at = ?, error_message = ?
                WHERE approval_id = ?
                """,
                (now_str, reason[:500], approval_id),
            )
            await db.execute(
                """
                UPDATE pending_approvals
                SET dispatch_status = 'uncertain', completed_at = ?, error_message = ?
                WHERE approval_id = ?
                """,
                (now_str, reason[:500], approval_id),
            )
            await db.commit()

    async def get_ledger_entry(
        self,
        tool_id: str | None = None,
        argument_digest: str | None = None,
        approval_id: str | None = None,
    ) -> dict[str, Any] | None:
        """Fetch an execution ledger entry by tool/digest or approval_id."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            if approval_id:
                async with db.execute(
                    "SELECT * FROM execution_ledger WHERE approval_id = ?",
                    (approval_id,),
                ) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else None
            elif tool_id and argument_digest:
                async with db.execute(
                    "SELECT * FROM execution_ledger WHERE tool_id = ? AND argument_digest = ?",
                    (tool_id, argument_digest),
                ) as cur:
                    row = await cur.fetchone()
                    return dict(row) if row else None
            return None

    # -----------------------------------------------------------------------
    # Durable Host Tool Policy Persistence (BRICK-005 Phase 6)
    # -----------------------------------------------------------------------

    async def save_host_tool_policy(
        self,
        tool_id: str,
        server_id: str,
        permission: str,
        enabled: bool,
        approved_fingerprint: str,
        policy_version: int,
        updated_by: str = "host_owner",
    ) -> None:
        """Persist or update host tool authorization policy durably."""
        await self.initialize()
        now_str = datetime.now(UTC).isoformat()

        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO host_tool_policies (
                    tool_id, server_id, permission, enabled, approved_fingerprint,
                    policy_version, updated_at, updated_by
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(tool_id) DO UPDATE SET
                    server_id = excluded.server_id,
                    permission = excluded.permission,
                    enabled = excluded.enabled,
                    approved_fingerprint = excluded.approved_fingerprint,
                    policy_version = excluded.policy_version,
                    updated_at = excluded.updated_at,
                    updated_by = excluded.updated_by
                """,
                (
                    tool_id,
                    server_id,
                    permission,
                    1 if enabled else 0,
                    approved_fingerprint,
                    policy_version,
                    now_str,
                    updated_by,
                ),
            )
            await db.execute(
                """
                INSERT INTO policy_metadata (key, value) VALUES ('policy_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(policy_version),),
            )
            await db.commit()

        logger.info(
            "Persisted host tool policy for '%s': tier=%s, enabled=%s, ver=%d",
            tool_id,
            permission,
            enabled,
            policy_version,
        )

    async def get_host_tool_policy(self, tool_id: str) -> dict[str, Any] | None:
        """Fetch persisted host policy for a single tool."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM host_tool_policies WHERE tool_id = ?",
                (tool_id,),
            ) as cur:
                row = await cur.fetchone()
                if not row:
                    return None
                rec = dict(row)
                rec["enabled"] = bool(rec["enabled"])
                return rec

    async def load_all_host_tool_policies(self) -> list[dict[str, Any]]:
        """Retrieve all persisted host tool policy records."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM host_tool_policies") as cur:
                rows = await cur.fetchall()
                results = []
                for r in rows:
                    rec = dict(r)
                    rec["enabled"] = bool(rec["enabled"])
                    results.append(rec)
                return results

    async def get_persisted_policy_version(self) -> int:
        """Retrieve current persisted host policy version revision counter."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT value FROM policy_metadata WHERE key = 'policy_version'"
            ) as cur:
                row = await cur.fetchone()
                if row and row[0]:
                    try:
                        return int(row[0])
                    except ValueError:
                        return 0
                return 0

    async def set_persisted_policy_version(self, version: int) -> None:
        """Set the persisted policy version counter."""
        await self.initialize()
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """
                INSERT INTO policy_metadata (key, value) VALUES ('policy_version', ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
                """,
                (str(version),),
            )
            await db.commit()

    async def cancel_pending_approvals_for_tool(
        self,
        tool_id: str,
        reason: str = "Host revoked tool permission to DENIED",
    ) -> int:
        """Invalidate and cancel all currently pending approvals for a specific tool.

        Prevents previously requested and interrupted tool calls from executing if host
        policy has been revoked.
        """
        await self.initialize()
        now_str = datetime.now(UTC).isoformat()
        async with aiosqlite.connect(self.db_path) as db:
            cur = await db.execute(
                """
                UPDATE pending_approvals
                SET status = 'cancelled', decision_at = ?, decision_by = 'host_policy_revocation',
                    rejection_reason = ?
                WHERE tool_id = ? AND status = 'pending'
                """,
                (now_str, reason, tool_id),
            )
            await db.commit()
            cancelled_count = cur.rowcount
            if cancelled_count > 0:
                logger.info(
                    "Cancelled %d pending approvals for tool '%s' due to revocation.",
                    cancelled_count,
                    tool_id,
                )
            return cancelled_count

    async def get_recent_ledger_entries(
        self,
        limit: int = 50,
        tool_id: str | None = None,
        state: str | None = None,
        server_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Return recent sanitized execution ledger records ordered by dispatch time."""
        await self.initialize()
        bounded_limit = max(1, min(limit, 100))
        query = """
            SELECT l.*, a.arguments_json
            FROM execution_ledger l
            LEFT JOIN pending_approvals a ON l.approval_id = a.approval_id
            WHERE 1=1
        """
        params: list[Any] = []
        if tool_id:
            query += " AND l.tool_id = ?"
            params.append(tool_id)
        if state:
            query += " AND l.state = ?"
            params.append(state)
        if server_id:
            query += " AND l.tool_id LIKE ?"
            params.append(f"{server_id}__%")
        query += " ORDER BY l.dispatched_at DESC LIMIT ?"
        params.append(bounded_limit)

        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(query, tuple(params)) as cur:
                rows = await cur.fetchall()
                results = []
                for r in rows:
                    row_dict = dict(r)
                    raw_args_json = row_dict.pop("arguments_json", None)
                    parsed_args: dict[str, Any] = {}
                    if raw_args_json:
                        try:
                            parsed_args = json.loads(raw_args_json)
                        except Exception:
                            parsed_args = {}
                    row_dict["arguments"] = redact_sensitive_value(parsed_args)
                    results.append(row_dict)
                return results

    async def get_approvals_summary(self) -> dict[str, int]:
        """Aggregate counts of human approvals across all states."""
        await self.initialize()
        counts: dict[str, int] = {
            "pending_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "expired_count": 0,
            "cancelled_count": 0,
            "total_count": 0,
        }
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT status, COUNT(*) FROM pending_approvals GROUP BY status"
            ) as cur:
                rows = await cur.fetchall()
                total = 0
                for status_name, cnt in rows:
                    total += cnt
                    key = f"{status_name}_count"
                    if key in counts:
                        counts[key] = cnt
                counts["total_count"] = total
        return counts

    async def close(self) -> None:
        """No persistent background connection pool needed for direct aiosqlite calls."""
        self._is_initialized = False
