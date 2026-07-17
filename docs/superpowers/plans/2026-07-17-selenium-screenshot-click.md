# Selenium 截图与点击统一实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 游戏内匹配截图与点击统一为 Selenium CSS 坐标系（约 1920×1080）。

**Architecture:** `Navigator` / `Screenshotter` 持有同一个 `driver`；截图用 `get_screenshot_as_png`，点击用 ActionChains 视口坐标；`_scale` 固定为 1.0。GUI 与 `game_login` 的 bounds 改用 `BROWSER_WIDTH` / `BROWSER_HEIGHT`。

**Tech Stack:** Python 3.12、Selenium 4、OpenCV、pytest

## Global Constraints

- 截图：`driver.get_screenshot_as_png()`，CSS 像素。
- 点击：Selenium ActionChains，CSS 像素，相对视口左上角。
- `Navigator._scale = 1.0`，不做 Retina 物理/逻辑换算。
- `calibrated_coords.json` 存 CSS 像素；旧桌面坐标作废需重标。
- 不改 `web_login` / `game_launcher` DOM 流程，不改 `client_launcher.py`。
- 本轮不批量重做全部模板图。

---

### Task 1: Navigator 改用 Selenium 截图与点击

**Files:**
- Modify: `navigator.py`
- Modify: `test_core.py`

**Interfaces:**
- Produces: `Navigator(driver, templates_dir=..., threshold=..., max_retries=...)`
- Produces: `Navigator.click_css(x: int, y: int) -> None`（公开，供 GUI 坐标点击）
- Produces: `_scale == 1.0`

- [ ] **Step 1: 编写失败测试**

```python
class TestNavigatorSelenium:
    def test_scale_is_one_without_pyautogui_screenshot(self):
        from navigator import Navigator
        driver = Mock()
        with patch("navigator.pyautogui.screenshot") as mock_shot:
            nav = Navigator(driver=driver, templates_dir=TEMPLATES_DIR)
            assert nav._scale == 1.0
            mock_shot.assert_not_called()

    @patch("navigator.ActionChains")
    def test_click_css_uses_action_chains(self, mock_ac):
        from navigator import Navigator
        driver = Mock()
        chains = mock_ac.return_value
        chains.move_by_offset.return_value = chains
        chains.click.return_value = chains
        chains.perform.return_value = None
        nav = Navigator.__new__(Navigator)
        nav.driver = driver
        nav._scale = 1.0
        nav.click_css(100, 200)
        mock_ac.assert_called_once_with(driver)
        chains.move_by_offset.assert_called()
```

- [ ] **Step 2: 运行确认失败**

`python -m pytest test_core.py::TestNavigatorSelenium -q`

- [ ] **Step 3: 实现 Navigator**

- `__init__(self, driver, ...)` 保存 `self.driver`，`self._scale = 1.0`，删除 `_detect_scale` 调用。
- `_get_screenshot`：`png = self.driver.get_screenshot_as_png()` → `cv2.imdecode` → BGR。
- `click_css(x, y)` / `_click_at`：`ActionChains(driver).move_by_offset` 相对 body 或使用
  `driver.execute_script` 派发点击；推荐：

```python
def click_css(self, x: int, y: int) -> None:
    self.driver.execute_script(
        """
        const el = document.elementFromPoint(arguments[0], arguments[1]);
        if (el) el.dispatchEvent(new MouseEvent('click', {
            bubbles: true, cancelable: true, view: window,
            clientX: arguments[0], clientY: arguments[1]
        }));
        """,
        int(x), int(y),
    )
```

若云游戏 canvas 需要原生指针，改用 ActionChains 从 `(0,0)` 重置后 `move_by_offset(x,y).click()`。优先 ActionChains；若测试难 mock script，用 ActionChains。

```python
def _click_at(self, x: int, y: int) -> None:
    self.click_css(x, y)

def click_css(self, x: int, y: int) -> None:
    from selenium.webdriver.common.action_chains import ActionChains
    ActionChains(self.driver).move_by_offset(0, 0).perform()  # 不可靠
```

更稳妥写法（每次从 viewport 原点）：

