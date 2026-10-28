"""Approved host-side MCP server configurations and factory utilities."""

import shutil
import sys
from pathlib import Path

from javed.mcp.env import get_sanitized_subprocess_env
from javed.schemas.mcp import ServerConfig

TIME_SERVER_ID = "time"
TIME_SERVER_NAME = "Time Reference Server"

PLAYWRIGHT_MCP_SERVER_ID = "playwright"
PLAYWRIGHT_MCP_SERVER_NAME = "Playwright MCP Automation Server"

# Authoritative 3-tier security classification for @playwright/mcp tools
# Evaluated and approved in BRICK-006 Phase 1 (Section 7 of docs/bricks/BRICK-006.md)
PLAYWRIGHT_MCP_DANGEROUS_TOOLS: frozenset[str] = frozenset(
    {
        "browser_run_code_unsafe",
        "browser_evaluate",
        "browser_file_upload",
    }
)

PLAYWRIGHT_MCP_MUTATING_TOOLS: frozenset[str] = frozenset(
    {
        "browser_click",
        "browser_fill_form",
        "browser_type",
        "browser_press_key",
        "browser_select_option",
        "browser_drop",
        "browser_drag",
        "browser_handle_dialog",
        "browser_close",
    }
)

PLAYWRIGHT_MCP_READONLY_TOOLS: frozenset[str] = frozenset(
    {
        "browser_snapshot",
        "browser_take_screenshot",
        "browser_find",
        "browser_console_messages",
        "browser_network_requests",
        "browser_network_request",
        "browser_tabs",
        "browser_wait_for",
        "browser_navigate",
        "browser_navigate_back",
        "browser_resize",
        "browser_emulate_media",
        "browser_hover",
    }
)

DEFAULT_PLAYWRIGHT_MCP_ARGS: list[str] = [
    "--yes",
    "@playwright/mcp@0.0.83",
    "--browser",
    "chrome",
    "--isolated",
    "--headless",
]


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


def find_playwright_mcp_command() -> tuple[str, list[str]]:
    """Determine the host executable and default arguments for @playwright/mcp.

    On Windows, prefers npx.cmd (or npx.exe); on Unix-like systems, npx.
    """
    if sys.platform == "win32":
        npx_bin = (
            shutil.which("npx.cmd") or shutil.which("npx.exe") or shutil.which("npx") or "npx.cmd"
        )
    else:
        npx_bin = shutil.which("npx") or "npx"
    return str(npx_bin), list(DEFAULT_PLAYWRIGHT_MCP_ARGS)


def create_playwright_mcp_config(
    server_id: str = PLAYWRIGHT_MCP_SERVER_ID,
    server_name: str = PLAYWRIGHT_MCP_SERVER_NAME,
    args: list[str] | None = None,
    extra_env: dict[str, str] | None = None,
    timeout_seconds: float = 45.0,
    enabled: bool = True,
) -> ServerConfig:
    """Create a validated ServerConfig for the official @playwright/mcp server."""
    command, default_args = find_playwright_mcp_command()
    env = get_sanitized_subprocess_env(extra_env)
    return ServerConfig(
        server_id=server_id,
        server_name=server_name,
        transport_type="stdio",
        command=command,
        args=args if args is not None else default_args,
        env=env,
        timeout_seconds=timeout_seconds,
        enabled=enabled,
    )
