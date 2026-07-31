#!/usr/bin/env python3
"""快速采集单个坐标（仅 keybind_pos）。

使用方法:
    python capture_one_coord.py
    启动浏览器 → 手动进入键位编辑页 → 移动鼠标到目标位置 → 按回车
"""

import json
import os
import sys
import time

import pyautogui

from browser import create_browser
from config import BROWSER_WIDTH, BROWSER_HEIGHT, CLOUD_GAMING_URL

COORDS_FILE = "calibrated_coords.json"
COORD_KEY = "keybind_pos"


def main():
    driver = None
    try:
        print("正在启动浏览器...")
        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
        try:
            driver.get(CLOUD_GAMING_URL)
        except Exception:
            pass

        inner_w = driver.execute_script("return window.innerWidth;")
        inner_h = driver.execute_script("return window.innerHeight;")
        print(f"浏览器 CSS 视口: {inner_w} × {inner_h}")
        print()

        # 读取窗口位置
        screen_x = driver.execute_script("return window.screenX;")
        screen_y = driver.execute_script("return window.screenY;")
        chrome_h = driver.execute_script("return window.outerHeight - window.innerHeight;")
        origin_x = int(screen_x)
        origin_y = int(screen_y) + int(chrome_h)
        print(f"视口屏幕原点: ({origin_x}, {origin_y})")
        print()

        # 加载已有坐标
        coords = {}
        if os.path.exists(COORDS_FILE):
            with open(COORDS_FILE, "r", encoding="utf-8") as f:
                coords = json.load(f)
        old = coords.get(COORD_KEY, "无")
        print(f"旧坐标 {COORD_KEY}: {old}")
        print()

        print("请在浏览器中：登录先锋 → 秒玩 → 进入游戏 → 打开键位编辑页")
        print("将鼠标移到键位布局中需要点击的位置")
        input("准备好后按回车记录...")

        mouse_x, mouse_y = pyautogui.position()
        css_x = mouse_x - origin_x
        css_y = mouse_y - origin_y

        # 再次读取视口（防止窗口被移动）
        vw = driver.execute_script("return window.innerWidth;")
        vh = driver.execute_script("return window.innerHeight;")

        if css_x < 0 or css_y < 0 or css_x >= vw or css_y >= vh:
            print(f"❌ 坐标 ({css_x}, {css_y}) 超出视口 0..{vw-1} × 0..{vh-1}")
            return

        coords[COORD_KEY] = [css_x, css_y]
        with open(COORDS_FILE, "w", encoding="utf-8") as f:
            json.dump(coords, f, indent=2, ensure_ascii=False)

        print(f"✅ {COORD_KEY}: ({css_x}, {css_y})  → 已写入 {COORDS_FILE}")

    except KeyboardInterrupt:
        print("\n已取消。")
    finally:
        if driver is not None:
            try:
                input("\n按回车关闭浏览器...")
            except KeyboardInterrupt:
                pass
            driver.quit()


if __name__ == "__main__":
    main()
