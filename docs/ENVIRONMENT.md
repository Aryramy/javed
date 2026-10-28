# Environment, Runtime Prerequisites & Configuration Guide — JARVIS

> **Document ID**: `ENV-001`  
> **Version**: 2.2 (Stage 1 / BRICK-001 Verified Foundation)  
> **Status**: VERIFIED STAGE 1 ENVIRONMENT  
> **Project**: Javed — New JARVIS  
> **Current Stage**: Stage 1 / BRICK-001 — Foundation & Real React UI Shell  
> **Last Revision**: 2026-10-22  

---

## 1. Host Operating System Profile

| System Property | Specification | Compatibility Notes |
|---|---|---|
| **Operating System** | Microsoft Windows 11 (64-bit) | Primary development and production target |
| **Primary Shell** | PowerShell (`powershell.exe` / `pwsh`) | All terminal commands, runner scripts, and tests use PowerShell syntax |
| **User Account Level** | Standard User (Non-Administrator) | Zero admin elevation required. All tools install in user profile |
| **Project Working Root** | `C:\Users\arehman\Desktop\AI Projects\Javed` | Canonical root directory |
| **Text Encoding** | UTF-8 | Global encoding standard across all files and terminal output |

---

## 2. Tooling & Runtime Specifications

### 2.1 Backend Runtime & Package Management
- **Python**: **3.12.15** (CPython managed via `uv 0.13.5` in user space).
- **Virtual Environment**: `.venv` in project root (`.venv/Scripts/python.exe`).
- **Package Manager**: **`uv 0.13.5`** (installed via pip `--user` without admin elevation).
- **Quality & Verification**: `pytest 9.1.1` and `ruff 0.15.5`.

### 2.2 Frontend Runtime & Tooling
- **Node.js**: **v24.19.0** (`node.exe`).
- **Package Manager**: **`npm.cmd` v11.17.0** (PowerShell execution requires `.cmd` wrapper due to script policy).
- **Bundler & Dev Server**: **Vite v8.3.5** with `@tailwindcss/vite`.
- **UI Framework**: **React 19.3.1** + **TypeScript ~6.0.3** (Strict Mode).
- **Styling**: **Tailwind CSS v4.0.0** + custom HSL slate design tokens (`#0a0d14`, `#0f141f`, `#1e2638`, `#3b82f6`).
- **Linter & Test Runner**: **Oxlint v1.88.0** (0 warnings/errors), **Vitest v5.0.5** (9/9 tests passed).

### 2.3 Browser Automation Binaries
- **Playwright Chromium**: Target `%USERPROFILE%\AppData\Local\ms-playwright` via user-space installation. Zero system-level driver installation needed.

---

## 3. Network Architecture & Local Port Allocations

| Service / Component | Protocol | Local Host & Port | Description |
|---|---|---|---|
| **FastAPI Backend Gateway** | HTTP / WebSocket | `http://127.0.0.1:8000` | REST API endpoints, WebSocket connection (`/ws`), SSE feed (`/events`) |
| **Vite Frontend Dev Server** | HTTP (HMR) | `http://localhost:5173` | React web application development server with proxy to backend |
| **OpenRouter Remote Gateway** | HTTPS REST / SSE | `https://openrouter.ai/api/v1` | External AI model gateway for chat, reasoning, and provisional voice |
| **Local LLM Engine (Optional)** | HTTP REST | `http://127.0.0.1:11434` | Ollama local inference server (when enabled) |
| **PostgreSQL (Production Target)** | TCP / SQL | `127.0.0.1:5432` | Production relational and pgvector database (Docker or local service) |

---

## 4. Environment Variables & Secret Management

