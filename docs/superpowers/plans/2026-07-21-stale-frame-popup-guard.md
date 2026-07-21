# Stale-Frame Popup Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ensure perception-loop classification uses one screenshot per tick, and abort mainline clicks if a popup appears between classify and click.

**Architecture:** `match_score` / `classify` accept an optional shared `screen` ndarray so all template scores come from one frame. `UiLoop` calls a popup-only recheck immediately before `CLICK_STEP` and `GO_BACK`; on hit it closes the popup and skips the mainline action for that tick.

**Tech Stack:** Python, OpenCV via existing Navigator screenshots, pytest + unittest.mock.

## Global Constraints

- Same-frame scores for one `classify` call (exactly one `_get_screenshot` when `screen` not passed).
- Pre-click popup recheck only for `CLICK_STEP` and `GO_BACK`.
- Reuse `POPUP_CLOSE_TEMPLATES`, `POPUP_CLOSE_THRESHOLD` (0.78), `popup_close_bounds`.
- No debounce, no path rollback, no task-table changes.
- TDD: failing tests first.

## File Map

| File | Role |
|------|------|
| `ui_state.py` | `match_score(..., screen=None)`; `classify` single capture |
| `ui_loop.py` | `_popup_pending()` / guard before click & back |
| `test_core.py` | Same-frame + pre-click cancel tests |

---

### Task 1: Same-frame `match_score` / `classify`

**Files:**
- Modify: `ui_state.py`
- Modify: `test_core.py` (`TestUiClassify`)

**Interfaces:**
- Produces: `match_score(nav, template_name, bounds=None, threshold=None, screen=None) -> float`
- Produces: `classify(nav, path_templates=None, *, allow_confirm=False, screen=None) -> (UiState, dict)` — if `screen` is None, capture once and reuse

- [x] **Step 1: Write failing tests**
- [x] **Step 2: Run tests — expect fail** (no `screen` kwarg)
- [x] **Step 3: Implement**
- [x] **Step 4: Run tests — expect pass**
- [x] **Step 5: Commit** (deferred — only if user requests)

---

### Task 2: Pre-click popup guard in `UiLoop`

**Files:**
- Modify: `ui_loop.py`
- Modify: `test_core.py` (`TestUiLoopRun`)

**Interfaces:**
- Produces: `UiLoop._popup_pending() -> bool` — fresh match of close templates
- Produces: `UiLoop._ensure_clear_for_click() -> bool` — if pending, `_close_popup()` and return False; else True
- Consumes: Task 1 `match_score(..., screen=...)`

- [x] **Step 1: Write failing tests**
- [x] **Step 2: Run — expect fail**
- [x] **Step 3: Implement**
- [x] **Step 4: Run all related tests — expect pass**
- [x] **Step 5: Commit** (deferred — only if user requests)

---

## Spec coverage

| Spec requirement | Task |
|------------------|------|
| Same-frame classify | Task 1 |
| Pre-click recheck for CLICK_STEP / GO_BACK | Task 2 |
| Skip TAKE_SHOT / WAIT / CLOSE_POPUP recheck | Task 2 (by omission) |
| Log on abort | Task 2 |
| Unit tests | Task 1–2 |
