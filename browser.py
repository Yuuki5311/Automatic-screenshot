"""反检测浏览器初始化。

绕过 gamer.qq.com 等网站对 Selenium 自动化特征的检测。
使用 Selenium Manager 自动管理 Windows EdgeDriver。

平台适配:
    macOS  → Google Chrome + ChromeDriver
    Windows → Microsoft Edge + EdgeDriver (系统自带)
"""

import platform
import os
import subprocess
import time

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.chrome import ChromeDriverManager

from logger import get_logger

log = get_logger()

# 页面加载超时：避免 EXE 下 driver.get 长时间无响应像“卡住”
PAGE_LOAD_TIMEOUT_SEC = 60
# 浏览器命令超时（含首次下载 EdgeDriver）
BROWSER_COMMAND_TIMEOUT_SEC = 120


# CDP 注入脚本：在页面加载前执行，隐藏自动化特征
PRELOAD_SCRIPT = """
// 1. 隐藏 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', {
    get: () => undefined
});

// 2. 伪造 plugins —— 真实浏览器有 PDF Viewer 等内置插件
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
    // 保留但确保行为与正常浏览器一致
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


def _read_inner_size(driver) -> tuple[int, int]:
    """读取页面 CSS 视口 innerWidth × innerHeight。"""
    iw = driver.execute_script("return window.innerWidth;")
    ih = driver.execute_script("return window.innerHeight;")
    if iw is None or ih is None:
        raise RuntimeError("无法读取 window.innerWidth/innerHeight")
    return int(iw), int(ih)


def lock_viewport(driver, target_w: int, target_h: int, *, tol: int = 2, rounds: int = 6) -> tuple[int, int]:
    """将浏览器内容区锁定为约 target_w × target_h（CSS 像素）。

    通过反复 set_window_size 补偿标题栏/边框，使 innerWidth/innerHeight 接近目标。
    不最大化窗口。屏幕过小可能导致无法达到目标，此时记录警告并返回实际视口。
    """
    try:
        driver.set_window_position(0, 0)
    except Exception:
        log.debug("set_window_position 失败", exc_info=True)

    # 外框初值：略大于视口，给 chrome 留空
    outer_w = int(target_w) + 16
    outer_h = int(target_h) + 140

    iw = ih = 0
    for i in range(rounds):
        try:
            driver.set_window_size(outer_w, outer_h)
        except Exception:
            log.warning(f"set_window_size({outer_w}, {outer_h}) 失败", exc_info=True)
            break
        time.sleep(0.25)
        try:
            iw, ih = _read_inner_size(driver)
        except Exception:
            log.warning("读取视口失败", exc_info=True)
            break

        dw = target_w - iw
        dh = target_h - ih
        if abs(dw) <= tol and abs(dh) <= tol:
            log.info(f"视口已锁定: {iw}x{ih}（目标 {target_w}x{target_h}）")
            return iw, ih

        outer_w = max(200, outer_w + dw)
        outer_h = max(200, outer_h + dh)
        log.debug(
            f"视口校正 #{i + 1}: inner={iw}x{ih} → 调整外框至 {outer_w}x{outer_h}"
        )

    log.warning(
        f"视口未能精确锁定: 实际 {iw}x{ih}，目标 {target_w}x{target_h}。"
        "请确认显示器分辨率足够（建议不低于目标视口）。"
    )
    return iw, ih


def _create_chrome(width: int, height: int) -> webdriver.Chrome:
    """macOS: 创建 Chrome 浏览器实例。"""
    options = ChromeOptions()

    # 外框初值略大于目标视口；最终由 lock_viewport 校正
    options.add_argument(f"--window-size={width + 16},{height + 140}")
    options.add_argument("--force-device-scale-factor=1")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-features=TranslateUI")
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    service = ChromeService(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    # CDP 注入反检测脚本
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": PRELOAD_SCRIPT},
    )

    subprocess.run([
        "osascript", "-e",
        'tell application "Google Chrome" to activate',
    ], capture_output=True)

    lock_viewport(driver, width, height)
    return driver


def _bring_to_front_windows() -> None:
    """尽量把 Edge 窗口带到前台（自动化窗口常被 GUI 挡住）。"""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW("Chrome_WidgetWin_1", None)
        if hwnd:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(hwnd)
    except Exception:
        log.debug("前置 Edge 窗口失败", exc_info=True)


def _create_edge(width: int, height: int) -> webdriver.Edge:
    """Windows: 创建 Edge 浏览器实例（Chromium 内核，与 Chrome 兼容）。"""
    options = EdgeOptions()

    options.add_argument(f"--window-size={width + 16},{height + 140}")
    options.add_argument("--force-device-scale-factor=1")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-features=TranslateUI")
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)

    # webdriver-manager 仍访问已停用的 msedgedriver.azureedge.net。
    # 改由 Selenium Manager 管理驱动，并明确指定微软的新官方下载源。
    os.environ.setdefault(
        "SE_MSEDGEDRIVER_MIRROR_URL",
        "https://msedgedriver.microsoft.com",
    )

    log.info(
        "正在启动 Microsoft Edge（首次可能下载驱动，需联网，最多约 "
        f"{BROWSER_COMMAND_TIMEOUT_SEC}s）..."
    )
    t0 = time.time()
    try:
        driver = webdriver.Edge(options=options)
    except Exception as e:
        raise RuntimeError(
            "无法启动 Microsoft Edge。"
            "请确认已安装 Edge、可访问互联网（首次需下载驱动），"
            "并关闭残留的 msedgedriver 进程后重试。"
            f" 原始错误: {e}"
        ) from e
    log.info(f"Edge 进程已创建 ({time.time() - t0:.1f}s)")

    driver.set_page_load_timeout(PAGE_LOAD_TIMEOUT_SEC)
    driver.set_script_timeout(PAGE_LOAD_TIMEOUT_SEC)

    # Edge 同样支持 CDP（Chromium 内核）
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": PRELOAD_SCRIPT},
    )

    _bring_to_front_windows()
    lock_viewport(driver, width, height)
    return driver


def create_browser(width: int = None, height: int = None):
    """创建配置了反检测措施的浏览器实例，并锁定 CSS 视口尺寸。

    根据当前操作系统自动选择:
        macOS  → Google Chrome
        Windows → Microsoft Edge (系统自带,无需额外安装)

    Args:
        width: 目标视口宽度 (CSS 像素)，默认 config.BROWSER_WIDTH。
        height: 目标视口高度 (CSS 像素)，默认 config.BROWSER_HEIGHT。

    Returns:
        webdriver.Chrome 或 webdriver.Edge 实例。
    """
    from config import BROWSER_WIDTH, BROWSER_HEIGHT

    if width is None:
        width = BROWSER_WIDTH
    if height is None:
        height = BROWSER_HEIGHT

    system = platform.system()

    if system == "Windows":
        return _create_edge(width, height)
    else:
        # macOS / Linux fallback → Chrome
        return _create_chrome(width, height)
