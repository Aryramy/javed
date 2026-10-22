# Technical Memory & Verified Architectural Learnings — JARVIS

> **Document ID**: `MEM-001`  
> **Version**: 2.2 (Master Architecture Correction Baseline)  
> **Status**: ACTIVE KNOWLEDGE STORE  
> **Project**: Javed — New JARVIS  
> **Last Revision**: 2026-10-22  

---

## 1. Purpose & Core Knowledge Invariants

This document captures durable technical insights, discovered platform constraints, validated architectural patterns, and verified antipatterns. Unlike [PROGRESS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/PROGRESS.md) (ephemeral state snapshot) or [TASKS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/TASKS.md) (operational registry), `MEMORY.md` preserves institutional knowledge across development cycles to prevent regression and duplicated architectural debates.

---

## 2. Validated Architectural Patterns

### 2.1 State Graph Checkpointing & Side-Effect Replay Safety
- **Insight**: Hand-rolled session managers and agent while-loops inevitably fail during unexpected crashes, process interruptions, or complex human-in-the-loop pauses. Furthermore, in modern LangGraph (`>= 0.2.0`), calling `interrupt()` pauses execution and commits the checkpoint. When resumed with `Command(resume=...)`, **LangGraph re-executes the interrupted node function from line 1**. When it reaches `interrupt()`, it yields the resume value without pausing.
- **Pattern**:
  1. Standardize on **LangGraph cyclic state graphs** with first-class checkpointers (`SqliteSaver` in development, `PostgresSaver` in production) scoped by unique `thread_id`.
  2. **Pure Gating Node Pattern**: To eliminate the critical risk of duplicating side effects (such as firing multiple API calls, duplicate database inserts, or duplicate file mutations), any node invoking `interrupt()` must be **strictly pure and idempotent** (evaluating risk and yielding the pause signal). The actual side-effect execution is isolated in a subsequent downstream node that only runs once permission is granted.

### 2.2 Single Primary Agent Harness (Deep Agents)
- **Insight**: Implementing bespoke agent loops alongside an agent framework introduces synchronization bugs, duplicate context management, and conflicting planning states.
- **Pattern**: Standardize on **Deep Agents** as the single primary agent harness. Deep Agents provides the execution loop, recursive planning, and long-term memory integration. Any custom LangGraph nodes or workflows must be strictly justified as domain-specific state graphs (e.g. human-in-the-loop approval or multi-step deterministic pipelines) rather than competing general agent loops.

### 2.3 Unopinionated Chat UI Runtime Decoupling
- **Insight**: Full-stack AI chat frameworks (such as CopilotKit) frequently bind the frontend to opinionated backend runtimes, specialized agent protocols, or commercial telemetry, creating vendor lock-in.
- **Pattern**: Pair **`assistant-ui`** with **Tailwind CSS** and **shadcn/ui**. `assistant-ui` manages headless message threads, token autoscroll, and custom tool cards in React, while connecting directly to our FastAPI WebSockets/SSE endpoints via native `useExternalMessageConverter` or custom runtime adapters.

### 2.4 Dual-Engine Browser Automation
- **Insight**: Using multimodal vision models (e.g. Browser Use) for every web task is slow and cost-prohibitive. Conversely, hardcoded Playwright scripts break on unfamiliar, dynamic sites.
- **Pattern**: Segregate browser automation into **Deterministic Playwright** (for known URLs, direct DOM scraping, file downloads, form entries with zero LLM token cost) and **Intelligent Browser Use** (for open-ended, visual navigation on unfamiliar sites).

### 2.5 Document Extraction Fidelity & Provenance
- **Insight**: Generic text extraction libraries (`pypdf`, `pdfplumber`) discard layout geometry and collapse multi-column text and tables into unreadable text streams.
- **Pattern**: Use **Docling** (by IBM Research). Its TableFormer model parses complex multi-line tables, reading orders, and headers into structured formats, preserving exact page and bounding box provenance.

### 2.6 Multilingual Voice Realities & Empirical Grounding
- **Insight**: Off-the-shelf TTS models trained predominantly on English datasets sound distorted and robotic when synthesizing Urdu or Arabic phonemes. Base **XTTS-v2** officially supports 17 languages (including Arabic and English) but **does not officially support Urdu** in its base release, and its CPML license restricts commercial use. **Piper TTS** has sparse Arabic support and lacks official Urdu checkpoints.
- **Pattern**:
  1. Maintain **replaceable voice adapter interfaces** (`BaseVoiceAdapter`).
  2. Local TTS models for Urdu and Arabic remain in **`EVALUATING`** status; fine-tuned community checkpoints or alternative open architectures must be empirically benchmarked in BRICK-012.
  3. The **OpenRouter audio gateway** (`openai/whisper-large-v3-turbo` for STT, `elevenlabs/eleven-v4-turbo` for TTS) serves as an approved provisional cloud pipeline.
  4. Latency (< 1.2s round-trip) and barge-in (< 50ms cut-off) are **empirical performance targets**, not pre-verified claims. Real-time conversational responsiveness must be validated through live network testing.

