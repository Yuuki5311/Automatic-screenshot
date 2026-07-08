"""QQ 账号登录腾讯先锋云游戏模块。

适配 gamer.qq.com 的登录流程：
    弹出式登录选择 → QQ OAuth iframe → 密码登录
"""

import time
from getpass import getpass

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CLOUD_GAMING_URL, PAGE_LOAD_WAIT


def _solve_captcha(driver: WebDriver) -> bool:
    """检测并处理验证码。"""
    try:
        verify_area = driver.find_element(By.ID, "verifyArea")
        if not verify_area.is_displayed():
            return True
    except Exception:
        return True

    print("[登录] ⚠️  检测到验证码，正在截图...")
    driver.save_screenshot("debug_captcha.png")
    print("[登录] 验证码截图已保存至 debug_captcha.png，请查看")

    captcha_code = input("[登录] 请输入验证码: ").strip()
    if not captcha_code:
        print("[登录] 未输入验证码")
        return False

    try:
        vc_input = driver.find_element(By.ID, "verifycode")
        vc_input.clear()
        vc_input.send_keys(captcha_code)
        print("[登录] 已填入验证码")
        return True
    except Exception as e:
        print(f"[错误] 填写验证码失败: {e}")
        return False


def _handle_authorization(driver: WebDriver) -> None:
    """在外层 iframe 中处理授权页面。"""
    time.sleep(3)

    try:
        if "授权" not in driver.page_source:
            return

        print("[登录] 处理授权页面...")

        try:
            select_all = driver.find_element(By.ID, "select_all")
            driver.execute_script("arguments[0].click();", select_all)
            time.sleep(0.5)
        except Exception:
            pass

        for xpath in [
            "//*[contains(text(), '授权') and contains(text(), '登录')]",
            "//button[contains(text(), '授权')]",
            "//*[@class='btn' or contains(@class, 'button')][contains(text(), '授权')]",
            "//input[@type='submit' and contains(@value, '授权')]",
            "//*[@id='login']",
        ]:
            try:
                btn = WebDriverWait(driver, 3).until(
                    EC.element_to_be_clickable((By.XPATH, xpath))
                )
                btn.click()
                print("[登录] 已点击授权按钮")
                return
            except Exception:
                continue

        print("[登录] ⚠️  未找到授权按钮，可能需要手动授权")
        input("[登录] 完成授权后按回车继续...")

    except Exception as e:
        print(f"[登录] 授权流程异常: {e}")


