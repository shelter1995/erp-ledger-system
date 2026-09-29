# Historical Blank Project Code Import Implementation Plan

> **For agentic workers:** When implementation is authorized, execute this plan task-by-task using the established method: subagent-driven-development when delegation is authorized and applicable, otherwise executing-plans inline. A planning-only request does not authorize execution. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow authoritative ledger rows with an empty B column to import safely by grouping them on the M-column order number and assigning a traceable temporary project code.

**Architecture:** Keep the original workbook row unchanged in `ledger_raw_row`, but resolve an effective project code before the normalized workbook reaches the existing importer. Use the exact trimmed order number as the fallback identity, a readable goods-based temporary code plus an order-derived digest for collision resistance, and transactional reconciliation when a later row supplies an official project code. Preview runs the same logic inside its existing nested transaction and therefore reports the exact commit behavior without persisting changes.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy Core, MySQL 8.4, openpyxl, pytest.

---

### Task 1: Add failing source-import behavior tests

**Files:**
- Modify: `backend/tests/test_source_import.py`

- [x] Add a workbook helper that creates blank-B rows with controlled M and O values without reading business files.
- [x] Add a test proving rows with the same M and blank B share one temporary project whose code contains the first O value and a stable digest suffix, while raw archived B remains empty.
- [x] Add a test proving identical first O values under different M values create different temporary projects.
- [x] Add a test proving an M that already belongs to more than one project is rejected as ambiguous.
- [x] Add tests for later official B reconciliation: rename a sole temporary project, and merge a single-order temporary project into an existing official project only when no order/history collision exists.
- [x] Run the new tests and confirm they fail because blank B is still rejected.

### Task 2: Resolve blank project codes and reconcile official codes

**Files:**
- Create: `backend/app/historical_project_identity.py`
- Modify: `backend/app/source_import.py`

- [x] Implement exact trimmed M lookup across active sales orders and order-number history, returning zero, one, or multiple project matches.
- [x] Implement a deterministic temporary code `临时待补-<first goods>等项目-<8 hex>` with control-character cleanup and a strict 64-character limit.
- [x] Resolve every blank-B group once per file; reuse a unique existing project, generate a new temporary project when none exists, and reject multiple matches.
- [x] Reconcile a later official B transactionally: rename a sole generated temporary project when the official code is unused; otherwise move its one M order to the existing official project only when all safety predicates and history checks pass.
- [x] Preserve the original blank B in `originals`, insert only the effective code into the normalized workbook, and add preview warnings describing every generated, reused, renamed, or merged mapping.
- [x] Run the targeted tests until green, then rerun the complete source-import test module.

### Task 3: Regression and delivery verification

**Files:**
- Modify if required by test findings: `backend/app/historical_project_identity.py`
- Modify if required by test findings: `backend/app/source_import.py`
- Modify if required by test findings: `backend/tests/test_source_import.py`

- [x] Run all backend tests against the current final files and record pass/skip counts: 405 passed, 2 skipped.
- [x] Run `git diff --check` and inspect the exact tracked diff; ensure no Excel files, output folders, credentials, or unrelated untracked files are staged.
- [ ] Commit only the plan, implementation, and tests with a Chinese commit summary.
- [ ] Verify the implementation commit descends from tag `archive/pre-blank-project-code-20260928-0cd4c33` and that the tag still resolves to `0cd4c336f86593b967db3f1535edb6052316b4b8`.
- [ ] Push the implementation branch only after the savepoint, scope, and verification evidence are confirmed.
