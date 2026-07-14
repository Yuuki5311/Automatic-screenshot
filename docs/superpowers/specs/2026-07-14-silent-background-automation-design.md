# 静默后台自动化方案设计

## 目标

EXE 在 Windows 端运行时，用户可以同时在前台做其他事情——脚本全程不抢占鼠标、不弹窗、不干扰用户操作。

## 当前架构 vs 目标架构

```
当前（前台侵入式）：
┌─────────────────────────────┐
│ pyautogui.screenshot() 全屏   │ ← 截到其他窗口
│ pyautogui.click() 物理鼠标    │ ← 鼠标被抢走
│ driver.maximize_window() 全屏 │ ← 弹到前台
└─────────────────────────────┘

目标（后台静默式）：
┌─────────────────────────────┐
│ driver.get_screenshot() 页面 │ ← 只截 Chrome，不受遮挡
│ SendInput / JS click 静默输入 │ ← 鼠标不动
│ driver.minimize_window()    │ ← 最小化到任务栏
└─────────────────────────────┘
```

## 改动范围

涉及 4 个文件，1 个新增文件：

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `browser.py` | 修改 | 窗口最小化 + 导出 driver 尺寸信息 |
| `navigator.py` | 重写 | PyAutoGUI 截图/点击 → Selenium 截图 + Win32 SendInput |
| `screenshotter.py` | 修改 | PyAutoGUI 截图 → Selenium 截图 |
| `popup_monitor.py` | 修改 | 截图源切换 |
| `input_injector.py` | **新增** | Windows SendInput / macOS Quartz 静默输入 |

## 一、Chrome 窗口最小化（browser.py）

```python
# 之前
driver.maximize_window()
# macOS 全屏 AppleScript
osascript ... keystroke "f" using {command down, control down}

# 之后
driver.set_window_position(0, 0)
driver.set_window_size(1920, 1080)  # 固定窗口尺寸（截图分辨率保证）
driver.minimize_window()             # Windows: 最小化到任务栏
# macOS: 不需要全屏，最小化即可（Selenium 截图不依赖窗口可见性）
```

**关键点**：`driver.minimize_window()` 后 Chrome GPU 渲染继续，`driver.get_screenshot_as_png()` 正常返回页面内容。

## 二、Selenium 页面截图替代 PyAutoGUI 全屏截图

### 2.1 Screenshotter 改造（screenshotter.py）

```python
# 之前
class Screenshotter:
    def take(self, name):
        img = pyautogui.screenshot()  # 全屏
        img.save(filepath)

# 之后
class Screenshotter:
    def __init__(self, output_dir, driver):
        self.driver = driver  # 新增：持有 WebDriver 引用
    
    def take(self, name):
        # Selenium 截图 → 只截 Chrome 窗口内的游戏画面
        png_bytes = self.driver.get_screenshot_as_png()
        with open(filepath, "wb") as f:
            f.write(png_bytes)
```

### 2.2 Navigator 改造（navigator.py）

```python
# 之前
def _get_screenshot(self):
    img = pyautogui.screenshot()  # 全屏物理截图
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

# 之后  
def __init__(self, ..., driver):
    self.driver = driver  # 新增：持有 WebDriver 引用
    self._window_width = None
    self._window_height = None

def _get_screenshot(self):
    # Selenium 页面截图 → 不依赖窗口位置/遮挡
    png_bytes = self.driver.get_screenshot_as_png()
    img_array = cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
    
    # 记录窗口尺寸用于坐标映射（只需一次）
    if self._window_width is None:
        self._window_height, self._window_width = img_array.shape[:2]
        log.info(f"Chrome 窗口截图尺寸: {self._window_width}x{self._window_height}")
    
    return img_array
```

### 2.3 坐标映射变化

当前 Navigator 有 Retina 物理→逻辑坐标转换（`_detect_scale()`，仅 macOS）。改为 Selenium 截图后：

| 概念 | 之前（PyAutoGUI） | 之后（Selenium） |
|------|-------------------|-----------------|
| 截图像素尺寸 | 物理像素（Retina 2x=2940） | CSS 像素（1920x1080） |
| 点击坐标 | 逻辑点（需 /scale） | CSS 像素 + Chrome 窗口偏移 |
| DPI 缩放 | `_detect_scale()` 动态计算 | driver.set_window_size 固定，无需缩放 |

**窗口偏移处理**：`driver.set_window_position(x, y)` 决定 Chrome 窗口在屏幕上的位置。`pyautogui.click(screen_x, screen_y)` 需要把模板匹配到的 CSS 坐标（相对于截图左上角）加上窗口在屏幕上的偏移量。

简化方案：窗口固定在 `(0, 0)` 位置，CSS 坐标就是屏幕坐标，无需额外偏移。但窗口最小化后无法获取屏幕位置——所以点击必须改用 SendInput，不依赖鼠标位置。

核心变化：**完全放弃 `pyautogui.click()` 和屏幕坐标体系，改用 `driver.execute_script()` 模拟网页点击 + Win32 SendInput 模拟桌面点击**。

## 三、静默输入（新增 input_injector.py）

### 3.1 设计思路

阶段 1-2（网页登录 + 搜索）：使用 `driver.execute_script("arguments[0].click()", elem)`——已经在用，无需改动。

