# GUI 登录启动器 实现计划

> **给执行者：** 使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 按任务逐个实现。步骤使用 `- [ ]` checkbox 跟踪。

**目标：** 将终端交互的登录/截图流程改造为 Tkinter GUI 控制面板，支持 QQ/微信扫码登录，全程驻留，可多轮执行。

**架构：** GUI 薄壳 + 业务模块不变。Tkinter 管理页面切换和进度展示，后台线程执行 Selenium/pyautogui 操作，通过 `queue.Queue` 跨线程通信。

**技术栈：** Python 3, Tkinter + ttk, Selenium + webdriver-manager, Pillow, OpenCV, pyautogui

## 全局约束

- 所有资源路径必须使用 `resource_path()` 兼容 PyInstaller `sys._MEIPASS`
- macOS AppleScript 全屏操作需平台检测，Windows 跳过
- 不使用 ChromeDriver 手动路径，统一用 webdriver-manager
- 二维码展示组件必须可复用（后续其他扫码场景）

---

### Task 1: 基础设施 — resource_path + Navigator 路径适配

**文件：**
- 修改: `config.py`
- 修改: `navigator.py`

**接口：**
- 产出: `config.resource_path(relative_path: str) -> str`

- [ ] **Step 1: 在 config.py 中添加 resource_path 函数并移除 QQ_NUMBER**

编辑 `config.py`，在文件末尾（`QQ_NUMBER` 行之后）添加 `resource_path` 函数，并删除 `QQ_NUMBER` 行：

```python
# 删除这一行:
# QQ_NUMBER = "2903937459"  # 在此填写 QQ 号，或运行时被询问

# 在文件末尾添加:
import sys
import os

def resource_path(relative_path: str) -> str:
    """获取资源文件绝对路径，兼容开发环境和 PyInstaller 打包。

    PyInstaller 打包后，资源文件解压到 sys._MEIPASS 临时目录。
    """
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative_path)
```

运行验证：

```bash
python -c "from config import resource_path; print(resource_path('templates'))"
```

- [ ] **Step 2: Navigator 使用 resource_path 解析模板目录**

编辑 `navigator.py`，在 `__init__` 中引入 `resource_path`：

```python
# navigator.py 顶部 import 区域添加:
from config import MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL, resource_path

# __init__ 中修改 templates_dir 赋值:
def __init__(self, templates_dir: str = "templates", ...):
    self.templates_dir = resource_path(templates_dir)
```

`_template_path` 方法保持不变（它已经用 `self.templates_dir` 拼接）。

- [ ] **Step 3: 更新 main.py 中引用 QQ_NUMBER 的地方**

`main.py` 第 28 行 `from config import ... QQ_NUMBER` 移除 `QQ_NUMBER`，第 259 行 `SCREENSHOTS_DIR, QQ_NUMBER` 改为 `SCREENSHOTS_DIR, "default"`（临时，后续 GUI 接管）。

- [ ] **Step 4: 提交**

```bash
git add config.py navigator.py main.py
git commit -m "feat: add resource_path for PyInstaller compatibility, remove hardcoded QQ_NUMBER

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 2: 浏览器模块 — webdriver-manager + 平台兼容

**文件：**
- 修改: `browser.py`

**接口：**
- 产出: `browser.create_browser(width: int, height: int) -> webdriver.Chrome`（签名不变，内部改动）

- [ ] **Step 1: 修改 browser.py — webdriver-manager + 平台检测**

完整重写 `browser.py`：

```python
"""反检测 Chrome 浏览器初始化。

绕过 gamer.qq.com 等网站对 Selenium 自动化特征的检测。
使用 webdriver-manager 自动管理 ChromeDriver 版本。
"""

import platform
import subprocess

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager


# CDP 注入脚本：在页面加载前执行，隐藏自动化特征
PRELOAD_SCRIPT = """
// 1. 隐藏 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// 2. 伪造 plugins —— 真实 Chrome 有 PDF Viewer 等内置插件
Object.defineProperty(navigator, 'plugins', {
    get: () => {
        const plugins = [
            { name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format' },
            { name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: '' },
            { name: 'Native Client', filename: 'internal-nacl-plugin', description: '' },
        ];
        plugins.item = (i) => plugins[i] || null;
        plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
        plugins.refresh = () => {};
        Object.setPrototypeOf(plugins, PluginArray.prototype);
        return plugins;
    }
});

// 3. 伪造 mimeTypes
Object.defineProperty(navigator, 'mimeTypes', {
    get: () => {
        const mimeTypes = [
            { type: 'application/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
            { type: 'text/pdf', suffixes: 'pdf', description: 'Portable Document Format' },
        ];
        mimeTypes.item = (i) => mimeTypes[i] || null;
        mimeTypes.namedItem = (name) => mimeTypes.find(m => m.type === name) || null;
        Object.setPrototypeOf(mimeTypes, MimeTypeArray.prototype);
        return mimeTypes;
    }
});

// 4. 修复 chrome.runtime (正常浏览器 connect 会报错而非不存在)
if (window.chrome && window.chrome.runtime) {
    // 保留但确保行为与正常 Chrome 一致
} else if (window.chrome) {
    window.chrome.runtime = {
        connect: () => ({ onMessage: { addListener: () => {} }, postMessage: () => {}, disconnect: () => {} }),
        onConnect: { addListener: () => {} },
        sendMessage: () => {},
        onMessage: { addListener: () => {} },
        getManifest: () => ({}),
        getURL: (path) => path,
        id: undefined,
    };
}

// 5. 覆盖 permissions API
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
        Promise.resolve({ state: Notification.permission, onchange: null }) :
        originalQuery(parameters)
);
"""


