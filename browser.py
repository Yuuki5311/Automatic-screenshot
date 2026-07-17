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

from selenium import webdriver
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from webdriver_manager.chrome import ChromeDriverManager


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


def _create_chrome(width: int, height: int) -> webdriver.Chrome:
    """macOS: 创建 Chrome 浏览器实例。"""
    options = ChromeOptions()

    options.add_argument(f"--window-size={width},{height}")
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

    driver.maximize_window()

    # macOS: AppleScript 全屏
    subprocess.run([
        "osascript", "-e",
        'tell application "Google Chrome" to activate',
    ], capture_output=True)
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "f" using {command down, control down}',
    ], capture_output=True)

    return driver


def _create_edge(width: int, height: int) -> webdriver.Edge:
    """Windows: 创建 Edge 浏览器实例（Chromium 内核，与 Chrome 兼容）。"""
    options = EdgeOptions()

    options.add_argument(f"--window-size={width},{height}")
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
    driver = webdriver.Edge(options=options)

    # Edge 同样支持 CDP（Chromium 内核）
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": PRELOAD_SCRIPT},
    )

    driver.maximize_window()

    return driver


def create_browser(width: int = 1920, height: int = 1080):
    """创建配置了反检测措施的浏览器实例。

    根据当前操作系统自动选择:
        macOS  → Google Chrome
        Windows → Microsoft Edge (系统自带,无需额外安装)

    Args:
        width: 浏览器窗口宽度 (CSS 像素)。
        height: 浏览器窗口高度 (CSS 像素)。

    Returns:
        webdriver.Chrome 或 webdriver.Edge 实例。
    """
    system = platform.system()

    if system == "Windows":
        return _create_edge(width, height)
    else:
        # macOS / Linux fallback → Chrome
        return _create_chrome(width, height)
