# 王者荣耀云游戏自动截图 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Python 脚本，通过 Selenium 自动登录腾讯先锋云游戏中的王者荣耀，并用 OpenCV 模板匹配导航至指定页面截图。

**Architecture:** Selenium 控制 Chrome 完成网页登录和游戏启动；OpenCV 对云游戏画面进行模板匹配定位按钮并模拟点击；截图按页面名称保存至 `screenshots/` 目录。

**Tech Stack:** Python 3.10+, Selenium 4.x, OpenCV 4.x, Pillow, NumPy

## Global Constraints

- macOS (Darwin 24.x), 屏幕 2560×1664 Retina
- 浏览器：Chrome + ChromeDriver
- QQ 密码通过 `getpass` 运行时输入，不写入文件
- 截图按页面名称保存：`screenshots/{名称}.png`
- 模板匹配阈值 ≥ 0.8，每个按钮最多重试 3 次
- 关键步骤（登录、游戏启动）失败则终止；截图失败则记录并继续

---

### Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `.gitignore`
- Create: `templates/.gitkeep`
- Create: `screenshots/.gitkeep`

- [ ] **Step 1: 创建 `requirements.txt`**

```txt
selenium>=4.15
opencv-python>=4.8
Pillow>=10.0
numpy>=1.24
```

- [ ] **Step 2: 创建 `.gitignore`**

```gitignore
# 敏感配置
config.py

# 截图输出
screenshots/

# Python
__pycache__/
*.pyc

# 虚拟环境
venv/
.venv/

# IDE
.vscode/
.idea/
```

- [ ] **Step 3: 创建目录和占位文件**

```bash
mkdir -p templates screenshots
touch templates/.gitkeep screenshots/.gitkeep
```

- [ ] **Step 4: 安装依赖**

```bash
pip install -r requirements.txt
```

- [ ] **Step 5: Commit**

```bash
git add requirements.txt .gitignore templates/.gitkeep screenshots/.gitkeep
git commit -m "chore: initialize project structure and dependencies"
```

---

### Task 2: config.py 配置模块

**Files:**
- Create: `config.py`

**Produces:**
- 模块 `config`，所有其他任务都通过 `import config` 或 `from config import ...` 使用

- [ ] **Step 1: 创建 `config.py`**

```python
"""全局配置常量。"""

# ---------------------------------------------------------------------------
# 腾讯先锋云游戏
# ---------------------------------------------------------------------------
CLOUD_GAMING_URL = "https://start.qq.com/"

# ---------------------------------------------------------------------------
# 浏览器窗口 (CSS 像素)
# ---------------------------------------------------------------------------
BROWSER_WIDTH = 1920
BROWSER_HEIGHT = 1080

# ---------------------------------------------------------------------------
# 等待时间 (秒)
# ---------------------------------------------------------------------------
PAGE_LOAD_WAIT = 3          # 页面加载后等待
CLICK_INTERVAL = 1.5        # 点击后等待
TEMPLATE_MATCH_TIMEOUT = 10 # 模板匹配总超时
GAME_LAUNCH_WAIT = 30       # 游戏启动后等待

# ---------------------------------------------------------------------------
# 模板匹配
# ---------------------------------------------------------------------------
MATCH_THRESHOLD = 0.8       # cv2 匹配置信度阈值
MAX_RETRIES = 3              # 每个按钮最大重试次数
RETRY_INTERVAL = 2           # 重试间隔 (秒)

# ---------------------------------------------------------------------------
# 目录路径 (相对于项目根目录)
# ---------------------------------------------------------------------------
TEMPLATES_DIR = "templates"
SCREENSHOTS_DIR = "screenshots"

# ---------------------------------------------------------------------------
# QQ 账号 (密码不存储，运行时通过 getpass 输入)
# ---------------------------------------------------------------------------
QQ_NUMBER = ""  # 在此填写 QQ 号，或运行时被询问
```

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add config module"
```

---

### Task 3: screenshotter.py 截图模块

**Files:**
- Create: `screenshotter.py`

**Interfaces:**
- Produces: `class Screenshotter`
  - `__init__(self, driver: WebDriver, output_dir: str = "screenshots")`
  - `take(self, name: str) -> str` — 截取当前画面，保存为 `{output_dir}/{name}.png`，返回文件路径

- [ ] **Step 1: 创建 `screenshotter.py`**

```python
"""截图捕获与保存模块。"""