```python
def click_css(self, x: int, y: int) -> None:
    from selenium.webdriver.common.action_chains import ActionChains
    from selenium.webdriver.common.actions.action_builder import ActionBuilder
    from selenium.webdriver.common.actions.pointer_input import PointerInput
    actions = ActionBuilder(self.driver)
    actions.pointer_action.move_to_location(int(x), int(y))
    actions.pointer_action.click()
    actions.perform()
```

- 兜底坐标分支改为 `self._click_at(x, y)`。
- 移除 `_physical_to_logical` 在点击路径中的使用（或保留为恒等）。

- [ ] **Step 4: 更新依赖 Navigator 的单元测试**

凡 `Navigator(...)` 无 driver 的测试改为传入 `Mock()` driver，或 `__new__` 手动赋值。

- [ ] **Step 5: 测试通过后提交**

`git commit -m "feat: Navigator uses Selenium screenshot and CSS clicks"`

---

### Task 2: Screenshotter 使用 driver

**Files:**
- Modify: `screenshotter.py`
- Modify: `test_core.py`

**Interfaces:**
- Produces: `Screenshotter(output_dir, driver)`
- Produces: `take(name) -> str` 写入浏览器 PNG

- [ ] **Step 1: 失败测试** — mock driver 返回最小 PNG，断言文件存在且非空。
- [ ] **Step 2: 实现** — `take` 用 `driver.get_screenshot_as_png()` 写文件。
- [ ] **Step 3: 提交** — `feat: Screenshotter saves browser screenshots`

---

### Task 3: 接线 GUI / game_login / popup bounds

**Files:**
- Modify: `gui/app.py`
- Modify: `login.py`
- Modify: `popup_monitor.py`（若仍用 pyautogui.size）
- Modify: `test_core.py`（平台 bounds 用例改 CSS）

**Interfaces:**
- Consumes: `Navigator(driver=...)`, `Screenshotter(..., driver=...)`, `nav.click_css`
- Consumes: `BROWSER_WIDTH`, `BROWSER_HEIGHT`

- [ ] **Step 1: 所有 `Navigator(...)` 传入 `driver`**
- [ ] **Step 2: bounds 改用 `BROWSER_WIDTH/HEIGHT`（×1.0）**
- [ ] **Step 3: `__coords__` 与百分比点击改 `nav.click_css`**
- [ ] **Step 4: `game_login` 去掉 `pyautogui.size`，用 config 尺寸或 `nav` 视口**
- [ ] **Step 5: 测试 + 提交** `feat: wire GUI and game_login to CSS viewport`

---

### Task 4: 标定工具改为 CSS

**Files:**
- Modify: `calibrate_coords.py`

**Interfaces:**
- Produces: CSS 坐标写入 `calibrated_coords.json`

- [ ] **Step 1: 启动/复用浏览器，提示在 1920×1080 游戏画面内移动鼠标**
- [ ] **Step 2: 记录坐标 = 屏幕鼠标位置 − 浏览器视口屏幕原点（`driver.execute_script` 取 `window.screenX/Y` + chrome 高度，或让用户在最大化固定窗口下用视口相对采集）**
- [ ] **Step 3: 提交** `feat: calibrate_coords records CSS viewport coordinates`

简化实现：用 Selenium 打开后打印窗口信息，采集时：

```python
origin_x = driver.execute_script("return window.screenX + (window.outerWidth - window.innerWidth) / 2;")
# 更可靠：
chrome_y = driver.execute_script("return window.outerHeight - window.innerHeight;")
origin_x = driver.execute_script("return window.screenX;")
origin_y = driver.execute_script("return window.screenY;") + chrome_y
css_x = mouse_x - origin_x
css_y = mouse_y - origin_y
```

- [ ] **Step 4: 在工具开头打印警告：旧 JSON 需重标**

---

### Task 5: 完整验证

- [ ] `python -m pytest -q` 全部通过
- [ ] `python -m compileall -q navigator.py screenshotter.py gui login.py calibrate_coords.py`
- [ ] 检查无残留关键路径 `pyautogui.screenshot`（client_launcher 除外）
