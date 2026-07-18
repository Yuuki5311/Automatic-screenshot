"""QQ / 微信扫码登录模块。

支持两种登录场景：
    1. web_login: 在 gamer.qq.com 网页中完成腾讯先锋平台扫码登录
    2. game_login: 在云游戏画面中检测游戏内登录二维码

两个函数都采用回调模式，通过 on_qr 和 on_status 将
二维码图片和状态更新推送给 GUI 层。
"""

import time
from typing import Callable

import cv2
import numpy as np
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import NoSuchElementException

from config import BROWSER_WIDTH, BROWSER_HEIGHT, CLOUD_GAMING_URL, PAGE_LOAD_WAIT
from logger import get_logger

log = get_logger()


def bottom_half_bounds(
    viewport_w: int, viewport_h: int
) -> tuple[int, int, int, int]:
    """按实际截图像素返回下半屏 bounds (x, y, w, h)。"""
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)
    y0 = h // 2
    return (0, y0, w, h - y0)


def top_half_bounds(
    viewport_w: int, viewport_h: int
) -> tuple[int, int, int, int]:
    """按实际截图像素返回上半屏 bounds (x, y, w, h)。"""
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)
    return (0, 0, w, h // 2)


# 退出/云服务器确认：画面上可能是「确定」或「同意」
CONFIRM_TEMPLATES = ("game_popup_confirm.png", "game_logout_confirm.png")
CONFIRM_THRESHOLD = 0.48  # 云游戏压缩下 0.53 易差一点点失败（曾见 0.513）


def click_confirm_dialog(nav, *, wait_after: float = 3.0) -> str | None:
    """在下半屏点击确认类按钮。

    Returns:
        点中的模板文件名；都未匹配则返回 None。
    """
    if wait_after > 0:
        time.sleep(wait_after)
    vw, vh = nav.viewport_size()
    bounds = bottom_half_bounds(vw, vh)
    log.info(
        f"确认弹窗搜索区 viewport={vw}x{vh} bounds={bounds} "
        f"templates={CONFIRM_TEMPLATES} threshold={CONFIRM_THRESHOLD}"
    )
    for tpl in CONFIRM_TEMPLATES:
        if nav.find_and_click(
            tpl,
            timeout=3,
            bounds=bounds,
            threshold=CONFIRM_THRESHOLD,
            max_retries=4,
        ):
            log.info(f"已点击确认弹窗: {tpl}")
            return tpl
    return None


def platform_select_bounds(
    viewport_w: int, viewport_h: int, platform: str
) -> tuple[int, int, int, int]:
    """按实际截图像素计算平台按钮搜索区。

    布局：下半屏；微信左半、QQ 右半。使用真实视口尺寸，避免固定
    1920×1080 与最大化截图不一致导致搜到错误半区。
    """
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)
    y0 = h // 2
    hh = h - y0
    half_w = w // 2
    if platform.startswith("wx"):
        return (0, y0, half_w, hh)
    return (half_w, y0, w - half_w, hh)


# ---------------------------------------------------------------------------
# 网页登录（腾讯先锋 gamer.qq.com）
# ---------------------------------------------------------------------------


