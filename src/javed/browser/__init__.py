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
from javed.browser.streamer import BrowserFrameStreamer
from javed.browser.tools import (
    BrowserSession,
    ClickInput,
    ExtractTextInput,
    FillFormInput,
    NavigateInput,
    TakeScreenshotInput,
    create_browser_tools,
    redact_browser_tool_args,
)

__all__ = [
    "BrowserContextError",
    "BrowserEngineError",
    "BrowserEngineManager",
    "BrowserFrameStreamer",
    "BrowserInitializationError",
    "BrowserSecurityGuard",
    "BrowserSession",
    "ClickInput",
    "DangerousSchemeError",
    "ExtractTextInput",
    "FillFormInput",
    "NavigateInput",
    "SSRFBlockedError",
    "SecurityViolationError",
    "SensitiveFieldBlockedError",
    "SensitivityInspectionResult",
    "TakeScreenshotInput",
    "assert_safe_form_input",
    "create_browser_tools",
    "inspect_attributes_sensitivity",
    "inspect_locator_sensitivity",
    "mask_sensitive_value",
    "redact_browser_tool_args",
    "redact_sensitive_value",
]
