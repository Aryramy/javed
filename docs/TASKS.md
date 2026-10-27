# Master Task Registry — JARVIS

> **Document ID**: `TASKS-001`  
> **Version**: 4.0 (Stage 2: BRICK-004 Verified — BRICK-005 Phase 2 In Progress)  
> **Status**: ACTIVE  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 2 / BRICK-005 — Dynamic MCP Tool Discovery & Security Gateway  
> **Last Revision**: 2026-10-26  

---

## 1. Task Management & Tracking Protocol

1. **Authoritative State Rules**:
   - `NOT STARTED`: Task is scoped and defined, awaiting prerequisites.
   - `IN PROGRESS`: Actively being worked within approved boundaries.
   - `BLOCKED`: Awaiting external resolution, missing prerequisite, or user review.
   - `READY FOR ACCEPTANCE`: Implementation and verification evidence complete, awaiting user sign-off.
   - `VERIFIED`: Explicit user approval recorded in [PROGRESS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/PROGRESS.md).
2. **Stable Task IDs**: Task IDs are permanent and immutable.
3. **No Premature Advancements**: A task cannot move to `IN PROGRESS` until all listed blockers/prerequisites are marked `VERIFIED`.

---

## 2. Master Task Registry

| Task ID | Brick Target | Task Description | Status | Prerequisites / Blockers | Acceptance Criteria |
|---|---|---|---|---|---|
| **TASK-000** | Stage 0 | Bootstrap Stage 0 Documentation Foundation | **VERIFIED** | None | All core governance files, single source of truth, and templates established. |
| **TASK-001** | BRICK-000 | Author Architecture Decision Records (ADR-001 to ADR-007) | **VERIFIED** | TASK-000 | ADRs formulated covering backend, frontend, agent runtime, persistence, browser, extraction, and voice. |
| **TASK-002** | BRICK-000 | Refine Core Architecture & Planning Documents (PRD, ARCH, TECH, SEC, UI, TEST, ROADMAP, ENV) | **VERIFIED** | TASK-001 | Complete planning deliverables aligned with Version 2.0 requirements. |
| **TASK-003** | BRICK-000 | Author BRICK-000 Master Planning Specification & Review Report | **VERIFIED** | TASK-002 | `BRICK-000.md` finalized; all Markdown links verified; planning stop condition enforced. |
| **TASK-004** | BRICK-000 | Final Architecture Correction & Acceptance Audit (v2.2) | **VERIFIED** | TASK-003 | Corrected HITL, Sandboxing, Voice, and Budget architecture; owner approval recorded. |
| **TASK-010** | BRICK-001 | Author BRICK-001 Implementation Specification | **VERIFIED** | Requires BRICK-000 Owner Sign-Off | Detailed spec drafted in `docs/bricks/BRICK-001.md` covering uv, React, Tailwind, and shadcn/ui shell. |
| **TASK-011** | BRICK-001 | Implement Project Scaffolding & Live React UI Shell | **VERIFIED** | TASK-010 | Python 3.12 virtualenv via `uv`; Vite + React shell running with User/Dev mode, themes, and navigation; Vitest and test discovery pass. |
| **TASK-012** | BRICK-001 | Produce Verification Report REPORT-001 & Evidence | **VERIFIED** | Requires TASK-011 | Verification report published; automated verification harness passed (9/9 vitest, 1/1 pytest, 0 ruff errors, 0 oxlint errors); owner approval recorded. |
| **TASK-020** | BRICK-002 | Draft & Implement FastAPI WebSocket & SSE Gateway | **VERIFIED** | Requires BRICK-001 Verification | Real-time gateway connecting UI status bar with live backend server; 15 pytest, 24 vitest, 5 Playwright E2E passed. Approved by owner 2026-10-22. |
| **TASK-030** | BRICK-003 | Implement OpenRouter Adapter, Live Streaming Chat & Intelligent Auto Router | **VERIFIED** | Requires BRICK-002 Verification | Dynamic catalog, SSE streaming, assistant-ui runtime, OpenRouter Auto Router multi-tier routing, micro-cost accounting. 35 pytest, 35 vitest, 12 Playwright E2E passed. Formally approved by Project Owner on 2026-10-22. |
| **TASK-040** | BRICK-004 | Implement Deep Agents + LangGraph Runtime & Checkpointer | **VERIFIED** | Authorized by Owner on 2026-10-25 | Deep Agents harness with LangGraph cyclic execution, SQLite checkpointer, task planning via write_todos, 3-layer positive tool allowlist, thread validation, and concurrency serialization. 55 pytest, 41 vitest, 19 Playwright passed. Formally accepted by Project Owner on 2026-10-25. |
| **TASK-050** | BRICK-005 | Build 4-Tier Tool Sandbox, HITL Approval Modal & Initial MCP Integration | **IN PROGRESS** | Authorized by Owner on 2026-10-26 | Phase 0 & Phase 1 verified; Phase 2 (Dynamic MCP Registry) complete: langchain[mcp] 1.4.7 + mcp-server-time 2026.10.19 pinned, DynamicMCPRegistry implemented, default-deny gating, SHA-256 fingerprinting, change invalidation. Ready for review. |
| **TASK-060** | BRICK-006 | Integrate Deterministic Playwright Browser, Playwright MCP Evaluation & Live Preview | **NOT STARTED** | Requires BRICK-005 Verification | Scripted browser automation, Playwright MCP evaluation, and real-time viewport preview panel. |
| **TASK-070** | BRICK-007 | Implement Crawl4AI & Docling Extraction Pipeline | **NOT STARTED** | Requires BRICK-006 Verification | Web and multi-format document extraction with table and provenance support. |
| **TASK-080** | BRICK-008 | Integrate Intelligent Navigation using Browser Use | **NOT STARTED** | Requires BRICK-007 Verification | Vision-guided autonomous web exploration with safety guards. |
| **TASK-090** | BRICK-009 | Build Persistent Memory, Fact Registry & Semantic RAG | **NOT STARTED** | Requires BRICK-008 Verification | SQLite/sqlite-vec memory store with user CRUD drawer. |
| **TASK-100** | BRICK-010 | Build Managed Model Context Protocol (MCP) Server Ecosystem & UI Controls | **NOT STARTED** | Requires BRICK-009 Verification | Multi-server MCP management, runtime discovery, health monitoring, and Developer Mode UI toggles. |
| **TASK-110** | BRICK-011 | Implement Specialized Subagents & Durable Execution | **NOT STARTED** | Requires BRICK-010 Verification | Dynamic subagent spawning with isolated subgraphs and cancellation. |
| **TASK-120** | BRICK-012 | Implement Real-Time Multilingual Voice System | **NOT STARTED** | Requires BRICK-011 Verification | Trilingual voice (Urdu, English, Arabic) with auto language detection, low latency (< 1.2s), barge-in (< 50ms), provider-independent adapters, and empirical performance verification. |
| **TASK-130** | BRICK-013 | Production Hardening, PG Migration & Release Validation | **NOT STARTED** | Requires BRICK-012 Verification | Full test suite execution, PostgreSQL migration, release audit report. |