### 4.1 The Pre-Existing `.env` File
- A local `.env` file exists at `C:\Users\arehman\Desktop\AI Projects\Javed\.env`, containing the user's live OpenRouter credentials and preliminary voice configurations.
- **Security Laws**:
  1. **Strict Preservation**: Under no circumstances may `.env` be modified, overwritten, or deleted by automated scripts or agents.
  2. **Exclusion from Git**: `.env` and `.env.*` are strictly excluded from source control via [.gitignore](file:///c:/Users/arehman/Desktop/AI Projects/Javed/.gitignore).
  3. **Zero Credential Exposure**: API keys, tokens, or private secrets must never be printed, logged, committed, or echoed in documentation or agent messages.
  4. **Sanitized Template**: A sanitized [.env.example](file:///c:/Users/arehman/Desktop/AI Projects/Javed/.env.example) template is maintained at root containing placeholders only.


> [!IMPORTANT]
> **Firm AI Spending Limit ($20/Month)**: Per project budget governance, external paid API spending (OpenRouter) is strictly capped at **$20/month** (~$0.65/day sustained average). All testing must default to deterministic/mocked runners; live OpenRouter suites must be tightly targeted and bounded.

### 4.2 Standard Configuration Schema

```bash
# Core Application Settings
JAVED_ENV=development                   # development | production | test
JAVED_HOST=127.0.0.1
JAVED_PORT=8000
JAVED_LOG_LEVEL=INFO                    # DEBUG | INFO | WARNING | ERROR

# Primary LLM & AI Gateway (Sole Preapproved Paid Exception)
OPENROUTER_API_KEY=sk-or-v1-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_DEFAULT_MODEL=anthropic/claude-3.5-sonnet
OPENROUTER_DAILY_BUDGET_USD=5.00        # Soft daily limit. Note: Firm $20/month total AI budget ceiling (~$0.65/day sustained average) per project budget governance.

# Provisional Voice Pipeline Configuration (OpenRouter Audio Gateway)
OPENROUTER_STT_MODEL=openai/whisper-large-v3-turbo
OPENROUTER_TTS_MODEL=elevenlabs/eleven-v4-turbo
OPENROUTER_TTS_VOICE=george

# Local Model Fallback (Optional)
LOCAL_LLM_BASE_URL=http://localhost:11434/v1
LOCAL_LLM_DEFAULT_MODEL=llama3.1:8b

# Persistence & Database
DATABASE_URL=sqlite+aiosqlite:///data/javed.db
# Production Target: postgresql+asyncpg://user:pass@127.0.0.1:5432/javed

# Browser Sandbox Settings
BROWSER_HEADLESS=true                   # true | false
BROWSER_ACTION_TIMEOUT_MS=15000

# Security & Sandboxing
WORKSPACE_ROOT=C:\Users\arehman\Desktop\AI Projects\Javed
ENABLE_HUMAN_APPROVAL_MODAL=true

# Local Host Administration & MCP Security (BRICK-005 Phase 6C)
# Required to unlock MCP admin mutations in Developer Mode.
# Must be explicitly configured per laptop (not committed to git). Known weak placeholders are rejected.
# Generate locally via: python -c "import secrets; print(secrets.token_urlsafe(32))"
# If unset, administration fails closed.
JAVED_OWNER_TOKEN=                      # Random 32+ character secret
```

---

## 5. Provisional Voice Model Notes & Performance Reality

The project environment configures provisional remote voice models accessible through the OpenRouter gateway:
- **Speech-to-Text (STT)**: `openai/whisper-large-v3-turbo`
- **Text-to-Speech (TTS)**: `elevenlabs/eleven-v4-turbo`
- **Voice Preset**: `george`

> [!CAUTION]
> **API Availability Does Not Equal Real-Time Performance**:
> The mere presence of STT/TTS models on an API endpoint does not prove they can support natural, low-latency, real-time conversational voice.
> 1. Turn-around latency must be proven (< 1.2s round-trip).
> 2. Voice Activity Detection (VAD) and immediate barge-in (interruption) must be benchmarked.
> 3. Flawless multilingual support (Urdu, English, Arabic) and dynamic code-switching must be verified empirically in **BRICK-012**.
> 4. Provider-independent adapter interfaces must be preserved so that local models (Faster-Whisper, Kokoro, XTTS v2) can seamlessly substitute for or supplement remote endpoints.

---

## 6. Service Execution & Verification Commands (BRICK-002)

### 6.1 Backend FastAPI Service
Run from project root using the `.venv` Python runtime:
```powershell
.\.venv\Scripts\python.exe -m uvicorn javed.main:app --host 127.0.0.1 --port 8000
```
- Listens on `http://127.0.0.1:8000` (loopback only; never binds to `0.0.0.0`).
- Validates origins: `http://localhost:5173`, `http://127.0.0.1:5173`.
- Tests: `.\.venv\Scripts\pytest.exe`
- Linter: `.\.venv\Scripts\ruff.exe check .`

### 6.2 Frontend Development Server
Run from `frontend/` directory:
```powershell
cd frontend
npm.cmd run dev
```
- Listens on `http://localhost:5173`.
- Proxies `/api` and WebSocket `/api/v1/ws` to `http://127.0.0.1:8000`.
- Unit tests: `npm.cmd run test` (Vitest)
- Linter: `npm.cmd run lint` (Oxlint)
- Production build: `npm.cmd run build`

### 6.3 Real Browser Acceptance Testing (Playwright on Google Chrome)
Automated E2E browser verification runs against running backend and frontend servers:
```powershell
cd frontend
npm.cmd run test:e2e
```
- Configured with `channel: 'chrome'` to leverage the pre-installed system Google Chrome (`155.0.8059.40`).
- Resolves previous Azure CDN Chromium download restrictions cleanly in user space.
