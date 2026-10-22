# Product Requirements Document (PRD) — JARVIS

> **Document ID**: `PRD-001`  
> **Version**: 2.0 (Master Architecture Baseline)  
> **Status**: APPROVED REQUIREMENTS BASELINE  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 0 / BRICK-000 — Master Architecture & Planning  
> **Last Revision**: 2026-10-22  

---

## 1. Product Vision & Executive Summary

**JARVIS** (Project Javed) is a general-purpose, autonomous, multimodal personal AI assistant and engineering co-pilot. Built upon a zero-trust, local-first foundation, JARVIS combines natural language reasoning, real-time multilingual voice interaction, deterministic and exploratory browser automation, high-fidelity document comprehension, sandboxed tool dispatch, and persistent verifiable memory.

The system enforces strict human-in-the-loop authorization for consequential operations, maintains complete transparency through real-time telemetry, and provides both a consumer-grade **User Mode** and a deep diagnostic **Developer Mode** within a unified web interface.

---

## 2. Target Personas & Use Cases

| Persona | Profile & Workload | Core Value Delivered |
|---|---|---|
| **Autonomous Power User / Engineer** | Executes coding, system automation, web research, file management, and data analysis. | Rapid multi-step task execution, sandboxed shell dispatch, automated code inspection, instant answers with source citations. |
| **Multilingual Professional** | Communicates across English, Urdu, and Arabic; requires voice and text interaction with seamless code-switching. | Natural, low-latency multilingual voice conversation with automatic language detection, hands-free operation, and instant barge-in. |
| **Document & Research Analyst** | Ingests complex multi-column PDFs, research papers, financial spreadsheets, and live web pages. | High-fidelity table and text extraction with exact page/bounding box provenance; semantic search across long-term knowledge corpora. |

---

## 3. Detailed Functional Requirements (FR)