---

## 3. Active Task Details (BRICK-005 In Progress)

### TASK-050: BRICK-005 Tool Registry, Permissions & MCP Integration
- **Status**: `IN PROGRESS` (Phase 5: VERIFIED — READY FOR OWNER ACCEPTANCE)
- **Scope**:
  - Official LangChain MCP integration (`langchain[mcp]==1.4.7`) + `mcp-server-time==2026.10.19`.
  - Dynamic registry (`DynamicMCPRegistry`) in `src/javed/mcp/registry.py`.
  - Pydantic models for servers, discovered tools, fingerprints, policies, and gateway exceptions in `src/javed/schemas/mcp.py`.
  - Collision-safe namespacing (`time__get_current_time`, `time__convert_time`).
  - Strict default-deny security: all newly discovered tools set to `DENIED` and disabled.
  - Deterministic SHA-256 metadata fingerprinting and automatic change invalidation.
  - Subprocess environment sanitization purging all secrets and API keys.
  - Phase 3 Time MCP STDIO integration and isolated execution test harness (`tests/test_mcp_time_integration.py`).
  - Phase 4 Secure Host MCP Tool Gateway (`SecureMCPGateway`) in `src/javed/mcp/gateway.py`.
  - Three-Layer Authorization (Layer 1 model visibility, Layer 2 execution gating, Layer 3 fail-closed runtime inventory).
  - Canonical permission model (`DENIED`, `ALLOWED_READ_ONLY`, `APPROVAL_REQUIRED`).
  - Phase 5 Durable Human-in-the-Loop (HITL) Approval & Safe Agent Resumption:
    - Official LangGraph HITL middleware deduplication (`create_deep_agent(interrupt_on=...)` automatic installation of `HumanInTheLoopMiddleware`).
    - Durable SQLite storage for pending approvals and execution ledger in `data/approvals.db` via `ApprovalStore` (separate from `data/checkpoints.db`).
    - Full identity tuple, canonical sorted argument digest (`compute_argument_digest`), and metadata fingerprint drift tracking.
    - Duplicate dispatch protection and atomic dispatch reservation via `start_dispatch()` with `uncertain` status handling.
    - Pre-dispatch host permission revalidation.
    - Agent pause without database lock contention and official `Command(resume=...)` resumption.
    - Full SSE HITL event taxonomy (`approval_required`, `approval_approved`, `approval_rejected`, `approval_cancelled`, `agent_resumed`, `tool_started`, `tool_completed`).
    - User Mode minimal vertical slice in React (`ApprovalCard.tsx`, `ChatView.tsx`).
    - 27/27 HITL tests passed (`tests/test_mcp_hitl.py`), 70/70 backend MCP tests passed, 46/46 frontend Vitest tests passed.
  - Phase 6 Secure MCP Administration APIs, Host Policy Management & Minimal Live UI Verification (ACCEPTED):
    - FastAPI versioned administration endpoints under `/api/v1/mcp`:
      - `GET /servers`: Approved server list and connection states.
      - `GET /servers/{server_id}`: Single server connection and capability inspection.
      - `POST /servers/{server_id}/refresh`: Safe tool discovery refresh with schema drift detection.
      - `GET /tools`: Dynamic catalog with effective permission levels and host policy version.
      - `GET /tools/{tool_id}`: Full tool details, schemas, fingerprint, and active policy.
      - `POST /tools/{tool_id}/permission`: Privileged host mutation (`denied`, `allowed_read_only`, `approval_required`) guarded by optimistic concurrency (`expected_policy_version`), integrity verification (`expected_fingerprint`), and owner token authorization (`X-Javed-Owner-Token`).
      - `GET /ledger`: Bounded recent execution ledger records with argument digests and terminal states.
      - `GET /approvals/summary`: Aggregated counts across pending, approved, rejected, expired, and cancelled approvals.
      - `POST /auth/session`: Authenticates owner credential (`{"owner_token": "..."}`) and issues short-lived volatile session token (`jvd_sess_...`, 1 hour expiry); master token is NEVER leaked.
      - `GET /auth/session`: Reports session status (`authenticated`, `expires_in_seconds`) without leaking credentials.
      - `POST /auth/logout`: Revokes active session token immediately.
    - Local Owner Authorization, Anti-CSRF & Anti-DNS-Rebinding:
      - Validates loopback / trusted origins (`127.0.0.1`, `localhost`).
      - Validates HTTP `Host` header against loopback; rejects external DNS-rebinding hosts with 403 Forbidden.
      - Explicitly rejects `Origin: null` and `Sec-Fetch-Site: cross-site`.
      - Requires `X-Javed-Owner-Token` matching master secret OR valid unexpired session token matching client IP.
      - In production, rejects default owner tokens and fails closed on startup.
      - Master token never persisted in localStorage or bundled into client code.
    - Durable Policy Storage & Invalidation:
      - Persisted `host_tool_policies` and `policy_metadata` tables in `data/approvals.db`.
      - Restart safety: Restores permissions only if redisovered tool fingerprint matches persisted fingerprint; schema drift resets to `denied`.
      - Cross-process verification across 3 independent OS processes (`tests/test_mcp_policy_cross_process.py`).
      - Revocation invalidation: Transition to `denied` immediately cancels outstanding pending approvals for the tool.
    - Minimal Developer Mode UI:
      - `frontend/src/components/dev/MCPAdminPanel.tsx` integrated into `ConnectivityView.tsx`.
      - Includes local Owner Authentication card with password input, unlock, and lock/logout buttons.
      - Displays Time MCP server status, discovered tools, fingerprint/version metadata, and live permission mutation controls (disabled until unlocked).
    - Phase 6C Owner Credential Hardening & Test Evidence Reconciliation (ACCEPTED):
      - Predictable owner credentials completely eliminated:
        - `Settings.owner_token` defaults to `None`.
        - Strict validator rejects empty strings, whitespace, and known weak placeholders (`javed-local-owner-token`, `admin`, `password`, `secret`, `changeme`, etc.) with minimum length >= 8 characters.
        - Fail-closed behavior: If `JAVED_OWNER_TOKEN` is unset/missing, `POST /auth/session`, `GET /auth/session`, and permission mutations immediately fail closed with HTTP 401 Unauthorized.
        - Zero master secret exposure in React bundles, HTTP responses, or subprocess environments.
        - Test fixtures use explicit nonproduction credentials (`test-owner-token-123456789`) in isolated fixtures; never runtime defaults.
        - Laptop secret configuration documented in `.env.example` and `docs/ENVIRONMENT.md` without modifying `.env`.
      - Backend Test Inventory Reconciled:
        - Pytest `--collect-only -q` verified: exactly **149 collected backend tests** across 18 test files.
        - Reconciled discrepancy where previous report stated 145 collected but summed to 150.
        - Precise execution classification: **94 BRICK-005 milestone tests executed and verified** in this gate; **55 historical baseline tests collected** from BRICK-001–004.
    - Verification:
      - 22/22 targeted API security and admin tests passed (`tests/test_mcp_admin_api.py`).
      - 1/1 cross-process policy persistence test passed across 3 independent OS subprocesses (`tests/test_mcp_policy_cross_process.py`).
      - 71/71 other MCP regression tests passed (`tests/test_mcp_cross_process.py`, `tests/test_mcp_gateway.py`, `tests/test_mcp_registry.py`, `tests/test_mcp_time_integration.py`, `tests/test_mcp_hitl.py`).
      - 50/50 frontend Vitest tests passed (including `frontend/src/test/mcpAdmin.test.tsx`).
      - 1/1 Playwright Phase 6B live Chrome acceptance test passed (`frontend/e2e/brick005_admin.spec.ts`).
      - 2/2 Playwright Phase 5B HITL approve/reject tests passed (`frontend/e2e/brick005.spec.ts`).
      - Ruff lint and formatting passed (0 errors, 56 files formatted).
      - Frontend TypeScript/Vite build passed (`tsc -b && vite build` in 2.15s) with zero leaked secrets.
  - Phase 7 Complete React User Mode MCP Tool Interaction & Live Agent Experience (READY FOR REVIEW):
    - React User Mode tool activity presentation in `ChatView.tsx` via `ToolActivityCard.tsx`:
      - Displays tool identity (`tool_id`), MCP server identity (`server_id`), purpose description, and lifecycle status badge.
      - Canonical lifecycle taxonomy: `REQUESTED`, `AWAITING_APPROVAL`, `APPROVED`, `REJECTED`, `EXECUTING`, `COMPLETED`, `FAILED`, `CANCELLED`, `UNCERTAIN`.
      - Real elapsed duration in milliseconds (`${elapsed_ms}ms`) when start/completion timestamps are measured.
      - Expandable argument viewer with formatted JSON and sanitized result summary / error message.
      - Zero credential, private checkpoint, or sensitive environment variable exposure.
    - SSE Event Stream Correlation & In-Place Updates:
      - Backend correlation: `stream_agent_execution` tracks `pending_tool_call_ids` and binds `tool_call_id` across `tool_requested`, `tool_started`, `tool_completed`, and `tool_failed`.
      - `resume_agent_execution` binds `approval.tool_call_id` to resumed tool events.
      - Frontend correlation: `findToolActivityIndex` in `ChatView.tsx` matches by `tool_call_id`, `approval_id`, or in-flight active tool fallback.
      - Robust in-place updates eliminate duplicate tool cards on replayed/reconnected events.
    - Human-in-the-Loop Approval UI Integration:
      - Reused `ApprovalCard.tsx` with local submitting lock (`isBusy = isProcessing || localSubmitting`) to prevent double-click dispatches.
      - Atomic backend reservation via SQLite execution ledger (`start_dispatch()`).
      - Verified LangGraph resume on approval and clean execution cancellation on rejection.
    - Thread Recovery & State Reconstruction:
      - `GET /api/v1/agent/approvals/thread/{thread_id}` endpoint in `src/javed/api/v1/approvals.py`.
      - `get_thread_state` correlates LangGraph checkpoints (`AIMessage.tool_calls` and `ToolMessage`) and durable `ApprovalStore` records (`data/approvals.db`).
      - Page reload recovers pending approvals and completed tool cards faithfully without fabricating data.
    - Truthful Error Handling & Trust Boundaries:
      - Handles tool denied by policy, rejected by user, MCP transport error, invalid arguments, controlled server failure, and disconnection truthfully.
      - Never displays generic success badge on failure; displays exact error in red banner and message bubble.
    - Verification Matrix:
      - 5/5 real Chrome Playwright tests PASSED (`frontend/e2e/brick005_phase7.spec.ts`) across Scenarios A through E.
      - 26/26 backend pytests PASSED (`tests/test_mcp_user_mode.py` and `tests/test_mcp_admin_api.py`).
      - 57/57 Vitest frontend tests PASSED across 11 files (`frontend/src/test/toolActivity.test.tsx`, `frontend/src/test/approval.test.tsx`, etc.).
      - Ruff check and format passed (0 errors, 57 files formatted).
      - Frontend TypeScript/Vite production build passed (`tsc -b && vite build` in 2.63s).
