"""在 gamer.qq.com 中搜索王者荣耀并启动。"""

import time

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import GAME_LAUNCH_WAIT, PAGE_LOAD_WAIT
from logger import get_logger

log = get_logger()


def switch_to_new_tab(
    driver: WebDriver,
    original_handle: str,
    timeout: float = GAME_LAUNCH_WAIT,
) -> bool:
    """等待秒玩打开的新标签页并切换过去。

    云游戏在第二个标签页运行；若 WebDriver 仍停在先锋首页标签，
    后续截图/点击会把浏览器焦点拉回第一个标签页。

    Args:
        driver: Selenium WebDriver。
        original_handle: 点击秒玩前的 window handle。
        timeout: 等待新标签出现的最长时间（秒）。

    Returns:
        bool: 成功切换到新标签返回 True，超时返回 False。
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        new_handles = [h for h in driver.window_handles if h != original_handle]
        if new_handles:
            target = new_handles[-1]
            driver.switch_to.window(target)
            try:
                url = driver.current_url
            except Exception:
                url = "(unknown)"
            log.info(
                f"已切换到云游戏标签页 (handles={len(driver.window_handles)}, url={url})"
            )
            return True
        time.sleep(0.5)

    log.error(
        f"超时未出现新标签页（仍为 {len(driver.window_handles)} 个）"
    )
    return False


def _dismiss_popups(driver: WebDriver) -> None:
    """关闭登录后可能出现的弹窗。"""
    for sel in [
        "img.svip-tip-img",
        "img.svip-tip-img + *",
        "img.svip-tip-img ~ *",
    ]:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, sel)
            if elem.is_displayed():
                driver.execute_script("arguments[0].click();", elem)
                time.sleep(1)
                return
        except Exception:
            continue

    for sel in [
        "img[class*='close']",
        "span[class*='close']",
        "div[class*='close']",
        "[class*='dialog'] [class*='close']",
        "[class*='modal'] [class*='close']",
    ]:
        try:
            for elem in driver.find_elements(By.CSS_SELECTOR, sel):
                if elem.is_displayed():
                    driver.execute_script("arguments[0].click();", elem)
                    time.sleep(1)
                    return
        except Exception:
            continue


def launch_game(driver: WebDriver) -> bool:
    """在 gamer.qq.com 中搜索王者荣耀并启动。

    登录后执行：
        1. 关闭弹窗
        2. 搜索栏输入"王者荣耀"
        3. 精确找到王者荣耀卡片的"秒玩"按钮并点击
    """
    print("=" * 50)
    print("[启动] 正在搜索并启动王者荣耀...")

    # ------------------------------------------------------------------
    # 1. 关闭弹窗
    # ------------------------------------------------------------------
    time.sleep(PAGE_LOAD_WAIT)
    _dismiss_popups(driver)

    # ------------------------------------------------------------------
    # 2. 搜索"王者荣耀"
    # ------------------------------------------------------------------
    try:
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.form-style"))
        )
        driver.execute_script("arguments[0].click();", search_input)
        time.sleep(0.5)
        search_input.clear()
        search_input.send_keys("王者荣耀")
        print("[启动] 已在搜索栏输入'王者荣耀'")
        time.sleep(3)
    except Exception as e:
        print(f"[错误] 找不到搜索栏: {e}")
        driver.save_screenshot("debug_search.png")
        return False

    # ------------------------------------------------------------------
    # 3. 精确找到王者荣耀卡片的"秒玩"按钮
    #    关键：不能点轮播横幅里的秒玩，必须点游戏卡片里的
    # ------------------------------------------------------------------
    try:
        # 找到王者荣耀的游戏卡片图
        game_img = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((
                By.XPATH,
                "//img[@alt='王者荣耀-支持iOS登录-云游戏']"
            ))
        )

        # 从图片向上找到 flex-4-num1 游戏卡片容器
        container = driver.execute_script("""
            let el = arguments[0];
            for (let i = 0; i < 10; i++) {
                el = el.parentElement;
                if (!el) return null;
                let cls = el.className || '';
                if (cls.includes('flex-4-num1')) return el;
            }
            return null;
        """, game_img)

        if not container:
            raise Exception("找不到王者荣耀的游戏卡片容器")

        # 在容器内找到"秒玩"
        play_btn = container.find_element(By.XPATH, ".//*[text()='秒玩']")

        if not play_btn.is_displayed():
            raise Exception("秒玩按钮不可见")

        original_handle = driver.current_window_handle
        driver.execute_script("arguments[0].click();", play_btn)
        print("[启动] 已点击【王者荣耀】的'秒玩'按钮")
        log.info(f"已点击秒玩，原标签 handle={original_handle}")

    except Exception as e:
        print(f"[错误] 找不到王者荣耀的秒玩按钮: {e}")
        driver.save_screenshot("debug_play_btn.png")
        return False

    # ------------------------------------------------------------------
    # 4. 等待云游戏新标签页并切换（秒玩会打开第二个标签）
    # ------------------------------------------------------------------
    print(f"[启动] 等待云游戏新标签页 (最多 {GAME_LAUNCH_WAIT} 秒)...")
    if not switch_to_new_tab(driver, original_handle, timeout=GAME_LAUNCH_WAIT):
        print("[错误] 未检测到云游戏新标签页，WebDriver 仍停在先锋首页")
        driver.save_screenshot("debug_no_game_tab.png")
        return False

    # 新标签已打开，再稍等画面加载
    time.sleep(PAGE_LOAD_WAIT)

    print("[启动] ✅ 游戏启动流程完成（已切换到云游戏标签页）")
    return True
