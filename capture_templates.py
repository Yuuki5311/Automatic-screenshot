#!/usr/bin/env python3
"""模板图辅助采集工具。

逐条引导你在游戏界面中截取按钮模板图，自动保存为正确文件名，
无需手动对照表格和命名。

使用方法:
    python capture_templates.py

流程:
    1. 先手动打开王者荣耀，停在主界面
    2. 运行此脚本
    3. 每条提示会告诉你截取什么（如"左上角头像"）
    4. 按回车后 macOS 截图工具出现，鼠标框选按钮区域
    5. 自动保存到 templates/ 目录
    6. 下一条，直到全部完成
"""

import os
import subprocess
import sys

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

    # ======== 游戏登录界面 ========
    ("game_logout_btn.png",      "退出登录按钮（右上角）",       "游戏画面右上角"),
    ("game_logout_confirm.png",  "退出确认弹窗「确定」按钮（底部）", "弹窗下方"),
    ("game_wx_ios.png",          "「与微信iOS好友玩」（绿色按钮）", "登录界面左半边"),
    ("game_wx_android.png",      "「与微信安卓好友玩」（绿色按钮）", "登录界面左半边"),
    ("game_qq_ios.png",          "「与QQ iOS好友玩」（蓝色按钮）", "登录界面右半边"),
    ("game_qq_android.png",      "「与QQ安卓好友玩」（蓝色按钮）", "登录界面右半边"),

    # ======== 可选 ========
    ("honor_of_kings.png",       "腾讯先锋页面中的【王者荣耀】图标", "腾讯先锋游戏列表"),
]


def clear_line():
    """清除当前行。"""
    sys.stdout.write("\033[2K\033[1G")
    sys.stdout.flush()


def capture_one(filename: str, description: str, location: str, index: int, total: int) -> bool:
    """引导用户截取一个模板图。

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
    input("    按回车启动截图工具（鼠标框选按钮区域）...")

    # 调用 macOS screencapture -i (交互式选区截图)
    # -i: 交互模式（鼠标框选）
    result = subprocess.run(
        ["screencapture", "-i", filepath],
        capture_output=True,
    )

    if result.returncode != 0:
        print(f"    ⚠️  截图取消或失败（返回码: {result.returncode}）")
        choice = input("    [r]重试  [s]跳过  [q]退出: ").strip().lower()
        if choice == "r":
            return capture_one(filename, description, location, index, total)
        elif choice == "q":
            print("\n已退出。")
            sys.exit(0)
        else:
            return False

    # 验证文件
    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
        size_kb = os.path.getsize(filepath) / 1024
        print(f"    ✅ 已保存 ({size_kb:.1f} KB)")
        return True
    else:
        print(f"    ⚠️  文件为空或未生成")
        return False


def main():
    print("=" * 50)
    print("  王者荣耀 — 模板图采集工具")
    print("=" * 50)
    print()
    print("使用前请确保：")
    print("  1. 已手动打开王者荣耀并停在主界面")
    print("  2. 需要进入子页面时（如商城、定制），先在游戏中点进去")
    print("  3. 截图时用鼠标框选按钮图标区域（留少许边距）")
    print()
    print(f"共 {len(TEMPLATES)} 个模板图需要采集")
    print()
    input("按回车开始...")

    os.makedirs(TEMPLATES_DIR, exist_ok=True)

    success = 0
    skipped = 0

    for i, (filename, desc, location) in enumerate(TEMPLATES, 1):
        ok = capture_one(filename, desc, location, i, len(TEMPLATES))
        if ok:
            if os.path.exists(os.path.join(TEMPLATES_DIR, filename)):
                success += 1

    print(f"\n{'=' * 50}")
    existing = sum(1 for f, _, _ in TEMPLATES if os.path.exists(os.path.join(TEMPLATES_DIR, f)))
    missing = len(TEMPLATES) - existing
    print(f"完成: {existing}/{len(TEMPLATES)} 个模板图已就绪")
    if missing > 0:
        print(f"还缺 {missing} 个，可以重新运行此脚本补充")
    else:
        print("全部模板图已就绪，可以运行 python main.py 了！")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n已取消。")