- **Phase 7 Status**: **ACCEPTED** (Explicitly reviewed and approved by Project Owner on 2026-10-27).
- **Phase 8 Scope**: Complete Developer MCP Console, Execution Ledger & Live Diagnostics:
  - Developer MCP Console Architecture (`frontend/src/components/dev/MCPAdminPanel.tsx`):
    - Dedicated operational tabs: Overview, Servers, Tools, Ledger, Approvals, Diagnostics.
    - Servers overview: Displays connection status, transport (`stdio`), negotiated protocol version (`2024-11-05`), discovered tools count, last discovery timestamp, and sanitized error messages.
    - Authenticated Refresh Discovery action: Requires memory-only owner session, provides truthful execution progress and error reporting.
  - Tool Registry Explorer:
    - Lists discovered tools with namespaced IDs (`time__get_current_time`, `time__convert_time`), server ID, human descriptions, effective host policies, schema fingerprints, and collapsible JSON schemas.
    - Live search and permission/status filters.
  - Secure Permission Management:
    - Gated by Phase 6C memory-only owner authentication (`DENIED`, `ALLOWED_READ_ONLY`, `APPROVAL_REQUIRED`).
    - Optimistic concurrency version checks and schema fingerprint drift validation.
    - Immediate runtime cache invalidation; internal tools (`write_todos`) remain immutable.
  - Durable Execution Ledger Viewer:
    - Queries `GET /api/v1/mcp/ledger` with limit pagination and tool/state/server filters.
    - Displays dispatch ID, approval ID, tool ID, server ID, state badges, ISO timestamps, and duration (`${duration_ms.toFixed(1)}ms`).
    - Explicit UNCERTAIN handling: Displays amber warning banner noting that automatic retry is prohibited and manual inspection is required (NO retry button).
  - Approvals Overview:
    - Queries `GET /api/v1/mcp/approvals/summary` for aggregate pending, approved, rejected, cancelled counts.
    - Live refresh button and safe navigation link to active User Mode chat thread.
  - Live Diagnostics & Observability:
    - Real-time telemetry cards: FastAPI gateway, MCP server status, discovered tools count, approval store readiness, checkpoint store readiness, test mode status.
    - Zero secret leakage: Strict redaction ensures no API keys, tokens, or environment secrets appear in DOM or browser payloads.
  - Security Carryovers Addressed:
    - Concurrent same-tool event correlation: `src/javed/agent/runtime.py` tracks `run_to_tool_call_id` mapping LangChain `run_id` to initiating `tool_call_id`; `ChatView.tsx` enforces strict ID matching.
    - Test database isolation: Automated tests run against isolated temporary databases (`data/test_e2e_checkpoints.db`, `data/test_e2e_approvals.db`), preserving real SQLite databases.
    - Tool lifecycle robustness: Prevents terminal state overwrites from delayed SSE events and eliminates duplicate cards.
  - Verification Matrix:
    - 5/5 real Chrome Playwright tests PASSED (`frontend/e2e/brick005_phase8.spec.ts`) across Scenarios A through E in 2.0m.
    - 5/5 real Chrome Playwright Phase 7 regression tests PASSED (`frontend/e2e/brick005_phase7.spec.ts`) in 2.0m.
    - 27/27 backend pytests PASSED (`tests/test_mcp_admin_api.py` and `tests/test_mcp_user_mode.py`) in 4.67s.
    - 62/62 Vitest frontend tests PASSED across 12 files (`frontend/src/test/mcpConsolePhase8.test.tsx`, etc.) in 14.76s.
    - Ruff check & format passed (0 errors, clean format).
    - Frontend TypeScript/Vite production build passed (`tsc -b && vite build` in 2.71s).
