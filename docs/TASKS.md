# Master Task Registry — JARVIS

> **Document ID**: `TASKS-001`  
> **Version**: 6.0 (Stage 3: BRICK-006 IN PROGRESS — Phase 0–1 Preflight & Evaluation Completed)  
> **Status**: ACTIVE  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 3 / BRICK-006 — Deterministic Playwright Browser & MCP Evaluation  
> **Last Revision**: 2026-10-28  

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
| **TASK-050** | BRICK-005 | Build 4-Tier Tool Sandbox, HITL Approval Modal & Initial MCP Integration | **VERIFIED** | Authorized by Owner on 2026-10-26 | Formally accepted by Project Owner on 2026-10-28. Phases 0–10 complete: 4-Tier sandbox, dynamic MCP registry (protocol 2026-07-28), 3-layer authorization, HITL approval modal, SQLite approvals ledger, argument redaction, full Developer & User Mode UI, partial-init teardown safety, full deterministic sweep (165 backend, 62 vitest, 0 ruff errors, 0 leak), REPORT-005 accepted. |
| **TASK-060** | BRICK-006 | Integrate Deterministic Playwright Browser, Playwright MCP Evaluation & Live Preview | **VERIFIED** | Authorized by Owner on 2026-10-28 | Formally accepted by Project Owner on 2026-10-29. Phases 0–10 complete: deterministic Python Playwright engine, 5 deterministic tools, SSRF & sensitive input guards, WebSocket preview streamer, @playwright/mcp 3-tier gateway evaluation, LangGraph agent binding, exactly-once approval resumption, 4/4 live OpenRouter tests, 224 backend pytests, 74 vitest tests, REPORT-006 accepted, merged into master (3110d62). |
| **TASK-070** | BRICK-007 | Implement Crawl4AI & Docling Extraction Pipeline | **IN PROGRESS** | Authorized by Owner on 2026-10-29 | Phase 6 Storage Manager & Metadata Registry Completed (13/13 storage tests, 168 extraction tests, 397/397 full regression tests passed, 0 leaks, $0.00 spend). Awaiting Phase 7 authorization. |
| **TASK-080** | BRICK-008 | Build Browser Use and Authenticated Navigation Subsystem | **NOT STARTED** | Requires BRICK-007 Verification | OpenCLI-based authenticated navigation with dedicated JAVED profiles, deterministic Playwright & Playwright MCP foundation, Stagehand eval-only, native owner takeover, redirect route checks, subresource guards, and single-use fail-closed approvals. Anti-bot/stealth/captcha-takeover bypasses removed by owner decision. |
| **TASK-090** | BRICK-009 | Build Persistent Memory, Fact Registry & Semantic RAG | **NOT STARTED** | Requires BRICK-008 Verification | Qdrant vector store with LangGraph orchestration, Mem0 eval-only, LangGraph Store/SQLite local structured memory, deterministic provenance-aware chunking, benchmarked English & Arabic embeddings, memory governance, and hash integrity. Urdu support removed by owner decision. |
| **TASK-100** | BRICK-010 | Build Managed Model Context Protocol (MCP) Server Ecosystem & UI Controls | **NOT STARTED** | Requires BRICK-009 Verification | Official & GitHub MCP registry discovery, JAVED Private Registry authority, SecureMCPGateway execution, Playwright/Time/GitHub/Context7 approved servers, conditional DBHub/Notion/MarkItDown, and 8-stage execution filter. Microsoft Fabric & Azure MCP removed by owner decision. |
| **TASK-110** | BRICK-011 | Implement Advanced Tasks, Specialized Subagents & Durable Execution | **NOT STARTED** | Requires BRICK-010 Verification | Deep Agents framework on LangGraph with 6 specialized subagents (Research, Document-Analysis, Analytics, Browser-Operator, Coding, Report-Generation), narrow tool allowlists, token/cost budgets, cancellation propagation, and parent authority. |
| **TASK-120** | BRICK-012 | Implement Real-Time English and Arabic Voice System | **NOT STARTED** | Requires BRICK-011 Verification | Bilingual voice (English and Arabic) with LiveKit transport, Silero VAD, faster-whisper STT, Kokoro English TTS, Piper fallback, benchmarked Arabic TTS, barge-in (< 50ms), and privacy controls. Urdu support removed by owner decision. |
| **TASK-130** | BRICK-013 | Production Hardening, PG Migration & Release Validation | **NOT STARTED** | Requires BRICK-012 Verification | Full test suite execution, PostgreSQL migration, authenticated browser-preview subscriptions, multi-user thread/session stream isolation, capability tokens, release audit report. |

---

## 3. Active Task Details (BRICK-005 In Progress)

### TASK-050: BRICK-005 Tool Registry, Permissions & MCP Integration
- **Status**: **`VERIFIED`** (Formally accepted by Project Owner on 2026-10-28)
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
    - Servers overview: Displays connection status, transport (`stdio`), negotiated protocol version (`2026-07-28`), discovered tools count, last discovery timestamp, and sanitized error messages.
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
- **Phase 9 Status**: **PROVISIONALLY ACCEPTED** (Pending Phase 9B Lifecycle & Evidence Gate).
- **Phase 9B Scope**: Windows Test Runner Lifecycle Hardening & Real Live Model Browser Acceptance Gate:
  - Critical Review of `os._exit(...)`:
    - Zero `os._exit` calls found in production code, tests, fixtures, or launch scripts.
    - Isolated root cause: unclosed `aiosqlite` worker threads in `tests/test_mcp_user_mode.py` due to missing fixture teardown.
    - Fixed fixture to `try: yield runtime finally: await runtime.close()` and closed runtime in `test_list_thread_approvals_api_endpoint`.
    - Enhanced `AgentRuntimeManager.close()` to cleanly disconnect and terminate MCP server adapters via supported async context managers (`await registry.disconnect_all()`).
    - Verified standard process teardown: 28/28 pytests pass in 4.03s with exit code 0 and zero retained handles.
  - Resume API Contract Check:
    - Hardened `resume_agent` and `resume_agent_execution` to reject swapped, ambiguous, or conflicting parameters.
    - Verified with dedicated unit test `test_resume_api_contract_validation` (PASSED).
  - Live OpenRouter Evidence Reconciliation:
    - Reconciled all 8 scenarios with OpenRouter `/auth/key` endpoint.
    - Total external spend today: $0.0085 USD (less than 1 cent) against planned $0.50 budget (1.7% utilized).
  - Real Live Model Browser Acceptance:
    - Built and executed `frontend/e2e/brick005_phase9b_live_model.spec.ts` in real Chrome.
    - Verified full real stack: React User Mode (Agent Mode) -> Real FastAPI -> Real Deep Agents -> Real OpenRouter `openai/gpt-4o-mini` -> Real `time__get_current_time` with `Asia/Qatar` -> Real Time MCP STDIO server -> Truthful Doha time synthesis in React.
    - Verified `ToolActivityCard` renders with status `COMPLETED` and no scripted-model substitution.
    - PASSED in 28.0s; incremental spend: $0.000276 USD (0.027 cents), within $0.10 limit.
