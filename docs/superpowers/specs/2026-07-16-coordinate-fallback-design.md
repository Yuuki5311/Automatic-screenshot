# Coordinate Fallback for Template Matching Failures

**Date**: 2026-07-16
**Status**: Approved

## Motivation

The screenshot workflow relies on OpenCV template matching (`cv2.matchTemplate`) to locate and click UI buttons in the game. When template matching fails (e.g., due to video stream compression artifacts, slight UI changes, or resolution differences), the entire screenshot task fails. Adding a coordinate-based fallback using pre-calibrated screen positions improves robustness.

## Design

### Scope

A single file change to `navigator.py`.

### Behavior

When `find_and_click(template_name)` exhausts all retry attempts:

1. Load `calibrated_coords.json` lazily (first use only)
2. Extract the key by stripping `.png` from `template_name`
3. If a coordinate exists for that key, click at `(x, y)` directly via `pyautogui.click()`
4. Return `True` on success; if no coordinate found, return `False` (existing behavior)

```
template match fails (all retries exhausted)
  → prior step anchor check (existing rollback logic)
  → lookup coordinate in calibrated_coords.json
    → found → pyautogui.click(x, y) → return True ✅
    → not found → log warning → return False ❌
```

### Implementation

**File**: `navigator.py`

**`__init__`** — add lazy-load flag:
```python
self._coords: dict | None = None
```

**`_load_coords()`** — new method, lazy-load on first fallback:
```python
def _load_coords(self) -> dict:
    if self._coords is not None:
        return self._coords
    try:
        import json
        path = resource_path("calibrated_coords.json")
        with open(path, "r") as f:
            self._coords = json.load(f)
        log.info(f"已加载 {len(self._coords)} 个兜底坐标")
    except Exception:
        log.warning("兜底坐标加载失败，将跳过坐标点击兜底")
        self._coords = {}
    return self._coords
```

**`find_and_click()`** — append before the final `return False`:
```python
# 兜底：坐标点击
coords = self._load_coords()
key = template_name.replace(".png", "")
if key in coords:
    x, y = coords[key]
    pyautogui.click(x, y)
    log.info(f"兜底点击 {template_name} @ ({x}, {y})")
    time.sleep(CLICK_INTERVAL)
    return True
```

### Key Decisions

| Decision | Rationale |
|---|---|
| Put fallback in `Navigator.find_and_click()` (not caller) | All consumers benefit: game_login, logout, screenshot workflow |
| Lazy-load coordinates on first use | Avoids unnecessary I/O on every Navigator instantiation |
| Skip `_physical_to_logical` conversion | JSON coordinates are logical pixels from `pyautogui.position()`; `pyautogui.click()` accepts logical directly |
| Key mapping: `template_name.replace('.png', '')` | JSON keys are template filenames without extension |
| Load failure → empty dict | Graceful degradation; subsequent fallbacks skip without retrying file I/O |

### Non-Goals

- No changes to `gui/app.py`, `login.py`, `game_launcher.py`, or any other caller
- No changes to `calibrated_coords.json` format or content
- No changes to the existing rollback/game-crash-recovery logic

## Testing

- Unit: `_load_coords()` returns dict on success, empty dict on file-not-found
- Unit: `find_and_click` with nonexistent template falls through to coordinate lookup
- Integration: Template matching failure triggers coordinate click as fallback in screenshot workflow