def create_browser(width: int = 1920, height: int = 1080) -> webdriver.Chrome:
    """创建配置了反检测措施的 Chrome 浏览器实例。

    Args:
        width: 浏览器窗口宽度 (CSS 像素)。
        height: 浏览器窗口高度 (CSS 像素)。

    Returns:
        webdriver.Chrome: 配置好的 Chrome 实例。
    """
    options = Options()

    # ---- 基础窗口设置 ----
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--force-device-scale-factor=1")

    # ---- 反检测: 移除自动化标记 ----
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    # ---- 反检测: 隐藏 webdriver 属性 ----
    options.add_argument("--disable-blink-features=AutomationControlled")

    # ---- 其他 ----
    options.add_argument("--no-sandbox")

    # 禁用翻译栏、密码保存等弹窗
    options.add_argument("--disable-features=TranslateUI")
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    # ---- webdriver-manager 自动管理 ChromeDriver ----
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # ---- CDP 注入：页面加载前覆盖检测点 ----
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": PRELOAD_SCRIPT},
    )

    driver.maximize_window()

    # ---- 平台特定全屏 ----
    system = platform.system()
    if system == "Darwin":
        subprocess.run([
            "osascript", "-e",
            'tell application "Google Chrome" to activate',
        ], capture_output=True)
        subprocess.run([
            "osascript", "-e",
            'tell application "System Events" to keystroke "f" using {command down, control down}',
        ], capture_output=True)
    elif system == "Windows":
        # Windows: maximize_window 已足够，如需全屏可发送 F11
        pass

    return driver
```

运行验证：

```bash
python -c "from browser import create_browser; print('browser module OK')"
```

- [ ] **Step 2: 提交**

```bash
git add browser.py
git commit -m "feat: use webdriver-manager for ChromeDriver, add platform detection

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 3: 二维码展示组件 `gui/widgets/qr_display.py`

**文件：**
- 创建: `gui/__init__.py`
- 创建: `gui/widgets/__init__.py`
- 创建: `gui/widgets/qr_display.py`

**接口：**
- 产出: `QRDisplay(ttk.Frame)` — `show_qr(image, title)`, `show_qr_from_file(path, title)`, `update_status(text, color)`, `clear()`

- [ ] **Step 1: 创建 gui 包和 widgets 包**

```bash
mkdir -p gui/widgets
touch gui/__init__.py
touch gui/widgets/__init__.py
```

- [ ] **Step 2: 实现 QRDisplay 组件**

创建 `gui/widgets/qr_display.py`：

```python
"""可复用的二维码展示组件。

接受 PIL Image，等比缩放后展示在 Tkinter Frame 中，
下方显示标题和状态文字。
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class QRDisplay(ttk.Frame):
    """二维码展示区域，包含标题、图片、状态文字。

    使用方式:
        qr = QRDisplay(parent)
        qr.pack(fill="both", expand=True)
        qr.show_qr(pil_image, "请扫描二维码")
        qr.update_status("⏳ 等待扫码中...", "gray")
        qr.update_status("✅ 扫码成功", "green")
    """

    def __init__(self, parent, qr_size: int = 280):
        """
        Args:
            parent: 父级 Tkinter 容器。
            qr_size: 二维码展示的最大边长（像素），等比缩放。
        """
        super().__init__(parent)
        self.qr_size = qr_size

        # 标题标签
        self._title_label = ttk.Label(
            self, text="", font=("", 13, "bold"), anchor="center"
        )
        self._title_label.pack(pady=(10, 5))

        # 二维码图片标签
        self._image_label = ttk.Label(self)
        self._image_label.pack(pady=10)

        # 状态文字
        self._status_label = ttk.Label(
            self, text="", font=("", 11), anchor="center"
        )
        self._status_label.pack(pady=(0, 10))

        self._tk_image = None  # 持有引用防止被 GC

    def show_qr(self, image: Image.Image, title: str) -> None:
        """展示二维码图片。

        Args:
            image: PIL Image 对象。
            title: 标题文字，如 "第 1/2 步：请扫描腾讯先锋登录二维码"。
        """
        self._title_label.config(text=title)

        # 等比缩放
        w, h = image.size
        scale = min(self.qr_size / w, self.qr_size / h, 1.0)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = image.resize((new_w, new_h), Image.LANCZOS)

        self._tk_image = ImageTk.PhotoImage(resized)
        self._image_label.config(image=self._tk_image)

    def show_qr_from_file(self, path: str, title: str) -> None:
        """从文件路径加载并展示二维码。

        Args:
            path: 图片文件路径。
            title: 标题文字。
        """
        image = Image.open(path)
        self.show_qr(image, title)

    def update_status(self, text: str, color: str = "black") -> None:
        """更新底部状态文字。

        Args:
            text: 状态文字，如 "⏳ 等待扫码中..."。
            color: 文字颜色，如 "gray"、"green"、"red"。
        """
        self._status_label.config(text=text, foreground=color)
        self.update_idletasks()

    def clear(self) -> None:
        """清空展示内容，准备下一次使用。"""
        self._title_label.config(text="")
        self._image_label.config(image="")
        self._tk_image = None
        self._status_label.config(text="")
```