- **Phase 10 Scope**: Final Polish, Full Regression Gate, Governance Synchronization & REPORT-005 Delivery:
  - Code Hardening:
    - Wrapped internal startup steps of `AgentRuntimeManager.initialize()` in `try ... except Exception: await self.close(); raise` to ensure partial-initialization rollback and zero leaked `aiosqlite` threads. Verified with dedicated test `test_partial_initialization_failure_teardown` (PASSED).
    - Hardened `resume_agent` and `resume_agent_execution` against swapped parameter pairs and thread mismatches, raising explicit `ValueError`. Verified with dedicated test in `test_mcp_user_mode.py` (PASSED).
    - Fixed fixture teardown in `tests/test_agent_api.py` (`test_app`) to ensure `await runtime.close()` is always called, resolving Python process shutdown hang on Windows (runs and exits in 2.79s).
  - Full Deterministic Quality & Regression Sweep:
    - 165/165 backend pytests PASSED in 141.80s with exit code 0 (`.\.venv\Scripts\python.exe -m pytest --ignore=tests/test_live_openrouter_mcp.py -v`).
    - 62/62 frontend Vitest tests PASSED across 12 files in 10.91s (`npm.cmd run test`).
    - 0 Ruff errors, 60 files formatted (`ruff check src tests` & `ruff format --check src tests`).
    - 0 Oxlint errors on 71 files (`npm.cmd run lint`).
    - Clean TypeScript/Vite production build in 0.99s (`npm.cmd run build`).
    - 0 orphaned `python.exe` MCP subprocesses verified via `Get-CimInstance Win32_Process`.
  - Governance Synchronization:
    - Reconciled Scenario F table in `BRICK-005.md` to truthfully reflect pre-model binding stripping by Layer 0/1.
    - Updated canonical 4-tier risk-to-MCP mapping in `BRICK-005.md` and explicitly noted out-of-scope boundaries (Filesystem, Shell, Playwright MCP).
    - Reconciled protocol version references consistently to `2026-07-28`.
    - Delivered authoritative milestone verification report `docs/reports/REPORT-005.md`.
    - Synchronized `AGENTS.md`, `PROGRESS.md`, `MEMORY.md`, and `ENVIRONMENT.md`.
- **Phase 10 Status**: **VERIFIED — READY FOR OWNER ACCEPTANCE**.
- **Final Milestone Status**: **`VERIFIED`** (Explicit Project Owner Sign-Off Granted 2026-10-28). BRICK-005 is formally complete. Fast-forward merge to `master` authorized.
- **Stop Condition**: Stage 3 / BRICK-006 is `NOT STARTED`. Mandatory Stop: Await explicit Project Owner authorization before initiating BRICK-006 Phase 0–1 preflight.


---

### TASK-060: BRICK-006 Deterministic Playwright Execution & Playwright MCP Evaluation
- **Status**: **VERIFIED** (Formally approved and accepted by Project Owner on 2026-10-29; Merge Commit `3110d62`)
- **Anchor Commit**: 1895072 (Verified BRICK-005 synchronized on master)
- **Working Branch**: feat/brick-006-playwright
- **Scope & Objectives**:
  - Implement deterministic Python Playwright automation subsystem (src/javed/browser/) with ephemeral context isolation (browser.new_context()).
  - Implement real-time low-latency viewport frame streamer over FastAPI WebSocket (/ws/browser) into React BrowserPreviewPanel.tsx.
  - Evaluate official Microsoft @playwright/mcp@0.0.83 server as an external Model Context Protocol integration under SecureMCPGateway.
  - Enforce zero-trust security: SSRF / private IP blocker, password & credit card input blocker, download quarantine, and zero leaked handles.
- **Phase 0 Status**: **COMPLETED**:
  - Baseline verification passed cleanly: 165/165 backend pytests passed in 142.21s; 62/62 frontend Vitest tests passed across 12 files in 12.08s.
  - Windows environment prerequisites verified: Python 3.12.15 in .venv, uv 0.13.3, Node.js v24.19.0, npm 11.17.0, system Chrome integration.
  - 0 orphaned subprocesses or retained handles.
- **Phase 1 Status**: **COMPLETED**:
  - Audited @playwright/mcp@0.0.83 via live STDIO JSON-RPC handshake.
  - Discovered and classified all 25 exposed tools under JARVIS's 3-tier host permission gateway:
    - DENIED (3 tools): browser_run_code_unsafe, browser_evaluate, browser_file_upload.
    - APPROVAL_REQUIRED (9 tools): browser_click, browser_fill_form, browser_type, browser_press_key, browser_select_option, browser_drop, browser_drag, browser_handle_dialog, browser_close.
    - ALLOWED_READ_ONLY (13 tools): browser_snapshot, browser_take_screenshot, browser_find, browser_console_messages, browser_network_requests, browser_network_request, browser_tabs, browser_wait_for, browser_navigate, browser_navigate_back, browser_resize, browser_emulate_media, browser_hover.
  - Formulated Dual / Hybrid Strategy: in-process Python Playwright for live viewport streaming and deterministic tool execution; @playwright/mcp for standardized MCP interoperability.
  - Authored comprehensive specification: docs/bricks/BRICK-006.md.
