"""Playwright browser automation and execution subsystem for Project Javed."""

from javed.browser.engine import (
    BrowserContextError,
    BrowserEngineError,
    BrowserEngineManager,
    BrowserInitializationError,
)
from javed.browser.security import (
    BrowserSecurityGuard,
    DangerousSchemeError,
    SecurityViolationError,
    SensitiveFieldBlockedError,
    SensitivityInspectionResult,
    SSRFBlockedError,
    assert_safe_form_input,
    inspect_attributes_sensitivity,
    inspect_locator_sensitivity,
    mask_sensitive_value,
    redact_sensitive_value,
)

__all__ = [
    "BrowserContextError",
    "BrowserEngineError",
    "BrowserEngineManager",
    "BrowserInitializationError",
    "BrowserSecurityGuard",
    "DangerousSchemeError",
    "SSRFBlockedError",
    "SecurityViolationError",
    "SensitiveFieldBlockedError",
    "SensitivityInspectionResult",
    "assert_safe_form_input",
    "inspect_attributes_sensitivity",
    "inspect_locator_sensitivity",
    "mask_sensitive_value",
    "redact_sensitive_value",
]
