"""Environment sanitization and credential isolation for MCP subprocesses."""

import os
from typing import Final

_ESSENTIAL_SYSTEM_VARS: Final[frozenset[str]] = frozenset(
    {
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "PATH",
        "PATHEXT",
        "COMSPEC",
        "TEMP",
        "TMP",
        "USERNAME",
        "USERPROFILE",
        "LOCALAPPDATA",
        "APPDATA",
    }
)

_SENSITIVE_PATTERNS: Final[tuple[str, ...]] = (
    "KEY",
    "SECRET",
    "TOKEN",
    "PASSWORD",
    "PASS",
    "AUTH",
    "CREDENTIAL",
    "OPENROUTER",
    "OPENAI",
    "ANTHROPIC",
    "GEMINI",
)


def get_sanitized_subprocess_env(extra_env: dict[str, str] | None = None) -> dict[str, str]:
    """Build a minimal, sanitized environment dictionary for MCP subprocesses.

    Explicitly excludes all private API keys, secrets, and auth tokens,
    forwarding only essential system runtime paths and explicit non-sensitive overrides.
    """
    clean_env: dict[str, str] = {}
    for var in _ESSENTIAL_SYSTEM_VARS:
        val = os.environ.get(var)
        if val is not None:
            clean_env[var] = val

    clean_env["PYTHONUNBUFFERED"] = "1"

    if extra_env:
        for k, v in extra_env.items():
            upper_k = k.upper()
            if any(p in upper_k for p in _SENSITIVE_PATTERNS):
                continue
            clean_env[k] = str(v)

    # Hard defense-in-depth: ensure sensitive patterns are strictly purged
    for k in list(clean_env.keys()):
        upper_k = k.upper()
        if any(p in upper_k for p in _SENSITIVE_PATTERNS):
            del clean_env[k]

    return clean_env