阶段 3-4（游戏内操作）：云游戏客户端是一个**视频流窗口内的 iframe**，模板匹配的按钮在视频画面中，不是 DOM 元素。所以：
- 模板匹配找到的 (x, y) 是**视频帧内部坐标**（CSS 像素）
- 需要点击的是 Chrome 窗口中对应屏幕位置
- 不能依赖 `pyautogui.click()`（移动物理鼠标，用户能感知）

### 3.2 方案：Win32 SendInput + macOS CGEvent

```python
# input_injector.py

import platform

SYSTEM = platform.system()

if SYSTEM == "Windows":
    import ctypes
    from ctypes import wintypes
    
    # Windows SendInput 结构体
    class MOUSEINPUT(ctypes.Structure): ...
    class INPUT(ctypes.Structure): ...
    
    def click_at(x: int, y: int):
        """向指定屏幕坐标注入鼠标点击事件，不移动物理光标。"""
        # SendInput(MOUSEEVENTF_LEFTDOWN | MOUSEEVENTF_LEFTUP)
        # 配合 MOUSEEVENTF_MOVE 到目标坐标
        # 鼠标光标不动（因为直接走硬件输入流，跳过了 SetCursorPos）

elif SYSTEM == "Darwin":
    import Quartz
    
    def click_at(x: int, y: int):
        """向指定屏幕坐标注入鼠标事件，不移动物理光标。"""
        # CGEventCreateMouseEvent + kCGMouseButtonLeft
        # CGEventPost(kCGHIDEventTap, event)
        # 相较于 PyAutoGUI：直接注入 HID 层级，不经过光标移动

else:  # Linux
    def click_at(x: int, y: int):
        # 使用 python-xlib 或回退到 pyautogui
```

### 3.3 Navigator 集成

```python
# navigator.py 中的 _click_at 方法

def _click_at(self, x: int, y: int):
    """将模板匹配到的 CSS 坐标转换为屏幕坐标并静默点击。"""
    # x, y 是相对于 Chrome 窗口视图的 CSS 像素坐标
    # 需要加上 Chrome 窗口在屏幕上的偏移
    screen_x = x + self._window_offset_x
    screen_y = y + self._window_offset_y
    click_at(screen_x, screen_y)  # input_injector.click_at
```

### 3.4 窗口偏移获取

在 `create_browser()` 后获取：

```python
# Selenium 不能直接获取窗口屏幕位置，需用 JS + CDP

# 方法：driver.set_window_position(x, y) 主动设置位置
driver.set_window_position(0, 0)
# 窗口固定在屏幕左上角 → 截图坐标 = 屏幕坐标
```

## 四、不需要改动的部分

| 模块 | 原因 |
|------|------|
| `login.py`（web_login） | 全程用 Selenium，不涉及 PyAutoGUI |
| `game_launcher.py` | 全程用 Selenium，不涉及 PyAutoGUI |
| `gui/app.py` | GUI 本身不直接调用 PyAutoGUI，通过 Navigator/Screenshotter 间接使用 |
| `client_launcher.py` | macOS 专用，暂不改造（当前关注 Windows） |
| `calibrate_coords.py` | 独立工具脚本 |
| `capture_templates.py` | 独立工具脚本 |

## 五、参数兼容性

### 窗口尺寸配置（config.py）

```python
# 新增
CHROME_WINDOW_X = 0       # Chrome 窗口屏幕 X 偏移
CHROME_WINDOW_Y = 0       # Chrome 窗口屏幕 Y 偏移
CHROME_WINDOW_WIDTH = 1920  # Chrome 窗口宽度（决定截图分辨率）
CHROME_WINDOW_HEIGHT = 1080
```

## 六、降级策略

```python
# 环境检测 → 自动选择输入方案
if platform.system() == "Windows":
    from input_injector import sendinput_click as click_at
elif platform.system() == "Darwin":
    from input_injector import quartz_click as click_at
else:
    import pyautogui
    click_at = lambda x, y: pyautogui.click(x, y)  # 回退
```

## 七、实现步骤

### 第一阶段（核心）
1. `browser.py`：窗口最小化，固定位置和尺寸
2. `config.py`：新增窗口配置常量
3. **新增** `input_injector.py`：Win32 SendInput 实现

### 第二阶段（集成）
4. `navigator.py`：`_get_screenshot()` 改用 Selenium；`_click_at()` 改用 `input_injector.click_at()`
5. `screenshotter.py`：`take()` 改用 `driver.get_screenshot_as_png()`

### 第三阶段（验证）
6. 本地 macOS 测试静默输入
7. Windows EXE 打包测试
8. 回归：确保 `test_core.py` 测试通过

## 八、风险与缓解

| 风险 | 缓解 |
|------|------|
| SendInput 在某些游戏反作弊中被检测 | 云游戏是网页视频流，输入事件走浏览器，不会被游戏客户端判定为外挂 |
| 最小化后 Selenium 截图可能空白 | 提前测试；如有问题改用 `set_window_position(-32000, -32000)` 隐藏到屏幕外 |
| DPI 缩放导致坐标偏移 | `driver.set_window_size(1920, 1080)` 固定 CSS 像素，不受系统 DPI 影响 |
| macOS Quartz 权限 | `CGEventPost` 需要辅助功能权限，已在运行 pyautogui 时授权过 |
