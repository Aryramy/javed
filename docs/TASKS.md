# Master Task Registry — JARVIS

> **Document ID**: `TASKS-001`  
> **Version**: 2.4 (Stage 1 Active Baseline: BRICK-002 In Progress)  
> **Status**: ACTIVE  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 1 / BRICK-002 — FastAPI Integration & Real-Time Communication  
> **Last Revision**: 2026-10-22  

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
| **TASK-020** | BRICK-002 | Draft & Implement FastAPI WebSocket & SSE Gateway | **READY FOR ACCEPTANCE** | Requires BRICK-001 Verification | Real-time gateway connecting UI status bar with live backend server; 15 pytest, 24 vitest, 5 Playwright E2E passed. |
| **TASK-030** | BRICK-003 | Implement OpenRouter Adapter & Live Streaming Chat | **NOT STARTED** | Requires BRICK-002 Verification | Live LLM token streaming in assistant-ui thread with token/cost tracking. |
| **TASK-040** | BRICK-004 | Implement Deep Agents + LangGraph Runtime & Checkpointer | **NOT STARTED** | Requires BRICK-003 Verification | Cyclic state graph with SQLite checkpointing and reasoning visualizer. |
| **TASK-050** | BRICK-005 | Build 4-Tier Tool Sandbox & HITL Approval Modal | **NOT STARTED** | Requires BRICK-004 Verification | Pydantic tool validation, path sandboxing, and interactive approval modal. |
| **TASK-060** | BRICK-006 | Integrate Deterministic Playwright Browser & Live Preview | **NOT STARTED** | Requires BRICK-005 Verification | Scripted browser automation with real-time viewport preview panel. |
| **TASK-070** | BRICK-007 | Implement Crawl4AI & Docling Extraction Pipeline | **NOT STARTED** | Requires BRICK-006 Verification | Web and multi-format document extraction with table and provenance support. |
| **TASK-080** | BRICK-008 | Integrate Intelligent Navigation using Browser Use | **NOT STARTED** | Requires BRICK-007 Verification | Vision-guided autonomous web exploration with safety guards. |
| **TASK-090** | BRICK-009 | Build Persistent Memory, Fact Registry & Semantic RAG | **NOT STARTED** | Requires BRICK-008 Verification | SQLite/sqlite-vec memory store with user CRUD drawer. |
| **TASK-100** | BRICK-010 | Implement Model Context Protocol (MCP) Host Client | **NOT STARTED** | Requires BRICK-009 Verification | External tool discovery and invocation within isolated subprocesses. |
| **TASK-110** | BRICK-011 | Implement Specialized Subagents & Durable Execution | **NOT STARTED** | Requires BRICK-010 Verification | Dynamic subagent spawning with isolated subgraphs and cancellation. |
| **TASK-120** | BRICK-012 | Implement Real-Time Multilingual Voice System | **NOT STARTED** | Requires BRICK-011 Verification | Trilingual voice (Urdu, English, Arabic) with auto language detection, low latency (< 1.2s), barge-in (< 50ms), provider-independent adapters, and empirical performance verification. |
| **TASK-130** | BRICK-013 | Production Hardening, PG Migration & Release Validation | **NOT STARTED** | Requires BRICK-012 Verification | Full test suite execution, PostgreSQL migration, release audit report. |

---

## 3. Active Task Details (BRICK-002 Implementation)

### TASK-020: BRICK-002 FastAPI Backend & Real-Time UI Gateway
- **Status**: `READY FOR ACCEPTANCE`
- **Completed Scope**:
  - FastAPI backend foundation with Uvicorn, Pydantic v2, lifespan management (`src/javed/`).
  - REST endpoints: `/api/v1/health/live`, `/api/v1/health/ready`, `/api/v1/system/status`, `/api/v1/ping`.
  - WebSocket gateway `/api/v1/ws` with heartbeat, correlation IDs, typed envelope, connection manager.
  - Server-Sent Events `/api/v1/events` stream for diagnostic telemetry.
  - Typed React communication layer (REST + WS + connection status) in `frontend/src/services/` and `frontend/src/context/`.
  - Live UI features: Header backend indicator with RTT, Developer Mode Connectivity, Diagnostics, Logs.
  - Full automated tests: 15/15 pytest, 24/24 vitest, and 5/5 Playwright E2E browser tests on real Google Chrome.
  - REPORT-002.md delivery and documentation updates.
- **Stop Condition**: Halt execution when BRICK-002 is ready for acceptance and await project owner review. Do not begin BRICK-003.
