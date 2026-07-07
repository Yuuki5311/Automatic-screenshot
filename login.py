"""QQ 账号登录腾讯先锋云游戏模块。"""

import time
from getpass import getpass

from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from config import CLOUD_GAMING_URL, PAGE_LOAD_WAIT, QQ_NUMBER


def login(driver: WebDriver) -> bool:
    """在腾讯先锋云游戏中完成 QQ 登录。

    Args:
        driver: 已初始化的 Chrome WebDriver 实例。

    Returns:
        bool: 登录成功返回 True，失败返回 False。
    """
    print("=" * 50)
    print("[登录] 开始 QQ 登录流程")

    # ------------------------------------------------------------------
    # 1. 打开腾讯先锋云游戏首页
    # ------------------------------------------------------------------
    print(f"[登录] 打开: {CLOUD_GAMING_URL}")
    driver.get(CLOUD_GAMING_URL)
    time.sleep(PAGE_LOAD_WAIT)

    # ------------------------------------------------------------------
    # 2. 点击页面上的"登录"按钮
    # ------------------------------------------------------------------
    try:
        # 腾讯先锋登录按钮可能有多种文字形式
        login_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(), '登录') or contains(text(), '登錄') "
                "or contains(@class, 'login')]"
            ))
        )
        login_button.click()
        print("[登录] 已点击登录按钮")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception as e:
        print(f"[错误] 找不到登录按钮: {e}")
        print("[提示] 请确认 CLOUD_GAMING_URL 是否正确，或页面结构是否变化")
        return False

    # ------------------------------------------------------------------
    # 3. 选择 QQ 登录方式 (可能需要在弹窗中切换)
    # ------------------------------------------------------------------
    try:
        qq_tab = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((
                By.XPATH,
                "//*[contains(text(), 'QQ') or contains(@title, 'QQ') "
                "or contains(@class, 'qq')]"
            ))
        )
        qq_tab.click()
        print("[登录] 已选择 QQ 登录")
        time.sleep(PAGE_LOAD_WAIT)
    except Exception:
        print("[登录] 未找到 QQ 登录切换标签（可能默认已是 QQ 登录）")

    # ------------------------------------------------------------------
    # 4. 获取 QQ 账号
    # ------------------------------------------------------------------
    qq_number = QQ_NUMBER
    if not qq_number:
        qq_number = input("[登录] 请输入 QQ 号: ").strip()
    else:
        print(f"[登录] 使用配置的 QQ 号: {qq_number}")

    # ------------------------------------------------------------------
    # 5. 输入 QQ 密码
    # ------------------------------------------------------------------
    qq_password = getpass("[登录] 请输入 QQ 密码 (输入不可见): ")

    # ------------------------------------------------------------------
    # 6. 填写登录表单
    # ------------------------------------------------------------------
    try:
        # QQ 登录页通常在 iframe 中
        # 先尝试直接查找，再尝试切换 iframe
        username_input = None
        password_input = None

        # 尝试在主页面查找输入框
        try:
            username_input = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((
                    By.XPATH,
                    "//input[@type='text' or @name='u' or @name='account' "
                    "or @placeholder='QQ号' or @placeholder='QQ号码']"
                ))
            )
        except Exception:
            # 尝试切换到 iframe
            iframes = driver.find_elements(By.TAG_NAME, "iframe")
            for iframe in iframes:
                driver.switch_to.frame(iframe)
                try:
                    username_input = driver.find_element(
                        By.XPATH,
                        "//input[@type='text' or @name='u' or @name='account']"
                    )
                    if username_input:
                        break
                except Exception:
                    driver.switch_to.default_content()

        if not username_input:
            print("[错误] 找不到 QQ 号输入框")
            driver.save_screenshot("debug_login.png")
            print("[调试] 已保存登录页面截图至 debug_login.png")
            return False

        username_input.clear()
        username_input.send_keys(qq_number)
        print("[登录] 已填入 QQ 号")

        # 密码输入框
        password_input = driver.find_element(
            By.XPATH,
            "//input[@type='password' or @name='p' or @name='password']"
        )
        password_input.clear()
        password_input.send_keys(qq_password)
        print("[登录] 已填入密码")

    except Exception as e:
        print(f"[错误] 填写登录表单失败: {e}")
        driver.save_screenshot("debug_login.png")
        return False

    # ------------------------------------------------------------------
    # 7. 点击登录提交按钮
    # ------------------------------------------------------------------
    try:
        submit_btn = driver.find_element(
            By.XPATH,
            "//*[@type='submit' or contains(@class, 'submit') "
            "or contains(@id, 'login') or contains(text(), '登录')]"
        )
        submit_btn.click()
        print("[登录] 已提交登录")
    except Exception as e:
        print(f"[错误] 找不到登录提交按钮: {e}")
        return False

    # ------------------------------------------------------------------
    # 8. 等待登录完成
    # ------------------------------------------------------------------
    time.sleep(5)
    driver.switch_to.default_content()  # 切回主页面

    # 检查是否需要验证码
    page_source = driver.page_source
    if "验证码" in page_source or "captcha" in page_source.lower():
        print("[登录] ⚠️  检测到验证码，请手动完成验证...")
        input("[登录] 完成验证码后按回车继续...")

    print("[登录] ✅ QQ 登录流程完成")
    return True
