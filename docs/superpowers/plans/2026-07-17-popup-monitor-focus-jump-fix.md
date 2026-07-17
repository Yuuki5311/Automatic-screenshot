# 弹窗监控误触导致页面跳转修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让后台弹窗监控只安全关闭明确的 X 按钮，不再误点确认按钮或校准坐标而跳回腾讯先锋页面。

**Architecture:** 在 `Navigator` 中为模板等待增加区域限制，并为点击增加可关闭的坐标兜底开关；默认行为保持兼容。`PopupMonitor` 使用严格白名单、统一上半屏区域和禁用兜底参数，登录及退出流程继续显式处理确认按钮。

**Tech Stack:** Python 3、OpenCV、PyAutoGUI、`unittest.mock`、现有 `test_core.py` 测试运行器

## Global Constraints

- 后台监控仅自动点击 `popup_close.png` 和 `popup_close_small.png`。
- 两个关闭按钮的匹配阈值固定为 `0.85`。
- 后台检测和点击必须使用同一上半屏 `bounds`。
- 后台监控不得使用 `calibrated_coords.json` 坐标兜底。
- 后台监控不得点击屏幕空白区域作为关闭失败兜底。
- `find_and_click` 的现有调用默认继续允许坐标兜底。
- 登录、退出和其他确认按钮继续由主流程显式操作。

---

### Task 1: 为 Navigator 增加安全匹配选项

**Files:**
- Modify: `test_core.py:206-234`
- Modify: `navigator.py:136-235`

**Interfaces:**
- Produces: `Navigator.find_and_click(..., allow_fallback: bool = True) -> bool`
- Produces: `Navigator.wait_for_template(..., bounds: tuple | None = None) -> bool`

- [ ] **Step 1: 写出失败测试**

在 `TestNavigatorThreshold` 后增加以下测试。测试通过 `__new__` 避免真实屏幕初始化，并验证禁用兜底及区域裁剪行为：

```python
class TestNavigatorSafetyOptions:
    """测试后台监控需要的安全匹配选项。"""

    @patch("navigator.time.sleep", return_value=None)
    @patch("navigator.pyautogui.click")
    def test_find_and_click_can_disable_coordinate_fallback(
        self, mock_click, _mock_sleep
    ):
        from navigator import Navigator

        nav = Navigator.__new__(Navigator)
        nav.threshold = 0.53
        nav.max_retries = 1
        nav._scale = 1.0
        nav._load_template = Mock(return_value=np.ones((2, 2, 3), dtype=np.uint8))
        nav._get_screenshot = Mock(return_value=np.zeros((8, 8, 3), dtype=np.uint8))
        nav._load_coords = Mock(return_value={"popup_close": [10, 20]})

        result = nav.find_and_click(
            "popup_close.png",
            max_retries=1,
            threshold=1.1,
            allow_fallback=False,
        )

        assert result is False
        nav._load_coords.assert_not_called()
        mock_click.assert_not_called()

    @patch("navigator.time.sleep", return_value=None)
    @patch("navigator.cv2.matchTemplate")
    def test_wait_for_template_limits_matching_to_bounds(
        self, mock_match, _mock_sleep
    ):
        from navigator import Navigator

        nav = Navigator.__new__(Navigator)
        nav.threshold = 0.53
        nav._load_template = Mock(return_value=np.ones((2, 2, 3), dtype=np.uint8))
        nav._get_screenshot = Mock(return_value=np.zeros((20, 30, 3), dtype=np.uint8))
        mock_match.return_value = np.array([[1.0]], dtype=np.float32)

        assert nav.wait_for_template(
            "popup_close.png",
            timeout=0.1,
            bounds=(4, 5, 10, 8),
        )

        search_area = mock_match.call_args.args[0]
        assert search_area.shape == (8, 10, 3)
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```bash
python -m pytest test_core.py::TestNavigatorSafetyOptions -v
```

Expected: FAIL，分别提示 `find_and_click()` 不接受 `allow_fallback`、`wait_for_template()` 不接受 `bounds`。

- [ ] **Step 3: 实现最小修改**

修改 `Navigator.find_and_click` 签名并只在允许时执行现有坐标兜底：

```python
def find_and_click(
    self, template_name: str, timeout: int = 10,
    bounds: tuple = None, max_retries: int = None,
    threshold: float = None, allow_fallback: bool = True,
) -> bool:
    # 保留现有模板匹配循环

    if allow_fallback:
        coords = self._load_coords()
        key = template_name.replace(".png", "")
        if key in coords:
            x, y = coords[key]
            pyautogui.click(x, y)
            log.info(f"兜底点击 {template_name} @ ({x}, {y})")
            time.sleep(CLICK_INTERVAL)
            return True

    log.warning(f"未能找到: {template_name}")
    return False
