"""Approved host-side MCP server configurations and factory utilities."""

import sys
from pathlib import Path

from javed.mcp.env import get_sanitized_subprocess_env
from javed.schemas.mcp import ServerConfig

TIME_SERVER_ID = "time"
TIME_SERVER_NAME = "Time Reference Server"


def find_time_server_command() -> tuple[str, list[str]]:
    """Determine the host-approved executable or module invocation for mcp-server-time.

    Prefers the compiled console script inside the current virtual environment,
    falling back to module dispatch via sys.executable.
    """
    scripts_dir = Path(sys.prefix) / "Scripts"
    exe_path = scripts_dir / "mcp-server-time.exe"
    if exe_path.exists():
        return str(exe_path), []

    bin_path = Path(sys.prefix) / "bin" / "mcp-server-time"
    if bin_path.exists():
        return str(bin_path), []

    return sys.executable, ["-m", "mcp_server_time"]


def create_time_server_config(
    server_id: str = TIME_SERVER_ID,
    server_name: str = TIME_SERVER_NAME,
    extra_env: dict[str, str] | None = None,
    timeout_seconds: float = 30.0,
) -> ServerConfig:
    """Create a validated ServerConfig for the official Time MCP reference server."""
    command, args = find_time_server_command()
    env = get_sanitized_subprocess_env(extra_env)
    return ServerConfig(
        server_id=server_id,
        server_name=server_name,
        transport_type="stdio",
        command=command,
        args=args,
        env=env,
        timeout_seconds=timeout_seconds,
        enabled=True,
    )
