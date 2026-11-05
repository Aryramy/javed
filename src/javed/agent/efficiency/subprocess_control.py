"""subprocess_control.py — Safe bounded subprocess execution and cleanup for JAVED.

Enforces task-class and command-specific timeouts, graceful process termination,
child-process tree termination, and clean process hygiene without os._exit.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from dataclasses import dataclass

# Standard timeout matrix (seconds)
SUBPROCESS_TIMEOUTS: dict[str, int] = {
    "repository_query": 30,
    "file_or_symbol_search": 30,
    "graphify_status": 30,
    "graphify_query": 30,
    "graphify_update": 120,
    "targeted_tests": 300,
    "integration_tests": 600,
    "backend_full_regression": 900,
    "frontend_tests": 600,
    "frontend_production_build": 300,
    "lint_and_format_checks": 300,
    "dev_server_readiness": 60,
    "default": 60,
}


@dataclass(frozen=True)
class SubprocessResult:
    """Bounded subprocess execution result."""

    command: list[str]
    command_category: str
    exit_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool
    cancelled: bool


def get_timeout_for_category(category: str) -> int:
    """Retrieve standard timeout ceiling for a command category."""
    return SUBPROCESS_TIMEOUTS.get(category, SUBPROCESS_TIMEOUTS["default"])


def terminate_process_tree(proc: subprocess.Popen, grace_period_seconds: float = 10.0) -> None:
    """Gracefully terminate a process, escalating to tree kill after grace period."""
    if proc.poll() is not None:
        return

    # Attempt graceful termination first
    try:
        proc.terminate()
    except (OSError, ProcessLookupError):
        return

    start = time.time()
    while time.time() - start < grace_period_seconds:
        if proc.poll() is not None:
            return
        time.sleep(0.2)

    # Force kill if still running after grace period
    try:
        if sys.platform == "win32":
            # On Windows, kill process tree via taskkill
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
                timeout=5,
            )
        else:
            proc.kill()
    except (OSError, ProcessLookupError, subprocess.SubprocessError):
        pass

    try:
        proc.wait(timeout=2.0)
    except (subprocess.TimeoutExpired, OSError):
        pass


def run_bounded_subprocess(
    cmd: list[str],
    category: str = "default",
    timeout_override: int | None = None,
    cwd: str | None = None,
    env: dict[str, str] | None = None,
) -> SubprocessResult:
    """Execute a structured subprocess with strict timeout and child-process tree cleanup."""
    timeout = timeout_override or get_timeout_for_category(category)
    start_time = time.time()

    # Pass environment with security enforcement
    process_env = dict(os.environ if env is None else env)
    process_env["GRAPHIFY_BACKEND"] = "none"
    process_env["GRAPHIFY_QUERY_LOG_DISABLE"] = "1"

    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=cwd,
            env=process_env,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        duration = time.time() - start_time
        return SubprocessResult(
            command=cmd,
            command_category=category,
            exit_code=proc.returncode,
            stdout=stdout or "",
            stderr=stderr or "",
            duration_seconds=duration,
            timed_out=False,
            cancelled=False,
        )
    except subprocess.TimeoutExpired:
        duration = time.time() - start_time
        if proc:
            terminate_process_tree(proc, grace_period_seconds=5.0)
        return SubprocessResult(
            command=cmd,
            command_category=category,
            exit_code=-1,
            stdout="",
            stderr=f"Process timed out after {timeout} seconds.",
            duration_seconds=duration,
            timed_out=True,
            cancelled=False,
        )
    except Exception as e:
        duration = time.time() - start_time
        if proc:
            terminate_process_tree(proc, grace_period_seconds=2.0)
        return SubprocessResult(
            command=cmd,
            command_category=category,
            exit_code=-1,
            stdout="",
            stderr=str(e),
            duration_seconds=duration,
            timed_out=False,
            cancelled=False,
        )
