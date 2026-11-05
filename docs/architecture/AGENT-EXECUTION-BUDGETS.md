# AGENT-EXECUTION-BUDGETS: Enforceable Task Budgets & Watchdog Architecture

> **Document ID**: `ARCH-010`<br/>
> **Title**: Hard Execution Limits, Action Ledger & Watchdog Engine Specification<br/>
> **Status**: `IMPLEMENTED & VERIFIED` (Milestone 4 Accepted)<br/>
> **Program**: Coding-Agent Intelligence and Execution Efficiency<br/>
> **Author**: Antigravity Agent Architecture Core Team<br/>
> **Date**: 2026-11-05<br/>
> **Target Branch**: `feat/agent-efficiency-architecture`<br/>
> **Anchor Commit**: `801c6b947e5d8fd693b3f79abe17afb9597209fd`

---

## 1. Executive Summary & Objective

The **Watchdog Engine** enforces deterministic, non-negotiable boundaries on autonomous agent tasks to eliminate:
- Infinite analysis or planning loops
- Repeated exploration of unchanged files
- Equivalent Graphify queries
- Small, uncontrolled iterative patches
- Test-debug-test thrashing
- Repeated identical failure retries
- Unbounded model tokens and billing spend
- Process leaks from hanging subprocesses

The watchdog is isolated as a library in `src/javed/agent/efficiency/` and verified with 42 deterministic tests. It is **not** activated globally in Chat Mode or Agent Mode during Milestone 4.

---

## 2. Six Canonical Task Classes & Default Budgets

Every task must declare a valid task class from `TaskClass`. Limits are strictly positive and bounded by the 60-minute global ceiling (`GLOBAL_MAX_DURATION_SECONDS = 3600`).

| Task Class | Max Duration | Max Analysis Iter | Max Replans | Max Files Read | Max Files Modified | Max Patches | Max Tests | Max Tool Calls | Max Model Calls | Max Tokens | Max Cost (USD) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **`documentation`** | 900s (15m) | 2 | 1 | 8 | 8 | 2 | 1 | 30 | 4 | 60,000 | \$0.50 |
| **`single_file_defect`** | 1200s (20m) | 3 | 1 | 10 | 3 | 2 | 3 | 40 | 6 | 80,000 | \$0.50 |
| **`multi_file_defect`** | 2100s (35m) | 3 | 2 | 20 | 10 | 3 | 3 | 70 | 8 | 140,000 | \$1.25 |
| **`frontend_backend_contract`** | 2700s (45m) | 3 | 2 | 24 | 14 | 4 | 3 | 80 | 8 | 160,000 | \$1.50 |
| **`security_sensitive`** | 2700s (45m) | 3 | 2 | 25 | 12 | 4 | 3 | 80 | 8 | 160,000 | \$1.50 |
| **`architecture_change`** | 3600s (60m) | 3 | 2 | 40 | 20 | 5 | 3 | 120 | 10 | 250,000 | \$3.00 |

---

## 3. Discrete Watchdog States

Transitions are discrete, explicit, and deterministic. No state may silently reset counters or increase limits:

```mermaid
flowchart TD
    ACTIVE["ACTIVE"] -->|>= 80% Resource| WARNING["BUDGET_WARNING"]
    ACTIVE -->|100% Resource| EXCEEDED["BUDGET_EXCEEDED"]
    ACTIVE -->|Wall-clock limit| TIMEOUT["TIMEOUT"]
    ACTIVE -->|2x No-Progress| STALLED["STALLED"]
    STALLED -->|record_replan()| ACTIVE
    STALLED -->|Replans exhausted| OWNER["OWNER_INPUT_REQUIRED"]
    ACTIVE -->|Undeclared file edit| SCOPE["SCOPE_EXPANSION_REQUIRED"]
    SCOPE -->|Owner Override| ACTIVE
    ACTIVE -->|Identical failure 2x| REPLAN["REPLAN_REQUIRED"]
    REPLAN -->|record_replan()| ACTIVE
    ACTIVE -->|All acceptance criteria met| COMPLETED["COMPLETED"]
    ACTIVE -->|Fatal error| FAILED["FAILED"]
```

---

## 4. 80% Warning & 100% Hard Stop Behavior

### 4.1 The 80% Warning Circuit
Triggered when any critical dimension (duration, tool calls, model calls, tokens, cost, files read, modified files, patches, test runs) reaches 80% allowance:
- Emits `BUDGET_WARNING` event detailing metric, current value, limit, percentage, and remaining allowance.
- Prohibits non-essential file inspection and opportunistic refactoring.
- Mandates state compaction and focuses strictly on completing approved patches and required tests.

### 4.2 The 100% Hard Stop Circuit
Triggered when any hard budget reaches 100%:
- Halts all further work dispatch.
- Terminates running subprocesses gracefully (10s grace, then tree termination).
- Preserves task state, action ledger, test evidence, and diff references in `TaskCheckpoint`.
- Sets `BUDGET_EXCEEDED` or `TIMEOUT`.
- Awaits explicit Project Owner override.
- Never uses `os._exit`.

---

## 5. Deduplication & No-Progress Detection

1. **Action Deduplication**: Actions are hashed using normalized parameters (`normalized_arguments_hash`). If a previous equivalent action succeeded under the identical Git HEAD and file hashes, the prior result is reused without execution. If it failed and is non-retryable, execution immediately halts with `REPLAN_REQUIRED`.
2. **File Read Deduplication**: Repeated reads of the identical file content hash and line range are rejected fail-closed (`DUPLICATE_READ_PREVENTED`). Rereading is authorized only when the file content hash changes.
3. **No-Progress Detection**: Actions that fail to produce tangible progress (evidence, confidence increase, patch completion, passing tests) are flagged. Two consecutive no-progress iterations trigger `STALLED`.

---

## 6. Subprocess Control & Cleanup

Subprocesses executed via `run_bounded_subprocess` adhere to strict timeout profiles:
- Status / Query / Search: 30s
- Incremental Graph Update: 120s
- Targeted Tests: 300s
- Integration Tests: 600s
- Full Regression: 900s

On timeout:
- Initiates graceful SIGTERM/terminate.
- Waits up to 10 seconds.
- Escalates to process tree termination (`taskkill /F /T /PID` on Windows).
- Records `TIMEOUT` and ensures zero orphan processes remain.

---

## 7. Project Owner Overrides & Checkpointing

1. **Owner Overrides**: Only the Project Owner can approve limit increases via `OwnerBudgetOverride`. Overrides specify task ID, budget metric, old/new values, justification, expiration timestamp, and optional scope expansion. Expired overrides are ignored fail-closed.
2. **Task Checkpoints**: Serializable JSON records capturing task metadata, counters, failure fingerprints, test summaries, and approved scopes. Checkpoints **strictly exclude** chain-of-thought, passwords, API tokens, user secrets, or raw file bodies.
