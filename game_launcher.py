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
