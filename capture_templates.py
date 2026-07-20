#!/usr/bin/env python3
"""从 Selenium 浏览器视口重截模板图（与运行时匹配同源）。

流程:
    1. 启动 Edge（与正式脚本同一套 create_browser）
    2. 手动登录并进入对应游戏页面（通常是第 2 个标签）
    3. 脚本会切到云游戏标签后再截图
    4. 框选 → 预览确认 → 不满意可重截或退出

使用方法:
    python capture_templates.py
    python capture_templates.py --only game_logout_btn.png
    python capture_templates.py --only tianmu.png xingyuan.png
    python capture_templates.py --only tianmu.png,xingyuan.png,xing_collection.png,xing_legend.png
    python capture_templates.py --all
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import cv2
import numpy as np

from browser import create_browser
from config import BROWSER_WIDTH, BROWSER_HEIGHT, CLOUD_GAMING_URL, resource_path

TEMPLATES_DIR = resource_path("templates")

# (文件名, 说明, 所在页面)
TEMPLATES = [
    # ---- 登录界面 ----
    ("game_logout_btn.png", "退出登录按钮（右上角「退出」）", "云游戏登录界面右上角"),
    ("game_wx_ios.png", "「与微信iOS好友玩」", "登录界面左半边"),
    ("game_wx_android.png", "「与微信安卓好友玩」", "登录界面左半边"),
    ("game_qq_ios.png", "「与QQ iOS好友玩」", "登录界面右半边"),
    ("game_qq_android.png", "「与QQ安卓好友玩」", "登录界面右半边"),
    ("game_login_other.png", "「登录其他账号」", "登录相关弹窗底部"),
    ("enter_game.png", "「进入游戏」按钮", "登录成功后"),
    ("game_logout_confirm.png", "退出确认「确定」", "退出确认弹窗下方"),
    ("game_popup_confirm.png", "通用/云服务器确认「确定」", "确认弹窗下方"),
    # ---- 弹窗 ----
    ("popup_close.png", "弹窗 X 关闭按钮", "弹窗右上角"),
    ("popup_close_small.png", "小弹窗 X 关闭按钮", "小弹窗右上角"),
    # ---- 主界面 ----
    ("avatar.png", "左上角头像", "主界面左上角"),
    ("shop_icon.png", "商城入口", "主界面右侧"),
    ("customize_icon.png", "定制入口", "主界面下方"),
    ("nobility_icon.png", "贵族图标", "主界面上方"),
    ("game_main.png", "主界面特征小块", "主界面任意辨识区"),
    ("back_arrow.png", "返回箭头", "子页面左上角"),
    ("settings_icon.png", "设置齿轮", "主界面右上角"),
    # ---- 个人主页 ----
    ("tab_home.png", "【主页】标签", "个人主页顶部"),
    ("tab_hero.png", "【英雄】标签", "个人主页顶部"),
    ("tab_illustrated.png", "【图鉴】标签", "个人主页顶部"),
    # ---- 图鉴 ----
    ("universal_illustrated.png", "【万象图鉴】入口", "图鉴页"),
    ("lingbao.png", "【灵宝】入口", "万象图鉴页"),
    ("tianmu.png", "【天幕】入口（需新截取）", "万象图鉴页"),
    ("xingyuan.png", "【星元】入口", "万象图鉴页"),
    ("xing_collection.png", "【星典藏】入口", "星元页内"),
    ("xing_legend.png", "【星传说】入口", "星元页内"),
    ("skin_illustrated.png", "【皮肤图鉴】入口", "图鉴页"),
    ("skin_treasure_wushuang.png", "【珍品无双】图标", "皮肤图鉴页"),
    ("skin_glory_collection.png", "【荣耀典藏】图标", "皮肤图鉴页"),
    ("skin_wushuang.png", "【无双】图标", "皮肤图鉴页"),
    ("skin_treasure_legend.png", "【珍品传说】图标", "皮肤图鉴页"),
    ("skin_legend.png", "【传说】图标", "皮肤图鉴页"),
    ("bag.png", "【背包】按钮", "主界面"),
    ("currency_bag.png", "【货币背包】按钮", "背包页右上角"),
    # ---- 商城 ----
    ("lottery_tab.png", "【夺宝】标签", "商城页"),
    ("points_lottery.png", "【积分夺宝】入口", "夺宝页"),
    # ---- 定制 ----
    ("skin_customize.png", "【皮肤定制】入口", "定制页"),
    ("my_tab.png", "【我的】标签", "皮肤定制页"),
    ("minion.png", "【小兵】选项", "皮肤定制-我的"),
    ("personal_customize.png", "【个性定制】入口", "定制页"),
    ("poke.png", "【个性戳戳】入口", "个性定制页"),
    # ---- 设置 ----
    ("settings_logout.png", "设置页「退出登录」", "设置页下方"),
    # ---- 可选 ----
    ("honor_of_kings.png", "先锋页王者荣耀图标", "腾讯先锋游戏列表"),
]


def grab_viewport_bgr(driver) -> np.ndarray:
    """与 Navigator 相同：Selenium PNG → BGR。"""
    png = driver.get_screenshot_as_png()
    arr = np.frombuffer(png, dtype=np.uint8)
    bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if bgr is None:
        raise RuntimeError("无法解码浏览器截图")
    return bgr


def list_tabs(driver) -> list[tuple[str, str, str]]:
    """返回 [(handle, title, url), ...]。会切换标签读取信息，调用后需再 focus。"""
    current = driver.current_window_handle
    infos: list[tuple[str, str, str]] = []
    for h in driver.window_handles:
        driver.switch_to.window(h)
        time.sleep(0.15)
        try:
            title = driver.title or ""
            url = driver.current_url or ""
        except Exception:
            title, url = "(无法读取)", "(无法读取)"
        infos.append((h, title, url))
    try:
        driver.switch_to.window(current)
    except Exception:
        if infos:
            driver.switch_to.window(infos[-1][0])
    return infos


def focus_game_tab(driver, *, interactive: bool = True) -> str:
    """切到云游戏标签页；截图前必须调用。

    优先匹配 URL 含 /v2/game/ 的标签；否则多标签时交互选择。
    返回当前 URL。
    """
    handles = driver.window_handles
    if len(handles) == 1:
        driver.switch_to.window(handles[0])
        try:
            return driver.current_url
        except Exception:
            return ""

    infos = list_tabs(driver)
    print(f"\n检测到 {len(infos)} 个标签页：")
    game_idxs = []
    for i, (h, title, url) in enumerate(infos):
        flag = ""
        if "/v2/game/" in url:
            flag = "  ← 疑似云游戏"
            game_idxs.append(i)
        print(f"  [{i}] {title[:48]}")
        print(f"      {url}{flag}")

    chosen = None
    if len(game_idxs) == 1:
        chosen = game_idxs[0]
        print(f"自动选择标签 [{chosen}]（云游戏 URL）")
    elif interactive:
        raw = input(
            "请输入要截图的标签编号"
            + (f"（推荐 {game_idxs}）" if game_idxs else "")
            + "，直接回车选最后一个: "
        ).strip()
        if raw == "":
            chosen = len(infos) - 1
        else:
            try:
                chosen = int(raw)
            except ValueError:
                chosen = len(infos) - 1
        if chosen < 0 or chosen >= len(infos):
            chosen = len(infos) - 1
    else:
        chosen = game_idxs[-1] if game_idxs else len(infos) - 1

    driver.switch_to.window(infos[chosen][0])
    time.sleep(0.3)
    url = infos[chosen][2]
    print(f"已切换到标签 [{chosen}]: {url}")
    return url


def _close_cv_windows() -> None:
    cv2.destroyAllWindows()
    # 让窗口真正关掉，避免立刻再开一张
    for _ in range(5):
        cv2.waitKey(1)


def select_roi(screen: np.ndarray, title: str) -> tuple[int, int, int, int] | None:
    """框选区域，返回原图像素 (x0,y0,x1,y1)；取消/关闭返回 None。"""
    h, w = screen.shape[:2]
    max_w, max_h = 1600, 900
    scale = min(1.0, max_w / w, max_h / h)
    display = (
        cv2.resize(screen, (int(w * scale), int(h * scale)))
        if scale < 1.0
        else screen
    )

    win = f"框选: {title}  | 拖拽后按空格/回车确认，按 c 取消"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    try:
        rect = cv2.selectROI(win, display, showCrosshair=True, fromCenter=False)
    finally:
        _close_cv_windows()

    x, y, rw, rh = rect
    if rw <= 0 or rh <= 0:
        return None

    x0 = max(0, int(x / scale))
    y0 = max(0, int(y / scale))
    x1 = min(w, int((x + rw) / scale))
    y1 = min(h, int((y + rh) / scale))
    if x1 <= x0 or y1 <= y0:
        return None
    return x0, y0, x1, y1


def preview_crop(crop: np.ndarray, title: str) -> None:
    """预览裁剪结果，任意键关闭（不自动进入下一次截图）。"""
    win = f"预览: {title}  | 看完后按任意键关闭"
    # 过小则放大便于查看
    h, w = crop.shape[:2]
    view = crop
    if w < 80 or h < 40:
        view = cv2.resize(crop, (max(w * 4, 120), max(h * 4, 60)), interpolation=cv2.INTER_NEAREST)
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.imshow(win, view)
    cv2.waitKey(0)
    _close_cv_windows()


def capture_one(
    driver,
    filename: str,
    description: str,
    location: str,
    index: int,
    total: int,
    *,
    force: bool,
) -> str:
    """采集单个模板。返回 status: saved | skipped | exists | quit。"""
    filepath = os.path.join(TEMPLATES_DIR, filename)

    print(f"\n{'─' * 50}")
    print(f"[{index}/{total}] {description}")
    print(f"    位置: {location}")
    print(f"    文件: {filepath}")

    if os.path.exists(filepath) and not force:
        print("    已存在。")
        choice = input("    [回车]跳过  [r]重截  [q]退出程序: ").strip().lower()
        if choice == "q":
            return "quit"
        if choice != "r":
            return "exists"

    print("    请在浏览器中打开对应云游戏画面。")
    choice = input("    [回车]开始截取  [s]跳过本项  [q]退出程序: ").strip().lower()
    if choice == "q":
        return "quit"
    if choice == "s":
        return "skipped"

    while True:
        # 每次截图前都切到云游戏标签，避免仍停在先锋首页
        url = focus_game_tab(driver, interactive=True)
        if "gamer.qq.com" in url and "/v2/game/" not in url and "honor" not in filename:
            print("    ⚠️  当前标签看起来仍是先锋首页，不是云游戏页。")
            cont = input("    [回车]仍然截这页  [t]重新选标签  [s]跳过  [q]退出: ").strip().lower()
            if cont == "q":
                return "quit"
            if cont == "s":
                return "skipped"
            if cont == "t":
                continue

        screen = grab_viewport_bgr(driver)
        print(f"    视口截图: {screen.shape[1]}×{screen.shape[0]}  |  {url}")

        roi = select_roi(screen, filename)
        if roi is None:
            print("    已取消框选（或关闭了窗口）。")
            # 默认不再自动重开；必须显式选 r
            again = input("    [r]重新截图  [s]跳过本项  [q]退出程序: ").strip().lower()
            if again == "q":
                return "quit"
            if again == "s" or again == "":
                return "skipped"
            continue

        x0, y0, x1, y1 = roi
        crop = screen[y0:y1, x0:x1]
        print(f"    裁剪预览 {x1 - x0}×{y1 - y0}，请查看弹窗…")
        preview_crop(crop, filename)

        decide = input(
            "    [回车]保存  [r]重截  [s]跳过不保存  [q]退出程序: "
        ).strip().lower()
        if decide == "q":
            return "quit"
        if decide == "s":
            return "skipped"
        if decide == "r":
            continue

        os.makedirs(TEMPLATES_DIR, exist_ok=True)
        cv2.imwrite(filepath, crop)
        kb = os.path.getsize(filepath) / 1024
        print(f"    ✅ 已保存 {filepath} ({kb:.1f} KB)")
        return "saved"


def parse_args():
    p = argparse.ArgumentParser(description="Selenium 视口模板采集")
    p.add_argument(
        "--all",
        action="store_true",
        help="强制重截（仍可对单项选跳过）",
    )
    p.add_argument(
        "--only",
        nargs="+",
        metavar="FILE",
        help="只采集指定文件名；空格或逗号均可，如 tianmu.png xingyuan.png 或 a.png,b.png",
    )
    p.add_argument(
        "--from",
        dest="from_item",
        metavar="N_OR_FILE",
        help="从第 N 个（1-based）或指定文件名开始采集后续项，例如 10 或 popup_close.png",
    )
    return p.parse_args()


def resolve_items(args) -> list:
    items = list(TEMPLATES)
    if args.only:
        # 支持空格分隔与逗号分隔（含混用）
        wanted: set[str] = set()
        for token in args.only:
            for part in token.split(","):
                name = part.strip()
                if not name:
                    continue
                if not name.endswith(".png"):
                    name = f"{name}.png"
                wanted.add(name)
        items = [t for t in TEMPLATES if t[0] in wanted]
        missing = wanted - {t[0] for t in items}
        if missing:
            raise ValueError(f"未知模板名: {', '.join(sorted(missing))}")
        if not items:
            raise ValueError("没有可采集的模板")
        return items

    if args.from_item:
        raw = args.from_item.strip()
        start_idx = None
        if raw.isdigit():
            n = int(raw)
            if n < 1 or n > len(TEMPLATES):
                raise ValueError(f"--from 序号应在 1..{len(TEMPLATES)}，收到 {n}")
            start_idx = n - 1
        else:
            name = raw if raw.endswith(".png") else f"{raw}.png"
            for i, (fname, _, _) in enumerate(TEMPLATES):
                if fname == name:
                    start_idx = i
                    break
            if start_idx is None:
                raise ValueError(f"--from 未找到模板: {name}")
        items = TEMPLATES[start_idx:]
        print(f"从第 {start_idx + 1} 项开始: {items[0][0]}（共剩余 {len(items)} 项）")
    return items


def main() -> int:
    args = parse_args()
    try:
        items = resolve_items(args)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1

    print("=" * 50)
    print("  模板图采集（Selenium 视口，与运行时同源）")
    print("=" * 50)
    print()
    print("说明：")
    print("  - 截图前会列出标签页并切到云游戏（/v2/game/）")
    print("  - 你在 Edge 里点到第 2 个标签还不够，必须让本脚本 switch 过去")
    print("  - 框选取消后不会自动再弹窗，需输入 r 才重截")
    print("  - 保存前可预览；不满意选 r 重截，选 q 退出")
    print(f"  - 本轮共 {len(items)} 项")
    if args.from_item:
        print("  - 已存在的项默认跳过；加 --all 可强制重截")
    print()

    driver = None
    try:
        print("正在启动浏览器...")
        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
        try:
            driver.get(CLOUD_GAMING_URL)
        except Exception as exc:
            print(f"打开首页失败（可手动导航）: {exc}")

        inner_w = driver.execute_script("return window.innerWidth;")
        inner_h = driver.execute_script("return window.innerHeight;")
        print(f"浏览器 CSS 视口: {inner_w}×{inner_h}")
        print()
        print("请先：登录先锋 → 秒玩打开云游戏（第 2 个标签）→ 停在要截的画面。")
        input("准备好后按回车（将自动检测并切换标签）...")

        focus_game_tab(driver, interactive=True)
        shot = grab_viewport_bgr(driver)
        print(f"当前截图像素: {shot.shape[1]}×{shot.shape[0]}")
        print()

        saved = skipped = existed = 0
        total_all = len(TEMPLATES)
        for filename, desc, location in items:
            abs_idx = next(i for i, t in enumerate(TEMPLATES, 1) if t[0] == filename)
            status = capture_one(
                driver,
                filename,
                desc,
                location,
                abs_idx,
                total_all,
                force=args.all,
            )
            if status == "quit":
                print("\n已退出。")
                break
            if status == "saved":
                saved += 1
            elif status == "skipped":
                skipped += 1
            elif status == "exists":
                existed += 1

        print(f"\n{'=' * 50}")
        print(f"本轮: 新截 {saved}，保留已有 {existed}，跳过 {skipped}")
        ready = sum(
            1
            for f, _, _ in TEMPLATES
            if os.path.exists(os.path.join(TEMPLATES_DIR, f))
        )
        print(f"templates/ 就绪: {ready}/{len(TEMPLATES)}")
        print("=" * 50)
        return 0

    except KeyboardInterrupt:
        print("\n\n已取消。")
        return 130
    finally:
        if driver is not None:
            try:
                input("\n按回车关闭浏览器...")
            except KeyboardInterrupt:
                pass
            driver.quit()


if __name__ == "__main__":
    sys.exit(main())
