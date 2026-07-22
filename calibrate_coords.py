#!/usr/bin/env python3
"""CSS 视口坐标采集工具。

在游戏内手动将鼠标移动到按钮位置，按回车记录坐标。
采集的坐标为浏览器 CSS 视口像素，存入 calibrated_coords.json。

使用方法:
    python calibrate_coords.py
"""

import json
import os
import sys
import time

import pyautogui

from browser import create_browser
from config import BROWSER_WIDTH, BROWSER_HEIGHT, CLOUD_GAMING_URL

COORDS_FILE = "calibrated_coords.json"

# (key, 说明, 所在页面提示) —— 覆盖工作流全部兜底坐标
TARGETS = [
    # ---- 登录界面 ----
    ("game_logout_btn", "退出登录按钮（右上角）", "登录界面"),
    ("game_wx_ios", "「与微信iOS好友玩」", "登录界面左半边"),
    ("game_wx_android", "「与微信安卓好友玩」", "登录界面左半边"),
    ("game_qq_ios", "「与QQ iOS好友玩」", "登录界面右半边"),
    ("game_qq_android", "「与QQ安卓好友玩」", "登录界面右半边"),
    ("game_login_other", "「登录其他账号」按钮", "登录相关弹窗底部"),
    ("enter_game", "「进入游戏」按钮", "登录成功后"),
    ("game_logout_confirm", "退出确认弹窗「确定」", "退出确认弹窗下方"),
    ("game_popup_confirm", "通用/云服务器确认弹窗「确定」", "确认弹窗下方"),
    # ---- 主界面 ----
    ("avatar", "左上角头像", "主界面"),
    ("nobility_icon", "贵族图标", "主界面上方"),
    ("shop_icon", "商城入口", "主界面右侧"),
    ("customize_icon", "定制入口", "主界面下方"),
    ("settings_icon", "设置齿轮", "主界面右上角"),
    ("back_arrow", "返回箭头", "任意子页面左上角"),
    # ---- 个人主页 ----
    ("tab_home", "【主页】标签", "个人主页顶部"),
    ("tab_hero", "【英雄】标签", "个人主页顶部"),
    ("tab_illustrated", "【图鉴】标签", "个人主页顶部"),
    # ---- 图鉴 ----
    ("universal_illustrated", "【万象图鉴】入口", "图鉴页"),
    ("lingbao", "【灵宝】入口", "万象图鉴页"),
    ("skin_illustrated", "【皮肤图鉴】入口", "图鉴页"),
    ("skin_treasure_wushuang", "【珍品无双】图标", "皮肤图鉴页"),
    ("skin_glory_collection", "【荣耀典藏】图标", "皮肤图鉴页"),
    ("skin_wushuang", "【无双】图标", "皮肤图鉴页"),
    ("skin_treasure_legend", "【珍品传说】图标", "皮肤图鉴页"),
    ("skin_legend", "【传说】图标", "皮肤图鉴页"),
    ("bag", "【背包】按钮", "主界面"),
    ("currency_bag", "【货币背包】按钮", "背包页右上角"),
    # ---- 商城 ----
    ("lottery_tab", "【夺宝】标签", "商城页"),
    ("points_lottery", "【积分夺宝】入口", "夺宝页"),
    # ---- 定制 ----
    ("skin_customize", "【皮肤定制】入口", "定制页"),
    ("minion", "【小兵】选项", "皮肤定制-我的"),
    ("personal_customize", "【个性定制】入口", "定制页"),
    ("poke", "【个性戳戳】入口", "个性定制页"),
    # ---- 设置 ----
    ("settings_logout", "设置页「退出登录」", "设置页下方"),
]

LEGACY_WARNING = """
⚠️  重要：旧桌面/屏幕坐标已作废！
    截图与点击已统一为浏览器 CSS 视口坐标系（目标见 config.BROWSER_WIDTH×HEIGHT）。
    请重新采集全部兜底坐标；超出视口的坐标会被拒绝。
"""