import os
from selenium.webdriver.remote.webdriver import WebDriver


class Screenshotter:
    """从浏览器当前画面截图并保存到本地。"""

    def __init__(self, driver: WebDriver, output_dir: str = "screenshots"):
        """
        Args:
            driver: Selenium WebDriver 实例。
            output_dir: 截图输出目录。
        """
        self.driver = driver
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def take(self, name: str) -> str:
        """截取当前浏览器画面并保存。

        Args:
            name: 截图名称（不含扩展名），如 "主页", "英雄"。

        Returns:
            str: 保存的文件路径。
        """
        filename = f"{name}.png"
        filepath = os.path.join(self.output_dir, filename)
        self.driver.save_screenshot(filepath)
        print(f"[截图] 已保存: {filepath}")
        return filepath
```

- [ ] **Step 2: Commit**

```bash
git add screenshotter.py
git commit -m "feat: add screenshot capture module"
```

---

### Task 4: navigator.py 游戏内导航模块

**Files:**
- Create: `navigator.py`

**Interfaces:**
- Consumes: `config` (MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL, TEMPLATES_DIR, TEMPLATE_MATCH_TIMEOUT)
- Produces: `class Navigator`
  - `__init__(self, driver: WebDriver, templates_dir: str, threshold: float, max_retries: int)`
  - `find_and_click(self, template_name: str, timeout: int = 10) -> bool`
  - `wait_for_template(self, template_name: str, timeout: int = 15) -> bool`

- [ ] **Step 1: 创建 `navigator.py`**

```python
"""游戏内导航模块 —— 基于 OpenCV 模板匹配定位按钮并点击。"""

import time
import cv2
import numpy as np
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from config import MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL


class Navigator:
    """在云游戏画面中通过图像识别找到按钮并点击。"""

    def __init__(
        self,
        driver: WebDriver,
        templates_dir: str = "templates",
        threshold: float = MATCH_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Args:
            driver: Selenium WebDriver 实例。
            templates_dir: 存放按钮模板图的目录。
            threshold: cv2.matchTemplate 匹配置信度阈值 (0~1)。
            max_retries: 单个按钮最大匹配重试次数。
        """
        self.driver = driver
        self.templates_dir = templates_dir
        self.threshold = threshold
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_screenshot(self) -> np.ndarray:
        """获取当前浏览器画面，返回 OpenCV 格式的 BGR numpy 数组。"""
        png = self.driver.get_screenshot_as_png()
        nparr = np.frombuffer(png, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def _template_path(self, template_name: str) -> str:
        """构建模板文件的完整路径。"""
        return f"{self.templates_dir}/{template_name}"

    def _click_at(self, x: int, y: int) -> None:
        """在浏览器画面上 (x, y) 位置模拟鼠标左键点击。

        使用 ActionChains 以 body 元素为锚点偏移点击，
        确保坐标与 Selenium 截图像素对齐。
        """
        body = self.driver.find_element(By.TAG_NAME, "body")
        ActionChains(self.driver) \
            .move_to_element_with_offset(body, x, y) \
            .click() \
            .perform()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def find_and_click(self, template_name: str, timeout: int = 10) -> bool:
        """在画面中匹配模板图并点击其中心位置。

        Args:
            template_name: 模板文件名（含扩展名），如 "avatar.png"。
            timeout: 单次尝试内的等待时间（暂保留接口，实际由重试控制）。

        Returns:
            bool: 匹配成功并点击返回 True，否则 False。
        """
        template_path = self._template_path(template_name)
        template = cv2.imread(template_path)

        if template is None:
            print(f"[警告] 模板文件不存在: {template_path}")
            return False

        t_h, t_w = template.shape[:2]

        for attempt in range(1, self.max_retries + 1):
            screen = self._get_screenshot()
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= self.threshold:
                center_x = max_loc[0] + t_w // 2
                center_y = max_loc[1] + t_h // 2
                self._click_at(center_x, center_y)
                print(f"[导航] 点击 {template_name} "
                      f"(置信度: {max_val:.2f}, 坐标: {center_x},{center_y})")
                time.sleep(CLICK_INTERVAL)
                return True

            print(f"[导航] 未匹配到 {template_name} "
                  f"(尝试 {attempt}/{self.max_retries}, "
                  f"最高置信度: {max_val:.2f})")
            time.sleep(RETRY_INTERVAL)

        print(f"[警告] 未能找到并点击: {template_name}")
        return False

    def wait_for_template(self, template_name: str, timeout: int = 15) -> bool:
        """轮询等待模板出现（不点击）。

        Args:
            template_name: 模板文件名。
            timeout: 最大等待时间（秒）。

        Returns:
            bool: 在超时前检测到模板返回 True，否则 False。
        """
        template_path = self._template_path(template_name)
        template = cv2.imread(template_path)

        if template is None:
            print(f"[警告] 模板文件不存在: {template_path}")
            return False

        start = time.time()
        while time.time() - start < timeout:
            screen = self._get_screenshot()
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= self.threshold:
                print(f"[导航] 检测到 {template_name}")
                return True
            time.sleep(1)

        print(f"[警告] 超时未检测到: {template_name}")
        return False
```

- [ ] **Step 2: Commit**

```bash
git add navigator.py
git commit -m "feat: add in-game navigation module with OpenCV template matching"
```

---

### Task 5: login.py QQ 登录模块

**Files:**
- Create: `login.py`

**Interfaces:**
- Consumes: `config` (CLOUD_GAMING_URL, PAGE_LOAD_WAIT, QQ_NUMBER)
- Consumes: `selenium.webdriver` (Chrome WebDriver)
- Produces: `login(driver: WebDriver) -> bool` — 执行 QQ 登录流程，成功返回 True

- [ ] **Step 1: 创建 `login.py`**

```python
"""QQ 账号登录腾讯先锋云游戏模块。"""

import time
from getpass import getpass

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CLOUD_GAMING_URL, PAGE_LOAD_WAIT, QQ_NUMBER


def login(driver: WebDriver) -> bool:
    """在腾讯先锋云游戏中完成 QQ 登录。

    Args:
        driver: 已初始化的 Chrome WebDriver 实例。

    Returns:
        bool: 登录成功返回 True，失败返回 False。
    """
    print("=" * 50)
    print("[登录] 开始 QQ 登录流程")

    # ------------------------------------------------------------------
    # 1. 打开腾讯先锋云游戏首页
    # ------------------------------------------------------------------
    print(f"[登录] 打开: {CLOUD_GAMING_URL}")
    driver.get(CLOUD_GAMING_URL)
    time.sleep(PAGE_LOAD_WAIT)

    # ------------------------------------------------------------------
    # 2. 点击页面上的"登录"按钮
    # ------------------------------------------------------------------
    try:
        # 腾讯先锋登录按钮可能有多种文字形式
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(), '登录') or contains(text(), '登錄') "
                "or contains(@class, 'login')]"
            ))
        )
        login_button.click()
        print("[登录] 已点击登录按钮")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        print(f"[错误] 找不到登录按钮: {e}")
        print("[提示] 请确认 CLOUD_GAMING_URL 是否正确，或页面结构是否变化")
        return False

    # ------------------------------------------------------------------
    # 3. 选择 QQ 登录方式 (可能需要在弹窗中切换)
    # ------------------------------------------------------------------
    try:
        qq_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(), 'QQ') or contains(@title, 'QQ') "
                "or contains(@class, 'qq')]"
            ))
        )
        qq_tab.click()
        print("[登录] 已选择 QQ 登录")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception:
        print("[登录] 未找到 QQ 登录切换标签（可能默认已是 QQ 登录）")

    # ------------------------------------------------------------------
    # 4. 获取 QQ 账号
    # ------------------------------------------------------------------
    qq_number = QQ_NUMBER
    if not qq_number:
        qq_number = input("[登录] 请输入 QQ 号: ").strip()
    else:
        print(f"[登录] 使用配置的 QQ 号: {qq_number}")

    # ------------------------------------------------------------------
    # 5. 输入 QQ 密码
    # ------------------------------------------------------------------
    qq_password = getpass("[登录] 请输入 QQ 密码 (输入不可见): ")

    # ------------------------------------------------------------------
    # 6. 填写登录表单
    # ------------------------------------------------------------------
    try:
        # QQ 登录页通常在 iframe 中
        # 先尝试直接查找，再尝试切换 iframe
        username_input = None
        password_input = None

        # 尝试在主页面查找输入框
        try:
            username_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//input[@type='text' or @name='u' or @name='account' "
                    "or @placeholder='QQ号' or @placeholder='QQ号码']"
                ))
            )
        except Exception:
            # 尝试切换到 iframe
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                driver.switch_to.frame(iframe)
                try:
                    username_input = driver.find_element(
                        By.XPATH,
                        "//input[@type='text' or @name='u' or @name='account']"
                    )
                    if username_input:
                        break
                except Exception:
                    driver.switch_to.default_content()

        if not username_input:
            print("[错误] 找不到 QQ 号输入框")
            driver.save_screenshot("debug_login.png")
            print("[调试] 已保存登录页面截图至 debug_login.png")
            return False

        username_input.clear()
        username_input.send_keys(qq_number)
        print("[登录] 已填入 QQ 号")

        # 密码输入框
        password_input = driver.find_element(
            By.XPATH,
            "//input[@type='password' or @name='p' or @name='password']"
        )
        password_input.clear()
        password_input.send_keys(qq_password)
        print("[登录] 已填入密码")

    except Exception as e:
        print(f"[错误] 填写登录表单失败: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 7. 点击登录提交按钮
    # ------------------------------------------------------------------
    try:
        submit_btn = driver.find_element(
            By.XPATH,
            "//*[@type='submit' or contains(@class, 'submit') "
            "or contains(@id, 'login') or contains(text(), '登录')]"
        )
        submit_btn.click()
        print("[登录] 已提交登录")
    except Exception as e:
        print(f"[错误] 找不到登录提交按钮: {e}")
        return False

    # ------------------------------------------------------------------
    # 8. 等待登录完成
    # ------------------------------------------------------------------
    time.sleep(5)
    driver.switch_to.default_content()  # 切回主页面

    # 检查是否需要验证码
    page_source = driver.page_source
    if "验证码" in page_source or "captcha" in page_source.lower():
        print("[登录] ⚠️  检测到验证码，请手动完成验证...")
        input("[登录] 完成验证码后按回车继续...")

    print("[登录] ✅ QQ 登录流程完成")
    return True
```

- [ ] **Step 2: Commit**

```bash
git add login.py
git commit -m "feat: add QQ login module for Tencent Start cloud gaming"
```

---

### Task 6: game_launcher.py 游戏启动模块

**Files:**
- Create: `game_launcher.py`

**Interfaces:**
- Consumes: `navigator.Navigator` (用于图像匹配定位游戏图标)
- Consumes: `config` (GAME_LAUNCH_WAIT, PAGE_LOAD_WAIT)
- Produces: `launch_game(driver: WebDriver, nav: Navigator) -> bool` — 启动王者荣耀，成功返回 True

- [ ] **Step 1: 创建 `game_launcher.py`**

```python
"""在腾讯先锋云游戏平台中启动王者荣耀。"""

import time

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from navigator import Navigator
from config import GAME_LAUNCH_WAIT, PAGE_LOAD_WAIT


def launch_game(driver: WebDriver, nav: Navigator) -> bool:
    """在腾讯先锋平台中找到并启动王者荣耀。

    优先使用 OpenCV 模板匹配查找游戏图标，
    降级为 DOM 文本搜索。

    Args:
        driver: Selenium WebDriver 实例。
        nav: Navigator 实例。

    Returns:
        bool: 游戏启动成功返回 True。
    """
    print("=" * 50)
    print("[启动] 正在启动王者荣耀...")

    # ------------------------------------------------------------------
    # 1. 确保在云游戏主页面
    # ------------------------------------------------------------------
    # 登录后可能跳转，需要等待页面稳定
    time.sleep(PAGE_LOAD_WAIT)

    # ------------------------------------------------------------------
    # 2. 查找并点击王者荣耀
    # ------------------------------------------------------------------
    # 方式 A: 使用模板匹配（如果有游戏图标模板）
    game_found = nav.find_and_click("honor_of_kings.png", timeout=10)

    # 方式 B: 降级为 DOM 文本搜索
    if not game_found:
        print("[启动] 模板匹配未找到，尝试 DOM 搜索...")
        try:
            game_element = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((
                    By.XPATH,
                    "//*[contains(text(), '王者荣耀') "
                    "or contains(@alt, '王者荣耀') "
                    "or contains(@title, '王者荣耀')]"
                ))
            )
            game_element.click()
            game_found = True
            print("[启动] 通过 DOM 搜索找到游戏入口")
        except Exception as e:
            print(f"[错误] 找不到王者荣耀入口: {e}")
            driver.save_screenshot("debug_find_game.png")
            return False

    # ------------------------------------------------------------------
    # 3. 点击"开始游戏"按钮
    # ------------------------------------------------------------------
    time.sleep(PAGE_LOAD_WAIT)
    try:
        start_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(), '开始游戏') "
                "or contains(text(), '启动') "
                "or contains(@class, 'start')]"
            ))
        )
        start_btn.click()
        print("[启动] 已点击开始游戏")
    except Exception:
        # 有些情况下点击游戏图标后直接开始加载，不需要二次点击
        print("[启动] 未找到开始游戏按钮（可能已自动启动）")

    # ------------------------------------------------------------------
    # 4. 等待游戏加载
    # ------------------------------------------------------------------
    print(f"[启动] 等待游戏加载 ({GAME_LAUNCH_WAIT} 秒)...")
    time.sleep(GAME_LAUNCH_WAIT)

    # 等待游戏主界面特征出现
    if nav.wait_for_template("game_main.png", timeout=30):
        print("[启动] ✅ 王者荣耀已启动")
        return True

    print("[启动] ⚠️  未检测到游戏主界面，但将继续执行...")
    return True
```

- [ ] **Step 2: Commit**

```bash
git add game_launcher.py
git commit -m "feat: add game launcher module"
```

---

### Task 7: main.py 主入口 — 编排完整截图流程

**Files:**
- Create: `main.py`

**Interfaces:**
- Consumes: `login.login`, `game_launcher.launch_game`, `navigator.Navigator`, `screenshotter.Screenshotter`, `config`
- Produces: 可执行脚本 `python main.py`

- [ ] **Step 1: 创建 `main.py`**

```python
#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— 主入口。

使用方法:
    python main.py

前置条件:
    1. 已安装 Chrome 浏览器
    2. 已安装 ChromeDriver 并加入 PATH
    3. 已在 templates/ 目录中放入按钮模板图
"""

import time
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import (
    BROWSER_WIDTH,
    BROWSER_HEIGHT,
    TEMPLATES_DIR,
    SCREENSHOTS_DIR,
    PAGE_LOAD_WAIT,
)
from login import login
from game_launcher import launch_game
from navigator import Navigator
from screenshotter import Screenshotter


# ---------------------------------------------------------------------------
# 截图任务定义
# 每个任务: (截图名称, [(模板名, 描述), ...])
# 列表表示点击序列：依次点击模板后截图
# ---------------------------------------------------------------------------
SCREENSHOT_TASKS = [
    # ====================
    # 1. 个人主页相关
    # ====================
    ("主页", [
        ("avatar.png", "点击左上角头像"),
        ("tab_home.png", "点击主页标签"),
    ]),
    ("英雄", [
        ("tab_hero.png", "点击英雄标签"),
    ]),
    ("万象图鉴首页", [
        ("tab_illustrated.png", "点击图鉴标签"),
        ("universal_illustrated.png", "点击万象图鉴"),
    ]),
    ("万象图鉴-灵宝", [
        ("lingbao.png", "点击灵宝"),
    ]),
    ("皮肤图鉴", [
        ("skin_illustrated.png", "点击皮肤图鉴"),
    ]),

    # ====================
    # 2. 商城 - 夺宝
    # ====================
    ("积分夺宝", [
        ("shop_icon.png", "点击商城"),
        ("lottery_tab.png", "点击夺宝"),
        ("points_lottery.png", "点击积分夺宝"),
    ]),

    # ====================
    # 3. 定制
    # ====================
    ("天幕", [
        ("customize_icon.png", "点击定制"),
        ("skin_customize.png", "点击皮肤定制"),
        ("my_tab.png", "点击我的"),
        ("sky_curtain.png", "点击天幕"),
    ]),
    ("小兵", [
        ("minion.png", "点击小兵"),
    ]),
    ("个性戳戳", [
        ("customize_icon.png", "点击定制"),
        ("personal_customize.png", "点击个性定制"),
        ("poke.png", "点击个性戳戳"),
    ]),

    # ====================
    # 4. 贵族
    # ====================
    ("贵族", [
        ("nobility_icon.png", "点击贵族图标"),
    ]),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def go_home(nav: Navigator) -> None:
    """尝试返回游戏主界面。"""
    print("[导航] 返回主界面...")
    # 尝试多次按 ESC 或点击空白区域关闭弹窗
    nav.find_and_click("close_button.png", timeout=3) or \
        nav.find_and_click("back_arrow.png", timeout=3)
    time.sleep(PAGE_LOAD_WAIT)


def run_screenshot_flow(driver: webdriver.Chrome, nav: Navigator, shot: Screenshotter):
    """执行所有截图任务。"""
    total = len(SCREENSHOT_TASKS)
    success = 0

    for idx, (name, clicks) in enumerate(SCREENSHOT_TASKS, 1):
        print(f"\n{'─' * 40}")
        print(f"[{idx}/{total}] 目标: {name}")

        # 执行点击序列
        all_ok = True
        for template, desc in clicks:
            print(f"  → {desc} ({template})")
            if not nav.find_and_click(template):
                print(f"  ⚠️  跳过（找不到 {template})")
                all_ok = False
                break

        # 截图
        if all_ok:
            time.sleep(PAGE_LOAD_WAIT)
            shot.take(name)
            success += 1
        else:
            print(f"  ❌ 截图失败: {name}")

        # 返回主界面（为下一个截图任务做准备）
        go_home(nav)

    print(f"\n{'=' * 50}")
    print(f"完成: {success}/{total} 张截图成功")
    if success < total:
        print(f"失败: {total - success} 张")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    """主入口。"""
    print("王者荣耀云游戏自动截图工具")
    print("=" * 50)

    # 1. 初始化 Chrome
    print("[初始化] 启动 Chrome...")
    chrome_options = Options()
    chrome_options.add_argument(f"--window-size={BROWSER_WIDTH},{BROWSER_HEIGHT}")
    # 如果 Chrome 未在 PATH 中，可取消下一行注释并指定路径
    # chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(BROWSER_WIDTH, BROWSER_HEIGHT)

    try:
        # 2. 登录
        if not login(driver):
            print("[错误] 登录失败，退出")
            sys.exit(1)

        # 3. 初始化 Navigator 和 Screenshotter
        nav = Navigator(driver, templates_dir=TEMPLATES_DIR)
        shot = Screenshotter(driver, output_dir=SCREENSHOTS_DIR)

        # 4. 启动游戏
        if not launch_game(driver, nav):
            print("[错误] 游戏启动失败，退出")
            sys.exit(1)

        # 5. 执行截图流程
        run_screenshot_flow(driver, nav, shot)

    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
    except Exception as e:
        print(f"\n[异常] {e}")
        driver.save_screenshot("debug_crash.png")
        print("[调试] 已保存崩溃截图至 debug_crash.png")
        raise
    finally:
        print("\n[清理] 关闭浏览器...")
        driver.quit()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add main entry point with complete screenshot flow"
```

---

### Task 8: 模板图准备指南

**Files:**
- Create: `templates/README.md`

**说明:** 此任务创建一个指南文档，说明如何准备 OpenCV 所需的模板图。不需要提交代码。

- [ ] **Step 1: 创建 `templates/README.md`**

```markdown
# 模板图准备指南

运行脚本前，需要在 `templates/` 目录下放入以下按钮模板图。
模板图通过首次手动进入游戏后截取小图获得。

## 截取方法

1. 运行脚本，在 QQ 登录完成后手动进入对应页面
2. 截取整个游戏画面
3. 用小画图工具裁剪出目标按钮区域（建议裁剪 30-50px 边距）
4. 保存为对应的文件名

## 所需模板图清单

### 主界面
| 文件名 | 说明 | 位置 |
|--------|------|------|
| `avatar.png` | 左上角头像 | 主界面左上角 |
| `shop_icon.png` | 商城入口图标 | 主界面右侧 |
| `customize_icon.png` | 定制入口图标 | 主界面下方 |
| `nobility_icon.png` | 贵族图标 | 主界面上方 |
| `game_main.png` | 游戏主界面特征 | 用于确认游戏已加载 |
| `close_button.png` | 关闭/返回按钮 | 弹窗右上角通用 X |
| `back_arrow.png` | 返回箭头 | 页面左上角通用返回 |

### 个人主页
| 文件名 | 说明 |
|--------|------|
| `tab_home.png` | 主页标签 |
| `tab_hero.png` | 英雄标签 |
| `tab_illustrated.png` | 图鉴标签 |

### 图鉴
| 文件名 | 说明 |
|--------|------|
| `universal_illustrated.png` | 万象图鉴入口 |
| `lingbao.png` | 灵宝入口 |
| `skin_illustrated.png` | 皮肤图鉴入口 |

### 商城
| 文件名 | 说明 |
|--------|------|
| `lottery_tab.png` | 夺宝标签 |
| `points_lottery.png` | 积分夺宝入口 |

### 定制
| 文件名 | 说明 |
|--------|------|
| `skin_customize.png` | 皮肤定制 |
| `my_tab.png` | 我的标签 |
| `sky_curtain.png` | 天幕 |
| `minion.png` | 小兵 |
| `personal_customize.png` | 个性定制 |
| `poke.png` | 个性戳戳 |

### 可选（游戏启动）
| 文件名 | 说明 |
|--------|------|
| `honor_of_kings.png` | 腾讯先锋页面中的王者荣耀图标 |

> **提示:** 模板图越精确，匹配成功率越高。建议在模板图周围保留少量游戏 UI 背景以增加匹配唯一性。
```

- [ ] **Step 2: Commit**

```bash
git add templates/README.md
git commit -m "docs: add template image preparation guide"
```

---

## 执行顺序

Tasks 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8

- Tasks 1-4 无依赖，但建议按顺序创建（2 依赖 1 的目录，3 依赖 2 的 config（实际上不依赖），4 依赖 2）
- Task 5 依赖 2 (config)
- Task 6 依赖 4 (Navigator)
- Task 7 依赖所有前序模块 (2, 3, 4, 5, 6)
- Task 8 可在任何时间完成

完成 Task 1-7 后，脚本即可运行（前提是已按 Task 8 准备了模板图）。