- **Delivered Phases**:
  - **Phase 2 Status**: **COMPLETED** (BrowserEngineManager, ephemeral contexts, 8/8 tests passed in 4.92s, 173/173 full regression passed, 0 leaks)
  - **Phase 3 Status**: **COMPLETED** (BrowserSecurityGuard, SSRF blocker, sensitive field detector, 12/12 security tests passed, 185/185 full regression passed, 0 leaks)
  - **Phase 4 Status**: **COMPLETED** (5 deterministic tools, Pydantic schemas, BrowserSession, argument redaction, 9/9 tests passed in 5.98s, 194/194 full regression passed, 0 leaks)
  - **Phase 5 Status**: **COMPLETED** (BrowserFrameStreamer, /ws/browser & /api/v1/ws/browser WebSocket endpoints, auto-pause zero-idle logic, 5/5 tests passed in 9.48s, 199/199 full regression passed, 0 leaks)
  - **Phase 6 Status**: **COMPLETED** (useBrowserStream hook, BrowserPreviewPanel, BrowserView integration, 12/12 Vitest tests passed, 74/74 full Vitest suite passed, clean Vite build)
  - **Phase 7 Status**: **COMPLETED** (@playwright/mcp server config, 3-tier policy constants, 10/10 gateway unit tests passed, 44/44 combined browser tests passed)
  - **Phase 8 Status**: **COMPLETED** (create_browser_tools_inventory, PositiveToolAllowlistMiddleware & assert_safe_tools browser support, AgentRuntimeManager browser binding & HITL click/fill gating, telemetry redaction, 8/8 tests passed in 3.41s, 52/52 combined browser tests passed)
  - **Phase 9 Status**: **COMPLETED** (Live OpenRouter browser acceptance suite, model-driven navigation & text extraction, multi-turn state retention, HITL interrupt/resume, budget reconciliation < $0.05, 4/4 tests passed in 23.22s)
  - **Phase 10 Status**: **COMPLETED**:
    - Implemented Phase 10 hardening and edge-case test suite in `tests/test_browser_agent_e2e.py` (7 new tests, 15/15 total passed):
      - Exactly-once browser tool execution across approval resumption with zero replay on duplicate decision attempts.
      - Rejection prevents tool dispatch and duplicate decision attempts fail-closed.
      - Cross-thread isolation rejecting approval decisions for mismatched thread IDs.
      - Cancellation flow preventing mutating browser tool execution.
      - Stale/expired approval rejection preventing mutating browser tool execution.
      - Unknown approval ID rejection and full cryptographic binding integrity in `ApprovalRecord`.
      - Checkpoint continuity without tool action duplication across subsequent conversational turns.
    - Completed formal production security audit of `AGENT_SYSTEM_PROMPT` change, verifying instructional vs enforcement separation, narrow browser tool scoping, and zero-trust fail-closed host layers.
    - Full project regression test gate:
      - 224/224 backend pytests PASSED in 164.86s with exit code 0 (`pytest --ignore=tests/test_live_openrouter_mcp.py --ignore=tests/test_live_openrouter_browser.py`).
      - 59/59 browser and Playwright MCP gateway tests PASSED in 40.55s.
      - 74/74 frontend Vitest tests PASSED across 13 test files in 13.79s.
      - 0 Ruff lint errors, 73 files formatted.
      - 0 Oxlint errors across 63 frontend files.
      - Clean TypeScript/Vite production build in 1.64s (`npm.cmd --prefix frontend run build`).
    - Subprocess leak audit: verified 0 dangling `chrome.exe`, `node.exe`, or `python.exe` processes via `Get-CimInstance Win32_Process`.
    - Zero `os._exit` calls across codebase.
    - Authored comprehensive verification report `docs/reports/REPORT-006.md`.
- **Milestone Status**: **`VERIFIED`** (Explicit Project Owner Sign-Off Granted 2026-10-29; Fast-Forward Merge to `master` Completed at `3110d62`).
- **Stop Condition**: Stage 4 / BRICK-007 is NOT STARTED. Mandatory Stop: Await explicit Project Owner preflight authorization before initiating BRICK-007.


---

### TASK-070: BRICK-007 Crawl4AI & Docling Extraction Pipeline
- **Status**: **IN PROGRESS** (Phase 3B Schema Integrity, Timeout Enforcement & Security Hardening Completed; Awaiting Phase 4 Authorization)
- **Anchor Commit**: 83cdeea (Verified BRICK-006 synchronized on master)
- **Working Branch**: feat/brick-007-extraction
- **Scope & Objectives**:
  - Implement dual-engine content extraction pipeline: Crawl4AI for web pages and Docling for local documents (PDF, DOCX, XLSX).
  - Design and enforce a unified intermediate schema (NormalizedDocument) capturing elements, structured tables, and page/bounding-box provenance.
  - Implement zero-trust security: file size limit (25 MB), page limit (200), MIME magic byte whitelist, archive expansion blocking, path traversal prevention, and pre-crawl SSRF IP gating (BrowserSecurityGuard).
  - Implement content hashing (SHA-256), SQLite deduplication registry, and incremental document versioning.
  - Expose LangChain agent tools (extract_web_page, extract_document, list_ingested_documents) gated under host permissions.
  - Expose FastAPI REST endpoints (/upload, /crawl, /documents) with streaming progress.
  - Build React Document Ingestion UI and Extraction Viewer in Developer/User modes.
- **Phase 0 Status**: **COMPLETED** (2026-10-29):
  - Verified clean master baseline at 83cdeea; branched feat/brick-007-extraction.
  - Dependency compatibility evaluation completed via uv pip compile: resolved 153 packages in 3.75s with zero conflicts on Windows 11 Python 3.12.15.
  - Documented offline fallback strategy (PdfFormatOption plus PyPdfiumDocumentBackend with model-backed stages disabled) when vision models or HuggingFace Hub are unreachable.
  - Designed canonical NormalizedDocument, ExtractionElement, TableRepresentation, and ElementProvenance Pydantic models (proposed for Phase 2 implementation in src/javed/extraction/schema.py).
  - Authored comprehensive specification: docs/bricks/BRICK-007.md.
  - Updated docs/decisions/ADR-006.md to ACCEPTED (PHASE 0 EVALUATED).
  - Enforced Phase 0 mandatory stop condition.
- **Phase 1 Status**: **COMPLETED** (2026-10-29):

  - Installed direct dependencies `crawl4ai>=0.9.0,<1.0.0` (0.9.5), `docling>=2.140.0,<3.0.0` (2.144.0), and `pypdfium2>=5.10.0,<6.0.0` (5.14.0) via `uv pip sync requirements.lock --torch-backend cpu`.

  - Pinned CPU-only PyTorch wheels (`torch==2.15.0+cpu`, `torchvision==0.29.2+cpu`), completely eliminating massive CUDA binaries.

  - Recorded hardware sandbox metrics: `.venv` size grew from 268.53 MB to 1445.09 MB (+1.15 GB), free disk space from 211.12 GB to 209.46 GB (-1.66 GB), memory load 93%. Process RSS at idle is 17.28 MB, reaching 374.55 MB with lightweight Docling initialized.

  - Implemented and verified `tests/test_extraction_smoke.py`: 5/5 passed (import compatibility, AsyncWebCrawler lifecycle and clean teardown, Docling lightweight initialization with HuggingFace download blocking, warm import time < 0.25s, thread hygiene).

  - Executed full project regression gate: 229/229 backend pytests passed in 192.12s.

  - Verified code quality: 0 Ruff errors, 74 files formatted.

  - Process teardown hygiene verified: 0 dangling Chromium, Node.js, Python, or Docling processes.

  - Enforced Phase 1 stop condition.

