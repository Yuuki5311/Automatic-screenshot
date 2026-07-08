#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— 主入口。

流程：
    1. 浏览器（Selenium）：登录 → 搜索王者荣耀 → 点击秒玩
    2. 等待桌面客户端启动游戏
    3. pyautogui + OpenCV：游戏内导航 → 全屏截图

使用方法:
    python main.py

前置条件:
    1. Chrome + ChromeDriver
    2. GamerUFO 桌面客户端
    3. templates/ 目录中放入按钮模板图
    4. macOS: 终端需「辅助功能」和「屏幕录制」权限
"""

import os
import time
import sys

from config import (
    BROWSER_WIDTH, BROWSER_HEIGHT,
    TEMPLATES_DIR, SCREENSHOTS_DIR,
    PAGE_LOAD_WAIT, GAME_LAUNCH_WAIT,
)
from logger import setup_logger, get_logger
from browser import create_browser
from login import login
from game_launcher import launch_game
from navigator import Navigator
from screenshotter import Screenshotter
from popup_monitor import PopupMonitor

log = get_logger()


# ---------------------------------------------------------------------------
# 截图任务定义
# ---------------------------------------------------------------------------
# 头像搜索区域: 左上 1/4 屏幕 (物理像素)，避免点到下方好友头像
# 在 navigator 初始化后设置
AVATAR_BOUNDS = None      # 运行时计算
NOBILITY_BOUNDS = None    # 运行时计算
ENTER_GAME_BOUNDS = None  # 运行时计算，下半屏


# 任务格式: (名称, 点击序列, 返回次数: 0/1/2)
SCREENSHOT_TASKS = [
    # ---- 个人主页（连续，不返回） ----
    ("主页", [
        ("avatar.png", "点击左上角头像", AVATAR_BOUNDS),
        ("tab_home.png", "点击主页标签"),
    ], 0),
    ("英雄", [
        ("tab_hero.png", "点击英雄标签"),
    ], 0),
    ("万象图鉴首页", [
        ("tab_illustrated.png", "点击图鉴标签"),
        ("universal_illustrated.png", "点击万象图鉴"),
    ], 0),
    ("万象图鉴-灵宝", [
        ("lingbao.png", "点击灵宝"),
    ], 1),
    ("皮肤图鉴", [
        ("skin_illustrated.png", ""),
    ], 1),

    # ---- 商城 ----
    ("积分夺宝", [
        ("shop_icon.png", "点击商城"),
        ("lottery_tab.png", "点击夺宝"),
        ("points_lottery.png", "点击积分夺宝"),
    ], 2),

    # ---- 定制 ----
    ("天幕", [
        ("customize_icon.png", "点击定制"),
        ("skin_customize.png", "点击皮肤定制"),
        ("my_tab.png", "点击我的"),
        ("sky_curtain.png", "点击天幕"),
    ], 1),
    ("小兵", [
        ("minion.png", "点击小兵"),
    ], 1),
    ("个性戳戳", [
        ("customize_icon.png", "点击定制"),
        ("personal_customize.png", "点击个性定制"),
        ("poke.png", "点击个性戳戳"),
    ], 1),

    # ---- 贵族 ----
    ("贵族", [
        ("nobility_icon.png", "点击贵族图标", NOBILITY_BOUNDS),
    ], 1),
]


# ---------------------------------------------------------------------------
# 辅助函数
# ---------------------------------------------------------------------------

def go_home(nav: Navigator) -> None:
    log.info("返回...")
    nav.find_and_click("back_arrow.png", timeout=3)
    time.sleep(PAGE_LOAD_WAIT)


def _recover_game(nav: Navigator) -> bool:
    """游戏重启后恢复：点击进入游戏 → 等待主界面 → 清理弹窗。

    Returns:
        True 表示成功恢复到主界面。
    """
    log.info("等待进入游戏按钮...")
    if not nav.find_and_click("enter_game.png", timeout=60, bounds=ENTER_GAME_BOUNDS):
        log.error("未检测到进入游戏按钮")
        return False
    time.sleep(2)
    log.info("等待进入主界面 (最多 90 秒)...")
    if not nav.wait_for_template("avatar.png", timeout=90):
        log.error("未检测到主界面")
        return False
    log.info("已重新进入主界面")
    _clear_all_popups(nav, detect_timeout=5)
    return True


def _clear_all_popups(nav: Navigator, max_rounds: int = 5, detect_timeout: int = 3):
    """循环清理弹窗：检测到弹窗 → 等2秒动画 → 关闭 → 等3秒复查。

    Args:
        max_rounds: 最大清理轮数。
        detect_timeout: 每轮检测弹窗的超时时间（秒）。
    """
    for _ in range(max_rounds):
        if nav.wait_for_template("popup_close.png", timeout=detect_timeout):
            log.info("检测到弹窗，2秒后关闭...")
            time.sleep(2)
            nav.find_and_click("popup_close.png", timeout=3)
            log.info("弹窗已关闭，3秒后复查...")
            time.sleep(3)
        else:
            break
    else:
        log.warning(f"弹窗清理达到上限 ({max_rounds} 轮)")


def run_screenshot_flow(nav: Navigator, shot: Screenshotter, monitor=None):
    total = len(SCREENSHOT_TASKS)
    success = 0

    if monitor:
        monitor.pause()

    while True:
        restart_needed = False

        for idx, task in enumerate(SCREENSHOT_TASKS, 1):
            name, clicks, back_count = task
            log.info(f"[{idx}/{total}] 目标: {name}")

            all_ok = True
            for item in clicks:
                if len(item) == 3:
                    template, desc, bounds = item
                else:
                    template, desc = item
                    bounds = None

                log.debug(f"  → {desc} ({template})")
                if not nav.find_and_click(template, bounds=bounds):
                    log.warning(f"找不到 {template}，跳过 {name}")
                    all_ok = False
                    break

            if all_ok:
                # 贵族：点击图标后解锁监控扫描弹窗
                if name == "贵族" and monitor:
                    monitor.resume()
                    time.sleep(3)
                    monitor.pause()

                time.sleep(PAGE_LOAD_WAIT)
                shot.take(name)
                success += 1
                log.info(f"已截图: {name}")
                # 返回
                for _ in range(back_count):
                    go_home(nav)
            else:
                log.error(f"截图失败: {name}")

                # 检测游戏重启：下半屏搜索 enter_game.png
                if nav.find_and_click("enter_game.png", timeout=5, bounds=ENTER_GAME_BOUNDS):
                    log.warning("检测到游戏重启，等待恢复...")
                    if _recover_game(nav):
                        restart_needed = True
                        break
                    else:
                        log.error("游戏恢复失败")

            # 过渡点：解锁监控3秒，有弹窗则关，无则过
            if all_ok and name in ("皮肤图鉴", "积分夺宝", "个性戳戳"):
                if monitor:
                    monitor.resume()
                    time.sleep(3)
                    monitor.pause()

        if not restart_needed:
            break
        else:
            log.info("游戏已恢复，从头重新执行截图工作流...")
            success = 0
            if monitor:
                monitor.pause()

    log.info(f"完成: {success}/{total} 张截图成功")
    if success < total:
        log.warning(f"失败: {total - success} 张")


# ---------------------------------------------------------------------------
# 主函数
# ---------------------------------------------------------------------------

def main():
    setup_logger()

    log.info("王者荣耀云游戏自动截图工具")
    log.info("=" * 50)

    # ==================================================================
    # 阶段 1: 浏览器 — 登录 + 搜索 + 秒玩
    # ==================================================================
    log.info("[阶段 1/3] 浏览器 — 登录并搜索游戏")

    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)

    if not login(driver):
        log.error("登录失败")
        sys.exit(1)

    if not launch_game(driver):
        log.error("搜索/启动失败")
        sys.exit(1)

    log.info("[阶段 1/3] 已点击秒玩，等待游戏画面出现...")
    # 浏览器保持打开——云游戏会话绑定浏览器，关了游戏也会断

    # ==================================================================
    # 阶段 2: 游戏初始化 — 坐标点击方案
    # ==================================================================
    log.info("[阶段 2/3] 游戏初始化...")

    nav = Navigator(templates_dir=TEMPLATES_DIR)
    shot = Screenshotter(output_dir=os.path.join(SCREENSHOTS_DIR, "default"))

    import pyautogui

    # 计算头像搜索区域（左上 1/4 屏幕，避免点到好友列表头像）
    # 用物理像素坐标
    screen_w, screen_h = pyautogui.size()
    global AVATAR_BOUNDS, NOBILITY_BOUNDS, ENTER_GAME_BOUNDS
    AVATAR_BOUNDS = (0, 0, int(screen_w * nav._scale * 0.4), int(screen_h * nav._scale * 0.5))
    NOBILITY_BOUNDS = (0, 0, int(screen_w * nav._scale), int(screen_h * nav._scale * 0.5))
    ENTER_GAME_BOUNDS = (0, int(screen_h * nav._scale * 0.5), int(screen_w * nav._scale), int(screen_h * nav._scale * 0.5))

    # 将运行时计算的 bounds 写入任务列表（元组在定义时捕获了 None）
    for i, task in enumerate(SCREENSHOT_TASKS):
        name, clicks, back_count = task
        if name == "主页":
            SCREENSHOT_TASKS[i] = (name, [
                (clicks[0][0], clicks[0][1], AVATAR_BOUNDS),
                clicks[1],
            ], back_count)
        elif name == "贵族":
            SCREENSHOT_TASKS[i] = (name, [
                (clicks[0][0], clicks[0][1], NOBILITY_BOUNDS),
            ], back_count)

    # ---- 等待并关闭初始弹窗 ----
    log.info("等待游戏加载并关闭弹窗 (最多 60 秒)...")
    if not nav.find_and_click("after_play_popup.png", timeout=60):
        log.warning("未检测到弹窗，跳过")
    time.sleep(2)

    # ---- 点击进入游戏 + 等待主界面 ----
    if not _recover_game(nav):
        log.warning("未能进入主界面，尝试继续执行")

    log.info("[阶段 2/3] 游戏已就绪")

    # ==================================================================
    # 阶段 3: 游戏内导航截图（弹窗由异步监控处理）
    # ==================================================================
    log.info("[阶段 3/3] 游戏内导航与截图")

    # 进入游戏后清理弹窗
    log.info("进入游戏后清理弹窗...")
    _clear_all_popups(nav, detect_timeout=10)

    # 启动异步弹窗监控，截图流程中只在过渡点放行
    monitor = PopupMonitor(navigator=nav)
    monitor.start()

    try:
        run_screenshot_flow(nav, shot, monitor)
    except KeyboardInterrupt:
        log.warning("用户中断")
    except Exception as e:
        log.error(f"异常: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        monitor.stop()


if __name__ == "__main__":
    main()
