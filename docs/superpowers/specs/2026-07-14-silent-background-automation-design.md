# 静默后台自动化方案设计

## 目标

EXE 在 Windows 端运行时，用户可以同时在前台做其他事情——脚本全程不抢占鼠标、不弹窗、不干扰用户操作。

## 核心原理：移出屏幕外（Out of Screen）

脚本在启动 Chrome 后，将窗口尺寸固定为 1920×1080，然后将窗口起始屏幕坐标设置到 **(-32000, -32000)**——显示器可见范围之外的负空间。

**对用户**：Chrome 窗口完全不可见，任务栏无额外图标。

**对系统**：窗口处于"正常展开且激活"状态。Chrome GPU 视频流解码全速运行，`driver.get_screenshot_as_png()` 稳定返回实时游戏画面，绝不黑屏。

### 为什么不用最小化？

最小化后 Windows 可能暂停 Chrome 的页面渲染和 GPU 合成，导致截图空白。移出屏幕外则完全避免了这个问题——对渲染引擎来说窗口始终"可见"。

## 全链路在浏览器内

腾讯先锋是云游戏平台，游戏画面是 Chrome 内的 `<video>` 视频流（不是独立的桌面客户端）。全部 4 个阶段都在 Chrome 内：

```
屏幕可见区域 (1920x1080):
┌──────────────────────────┐
│  用户的应用窗口（前台）    │
│                          │
└──────────────────────────┘

屏幕外 (-32000, -32000):
┌──────────────────────────────┐
│ Chrome @ (-32000, -32000)    │
│  1920×1080                   │
│  ├─ 阶段1-2: gamer.qq.com   │ ← Selenium DOM 操控
│  ├─ 阶段3-4: 云游戏视频流    │ ← 模板匹配 + SendInput 点击
│  └─ 截图: get_screenshot()  │ ← 实时画面，不受遮挡
└──────────────────────────────┘
```

## 改动范围

涉及 5 个文件，1 个新增文件：

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `config.py` | 修改 | 新增窗口偏移常量 |
| `browser.py` | 修改 | 窗口移出屏幕外 + 固定尺寸 |
| `navigator.py` | 重写 | PyAutoGUI 截图/点击 → Selenium 截图 + SendInput |
| `screenshotter.py` | 修改 | PyAutoGUI 截图 → Selenium 截图 |
| `popup_monitor.py` | 修改 | 截图源切换为 Navigator（Selenium） |
| `input_injector.py` | **新增** | Win32 SendInput / macOS CGEvent 静默输入 |

## 一、Chrome 窗口移出屏幕外（browser.py + config.py）

```python
# config.py 新增
WINDOW_HIDE_X = -32000   # Chrome 窗口屏幕 X 偏移（屏幕外）
WINDOW_HIDE_Y = -32000   # Chrome 窗口屏幕 Y 偏移（屏幕外）
WINDOW_WIDTH = 1920      # 窗口宽度（决定截图 CSS 分辨率）
WINDOW_HEIGHT = 1080     # 窗口高度

# browser.py
options.add_argument("--window-size=1920,1080")
options.add_argument("--force-device-scale-factor=1")

# 反后台暂停：确保窗口被遮挡/移出屏幕外后仍然渲染
options.add_argument("--disable-backgrounding-occluded-windows")
options.add_argument("--disable-renderer-backgrounding")

# 移出屏幕外（代替 maximize_window + 全屏）
driver.set_window_position(-32000, -32000)
driver.set_window_size(1920, 1080)  # 固定 CSS 像素分辨率
```

**关键点**：`set_window_position(-32000, -32000)` 后 Chrome 认为窗口仍在"活跃展开"状态，GPU 视频流解码不暂停，截图始终正常。`--disable-backgrounding-occluded-windows` 和 `--disable-renderer-backgrounding` 是双层保险。

## 二、Selenium 页面截图替代 PyAutoGUI 全屏截图

### 2.1 Screenshotter 改造（screenshotter.py）