- **Phase 2 Status**: **COMPLETED** (2026-10-29):
  - Implemented canonical normalized extraction models in `src/javed/extraction/schema.py`: `NormalizedDocument`, `SourceDescriptor`, `ExtractorDescriptor`, `ExtractionElement`, `ElementProvenance`, `BoundingBox`, `TableRepresentation`, `MergedCell`, `TableCell`, `SectionReference`, `DocumentMetadata`, `ExtractionWarning`, `ExtractionError`, and `AuthenticatedSourceContext`.
  - Enforced zero runtime imports of `crawl4ai`, `docling`, `torch`, `torchvision`, `playwright`, OCR engines, or database modules.
  - Enforced zero import side-effects (zero threads, network sockets, file creations, or process spawns).
  - Implemented deterministic canonical serialization `to_canonical_json()` and non-circular output hashing `compute_canonical_sha256()`.
  - Enforced fail-closed unknown-field rejection (`extra="forbid"`) on all models.
  - Enforced strict UTC datetime validation across all timestamp fields.
  - Enforced 64-hex lowercase SHA-256 validation for `source_sha256`, `normalized_output_sha256`, and `extractor_config_sha256`.
  - Enforced absolute secrets prohibition: `AuthenticatedSourceContext` strictly rejects credentials, tokens, cookies, or profile paths; session references are opaque tokens.
  - Recorded OpenCLI architecture decision: candidate `jackwener/OpenCLI` assigned to BRICK-008.
  - Implemented 21 comprehensive deterministic unit tests in `tests/test_extraction_schema.py` (21/21 passed in 0.30s).
  - Executed full project regression gate: 250/250 backend pytests passed in 229.12s.
  - Verified code quality: 0 Ruff errors, 77 files formatted.
  - Process hygiene verified: 0 dangling Chromium, Node.js, Python, or Docling processes.
  - Enforced Phase 2 stop condition.
- **Phase 3B Status**: **COMPLETED & HARDENED** (2026-11-01):
  - Implemented extraction security guard and defensive input boundary in `src/javed/extraction/security.py`: `ExtractionSecurityGuard`, `QuarantineManager`, and `SecurityValidationDecision`.
  - Enforced 25 MB default and 50 MB hard ceiling file size validation via streaming consumption (`stage_stream`).
  - Implemented UUID-based isolated quarantine staging (`data/quarantine/`) with safe perms, directory traversal prevention, Windows reserved name sanitization, and atomic no-overwrite creation (`CREATE_NEW`).
  - Implemented MIME magic byte detection (`python-magic-bin` with binary fallback), rejecting ZIP bombs (uncompressed size > 250 MB or ratio > 100x), encrypted/password-protected ZIPs, and path traversal members.
  - Implemented lightweight PDF preflight via `pypdfium2` and heuristic raw PDF marker detection (`/Encrypt`, `/JavaScript`, `/Launch`, `/EmbeddedFiles`, page count limit <= 200).
  - Implemented HTML preflight with script/event-handler detection and safe classification (heuristic preflight notice recorded).
  - Hardened schema models (`src/javed/extraction/schema.py`):
    - Corrected false immutability naming by renaming `ImmutableExtractionBase` to `ExtractionBaseModel` (retaining backward-compatible alias).
    - Separated `normalized_content_sha256` (pure content/elements) and `extraction_record_sha256` (full extraction record lifecycle digest), with `normalized_output_sha256` alias.
    - Added `__setattr__` on `NormalizedDocument` to clear cached hashes before attribute assignment, completely eliminating stale digests.
    - Implemented deep immutability after finalization (`finalize()`, `ReadOnlyList`, `ReadOnlyDict`), strictly rejecting mutations on child models, list items, and dictionary entries.
    - Implemented unfinalized child-model hash invalidation via `_root_doc_ref` backreferences, clearing parent digests on nested mutation.
    - Implemented mandatory hash reverification before trust boundaries (`verify_trust_boundary()`, `assert_hash_integrity()`, `HashIntegrityError`).
    - Hardened `validate_document_contracts` to fail-closed on mismatched explicit hashes.
  - Hardened asynchronous timeout, concurrency, and cleanup guarantees:
    - Implemented active file tracking in `QuarantineManager` (`_active_files`, `cleanup_inspection`, `cleanup_all_active`, `is_inspection_active`).
    - Managed thread pool executor with bounded timeout in `validate_file`, guaranteeing immediate return without blocking on worker thread termination.
    - Implemented `validate_file_async` executing off event loop with `asyncio.wait_for` and guaranteed quarantine cleanup on timeout or cancellation.
    - Guaranteed semaphore release preventing deadlocks, with worker pool capacity preventing starvation from lingering cancelled tasks.
    - Enforced late promotion prevention: timed-out or cancelled inspections are verified via `is_inspection_active()` and strictly aborted with unlinking.
  - Implemented explicit inspection entry points (`validate_bytes`, `validate_stream`, `validate_local_file`, `validate_text`, `validate_html`, and async counterparts) to eliminate ambiguous string inference.
  - Implemented 74 comprehensive security tests in `tests/test_extraction_security.py` (74/74 passed in 3.55s) and 28 schema tests in `tests/test_extraction_schema.py` (28/28 passed in 0.31s).
  - Executed full project regression gate: 331/331 backend pytests passed.
  - Verified code quality: 0 Ruff errors, 79 files formatted.
  - Process hygiene verified: 0 dangling Chromium, Node.js, Python, or Docling processes.
  - Enforced Phase 3B stop condition.
