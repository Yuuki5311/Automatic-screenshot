#!/usr/bin/env python3
"""模板图辅助采集工具（Selenium CSS 像素版）。

在浏览器游戏画面中截取按钮模板图，自动保存为正确文件名。
截图源为 Selenium CSS 像素（1920×1080），跨平台分辨率一致。

使用方法:
    python capture_templates.py

流程:
    1. 脚本自动打开浏览器并导航到 gamer.qq.com
    2. 手动登录并启动王者荣耀
    3. 每条提示告诉你截取什么（如"左上角头像"）
    4. 按回车后自动截取浏览器画面，用鼠标框选按钮区域
    5. 自动保存到 templates/ 目录
    6. 下一条，直到全部完成
"""

import os
import sys
import cv2
import numpy as np

from browser import create_browser
from config import BROWSER_WIDTH, BROWSER_HEIGHT

TEMPLATES_DIR = "templates"

# 模板列表：(文件名, 说明, 在哪找)
TEMPLATES = [
    # ======== 主界面 ========
    ("avatar.png",               "左上角头像",                   "主界面左上角"),
    ("shop_icon.png",            "商城入口图标",                 "主界面右侧"),
    ("customize_icon.png",       "定制入口图标",                 "主界面下方"),
    ("nobility_icon.png",        "贵族图标",                     "主界面上方"),
    ("game_main.png",            "游戏主界面特征（截一小块有辨识度的区域）", "主界面任意位置"),
    ("back_arrow.png",           "返回箭头",                     "页面左上角"),

    # ======== 个人主页 (先点击头像进入) ========
    ("tab_home.png",             "【主页】标签",                  "个人主页顶部"),
    ("tab_hero.png",             "【英雄】标签",                  "个人主页顶部"),
    ("tab_illustrated.png",      "【图鉴】标签",                  "个人主页顶部"),

    # ======== 图鉴 (点击图鉴后) ========
    ("universal_illustrated.png","【万象图鉴】入口",              "图鉴页面"),
    ("lingbao.png",              "【灵宝】入口",                  "万象图鉴页面中"),
    ("skin_illustrated.png",     "【皮肤图鉴】入口",              "图鉴页面"),

    # ======== 商城 (点击商城后) ========
    ("lottery_tab.png",          "【夺宝】标签",                  "商城页面中"),
    ("points_lottery.png",       "【积分夺宝】入口",              "夺宝页面中"),

    # ======== 定制 (点击定制后) ========
    ("skin_customize.png",       "【皮肤定制】入口",              "定制页面"),
    ("my_tab.png",               "【我的】标签",                  "皮肤定制页面"),
    ("sky_curtain.png",          "【天幕】选项",                  "皮肤定制-我的页面"),
    ("minion.png",               "【小兵】选项",                  "皮肤定制-我的页面"),
    ("personal_customize.png",   "【个性定制】入口",              "定制页面"),
    ("poke.png",                 "【个性戳戳】入口",              "个性定制页面"),

    # ======== 设置界面 ========
    ("settings_icon.png",       "设置按钮（右上角齿轮）",       "主界面右上角"),
    ("settings_logout.png",     "设置页中的「退出登录」按钮（底部）", "设置页面下方"),

    # ======== 弹窗相关 ========
    ("popup_close.png",          "弹窗 X 关闭按钮",             "弹窗右上角"),
    ("popup_close_small.png",    "小弹窗 X 关闭按钮",           "小弹窗右上角"),
    ("game_logout_confirm.png",  "退出确认弹窗「确定」按钮（底部）", "弹窗下方"),
    ("game_popup_confirm.png",   "通用弹窗确认按钮（底部）",       "弹窗下方"),

    # ======== 游戏登录界面 ========
    ("game_logout_btn.png",      "退出登录按钮（右上角）",       "游戏画面右上角"),
    ("game_login_other.png",     "「登录其他账号」按钮（底部）",    "弹窗下方"),
    ("game_wx_ios.png",          "「与微信iOS好友玩」（绿色按钮）", "登录界面左半边"),
    ("game_wx_android.png",      "「与微信安卓好友玩」（绿色按钮）", "登录界面左半边"),
    ("game_qq_ios.png",          "「与QQ iOS好友玩」（蓝色按钮）", "登录界面右半边"),
    ("game_qq_android.png",      "「与QQ安卓好友玩」（蓝色按钮）", "登录界面右半边"),

    # ======== 可选 ========
    ("honor_of_kings.png",       "腾讯先锋页面中的【王者荣耀】图标", "腾讯先锋游戏列表"),
]


