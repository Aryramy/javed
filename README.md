# Javed — New JARVIS

> **Autonomous AI Assistant & Modular Agent Framework**  
> **Project State**: `NOT STARTED`  
> **Current Stage**: `Stage 0 — Documentation Foundation`  
> **Active Brick**: None (BRICK-000 not started)  
> **Last Revision**: 2026-10-22  

---

## Overview

**Javed** is a next-generation, local-first autonomous AI assistant system designed to deliver robust computer interaction, intelligent task orchestration, multi-turn reasoning, and safe tool execution. It represents an independent, clean-slate architecture prioritizing software reliability, transparency, strict authorization boundaries, and human-in-the-loop control.

> [!NOTE]
> This repository is a new, independent project. No previous JARVIS implementation assumptions or pre-existing code artifacts apply here.

---

## Core Principles

1. **Reuse Before Build**: Rely on battle-tested, compatible open-source software before writing custom systems.
2. **Open-Source by Default**: Free, open-source software (FOSS) is standard across runtime, libraries, models, and tools.
3. **Single Paid Service Exception**: OpenRouter is the only preapproved proprietary paid service, strictly managed via a swappable adapter.
4. **Brick-by-Brick Verification**: The system is constructed through incremental, modular "bricks" verified against strict acceptance criteria and live UI demonstration before advancing.
5. **No Simulated Success**: Features must demonstrate real, functional execution. Simulated mocks passed off as functional reality are prohibited.
6. **Strict Security & Sandboxing**: Tool invocation, filesystem mutations, and shell executions require least-privilege scoping and human confirmation where impactful.

---

## Project Documentation Structure

All authoritative technical records, plans, and guidelines are maintained in the [`docs/`](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/) directory.

```
Javed/
├── AGENTS.md                  # Mandatory agent pre-flight protocol & operating loop
├── README.md                  # Project overview & navigation (this file)
├── .env                       # Environment credentials (git-ignored, local secrets)
└── docs/
    ├── RULES.md               # 12 Binding operational & architectural rules
    ├── PRD.md                 # Product requirements document
    ├── ARCHITECTURE.md        # Technical architecture & subsystem design
    ├── TECH_STACK.md          # Technology evaluations, approvals, & licenses
    ├── SECURITY.md            # Threat model, sandboxing, and security policies
    ├── ROADMAP.md             # Long-term phases, milestones, & dependencies
    ├── TASKS.md               # Master task registry & operational status
    ├── PROGRESS.md            # Authoritative project state snapshot
    ├── MEMORY.md              # Durable technical knowledge & verified learnings
    ├── UI_STANDARDS.md        # UI design system & live verification rules
    ├── TEST_STRATEGY.md       # Quality assurance, test pyramid, & verification
    ├── ENVIRONMENT.md         # Prerequisites, OS environment, & configuration
    ├── bricks/                # Modular brick specifications (BRICK-XXX.md)
    ├── decisions/             # Architecture Decision Records (ADR-XXX.md)
    ├── reports/               # Evidence-based verification reports (REPORT-XXX.md)
    └── templates/             # Standardized templates for bricks and reports
```

---

## Developer & Agent Entry Point

All human developers and AI agents must begin by reviewing [AGENTS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/AGENTS.md) and following the mandatory pre-flight protocol before touching any code or documentation.

---

## Current Project Status

- **Stage**: Stage 0 — Documentation Foundation
- **Application Code**: Not started (zero source lines written)
- **Dependencies**: None installed
- **Current Brick**: [BRICK-000.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/bricks/BRICK-000.md) (`NOT STARTED`)
- **Last Verified Brick**: None
- **Overall Status**: `NOT STARTED`