- **Phase 8 Status**: **ACCEPTED** (Explicitly reviewed and approved by Project Owner on 2026-10-27).
- **Phase 9 Scope**: Live OpenRouter Model-Driven MCP Tool Selection, Intent Routing & Security Acceptance:
  - Model Catalog & Intent Routing:
    - Extended `ModelInfo` with `supports_tools: bool` and `supported_parameters: list[str]`.
    - Added catalog helpers `supports_tools(model_id)`, `get_model_info(model_id)`, and `get_best_tool_capable_model()`.
    - Incompatible model fallback: In `create_model()`, if requested model lacks structured tool calling support, safely routes to verified cheapest tool-capable model (`google/gemini-2.5-flash`).
    - Section 7 security guard: Strict host validation prohibiting server-hosted plugins (web, search, code); only local user MCP tools permitted.
  - Confidentiality & Argument Redaction:
    - Backend recursive redaction function `redact_sensitive_value` in `approval_store.py` masks secrets matching sensitive key and value patterns.
    - Preserves raw arguments in SQLite `pending_approvals` table for cryptographic digest integrity.
    - Redacts arguments before serialization in `GET /api/v1/mcp/ledger`, `GET /api/v1/agent/approvals/*`, and SSE events (`tool_requested`, `tool_started`, `approval_required`).
    - Added expandable arguments viewer in `MCPAdminPanel.tsx` (`data-testid="ledger-arguments-view"`).
  - Telemetry & Cost Accumulation:
    - Multiple `on_chat_model_end` events within a tool loop accumulate token counts and upstream inference costs from `usage_metadata` and `response_metadata`.
  - Protocol Version Reconciliation:
    - Live FastMCP / python-mcp / time-server handshake confirmed negotiating protocol version `2026-07-28`.
    - Corrected stale references across documentation, backend diagnostics, and Developer Console.
  - Verification Matrix:
    - 8/8 live OpenRouter pytests PASSED (`tests/test_live_openrouter_mcp.py`) covering Scenarios A through H.
    - 9/9 confidentiality & model routing pytests PASSED (`tests/test_mcp_confidentiality.py` and `tests/test_mcp_model_routing.py`) in 2.90s.
    - 27/27 backend pytests PASSED (`tests/test_mcp_admin_api.py` and `tests/test_mcp_user_mode.py`) in 4.35s.
    - 4/4 real Chrome Playwright tests PASSED (`frontend/e2e/brick005_phase9.spec.ts`) across Scenarios A through D in 1.6m.
    - 5/5 real Chrome Playwright Phase 8 regression tests PASSED (`frontend/e2e/brick005_phase8.spec.ts`) in 1.9m.
    - 62/62 Vitest frontend tests PASSED across 12 files in 15.68s.
    - Ruff check passed with 0 errors (`ruff check src tests`).
    - Frontend TypeScript/Vite production build passed (`tsc -b && vite build` in 2.13s).
- **Stop Condition**: Phase 9 Complete & READY FOR REVIEW. Mandatory Stop: Phase 9: READY FOR REVIEW, BRICK-005: IN PROGRESS, Phase 10: NOT STARTED. Await project owner explicit authorization before beginning Phase 10.

