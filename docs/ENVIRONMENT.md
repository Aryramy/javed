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
OPENROUTER_DAILY_BUDGET_USD=5.00

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

## 6. Planned Setup Sequence for BRICK-001 (For Reference Only)

> [!WARNING]
> In accordance with Stage 0 execution boundaries, **NO installation commands may be run at this time**. The commands below are documented strictly as the verified blueprint for BRICK-001 execution once approved.

```powershell
# 1. Initialize Python virtual environment with uv
uv venv .venv --python 3.12
.venv\Scripts\activate

# 2. Install backend foundation dependencies
uv pip install fastapi uvicorn[standard] pydantic httpx ruff pytest pytest-asyncio

# 3. Initialize React Vite frontend
npm create vite@latest frontend -- --template react-ts
cd frontend
npm install
npm install -D tailwindcss postcss autoprefixer
npx tailwindcss init -p
```