---

## 3. Discovered Technical & Environmental Constraints

| Category | Discovered Constraint | Engineering Workaround / Defense |
|---|---|---|
| **Prompt Injection Defense** | XML tags (e.g., `<user_input>`) alone do not prevent prompt injection; attackers can break out of tags or manipulate system semantics. | Enforce multi-layered defense-in-depth: strict input length bounds, structural sanitization, secondary LLM intent classification, and deterministic host-side execution barriers. |
| **Filesystem Sandboxing** | `Path.resolve()` canonicalization alone fails against symlink races (TOCTOU), Windows junction points, and Alternate Data Streams (ADS). | Implement strict defense-in-depth: resolve realpaths, detect and reject reparse points/junctions, disallow Windows ADS stream colons (`:`), perform pre- and post-operation checks, and lock writes to designated workspace roots. |
| **Tool Authorization Gating** | The LLM must never be capable of self-authorizing tool executions or elevating its own privileges. | Gating is enforced strictly in immutable host Python code. Tier 2 and Tier 3 actions pause execution via LangGraph `interrupt()` and require a cryptographically verified or UI-driven user signature before proceeding. |
| **OpenRouter Billing Limits** | Client-side token estimation cannot guarantee hard billing enforcement due to dropped connection retries or concurrent streaming requests. | Enforce client-side soft thresholds and warning triggers, but require an authoritative hard spending limit configured directly on the OpenRouter provider dashboard. |
| **Windows Portability (Non-Admin)** | User runs on Windows 11 without administrator privileges. | Use `uv` for Python package management and virtual environments; use user-level Node.js/npm. Never write installation scripts requiring global `PATH` modifications or admin UAC elevation. |
| **Playwright on Windows** | Chromium binaries must install within user directory. | Execute `playwright install chromium` inside the local virtual environment; binaries reside in `%USERPROFILE%\AppData\Local\ms-playwright`. |
| **SQLite Concurrency** | SQLite file-locking under simultaneous async read/write. | Enable Write-Ahead Logging (`PRAGMA journal_mode=WAL;`) upon connection initialization in `aiosqlite`. |
| **Secret Isolation** | Automated tools and Git must never expose `.env`. | `.env` is ignored by Git, read-only for application configuration, and strictly excluded from loggers, agent contexts, and tool targets. |
| **PowerShell Script Policy (Windows)** | Running `npm` or `npx` invokes `.ps1` files, triggering execution policy blocks on standard non-admin accounts. | Always execute `npm.cmd` and `npx.cmd` in Windows PowerShell subprocesses and build scripts. |
| **Vite 8 & Vitest Type Isolation** | Vite 8 utilizes Rolldown internals; importing `defineConfig` from `vitest/config` in `vite.config.ts` causes a TypeScript plugin mismatch in `tsconfig.node.json`. | Decouple build from test: maintain a pure `vite.config.ts` for Vite bundling and a standalone `vitest.config.ts` for Vitest test execution. |
| **React Fast Refresh Export Rules** | In Vite React with Fast Refresh, `.tsx` files should export only React components; exporting custom hooks or contexts alongside components breaks HMR and triggers linter warnings. | Separate React contexts and custom hooks into `.ts` files (`theme-context.ts`, `useTheme.ts`) and export UI providers in `.tsx` files (`ThemeContext.tsx`). |
| **Tailwind CSS v4 Configuration** | Legacy `tailwind.config.js` and `postcss.config.js` are superseded in Tailwind CSS v4. | Use `@tailwindcss/vite` plugin and declare design tokens directly using `@theme` and HSL CSS variables in `src/index.css`. |

---

## 4. Antipatterns & Architectural Traps to Avoid

1. **Simulated Success (The "Mocking Trap")**: Writing mock responses or fake progress bars and claiming a feature is functional. Functional bricks must run real backend processes and display real UI state.
2. **Side-Effect Replay Trap**: Placing side-effect code (file writes, DB mutations, API dispatches) inside an interruptible LangGraph node prior to `interrupt()`. Upon resumption, LangGraph re-runs the node from line 1, causing duplicate execution.
3. **Prompt Injection Delimiter Illusion**: Assuming that wrapping untrusted text in XML or markdown tags guarantees security. Host-side deterministic validation is always mandatory.
4. **Client-Side Billing Ceiling Fallacy**: Assuming client token tracking alone will prevent provider-side cost overruns without a provider-side hard cap.
5. **Framework Overlap**: Introducing redundant libraries (e.g. adding CrewAI alongside LangGraph, or LlamaIndex alongside LangChain, or multiple CSS libraries). Maintain architectural parsimony per Rule 11.
6. **Premature Autonomous Expansion**: Implementing capabilities out-of-order or introducing dependencies before their designated brick in the 14-brick roadmap.
7. **Unsandboxed Shell Dispatch**: Running shell commands without human-in-the-loop approval modals. Any Tier 3 action must block execution until the user clicks Approve in the UI.

