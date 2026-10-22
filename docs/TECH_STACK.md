# Technology Stack Specification & Evaluation Registry

> **Document ID**: `TECH-001`  
> **Version**: 2.2 (Governance, Licensing & Voice Audit)  
> **Status**: PROPOSED BASELINE (PENDING OWNER APPROVAL)  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 0 / BRICK-000 — Master Architecture & Planning  
> **Last Revision**: 2026-10-22  

---

## 1. Governance & Technology Selection Laws

Per [RULES.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/RULES.md) (Rules 1, 2, 3, 4, 11) and [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) through [ADR-007](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-007.md):
1. **Permissive Open-Source Preference**: Direct runtime dependencies must carry OSI-approved permissive licenses (MIT, Apache 2.0, BSD, ISC, PSF). 
2. **Transitive Dependency Audit Policy**: Direct package dependencies have been verified. In accordance with honest reporting (Rule 10), transitive dependencies have **not** yet been fully audited; an automated audit (`pip-audit`, `licensecheck`, `npm audit`) will be executed upon initial dependency resolution in BRICK-001.
3. **Model Weight vs Software Licenses**: Model weight licenses (e.g. Apache 2.0 for Kokoro, CPML for XTTS-v2, open-weights licenses for Llama 3) must be tracked independently from Python/Node package licenses.
4. **Sole Paid Exception**: [OpenRouter](https://openrouter.ai/) (`https://openrouter.ai/api/v1`) is the only preapproved proprietary paid service, strictly isolated behind a replaceable adapter interface.
5. **No Overlapping Frameworks**: Exactly one primary technology per functional layer. Redundant, competing libraries are rejected.
6. **Zero Administrative Elevation**: All tools, runtimes, package managers, and browsers must install and run cleanly in standard Windows user space without requiring administrator privileges.
7. **MCP-First Tool Selection Law**: Prioritize proven, actively maintained, free/open-source Model Context Protocol (MCP) servers for external tools rather than implementing custom integrations (Rule 1). Reuse the native LangChain MCP integration (`langchain.mcp`). Validate licensing, authenticity, security, Windows compatibility, and resource consumption. Prefer native Python libraries only when measurably simpler, faster, more secure, or more reliable.

---

## 2. Technology Registry & Evaluation Matrix

| Layer / Subsystem | Proposed Technology | License (Software / Weights) | Status for BRICK-000 | Architectural Role & Evaluation | Reference |
|---|---|---|---|---|---|
| **Backend Runtime** | **Python 3.12+** | PSF License | **PROPOSED** | Native ecosystem for AI/agent libraries, asyncio concurrency, native typing. | [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) |
| **Package Management** | **uv** | Apache 2.0 / MIT | **PROPOSED** | Rust-based Python package resolver; 10x-100x faster than pip; runs in user space without admin. | [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) |
| **API Framework** | **FastAPI 0.110+** | MIT | **PROPOSED** | High-performance asynchronous REST and WebSocket gateway; native OpenAPI docs. | [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) |
| **Data Validation** | **Pydantic v2** | MIT | **PROPOSED** | High-speed Rust-backed validation for API models, tool inputs, and agent state schemas. | [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) |
| **HTTP Client** | **HTTPX** | BSD 3-Clause | **PROPOSED** | Asynchronous HTTP client with connection pooling for OpenRouter and REST APIs. | [ADR-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-001.md) |
| **Frontend Runtime** | **React 18 / 19 + TypeScript** | MIT | **PROPOSED** | Industry-standard declarative UI with strict TypeScript typing and rich AI streaming ecosystem. | [ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md) |
| **Build Tooling** | **Vite** | MIT | **PROPOSED** | Lightning-fast HMR and optimized production bundling for the React application. | [ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md) |
| **Styling & Components** | **Tailwind CSS + shadcn/ui** | MIT | **PROPOSED** | Utility-first CSS with accessible, copy-in Radix UI primitives. Complete code ownership. | [ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md) |
| **AI Chat UI** | **assistant-ui** | MIT | **PROPOSED** | Modular, unopinionated React components for streaming chat, markdown, and custom tool cards. | [ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md) |
| **Frontend State** | **TanStack Query + Zustand** | MIT | **PROPOSED** | TanStack Query for server-state caching; Zustand for lightweight client mode toggles. | [ADR-002](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-002.md) |
| **Agent Orchestration** | **Deep Agents + LangGraph** | MIT | **PROPOSED** | Deep Agents planning harness on top of LangGraph cyclic state graph with modern `interrupt()` HITL. | [ADR-003](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-003.md) |
| **Model Interfaces** | **LangChain Core** | MIT | **PROPOSED** | Abstract chat model primitives and standard tool binding decorators. | [ADR-003](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-003.md) |
| **Primary AI Gateway** | **OpenRouter API** (`https://openrouter.ai/api/v1`) | Commercial API | **PROPOSED EXCEPTION** | Sole preapproved paid API; provides unified access to leading reasoning, vision, and audio models. | [ADR-000](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-000.md) |
| **Local LLM Fallback** | **Ollama / vLLM** | MIT / Apache 2.0 | **PROPOSED** | Local open-weight models (Llama 3, Qwen 2.5) for offline privacy and zero-cost operation. | [ARCH-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/ARCHITECTURE.md) |
| **Relational Database** | **SQLite (Dev) / PostgreSQL (Prod)** | Public Domain / PostgreSQL | **PROPOSED** | SQLite file-based store for zero-config dev; PostgreSQL 16+ for enterprise production scale. | [ADR-004](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-004.md) |
| **Database ORM & Migrations** | **SQLAlchemy 2.0 + Alembic** | MIT | **PROPOSED** | Asynchronous ORM and declarative database migration tool. | [ADR-004](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-004.md) |
| **Semantic Vector Search** | **sqlite-vec (Dev) / pgvector (Prod)** | MIT / PostgreSQL | **PROPOSED** | Embedded vector search avoiding separate vector server daemons. | [ADR-004](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-004.md) |
| **Deterministic Browser** | **Playwright Python** | Apache 2.0 | **PROPOSED** | Fast, deterministic browser automation for URLs, DOM scraping, forms, and screenshots. | [ADR-005](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-005.md) |
| **Intelligent Browser** | **Browser Use** | MIT | **PROPOSED** | Vision-guided autonomous navigation on unfamiliar dynamic websites. | [ADR-005](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-005.md) |
| **Web Scraping** | **Crawl4AI** | Apache 2.0 | **PROPOSED** | LLM-ready web crawler producing clean semantic Markdown from modern dynamic SPAs. | [ADR-006](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-006.md) |
| **Document Understanding** | **Docling** | MIT | **PROPOSED** | High-fidelity parser for PDF, DOCX, XLSX with advanced table and reading-order extraction. | [ADR-006](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-006.md) |
| **Voice Activity Detection** | **Silero VAD** | MIT | **PROPOSED (BRICK-012)** | Ultra-fast local ONNX VAD for instant voice detection and immediate barge-in cut-off. | [ADR-007](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-007.md) |
| **Speech-to-Text (STT)** | **openai/whisper-large-v3-turbo** (Remote) / **Faster-Whisper** (Local) | Commercial API / MIT | **PROPOSED (BRICK-012)** | Dual-path: provisional OpenRouter Whisper endpoint with local Faster-Whisper fallback. | [ADR-007](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-007.md) |
| **Text-to-Speech (TTS)** | **elevenlabs/eleven-v4-turbo (voice: george)** (Remote) / **Local Candidates** | Commercial API / FOSS | **PROPOSED (BRICK-012)** | Dual-path: OpenRouter ElevenLabs endpoint + reopened evaluation of local TTS for Urdu/Arabic/English. | [ADR-007](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/decisions/ADR-007.md) |
| **Tool Interoperability** | **Model Context Protocol (MCP)** via native **LangChain MCP (`langchain.mcp`)** | MIT | **PROPOSED (BRICK-005 Baseline, BRICK-006 Browser, BRICK-010 Ecosystem)** | Open standard for tool calling. MCP-first strategy prefers maintained, open-source MCP servers over custom tools. Evaluated for licenses, authenticity, Windows compatibility, and security. | [ARCH-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/ARCHITECTURE.md) |
| **Observability** | **OpenTelemetry + Langfuse OSS** | Apache 2.0 / MIT | **PROPOSED (Self-Hosted)** | Open instrumentation and self-hosted trace monitoring; zero proprietary cloud telemetry. | [ARCH-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/ARCHITECTURE.md) |
| **Testing Harness** | **pytest + Vitest + Playwright Test** | MIT / Apache 2.0 | **PROPOSED** | Automated unit, contract, and browser-driven live UI verification. | [TEST-001](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/TEST_STRATEGY.md) |

---

## 3. Accurate Framework Comparisons & Overlap Analysis

### 3.1 Agent Frameworks: Deep Agents + LangGraph vs CrewAI
- **CrewAI**: Open source (MIT license). High-level framework designed for role-playing multi-agent "crews" (agents, tasks, sequential/hierarchical crews). While effective for collaborative role simulation, it is more rigid for fine-grained graph checkpointing, low-level token streaming, and stateful human-in-the-loop pause/resume compared to LangGraph.
- **Deep Agents + LangGraph**: LangGraph provides explicit cyclic state graphs with native `interrupt()` and `Command(resume=...)` support, first-class checkpointing, and token-level streaming. Deep Agents serves as the primary planning harness. We do **not** build a redundant second agent loop. Adopting both CrewAI and LangGraph would violate Rule 11.

### 3.2 Chat & UI Frameworks: assistant-ui vs CopilotKit
- **CopilotKit**: Open source core (MIT license). Highly capable framework specifically architected for embedded in-app copilots, sidebars, and in-app document co-editing. While it can be self-hosted, it introduces its own specialized runtime abstractions that add unnecessary complexity when wrapping an existing FastAPI + LangGraph architecture.
- **assistant-ui**: Open source (MIT license). Provides headless, unopinionated React primitives for conversational AI threads. Connects directly to our FastAPI WebSockets and SSE streams, pairing naturally with Tailwind CSS and shadcn/ui without intermediary runtime overhead.
- **Archived Tool UI Check**: We strictly **do not** depend on the archived `assistant-ui/tool-ui` repository as a maintained core dependency.

### 3.3 Storage & Retrieval: pgvector vs Qdrant vs LlamaIndex
- **LlamaIndex**: Open source (MIT). Rich RAG framework, but introduces severe overlap with LangGraph's native document loaders and vector store retrievers.
- **Qdrant**: Dedicated vector database. Deferred until vector scale (> 1M vectors) benchmarks prove pgvector is insufficient.
- **SQLite -> PostgreSQL + pgvector**: Unified database storing relational entities, checkpoints, and embeddings without running multiple database daemons.

### 3.4 Tool Execution Architecture: MCP-First Strategy vs Custom Tooling
- **MCP-First Strategy**: Prefer proven, actively maintained, free/open-source MCP servers for tool calling rather than developing custom tools or bespoke integration code.
- **Client Framework**: Reuse the current native LangChain MCP integration (`langchain.mcp` / official LangChain MCP capabilities), subject to compatibility verification, rather than inventing a custom MCP client protocol runner.
- **Phased Rollout**:
  - **BRICK-005**: Establish central tool authorization, Pydantic argument validation, and initial MCP client integration.
  - **BRICK-006**: Evaluate and integrate Playwright MCP for browser tasks alongside direct Playwright execution.
  - **BRICK-010**: Expand to a managed MCP server ecosystem with Developer Mode UI management and health monitoring.
- **Required Build vs Reuse Criteria**: Every prospective tool must document required capability, existing MCP candidates, maintenance/license status, security/permissions, integration compatibility, expected performance, and justification before implementation. Write custom integrations only when no suitable, trustworthy solution exists. Native Python libraries are preferred when measurably simpler, faster, more secure, or more reliable.

---

## 4. Hardware, Operating System & Resource Expectations

| Environment | Minimum Specification | Recommended Specification | Notes |
|---|---|---|---|
| **Operating System** | Windows 11 (64-bit) | Windows 11 (64-bit) | PowerShell 7+ or standard `powershell.exe`. Non-admin account fully supported. |
| **CPU** | 4 Cores (x86_64) | 8+ Cores (Intel 12th+ Gen / AMD Ryzen 5000+) | Fast multi-threading for Docling parsing and Faster-Whisper inference. |
| **RAM** | 8 GB RAM | 16 GB - 32 GB RAM | Idle stack uses < 250MB. Local Whisper/Docling models require 1-3 GB transient memory. |
| **Disk Space** | 10 GB free space | 50 GB free SSD | Accommodates virtual environments, Chromium binaries, and local model weights. |
| **GPU (Optional)** | None (CPU inference supported) | NVIDIA RTX 3060+ (6GB+ VRAM) | CUDA acceleration dramatically accelerates local Faster-Whisper, Kokoro, and Ollama. |

---

## 5. OpenRouter Budgeting, Cost Reporting & Billing Controls

1. **Configurable Spending Limits**:
   - The application supports user-configurable spending limits defined via environment variables (`OPENROUTER_DAILY_BUDGET_USD`).
   - Limits are not hardcoded to arbitrary values; they are set by the project owner based on active workloads.
2. **Real-Time Cost Reporting**:
   - The model adapter tracks prompt tokens, completion tokens, audio generation units, and estimated costs using OpenRouter published rate cards.
   - The UI displays running session token counts and estimated costs in both User Mode and Developer Mode.
3. **Retry Budgets & Circuit Breaking**:
   - Strict retry limits (maximum 3 exponential backoff retries on HTTP 429/503) prevent runaway loops from draining balances.
4. **Provider-Side Spending Caps (Crucial Security Invariant)**:
   > [!CAUTION]
   > **Application-Side Cost Estimates Alone Do Not Guarantee Hard Billing Enforcement**:
   > Client-side token counting can drift due to tokenization discrepancies, dropped network connections, or concurrent sessions. 
   > **Guaranteed billing protection must be configured directly within the OpenRouter account dashboard** (`https://openrouter.ai/settings/limits`), establishing a provider-side hard credit ceiling that OpenRouter enforces authoritatively.
