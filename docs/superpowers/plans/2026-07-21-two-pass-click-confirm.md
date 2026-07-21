# Two-Pass Click Confirm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Before mainline `click_css`, re-check a small ROI around the planned click against the Pass1 reference crop; abort click if similarity is too low.

**Architecture:** New `click_confirm.py` builds a `ClickPlan` (x, y, roi_ref) from a frame; `confirm_roi` / `execute_click_with_confirm` do Pass2. `Navigator.grab_roi` crops from a full screenshot (P0). `UiLoop` `_do_click_step` / `_do_back` use this path instead of bare `find_and_click` for mainline clicks.

**Tech Stack:** Python, OpenCV, Selenium Navigator, pytest.

## Global Constraints

- P0 only: full-frame grab then crop ROI (no CDP clip yet).
- Enable for `CLICK_STEP` and `GO_BACK` only.
- ROI failure: no click, no cursor advance, no `rewind_to_previous_step`.
- Similarity via `TM_CCOEFF_NORMED` (or equivalent), threshold 0.90.
- Keep existing popup pre-check and post-back verify/rewind.

## File Map

| File | Role |
|------|------|
| `click_confirm.py` (new) | ClickPlan, ROI crop, similarity, execute_click_with_confirm |
| `navigator.py` | `grab_roi(x,y,w,h)` via full screenshot crop |
| `ui_loop.py` | Wire click/back to confirm path |
| `test_core.py` | Unit tests |

---

### Task 1: `click_confirm` + `Navigator.grab_roi`

**Files:**
- Create: `click_confirm.py`
- Modify: `navigator.py`
- Modify: `test_core.py`

**Interfaces:**
- `ROI_PAD_PX = 12`, `ROI_CONFIRM_THRESHOLD = 0.90`, `COORDS_ROI_SIZE = 48`
- `ClickPlan(x, y, roi_ref, template_name, score)`
- `roi_bounds_around(cx, cy, tw, th, vw, vh, pad=...) -> (x,y,w,h)`
- `crop_roi(screen, x, y, w, h) -> ndarray`
- `roi_similar(ref, now, threshold=...) -> tuple[bool, float]`
- `plan_template_click(nav, screen, template_name, bounds=None, threshold=None) -> ClickPlan | None`
- `plan_coords_click(screen, x, y) -> ClickPlan`
- `confirm_roi(nav, plan) -> tuple[bool, float]` — uses `nav.grab_roi`
- `execute_click_with_confirm(nav, plan) -> bool`
- `Navigator.grab_roi(self, x, y, w, h) -> ndarray` — full shot + crop

- [x] **Step 1: Tests** for `roi_similar` same/blocked; `execute_click_with_confirm` skips click on fail
- [x] **Step 2: Implement module + grab_roi**
- [x] **Step 3: Tests pass**

---

### Task 2: Wire `UiLoop`

**Files:**
- Modify: `ui_loop.py`
- Modify: `test_core.py`

- [x] **Step 1: Tests** — click step / back do not advance when confirm fails; back does not rewind on ROI fail
- [x] **Step 2: `_do_click_step` / `_do_back` use plan + execute_click_with_confirm**
- [x] **Step 3: Related tests pass**

---

### Task 3: Rebuild desktop exe (when user needs it)

Optional; only if requested after tests green.