```python
# 之前
class Screenshotter:
    def take(self, name):
        img = pyautogui.screenshot()  # 全屏，截到其他窗口
        img.save(filepath)

# 之后
class Screenshotter:
    def __init__(self, output_dir, driver):
        self.driver = driver  # 持有 WebDriver 引用

    def take(self, name):
        png_bytes = self.driver.get_screenshot_as_png()
        with open(filepath, "wb") as f:
            f.write(png_bytes)
```

### 2.2 Navigator 改造（navigator.py）

```python
# 之前
def __init__(self, templates_dir, threshold=..., max_retries=...):
    self.templates_dir = resource_path(templates_dir)
    self._detect_scale()
    self._template_cache = {}

def _get_screenshot(self):
    img = pyautogui.screenshot()
    return cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)

# 之后
def __init__(self, templates_dir, driver, threshold=..., max_retries=...):
    self.templates_dir = resource_path(templates_dir)
    self.driver = driver              # 持有 WebDriver
    self._template_cache = {}
    # 不再需要 Retina scale 检测；Selenium 截图是 CSS 像素

def _get_screenshot(self):
    png_bytes = self.driver.get_screenshot_as_png()
    return cv2.imdecode(np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR)
```

### 2.3 坐标映射简化

之前 Navigator 有 `_detect_scale()` → `_physical_to_logical()` → `_click_at()` 的 Retina 转换链。

改为 Selenium 截图后：

| 概念 | 之前（PyAutoGUI） | 之后（Selenium） |
|------|-------------------|-----------------|
| 截图像素 | 物理像素（Retina 2x=2940） | CSS 像素（1920×1080） |
| 点击坐标 | `pyautogui.click(logical_x, logical_y)` | `input_injector.click_at(screen_x, screen_y)` |
| 坐标换算 | 物理/scale → 逻辑→屏幕 | CSS + 窗口偏移 = 屏幕坐标 |
| DPI 处理 | `_detect_scale()` 动态 | 不需要，`force-device-scale-factor=1` |

窗口偏移 = (-32000, -32000)，所以：

```python
def _click_at(self, css_x, css_y):
    """CSS 像素坐标 → 屏幕坐标 → 静默点击。"""
    screen_x = css_x + WINDOW_HIDE_X   # css_x + (-32000)
    screen_y = css_y + WINDOW_HIDE_Y   # css_y + (-32000)
    input_injector.click_at(screen_x, screen_y)
```

## 三、静默输入（新增 input_injector.py）

### 3.1 阶段 1-2（网页操作）

继续用 `driver.execute_script("arguments[0].click()", elem)`——已经在用，无需改动。

### 3.2 阶段 3-4（云游戏视频流内操作）

游戏画面是 `<video>` 视频流，模板匹配的按钮在视频帧内是像素坐标，不是 DOM 元素。需要用 SendInput 向窗口的屏幕位置注入鼠标事件。

