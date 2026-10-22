# Architecture Decision Records (ADRs)

> **Directory**: `docs/decisions/`  
> **Status**: ACTIVE REGISTRY  
> **Authority**: Single source of truth for architectural decision history  

---

## 1. Overview

This directory preserves Architecture Decision Records (ADRs) for project **Javed (New JARVIS)**. An ADR captures significant architectural, technical, or governance decisions, including the context, evaluated alternatives, trade-offs, and final rationale.

---

## 2. Decision Log

| ADR ID | Title | Date | Status | Impact Area |
|---|---|---|---|---|
| **[ADR-000](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-000.md)** | Documentation and Governance System | 2026-10-22 | **APPROVED** | Project Foundation & Governance |
| **[ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md)** | Backend Architecture, Runtime, and Tooling (Python 3.12, FastAPI, uv) | 2026-10-22 | **APPROVED** | Core Backend & API Gateway |
| **[ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md)** | Frontend Architecture & UI Frameworks (React, Vite, Tailwind, shadcn/ui, assistant-ui) | 2026-10-22 | **APPROVED** | Web Client & Presentation |
| **[ADR-003](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-003.md)** | Agent Orchestration Runtime (Deep Agents + LangGraph vs CrewAI) | 2026-10-22 | **APPROVED** | Agent Core, Checkpointing, State Graph |
| **[ADR-004](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-004.md)** | Storage, Vector Retrieval & Memory Strategy (SQLite -> PostgreSQL + pgvector) | 2026-10-22 | **APPROVED** | Persistence, Semantic Memory, Checkpointing |
| **[ADR-005](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-005.md)** | Dual-Engine Browser Automation (Playwright Python + Browser Use) | 2026-10-22 | **APPROVED** | Browser Automation & Web Navigation |
| **[ADR-006](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-006.md)** | Web and Document Extraction Pipeline (Crawl4AI + Docling) | 2026-10-22 | **APPROVED** | Web Scraping, PDF/DOCX/XLSX Extraction |
| **[ADR-007](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-007.md)** | Multilingual Voice Architecture & Pipeline (STT, TTS, VAD, English/Urdu/Arabic) | 2026-10-22 | **APPROVED BASELINE (Local Models EVALUATING)** | Audio I/O, Voice Streaming, Barge-in |

---

## 3. ADR Lifecycle & Format

Every ADR follows this standardized lifecycle:
- `PROPOSED`: Drafted and open for architectural evaluation.
- `PENDING APPROVAL`: Submitted for project owner review.
- `APPROVED`: Explicitly approved by the project owner.
- `REJECTED`: Evaluated and discarded with documented rationale.
- `SUPERSEDED`: Replaced by a subsequent ADR.