def load_existing() -> dict:
    if os.path.exists(COORDS_FILE):
        with open(COORDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_coords(coords: dict) -> None:
    with open(COORDS_FILE, "w", encoding="utf-8") as f:
        json.dump(coords, f, indent=2, ensure_ascii=False)


def get_viewport_origin(driver) -> tuple[int, int]:
    """返回 CSS 视口左上角在屏幕上的像素位置。"""
    try:
        screen_x = driver.execute_script("return window.screenX;")
        screen_y = driver.execute_script("return window.screenY;")
        chrome_height = driver.execute_script(
            "return window.outerHeight - window.innerHeight;"
        )
    except Exception as exc:
        raise RuntimeError(f"无法通过 Selenium 读取浏览器窗口位置: {exc}") from exc

    if screen_x is None or screen_y is None or chrome_height is None:
        raise RuntimeError(
            "浏览器未返回 window.screenX/screenY 或 chrome 高度，无法换算 CSS 坐标。"
        )

    origin_x = int(screen_x)
    origin_y = int(screen_y) + int(chrome_height)
    return origin_x, origin_y


def screen_to_css(driver, mouse_x: int, mouse_y: int) -> tuple[int, int]:
    origin_x, origin_y = get_viewport_origin(driver)
    return int(mouse_x) - origin_x, int(mouse_y) - origin_y


def verify_viewport(driver) -> tuple[int, int]:
    inner_w = driver.execute_script("return window.innerWidth;")
    inner_h = driver.execute_script("return window.innerHeight;")
    print(f"浏览器 CSS 视口: {inner_w} × {inner_h}（目标 {BROWSER_WIDTH} × {BROWSER_HEIGHT}）")
    if inner_w is None or inner_h is None:
        raise RuntimeError("无法读取 window.innerWidth/innerHeight。")
    if abs(int(inner_w) - BROWSER_WIDTH) > 20 or abs(int(inner_h) - BROWSER_HEIGHT) > 20:
        print(
            f"⚠️  视口尺寸与目标 {BROWSER_WIDTH}×{BROWSER_HEIGHT} 偏差较大，"
            "请确认显示器分辨率足够（脚本会尝试锁定视口，不再依赖最大化）。"
        )
    return int(inner_w), int(inner_h)


def launch_driver():
    print(f"正在启动浏览器（目标视口 {BROWSER_WIDTH}×{BROWSER_HEIGHT}）...")
    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
    try:
        driver.get(CLOUD_GAMING_URL)
        time.sleep(2)
    except Exception as exc:
        print(f"打开云游戏页面失败（可手动导航）: {exc}")
    return driver


def collect_targets(
    driver,
    existing: dict,
    merged: dict,
    *,
    force_all: bool,
    viewport_size: tuple[int, int],
) -> dict:
    """采集坐标；每成功一项即写入 merged 并落盘，便于中途取消。"""
    new_coords = {}
    total = len(TARGETS)
    vw, vh = viewport_size
    last_page = None

    for idx, (key, description, page) in enumerate(TARGETS, 1):
        if page != last_page:
            print()
            print(f"—— 请切换到: {page} ——")
            last_page = page

        print(f"[{idx}/{total}] {description} ({key})")

        if key in existing and not force_all:
            old = existing[key]
            print(f"    已有坐标 (CSS): ({old[0]}, {old[1]})")
            choice = input("    [回车]保留  [r]重新采集  [s]跳过: ").strip().lower()
            if choice == "s":
                continue
            if choice != "r":
                new_coords[key] = [int(old[0]), int(old[1])]
                merged[key] = new_coords[key]
                save_coords(merged)
                continue

        while True:
            input("    将鼠标移到目标按钮中心，按回车记录...")
            mouse_x, mouse_y = pyautogui.position()
            css_x, css_y = screen_to_css(driver, mouse_x, mouse_y)

            if css_x < 0 or css_y < 0 or css_x >= vw or css_y >= vh:
                print(
                    f"    ❌ 坐标 ({css_x}, {css_y}) 超出视口 0..{vw-1} × 0..{vh-1}，请重试"
                )
                retry = input("    [回车]重试  [s]跳过此项: ").strip().lower()
                if retry == "s":
                    break
                continue

            new_coords[key] = [css_x, css_y]
            merged[key] = new_coords[key]
            save_coords(merged)
            print(f"    ✅ 已记录 CSS 坐标: ({css_x}, {css_y})")
            break

    return new_coords


def main() -> int:
    print("=" * 50)
    print("  CSS 视口坐标采集工具（全部兜底项）")
    print("=" * 50)
    print(LEGACY_WARNING)

    existing = load_existing()
    merged = dict(existing)
    driver = None
    new_coords = {}

    try:
        print("使用前请确保：")
        print(f"  1. 浏览器 CSS 视口为 {BROWSER_WIDTH}×{BROWSER_HEIGHT}")
        print("  2. 已登录并进入对应游戏页面（工具会按分组提示切换）")
        print("  3. 标定过程中不要移动或缩放浏览器窗口")
        print()
        mode = input(
            "[a] 强制重新采集全部  [回车] 逐项确认保留/重采: "
        ).strip().lower()
        force_all = mode == "a"

        if force_all:
            print("将强制重采全部坐标（旧值仅作对照，不自动保留）。")
            clear = input("是否先清空 calibrated_coords.json？ [y/N]: ").strip().lower()
            if clear == "y":
                merged = {}
                save_coords(merged)
                existing = {}
                print("已清空，开始全新采集。")

        print()
        choice = input("[回车] 启动浏览器标定  [n] 我已打开游戏但仍需本工具会话: ").strip().lower()
        if choice == "n":
            print()
            print(f"请确认 Edge 中游戏画面 CSS 视口已为 {BROWSER_WIDTH}×{BROWSER_HEIGHT}。")
            print("本工具仍需 Selenium 会话读取 window.screenX/Y 以换算 CSS 坐标。")
            print("将启动浏览器窗口；请在新窗口中进入相同页面后继续标定。")
            print()

        driver = launch_driver()
        viewport_size = verify_viewport(driver)

        origin_x, origin_y = get_viewport_origin(driver)
        print(f"视口屏幕原点: ({origin_x}, {origin_y})")
        print()
        print("每轮: 移动鼠标到目标中心 → 按回车记录 CSS 坐标")
        print("可按 Ctrl+C 中途退出（已采项会保存）。")
        print()

        input("准备好后按回车开始采集...")
        new_coords = collect_targets(
            driver, existing, merged, force_all=force_all, viewport_size=viewport_size
        )

        print()
        print("=" * 50)
        print(f"本轮写入 {len(new_coords)} 项，文件共 {len(merged)} 项 → {COORDS_FILE}:")
        for key, coords in merged.items():
            print(f"  {key}: ({coords[0]}, {coords[1]})")
        print("=" * 50)
        return 0

    except KeyboardInterrupt:
        print("\n\n已取消。")
        if new_coords or merged != existing:
            save_coords(merged)
            print(f"已保存已采集的部分坐标到 {COORDS_FILE}。")
        return 130
    except RuntimeError as exc:
        print(f"\n错误: {exc}", file=sys.stderr)
        if new_coords or merged != existing:
            save_coords(merged)
            print(f"已保存已采集的部分坐标到 {COORDS_FILE}。")
        return 1
    finally:
        if driver is not None:
            try:
                input("\n按回车关闭浏览器...")
            except KeyboardInterrupt:
                pass
            driver.quit()


if __name__ == "__main__":
    sys.exit(main())