运行验证：

```bash
python -c "from gui.widgets.qr_display import QRDisplay; print('QRDisplay OK')"
```

- [ ] **Step 3: 提交**

```bash
git add gui/__init__.py gui/widgets/__init__.py gui/widgets/qr_display.py
git commit -m "feat: add reusable QR code display widget

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 4: 日志进度组件 `gui/widgets/log_view.py`

**文件：**
- 创建: `gui/widgets/log_view.py`

**接口：**
- 产出: `LogView(ttk.Frame)` — `add_log(text)`, `update_progress(current, total)`, `reset_progress()`, `clear()`

- [ ] **Step 1: 实现 LogView 组件**

创建 `gui/widgets/log_view.py`：

```python
"""实时日志和进度展示组件。

包含可滚动的日志区域和进度条，用于展示执行过程中的
每一步状态和截图进度。
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime


class LogView(ttk.Frame):
    """日志 + 进度条组合组件。

    使用方式:
        log_view = LogView(parent)
        log_view.pack(fill="both", expand=True)
        log_view.add_log("✅ 腾讯先锋登录成功")
        log_view.update_progress(3, 12)
    """

    def __init__(self, parent):
        super().__init__(parent)

        # ---- 日志区域 ----
        log_frame = ttk.LabelFrame(self, text="执行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            font=("", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            relief="flat",
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self._log_text.yview
        )
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 配置 tag 颜色
        self._log_text.tag_configure("success", foreground="#4ec94e")
        self._log_text.tag_configure("error", foreground="#f44747")
        self._log_text.tag_configure("info", foreground="#d4d4d4")
        self._log_text.tag_configure("warn", foreground="#cca700")

        # ---- 进度区域 ----
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", padx=10, pady=(0, 5))

        self._progress_label = ttk.Label(
            progress_frame, text="截图进度: 0/0", font=("", 10)
        )
        self._progress_label.pack(anchor="w")

        self._progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self._progress_bar.pack(fill="x", pady=(2, 5))

    def add_log(self, text: str, level: str = "info") -> None:
        """添加一行日志。

        Args:
            text: 日志内容。
            level: 'info' | 'success' | 'error' | 'warn'
        """
        self._log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"
        self._log_text.insert("end", line, level)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
        self.update_idletasks()

    def update_progress(self, current: int, total: int) -> None:
        """更新截图进度。

        Args:
            current: 当前已完成数量。
            total: 总数。
        """
        self._progress_label.config(text=f"截图进度: {current}/{total}")
        if total > 0:
            self._progress_bar["maximum"] = total
            self._progress_bar["value"] = current
        self.update_idletasks()

    def reset_progress(self) -> None:
        """重置进度为零。"""
        self._progress_bar["value"] = 0
        self._progress_label.config(text="截图进度: 0/0")
        self.update_idletasks()

    def clear(self) -> None:
        """清空日志和进度。"""
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self.reset_progress()
```

运行验证：

```bash
python -c "from gui.widgets.log_view import LogView; print('LogView OK')"
```

- [ ] **Step 2: 提交**

```bash
git add gui/widgets/log_view.py
git commit -m "feat: add log and progress view widget

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 5: 登录模块改造 — callback 模式的 web_login 和 game_login

**文件：**
- 修改: `login.py`

**接口：**
- 产出:
  - `web_login(driver: WebDriver, login_type: str, on_qr: Callable, on_status: Callable, timeout: int = 300) -> bool`
  - `game_login(nav: Navigator, on_qr: Callable, on_status: Callable, timeout: int = 300) -> bool`

- [ ] **Step 1: 重写 login.py**

```python
"""QQ / 微信扫码登录模块。

支持两种登录场景：
    1. web_login: 在 gamer.qq.com 网页中完成腾讯先锋平台扫码登录
    2. game_login: 在云游戏画面中检测游戏内登录二维码

