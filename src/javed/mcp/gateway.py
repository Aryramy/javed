"""Authoritative host-controlled security gateway for Model Context Protocol (MCP) tools.

Enforces Three-Layer Authorization:
- Layer 1: Model-Visible Exposure Filtering (only verified ALLOWED_READ_ONLY tools reach the model).
- Layer 2: Execution-Time Authorization & Safety Limits (identity, fingerprint, schema, timeout).
- Layer 3: Runtime Inventory Validation (fail-closed graph and tool node verification).

This gateway is the SOLE authorized application execution interface between Project Javed's
agent runtime and external MCP servers.
"""

import asyncio
import json
import logging
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

import jsonschema
from langchain_core.tools import StructuredTool

from javed.agent.security import ALLOWED_TOOLS, EXCLUDED_TOOLS
from javed.mcp.approval_store import ApprovalStore
from javed.mcp.registry import DynamicMCPRegistry
from javed.schemas.approval import ApprovalRecord, compute_argument_digest
from javed.schemas.mcp import (
    DiscoveredTool,
    MCPApprovalUnavailableError,
    MCPInputValidationError,
    MCPOutputContractError,
    MCPPermissionDeniedError,
    MCPServerTransportError,
    MCPTimeoutError,
    MCPToolExecutionError,
    parse_namespaced_tool_id,
)

logger = logging.getLogger("javed.mcp.gateway")

# Context variable binding active human approval record to the execution task
current_approval_context: ContextVar[ApprovalRecord | None] = ContextVar(
    "current_approval_context", default=None
)