### 3.1 Conversational Intelligence & Model Orchestration
- **FR-01: Provider-Independent Model Adapter**: Interface seamlessly with [OpenRouter](https://openrouter.ai/) (preapproved paid exception) and local OpenAI-compatible engines (Ollama, llama.cpp, vLLM). Decoupled via an abstract client adapter.
- **FR-02: Capability-Aware Model Routing**: Automatically verify and route tasks based on model capabilities (tool calling, context window, vision, reasoning, cost budgets).
- **FR-03: Real-Time Streaming & Branching**: Stream tokens incrementally with sub-800ms time-to-first-token; support multi-turn thread branching, message editing, and regeneration.

### 3.2 Multilingual Voice System
- **FR-04: Trilingual Voice Conversation**: Natural voice interaction in **Urdu, English, and Arabic** without requiring separate assistant personas.
- **FR-05: Automatic Language Detection & Switching**: Automatically detect spoken language per utterance and respond in the matching language; handle mixed-language code-switching gracefully.
- **FR-06: Low-Latency Streaming & Barge-in**: Support Voice Activity Detection (VAD via Silero VAD) with immediate speaker cut-off and generation cancellation upon user interruption (barge-in).
- **FR-06b: Provider-Independent Voice Adapters & Provisional Models**: Maintain abstract `AudioSTTAdapter` and `AudioTTSAdapter` interfaces. Support provisional OpenRouter audio endpoints (`openai/whisper-large-v3-turbo` for STT; `elevenlabs/eleven-v4-turbo`, voice `george` for TTS) alongside local fallbacks (Faster-Whisper, Kokoro-82M, XTTS v2).
- **FR-06c: Empirical Real-Time Verification**: Endpoint availability does not substitute for real-time verification; end-to-end conversational turn-around latency (< 1.2s) and multilingual pronunciation quality must be proven empirically in BRICK-012.

### 3.3 Autonomous Planning & Task Execution
- **FR-07: Multi-Step Graph Orchestration**: Utilize LangGraph cyclic state machines and Deep Agents planning harnesses to decompose complex user prompts into step-by-step execution plans.
- **FR-08: Checkpointing & Session Resumption**: Persist full agent graph state at every step; allow seamless task resumption across server restarts or system interruptions.
- **FR-09: Specialized Subagent Delegation**: Dynamically spawn and delegate sub-tasks to isolated child graphs (e.g. Research Subagent, Coder Subagent) with bounded context and parent-controlled return values.

### 3.4 Browser Automation & Web Operations
- **FR-10: Dual-Engine Browser Automation**:
  - *Deterministic*: Playwright Python for predictable, zero-token URL navigation, DOM scraping, form entry, and file downloads.
  - *Intelligent*: Browser Use for vision-driven, autonomous navigation on unfamiliar dynamic websites.
- **FR-11: Live Browser UI Preview**: Stream real-time browser actions, viewport frames, and step screenshots directly into the JARVIS web interface.

### 3.5 Content & Document Extraction
- **FR-12: High-Fidelity Web & Document Extraction**:
  - Crawl web pages into clean Markdown using Crawl4AI.
  - Parse PDFs, DOCX, and XLSX using Docling, preserving complex table structures, reading orders, and page-level provenance.

### 3.6 Tool Interoperability & Security
- **FR-13: Four-Tier Tool Sandbox & Model Context Protocol (MCP)**: Enforce a strict permission taxonomy (Tier 0 Safe Read to Tier 3 High Risk). Support external tools via standard MCP servers with schema validation and input sanitization.
- **FR-14: Human-in-the-Loop Approval Modal**: Block consequential operations (shell execution, file deletion, financial web actions, environment mutations) until explicit user approval is granted via the UI.

### 3.7 Persistent Memory & Knowledge Base
- **FR-15: Segmented Long-Term Memory**: Isolate agent checkpoints, conversation history, application state, long-term user memory, and document knowledge embeddings.
- **FR-16: User Memory Management**: Enable users to view, search, correct, and permanently delete facts and preferences stored by the assistant.

---

## 4. Non-Functional Requirements (NFR)

| ID | Category | Metric / Specification |
|---|---|---|
| **NFR-01** | **Security & Sandboxing** | Zero unauthorized filesystem or shell mutations. All Tier 3 tools require explicit human approval. Zero credential leakage in logs or context windows. |
| **NFR-02** | **Latency & Responsiveness** | UI initial load < 1.0s. Local streaming TTFT < 500ms; OpenRouter TTFT < 800ms. Voice turn-around latency < 1.2s end-to-end. |
| **NFR-03** | **Truthfulness & Verification** | Zero simulated or mocked successes in production/verification. All tool responses reflect real process exit codes and stdout/stderr. |
| **NFR-04** | **Extensibility & Modularity** | New tools, MCP servers, and model adapters plug in via modular Python classes without modifying core orchestration graphs. |
| **NFR-05** | **Platform Portability** | Runs reliably on Windows 11 (PowerShell) without requiring administrator elevation. Managed via `uv` and standard npm tooling. |
| **NFR-06** | **Resource Footprint** | Base background idle memory < 250MB RAM. Operates comfortably on modern workstations with or without discrete GPUs. |
| **NFR-07** | **Aesthetic Standards** | Modern dark-mode-first aesthetic with Tailwind CSS, shadcn/ui, glassmorphism, and micro-animations per [UI_STANDARDS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/UI_STANDARDS.md). |
| **NFR-08** | **Dual Operational Views** | Seamless toggling between **User Mode** (streamlined personal assistant) and **Developer Mode** (deep telemetry, traces, and state inspection). |

---

## 5. Explicit Scope Boundaries

### In Scope (Phased Delivery)
- Local FastAPI backend + React Vite frontend connected via WebSockets and SSE.
- OpenRouter as primary external model gateway; local fallback via Ollama.
- Deep Agents + LangGraph agent execution with checkpoint persistence.
- Dual browser engine (Playwright + Browser Use) with live UI stream preview.
- Crawl4AI web scraper + Docling document understanding engine.
- SQLite (local dev) migrating cleanly to PostgreSQL + pgvector (production).
- Model Context Protocol (MCP) client integration.
- Trilingual voice pipeline (Urdu, English, Arabic) with VAD and barge-in.

### Out of Scope (Explicit Non-Goals)
- Hard dependencies on proprietary cloud platforms (AWS Bedrock, Azure OpenAI SaaS, Google Vertex exclusive APIs).
- Unapproved proprietary paid services (Pinecone, LangSmith SaaS, ElevenLabs, Claude Team SaaS).
- Closed-source commercial desktop wrappers or Electron bloatware (runs cleanly in modern web browsers).
- Multi-tenant enterprise IAM, billing, or organization management (JARVIS is an independent, single-user personal system).
- Untrusted, autonomous self-modification of core governance documentation.

---

## 6. Key User Stories

1. **Autonomous Coding & System Task**:
   > *"As a developer, I want JARVIS to research an API, write a test suite, run it via the terminal, and show me the exact diff and test logs before committing, so that I can automate repetitive workflows with complete safety."*
2. **Multilingual Voice Research**:
   > *"As a multilingual user, I want to speak to JARVIS in Urdu or Arabic, have it understand my query, summarize an English technical PDF, and explain the findings back to me in natural Urdu, interrupting immediately if I speak."*
3. **Complex Document & Financial Analysis**:
   > *"As an analyst, I want to drop a 50-page financial PDF with complex multi-year tables into JARVIS and receive exact calculations with references to the specific table cells and page numbers."*
4. **Autonomous Web Task with Approval**:
   > *"As a user, I want JARVIS to find an item on a website, add it to the cart, and stop at the checkout screen with a clear approval popup displaying the total cost before proceeding."*

---

## 7. Success Metrics

- **Task Completion Rate**: > 90% autonomous success on multi-step tasks without human intervention on non-consequential steps.
- **Safety Enforcement**: 100% compliance on human-in-the-loop gating for Tier 3 actions (zero unapproved shell commands or financial actions).
- **Extraction Fidelity**: > 95% table structure and text accuracy on complex multi-column PDFs and spreadsheets via Docling.
- **Voice Turn-around Latency**: < 1.2s round-trip audio latency for voice conversations.
- **Zero Hallucinated Tool Success**: 100% truth in tool execution reporting.