- **Phase 3C Status**: **COMPLETED & VERIFIED** (2026-11-02):
  - Addressed nested mutation hash integrity and finalization contract:
    - Tested mandatory 10 mutation operations: `elements.append`, `elements.pop`, `elements[0].text = ...`, `metadata.title = ...`, `elements[0].provenance.page_number = ...`, `elements[0].table.rows[0][0].value = ...`, `warnings.append`, `errors.append`, `full_text = ...`, `full_markdown = ...`.
    - Proved in-place collection mutations (`append`, `pop`) modify lists directly, bypassing `NormalizedDocument.__setattr__` on unfinalized drafts; proved that stored digests on unfinalized drafts are unauthoritative.
    - Implemented live cryptographic reverification via `verify_hashes()` and `verify_hash_integrity()` using constant-time comparison (`hmac.compare_digest`): recomputes normalized-content and extraction-record digests from live state, catching stale hashes fail-closed.
    - Added structured verification reports via `HashVerificationResult` (supporting `structured=True` and `fail_closed=True`).
    - Added canonical entry points `compute_normalized_content_sha256()` and `compute_extraction_record_sha256()`.
    - Defined explicit trust boundary gates: mandatory verification before persistence, quarantine promotion, deduplication, cache reuse, version comparison, API response publication, BRICK-009 chunking, embedding generation, vector indexing, and agent handoff.
    - Adopted Preferred Integrity Model:
      - Mutable draft during extraction/pipeline assembly (`is_finalized == False`) with standard Python lists and dicts.
      - Explicit finalization via `doc.finalize()` computing canonical digests from live content/record.
      - Deep freezing into immutable representations (`ReadOnlyList`, `ReadOnlyDict`) across all nested models and collections.
      - Finalized documents reject all direct and nested mutations with `TypeError`.
    - Implemented `TableCell.value` property and setter, with recursive weak backreferences (`_root_doc_ref`) invalidating unfinalized root hashes on cell mutations.
    - Marked `ImmutableExtractionBase` as a deprecated compatibility alias scheduled for removal in Stage 5 / BRICK-013.
    - Added deterministic test suite: 35/35 schema tests in `tests/test_extraction_schema.py` (covering all 10 mutation operations, list append/pop, nested provenance, nested table cell, structured results, sensitivity matrix, order independence, JSON round-trip stability, serialization parity, and finalized immutability).
    - 74/74 security tests in `tests/test_extraction_security.py` passed.
    - 109/109 total targeted extraction tests passed in 3.35s.
    - Ruff check (0 errors) and ruff format (79 files) verified.
- **Phase 4 Status**: **COMPLETED & VERIFIED** (2026-11-02):
  - Implemented `src/javed/extraction/web.py` (`Crawl4AIWebExtractor`, `extract_url`, `validate_web_url`, `WebExtractionConfig`, `WebExtractionLimits`, `WebExtractionStrategy`):
    - Strict single-page policy: 1 page max, crawl depth 0, no recursive crawl, no sitemap expansion, no link following, no speculative prefetching.
    - Zero-trust URL & SSRF validation: HTTP/HTTPS only, blocked embedded credentials, stripped secret-bearing query params (`token`, `api_key`, `secret`, etc.), blocked RFC 1918, loopbacks, and cloud metadata (169.254.169.254).
    - Request-time and redirect-time enforcement: Playwright `page.route` with `route.fetch(max_redirects=0)` validating every redirect hop and subresource (images, scripts, stylesheets, iframes). Intercepted and closed WebSockets via `page.route_web_socket`. Blocked popups and downloads.
    - Dual execution modes: STATIC (non-browser HTTP GET with streaming body read up to 10 MB and redirect SSRF checks) and RENDERED (controlled dynamic browser rendering via `AsyncWebCrawler`).
    - Structured element extraction: ordered `ExtractionElement` stream with `SectionReference` hierarchy paths, `TableRepresentation` normalization with `MALFORMED_TABLE` warnings for irregular rows, discovered link sanitization (max 2,000 links, credentials/tokens stripped, internal/external classified).
    - Authentication and challenge defense: classified HTTP 401 as `AUTH_REQUIRED`, HTTP 403 as `ACCESS_DENIED`, HTTP 429 as `RATE_LIMITED` (honoring `Retry-After`), login forms (`<input type="password">`) as `AUTH_REQUIRED`, Cloudflare/CAPTCHA markers as `AUTOMATION_NOT_ALLOWED`. Zero credential handling, zero CAPTCHA bypass, zero stealth spoofing.
    - Resource limits: 10 MB main document, 25 MB total responses, character and element limits enforced.
    - Canonical schema integration: output mapped to `NormalizedDocument`, finalized via `finalize()` (digests generated, models and collections deeply frozen), verified against `verify_trust_boundary(doc)`.
    - Lifecycle management: idempotent `close()`, context manager, zero `os._exit`, zero process/thread leaks, zero model downloads, $0.00 external spend.
    - Test verification: 33/33 targeted web tests passed (`tests/test_extraction_web.py`), 109/109 schema and security regression tests passed (142 extraction tests total), 371/371 full regression suite passed, 0 ruff errors.
    - Live public test against `https://example.com` verified in both STATIC (0.16s) and RENDERED (1.52s) modes.
    - OpenCLI remains uninstalled and formally deferred to BRICK-008.
- **Phase 5 Status**: **COMPLETED & VERIFIED** (2026-11-02):
  - Implemented `src/javed/extraction/documents.py` (`DoclingDocumentExtractor`, `extract_document`, `extract_document_async`, `DocumentExtractionConfig`, `DocumentExtractionLimits`):
    - Multi-format local document understanding: PDF, Word DOCX, Excel XLSX.
    - 100% offline, zero HuggingFace model download execution via `NativePdfPipeline` and `PyPdfiumDocumentBackend`.
    - Hierarchical section heading breadcrumbs and section paths across document elements.
    - Deep table structure extraction with `TableRepresentation`, `TableCell`, row/col counts, sheet names, and markdown.
    - Element-level provenance with page numbers, sheet names, `POINTS` bounding boxes, and char spans.
    - Defensive boundary integration via `ExtractionSecurityGuard` preflight.
    - Resource limit enforcements (file size, page counts, element truncation).
    - Canonical `NormalizedDocument` contract, hash integrity, finalization, and trust boundary.
    - Clean async execution and idempotent resource teardown without leaks or `os._exit`.
    - 13/13 targeted document tests passed, 155 extraction tests passed, 384/384 full deterministic regression suite passed, 0 ruff errors, 0 process/thread leaks, $0.00 spend.
- **Phase 6 Status**: **COMPLETED & VERIFIED** (2026-11-02):
  - Implemented `src/javed/extraction/storage.py` (`ExtractionStorageManager`, `StorageConfig`, `StoredDocumentSummary`, `StoredExtractionRecord`, `StoredTableInfo`, `IngestionResult`):
    - SQLite database schema: `extraction_documents`, `extraction_records`, and `extraction_tables` tables with WAL mode, foreign keys, and busy timeout handlers.
    - Content deduplication via `normalized_content_sha256` and `source_sha256`: identical content reuses existing document entity and avoids duplicate raw source files.
    - Execution record deduplication via `extraction_record_sha256`: exact duplicate runs return cached result immediately without DB mutation.
    - Monotonic document versioning for evolving URLs with differing content: updates `version_count`, `current_version_id`, and `last_ingested_at`.
    - Safe quarantine promotion: atomically stages raw sources from `data/quarantine/` into `data/sources/{source_sha256}.ext` and purges quarantine file.
    - Atomic canonical JSON persistence: writes indentation-formatted, deterministic JSON representations to `data/extractions/{record_sha256}.json`.
    - Structured table artifact exports: exports individual table CSV and JSON files to `data/tables/{table_id}.csv` and `.json`.
    - Zero-trust boundary validation: documents must be finalized (`is_finalized=True`) and verified (`verify_trust_boundary(doc)`) before persistence and on reload.
    - Complete sync and async APIs: `store_document`/`store_document_async`, `get_document`/`get_document_async`, `load_normalized_document`/`load_normalized_document_async`, `delete_document`/`delete_document_async`.
    - Clean resource management, context managers, zero `os._exit`, zero process/thread leaks, and $0.00 spend.
    - 13/13 targeted storage tests passed, 168 extraction subsystem tests passed, 397/397 full deterministic regression tests passed, 0 ruff errors.