两个函数都采用回调模式，通过 on_qr 和 on_status 将
二维码图片和状态更新推送给 GUI 层。
"""

import time
from io import BytesIO
from typing import Callable

from PIL import Image
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CLOUD_GAMING_URL, PAGE_LOAD_WAIT
from logger import get_logger

log = get_logger()


# ---------------------------------------------------------------------------
# 网页登录（腾讯先锋 gamer.qq.com）
# ---------------------------------------------------------------------------

def web_login(
    driver: WebDriver,
    login_type: str,
    on_qr: Callable[[Image.Image], None],
    on_status: Callable[[str], None],
    timeout: int = 300,
) -> bool:
    """在 gamer.qq.com 完成 QQ / 微信扫码登录。

    流程：
        1. 打开 gamer.qq.com → 点击登录按钮
        2. 根据 login_type 点击 QQ 或微信图标
        3. 切换到 OAuth iframe
        4. 截取二维码 → on_qr(image)
        5. 轮询检测登录成功（iframe 消失或页面跳转）
        6. 切回主页面 → 返回 True

    Args:
        driver: Selenium WebDriver 实例。
        login_type: 'qq' 或 'wechat'。
        on_qr: 截取到二维码时的回调，传入 PIL Image。
        on_status: 状态更新回调，传入文字描述。
        timeout: 扫码等待超时（秒），默认 5 分钟。

    Returns:
        bool: 登录成功返回 True，失败返回 False。
    """
    on_status(f"开始{'QQ' if login_type == 'qq' else '微信'}扫码登录...")

    # ---- 1. 打开 gamer.qq.com ----
    driver.get(CLOUD_GAMING_URL)
    time.sleep(PAGE_LOAD_WAIT * 2)

    # ---- 2. 点击登录按钮 ----
    try:
        login_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "user_login"))
        )
        login_btn.click()
        on_status("已打开登录弹窗")
        time.sleep(3)
    except Exception as e:
        on_status(f"找不到登录按钮: {e}")
        return False

    # ---- 3. 根据 login_type 点击对应图标 ----
    try:
        if login_type == "qq":
            selector = "img.qq-login"
        else:
            selector = "img.wx-login"

        icon = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
        )
        icon.click()
        on_status(f"已选择 {'QQ' if login_type == 'qq' else '微信'} 登录")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        on_status(f"找不到 {'QQ' if login_type == 'qq' else '微信'} 登录选项: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ---- 4. 切换到 iframe 并截取二维码 ----
    try:
        # 获取所有 iframe
        iframes = driver.find_elements(By.TAG_NAME, "iframe")
        if not iframes:
            on_status("未找到登录 iframe")
            return False

        outer_iframe = iframes[0]
        driver.switch_to.frame(outer_iframe)
        time.sleep(2)

        # 尝试切换到内层 ptlogin_iframe (QQ登录)
        try:
            ptlogin_iframe = driver.find_element(By.ID, "ptlogin_iframe")
            driver.switch_to.frame(ptlogin_iframe)
            time.sleep(2)
        except Exception:
            # 微信登录可能没有 ptlogin_iframe
            pass

        on_status("正在截取登录二维码...")
        time.sleep(2)

        # 截取整个 iframe 内容（包含二维码）
        body = driver.find_element(By.TAG_NAME, "body")
        screenshot_png = body.screenshot_as_png
        qr_image = Image.open(BytesIO(screenshot_png))

        # 尝试定位二维码图片元素以获得更精确的截图
        for qr_selector in [
            "img.qr-img", "img[class*='qrcode']", "img[class*='qr']",
            "#qrlogin_img", "img[src*='qrcode']", "img[src*='qr']",
            "canvas", "img",
        ]:
            try:
                qr_elem = driver.find_element(By.CSS_SELECTOR, qr_selector)
                if qr_elem.is_displayed() and qr_elem.size["width"] > 100:
                    screenshot_png = qr_elem.screenshot_as_png
                    qr_image = Image.open(BytesIO(screenshot_png))
                    break
            except Exception:
                continue

        on_qr(qr_image)
        on_status("请使用手机扫描二维码登录...")

    except Exception as e:
        on_status(f"截取二维码失败: {e}")
        driver.save_screenshot("debug_qr.png")
        return False

    # ---- 5. 轮询等待登录成功 ----
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 切回顶层检测页面变化
            driver.switch_to.default_content()

            # 检测是否已登录：查找用户头像或昵称元素
            user_elements = driver.find_elements(By.CSS_SELECTOR, ".user-info, .user-name, .avatar, img[class*='avatar']")
            for elem in user_elements:
                if elem.is_displayed():
                    on_status("✅ 腾讯先锋登录成功")
                    time.sleep(PAGE_LOAD_WAIT)
                    return True

            # 检测登录弹窗是否已关闭
            try:
                login_popup = driver.find_element(By.ID, "user_login")
                if not login_popup.is_displayed():
                    on_status("✅ 腾讯先锋登录成功")
                    time.sleep(PAGE_LOAD_WAIT)
                    return True
            except Exception:
                on_status("✅ 腾讯先锋登录成功")
                time.sleep(PAGE_LOAD_WAIT)
                return True

        except Exception:
            pass

        time.sleep(2)

    on_status("⚠️ 扫码超时")
    return False


# ---------------------------------------------------------------------------
# 游戏内登录（云游戏画面）
# ---------------------------------------------------------------------------

def game_login(
    nav,  # Navigator 实例
    on_qr: Callable[[Image.Image], None],
    on_status: Callable[[str], None],
    timeout: int = 300,
) -> bool:
    """在云游戏画面中检测登录二维码并等待用户扫码。

    游戏启动后，画面中会出现游戏内登录二维码。
    此函数截屏 → 检测二维码 → 展示给用户 → 等待扫码完成。

    Args:
        nav: Navigator 实例。
        on_qr: 截取到二维码时的回调。
        on_status: 状态更新回调。
        timeout: 扫码等待超时（秒）。

    Returns:
        bool: 登录成功返回 True。
    """
    import cv2
    import numpy as np
    import pyautogui

    on_status("等待游戏加载并检测登录二维码...")
    time.sleep(8)  # 等游戏画面加载

    # ---- 使用 OpenCV QRCodeDetector 检测二维码 ----
    qr_detector = cv2.QRCodeDetector()

    start = time.time()
    qr_sent = False

    while time.time() - start < timeout:
        # 截屏
        screenshot = pyautogui.screenshot()
        frame = np.array(screenshot)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        if not qr_sent:
            # 尝试检测二维码
            try:
                data, bbox, _ = qr_detector.detectAndDecode(frame_bgr)
                if bbox is not None and len(bbox) > 0:
                    # 裁剪二维码区域
                    pts = bbox.astype(int).reshape(4, 2)
                    x_min = max(0, pts[:, 0].min() - 20)
                    y_min = max(0, pts[:, 1].min() - 20)
                    x_max = min(frame_bgr.shape[1], pts[:, 0].max() + 20)
                    y_max = min(frame_bgr.shape[0], pts[:, 1].max() + 20)

                    qr_crop = screenshot.crop((x_min, y_min, x_max, y_max))
                    on_qr(qr_crop)
                    qr_sent = True
                    on_status("请使用手机扫描游戏登录二维码...")
            except Exception:
                pass

        # 检测登录成功：avatar.png 出现在屏幕上
        if nav.wait_for_template("avatar.png", timeout=2):
            on_status("✅ 游戏登录成功")
            time.sleep(3)
            return True

        # 检测 enter_game.png 可能出现在登录完成后
        if nav.wait_for_template("enter_game.png", timeout=2):
            if nav.find_and_click("enter_game.png", timeout=3):
                on_status("✅ 游戏登录成功，已进入游戏")
                time.sleep(3)
                return True

        time.sleep(2)

    on_status("⚠️ 游戏登录扫码超时")
    return False
```

运行验证：

```bash
python -c "from login import web_login, game_login; print('login module OK')"
```

- [ ] **Step 2: 提交**

```bash
git add login.py
git commit -m "feat: rewrite login with callback-based QR scan for QQ/WeChat and in-game

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 6: GUI 主应用 `gui/app.py`

**文件：**
- 创建: `gui/app.py`

**接口：**
- 产出: `App(tk.Tk)` — 主窗口类，暴露 `run()` 方法启动事件循环

- [ ] **Step 1: 实现 gui/app.py**

创建 `gui/app.py`：

```python
"""Tkinter GUI 主应用。

