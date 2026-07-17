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

TARGETS = [
    ("avatar", "左上角头像（主界面）"),
    ("minion", "小兵按钮（皮肤定制-我的页面）"),
]

LEGACY_WARNING = """
⚠️  重要：calibrated_coords.json 中旧的桌面/屏幕坐标已作废！
    截图与点击已统一为浏览器 CSS 视口坐标系（约 1920×1080）。
    请在本工具中重新采集全部兜底坐标，旧值不可直接使用。
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


def verify_viewport(driver) -> None:
    inner_w = driver.execute_script("return window.innerWidth;")
    inner_h = driver.execute_script("return window.innerHeight;")
    print(f"浏览器 CSS 视口: {inner_w} × {inner_h}（目标 {BROWSER_WIDTH} × {BROWSER_HEIGHT}）")
    if inner_w is None or inner_h is None:
        raise RuntimeError("无法读取 window.innerWidth/innerHeight。")
    if abs(int(inner_w) - BROWSER_WIDTH) > 20 or abs(int(inner_h) - BROWSER_HEIGHT) > 20:
        print(
            f"⚠️  视口尺寸与目标 {BROWSER_WIDTH}×{BROWSER_HEIGHT} 偏差较大，"
            "请调整窗口或最大化后重试。"
        )


def launch_driver():
    print(f"正在启动浏览器（目标视口 {BROWSER_WIDTH}×{BROWSER_HEIGHT}）...")
    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
    try:
        driver.get(CLOUD_GAMING_URL)
        time.sleep(2)
    except Exception as exc:
        print(f"打开云游戏页面失败（可手动导航）: {exc}")
    return driver


def collect_targets(driver, existing: dict, merged: dict) -> dict:
    """采集坐标；每成功一项即写入 merged 并落盘，便于中途取消。"""
    new_coords = {}
    total = len(TARGETS)

    for idx, (key, description) in enumerate(TARGETS, 1):
        print(f"[{idx}/{total}] {description} ({key})")

        if key in existing:
            old = existing[key]
            print(f"    已有坐标 (CSS): ({old[0]}, {old[1]})")
            choice = input("    [回车]保留  [r]重新采集: ").strip().lower()
            if choice != "r":
                new_coords[key] = [int(old[0]), int(old[1])]
                merged[key] = new_coords[key]
                save_coords(merged)
                continue

        input("    将鼠标移到目标按钮中心，按回车记录...")

        mouse_x, mouse_y = pyautogui.position()
        css_x, css_y = screen_to_css(driver, mouse_x, mouse_y)
        new_coords[key] = [css_x, css_y]
        merged[key] = new_coords[key]
        save_coords(merged)
        print(f"    ✅ 已记录 CSS 坐标: ({css_x}, {css_y})")

    return new_coords


def main() -> int:
    print("=" * 50)
    print("  CSS 视口坐标采集工具")
    print("=" * 50)
    print(LEGACY_WARNING)

    existing = load_existing()
    merged = dict(existing)
    driver = None
    new_coords = {}

    try:
        print("使用前请确保：")
        print(f"  1. 浏览器 CSS 视口为 {BROWSER_WIDTH}×{BROWSER_HEIGHT}（本工具可代为启动）")
        print("  2. 已进入需要标定的游戏页面")
        print("  3. 标定过程中不要移动或缩放浏览器窗口")
        print()
        choice = input("[回车] 启动浏览器标定  [n] 我已在 Edge 中打开游戏: ").strip().lower()
        if choice == "n":
            print()
            print(f"请确认 Edge 中游戏画面 CSS 视口已为 {BROWSER_WIDTH}×{BROWSER_HEIGHT}。")
            print("本工具仍需 Selenium 会话读取 window.screenX/Y 以换算 CSS 坐标。")
            print("将启动浏览器窗口；请在新窗口中进入相同页面后继续标定。")
            print()

        driver = launch_driver()
        verify_viewport(driver)

        origin_x, origin_y = get_viewport_origin(driver)
        print(f"视口屏幕原点: ({origin_x}, {origin_y})")
        print()
        print("每轮: 移动鼠标到目标中心 → 按回车记录 CSS 坐标")
        print()

        new_coords = collect_targets(driver, existing, merged)

        print()
        print("=" * 50)
        print(f"已保存 {len(new_coords)} 个 CSS 坐标到 {COORDS_FILE}:")
        for key, coords in new_coords.items():
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
