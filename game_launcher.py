"""在 gamer.qq.com 中搜索王者荣耀并启动。"""

import time

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import GAME_LAUNCH_WAIT, PAGE_LOAD_WAIT


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

        driver.execute_script("arguments[0].click();", play_btn)
        print("[启动] 已点击【王者荣耀】的'秒玩'按钮")

    except Exception as e:
        print(f"[错误] 找不到王者荣耀的秒玩按钮: {e}")
        driver.save_screenshot("debug_play_btn.png")
        return False

    # ------------------------------------------------------------------
    # 4. 等待桌面客户端启动游戏
    # ------------------------------------------------------------------
    print(f"[启动] 等待桌面客户端启动游戏 ({GAME_LAUNCH_WAIT} 秒)...")
    time.sleep(GAME_LAUNCH_WAIT)

    print("[启动] ✅ 游戏启动流程完成")
    return True