def login(driver: WebDriver) -> bool:
    """在腾讯先锋 gamer.qq.com 完成 QQ 登录。

    流程：
        1. 打开 gamer.qq.com
        2. 点击 #user_login 打开登录弹窗
        3. 点击 img.qq-login 选择 QQ 登录
        4. 切换到 graph.qq.com iframe
        5. 切换到内层 ptlogin_iframe
        6. 切换到密码登录模式
        7. 填写 QQ 号 + 密码 → 提交
        8. 如有验证码则手动输入
        9. 处理授权确认
        10. 切回主页面

    Args:
        driver: 已初始化的 Chrome WebDriver 实例。

    Returns:
        bool: 登录成功返回 True，失败返回 False。
    """
    print("=" * 50)
    print("[登录] 开始 QQ 登录流程 (gamer.qq.com)")

    # ------------------------------------------------------------------
    # 1. 打开 gamer.qq.com
    # ------------------------------------------------------------------
    print(f"[登录] 打开: {CLOUD_GAMING_URL}")
    driver.get(CLOUD_GAMING_URL)
    time.sleep(PAGE_LOAD_WAIT * 2)  # gamer.qq.com 加载较慢

    # ------------------------------------------------------------------
    # 2. 点击登录按钮 (#user_login)，打开登录弹窗
    # ------------------------------------------------------------------
    try:
        login_btn = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.ID, "user_login"))
        )
        login_btn.click()
        print("[登录] 已点击登录按钮，弹窗已打开")
        time.sleep(3)
    except Exception as e:
        print(f"[错误] 找不到登录按钮: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 3. 点击 QQ 登录选项
    # ------------------------------------------------------------------
    try:
        qq_login = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "img.qq-login"))
        )
        qq_login.click()
        print("[登录] 已选择 QQ 登录")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        print(f"[错误] 找不到 QQ 登录选项: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 4. 切换到 QQ OAuth iframe (graph.qq.com)
    # ------------------------------------------------------------------
    try:
        outer_iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "iframe"))
        )
        driver.switch_to.frame(outer_iframe)
        print("[登录] 已切换到 QQ OAuth iframe")
        time.sleep(2)
    except Exception as e:
        print(f"[错误] 找不到 QQ OAuth iframe: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 5. 切换到内层 ptlogin_iframe
    # ------------------------------------------------------------------
    try:
        ptlogin_iframe = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "ptlogin_iframe"))
        )
        driver.switch_to.frame(ptlogin_iframe)
        print("[登录] 已切换到登录表单 iframe")
        time.sleep(2)
    except Exception as e:
        print(f"[错误] 找不到 ptlogin_iframe: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 6. 切换到"密码登录"模式
    # ------------------------------------------------------------------
    try:
        switcher = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.ID, "switcher_plogin"))
        )
        switcher.click()
        print("[登录] 已切换到密码登录模式")
        time.sleep(2)
    except Exception as e:
        print(f"[错误] 找不到密码登录切换按钮: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 7. 获取 QQ 账号（交互式输入）
    # ------------------------------------------------------------------
    qq_number = input("[登录] 请输入 QQ 号: ").strip()
    if not qq_number:
        print("[错误] QQ 号不能为空")
        return False

    # ------------------------------------------------------------------
    # 8. 输入 QQ 密码
    # ------------------------------------------------------------------
    qq_password = getpass("[登录] 请输入 QQ 密码 (输入不可见): ")

    # ------------------------------------------------------------------
    # 9. 填写登录表单
    # ------------------------------------------------------------------
    try:
        username_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.ID, "u"))
        )
        username_input.clear()
        username_input.send_keys(qq_number)
        print("[登录] 已填入 QQ 号")

        password_input = driver.find_element(By.ID, "p")
        password_input.clear()
        password_input.send_keys(qq_password)
        print("[登录] 已填入密码")

    except Exception as e:
        print(f"[错误] 填写登录表单失败: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 10. 提交登录（带验证码处理循环）
    # ------------------------------------------------------------------
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            submit_btn = driver.find_element(By.ID, "login_button")
            submit_btn.click()
            print(f"[登录] 已提交登录 (第 {attempt} 次)")
        except Exception as e:
            print(f"[错误] 找不到登录提交按钮: {e}")
            driver.save_screenshot("debug_login.png")
            return False

        time.sleep(3)

        # 检查错误提示
        try:
            err_m = driver.find_element(By.ID, "err_m")
            if err_m.is_displayed() and err_m.text.strip():
                print(f"[登录] 错误提示: {err_m.text}")

                if "验证码" in err_m.text or "验证" in err_m.text:
                    if not _solve_captcha(driver):
                        continue
                    continue
                elif "密码" in err_m.text or "帐号" in err_m.text or "账号" in err_m.text:
                    print("[错误] 账号或密码错误")
                    return False
                else:
                    continue
        except Exception:
            pass

        # 检查验证码输入框
        try:
            vc = driver.find_element(By.ID, "verifycode")
            if vc.is_displayed():
                print("[登录] 需要输入验证码")
                if not _solve_captcha(driver):
                    continue
                continue
        except Exception:
            pass

        # 没有错误，登录成功
        print("[登录] 登录提交成功")
        break
    else:
        print("[错误] 登录尝试次数已达上限")
        return False

    # ------------------------------------------------------------------
    # 11. 切回主页面（登录成功后 iframe 可能已自动关闭）
    # ------------------------------------------------------------------
    try:
        driver.switch_to.parent_frame()  # 从 ptlogin_iframe 回到 graph.qq.com
    except Exception:
        pass  # iframe 可能已经自动销毁

    # gamer.qq.com 登录成功后无授权环节，直接切回主页面
    driver.switch_to.default_content()
    time.sleep(PAGE_LOAD_WAIT)

    print("[登录] ✅ QQ 登录流程完成")
    return True
