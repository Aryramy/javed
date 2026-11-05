# REPOSITORY-INTELLIGENCE-DESIGN: Graphify-First Repository Awareness Specification

> **Document ID**: `ARCH-009`<br/>
> **Title**: Codebase Knowledge Graph and Repository-Query-First Orientation Architecture<br/>
> **Status**: `PROPOSED SPECIFICATION`<br/>
> **Program**: Coding-Agent Intelligence and Execution Efficiency<br/>
> **Author**: Antigravity Agent Architecture Core Team<br/>
> **Date**: 2026-11-05<br/>
> **Target Branch**: `feat/agent-efficiency-architecture`<br/>
> **Anchor Commit**: `5c00b9eaa6afd75dbf801ab2ca7793580437806a` (`master`)

---

## 1. Executive Summary & Objective

The primary driver of excessive agent token consumption, long turn durations, and regression introduction is **weak repository awareness**. When tasked with fixing a defect or extending a feature, an unassisted agent resorts to broad substring searches (`grep`, `Select-String`, or recursive directory scans) and speculative full-file reading.

**Repository Intelligence** replaces probabilistic, brute-force file exploration with a deterministic, indexed knowledge graph. This document specifies the architecture for a **Repository-Query-First** orientation pipeline, evaluating **Graphify-Labs/graphify** as the primary candidate, contrasted with Aider repository-map concepts and raw Tree-sitter AST indexing.

---

## 2. Technology Candidate Evaluation

### 2.1 Comparative Analysis

| Dimension | Option A: Graphify (`Graphify-Labs/graphify`) | Option B: Aider Repo-Map Pattern | Option C: Bespoke Tree-Sitter Index |
|---|---|---|---|
| **Architecture** | Semantic Knowledge Graph (Nodes: Files, Classes, Functions, Endpoints; Edges: Imports, Calls, Extends, References). | Weighted Symbol Graph with PageRank ranking over AST symbols. | Direct relational SQLite database storing AST symbol tables and raw xrefs. |
| **Cross-Language Support** | High (Python, TypeScript, JavaScript, Markdown, JSON). | High (Tree-sitter based multi-language grammar support). | Manual parser integration required per language. |
| **Relationship Depth** | Deep (call hierarchies, data flow, component-to-endpoint linkages). | Moderate (primarily symbol definitions and immediate references). | Custom-coded queries required for multi-hop traversals. |
| **Context Density** | High-precision subgraph extraction per query (answers specific questions in < 500 tokens). | Produces compact global summary map (~1,000 to 2,000 tokens). | Raw SQL results require post-processing. |
| **Maintenance Burden** | Low (managed open-source library used as developer tooling). | Moderate (requires integrating Aider repo-map algorithm). | High (requires ongoing maintenance of custom AST visitor logic). |
| **Operational Sandbox** | Can run 100% locally as a read-only CLI or MCP server in dev environment. | Runs locally via Python Tree-sitter bindings. | Runs locally. |
| **Verdict** | **PREFERRED PILOT CANDIDATE** (Milestone 2). | **SECONDARY COMPLEMENTARY PATTERN** (for prompt map). | **REJECTED** (Unnecessary reinvention of AST tooling). |

---

## 3. Answering the 8 Core Repository Questions

To justify adoption, Graphify must deterministically answer the 8 core questions that coding agents struggle with:

```mermaid
flowchart LR
    subgraph RepoGraph ["Repository Knowledge Graph"]
        Def["1. Symbol Definition"]
        Ref["2. Symbol References"]
        Callers["3. Component Callers"]
        Coverage["4. Test Coverage"]
        Endpoints["5. API Linkages"]
        Models["6. Model Mappings"]
        Blast["7. Blast Radius"]
        Coupling["8. Co-Change History"]
    end
    AgentQuery["Agent Query"] --> RepoGraph
    RepoGraph --> FocusedEvidence["Focused Source Target & Line Range"]
```

### Detailed Evaluation Matrix

