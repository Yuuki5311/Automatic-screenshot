#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— 主入口。

使用方法:
    python main.py

前置条件:
    1. 已安装 Chrome 浏览器
    2. 已安装 ChromeDriver 并加入 PATH
    3. 已在 templates/ 目录中放入按钮模板图
"""

import time
import sys

from selenium import webdriver
from selenium.webdriver.chrome.options import Options

from config import (
    BROWSER_WIDTH,
    BROWSER_HEIGHT,
    TEMPLATES_DIR,
    SCREENSHOTS_DIR,
    PAGE_LOAD_WAIT,
)
from login import login
from game_launcher import launch_game
from navigator import Navigator
from screenshotter import Screenshotter


# ---------------------------------------------------------------------------
# 截图任务定义
# 每个任务: (截图名称, [(模板名, 描述), ...])
# 列表表示点击序列：依次点击模板后截图
# ---------------------------------------------------------------------------
SCREENSHOT_TASKS = [
    # ====================
    # 1. 个人主页相关
    # ====================
    ("主页", [
        ("avatar.png", "点击左上角头像"),
        ("tab_home.png", "点击主页标签"),
    ]),
    ("英雄", [
        ("tab_hero.png", "点击英雄标签"),
    ]),
    ("万象图鉴首页", [
        ("tab_illustrated.png", "点击图鉴标签"),
        ("universal_illustrated.png", "点击万象图鉴"),
    ]),
    ("万象图鉴-灵宝", [
        ("lingbao.png", "点击灵宝"),
    ]),
    ("皮肤图鉴", [
        ("skin_illustrated.png", "点击皮肤图鉴"),
    ]),

    # ====================
    # 2. 商城 - 夺宝
    # ====================
    ("积分夺宝", [
        ("shop_icon.png", "点击商城"),
        ("lottery_tab.png", "点击夺宝"),
        ("points_lottery.png", "点击积分夺宝"),
    ]),

    # ====================
    # 3. 定制
    # ====================
    ("天幕", [
        ("customize_icon.png", "点击定制"),
        ("skin_customize.png", "点击皮肤定制"),
        ("my_tab.png", "点击我的"),
        ("sky_curtain.png", "点击天幕"),
    ]),
    ("小兵", [
        ("minion.png", "点击小兵"),
    ]),
    ("个性戳戳", [
        ("customize_icon.png", "点击定制"),
        ("personal_customize.png", "点击个性定制"),
        ("poke.png", "点击个性戳戳"),
    ]),

    # ====================
    # 4. 贵族
    # ====================
    ("贵族", [
        ("nobility_icon.png", "点击贵族图标"),
    ]),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def go_home(nav: Navigator) -> None:
    """尝试返回游戏主界面。"""
    print("[导航] 返回主界面...")
    # 尝试多次按 ESC 或点击空白区域关闭弹窗
    nav.find_and_click("close_button.png", timeout=3) or \
        nav.find_and_click("back_arrow.png", timeout=3)
    time.sleep(PAGE_LOAD_WAIT)


def run_screenshot_flow(driver: webdriver.Chrome, nav: Navigator, shot: Screenshotter):
    """执行所有截图任务。"""
    total = len(SCREENSHOT_TASKS)
    success = 0

    for idx, (name, clicks) in enumerate(SCREENSHOT_TASKS, 1):
        print(f"\n{'─' * 40}")
        print(f"[{idx}/{total}] 目标: {name}")

        # 执行点击序列
        all_ok = True
        for template, desc in clicks:
            print(f"  → {desc} ({template})")
            if not nav.find_and_click(template):
                print(f"  ⚠️  跳过（找不到 {template})")
                all_ok = False
                break

        # 截图
        if all_ok:
            time.sleep(PAGE_LOAD_WAIT)
            shot.take(name)
            success += 1
        else:
            print(f"  ❌ 截图失败: {name}")

        # 返回主界面（为下一个截图任务做准备）
        go_home(nav)

    print(f"\n{'=' * 50}")
    print(f"完成: {success}/{total} 张截图成功")
    if success < total:
        print(f"失败: {total - success} 张")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    """主入口。"""
    print("王者荣耀云游戏自动截图工具")
    print("=" * 50)

    # 1. 初始化 Chrome
    print("[初始化] 启动 Chrome...")
    chrome_options = Options()
    chrome_options.add_argument(f"--window-size={BROWSER_WIDTH},{BROWSER_HEIGHT}")
    # 如果 Chrome 未在 PATH 中，可取消下一行注释并指定路径
    # chrome_options.binary_location = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

    driver = webdriver.Chrome(options=chrome_options)
    driver.set_window_size(BROWSER_WIDTH, BROWSER_HEIGHT)

    try:
        # 2. 登录
        if not login(driver):
            print("[错误] 登录失败，退出")
            sys.exit(1)

        # 3. 初始化 Navigator 和 Screenshotter
        nav = Navigator(driver, templates_dir=TEMPLATES_DIR)
        shot = Screenshotter(driver, output_dir=SCREENSHOTS_DIR)

        # 4. 启动游戏
        if not launch_game(driver, nav):
            print("[错误] 游戏启动失败，退出")
            sys.exit(1)

        # 5. 执行截图流程
        run_screenshot_flow(driver, nav, shot)

    except KeyboardInterrupt:
        print("\n[中断] 用户取消")
    except Exception as e:
        print(f"\n[异常] {e}")
        driver.save_screenshot("debug_crash.png")
        print("[调试] 已保存崩溃截图至 debug_crash.png")
        raise
    finally:
        print("\n[清理] 关闭浏览器...")
        driver.quit()


if __name__ == "__main__":
    main()