```

修改 `wait_for_template`，在调用 OpenCV 前应用与 `find_and_click` 相同的区域裁剪：

```python
def wait_for_template(
    self, template_name: str, timeout: int = 15,
    threshold: float = None, bounds: tuple = None,
) -> bool:
    # 保留现有模板加载和循环
    screen = self._get_screenshot()
    if bounds is not None:
        x, y, w, h = bounds
        search_area = screen[y:y+h, x:x+w]
    else:
        search_area = screen
    result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
```

同时更新两个方法的 docstring，准确说明新参数。

- [ ] **Step 4: 运行测试并确认通过**

Run:

```bash
python -m pytest test_core.py::TestNavigatorSafetyOptions -v
```

Expected: `2 passed`。

- [ ] **Step 5: 运行 Navigator 相关回归测试**

Run:

```bash
python -m pytest test_core.py::TestNavigatorThreshold test_core.py::TestTemplateCache -v
```

Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add navigator.py test_core.py
git commit -m "feat: 增加安全模板匹配选项"
```

---

### Task 2: 将 PopupMonitor 收紧为关闭按钮白名单

**Files:**
- Modify: `test_core.py:73-123,178-204`
- Modify: `popup_monitor.py:42-98`

**Interfaces:**
- Consumes: `Navigator.wait_for_template(..., bounds: tuple | None = None) -> bool`
- Consumes: `Navigator.find_and_click(..., allow_fallback: bool = True) -> bool`
- Produces: `PopupMonitor._do_scan() -> bool`，只允许两个 X 模板产生点击

- [ ] **Step 1: 写出失败测试并替换旧配置断言**

删除 `TestPopupThresholds.test_thresholds_configured_correctly` 中要求两个确认模板存在的源码字符串断言，改为行为测试：

```python
class TestPopupSafety:
    """验证后台监控只操作安全的关闭按钮。"""

    @patch("popup_monitor.time.sleep", return_value=None)
    @patch("popup_monitor.pyautogui.size", return_value=(1470, 956))
    def test_scan_uses_close_only_allowlist_and_disables_fallback(
        self, _mock_size, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        nav.wait_for_template.side_effect = [True, True, False]
        nav.find_and_click.return_value = True
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is True

        top_bounds = (0, 0, 2940, 956)
        nav.find_and_click.assert_called_once_with(
            "popup_close.png",
            timeout=2,
            bounds=top_bounds,
            threshold=0.85,
            allow_fallback=False,
        )
        checked_templates = [
            call.args[0] for call in nav.wait_for_template.call_args_list
        ]
        assert set(checked_templates) <= {
            "popup_close.png",
            "popup_close_small.png",
        }
        for call in nav.wait_for_template.call_args_list:
            assert call.kwargs["bounds"] == top_bounds

    @patch("popup_monitor.time.sleep", return_value=None)
    @patch("popup_monitor.pyautogui.click")
    @patch("popup_monitor.pyautogui.size", return_value=(1470, 956))
    def test_scan_never_uses_blank_area_fallback(
        self, _mock_size, mock_click, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        nav.wait_for_template.return_value = True
        nav.find_and_click.return_value = False
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is False
        mock_click.assert_not_called()
```