class SecureMCPGateway:
    """Central host-side security gateway governing all agent-to-MCP interactions."""

    def __init__(
        self,
        registry: DynamicMCPRegistry,
        approval_store: ApprovalStore | None = None,
    ) -> None:
        self.registry = registry
        self.approval_store = approval_store

    @property
    def policy_version(self) -> int:
        """Current policy revision from registry."""
        return self.registry.policy_version

    # -----------------------------------------------------------------------
    # Layer 1: Model-Visible Exposure Filtering
    # -----------------------------------------------------------------------

    def get_model_visible_tools(self, include_approval_required: bool = False) -> list[str]:
        """Return namespaced tool IDs currently authorized for LLM visibility under host policy.

        By default (include_approval_required=False), only 'allowed_read_only' tools are visible.
        When include_approval_required=True, 'approval_required' tools are also included as
        requestable tools. Denied tools remain strictly hidden.
        """
        return self.registry.get_model_visible_mcp_tools(
            include_approval_required=include_approval_required
        )

    def get_approval_required_tools(self) -> list[str]:
        """Return namespaced tool IDs that require Human-in-the-Loop approval before execution."""
        return self.registry.get_approval_required_mcp_tools()

    def get_allowed_read_only_tools(self) -> list[str]:
        """Return namespaced tool IDs authorized for execution without HITL gating."""
        return self.registry.get_allowed_read_only_mcp_tools()

    def is_model_visible(self, tool_id: str, include_approval_required: bool = False) -> bool:
        """Check if a specific tool is authorized to be visible to the model."""
        return tool_id in self.get_model_visible_tools(
            include_approval_required=include_approval_required
        )

    # -----------------------------------------------------------------------
    # Layer 2: Execution-Time Authorization & Verification
    # -----------------------------------------------------------------------

    def get_executable_tools(self) -> list[str]:
        """Return namespaced tool IDs currently authorized for host execution."""
        return self.registry.get_executable_mcp_tools()

    def verify_execution_eligibility(
        self,
        tool_id: str,
        arguments: dict[str, Any] | None = None,
        approval_record: ApprovalRecord | None = None,
    ) -> tuple[bool, str | None]:
        """Independently verify tool identity, server state, policy, fingerprint, and arguments.

        Checks performed:
        1. Namespaced identity resolution & delimiter validation.
        2. Server identity & enabled status in host registry.
        3. Discovered tool existence & enabled status.
        4. Canonical permission classification (ALLOWED_READ_ONLY or valid APPROVED record).
        5. Deterministic SHA-256 metadata fingerprint matching approved policy.
        6. Full JSON Schema input argument validation (field types, required, extra properties).

        Returns:
            (True, None) if authorized; (False, error_reason) if rejected.
        """
        # Context-var fallback if approval_record was not explicitly passed
        if approval_record is None:
            approval_record = current_approval_context.get()

        # 1. Identity resolution
        try:
            server_id, original_name = parse_namespaced_tool_id(tool_id)
        except Exception as exc:
            return False, f"Tool identity '{tool_id}' is invalid or not properly namespaced: {exc}"

        # 2. Approved server verification
        server_config = self.registry.get_server_config(server_id)
        if not server_config:
            return False, f"Server '{server_id}' is unknown or not registered by host policy."
        if not server_config.enabled:
            return False, f"Server '{server_id}' is disabled by host policy."

        # 3. Discovered tool existence
        tool = self.registry.get_tool(tool_id)
        if not tool:
            return False, f"Tool '{tool_id}' is not in discovered registry."

        # 4. Canonical permission classification
        if tool.permission == "denied" or not tool.enabled:
            return False, f"Tool '{tool_id}' is DENIED by host policy."

        if tool.permission == "approval_required":
            if approval_record is None:
                return False, (
                    f"Tool '{tool_id}' requires Human-in-the-Loop approval, "
                    "which is not available in Phase 4 (approval-not-available)."
                )
            if approval_record.status != "approved":
                return False, (
                    f"Tool '{tool_id}' approval record is in status '{approval_record.status}', "
                    "not 'approved'."
                )
            if approval_record.server_id != server_id:
                return False, (
                    f"Approval record server mismatch: expected '{server_id}', "
                    f"got '{approval_record.server_id}'."
                )
            if approval_record.tool_id != tool_id:
                return False, (
                    f"Approval record tool mismatch: expected '{tool_id}', "
                    f"got '{approval_record.tool_id}'."
                )
            if arguments is not None:
                digest = compute_argument_digest(arguments)
                if approval_record.argument_digest != digest:
                    return False, (
                        f"Approval argument digest mismatch for '{tool_id}'. "
                        "Arguments were modified after approval was granted."
                    )
            if approval_record.tool_fingerprint != tool.fingerprint:
                return False, (
                    f"Tool '{tool_id}' metadata fingerprint mismatch. "
                    "Schema drifted after human approval was granted."
                )
            if approval_record.dispatch_status not in ("not_dispatched", "in_flight"):
                return False, (
                    f"Approval record has dispatch status '{approval_record.dispatch_status}'. "
                    "Duplicate transport execution prevented."
                )
        elif tool.permission != "allowed_read_only":
            return False, f"Tool '{tool_id}' has unapproved permission tier '{tool.permission}'."

        # 5. Metadata fingerprint verification against host policy
        policy = self.registry.get_policy(tool_id)
        if not policy:
            return False, f"Tool '{tool_id}' lacks a valid host approval policy."
        if policy.approved_fingerprint != tool.fingerprint:
            return False, (
                f"Tool '{tool_id}' metadata fingerprint mismatch. "
                "Schema or documentation drifted; prior approval invalidated."
            )
        if tool.permission == "approval_required" and approval_record is not None:
            if approval_record.policy_version != self.policy_version:
                return False, (
                    f"Tool '{tool_id}' policy version mismatch. "
                    f"Approval granted under policy v{approval_record.policy_version}, "
                    f"current host policy is v{self.policy_version}."
                )

        # 6. JSON Schema input argument validation
        if arguments is not None:
            try:
                self.validate_arguments(tool, arguments)
            except MCPInputValidationError as err:
                return False, f"Input validation failed for '{tool_id}': {err}"

        return True, None

    def validate_arguments(self, tool: DiscoveredTool, arguments: dict[str, Any]) -> None:
        """Validate input arguments against the complete discovered JSON Schema."""
        schema = tool.input_schema or {}

        # 1. Required properties check
        required = schema.get("required", [])
        missing = [req for req in required if req not in arguments]
        if missing:
            raise MCPInputValidationError(f"Missing required argument(s): {missing}")

        # 2. Strict schema discipline: reject unexpected properties not defined in schema
        props = schema.get("properties", {})
        unexpected = set(arguments.keys()) - set(props.keys())
        if unexpected:
            raise MCPInputValidationError(
                f"Unexpected argument(s) not in declared schema: {sorted(unexpected)}"
            )

        # 3. Full JSON Schema type, constraint, enum, and nested structure validation
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as exc:
            raise MCPInputValidationError(f"Schema validation error: {exc.message}") from exc

    def validate_output(self, tool: DiscoveredTool, output_data: Any, raw_content: str) -> None:
        """Validate returned tool output against declared output schema if provided."""
        if tool.output_schema and isinstance(output_data, dict):
            try:
                jsonschema.validate(instance=output_data, schema=tool.output_schema)
            except jsonschema.ValidationError as exc:
                raise MCPOutputContractError(
                    f"Tool output violated return schema: {exc.message}"
                ) from exc

    async def execute_tool(
        self,
        tool_id: str,
        arguments: dict[str, Any] | None = None,
        timeout_seconds: float | None = None,
        approval_record: ApprovalRecord | None = None,
    ) -> str:
        """The sole authorized application execution interface for MCP tools.

        Applies full Layer 2 gating, connects to the MCP transport, invokes the real
        tool with bounded timeout, validates the response, records ledger telemetry,
        and revalidates host authorization immediately before transport dispatch.
        """
        args = arguments or {}
        if approval_record is None:
            approval_record = current_approval_context.get()

        # Layer 2 pre-execution check
        is_eligible, err_msg = self.verify_execution_eligibility(
            tool_id, args, approval_record=approval_record
        )
        if not is_eligible:
            err = err_msg or "Execution denied by host security gateway."
            if "DENIED" in err:
                raise MCPPermissionDeniedError(err)
            if "approval-not-available" in err:
                raise MCPApprovalUnavailableError(err)
            if "Input validation failed" in err:
                raise MCPInputValidationError(err)
            raise MCPPermissionDeniedError(err)

        server_id, original_name = parse_namespaced_tool_id(tool_id)
        server_config = self.registry.get_server_config(server_id)
        assert server_config is not None  # Guaranteed by verify_execution_eligibility

        tool = self.registry.get_tool(tool_id)
        assert tool is not None

        # Ledger reservation for approval_required tools (prevents duplicate dispatch)
        if (
            tool.permission == "approval_required"
            and approval_record is not None
            and self.approval_store is not None
        ):
            reserved = await self.approval_store.start_dispatch(
                approval_record.approval_id, tool_id, approval_record.argument_digest
            )
            if not reserved:
                raise MCPPermissionDeniedError(
                    f"Duplicate execution blocked: Approval '{approval_record.approval_id}' "
                    "is already in-flight or completed."
                )

        # Revalidate full host policy immediately before transport dispatch
        fresh_tool = self.registry.get_tool(tool_id)
        if not fresh_tool or fresh_tool.permission == "denied" or not fresh_tool.enabled:
            if (
                tool.permission == "approval_required"
                and approval_record is not None
                and self.approval_store is not None
            ):
                await self.approval_store.fail_dispatch(
                    approval_record.approval_id, "Policy revoked immediately before dispatch"
                )
            raise MCPPermissionDeniedError(
                f"Host policy revoked for tool '{tool_id}' immediately before transport dispatch."
            )

        # Bounded execution timeout
        timeout = timeout_seconds or server_config.timeout_seconds

        # Connect to transport
        try:
            adapter = await self.registry.connect(server_id)
        except Exception as exc:
            if (
                tool.permission == "approval_required"
                and approval_record is not None
                and self.approval_store is not None
            ):
                await self.approval_store.fail_dispatch(approval_record.approval_id, str(exc))
            raise MCPServerTransportError(
                f"Failed to connect to MCP server '{server_id}': {exc}"
            ) from exc

        # Execute genuine MCP tool over client
        try:
            async with asyncio.timeout(timeout):
                mcp_res = await adapter.client.call_tool(original_name, args)
        except TimeoutError as exc:
            err_text = f"Tool call to '{tool_id}' timed out after {timeout}s"
            tool.last_error = err_text
            if (
                tool.permission == "approval_required"
                and approval_record is not None
                and self.approval_store is not None
            ):
                await self.approval_store.fail_dispatch(approval_record.approval_id, err_text)
            raise MCPTimeoutError(err_text) from exc
        except Exception as exc:
            err_text = str(exc)
            tool.last_error = err_text
            if (
                tool.permission == "approval_required"
                and approval_record is not None
                and self.approval_store is not None
            ):
                # When dispatch outcome is unknown after crash/exception, record UNCERTAIN
                await self.approval_store.mark_uncertain(approval_record.approval_id, err_text)
            raise MCPToolExecutionError(f"MCP server execution error: {err_text}") from exc

        # Process server response
        if getattr(mcp_res, "is_error", False):
            error_content = ""
            if hasattr(mcp_res, "content") and mcp_res.content:
                error_content = " ".join(getattr(c, "text", str(c)) for c in mcp_res.content)
            tool.last_error = error_content
            if (
                tool.permission == "approval_required"
                and approval_record is not None
                and self.approval_store is not None
            ):
                await self.approval_store.fail_dispatch(approval_record.approval_id, error_content)
            raise MCPToolExecutionError(
                f"MCP server returned tool error for '{tool_id}': {error_content}"
            )

        # Extract text content
        raw_text = ""
        structured_data = getattr(mcp_res, "structured_content", None)
        if hasattr(mcp_res, "content") and mcp_res.content:
            raw_text = "\n".join(getattr(c, "text", str(c)) for c in mcp_res.content)

        # Output schema validation
        if tool.output_schema:
            data_to_validate = structured_data
            if data_to_validate is None and raw_text:
                try:
                    data_to_validate = json.loads(raw_text)
                except Exception:
                    data_to_validate = None
            if data_to_validate is not None:
                self.validate_output(tool, data_to_validate, raw_text)

        tool.last_executed_at = datetime.now(UTC)
        tool.last_error = None

        final_summary = raw_text or json.dumps(structured_data or {})
        if (
            tool.permission == "approval_required"
            and approval_record is not None
            and self.approval_store is not None
        ):
            await self.approval_store.complete_dispatch(approval_record.approval_id, final_summary)

        return final_summary

    def is_execution_authorized(self, tool_id: str) -> tuple[bool, str | None]:
        """Check whether a tool is currently authorized for execution (without arg validation)."""
        return self.verify_execution_eligibility(tool_id, arguments=None)

    # -----------------------------------------------------------------------
    # Layer 3: Runtime Inventory Validation & Tool Construction
    # -----------------------------------------------------------------------

    def build_langchain_tools(self) -> list[StructuredTool]:
        """Construct host-gated LangChain StructuredTools for currently authorized MCP tools.

        Each tool:
        - Uses the namespaced identity as its tool name ({server_id}__{tool_name}).
        - Binds the real JSON Schema as its input args_schema.
        - Routes execution strictly through self.execute_tool().
        """
        tools: list[StructuredTool] = []
        for tool_id in self.get_executable_tools():
            tool_rec = self.registry.get_tool(tool_id)
            if not tool_rec:
                continue

            # Closure capturing tool_id safely
            def _make_tool(tid: str, record: DiscoveredTool) -> StructuredTool:
                def _sync_raise(**kwargs: Any) -> Any:
                    raise NotImplementedError(
                        f"MCP tool '{tid}' must be invoked asynchronously via coroutine."
                    )

                async def _coro(**kwargs: Any) -> str:
                    return await self.execute_tool(tid, kwargs)

                return StructuredTool(
                    name=tid,
                    description=record.description,
                    args_schema=record.input_schema,
                    func=_sync_raise,
                    coroutine=_coro,
                )

            tools.append(_make_tool(tool_id, tool_rec))

        return tools

    def assert_safe_inventory(self, tools: list[Any]) -> None:
        """Verify that every tool in the runtime inventory is strictly authorized (Layer 3).

        Raises:
            PermissionError: If any unapproved tool or prohibited tool is detected.
        """
        allowed = set(ALLOWED_TOOLS) | set(self.get_executable_tools())

        for t in tools:
            name = getattr(t, "name", str(t))
            if name in EXCLUDED_TOOLS:
                raise PermissionError(
                    f"Security Violation: Prohibited tool '{name}' detected in agent inventory!"
                )
            if name not in allowed:
                raise PermissionError(
                    f"Security Violation: Unauthorized tool '{name}' in agent inventory. "
                    f"Permitted tools: {sorted(allowed)}"
                )