- **Phased Implementation Roadmap**:
  - **TASK-070-P1 (Phase 1)**: Dependency Installation & Hardware Sandbox — `VERIFIED`
  - **TASK-070-P2 (Phase 2)**: Normalized Extraction Schema & Pydantic Data Models — `VERIFIED`
  - **TASK-070-P3 (Phase 3)**: Security Guard, Quarantine & Whitelist Validator — `VERIFIED`
  - **TASK-070-P3B (Phase 3B)**: Schema Hash Integrity, Timeout Enforcement & Defensive Contract Hardening — `VERIFIED`
  - **TASK-070-P3C (Phase 3C)**: Nested Mutation Hash Integrity & Finalization Contract — `VERIFIED`
  - **TASK-070-P4 (Phase 4)**: Crawl4AI Web Extraction Subsystem — `VERIFIED`
  - **TASK-070-P5 (Phase 5)**: Docling Document Extraction Subsystem (PDF, DOCX, XLSX) — `VERIFIED`
  - **TASK-070-P6 (Phase 6)**: Storage Manager, Deduplication & Metadata Registry — `VERIFIED`
  - **TASK-070-P7 (Phase 7)**: LangChain Extraction Tools & Agent Runtime Integration
  - **TASK-070-P8 (Phase 8)**: REST API & Developer Mode Telemetry
  - **TASK-070-P9 (Phase 9)**: React Document Ingestion UI & Extraction Viewer
  - **TASK-070-P10 (Phase 10)**: Full Regression Gate, Hardening & REPORT-007 (TASK-080 preserved for BRICK-008)
- **Milestone Status**: **IN PROGRESS** (Phase 6 Completed and Verified; Awaiting Phase 7 Authorization).
- **Stop Condition**: Phase 6 Storage Manager, Deduplication & Metadata Registry complete. Mandatory Stop: Await explicit Project Owner review and Phase 7 authorization before authoring LangChain Extraction Tools & Agent Runtime Integration.


---

### TASK-080: BRICK-008 — Browser Use and Authenticated Navigation

- **Milestone**: BRICK-008
- **Status**: **NOT STARTED** (Requires BRICK-007 Verification and Owner Authorization)
- **Approved Stack**:
  - Primary deterministic browser foundation: Microsoft Playwright, Microsoft Playwright MCP, native JAVED browser tools, Browser Preview Panel.
  - Primary authenticated browser and session foundation candidate: OpenCLI (`opencli`) connecting to a dedicated JAVED Chrome profile.
  - Evaluation-only candidate: Stagehand (`stagehand`) for semantic element discovery where deterministic selectors fail.
  - Reference-only architecture: Browser Use (`browser-use`) for multi-step reasoning patterns (reference only; not a direct dependency).
  - Human takeover: Native JAVED owner takeover for MFA, passkeys, logins, and security challenges.
- **Responsibility Hierarchy**:
  1. *Deterministic Playwright / Playwright MCP*: Direct, predictable web automation and structured interactions.
  2. *OpenCLI*: Authenticated sessions via dedicated JAVED Chrome profile.
  3. *Stagehand*: Semantic element discovery when deterministic selectors fail.
  4. *Native Owner Takeover*: When human judgment, login, MFA, or CAPTCHA is required.
  5. *Browser Use*: Architecture and reasoning reference only.
- **OpenCLI Integration Boundary**:
  - Model never receives an unrestricted shell, raw CLI, or unrestricted everyday Chrome profile.
  - Flow: JAVED Agent -> `PositiveToolAllowlistMiddleware` -> Typed JAVED Authenticated-Browser Tool -> Owner, profile, domain, thread, run, and action policy -> Approval Gateway (where required) -> Argument and result redaction -> Constrained OpenCLI Adapter -> Dedicated JAVED Chrome Profile.
  - Dedicated profiles: `work-outlook`, `personal-outlook`, `work-gmail`, `personal-gmail`, `google-analytics`, `general-research`.
  - Profile bindings: owner identity, account alias, approved domains, allowed read actions, approval-required actions, browser session ID, connected timestamp, expiry state, revocation state.
- **Proposed Tools**:
  - *Read-Only*: `authenticated_page_read`, `authenticated_page_search`, `authenticated_page_extract`, `authenticated_page_list_links`, `mail_list_messages`, `mail_search_messages`, `mail_open_message`, `mail_read_conversation`, `analytics_read_page`, `analytics_extract_report`, `browser_owner_takeover`, `browser_session_status`, `browser_session_disconnect`.
  - *Approval-Required (Single-Use Fail-Closed HITL)*: `mail_download_attachment`, `mail_create_draft`, `mail_reply`, `mail_forward`, `mail_send`, `mail_move`, `mail_archive`, `mail_delete`, `authenticated_form_fill`, `authenticated_form_submit`, `browser_upload_file`, `browser_download_file`, `browser_change_setting`.
- **Session Security & Zero Secrets to Model**:
  - Dedicated profile, encrypted session metadata, OS-backed secret storage where available, domain-scoped use, session expiry detection, manual reauthentication, immediate revocation, secure deletion, owner-visible control indicator, authenticated preview subscriptions, per-thread and per-session stream isolation, exact resource teardown.
  - Model never receives cookies, raw Chrome profile data, browser storage, auth headers, login form values, auth-page DOM, sensitive screenshots, passkeys, recovery material.
  - During owner login / security challenges: pause model-visible DOM extraction and screenshots; transfer full control to owner; resume only after explicit owner approval; preserve exactly-once action semantics.
- **Mandatory Browser Security Follow-Up Criteria (Inherited from BRICK-006)**:
  - Redirect-destination validation (3xx), request-time private-network validation (RFC 1918 / loopback / link-local), DNS rebinding resistance, subresource interception, fetch/XHR destination enforcement, iframe destination enforcement, page WebSocket destination enforcement, download blocking or quarantine, authenticated preview subscriptions, thread/session isolation.
- **Explicit Exclusions (Owner Decision)**:
  - `beyahcuruk-del/captcha-takeover` — **REMOVED BY PROJECT OWNER DECISION**
  - `scrapfly/Antibot-Detector` — **REMOVED BY PROJECT OWNER DECISION**
  - `rebrowser/rebrowser-bot-detector` — **REMOVED BY PROJECT OWNER DECISION**
  - Stealth plugins, fingerprint spoofing, automated CAPTCHA solvers, residential proxy rotation, access-control circumvention.