- [ ] **Step 2: 运行测试并确认按预期失败**

Run:

```bash
python -m pytest test_core.py::TestPopupSafety -v
```

Expected: FAIL，显示 `find_and_click` 调用缺少 `allow_fallback=False`、`wait_for_template` 调用缺少 `bounds`，或监控仍执行空白区域点击。

- [ ] **Step 3: 实现白名单监控**

将 `_do_scan` 中按钮配置和调用收紧为：

```python
top_bounds = (0, 0, int(sw * scale), int(sh * scale * 0.5))
buttons = [
    ("popup_close.png", top_bounds, "X按钮", 0.85),
    ("popup_close_small.png", top_bounds, "小弹窗X按钮", 0.85),
]

for template, bounds, label, threshold in buttons:
    kwargs = {"threshold": threshold, "bounds": bounds}
    if self.navigator.wait_for_template(template, timeout=1, **kwargs):
        time.sleep(0.5)
        if not self.navigator.wait_for_template(
            template, timeout=0.5, **kwargs
        ):
            continue
        found_any = True
        time.sleep(2)
        if self.navigator.find_and_click(
            template,
            timeout=2,
            bounds=bounds,
            threshold=threshold,
            allow_fallback=False,
        ):
            time.sleep(1)
            if not self.navigator.wait_for_template(
                template, timeout=1, **kwargs
            ):
                self._closed_count += 1
                closed_this_round += 1
                log.info(
                    f"异步关闭弹窗 #{self._closed_count} ({label})"
                )
                break
```

删除不再使用的 `bottom_bounds`，并删除“未关掉时点击屏幕空白区域”的兜底逻辑。

- [ ] **Step 4: 运行弹窗监控测试并确认通过**

Run:

```bash
python -m pytest test_core.py::TestPopupMonitor test_core.py::TestPopupSafety -v
```

Expected: 全部 PASS。

- [ ] **Step 5: 运行完整测试**

Run:

```bash
python -m pytest test_core.py -v
```

Expected: 全部 PASS，无异常或警告。

- [ ] **Step 6: 静态检查危险模板不再由后台监控引用**

Run:

```bash
rg "game_logout_confirm|game_popup_confirm" popup_monitor.py
```

Expected: 无输出，退出码为 1。

- [ ] **Step 7: 提交**

```bash
git add popup_monitor.py test_core.py
git commit -m "fix: 防止弹窗监控误点确认按钮"
```

---

### Task 3: 最终回归与人工验收交接

**Files:**
- Verify: `navigator.py`
- Verify: `popup_monitor.py`
- Verify: `test_core.py`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的最终行为
- Produces: 可交付的测试证据和人工运行检查项

- [ ] **Step 1: 执行语法编译检查**

Run:

```bash
python -m py_compile navigator.py popup_monitor.py test_core.py
```

Expected: 无输出，退出码为 0。

- [ ] **Step 2: 再次执行完整测试**

Run:

```bash
python -m pytest test_core.py -v
```

Expected: 全部 PASS。

- [ ] **Step 3: 检查最终差异**

Run:

```bash
git diff HEAD~2 --check
git status --short
```

Expected: `git diff --check` 无输出；状态仅包含用户已有的未跟踪构建产物，不包含未提交的源代码修改。

- [ ] **Step 4: 人工运行验收**

启动应用进入截图阶段，保持异步监控运行，依次验证：

1. 手动切换到云游戏画面后，等待至少 15 秒，不再自动跳回腾讯先锋。
2. 日志中不出现 `game_logout_confirm.png` 或 `game_popup_confirm.png` 的后台扫描记录。
3. 制造一个包含已配置 X 按钮的普通弹窗，确认它仍被自动关闭。
4. 完成截图流程后的显式退出确认仍可正常点击。

Expected: 四项全部满足；若无法访问真实云游戏环境，则明确将本步骤标记为待用户执行，不以自动测试替代该结论。
