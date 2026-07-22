# 截图任务「按键」插入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在阶段 4 任务表「万象图鉴-灵宝」与「天幕」之间插入「按键」截图任务（局内 → 按键 → 截图 → 返回）。

**Architecture:** 仅扩展现有 `screenshot_tasks` 三元组列表；`UiLoop` 无需改动。同步更新结构单测与 `capture_templates.py` 登记，便于本地截取 `in_game_btn.png` / `keybind_btn.png`。

**Tech Stack:** Python、pytest、现有 OpenCV 模板匹配导航

## Global Constraints

- 任务名 / 输出文件：`按键`
- 模板文件名：`in_game_btn.png`、`keybind_btn.png`
- `back_count = 1`；无 bounds
- 不改 `UiLoop` / 登录 / 启游戏
- 不伪造游戏模板 PNG；不自动 git commit（除非用户明确要求）

---

### Task 1: 单测先插入「按键」任务

**Files:**
- Modify: `test_core.py`（`TestScreenshotTasks.test_all_tasks_have_valid_structure` 内 `screenshot_tasks`）
- Test: `test_core.py::TestScreenshotTasks`

**Interfaces:**
- Consumes: 无
- Produces: 测试列表在灵宝后含 `("按键", [("in_game_btn.png", ...), ("keybind_btn.png", ...)], 1)`

- [ ] **Step 1: 写失败断言（扩展任务列表）**

在 `TestScreenshotTasks` 的 `screenshot_tasks` 中，将「万象图鉴-灵宝」与「天幕」之间改为：

```python
("万象图鉴-灵宝", [("lingbao.png", "desc")], 1),
("按键", [
    ("in_game_btn.png", "desc"),
    ("keybind_btn.png", "desc"),
], 1),
("天幕", [("tianmu.png", "desc")], 1),
```

另增一项顺序断言（同 class 内新方法）：

```python
def test_anjian_follows_lingbao(self):
    names = [
        "主页", "英雄", "万象图鉴首页", "万象图鉴-灵宝", "按键", "天幕",
    ]
    # 最小检查：按键紧跟灵宝
    tasks = [
        ("万象图鉴-灵宝", [("lingbao.png", "d")], 1),
        ("按键", [("in_game_btn.png", "d"), ("keybind_btn.png", "d")], 1),
        ("天幕", [("tianmu.png", "d")], 1),
    ]
    assert [t[0] for t in tasks] == ["万象图鉴-灵宝", "按键", "天幕"]
    assert tasks[1][2] == 1
    assert [c[0] for c in tasks[1][1]] == ["in_game_btn.png", "keybind_btn.png"]
```

（若不想单独方法，仅扩展原列表即可；原 `test_all_tasks_have_valid_structure` 已覆盖结构。）

- [ ] **Step 2: 运行单测确认仍通过（仅改测试数据时本步应绿）**

Run: `pytest test_core.py::TestScreenshotTasks -v`

Expected: PASS（本任务只改测试内嵌列表，尚不依赖 `gui/app.py`）

- [ ] **Step 3: （可选）Commit** — 仅当用户要求时提交

---

### Task 2: `gui/app.py` 插入真实任务

**Files:**
- Modify: `gui/app.py`（`screenshot_tasks`，约灵宝条目之后）

**Interfaces:**
- Consumes: Task 1 约定的模板名与顺序
- Produces: 运行时任务表与单测一致

- [ ] **Step 1: 写失败测试（对照生产任务表）**

在 `TestScreenshotTasks` 增加从 `gui.app` 不可直接导入任务表时，改为**文档化对照**：在同文件增加注释或小型测试，解析期望顺序字符串：

更稳妥做法：把期望片段写成断言，实现时复制到 `gui/app.py`。实现前先加：

```python
def test_expected_anjian_task_tuple(self):
    task = ("按键", [
        ("in_game_btn.png", "点击局内按钮"),
        ("keybind_btn.png", "点击按键按钮"),
    ], 1)
    assert task[0] == "按键"
    assert task[2] == 1
```

- [ ] **Step 2: 在 `gui/app.py` 的 `screenshot_tasks` 中，灵宝后插入：**

```python
("万象图鉴-灵宝", [
    ("lingbao.png", "点击灵宝"),
], 1),
("按键", [
    ("in_game_btn.png", "点击局内按钮"),
    ("keybind_btn.png", "点击按键按钮"),
], 1),
("天幕", [
    ("tianmu.png", "点击天幕"),
], 1),
```

- [ ] **Step 3: 同步 `TestScreenshotTasks` 内嵌完整列表与 `gui/app.py` 任务名顺序一致（含「按键」）**

- [ ] **Step 4: 运行**

Run: `pytest test_core.py::TestScreenshotTasks -v`

Expected: PASS

- [ ] **Step 5: （可选）Commit** — 仅当用户要求时提交

---

### Task 3: 登记 capture 模板

**Files:**
- Modify: `capture_templates.py`（`TEMPLATES`，图鉴段 `lingbao.png` 附近）

**Interfaces:**
- Consumes: `in_game_btn.png`、`keybind_btn.png`
- Produces: `python capture_templates.py --only in_game_btn.png keybind_btn.png` 可选中这两项

- [ ] **Step 1: 在 `lingbao.png` 条目后加入：**

```python
("lingbao.png", "【灵宝】入口", "万象图鉴页"),
("in_game_btn.png", "【局内】按钮（需新截取）", "灵宝返回后当前页"),
("keybind_btn.png", "【按键】按钮（需新截取）", "点局内后页面"),
("tianmu.png", "【天幕】入口（需新截取）", "万象图鉴页"),
```

- [ ] **Step 2: 冒烟**

Run: `python -c "from capture_templates import TEMPLATES; n=[t[0] for t in TEMPLATES]; assert 'in_game_btn.png' in n and 'keybind_btn.png' in n; print('ok')"`

Expected: `ok`

- [ ] **Step 3: （可选）Commit** — 仅当用户要求时提交

---

## Spec coverage

| Spec 项 | Task |
|---------|------|
| 灵宝后插入「按键」 | Task 2 |
| 局内→按键→截图→返回1 | Task 2 |
| 单测结构 | Task 1–2 |
| capture 登记 | Task 3 |
| 不改 UiLoop | 无相关 task |

## 实战后续（非本 plan 代码）

模板就位后本地执行：

```text
python capture_templates.py --only in_game_btn.png keybind_btn.png
```

将 PNG 放入 `templates/` 后再跑完整阶段 4。
