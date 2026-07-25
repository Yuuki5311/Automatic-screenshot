# 进入游戏后返回箭头清理 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 在点击"进入游戏"后、弹窗清理前，插入一个返回箭头清理环，防止因停在子页面而导致头像验证失败。

**架构:** 单文件内联改动 —— 在 `gui/app.py` 的 `_run_workflow()` 中，`time.sleep(10)` 之后、弹窗清理之前，添加 8 行 while 循环。

**技术栈:** Python 3.12, Selenium (Navigator 模板匹配)

## 全局约束

- 不向 `ui_state.py` 的 `POPUP_CLOSE_TEMPLATES` 或 `POPUP_CONFIRM_TEMPLATES` 添加 `back_arrow.png`
- 不修改 `popup_monitor.py`
- 不修改 `ui_loop.py` 中现有的 back_arrow 用法

---

### 任务 1: 在进入游戏后的清理阶段插入返回箭头清理环

**文件:**
- 修改: `C:\Automatic-screenshot\gui\app.py:629-632`

**接口:**
- 消费: `Navigator.find_and_click()`（已存在）, `time.sleep()`（内置）
- 产出: 无新函数 — 内联 while 循环

- [ ] **步骤 1: 运行现有测试以确认基线通过**

```bash
cd C:\Automatic-screenshot && python test_core.py
```

预期: 全部测试通过。

- [ ] **步骤 2: 插入返回箭头清理环**

编辑 `gui/app.py`，将第 629-632 行：

```python
            # ---- 进入游戏后先等 10 秒，再清弹窗，然后验证是否进入主界面 ----
            self._send({"type": "log", "text": "等待 10 秒后处理弹窗..."})
            time.sleep(10)
            self._send({"type": "log", "text": "进入游戏后清理弹窗..."})
```

替换为：

```python
            # ---- 进入游戏后先等 10 秒，再清返回箭头 + 弹窗，然后验证是否进入主界面 ----
            self._send({"type": "log", "text": "等待 10 秒后处理弹窗..."})
            time.sleep(10)

            # 先处理返回箭头：点进入游戏后可能停在子页面
            ARROW_TIMEOUT = 5
            while True:
                if nav.find_and_click("back_arrow.png", timeout=ARROW_TIMEOUT, max_retries=1):
                    self._send({"type": "log", "text": "已点击返回箭头，继续检查..."})
                    time.sleep(1)
                    continue
                break
            self._send({"type": "log", "text": "返回箭头检查完毕"})

            # 再清弹窗
            self._send({"type": "log", "text": "进入游戏后清理弹窗..."})
```

- [ ] **步骤 3: 再次运行测试套件**

```bash
cd C:\Automatic-screenshot && python test_core.py
```

预期: 全部测试通过。（新增代码不在测试覆盖范围内——它依赖 Selenium + Navigator，且是纯内联逻辑。现有测试确认无回归。）

- [ ] **步骤 4: 提交**

```bash
cd C:\Automatic-screenshot
git add gui/app.py
git commit -m "feat: add back-arrow cleanup loop after enter-game before popup drain

Insert a while loop that detects and clicks back_arrow.png for up to 5s
per iteration, repeating until no arrow remains. Runs after the 10s
post-enter-game wait, before the existing popup cleanup, ensuring the
game has navigated back to the main UI before avatar verification."
```
