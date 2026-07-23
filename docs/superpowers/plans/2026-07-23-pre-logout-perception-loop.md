# 预退出感知环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 云游戏打开后到点登录页「退出」并确认期间，用同步感知环替换 PopupMonitor + 30s 重试。

**Architecture:** 在 `ui_loop.py` 新增 `run_pre_logout_loop` + `PreLogoutResult`；复用 `_close_popup` / `classify` 弹窗路径。`gui/app.py` 阶段 2 与再跑一轮改为调用该环。

**Tech Stack:** Python、现有 `Navigator` / `ui_state.classify`、pytest。

**Spec:** `docs/superpowers/specs/2026-07-23-pre-logout-perception-loop-design.md`

## Global Constraints

- 弹窗优先于退出按钮；确认模板用下半屏 + `CONFIRM_THRESHOLD`
- 超时未退出不中断工作流，进入阶段 3
- 不改阶段 4 截图 `UiLoop.run`
- 用户未要求则不 git commit

---

### Task 1: `run_pre_logout_loop` API + 单测

**Files:**
- Modify: `ui_loop.py`
- Modify: `test_core.py`

**Interfaces:**
- Produces:
  - `PreLogoutResult(logout_clicked: bool, confirm_clicked: str | None, timed_out: bool)`
  - `run_pre_logout_loop(nav, *, stop_event=None, on_log=None, timeout_s=120.0, tick_s=0.5, confirm_wait_s=5.0) -> PreLogoutResult`

- [ ] **Step 1: Write failing tests** in `test_core.py` class `TestPreLogoutLoop`:

```python
class TestPreLogoutLoop:
    def test_closes_popup_before_logout(self):
        from ui_loop import run_pre_logout_loop
        from ui_state import UiState
        nav = Mock()
        # classify: POPUP then MAIN-like (no popup); find_and_click logout True then confirm
        ...

    def test_logout_then_confirm_ends(self):
        ...

    def test_logout_without_confirm_ends_after_wait(self):
        ...

    def test_timeout_without_logout(self):
        ...

    def test_stop_event_aborts(self):
        ...
```

- [ ] **Step 2: Run tests — expect FAIL** (import / not found)

- [ ] **Step 3: Implement `PreLogoutResult` + `run_pre_logout_loop`**

逻辑草图：
1. `deadline = time.time() + timeout_s`
2. `logout_clicked=False`, `confirm_clicked=None`, `post_logout_since=None`
3. loop until stop / deadline:
   - `state, _ = classify(nav)`（无 path）
   - if POPUP/CONFIRM: close via shared helper；若 `logout_clicked` 且点到确认模板 → 设 `confirm_clicked` 并 return
   - elif not logout_clicked: `find_and_click("game_logout_btn.png", ...)` → 成功则 `logout_clicked=True`, `post_logout_since=now`
   - elif logout_clicked: 若 `now - post_logout_since >= confirm_wait_s` → return（无确认也结束）
   - else sleep tick_s
4. return timed_out=True if never logout

抽取：让 `UiLoop._close_popup` 可被模块级函数 `close_perception_popup(nav, on_log=...)` 复用，或 `run_pre_logout_loop` 内复制同等逻辑（优先抽函数避免重复）。

- [ ] **Step 4: Run `TestPreLogoutLoop` — PASS**

---

### Task 2: 接入 `gui/app.py`

**Files:**
- Modify: `gui/app.py`（阶段 2 首次 + 再跑一轮两处）

- [ ] **Step 1:** 两处替换为：

```python
from ui_loop import run_pre_logout_loop
# 可选：保留一次百分比粗清
result = run_pre_logout_loop(
    _nav,
    stop_event=self._stop_event,
    on_log=lambda text, level="info": self._send({"type": "log", "text": text, "level": level}),
)
# 按 result 打日志；不因 timed_out 中断
```

删除该时段的 `PopupMonitor.close_all` / 30s 重试 / 单独 `click_confirm_dialog`（环内已覆盖）。

- [ ] **Step 2:** 跑相关单测 + `TestUiClassify` / `TestUiLoopRun` 回归

---

### Task 3: 验收说明

- [ ] 日志可见「预退出感知环」启停
- [ ] 不要求本步打包 exe（除非用户另提）
