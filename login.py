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
                pass  # transient error, keep polling

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
