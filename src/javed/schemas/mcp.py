"""Pydantic schemas and typed data models for the Model Context Protocol (MCP) subsystem."""

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

TransportType = Literal["stdio", "sse", "http"]
ConnectionState = Literal["disconnected", "connecting", "connected", "error"]
ToolPermission = Literal["denied", "allowed_read_only", "approval_required"]

SERVER_ID_REGEX = r"^[a-z0-9_\-]+$"
_SERVER_ID_PATTERN = re.compile(SERVER_ID_REGEX)

TOOL_ID_REGEX = r"^[a-z0-9_\-]+__[a-zA-Z0-9_\-]+$"
_TOOL_ID_PATTERN = re.compile(TOOL_ID_REGEX)


def validate_server_id(server_id: str) -> str:
    """Validate a server identifier. Must be lowercase alphanumeric, hyphens, or underscores."""
    if not isinstance(server_id, str):
        raise ValueError("server_id must be a string")
    stripped = server_id.strip()
    if not stripped:
        raise ValueError("server_id cannot be empty")
    if len(stripped) > 64:
        raise ValueError(f"server_id exceeds maximum length of 64 characters (got {len(stripped)})")
    if not _SERVER_ID_PATTERN.match(stripped):
        raise ValueError(
            f"Invalid server_id '{server_id}'. Must be lowercase alphanumeric, "
            f"hyphens, or underscores (pattern: {SERVER_ID_REGEX})"
        )
    return stripped


def build_namespaced_tool_id(server_id: str, tool_name: str) -> str:
    """Generate a stable, collision-safe namespaced tool identifier: {server_id}__{tool_name}."""
    valid_sid = validate_server_id(server_id)
    stripped_name = tool_name.strip()
    if not stripped_name:
        raise ValueError("tool_name cannot be empty")
    return f"{valid_sid}__{stripped_name}"


def parse_namespaced_tool_id(namespaced_id: str) -> tuple[str, str]:
    """Parse a namespaced tool ID into (server_id, original_tool_name)."""
    if "__" not in namespaced_id:
        raise ValueError(f"Invalid namespaced tool ID '{namespaced_id}'. Missing '__' delimiter.")
    parts = namespaced_id.split("__", 1)
    return validate_server_id(parts[0]), parts[1].strip()


def compute_tool_fingerprint(
    tool_name: str,
    description: str,
    input_schema: dict[str, Any] | None,
    output_schema: dict[str, Any] | None = None,
) -> str:
    """Generate a deterministic SHA-256 fingerprint for security-relevant tool metadata.

    Covers tool identity, description, and parameter/return schemas using canonical JSON.
    Any modification to the schema or description produces a different hash, triggering
    authorization invalidation.
    """
    canonical_payload = {
        "name": tool_name.strip(),
        "description": description.strip() if description else "",
        "input_schema": input_schema or {},
        "output_schema": output_schema or {},
    }
    encoded = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


class ServerConfig(BaseModel):
    """Host-controlled configuration for an approved MCP server."""

    server_id: str = Field(
        ..., description="Stable, host-assigned unique identifier (e.g., 'time')"
    )
    server_name: str = Field(..., description="Human-readable server name")
    transport_type: TransportType = Field("stdio", description="Underlying transport protocol")
    command: str = Field(..., description="Host-approved binary/executable to spawn (STDIO)")
    args: list[str] = Field(default_factory=list, description="Command line arguments")
    env: dict[str, str] = Field(default_factory=dict, description="Sanitized environment variables")
    cwd: str | None = Field(default=None, description="Working directory for the subprocess")
    enabled: bool = Field(True, description="Whether this server is enabled for connection")
    timeout_seconds: float = Field(
        30.0, ge=1.0, le=300.0, description="Operation timeout in seconds"
    )

    @field_validator("server_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        return validate_server_id(v)


class ServerStatus(BaseModel):
    """Runtime status and connection telemetry of an MCP server."""

    server_id: str
    server_name: str
    transport_type: TransportType
    connection_state: ConnectionState = "disconnected"
    protocol_version: str | None = None
    server_info: dict[str, Any] | None = None
    capabilities: dict[str, Any] | None = None
    discovered_tool_count: int = 0
    last_connected_at: datetime | None = None
    last_discovered_at: datetime | None = None
    last_error: str | None = None


class DiscoveredTool(BaseModel):
    """Metadata and security posture of a dynamically discovered MCP tool."""

    tool_id: str = Field(..., description="Namespaced tool ID: {server_id}__{tool_name}")
    server_id: str = Field(..., description="Originating server ID")
    original_name: str = Field(..., description="Raw tool name from MCP tools/list")
    description: str = Field("", description="Tool documentation/description provided by server")
    input_schema: dict[str, Any] = Field(default_factory=dict, description="JSON Schema for inputs")
    output_schema: dict[str, Any] | None = Field(None, description="Optional return schema")
    fingerprint: str = Field(..., description="SHA-256 fingerprint of identity and schemas")
    permission: ToolPermission = Field(
        "denied",
        description="Host-owned permission policy. Defaults strictly to 'denied'.",
    )
    enabled: bool = Field(
        False,
        description="Whether tool is enabled by host policy. Defaults strictly to False.",
    )
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    last_verified_at: datetime | None = None
    last_executed_at: datetime | None = None
    last_error: str | None = None


class ToolApprovalPolicy(BaseModel):
    """Host-owned approval record tracking verified tool fingerprint and authorized tier."""

    tool_id: str
    permission: ToolPermission
    approved_fingerprint: str
    approved_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    approved_by: str = "host_policy"


# ---------------------------------------------------------------------------
# Host Security Gateway Exception Hierarchy
# ---------------------------------------------------------------------------


class MCPGatewayError(Exception):
    """Base exception for host MCP security gateway errors."""


class MCPPermissionDeniedError(MCPGatewayError):
    """Raised when tool execution is denied by host policy (e.g. DENIED tier)."""


class MCPApprovalUnavailableError(MCPGatewayError):
    """Raised when a tool requires Human-in-the-Loop approval, not available in Phase 4."""


class MCPInputValidationError(MCPGatewayError):
    """Raised when model arguments fail full JSON Schema validation."""


class MCPServerTransportError(MCPGatewayError):
    """Raised when the MCP server subprocess transport or connection fails."""


class MCPToolExecutionError(MCPGatewayError):
    """Raised when the MCP server returns an execution-level error."""


class MCPOutputContractError(MCPGatewayError):
    """Raised when tool output violates the declared return schema."""


class MCPTimeoutError(MCPGatewayError):
    """Raised when tool execution exceeds the host-configured timeout limit."""