| Question | Current Manual Search Method | Graphify Query Capability | Efficiency Gain |
|---|---|---|---|
| **1. Which file defines this symbol?** | `Select-String -Pattern "class ModelName"` across all directories (10–30s). | Direct index lookup: `MATCH (s:Symbol {name: 'ModelName'}) RETURN s.file, s.line`. | **Instant (< 50ms)**; 0 file reads required. |
| **2. Which files reference this symbol?** | Grep pattern search returning dozens of comments, strings, and imports. | Edge traversal: `(s:Symbol)<-[:REFERENCES]-(ref) RETURN ref.file`. | Eliminates false positive string matches. |
| **3. Which components call this service?** | Grep service name across `frontend/src/` or `src/javed/`. | Call graph query: `(s:Service)<-[:CALLS]-(c:Component)`. | Pinpoints exact caller components. |
| **4. Which tests cover this component?** | Guessed by filename match (e.g. `test_extraction_storage.py`). | Test-to-target mapping: `(c:Module)<-[:TESTS]-(t:TestCase)`. | Selects minimal targeted test set automatically. |
| **5. Which frontend service calls this API?** | String search for URL paths like `/api/v1/extraction/upload`. | Cross-tier edge: `(api:Endpoint)<-[:HTTP_REQUEST]-(svc:FrontendService)`. | Bridges backend FastAPI routes to React services. |
| **6. Which models feed this React component?** | Manual tracing from React props up to service response types. | Schema lineage: `(pydantic:Schema)-[:SERIALIZES_TO]->(ts:Type)-[:PROPS]->(comp:Component)`. | Prevents frontend/backend type desynchronization. |
| **7. What is the modification blast radius?** | Agent edits file blind; full test suite catches breakages later. | Transitive closure traversal (depth <= 2): `(target)-[:DEPENDS_ON*1..2]->(impacted)`. | Predicts dependent module impacts before editing. |
| **8. Which files commonly change together?** | Mental model or git log inspection. | Co-commit frequency edge: `(f1:File)-[:COMMITTED_WITH {count: N}]-(f2:File)`. | Identifies forgotten doc or schema files. |

---

## 4. Repository-Query-First Workflow

The future workflow enforces that no exploratory file searches or unguided full-file reads occur before querying the repository graph:

```mermaid
flowchart TD
    A[Task Intake] --> B[Parse Target Symbols & Keywords]
    B --> C[Query Graphify Index]
    C --> D{Graph Confidence?}
    D -- EXTRACTED --> E[Verify Line Ranges in Target Source]
    D -- INFERRED --> F[Perform Bounded Target Read of Candidate]
    D -- AMBIGUOUS --> G[Request Single Clarification / Replan]
    E --> H[Generate Pre-Edit Brief]
    F --> H
    H --> I[Proceed to Plan Gate]
```

### Confidence Policy
1. **`EXTRACTED`**: Direct AST-derived fact (e.g., function definition line, direct import statement). The agent may proceed directly to targeted source inspection of the specified line range.
2. **`INFERRED`**: Multi-hop heuristic or co-change association (e.g., component likely affected based on shared types). Must be verified by reading the specific interface lines before editing.
3. **`AMBIGUOUS`**: Multiple conflicting candidates or incomplete graph coverage. **Cannot authorize a code edit**. Requires one bounded exploration round or user input.

---

## 5. Strict Exclusion Boundaries & Index Sanitization

The repository index must be strictly isolated from runtime code, sensitive assets, and dynamic artifacts.

### Mandatory Indexing Exclusions
The following paths and patterns are **strictly excluded** from Graphify indexing:
- **Secrets & Credentials**: `.env`, `.env.*`, `*token*`, `*secret*`, `*.pem`, `*.key`.
- **Virtual Environments & Node Packages**: `.venv/`, `venv/`, `env/`, `node_modules/`, `frontend/node_modules/`.
- **Build & Distribution Outputs**: `dist/`, `build/`, `*.egg-info/`, `__pycache__/`, `.pytest_cache/`, `.oxlint_cache/`.
- **Dynamic Application Storage**: `data/`, `data/sources/`, `data/extractions/`, `data/tables/`, `data/quarantine/`, `data/*.db`.
- **Ephemeral Logs & Browser Traces**: `logs/`, `*.log`, `.playwright/`, `browser-profiles/`, `test-results/`.
- **Binary & Media Assets**: `*.pdf`, `*.docx`, `*.xlsx`, `*.png`, `*.jpg`, `*.svg`, `*.ico`.

### Sandbox Isolation
- Graphify is executed strictly as a developer-side CLI / local server.
- Graphify is **NEVER** imported into the production runtime (`src/javed/`).
- The generated graph database (e.g., SQLite or property graph file) resides in a git-ignored directory (`.graphify/`) and is completely disposable and rebuildable from scratch via a single command.

---

## 6. Pilot Evaluation Criteria & Go/No-Go Recommendation

### Pilot Success Criteria (Milestone 2)
1. **Query Accuracy**: Accurately resolves 100% of tested symbol definitions and references across both Python and TypeScript without hallucinating non-existent files.
2. **Indexing Time**: Full repository index builds in less than 45 seconds on the local development workstation.
3. **Storage Footprint**: Total index size does not exceed 100 MB on disk.
4. **Tool Call Reduction**: Reduces exploratory tool calls during orientation from an average of 14 calls down to <= 3 graph queries.
5. **Clean Teardown**: Leaves zero background daemon processes or memory leaks upon query completion.

### Recommendation: **GO FOR PILOT**
- **Recommendation**: **GO** for a bounded, read-only developer-tooling pilot of **Graphify** in **Milestone 2**.
- **Constraint**: Do not install Graphify during this assessment. Do not modify production source code. Graphify must be evaluated in an isolated branch (`feat/graphify-pilot`) with dedicated evaluation tasks.
