# Lightweight FSM Perception Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the linear screenshot-phase click loop with a lightweight UI perception loop that always prioritizes popups over mainline navigation.

**Architecture:** `ui_state.py` classifies the current screen into a small enum by priority; `ui_loop.py` runs a tick loop that decides/executes one action per frame against the existing `screenshot_tasks` goal cursor; `gui/app.py` stage 4 calls `UiLoop.run()` and stops async `PopupMonitor` during the loop (option A).

**Tech Stack:** Python, OpenCV template matching via existing `Navigator`, pytest.

## Global Constraints

- Screenshot-phase only; keep `web_login` / `launch_game` / `game_login` linear.
- Keep `screenshot_tasks` order and output filenames unchanged.
- Do not auto-click confirm dialogs during screenshot phase.
- POPUP always blocks mainline clicks (hard rule).
- Reuse popup close threshold `0.78` and top-right-half search bounds.
- TDD: failing test first for each behavior.

## File Map

| File | Role |
|------|------|
| `ui_state.py` (new) | `UiState`, shared popup bounds/threshold, `classify_from_scores`, `classify` |
| `ui_loop.py` (new) | `Goal`, `Action`, `decide`, `UiLoop.run` |
| `popup_monitor.py` | Import shared threshold/bounds from `ui_state` |
| `gui/app.py` | Stage 4 → `UiLoop`; stop async monitor in screenshot phase |
| `test_core.py` | New classify/decide/loop tests; update PopupSafety bounds imports if needed |

---

### Task 1: P0 — `UiState` + score-based `classify`

**Files:**
- Create: `ui_state.py`
- Modify: `test_core.py` (add `TestUiClassify`)
- Modify: `popup_monitor.py` (share threshold/bounds)

**Interfaces:**
- Produces: `UiState`, `POPUP_CLOSE_THRESHOLD`, `popup_close_bounds(vw,vh)`, `classify_from_scores(scores, path_keys=..., allow_confirm=False) -> (UiState, dict)`

- [x] **Step 1: Write failing tests** for priority: popup wins over avatar; login over main; unknown when all low; confirm ignored unless `allow_confirm`
- [x] **Step 2: Run tests — expect fail**
- [x] **Step 3: Implement `ui_state.py` + wire PopupMonitor shared constants**
- [x] **Step 4: Run tests — expect pass**
- [x] **Step 5: Commit** (deferred to user request)

### Task 2: P0b — `classify` via Navigator match helpers

- [x] Implemented `match_score` + `classify(nav, path_templates)`

### Task 3: P1 — `decide` + Goal cursor (no browser)

- [x] **decide/Goal tests + implementation**

### Task 4: P1/P2 — `UiLoop.run` executes actions

- [x] **UiLoop + popup-before-click test**

### Task 5: Wire `gui/app.py` stage 4

- [x] **Stage 4 → UiLoop; no async PopupMonitor in screenshot phase**

### Task 6: P3 checklist (manual)

- [ ] Manual regression: full round 1 + round 2 with popup present must close before homepage click