管理页面切换、后台任务调度、跨线程通信。
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import sys
import time

from gui.widgets.qr_display import QRDisplay
from gui.widgets.log_view import LogView


class App(tk.Tk):
    """GUI 主窗口，4 个页面：待命、扫码、进度、完成。"""

    def __init__(self):
        super().__init__()

        self.title("王者荣耀云游戏自动截图")
        self.geometry("480x620")
        self.resizable(True, True)
        self.minsize(400, 500)

        # 禁止直接关闭窗口时残留进程
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- 跨线程通信 ----
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None

        # ---- 状态 ----
        self._platform_logged_in = False  # 腾讯先锋是否已登录

        # ---- 构建 UI ----
        self._build_ui()

        # ---- 启动队列轮询 ----
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """构建所有页面框架。"""

        # ---- 顶部标题栏 ----
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(
            header, text="王者荣耀云游戏自动截图",
            font=("", 16, "bold")
        ).pack(side="left")

        # ---- 页面容器 ----
        self._page_container = ttk.Frame(self)
        self._page_container.pack(fill="both", expand=True, padx=10, pady=5)

        # ---- 页面 1: 待命页 ----
        self._page_idle = ttk.Frame(self._page_container)
        ttk.Label(
            self._page_idle, text="就绪",
            font=("", 14, "bold")
        ).pack(pady=(40, 5))
        ttk.Label(
            self._page_idle,
            text="选择登录方式并启动",
            font=("", 11)
        ).pack(pady=(0, 15))

        # 登录方式选择
        login_frame = ttk.LabelFrame(self._page_idle, text="登录方式", padding=10)
        login_frame.pack(pady=10)
        self._login_type = tk.StringVar(value="qq")
        ttk.Radiobutton(
            login_frame, text="QQ 扫码登录", variable=self._login_type, value="qq"
        ).pack(anchor="w", pady=3)
        ttk.Radiobutton(
            login_frame, text="微信扫码登录", variable=self._login_type, value="wechat"
        ).pack(anchor="w", pady=3)

        ttk.Button(
            self._page_idle, text="启 动",
            command=self._on_start, width=20
        ).pack(pady=15)

        # ---- 页面 2: 扫码页 ----
        self._page_qr = ttk.Frame(self._page_container)
        self._qr_display = QRDisplay(self._page_qr, qr_size=260)
        self._qr_display.pack(fill="both", expand=True, pady=20)

        # ---- 页面 3: 进度页 ----
        self._page_progress = ttk.Frame(self._page_container)
        self._log_view = LogView(self._page_progress)
        self._log_view.pack(fill="both", expand=True)

        # ---- 页面 4: 完成页 ----
        self._page_done = ttk.Frame(self._page_container)
        self._done_summary = ttk.Label(
            self._page_done, text="", font=("", 12)
        )
        self._done_summary.pack(pady=(40, 10))
        btn_frame = ttk.Frame(self._page_done)
        btn_frame.pack(pady=10)
        ttk.Button(
            btn_frame, text="再跑一轮",
            command=self._on_rerun, width=15
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="退 出",
            command=self._on_close, width=15
        ).pack(side="left", padx=5)

        # ---- 底部退出按钮 ----
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._exit_btn = ttk.Button(
            bottom, text="退 出", command=self._on_close
        )
        self._exit_btn.pack(side="right")

        # 默认显示待命页
        self._show_page("idle")

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------

    def _show_page(self, name: str):
        """显示指定页面，隐藏其余。"""
        for page in [self._page_idle, self._page_qr,
                     self._page_progress, self._page_done]:
            page.pack_forget()

        mapping = {
            "idle": self._page_idle,
            "qr": self._page_qr,
            "progress": self._page_progress,
            "done": self._page_done,
        }
        page = mapping.get(name)
        if page:
            page.pack(fill="both", expand=True)

        # 扫码页的特殊处理：底部退出按钮在扫码时可用
        if name == "qr":
            self._exit_btn.config(state="normal")

    # ------------------------------------------------------------------
    # 按钮事件
    # ------------------------------------------------------------------

    def _on_start(self):
        """点击启动按钮。"""
        self._stop_event.clear()
        self._log_view.clear()
        self._show_page("progress")
        self._log_view.add_log("启动任务...", "info")
        self._exit_btn.config(state="normal")

        self._worker_thread = threading.Thread(
            target=self._run_workflow, daemon=True
        )
        self._worker_thread.start()

    def _on_rerun(self):
        """完成页点击「再跑一轮」。"""
        self._on_start()

    def _on_close(self):
        """关闭窗口。"""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)
        self.destroy()
        sys.exit(0)

    # ------------------------------------------------------------------
    # 队列轮询
    # ------------------------------------------------------------------

    def _poll_queue(self):
        """定时从队列取出消息并更新 UI。"""
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_message(self, msg: dict):
        """处理来自后台线程的消息。"""
        msg_type = msg.get("type")

        if msg_type == "log":
            self._log_view.add_log(msg["text"], msg.get("level", "info"))

        elif msg_type == "progress":
            self._log_view.update_progress(msg["current"], msg["total"])

        elif msg_type == "qr":
            self._show_page("qr")
            self._qr_display.show_qr(msg["image"], msg["title"])
            self._qr_display.update_status(
                msg.get("status", "⏳ 等待扫码中..."), "gray"
            )

        elif msg_type == "qr_status":
            self._qr_display.update_status(
                msg["text"], msg.get("color", "black")
            )

        elif msg_type == "page":
            self._show_page(msg["name"])

        elif msg_type == "done":
            self._show_page("done")
            self._done_summary.config(text=msg["text"])

    # ------------------------------------------------------------------
    # 后台工作流
    # ------------------------------------------------------------------

    def _send(self, msg: dict):
        """线程安全地向 GUI 队列发送消息。"""
        self._queue.put(msg)

    def _run_workflow(self):
        """后台线程：执行完整的登录 → 截图工作流。"""
        from browser import create_browser
        from config import BROWSER_WIDTH, BROWSER_HEIGHT, TEMPLATES_DIR, SCREENSHOTS_DIR, resource_path
        from login import web_login, game_login
        from game_launcher import launch_game
        from navigator import Navigator
        from screenshotter import Screenshotter
        from popup_monitor import PopupMonitor
        import pyautogui
        import os

        driver = None
        nav = None

        try:
            # ====== 阶段 1: 腾讯先锋登录（仅一次） ======
            if not self._platform_logged_in:
                if self._stop_event.is_set():
                    return

                self._send({"type": "log", "text": "正在打开浏览器..."})

                driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)

                login_type = self._login_type.get()

                def on_qr(image):
                    self._send({
                        "type": "qr",
                        "image": image,
                        "title": f"第 1/2 步：请扫描腾讯先锋{'QQ' if login_type == 'qq' else '微信'}登录二维码",
                        "status": "⏳ 等待扫码中...",
                    })

                def on_status(text):
                    if "成功" in text:
                        self._send({"type": "qr_status", "text": text, "color": "green"})
                    elif "失败" in text or "超时" in text or "⚠" in text:
                        self._send({"type": "qr_status", "text": text, "color": "red"})
                    else:
                        self._send({"type": "qr_status", "text": text})
                    self._send({"type": "log", "text": text,
                                "level": "success" if "成功" in text else ("error" if "失败" in text or "超时" in text else "info")})

                self._send({"type": "log", "text": f"开始腾讯先锋{'QQ' if login_type == 'qq' else '微信'}扫码登录..."})

                if not web_login(driver, login_type, on_qr, on_status):
                    self._send({"type": "log", "text": "❌ 腾讯先锋登录失败", "level": "error"})
                    self._send({"type": "done", "text": "❌ 腾讯先锋登录失败"})
                    return

                self._platform_logged_in = True
                self._send({"type": "page", "name": "progress"})
                self._send({"type": "log", "text": "✅ 腾讯先锋登录成功", "level": "success"})

                # ====== 阶段 2: 搜索游戏并启动 ======
                if self._stop_event.is_set():
                    return

                self._send({"type": "log", "text": "正在搜索王者荣耀..."})
                if not launch_game(driver):
                    self._send({"type": "log", "text": "❌ 搜索/启动游戏失败", "level": "error"})
                    self._send({"type": "done", "text": "❌ 启动游戏失败"})
                    return

                self._send({"type": "log", "text": "✅ 已点击秒玩，等待游戏启动...", "level": "success"})

            # ====== 阶段 3: 游戏内登录 + 截图 ======
            if self._stop_event.is_set():
                return

            self._send({"type": "log", "text": "等待游戏窗口..."})

            nav = Navigator(templates_dir=TEMPLATES_DIR)

            def on_game_qr(image):
                self._send({
                    "type": "qr",
                    "image": image,
                    "title": "第 2/2 步：请扫描游戏登录二维码",
                    "status": "⏳ 等待扫码中...",
                })

            def on_game_status(text):
                if "成功" in text:
                    self._send({"type": "qr_status", "text": text, "color": "green"})
                else:
                    self._send({"type": "qr_status", "text": text})
                self._send({"type": "log", "text": text,
                            "level": "success" if "成功" in text else "info"})

            if not game_login(nav, on_game_qr, on_game_status):
                self._send({"type": "log", "text": "❌ 游戏登录失败", "level": "error"})
                self._send({"type": "done", "text": "❌ 游戏登录失败"})
                return

            self._send({"type": "page", "name": "progress"})
            self._send({"type": "log", "text": "✅ 游戏登录成功", "level": "success"})

            # ====== 阶段 4: 截图（复用 main.py 逻辑） ======
            avatar_bounds = None
            nobility_bounds = None
            enter_game_bounds = None

            shot = Screenshotter(output_dir=os.path.join(SCREENSHOTS_DIR, "screenshots"))

            screen_w, screen_h = pyautogui.size()
            avatar_bounds = (0, 0, int(screen_w * nav._scale * 0.4), int(screen_h * nav._scale * 0.5))
            nobility_bounds = (0, 0, int(screen_w * nav._scale), int(screen_h * nav._scale * 0.5))
            enter_game_bounds = (0, int(screen_h * nav._scale * 0.5), int(screen_w * nav._scale), int(screen_h * nav._scale * 0.5))

            # 截图任务（和 main.py 一致）
            screenshot_tasks = [
                ("主页", [
                    ("avatar.png", "点击左上角头像", avatar_bounds),
                    ("tab_home.png", "点击主页标签"),
                ], 0),
                ("英雄", [
                    ("tab_hero.png", "点击英雄标签"),
                ], 0),
                ("万象图鉴首页", [
                    ("tab_illustrated.png", "点击图鉴标签"),
                    ("universal_illustrated.png", "点击万象图鉴"),
                ], 0),
                ("万象图鉴-灵宝", [
                    ("lingbao.png", "点击灵宝"),
                ], 1),
                ("皮肤图鉴", [
                    ("skin_illustrated.png", ""),
                ], 1),
                ("积分夺宝", [
                    ("shop_icon.png", "点击商城"),
                    ("lottery_tab.png", "点击夺宝"),
                    ("points_lottery.png", "点击积分夺宝"),
                ], 2),
                ("天幕", [
                    ("customize_icon.png", "点击定制"),
                    ("skin_customize.png", "点击皮肤定制"),
                    ("my_tab.png", "点击我的"),
                    ("sky_curtain.png", "点击天幕"),
                ], 1),
                ("小兵", [
                    ("minion.png", "点击小兵"),
                ], 1),
                ("个性戳戳", [
                    ("customize_icon.png", "点击定制"),
                    ("personal_customize.png", "点击个性定制"),
                    ("poke.png", "点击个性戳戳"),
                ], 1),
                ("贵族", [
                    ("nobility_icon.png", "点击贵族图标", nobility_bounds),
                ], 1),
            ]

            total = len(screenshot_tasks)
            success = 0

            for idx, (name, clicks, back_count) in enumerate(screenshot_tasks, 1):
                if self._stop_event.is_set():
                    return

                self._send({"type": "log", "text": f"[{idx}/{total}] {name}"})
                self._send({"type": "progress", "current": idx - 1, "total": total})

                all_ok = True
                for item in clicks:
                    if len(item) == 3:
                        template, desc, bounds = item
                    else:
                        template, desc = item
                        bounds = None

                    if not nav.find_and_click(template, bounds=bounds):
                        self._send({"type": "log", "text": f"  ⚠ 找不到 {template}，跳过 {name}", "level": "warn"})
                        all_ok = False
                        break

                if all_ok:
                    time.sleep(3)  # PAGE_LOAD_WAIT
                    shot.take(name)
                    success += 1
                    self._send({"type": "log", "text": f"  已截图: {name}", "level": "success"})

                    for _ in range(back_count):
                        nav.find_and_click("back_arrow.png", timeout=3)
                        time.sleep(3)
                else:
                    self._send({"type": "log", "text": f"  ❌ 截图失败: {name}", "level": "error"})

            self._send({"type": "progress", "current": total, "total": total})
            self._send({"type": "log", "text": f"完成: {success}/{total} 张截图成功", "level": "success"})

            # ====== 退出游戏登录 ======
            self._send({"type": "log", "text": "正在退出游戏登录...", "level": "info"})
            # 返回主界面 → 设置 → 退出登录
            for _ in range(3):
                nav.find_and_click("back_arrow.png", timeout=3)
                time.sleep(2)
            self._send({"type": "log", "text": "已退出游戏登录", "level": "info"})

            self._send({
                "type": "done",
                "text": f"✅ 本轮完成: {success}/{total} 张截图\n已退出游戏登录"
            })

        except Exception as e:
            import traceback
            self._send({"type": "log", "text": f"异常: {e}", "level": "error"})
            self._send({"type": "done", "text": f"❌ 运行异常: {e}"})
            traceback.print_exc()

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def run(self):
        """启动 GUI 主循环。"""
        self.mainloop()
