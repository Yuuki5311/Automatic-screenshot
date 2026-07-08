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

import cv2
import numpy as np
import pyautogui
from PIL import Image
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from selenium.common.exceptions import NoSuchElementException

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
                pass  # 真正的瞬态错误，继续轮询

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
                pass

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
                    continue

        except Exception:
            pass

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
    on_qr: Callable[[Image.Image], None],
    on_status: Callable[[str], None],
    timeout: int = 300,
) -> bool:
    """在云游戏画面中完成游戏内账号登录。

    流程：
        1. 退出当前登录（点击左上角退出按钮）
        2. 点击用户选择的平台登录按钮
        3. 截取二维码 → on_qr(image)
        4. 轮询检测登录成功
        5. 点击「进入游戏」

    Args:
        nav: Navigator 实例。
        platform: 'wx_ios' | 'wx_android' | 'qq_ios' | 'qq_android'
        on_qr: 截取到二维码时的回调。
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

    # ---- 计算搜索区域 ----
    screen_w, screen_h = pyautogui.size()
    scale = nav._scale

    # 退出按钮：左上角 30%×15% 区域
    logout_bounds = (0, 0, int(screen_w * scale * 0.3), int(screen_h * scale * 0.15))

    # 平台按钮：微信在左半边，QQ 在右半边
    if platform.startswith("wx"):
        platform_bounds = (0, 0, int(screen_w * scale * 0.5), int(screen_h * scale))
    else:
        platform_bounds = (int(screen_w * scale * 0.5), 0, int(screen_w * scale * 0.5), int(screen_h * scale))

    # ---- 1. 退出当前登录 ----
    on_status("正在退出当前游戏登录...")
    time.sleep(3)  # 等游戏画面稳定

    if nav.find_and_click("game_logout_btn.png", timeout=5, bounds=logout_bounds):
        on_status("已点击退出登录")
        time.sleep(3)

        # 处理确认退出的弹窗
        nav.find_and_click("popup_close.png", timeout=3)
        time.sleep(2)
    else:
        on_status("未检测到退出按钮，可能已是未登录状态")
        time.sleep(1)

    # ---- 2. 点击平台登录按钮 ----
    on_status(f"选择登录平台: {platform_name}...")
    time.sleep(2)

    if not nav.find_and_click(template_file, timeout=10, bounds=platform_bounds):
        on_status(f"找不到 {platform_name} 登录按钮 ({template_file})")
        return False

    on_status(f"已选择 {platform_name} 登录")

    # ---- 3. 等待并截取二维码 ----
    on_status("等待登录二维码...")
    time.sleep(3)

    qr_detector = cv2.QRCodeDetector()
    start = time.time()
    qr_sent = False

    while time.time() - start < timeout:
        # 截屏
        screenshot = pyautogui.screenshot()
        frame = np.array(screenshot)
        frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

        # ---- 检测登录成功 ----
        if nav.wait_for_template("avatar.png", timeout=2):
            on_status("✅ 游戏登录成功")
            time.sleep(2)
            # 步骤 4: 点击进入游戏
            if nav.find_and_click("enter_game.png", timeout=10):
                on_status("✅ 已点击进入游戏")
                time.sleep(3)
                return True
            else:
                # enter_game 可能已自动进入
                on_status("✅ 游戏登录成功，已进入游戏")
                time.sleep(3)
                return True

        if nav.wait_for_template("enter_game.png", timeout=2):
            if nav.find_and_click("enter_game.png", timeout=3):
                on_status("✅ 游戏登录成功，已进入游戏")
                time.sleep(3)
                return True

        # ---- 截取二维码 ----
        if not qr_sent:
            try:
                data, bbox, _ = qr_detector.detectAndDecode(frame_bgr)
                if bbox is not None and len(bbox) > 0:
                    pts = bbox.astype(int).reshape(4, 2)
                    x_min = max(0, pts[:, 0].min() - 20)
                    y_min = max(0, pts[:, 1].min() - 20)
                    x_max = min(frame_bgr.shape[1], pts[:, 0].max() + 20)
                    y_max = min(frame_bgr.shape[0], pts[:, 1].max() + 20)

                    qr_crop = screenshot.crop((x_min, y_min, x_max, y_max))
                    on_qr(qr_crop)
                    qr_sent = True
                    on_status(f"请使用手机扫描 {platform_name} 登录二维码...")
            except Exception:
                pass

        time.sleep(2)

    on_status("⚠️ 游戏登录扫码超时")
    return False
