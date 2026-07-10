#!/usr/bin/env python3
"""绝对坐标采集工具。

在游戏内手动将鼠标移动到按钮位置，按回车记录坐标。
采集的坐标存入 config.py 供截图工作流使用。

使用方法:
    python calibrate_coords.py
"""

import json
import os
import pyautogui
import sys
import time

COORDS_FILE = "calibrated_coords.json"

TARGETS = [
    ("avatar",         "左上角头像（主界面）"),
    ("minion",         "小兵按钮（皮肤定制-我的页面）"),
]

# 已有坐标记录则加载
existing = {}
if os.path.exists(COORDS_FILE):
    with open(COORDS_FILE, "r") as f:
        existing = json.load(f)


def get_mouse_pos() -> tuple:
    """获取当前鼠标逻辑坐标。"""
    return pyautogui.position()


def main():
    print("=" * 50)
    print("  绝对坐标采集工具")
    print("=" * 50)
    print()
    print("使用前请确保：")
    print("  1. 已打开王者荣耀并进入对应页面")
    print("  2. 将鼠标精确移动到目标按钮的中心")
    print()
    print("每轮: 移动鼠标 → 按回车记录 → 下一个目标")
    print()

    screen_w, screen_h = pyautogui.size()
    print(f"屏幕逻辑分辨率: {screen_w} × {screen_h}")
    print()

    new_coords = {}
    total = len(TARGETS)

    for idx, (key, description) in enumerate(TARGETS, 1):
        print(f"[{idx}/{total}] {description} ({key})")

        if key in existing:
            old = existing[key]
            print(f"    已有坐标: ({old[0]}, {old[1]})")
            choice = input("    [回车]保留  [r]重新采集: ").strip().lower()
            if choice != "r":
                new_coords[key] = old
                continue

        input("    将鼠标移到目标按钮上，按回车记录...")

        try:
            x, y = get_mouse_pos()
            new_coords[key] = [x, y]
            print(f"    ✅ 已记录: ({x}, {y})")
        except KeyboardInterrupt:
            print("\n\n已取消。")
            sys.exit(0)

    # 保存
    existing.update(new_coords)
    with open(COORDS_FILE, "w") as f:
        json.dump(existing, f, indent=2)

    print()
    print("=" * 50)
    print(f"已保存 {len(new_coords)} 个坐标到 {COORDS_FILE}:")
    for key, coords in new_coords.items():
        print(f"  {key}: ({coords[0]}, {coords[1]})")
    print()
    print("接下来可以把这些坐标用于截图工作流中的绝对点击。")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消。")