def capture_one(filename: str, description: str, location: str,
                index: int, total: int, driver) -> bool:
    """引导用户截取一个模板图。

    从 Selenium 截取整张浏览器画面，用 OpenCV ROI 选择器框选区域。

    Returns:
        True: 成功
        False: 跳过
    """
    filepath = os.path.join(TEMPLATES_DIR, filename)

    # 已有的跳过
    if os.path.exists(filepath):
        print(f"\n[{index}/{total}] {filename} — 已存在，跳过")
        return True

    print(f"\n{'─' * 50}")
    print(f"[{index}/{total}] 请截取: {description}")
    print(f"    位置: {location}")
    print(f"    将保存为: {filename}")
    print()
    input("    按回车截取当前浏览器画面（请先确保游戏画面已就绪）...")

    # Selenium 截图（CSS 像素 1920×1080）
    try:
        png_bytes = driver.get_screenshot_as_png()
        full_img = cv2.imdecode(
            np.frombuffer(png_bytes, np.uint8), cv2.IMREAD_COLOR
        )
    except Exception as e:
        print(f"    ⚠️  截图失败: {e}")
        choice = input("    [r]重试  [s]跳过  [q]退出: ").strip().lower()
        if choice == "r":
            return capture_one(filename, description, location, index, total, driver)
        elif choice == "q":
            print("\n已退出。")
            sys.exit(0)
        else:
            return False

    # OpenCV ROI 选择器 —— 鼠标框选后按 ENTER 确认，按 ESC 跳过
    print("    🖱 用鼠标框选按钮区域 → 按 ENTER 确认 → 按 ESC 跳过")
    print("    （若图像窗口未在前台，请切换过去操作）")

    roi = cv2.selectROI(
        f"[{index}/{total}] 框选: {description}",
        full_img,
        showCrosshair=True,
        fromCenter=False,
    )
    cv2.destroyAllWindows()
    cv2.waitKey(1)  # 确保窗口完全销毁

    x, y, w, h = roi
    if w == 0 or h == 0:
        print(f"    ⚠️  未框选，跳过")
        choice = input("    [r]重试  [s]跳过  [q]退出: ").strip().lower()
        if choice == "r":
            return capture_one(filename, description, location, index, total, driver)
        elif choice == "q":
            print("\n已退出。")
            sys.exit(0)
        else:
            return False

    # 裁剪并保存
    cropped = full_img[y:y+h, x:x+w]
    cv2.imwrite(filepath, cropped)

    # 验证文件
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        size_kb = os.path.getsize(filepath) / 1024
        print(f"    ✅ 已保存 ({size_kb:.1f} KB, {w}x{h}px)")
        return True
    else:
        print(f"    ⚠️  文件为空或未生成")
        return False


def main():
    print("=" * 50)
    print("  王者荣耀 — 模板图采集工具 (Selenium CSS 像素)")
    print("=" * 50)
    print()
    print("使用前请确保：")
    print("  1. 浏览器会自动打开（1920×1080 CSS 像素）")
    print("  2. 手动登录腾讯先锋并启动王者荣耀")
    print("  3. 需要截取子页面时，先在游戏中点进去")
    print("  4. 截图时用鼠标框选按钮图标区域（留少许边距）")
    print(f"  5. 截图分辨率固定为 {BROWSER_WIDTH}x{BROWSER_HEIGHT} CSS 像素")
    print()
    print(f"共 {len(TEMPLATES)} 个模板图需要采集")
    print()
    input("按回车启动浏览器...")

    # 启动浏览器
    print("\n正在启动浏览器...")
    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)

    print()
    print("浏览器已启动。请手动完成以下操作：")
    print("  1. 在浏览器中登录腾讯先锋")
    print("  2. 搜索并启动王者荣耀")
    print("  3. 进入游戏主界面")
    print()
    input("准备就绪后按回车开始采集模板...")

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    success = 0

    for i, (filename, desc, location) in enumerate(TEMPLATES, 1):
        ok = capture_one(filename, desc, location, i, len(TEMPLATES), driver)
        if ok:
            success += 1

    print(f"\n{'=' * 50}")
    existing = sum(
        1 for f, _, _ in TEMPLATES
        if os.path.exists(os.path.join(TEMPLATES_DIR, f))
    )
    missing = len(TEMPLATES) - existing
    print(f"完成: {existing}/{len(TEMPLATES)} 个模板图已就绪")
    if missing > 0:
        print(f"还缺 {missing} 个，可以重新运行此脚本补充")
    else:
        print("全部模板图已就绪！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消。")
    finally:
        cv2.destroyAllWindows()
