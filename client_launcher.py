"""在 GamerUFO 桌面客户端中登录、搜索并启动王者荣耀。

全流程 pyautogui + OpenCV 模板匹配。
登录部分自动打开登录弹窗和选择 QQ，密码填写由用户手动完成。
"""

import subprocess
import time
import pyautogui

from navigator import Navigator
from config import GAME_LAUNCH_WAIT


def launch_in_client(nav: Navigator) -> bool:
    """在 GamerUFO 客户端中登录并启动王者荣耀。

    流程：
        1. 打开客户端
        2. 点击登录按钮
        3. 点击 QQ 登录选项
        4. 用户手动完成密码和验证码 → 按回车
        5. 搜索王者荣耀 → 秒玩 → 等待游戏加载

    Args:
        nav: 原生 Navigator 实例。

    Returns:
        bool: 启动成功返回 True。
    """
    print("=" * 50)
    print("[客户端] 正在启动 GamerUFO...")

    # ------------------------------------------------------------------
    # 1. 打开客户端
    # ------------------------------------------------------------------
    subprocess.run(["open", "-a", "GamerUFO"], check=True)
    print("[客户端] GamerUFO 已启动")
    time.sleep(5)

    # ------------------------------------------------------------------
    # 2. 点击登录按钮
    # ------------------------------------------------------------------
    if not nav.find_and_click("client_login_btn.png", timeout=10):
        print("[错误] 找不到登录按钮")
        return False
    time.sleep(3)

    # ------------------------------------------------------------------
    # 3. 选择 QQ 登录
    # ------------------------------------------------------------------
    if not nav.find_and_click("client_qq_login.png", timeout=10):
        print("[错误] 找不到 QQ 登录选项")
        return False
    time.sleep(2)

    # ------------------------------------------------------------------
    # 4. 用户手动完成密码登录（含可能的验证码）
    # ------------------------------------------------------------------
    print("\n" + "=" * 50)
    print("[登录] 请在客户端中手动完成 QQ 密码登录")
    print("[登录] 登录成功后，回到终端按回车继续...")
    print("=" * 50)
    input()

    # 登录后等待页面刷新
    time.sleep(3)

    # ------------------------------------------------------------------
    # 5. 搜索王者荣耀
    # ------------------------------------------------------------------
    if not nav.find_and_click("client_search.png", timeout=10):
        print("[错误] 找不到搜索栏")
        return False

    time.sleep(0.5)
    pyautogui.hotkey("command", "a")
    pyautogui.press("backspace")
    pyautogui.write("王者荣耀", interval=0.1)
    print("[客户端] 已在搜索栏输入'王者荣耀'")
    time.sleep(2)

    # ------------------------------------------------------------------
    # 6. 点击秒玩
    # ------------------------------------------------------------------
    if not nav.find_and_click("client_play.png", timeout=10):
        print("[错误] 找不到'秒玩'按钮")
        return False

    print("[客户端] 已点击'秒玩'")

    # ------------------------------------------------------------------
    # 7. 等待游戏加载
    # ------------------------------------------------------------------
    print(f"[客户端] 等待游戏加载 ({GAME_LAUNCH_WAIT} 秒)...")
    time.sleep(GAME_LAUNCH_WAIT)

    print("[客户端] ✅ 游戏启动流程完成")
    return True