```

运行验证：

```bash
python -c "from gui.app import App; print('App module OK')"
```

- [ ] **Step 2: 提交**

```bash
git add gui/app.py
git commit -m "feat: add Tkinter GUI main app with page navigation and background workflow

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 7: 更新入口 `main.py`

**文件：**
- 修改: `main.py`

**接口：**
- 消费: `gui.app.App`

- [ ] **Step 1: 将 main.py 改为 GUI 入口**

```python
#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— GUI 入口。

启动 Tkinter 控制面板，提供 QQ/微信扫码登录、
游戏启动、自动截图等功能。

使用方法:
    python main.py
"""

import sys

if __name__ == "__main__":
    from gui.app import App
    app = App()
    app.run()
```

运行验证（仅检查启动无报错，手动关闭窗口）：

```bash
python main.py
```

预期：GUI 窗口弹出，显示"就绪"页面和启动按钮，关闭按钮可退出。

- [ ] **Step 2: 提交**

```bash
git add main.py
git commit -m "feat: replace main.py with GUI entry point

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 8: 更新依赖 `requirements.txt`

**文件：**
- 修改: `requirements.txt`

- [ ] **Step 1: 添加新依赖**

读取当前 `requirements.txt`，在末尾追加 `webdriver-manager`：

```bash
echo "webdriver-manager>=4.0" >> requirements.txt
```

- [ ] **Step 2: 安装依赖**

```bash
pip install webdriver-manager
```

- [ ] **Step 3: 验证依赖完整**

```bash
python -c "
import selenium
import cv2
import numpy
import pyautogui
import PIL
import webdriver_manager
from tkinter import ttk
print('所有依赖可用')
"
```

- [ ] **Step 4: 提交**

```bash
git add requirements.txt
git commit -m "chore: add webdriver-manager to requirements

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### Task 9: 集成测试 — 端到端验证

