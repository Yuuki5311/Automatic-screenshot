"""反检测浏览器初始化。

绕过 gamer.qq.com 等网站对 Selenium 自动化特征的检测。
使用 webdriver-manager 自动管理浏览器驱动版本。

- macOS: Chrome + ChromeDriver（本地检测版本 + npmmirror 镜像下载）
- Windows: Edge + EdgeDriver（系统自带 Edge，驱动从微软服务器下载，国内可达）
"""

import platform
import re
import subprocess

_SYSTEM = platform.system()


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


def _get_chrome_version() -> str | None:
    """获取本地 Chrome 主版本号，失败返回 None。"""
    system = platform.system()
    commands: list[list[str]] = []
    if system == "Darwin":
        commands = [
            ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "--version"],
        ]
    elif system == "Windows":
        commands = [
            [r'reg', 'query', r'HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon', '/v', 'version'],
            [r'chrome', '--version'],
        ]
    else:
        commands = [
            ["google-chrome", "--version"],
            ["chromium-browser", "--version"],
        ]

    for cmd in commands:
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                m = re.search(r'([\d]+)\.', result.stdout)
                if m:
                    return m.group(1)
        except Exception:
            continue

    # Windows fallback: parse registry string "0x00011000 REG_SZ 150.0..."
    if system == "Windows":
        for cmd in commands:
            try:
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
                m = re.search(r'REG_SZ\s+([\d]+)\.', result.stdout)
                if m:
                    return m.group(1)
            except Exception:
                continue

    return None


def _create_chrome(width: int, height: int):
    """macOS: Chrome + ChromeDriver（npmmirror 镜像下载）。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    _configure_chromium_options(options, width, height)

    # 传入 driver_version 跳过 googlechromelabs.github.io 版本检测（国内被墙）
    # 本地检测失败时使用硬编码版本号，防止退化到被墙 API 导致超时卡死
    _chrome_ver = _get_chrome_version() or "150"
    _driver_path = ChromeDriverManager(
        url="https://registry.npmmirror.com/-/binary/chrome-for-testing",
        driver_version=_chrome_ver,
    ).install()

    # macOS Gatekeeper 会阻止未签名 chromedriver 运行 (status code -9)
    import os as _os
    _driver_bin = _driver_path
    if _os.path.isdir(_driver_path):
        for _f in _os.listdir(_driver_path):
            if _f.startswith("chromedriver"):
                _driver_bin = _os.path.join(_driver_path, _f)
                break
    subprocess.run(["xattr", "-c", _driver_bin], capture_output=True)
    subprocess.run(["chmod", "+x", _driver_bin], capture_output=True)
    subprocess.run(  # macOS 15+ 拒绝外部 ad-hoc 签名，需本地重签
        ["codesign", "--sign", "-", "--force", _driver_bin],
        capture_output=True,
    )

    service = Service(_driver_path)
    driver = webdriver.Chrome(service=service, options=options)

    _post_launch_setup(driver)

    # macOS: 全屏 Chrome
    subprocess.run([
        "osascript", "-e",
        'tell application "Google Chrome" to activate',
    ], capture_output=True)
    subprocess.run([
        "osascript", "-e",
        'tell application "System Events" to keystroke "f" using {command down, control down}',
    ], capture_output=True)

    return driver


def _create_edge(width: int, height: int):
    """Windows: Edge + EdgeDriver（系统自带 Edge，驱动从微软服务器下载）。"""
    from selenium import webdriver
    from selenium.webdriver.edge.options import Options as EdgeOptions
    from selenium.webdriver.edge.service import Service as EdgeService
    from webdriver_manager.microsoft import EdgeChromiumDriverManager

    options = EdgeOptions()
    _configure_chromium_options(options, width, height)

    # EdgeDriver 从微软 CDN 下载，国内不受限；自动匹配系统 Edge 版本
    _driver_path = EdgeChromiumDriverManager().install()

    service = EdgeService(_driver_path)
    driver = webdriver.Edge(service=service, options=options)

    _post_launch_setup(driver)

    driver.maximize_window()
    return driver


def _configure_chromium_options(options, width: int, height: int):
    """配置 Chromium 系浏览器通用选项（Chrome / Edge 共用）。"""
    options.add_argument(f"--window-size={width},{height}")
    options.add_argument("--force-device-scale-factor=1")

    # 反检测
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    options.add_argument("--disable-blink-features=AutomationControlled")

    # 稳定性
    options.add_argument("--no-sandbox")

    # 禁止无关弹窗
    options.add_argument("--disable-features=TranslateUI")
    prefs = {
        "credentials_enable_service": False,
        "profile.password_manager_enabled": False,
    }
    options.add_experimental_option("prefs", prefs)


def _post_launch_setup(driver):
    """Chromium 浏览器启动后的通用 CDP 注入。"""
    driver.execute_cdp_cmd(
        "Page.addScriptToEvaluateOnNewDocument",
        {"source": PRELOAD_SCRIPT},
    )


# ---------------------------------------------------------------------------
# 公开入口
# ---------------------------------------------------------------------------


def create_browser(width: int = 1920, height: int = 1080):
    """创建配置了反检测措施的浏览器实例。

    平台分派：
        - macOS  → Chrome  + ChromeDriver（npmmirror 镜像）
        - Windows → Edge   + EdgeDriver（微软 CDN，国内可达）
        - Linux   → Chrome（fallback）

    Args:
        width: 浏览器窗口宽度 (CSS 像素)。
        height: 浏览器窗口高度 (CSS 像素)。

    Returns:
        Selenium WebDriver 实例。
    """
    if _SYSTEM == "Windows":
        return _create_edge(width, height)

    # macOS / Linux: Chrome
    return _create_chrome(width, height)
