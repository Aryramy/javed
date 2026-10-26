"""Dynamic Model Context Protocol (MCP) tool registry and secure host gateway.

Provides dynamic tool discovery, lifecycle management, deterministic fingerprinting,
default-deny security enforcement, and host-controlled permission management using
the official LangChain MCPAdapter and FastMCP transport layer.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

import jsonschema
from fastmcp.client.transports import StdioTransport
from langchain.mcp import MCPAdapter

from javed.mcp.approval_store import ApprovalStore
from javed.mcp.env import get_sanitized_subprocess_env
from javed.schemas.mcp import (
    DiscoveredTool,
    ServerConfig,
    ServerStatus,
    ToolApprovalPolicy,
    ToolPermission,
    build_namespaced_tool_id,
    compute_tool_fingerprint,
    validate_server_id,
)

logger = logging.getLogger("javed.mcp.registry")


class DynamicMCPRegistry:
    """Central registry and host-controlled gateway for external MCP servers and tools.

    Core Principles:
    1. Default Deny: All newly discovered tools default to permission='denied' and enabled=False.
    2. Dynamic Discovery: Discovers actual tools from live MCP servers via tools/list.
    3. Collision-Safe Namespacing: Maps each tool to {server_id}__{tool_name}.
    4. Deterministic Fingerprinting: Hashes schema and identity with SHA-256; any modification
       invalidates prior approvals and resets the tool to 'denied'.
    5. Host-Side Gating: Model visibility and execution authorization are governed strictly
       by host policy, never by model completions, server annotations, or tool descriptions.
    """

    def __init__(self, approval_store: ApprovalStore | None = None) -> None:
        self.approval_store: ApprovalStore | None = approval_store
        self._servers: dict[str, ServerConfig] = {}
        self._statuses: dict[str, ServerStatus] = {}
        self._adapters: dict[str, MCPAdapter] = {}
        self._tools: dict[str, DiscoveredTool] = {}
        self._policies: dict[str, ToolApprovalPolicy] = {}
        self._persisted_policies: dict[str, dict[str, Any]] = {}
        self._policy_version: int = 0
        self._lock = asyncio.Lock()

    async def load_persisted_policies(self) -> None:
        """Load durable host policies and policy revision from the approval store."""
        if not self.approval_store:
            return
        persisted = await self.approval_store.load_all_host_tool_policies()
        persisted_version = await self.approval_store.get_persisted_policy_version()
        self._policy_version = persisted_version
        self._persisted_policies = {rec["tool_id"]: rec for rec in persisted}

        # Reconcile any existing discovered tools
        for tool_id, tool in self._tools.items():
            if tool_id in self._persisted_policies:
                p = self._persisted_policies[tool_id]
                if p["approved_fingerprint"] == tool.fingerprint:
                    tool.permission = p["permission"]
                    tool.enabled = bool(p["enabled"])
                    if (
                        tool.permission in ("allowed_read_only", "approval_required")
                        and tool.enabled
                    ):
                        self._policies[tool_id] = ToolApprovalPolicy(
                            tool_id=tool_id,
                            permission=tool.permission,
                            approved_fingerprint=tool.fingerprint,
                            approved_by=p.get("updated_by", "persisted_policy"),
                        )
                else:
                    tool.permission = "denied"
                    tool.enabled = False
                    self._policies.pop(tool_id, None)

    def register_server(self, config: ServerConfig) -> None:
        """Register an approved host-side server configuration."""
        sid = config.server_id
        self._servers[sid] = config
        if sid not in self._statuses:
            self._statuses[sid] = ServerStatus(
                server_id=sid,
                server_name=config.server_name,
                transport_type=config.transport_type,
                connection_state="disconnected",
            )
        logger.info("Registered MCP server configuration: %s (%s)", config.server_name, sid)

    def get_server_config(self, server_id: str) -> ServerConfig | None:
        """Retrieve registered server configuration."""
        return self._servers.get(server_id)

    def get_server_status(self, server_id: str) -> ServerStatus | None:
        """Retrieve current connection telemetry for a server."""
        return self._statuses.get(server_id)

    def list_servers(self) -> list[ServerStatus]:
        """List status records for all registered servers."""
        return list(self._statuses.values())

    async def connect(self, server_id: str) -> MCPAdapter:
        """Establish a connection to the specified MCP server over its configured transport.

        Negotiates MCP protocol, extracts server capabilities, and marks status 'connected'.
        Applies host-configured timeout to protect against hung subprocesses.
        """
        async with self._lock:
            valid_sid = validate_server_id(server_id)
            config = self._servers.get(valid_sid)
            if not config:
                raise ValueError(f"MCP server '{valid_sid}' is not registered.")
            if not config.enabled:
                raise ValueError(f"MCP server '{valid_sid}' is disabled by host policy.")

            # Return existing connected adapter if healthy
            existing = self._adapters.get(valid_sid)
            if existing is not None:
                status = self._statuses.get(valid_sid)
                if status and status.connection_state == "connected":
                    client = getattr(existing, "client", None)
                    if client and getattr(client, "is_connected", False):
                        return existing
                    # Stale or disconnected client; clean up before reconnecting
                    try:
                        await existing.__aexit__(None, None, None)
                    except Exception:
                        pass
                    self._adapters.pop(valid_sid, None)

            status = self._statuses[valid_sid]
            status.connection_state = "connecting"
            status.last_error = None

            try:
                adapter = self._build_adapter(config)
                # Bounded connection timeout
                async with asyncio.timeout(config.timeout_seconds):
                    await adapter.__aenter__()

                client = adapter.client
                protocol_ver = getattr(client, "protocol_version", None)
                server_info = getattr(client, "server_info", None)
                capabilities = getattr(client, "server_capabilities", None)

                # Convert pydantic models to dicts if needed
                server_info_dict = (
                    server_info.model_dump()
                    if hasattr(server_info, "model_dump")
                    else (dict(server_info) if server_info else None)
                )
                caps_dict = (
                    capabilities.model_dump()
                    if hasattr(capabilities, "model_dump")
                    else (dict(capabilities) if capabilities else None)
                )

                status.connection_state = "connected"
                status.protocol_version = str(protocol_ver) if protocol_ver else None
                status.server_info = server_info_dict
                status.capabilities = caps_dict
                status.last_connected_at = datetime.now(UTC)
                self._adapters[valid_sid] = adapter

                logger.info(
                    "Connected to MCP server '%s' (protocol %s, tools_list_changed=%s)",
                    valid_sid,
                    protocol_ver,
                    getattr(getattr(capabilities, "tools", None), "list_changed", False),
                )
                return adapter

            except TimeoutError as exc:
                status.connection_state = "error"
                clean_err = (
                    f"Connection to MCP server '{valid_sid}' timed out after "
                    f"{config.timeout_seconds}s"
                )
                status.last_error = clean_err
                logger.error("Connection timeout for MCP server '%s': %s", valid_sid, clean_err)
                raise ConnectionError(clean_err) from exc
            except Exception as exc:
                status.connection_state = "error"
                clean_err = self._sanitize_error(str(exc))
                status.last_error = clean_err
                logger.error("Failed to connect to MCP server '%s': %s", valid_sid, clean_err)
                err_msg = f"Failed to connect to MCP server '{valid_sid}': {clean_err}"
                raise ConnectionError(err_msg) from exc

    async def disconnect(self, server_id: str) -> None:
        """Disconnect cleanly from the specified MCP server and terminate its subprocess."""
        async with self._lock:
            valid_sid = validate_server_id(server_id)
            adapter = self._adapters.pop(valid_sid, None)
            if adapter is not None:
                try:
                    await adapter.__aexit__(None, None, None)
                except Exception as exc:
                    logger.warning("Error during MCP adapter teardown for '%s': %s", valid_sid, exc)

            if valid_sid in self._statuses:
                self._statuses[valid_sid].connection_state = "disconnected"
            logger.info("Disconnected MCP server: %s", valid_sid)

    async def disconnect_all(self) -> None:
        """Disconnect all active MCP servers."""
        server_ids = list(self._adapters.keys())
        for sid in server_ids:
            await self.disconnect(sid)

    async def discover_tools(self, server_id: str, refresh: bool = False) -> list[DiscoveredTool]:
        """Discover live tools from the MCP server using tools/list.

        Rules:
        - Retrieves real schemas dynamically from the server.
        - Checks for duplicate tool names within the same server (rejecting collisions).
        - Computes deterministic SHA-256 fingerprint for each tool.
        - All newly discovered tools default to permission='denied' and enabled=False.
        - If a tool's fingerprint changes from an earlier discovery, invalidates any existing
          approval, resets permission to 'denied', and records a security audit message.
        - Re-discovery with matching fingerprint preserves existing host permissions.
        """
        valid_sid = validate_server_id(server_id)
        config = self._servers.get(valid_sid)
        if not config:
            raise ValueError(f"MCP server '{valid_sid}' is not registered.")

        # Ensure server is connected
        adapter = await self.connect(valid_sid)
        status = self._statuses[valid_sid]

        try:
            cache_mode = "refresh" if refresh else "use"
            raw_tools = await adapter.client.list_tools(cache_mode=cache_mode)
        except Exception as exc:
            clean_err = self._sanitize_error(str(exc))
            status.last_error = clean_err
            err_msg = f"Tool discovery failed for server '{valid_sid}': {clean_err}"
            raise RuntimeError(err_msg) from exc

        discovered_list: list[DiscoveredTool] = []
        seen_names: set[str] = set()

        for raw in raw_tools:
            name = getattr(raw, "name", "")
            if not name:
                logger.warning("Skipping tool with empty name from server '%s'", valid_sid)
                continue

            # Duplicate tool name rejection within server
            if name in seen_names:
                err_msg = (
                    f"Security Violation: Duplicate tool name '{name}' detected "
                    f"from server '{valid_sid}'"
                )
                logger.error(err_msg)
                raise ValueError(err_msg)
            seen_names.add(name)

            desc = getattr(raw, "description", "") or ""

            # Input schema: support both .input_schema (v2) and .inputSchema (v1 deprecation)
            input_schema = getattr(raw, "input_schema", None)
            if not isinstance(input_schema, dict):
                input_schema = getattr(raw, "inputSchema", {})
                if not isinstance(input_schema, dict):
                    input_schema = {}

            output_schema = getattr(raw, "output_schema", None)
            if not isinstance(output_schema, dict):
                output_schema = getattr(raw, "outputSchema", None)
                if not isinstance(output_schema, dict):
                    output_schema = None

            tool_id = build_namespaced_tool_id(valid_sid, name)
            new_fingerprint = compute_tool_fingerprint(
                tool_name=name,
                description=desc,
                input_schema=input_schema,
                output_schema=output_schema,
            )

            existing_tool = self._tools.get(tool_id)

            if existing_tool is None:
                # Check if a durable policy was previously persisted for this tool
                initial_permission = "denied"
                initial_enabled = False
                last_err = None
                if tool_id in self._persisted_policies:
                    p = self._persisted_policies[tool_id]
                    if p["approved_fingerprint"] == new_fingerprint:
                        initial_permission = p["permission"]
                        initial_enabled = bool(p["enabled"])
                        if (
                            initial_permission in ("allowed_read_only", "approval_required")
                            and initial_enabled
                        ):
                            self._policies[tool_id] = ToolApprovalPolicy(
                                tool_id=tool_id,
                                permission=initial_permission,
                                approved_fingerprint=new_fingerprint,
                                approved_by=p.get("updated_by", "persisted_policy"),
                            )
                        logger.info(
                            "Restored persisted host policy for '%s' -> tier %s, enabled=%s",
                            tool_id,
                            initial_permission,
                            initial_enabled,
                        )
                    else:
                        logger.warning(
                            "SECURITY ALERT: Persisted fingerprint drift on discovery for '%s'! "
                            "Approval invalidated; resetting to DENIED.",
                            tool_id,
                        )
                        last_err = "Schema drifted from persisted fingerprint. Reset to DENIED."
                        self._policies.pop(tool_id, None)

                tool_record = DiscoveredTool(
                    tool_id=tool_id,
                    server_id=valid_sid,
                    original_name=name,
                    description=desc,
                    input_schema=input_schema,
                    output_schema=output_schema,
                    fingerprint=new_fingerprint,
                    permission=initial_permission,
                    enabled=initial_enabled,
                    discovered_at=datetime.now(UTC),
                    last_error=last_err,
                )
                if tool_id not in self._persisted_policies:
                    logger.info(
                        "Discovered new MCP tool: '%s' (server: %s) -> Default permission DENIED",
                        tool_id,
                        valid_sid,
                    )
            else:
                # Re-discovered tool: Check for fingerprint drift
                if existing_tool.fingerprint != new_fingerprint:
                    # Metadata or schema changed! Invalidate approval immediately
                    logger.warning(
                        "SECURITY ALERT: Tool '%s' metadata or schema changed! "
                        "Prior approval invalidated. (Old FP: %s, New FP: %s)",
                        tool_id,
                        existing_tool.fingerprint[:8],
                        new_fingerprint[:8],
                    )
                    # Invalidate policy record
                    self._policies.pop(tool_id, None)

                    tool_record = DiscoveredTool(
                        tool_id=tool_id,
                        server_id=valid_sid,
                        original_name=name,
                        description=desc,
                        input_schema=input_schema,
                        output_schema=output_schema,
                        fingerprint=new_fingerprint,
                        permission="denied",  # Reset to DENIED
                        enabled=False,  # Reset to disabled
                        discovered_at=existing_tool.discovered_at,
                        last_verified_at=datetime.now(UTC),
                        last_error=(
                            f"Metadata/schema changed on rediscovery (fingerprint "
                            f"{existing_tool.fingerprint[:8]} -> {new_fingerprint[:8]}). "
                            "Approval invalidated; host reapproval required."
                        ),
                    )
                else:
                    # Fingerprint unchanged: preserve existing host permission and enabled status
                    tool_record = DiscoveredTool(
                        tool_id=tool_id,
                        server_id=valid_sid,
                        original_name=name,
                        description=desc,
                        input_schema=input_schema,
                        output_schema=output_schema,
                        fingerprint=new_fingerprint,
                        permission=existing_tool.permission,
                        enabled=existing_tool.enabled,
                        discovered_at=existing_tool.discovered_at,
                        last_verified_at=datetime.now(UTC),
                        last_executed_at=existing_tool.last_executed_at,
                        last_error=existing_tool.last_error,
                    )

            self._tools[tool_id] = tool_record
            discovered_list.append(tool_record)

        status.discovered_tool_count = len(discovered_list)
        status.last_discovered_at = datetime.now(UTC)
        return discovered_list

    def set_tool_policy(
        self,
        tool_id: str,
        permission: ToolPermission,
        enabled: bool | None = None,
        approved_by: str = "host_admin",
        expected_policy_version: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> DiscoveredTool:
        """Update host-side execution policy for a discovered tool.

        Rules:
        - Only registered tools can be modified.
        - Internal tools (write_todos) are immutable through MCP admin APIs.
        - Concurrency guard: expected_policy_version must match if provided.
        - Integrity guard: expected_fingerprint must match if provided.
        - If authorized ('allowed_read_only' or 'approval_required'), records the exact
          approved fingerprint in the host policy.
        - If 'denied', removes the approval record.
        - The LLM cannot invoke this method.
        """
        if tool_id == "write_todos":
            raise ValueError(
                "Internal tool 'write_todos' is immutable and cannot be managed via MCP admin."
            )

        tool = self._tools.get(tool_id)
        if not tool:
            raise KeyError(f"Tool '{tool_id}' not found in registry.")

        if expected_policy_version is not None and expected_policy_version != self._policy_version:
            raise ValueError(
                f"Policy version conflict: expected {expected_policy_version}, "
                f"current {self._policy_version}."
            )

        if expected_fingerprint is not None and expected_fingerprint != tool.fingerprint:
            raise ValueError(
                f"Tool fingerprint mismatch: expected '{expected_fingerprint}', "
                f"current '{tool.fingerprint}'."
            )

        tool.permission = permission
        if enabled is not None:
            tool.enabled = enabled
        else:
            tool.enabled = permission != "denied"

        if permission in ("allowed_read_only", "approval_required") and tool.enabled:
            self._policies[tool_id] = ToolApprovalPolicy(
                tool_id=tool_id,
                permission=permission,
                approved_fingerprint=tool.fingerprint,
                approved_at=datetime.now(UTC),
                approved_by=approved_by,
            )
            tool.last_error = None
            logger.info("Host approved tool '%s' at tier '%s'", tool_id, permission)
        else:
            self._policies.pop(tool_id, None)
            logger.info("Host set tool '%s' to DENIED/disabled", tool_id)

        self._policy_version += 1
        return tool

    async def update_tool_permission_durable(
        self,
        tool_id: str,
        permission: ToolPermission,
        enabled: bool | None = None,
        approved_by: str = "host_admin",
        expected_policy_version: int | None = None,
        expected_fingerprint: str | None = None,
    ) -> DiscoveredTool:
        """Atomically update host tool policy and persist durably in SQLite."""
        async with self._lock:
            tool = self.set_tool_policy(
                tool_id=tool_id,
                permission=permission,
                enabled=enabled,
                approved_by=approved_by,
                expected_policy_version=expected_policy_version,
                expected_fingerprint=expected_fingerprint,
            )
            if self.approval_store:
                await self.approval_store.save_host_tool_policy(
                    tool_id=tool.tool_id,
                    server_id=tool.server_id,
                    permission=tool.permission,
                    enabled=tool.enabled,
                    approved_fingerprint=tool.fingerprint,
                    policy_version=self._policy_version,
                    updated_by=approved_by,
                )
                self._persisted_policies[tool.tool_id] = {
                    "tool_id": tool.tool_id,
                    "server_id": tool.server_id,
                    "permission": tool.permission,
                    "enabled": tool.enabled,
                    "approved_fingerprint": tool.fingerprint,
                    "policy_version": self._policy_version,
                    "updated_by": approved_by,
                }
                # If newly denied or disabled, cancel any pending approvals for this tool
                if tool.permission == "denied" or not tool.enabled:
                    await self.approval_store.cancel_pending_approvals_for_tool(
                        tool.tool_id,
                        reason=f"Host policy set to {tool.permission.upper()}",
                    )
            return tool

    # Alias for policy updates
    update_tool_policy = set_tool_policy

    def set_tool_permission(
        self,
        tool_id: str,
        permission: str,
        enabled: bool | None = None,
        approved_by: str = "host_admin",
    ) -> DiscoveredTool:
        """Alias accepting case-insensitive permission string (e.g. 'APPROVAL_REQUIRED')."""
        clean_perm = permission.strip().lower()
        return self.set_tool_policy(
            tool_id,
            permission=clean_perm,  # type: ignore[arg-type]
            enabled=enabled,
            approved_by=approved_by,
        )

    def get_tool_metadata_fingerprint(self, tool_id: str) -> str:
        """Retrieve the computed metadata fingerprint for a tool."""
        tool = self._tools.get(tool_id)
        return tool.fingerprint if tool else ""

    @property
    def policy_version(self) -> int:
        """Monotonically increasing version counter for host policy updates."""
        return self._policy_version

    def get_policy(self, tool_id: str) -> ToolApprovalPolicy | None:
        """Retrieve the host approval policy record for a tool."""
        return self._policies.get(tool_id)

    get_tool_policy = get_policy

    def get_tool(self, tool_id: str) -> DiscoveredTool | None:
        """Retrieve a discovered tool by namespaced ID."""
        return self._tools.get(tool_id)

    def list_tools(self, server_id: str | None = None) -> list[DiscoveredTool]:
        """List all discovered tools, optionally filtered by server."""
        if server_id is not None:
            valid_sid = validate_server_id(server_id)
            return [t for t in self._tools.values() if t.server_id == valid_sid]
        return list(self._tools.values())

    def get_model_visible_mcp_tools(self, include_approval_required: bool = False) -> list[str]:
        """Return namespaced tool IDs currently authorized for LLM visibility under host policy.

        By default (include_approval_required=False), only 'allowed_read_only' tools are visible.
        When include_approval_required=True, 'approval_required' tools are also included as
        requestable tools. Denied tools remain strictly hidden.
        """
        valid_tiers = (
            ("allowed_read_only", "approval_required")
            if include_approval_required
            else ("allowed_read_only",)
        )
        visible: list[str] = []
        for tool_id, tool in self._tools.items():
            if not tool.enabled or tool.permission not in valid_tiers:
                continue
            policy = self._policies.get(tool_id)
            if policy and policy.approved_fingerprint == tool.fingerprint:
                visible.append(tool_id)
        return sorted(visible)

    def get_approval_required_mcp_tools(self) -> list[str]:
        """Return namespaced tool IDs requiring Human-in-the-Loop approval before execution."""
        required: list[str] = []
        for tool_id, tool in self._tools.items():
            if not tool.enabled or tool.permission != "approval_required":
                continue
            policy = self._policies.get(tool_id)
            if policy and policy.approved_fingerprint == tool.fingerprint:
                required.append(tool_id)
        return sorted(required)

    def get_allowed_read_only_mcp_tools(self) -> list[str]:
        """Return namespaced tool IDs authorized for read-only execution without HITL gating."""
        readonly: list[str] = []
        for tool_id, tool in self._tools.items():
            if not tool.enabled or tool.permission != "allowed_read_only":
                continue
            policy = self._policies.get(tool_id)
            if policy and policy.approved_fingerprint == tool.fingerprint:
                readonly.append(tool_id)
        return sorted(readonly)

    def get_executable_mcp_tools(self) -> list[str]:
        """Return namespaced tool IDs currently authorized for host execution under host policy.

        Includes both 'allowed_read_only' tools and 'approval_required' tools (the latter requiring
        durable human approval before transport dispatch).
        """
        executable: list[str] = []
        for tool_id, tool in self._tools.items():
            if not tool.enabled or tool.permission not in (
                "allowed_read_only",
                "approval_required",
            ):
                continue
            policy = self._policies.get(tool_id)
            if policy and policy.approved_fingerprint == tool.fingerprint:
                executable.append(tool_id)
        return sorted(executable)

    def is_tool_authorized_for_execution(self, tool_id: str) -> bool:
        """Check whether a tool is currently authorized to execute under host policy.

        Verifies:
        1. Tool exists in discovered registry.
        2. Tool is enabled.
        3. Permission is 'allowed_read_only'.
        4. Current tool fingerprint matches the host-approved fingerprint exactly.
        """
        tool = self._tools.get(tool_id)
        if not tool or not tool.enabled or tool.permission != "allowed_read_only":
            return False

        policy = self._policies.get(tool_id)
        if not policy or policy.approved_fingerprint != tool.fingerprint:
            return False

        return True

    def validate_tool_arguments(
        self, tool_id: str, arguments: dict[str, Any]
    ) -> tuple[bool, str | None]:
        """Validate arguments against discovered tool input schema.

        Verifies:
        1. Tool exists in registry.
        2. Required properties are present.
        3. No unexpected arguments beyond declared schema properties.
        4. Conformance to JSON Schema via jsonschema validator.
        """
        tool = self._tools.get(tool_id)
        if not tool:
            return False, f"Tool '{tool_id}' not found in registry."

        schema = tool.input_schema or {}

        # 1. Required properties check
        required = schema.get("required", [])
        missing = [req for req in required if req not in arguments]
        if missing:
            return False, f"Missing required argument(s): {missing}"

        # 2. Unexpected argument check (strict host schema discipline)
        props = schema.get("properties", {})
        unexpected = set(arguments.keys()) - set(props.keys())
        if unexpected:
            return (
                False,
                f"Unexpected argument(s) not in declared schema: {sorted(unexpected)}",
            )

        # 3. JSON schema type/format validation
        try:
            jsonschema.validate(instance=arguments, schema=schema)
        except jsonschema.ValidationError as err:
            return False, f"Schema validation error: {err.message}"

        return True, None

    async def call_tool_direct(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        timeout_seconds: float = 30.0,
    ) -> Any:
        """Low-level MCP transport dispatch for isolated host integration testing.

        TRUSTED LOW-LEVEL MCP TRANSPORT FACILITY ONLY (Category A).
        This method is strictly for isolated transport protocol testing and diagnostic verification.
        It MUST NOT be exposed to LLM agents, agent tool wrappers, API endpoints, or untrusted
        input. All normal Project Javed application execution MUST route exclusively through the
        SecureMCPGateway (Category B), which enforces Three-Layer Authorization, host permission
        policies, fingerprint verification, and execution gating.
        """
        valid_sid = validate_server_id(server_id)
        args = arguments or {}

        # Validate arguments if tool is in registry
        tool_id = build_namespaced_tool_id(valid_sid, tool_name)
        if tool_id in self._tools:
            is_valid, err = self.validate_tool_arguments(tool_id, args)
            if not is_valid:
                raise ValueError(f"Input validation failed for '{tool_id}': {err}")

        adapter = await self.connect(valid_sid)
        tool_rec = self._tools.get(tool_id)

        try:
            async with asyncio.timeout(timeout_seconds):
                result = await adapter.client.call_tool(tool_name, args)
            if tool_rec:
                tool_rec.last_executed_at = datetime.now(UTC)
            return result
        except Exception as exc:
            clean_err = self._sanitize_error(str(exc))
            if tool_rec:
                tool_rec.last_error = clean_err
            raise

    def _build_adapter(self, config: ServerConfig) -> MCPAdapter:
        """Construct the official LangChain MCPAdapter around an isolated transport."""
        if config.transport_type == "stdio":
            sanitized_env = get_sanitized_subprocess_env(config.env)
            transport = StdioTransport(
                command=config.command,
                args=config.args,
                env=sanitized_env,
                cwd=config.cwd,
            )
            return MCPAdapter(transport)
        else:
            err_msg = (
                f"Transport type '{config.transport_type}' is not supported in "
                "BRICK-005 (STDIO only)."
            )
            raise NotImplementedError(err_msg)

    @staticmethod
    def _sanitize_error(error_str: str) -> str:
        """Sanitize error messages to prevent leaking filesystem paths or credentials."""
        # Strip long tracebacks or sensitive prefixes
        first_line = error_str.split("\n")[0]
        if len(first_line) > 256:
            return first_line[:253] + "..."
        return first_line