---

### TASK-090: BRICK-009 — Persistent Memory and Semantic RAG

- **Milestone**: BRICK-009
- **Status**: **NOT STARTED** (Requires BRICK-008 Verification and Owner Authorization)
- **Approved Stack**:
  - Primary orchestration: LangGraph.
  - Canonical extraction input: BRICK-007 `NormalizedDocument`.
  - Primary vector-store candidate: Qdrant.
  - Personal-memory evaluation candidate: Mem0 (evaluation only).
  - Local structured-memory foundation: LangGraph Store, SQLite where appropriate during local development.
  - Reference-only memory project: `BjornMelin/enhanced-mem-vector-rag` (reference only; not a direct dependency).
  - Primary chunking: JAVED deterministic provenance-aware chunker.
  - Embeddings: Benchmark-selected English and Arabic embedding model.
  - Optional retrieval improvements: sparse lexical retrieval, metadata filtering, multilingual reranking.
- **Data Flow & Trust Boundary**:
  - `NormalizedDocument` -> integrity verification -> source authorization check -> document and version comparison -> deterministic chunking -> chunk hashing -> embedding generation -> Qdrant indexing -> provenance-aware retrieval -> reranking -> citation construction -> grounded answer.
  - No crawler, browser, mailbox reader, Docling converter, or MCP server may write directly to Qdrant. All indexed content must originate from a verified BRICK-007 `NormalizedDocument` or governed memory write.
- **Qdrant Responsibilities**:
  - Store: chunk ID, document ID, version ID, ingestion ID, element IDs, source type, source URI or safe reference, source title, section hierarchy, page/sheet provenance, source hash, normalized-content hash, chunk hash, embedding model and version, language, owner/tenant scope, access classification, retention state, deletion state.
  - Enforce on every search: owner/tenant isolation, source authorization, document status, version status, deletion state, language and metadata filters.
- **Memory Governance**:
  - Do not allow the model to persist arbitrary inferred facts automatically.
  - Memory schema: memory ID, owner ID, source, source-message/document reference, provenance, created timestamp, updated timestamp, verification state, retention policy, expiry, sensitivity classification, deletion state.
  - Categories: owner-stated fact, owner preference, project decision, verified system fact, document-derived fact, model inference. Model inferences must not silently become trusted owner facts.
  - Owner UI controls: list, inspect provenance, edit, delete, expire, export, disable auto-recall, clear by project/owner.
- **Hash and Version Rules**:
  - `source_sha256`: exact source-byte identity.
  - `normalized_content_sha256`: stable normalized content identity.
  - `extraction_record_sha256`: complete extraction-run record identity.
  - `chunk_sha256`: canonical chunk identity.
  - `embedding_config_sha256`: embedding model and configuration identity.
  - Do not re-embed unchanged content unless model, chunking policy, security classification, or metadata contract changes.
- **Evaluation Requirements**:
  - Benchmark English and Arabic separately for: semantic retrieval, mixed-language queries, exact-name retrieval, numbers and dates, table retrieval, heading retrieval, source citation accuracy, stale-version filtering, owner isolation, deletion propagation, latency, memory use, and index size.
- **Explicit Exclusions (Owner Decision)**:
  - Urdu language support — **REMOVED BY PROJECT OWNER DECISION** (Urdu-specific memory, embeddings, retrieval tests, rerankers, and voice requirements are strictly excluded).

---

### TASK-100: BRICK-010 — Managed Model Context Protocol (MCP) Ecosystem

- **Milestone**: BRICK-010
- **Status**: **NOT STARTED** (Requires BRICK-009 Verification and Owner Authorization)
- **Approved Control Plane**:
  - Primary public discovery: Official MCP Registry (`modelcontextprotocol/registry`).
  - Secondary discovery: GitHub MCP Registry.
  - Private authority: JAVED Private MCP Registry.
  - Execution: `SecureMCPGateway`.
  - Authorization states: `DENIED`, `ALLOWED_READ_ONLY`, `APPROVAL_REQUIRED`.
  - Public registry is a discovery source, not a trust authority.
- **MCP Admission Pipeline**:
  - Registry discovery -> publisher verification -> source repo inspection -> license review -> supply-chain audit -> version selection -> package hash -> isolated installation -> transport validation -> tool discovery -> schema fingerprinting -> security classification -> owner approval -> private-registry entry -> activation -> health monitoring -> revocation.
  - Unknown tools default to `DENIED`. Schema changes reset affected tools to `DENIED` pending re-review.
- **Initial Approved MCP Servers**:
  - Existing / Primary: Playwright MCP, Time MCP, GitHub MCP, Context7 MCP.
  - Conditional Future Candidates: DBHub, Notion MCP, MarkItDown MCP (must not be installed or enabled without a concrete use case, security review, and Project Owner authorization).
- **Explicitly Removed MCP Servers (Owner Decision)**:
  - Microsoft Fabric MCP Server — **REMOVED BY PROJECT OWNER DECISION**
  - Azure MCP Server — **REMOVED BY PROJECT OWNER DECISION**
- **Not Enabled by Default**:
  - Generic shell MCP, generic filesystem MCP, Desktop Commander, arbitrary remote MCP servers, unverified community servers, duplicate web/document servers, servers requiring broad unscoped credentials.
- **Private MCP Registry Record**:
  - Server ID, display name, publisher, repository, license, approved version, package location, package hash, transport, command and arguments, required env vars, sandbox profile, discovered tools, tool schema digests, permission states, owner approval, installation timestamp, last health check, revocation state, last security review. Never store secret values directly.
- **MCP Execution Controls**:
  - 8-stage filter: 1. Tool-construction filtering, 2. Pre-model schema filtering, 3. Execution-time authorization, 4. Secret redaction, 5. Output bounding, 6. Telemetry, 7. Execution ledger, 8. Process teardown. Single-use HITL for mutating operations. Individual tool classification.

---

### TASK-110: BRICK-011 — Advanced Tasks and Specialized Subagents

- **Milestone**: BRICK-011
- **Status**: **NOT STARTED** (Requires BRICK-010 Verification and Owner Authorization)
- **Approved Stack**:
  - Primary subagent framework: Deep Agents.
  - Orchestration: LangGraph.
  - Memory: BRICK-009 governed memory and RAG.
  - External tools: BRICK-010 managed MCP tools.
  - Approvals: Existing JAVED HITL system (`ApprovalStore`).
  - Persistence: Existing checkpointing (`SqliteSaver` / approved stores).
