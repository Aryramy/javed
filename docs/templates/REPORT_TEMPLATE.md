# REPORT-XXX: [Brick Title] Verification Report

> **Report ID**: `REPORT-XXX`  
> **Associated Brick**: [BRICK-XXX](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/bricks/)  
> **Verification Date**: YYYY-MM-DD  
> **Verifier**: [Agent / Developer Name]  
> **Overall Outcome**: [PASS / FAIL / BLOCKED]  
> **Human Sign-Off Status**: [PENDING / APPROVED / REJECTED]  

---

## 1. Executive Summary

[Brief statement describing the verification activity, environmental context, and overall test outcome.]

---

## 2. Automated Test Execution Evidence

### 2.1 Test Command & Environment
```powershell
# Command executed:
pytest tests/ -v --tb=short
```

### 2.2 Raw Test Output / Logs
```text
============================= test session starts =============================
platform win32 -- Python 3.x.x
collected X items

tests/unit/test_module.py::test_case_1 PASSED                            [ 50%]
tests/integration/test_flow.py::test_case_2 PASSED                      [100%]

============================== X passed in 0.42s ==============================
```

---

## 3. Mandatory Live UI Verification Evidence (Rule 6)

> [!IMPORTANT]
> Headless verification alone is invalid for functional bricks. UI evidence must demonstrate actual live interaction without mocked data.

### 3.1 UI State & Interaction Description
- **Browser / Viewport**: [e.g., Chrome 1280x800]
- **Target URL / View**: [e.g., http://localhost:8000/]
- **Observed Behavior**: [Detailed description of interactive verification]

### 3.2 Visual & DOM Evidence
- **DOM / Console Snapshot**:
```text
[Console output or captured state snapshot demonstrating real data flow]
```
- **Visual Artifact**: [Link to screenshot artifact in report directory or browser log]

---

## 4. Security & Rule Compliance Audit

| Rule | Check Description | Result |
|---|---|---|
| **Rule 2** | Permissive open-source licenses verified for all dependencies | PASS / N/A |
| **Rule 3** | OpenRouter adapter isolated; zero hardcoded vendor coupling | PASS / N/A |
| **Rule 4** | Zero unapproved proprietary paid dependencies introduced | PASS / N/A |
| **Rule 7** | Zero simulated or mocked data presented as real functionality | PASS |
| **Rule 8** | Least-privilege permissions enforced; HITL prompt verified | PASS / N/A |
| **Rule 11** | No overlapping redundant frameworks added | PASS |
| **Rule 12** | Scope strictly constrained to active brick specification | PASS |

---

## 5. Acceptance Criteria Verification Checklist

- [ ] All automated unit and integration tests passing.
- [ ] Live UI verification demonstrated and recorded.
- [ ] No unhandled edge-case crashes or regressions.
- [ ] Documentation updated to reflect changes.
- [ ] Task status in `docs/TASKS.md` updated to `READY FOR ACCEPTANCE`.

---

## 6. Human Sign-Off & Status Promotion

- **Reviewing User**: [Name / Sign-off identifier]
- **Decision**: [APPROVED / CHANGES REQUESTED]
- **Date**: YYYY-MM-DD
- **Promotion Action**: Update [docs/PROGRESS.md](file:///c:/Users/arehman/Desktop/AI Projects/Javed/docs/PROGRESS.md) to mark brick `VERIFIED`.
