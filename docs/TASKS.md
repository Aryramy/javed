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
  - Phase 5B Final HITL Browser, Persistence & Security Verification Gate:
    - Real Chrome Playwright E2E verification (`frontend/e2e/brick005.spec.ts`): Approve and Reject browser scenarios passed against live React, live FastAPI, compiled LangGraph runtime, SQLite approvals/checkpoints, and live Time MCP STDIO server.
    - Genuine Cross-Process Isolation (`tests/test_mcp_cross_process.py`): Process A (PID 21876) paused and exited; Process B (PID 23876) recovered state, validated identities, approved, resumed execution, executed Time MCP server exactly once, and verified duplicate approval prevention.
    - Identity & Security Binding Check: Verified bindings for approval ID, thread ID, run ID, interrupt ID, tool-call ID, server ID, tool ID, argument digest, fingerprint, and policy version. Enforced positive origin allowlist and `Sec-Fetch-Site` validation.
- **Stop Condition**: Halt execution after Phase 5B verification. Mandatory Stop: Phase 5 VERIFIED — READY FOR OWNER ACCEPTANCE, BRICK-005 IN PROGRESS, Phase 6 NOT STARTED. Await project owner review and explicit authorization before beginning Phase 6.