```python
# input_injector.py

import platform

SYSTEM = platform.system()

if SYSTEM == "Windows":
    import ctypes
    from ctypes import wintypes

    # Win32 SendInput 结构体
    class MOUSEINPUT(ctypes.Structure):
        _fields_ = [
            ("dx", wintypes.LONG),
            ("dy", wintypes.LONG),
            ("mouseData", wintypes.DWORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [
            ("wVk", wintypes.WORD),
            ("wScan", wintypes.WORD),
            ("dwFlags", wintypes.DWORD),
            ("time", wintypes.DWORD),
            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
        ]

    class INPUT(ctypes.Structure):
        _fields_ = [
            ("type", wintypes.DWORD),
            ("mi", MOUSEINPUT),
            ("ki", KEYBDINPUT),
        ]

    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_ABSOLUTE = 0x8000
    INPUT_MOUSE = 0

    def click_at(x: int, y: int):
        """向指定屏幕坐标注入鼠标点击事件，不移动物理光标。

        SendInput 直接将事件注入系统输入队列，物理鼠标箭头不动。
        """
        # 转换为绝对坐标 (0-65535)
        from ctypes import windll
        screen_w = windll.user32.GetSystemMetrics(0)
        screen_h = windll.user32.GetSystemMetrics(1)
        abs_x = int(x * 65535 / screen_w)
        abs_y = int(y * 65535 / screen_h)

        # 事件序列: 移动 → 按下 → 抬起
        events = []
        for flags in [(MOUSEEVENTF_MOVE | MOUSEEVENTF_ABSOLUTE),
                       (MOUSEEVENTF_LEFTDOWN),
                       (MOUSEEVENTF_LEFTUP)]:
            inp = INPUT()
            inp.type = INPUT_MOUSE
            inp.mi.dx = abs_x
            inp.mi.dy = abs_y
            inp.mi.dwFlags = flags
            events.append(inp)

        windll.user32.SendInput(len(events), 
            ctypes.byref(INPUT(*events)), ctypes.sizeof(INPUT))

elif SYSTEM == "Darwin":
    import Quartz

    def click_at(x: int, y: int):
        """macOS Quartz 事件注入，不移动物理光标。"""
        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseDown,
            (x, y), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

        event = Quartz.CGEventCreateMouseEvent(
            None, Quartz.kCGEventLeftMouseUp,
            (x, y), Quartz.kCGMouseButtonLeft
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)

else:
    import pyautogui
    def click_at(x, y):
        pyautogui.click(x, y)
```

### 3.3 降级策略

```python
# 环境检测 → 自动选择最优输入方案
if platform.system() == "Windows":
    from input_injector import sendinput_click as click_at
elif platform.system() == "Darwin":
    from input_injector import quartz_click as click_at
else:
    import pyautogui
    click_at = lambda x, y: pyautogui.click(x, y)
```

## 四、不需要改动的部分

| 模块 | 原因 |
|------|------|
| `login.py` | web_login 全程 Selenium；game_login 通过 Navigator 间接使用，Navigator 改了就自动适配 |
| `game_launcher.py` | 全程 Selenium，不涉及 PyAutoGUI |
| `gui/app.py` | 通过 Navigator/Screenshotter 间接使用，底层改了自动适配 |
| `client_launcher.py` | macOS 专用，暂不改造 |
| `calibrate_coords.py` | 独立工具，坐标基准不变（CSS 像素） |
| `capture_templates.py` | 独立工具 |
| `test_core.py` | 测试需要适配新接口 |

## 五、实现步骤

### 第一阶段（核心基础设施）
1. `config.py`：新增 `WINDOW_HIDE_X/Y` 常量
2. `browser.py`：移出屏幕外 + 反后台暂停 flag
3. **新增** `input_injector.py`：Win32 SendInput 完整实现

### 第二阶段（截图与导航集成）
4. `navigator.py`：`_get_screenshot()` 改 Selenium；移除 `_detect_scale()` / `_physical_to_logical()`；`_click_at()` 改 `input_injector.click_at()`
5. `screenshotter.py`：`take()` 改 `driver.get_screenshot_as_png()`
6. `popup_monitor.py`：扫码截图源适配

### 第三阶段（连接层）
7. `gui/app.py`：向 Navigator 和 Screenshotter 传入 `driver`

### 第四阶段（验证）
8. 本地 macOS 基础功能测试
9. GitHub Actions 构建 Windows EXE
10. Windows 端端到端测试
11. `test_core.py` 适配

## 六、风险与缓解

| 风险 | 缓解 |
|------|------|
| 移出屏幕外后被某些安全软件拦截 | (-32000, -32000) 是合法屏幕坐标，不触发安全检测 |
| SendInput 被云游戏反作弊检测 | 云游戏是浏览器视频流，输入走浏览器管道，不是游戏客户端直连，不会被判定为外挂 |
| DPI 缩放不一致 | `--force-device-scale-factor=1` 固定 CSS 像素比例 |
| macOS 无负坐标可用 | macOS 也用负坐标移动窗口；或改为设置窗口 Alpha 透明度为 0（透明但活跃） |
