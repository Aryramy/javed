# BRICK-002: FastAPI Backend & Real-Time UI Communication

> **Brick ID**: `BRICK-002`  
> **Phase**: Phase 1 — Foundations & Core Capabilities  
> **Version**: 1.0 (Implementation Specification)  
> **Status**: `READY FOR ACCEPTANCE`  
> **Author**: Principal Full-Stack Engineer & System Architect  
> **Implementation Date**: 2026-10-22  
> **Report Reference**: [docs/reports/REPORT-002.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/reports/REPORT-002.md)  

---

## 1. Executive Summary & Objective

**BRICK-002** transforms the frontend-only UI shell from BRICK-001 into a true full-stack client-server application. It establishes a minimal, robust, secure FastAPI service coupled directly to the React control center through:

1. **REST Endpoints**: Typed health and status inspection (`/api/v1/health/live`, `/api/v1/health/ready`, `/api/v1/system/status`, `/api/v1/ping`).
2. **WebSocket Gateway**: Native Starlette bidirectional stream (`/api/v1/ws`) with typed JSON envelopes, heartbeat keep-alive, client correlation, and origin verification.
3. **SSE Telemetry Channel**: Lightweight server-to-client unidirectional broadcast (`/api/v1/events`) for broadcast telemetry without competing with WebSocket channels.
4. **Resilient Frontend Communication Layer**: Typed REST client (`apiService`) and robust WebSocket client (`WebSocketClient`) with jittered exponential backoff, connection state management, and React Context (`BackendProvider`).
5. **Mandatory Live UI Upgrades**:
   - Dynamic connection status badge with measured RTT in the global Header.
   - Interactive diagnostic test console in Developer Mode Diagnostics.
   - Real-time transport telemetry and heartbeat monitoring in Connectivity View.
   - Bounded event audit log stream in Logs View.
   - Truthful backend connection status in User Mode Chat View.
6. **End-to-End Verification**: 15/15 pytest unit tests, 24/24 Vitest unit tests, clean production builds, and 5/5 Playwright browser acceptance tests running against real Google Chrome.

---

## 2. Strict Scope Boundaries

Per project governance and Rule 5:
- **Included**: FastAPI application factory, lifespan management, CORS and request-body limits, Starlette WebSocket manager, SSE broadcaster, Pydantic v2 schemas, REST endpoints, frontend services and context, live UI components, automated testing, real browser E2E test suite.
- **Strictly Excluded**:
  - OpenRouter API integration (Deferred to BRICK-003).
  - AI reasoning, chat execution, and assistant-ui thread streaming (Deferred to BRICK-003).
  - Deep Agents, LangGraph, tool runtimes, HITL interrupt policies (Deferred to BRICK-004 / BRICK-005).
  - Web automation, Docling, ChromaDB, Whisper, MCP servers (Deferred to subsequent bricks).

---

## 3. Architecture & Contracts

### 3.1 REST API Surface (`/api/v1`)

| Endpoint | Method | Response Schema | Purpose |
|---|---|---|---|
| `/api/v1/health/live` | `GET` | `LiveResponse` | Process liveness check (`status: "live"`) |
| `/api/v1/health/ready` | `GET` | `ReadyResponse` | Dependency readiness (`status: "ready"`, transport checks) |
| `/api/v1/system/status` | `GET` | `SystemStatusResponse` | App metadata, uptime, version, honest capability matrix |
| `/api/v1/ping` | `GET` | `PingResponse` | Sub-5ms round-trip latency probe (`"message": "pong"`) |

### 3.2 WebSocket Surface (`/api/v1/ws`)

- **Protocol**: JSON-serialized `EventEnvelope` (`event_type`, `schema_version`, `correlation_id`, `timestamp`, `payload`).
- **Heartbeat Contract**:
  - Client sends `event_type: "HEARTBEAT_PING"`.
  - Server replies with `event_type: "HEARTBEAT_PONG"`.
- **Diagnostics Ping Contract**:
  - Client sends `event_type: "PING"`.
  - Server replies with `event_type: "PING_ACK"`.
- **Security & Limits**:
  - Strict Origin verification against `allowed_origins` (`http://localhost:5173`, `http://127.0.0.1:5173`).
  - Max text frame size enforced: 64 KB (`MAX_WS_MESSAGE_BYTES = 65536`).
  - Graceful closure on lifespan shutdown (`close_code: 1001`).

### 3.3 Server-Sent Events Surface (`/api/v1/events`)

- **MIME**: `text/event-stream`.
- **Purpose**: Unidirectional server telemetry and broadcast audit events.
- **Transport Separation**: WebSocket owns client-initiated bidirectional workflows; SSE provides decoupled system-wide metric streams.

---

## 4. Verification & Evidence Summary

- **Backend Pytest**: 15 passed in 0.48s (`tests/test_health.py`, `tests/test_sse.py`, `tests/test_system.py`, `tests/test_version.py`, `tests/test_websocket.py`).
- **Backend Linting**: `ruff check .` passed with 0 errors.
- **Frontend Vitest**: 24 passed across 6 test files in 3.17s (`api.test.ts`, `websocket.test.ts`, `backend-ui.test.tsx`, `mode.test.tsx`, `theme.test.tsx`, `navigation.test.tsx`).
- **Frontend Linting**: `oxlint` passed with 0 warnings, 0 errors across 45 files.
- **Frontend Production Build**: `tsc -b && vite build` succeeded in 698ms.
- **Real Browser E2E (Playwright on Google Chrome)**: 5 passed in 1.8m (`frontend/e2e/brick002.spec.ts`).
- **Actual Measured Latency**:
  - REST round-trip latency: ~2.2ms - 2.8ms warm (127ms cold).
  - WebSocket ping RTT: ~9.1ms observed in live browser session.

---

## 5. Acceptance Criteria Checklist

- [x] Initialized Git repository has verified BRICK-001 baseline committed (`c3c80c4`).
- [x] Fast, typed FastAPI backend runs on loopback `http://127.0.0.1:8000`.
- [x] REST health (`/live`, `/ready`), status (`/system/status`), and ping (`/ping`) endpoints functional.
- [x] Pydantic v2 schemas strictly validate all inbound and outbound payloads.
- [x] Starlette WebSocket gateway operates on `/api/v1/ws` with heartbeat keep-alive.
- [x] Unidirectional SSE stream operational on `/api/v1/events`.
- [x] React frontend features typed communication layer (`apiService`, `WebSocketClient`, `BackendContext`).
- [x] Global Header features live backend indicator displaying real connection state and measured RTT.
- [x] Developer Mode Connectivity view displays live REST, WebSocket, and subsystem statuses.
- [x] Developer Mode Diagnostics view provides interactive testing controls with live JSON terminal.
- [x] Developer Mode Logs view streams real-time transport lifecycle and audit events.
- [x] User Mode Chat view displays accurate backend connectivity banner while preserving honest empty states for BRICK-003.
- [x] Reconnection logic uses bounded exponential backoff with jitter and aborts on cleanup.
- [x] Origin validation and 64KB frame limits protect the WebSocket gateway; 1MB body limit protects REST.
- [x] Zero API keys or secrets exposed in frontend bundles or API responses; `.env` untracked and untouched.
- [x] Automated backend tests (`pytest`) pass (15/15).
- [x] Automated frontend tests (`vitest`) pass (24/24).
- [x] Automated Playwright E2E browser tests pass (5/5) using real Google Chrome.
- [x] Complete verification report generated at `docs/reports/REPORT-002.md`.