- **6 Planned Subagents**:
  1. **Research Subagent**: Public web extraction, read-only RAG, read-only approved MCP sources. Outputs source-backed research packet, citations, uncertainty and missing evidence.
  2. **Document-Analysis Subagent**: BRICK-007 normalized documents, BRICK-009 retrieval, table and provenance operations. Outputs structured document analysis, evidence references, extracted risks and findings.
  3. **Analytics Subagent**: Approved analytics data, SEO datasets, approved spreadsheets, RAG. Outputs metrics, anomalies, trends, recommendations, and source references.
  4. **Browser-Operator Subagent**: Deterministic Playwright, approved OpenCLI-backed tools, owner takeover, read-only operations by default. Outputs task result, browser evidence, action and approval ledger.
  5. **Coding Subagent**: Sandboxed repository operations, GitHub MCP, test runners, narrowly approved file operations. Outputs patch proposal, changed files, verification evidence, unresolved risks.
  6. **Report-Generation Subagent**: Retrieved evidence, approved document-generation tools, citation validator. Outputs structured draft report, source traceability, unsupported-claim warnings.
- **Subagent Contract**:
  - Every subagent receives: unique subagent ID, parent run ID, explicit task, detailed system instruction, explicit output schema, narrow tool allowlist, model selection, token budget, monetary budget, maximum steps, timeout, cancellation token, source-access policy, mutation policy, memory policy, retention policy.
  - Subagents must not automatically inherit all parent tools; no creating child subagents unless explicitly authorized.
- **Subagent Execution Rules**:
  - Parent remains authoritative; subagents return concise structured results; large intermediate outputs remain isolated; tool calls remain visible in telemetry; mutating operations remain approval-controlled; cancellation must propagate; failed subagents must not corrupt parent state; duplicate resumption must not duplicate actions; budget exhaustion stops subagent; output retains provenance; memory writes follow BRICK-009 governance; MCP access uses BRICK-010 permissions; browser access uses BRICK-008 controls.

---

### TASK-120: BRICK-012 — Real-Time English and Arabic Voice System

- **Milestone**: BRICK-012
- **Status**: **NOT STARTED** (Requires BRICK-011 Verification and Owner Authorization)
- **Approved Stack**:
  - Primary real-time media transport: LiveKit.
  - Primary voice activity detection (VAD): Silero VAD.
  - Primary local speech-to-text candidate: `faster-whisper`.
  - Primary English TTS candidate: Kokoro.
  - Lightweight fallback TTS candidate: Piper.
  - Arabic TTS: Benchmark-selected Arabic TTS engine.
  - Reference-only architectures: `S-P-A-C-E-B-A-R/VoxBigBrain`, `Madhurelision/AI_assist` (reference only; not direct dependencies).
- **Voice Pipeline**:
  - Browser microphone -> owner permission -> LiveKit room -> Silero VAD -> streaming audio segmentation -> faster-whisper -> language detection -> normalized transcript -> JAVED LangGraph agent -> response-language selection -> English or Arabic TTS router -> streaming synthesized audio -> LiveKit room -> browser speaker.
  - Barge-in: Silero VAD detects user speech while audio is playing -> LiveKit immediately mutes playback -> active agent generation cancelled -> user input collected.
- **Language Routing**:
  - English speech -> English STT -> English text response -> Kokoro (or Piper).
  - Arabic speech -> Arabic STT -> Arabic text response -> benchmarked Arabic TTS.
  - Mixed English and Arabic -> language detection chooses primary response language, matching TTS engine.
- **Arabic TTS Benchmark**:
  - Evaluate candidate Arabic TTS engines for: natural pronunciation, diacritics/tashkeel handling, latency to first audio chunk, real-time factor (RTF), CPU/GPU footprint, license, stability under continuous streaming.
- **Voice Session Security**:
  - Microphone access requires explicit owner authorization; visual recording/listening indicator; hardware/software mute; session timeout; audio stream ephemeral by default (in-memory only); no audio saved without approval; transcripts classified as user-private; no audio or transcripts sent to unauthorized third-party services; room tokens time-bounded, single-use, scoped to authorized session.
- **Proposed Voice Tools**:
  - *Read / Session-Control*: `voice_session_status`, `voice_get_active_language`, `voice_interrupt_output`, `voice_replay_last_response`, `voice_list_available_voices`, `voice_mute`, `voice_unmute`.
  - *Approval-Required*: `voice_enable_microphone`, `voice_record_session`, `voice_export_transcript`, `voice_send_transcript_to_external_service`, `voice_retain_audio`, `voice_retain_transcript`.
- **Acceptance Criteria (Evaluated Separately for English and Arabic)**:
  - Language detection, final transcript accuracy, partial transcript stability, names, dates, numbers, commands, mixed English and Arabic terms, response-language correctness, TTS naturalness, first-audio latency, end-to-end latency (< 1.2s), interruption latency (< 50ms), false interruption recovery, long-silence handling, noisy-room behavior, browser reconnect, microphone revocation, session cleanup, zero audio leakage, zero process leakage.
- **Explicit Exclusions (Owner Decision)**:
  - Urdu language support — **REMOVED BY PROJECT OWNER DECISION** (Urdu STT, TTS, fixtures, evaluation metrics, voices, routing, and acceptance criteria are completely removed).

---

## 4. Explicitly Removed Technologies & Architecture Decisions

In accordance with the **Owner Architecture Directive (2026-11-02)**, the following technologies, tools, and capabilities are explicitly removed from the planned JAVED architecture and task backlog:

1. **Microsoft Fabric MCP Server** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Enterprise cloud-specific scope outside core local-first and governed architecture; unapproved external SaaS dependency.
2. **Azure MCP Server** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Proprietary cloud-platform coupling violating FOSS-first, model-agnostic, and local-first architecture principles (Rule 1, Rule 4).
3. **beyahcuruk-del/captcha-takeover** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Security-challenge detection and human takeover must be implemented natively within JAVED (Rule 1, Rule 3, Rule 4); no unvetted external takeover wrappers.
4. **scrapfly/Antibot-Detector** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Stealth bot-detection evasion violates core operational constraints (human takeover, not security bypass); JAVED does not evade anti-bot measures.
5. **rebrowser/rebrowser-bot-detector** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Fingerprint spoofing and bot-detection patching violate Rule 4 and security principles; native owner takeover is the sole authorized path for security challenges.
6. **Urdu Language Support** — `REMOVED BY PROJECT OWNER DECISION`
   - *Rationale*: Voice, STT, TTS, memory, and RAG capabilities are formally bounded to English and Arabic to ensure acoustic quality, reliable diacritics/tashkeel handling, and high-fidelity benchmarked evaluation without unsupported models or synthetic artifacts.