**文件：**
- 无新增，运行完整流程验证

- [ ] **Step 1: 模块导入测试**

```bash
python -c "
from gui.widgets.qr_display import QRDisplay
from gui.widgets.log_view import LogView
from gui.app import App
from login import web_login, game_login
from browser import create_browser
from config import resource_path
print('全部模块导入成功')
"
```

- [ ] **Step 2: GUI 窗口启动测试**

```bash
# 手动测试：启动 GUI，检查各页面切换
python main.py
# 验证：窗口弹出 → 显示待命页 → 关闭窗口正常退出
```

- [ ] **Step 3: 完整流程测试（需要实际 Chrome 和网络）**

```bash
python main.py
# 1. 点击启动 → 应显示浏览器 → 截取二维码 → GUI 显示二维码
# 2. 用手机扫码 → 应自动检测登录成功
# 3. 等待游戏搜索 → 秒玩 → 游戏窗口出现 → 游戏二维码
# 4. 游戏扫码 → 截图流程开始
# 5. 完成页显示结果 → 点击再跑一轮 → 重复步骤 3-4
# 6. 点击退出 → 正常退出
```

- [ ] **Step 4: 提交最终状态**

```bash
git add -A
git commit -m "test: verify end-to-end GUI login and screenshot flow

Co-Authored-By: Claude <noreply@anthropic.com>"
```