def web_login(
    driver: WebDriver,
    login_type: str,
    on_qr: Callable[[], None] | None = None,
    on_status: Callable[[str], None] | None = None,
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
        on_qr: 可选，通知 GUI 等待扫码的回调。
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

    # ---- 4. 切换到 iframe，提示用户扫码 ----
    try:
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
            pass

    except Exception as e:
        on_status(f"切换登录 iframe 失败: {e}")
        driver.save_screenshot("debug_qr.png")
        return False

    # 通知 GUI 等待扫码（不截取二维码）
    if on_qr:
        on_qr()
    on_status("请使用手机扫描二维码登录...")

    # ---- 5. 轮询等待登录成功 ----
    start = time.time()
    while time.time() - start < timeout:
        try:
            # 切回顶层检测页面变化
            driver.switch_to.default_content()

            # ---- 5a. 检测登录弹窗状态 ----
            try:
                login_popup = driver.find_element(By.ID, "user_login")
                if not login_popup.is_displayed():
                    on_status("✅ 腾讯先锋登录成功（弹窗已关闭）")
                    time.sleep(PAGE_LOAD_WAIT)
                    driver.save_screenshot("debug_login_success.png")
                    return True
            except NoSuchElementException:
                # 登录按钮从 DOM 彻底消失 = 页面已切换为登录后状态
                on_status("✅ 腾讯先锋登录成功（已登录）")
                time.sleep(PAGE_LOAD_WAIT)
                driver.save_screenshot("debug_login_success.png")
                return True
            except Exception:
                log.debug(f"检测登录弹窗状态异常，继续轮询", exc_info=True)

            # ---- 5b. Cookie 检测 ----
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie.get("name", "") in (
                    "p_uin", "p_skey", "pt2gguin", "uin", "skey",
                ):
                    on_status("✅ 腾讯先锋登录成功（Cookie 检测）")
                    time.sleep(PAGE_LOAD_WAIT)
                    driver.save_screenshot("debug_login_success.png")
                    return True

            # ---- 5c. JS 检测页面用户元素或 auth cookie ----
            try:
                logged_in = driver.execute_script("""
                    if (document.cookie.indexOf('p_uin=') > -1) return true;
                    if (document.cookie.indexOf('uin=') > -1) return true;
                    if (document.querySelector('[class*="user"]')) return true;
                    if (document.querySelector('[class*="avatar"]')) return true;
                    if (document.querySelector('[class*="nick"]')) return true;
                    return false;
                """)
                if logged_in:
                    on_status("✅ 腾讯先锋登录成功（JS 检测）")
                    time.sleep(PAGE_LOAD_WAIT)
                    driver.save_screenshot("debug_login_success.png")
                    return True
            except Exception:
                log.debug(f"JS检测用户元素异常", exc_info=True)

            # ---- 5d. CSS 检测用户元素 ----
            user_selectors = [
                ".user-info", ".user-name", ".user-avatar", ".avatar",
                "img[class*='avatar']", "[class*='user']", "[class*='nickname']",
                ".header-avatar", ".login-user", "#user-info",
            ]
            for sel in user_selectors:
                try:
                    elements = driver.find_elements(By.CSS_SELECTOR, sel)
                    for elem in elements:
                        if elem.is_displayed():
                            on_status("✅ 腾讯先锋登录成功（用户元素检测）")
                            time.sleep(PAGE_LOAD_WAIT)
                            driver.save_screenshot("debug_login_success.png")
                            return True
                except Exception:
                    log.debug(f"CSS选择器 {sel} 检测异常", exc_info=True)
                    continue

        except Exception:
            log.debug(f"登录轮询外层异常，继续尝试", exc_info=True)

        time.sleep(2)

    driver.save_screenshot("debug_login_timeout.png")
    on_status("⚠️ 扫码超时")
    return False


# ---------------------------------------------------------------------------
# 游戏内登录（云游戏画面）
# ---------------------------------------------------------------------------


# 平台 → 模板文件映射
PLATFORM_TEMPLATES = {
    "wx_ios": "game_wx_ios.png",
    "wx_android": "game_wx_android.png",
    "qq_ios": "game_qq_ios.png",
    "qq_android": "game_qq_android.png",
}


def game_login(
    nav,  # Navigator 实例
    platform: str,
    on_qr: Callable[[], None] | None = None,
    on_status: Callable[[str], None] | None = None,
    timeout: int = 300,
) -> bool:
    """在云游戏画面中完成游戏内账号登录。

    流程：
        1. 点击用户选择的平台登录按钮
        2. 通知 GUI 等待扫码
        3. 轮询检测登录成功
        4. 点击「进入游戏」

    Args:
        nav: Navigator 实例。
        platform: 'wx_ios' | 'wx_android' | 'qq_ios' | 'qq_android'
        on_qr: 可选，通知 GUI 等待扫码的回调。
        on_status: 状态更新回调。
        timeout: 扫码等待超时（秒）。

    Returns:
        bool: 登录成功返回 True。
    """
    platform_name = {
        "wx_ios": "微信 iOS",
        "wx_android": "微信安卓",
        "qq_ios": "QQ iOS",
        "qq_android": "QQ 安卓",
    }.get(platform, platform)

    template_file = PLATFORM_TEMPLATES.get(platform)
    if template_file is None:
        on_status(f"未知的平台选择: {platform}")
        return False

    # ---- 按实际截图像素计算搜索区域（下半屏：微信左 / QQ 右） ----
    vw, vh = nav.viewport_size()
    platform_bounds = platform_select_bounds(vw, vh, platform)
    log.info(
        f"平台选择搜索区 platform={platform} viewport={vw}x{vh} bounds={platform_bounds}"
    )

    # ---- 1. 点击平台登录按钮 ----
    on_status(f"选择登录平台: {platform_name}...")
    time.sleep(2)

    if not nav.find_and_click(template_file, timeout=10, bounds=platform_bounds, max_retries=5):
        on_status(f"找不到 {platform_name} 登录按钮 ({template_file})")
        return False

    on_status(f"已选择 {platform_name} 登录")

    # ---- 1a. 检查「登录其他账号」弹窗 ----
    time.sleep(2)
    login_other_bounds = bottom_half_bounds(vw, vh)
    if nav.find_and_click("game_login_other.png", timeout=3, bounds=login_other_bounds):
        on_status("已点击「登录其他账号」")
        time.sleep(2)

    # ---- 3. 通知 GUI 并等待扫码登录 ----
    if on_qr:
        on_qr()
    on_status(f"请在游戏窗口中扫描 {platform_name} 登录二维码...")
    time.sleep(3)

    start = time.time()
    qr_appeared = False
    QR_CODE_TIMEOUT = 15  # 15 秒内必须出现二维码

    avatar_detected_at = None  # 头像出现时间（用于快速重试）

    # 重新启用 QRCodeDetector 用于检测二维码是否出现
    qr_detector = cv2.QRCodeDetector()

    while time.time() - start < timeout:
        # ---- 检测登录成功 ----
        if nav.wait_for_template("avatar.png", timeout=2):
            on_status("✅ 游戏登录成功")
            time.sleep(2)
            if nav.find_and_click("enter_game.png", timeout=10):
                on_status("✅ 已点击进入游戏")
                time.sleep(3)
                return True
            # avatar 出现但 enter_game 没出现 → 记录时间，限期等待
            if avatar_detected_at is None:
                avatar_detected_at = time.time()

        if nav.wait_for_template("enter_game.png", timeout=2):
            if nav.find_and_click("enter_game.png", timeout=3):
                on_status("✅ 游戏登录成功，已进入游戏")
                time.sleep(3)
                return True

        # avatar 已出现超过 30 秒仍未找到 enter_game → 返回重试平台选择
        if avatar_detected_at and time.time() - avatar_detected_at > 30:
            on_status("⚠️ 登录成功但未找到进入游戏按钮，将重试平台选择")
            return False

        # ---- 检测二维码是否出现 ----
        if not qr_appeared:
            try:
                png = nav.driver.get_screenshot_as_png()
                frame_bgr = cv2.imdecode(
                    np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR
                )
                del png
                data, bbox, _ = qr_detector.detectAndDecode(frame_bgr)
                if bbox is not None and len(bbox) > 0:
                    qr_appeared = True
                    on_status("✅ 检测到登录二维码")
                del frame_bgr
            except Exception:
                log.debug(f"二维码检测异常", exc_info=True)

            # 15 秒内未出现二维码 → 返回失败，触发重试
            if time.time() - start > QR_CODE_TIMEOUT:
                on_status("⚠️ 未检测到登录二维码，将重试")
                return False

        time.sleep(2)

    on_status("⚠️ 游戏登录扫码超时")
    return False
