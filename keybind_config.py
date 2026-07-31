"""键位配置模块。

在 enter_game 后配置自定义键位布局：
1. 点击键位编辑按钮（模板匹配）
2. 点击指定坐标（ROI 双重确认，参考 ui_loop.py 中 __coords__ 分支）
3. 点击保存键位按钮（模板匹配）
4. 点击"暂不更改"按钮（不存在则跳过）
"""

from __future__ import annotations

import json
import os
import time
from typing import Callable

from config import CLICK_INTERVAL, resource_path
from logger import get_logger

log = get_logger()

# ---- 模板名（换模板只需改这里）----
KEYBIND_EDIT_BTN = "keybind_edit.png"
KEYBIND_SAVE_BTN = "keybind_save.png"
KEYBIND_POS_TEMPLATE = "keybind_pos_target.png"
KEYBIND_SKIP_BTN = "keybind_skip.png"  # "暂不更改" 按钮

# ---- calibrated_coords.json 中的坐标 key ----
KEYBIND_CLICK_COORD_KEY = "keybind_pos"

# ---- 坐标搜索区域半径 (CSS 像素) ----
COORD_SEARCH_MARGIN = 80

# ---- 重试 ----
MAX_RETRIES = 3


def _load_keybind_coords() -> tuple[int, int] | None:
    """从 calibrated_coords.json 读取键位点击坐标。"""
    path = resource_path("calibrated_coords.json")
    if not os.path.isfile(path):
        log.error(f"坐标文件不存在: {path}")
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            coords = json.load(f)
    except Exception as exc:
        log.error(f"读取坐标文件失败: {exc}")
        return None

    keybind_pos = coords.get(KEYBIND_CLICK_COORD_KEY)
    if keybind_pos is None:
        log.error(f"坐标文件中未找到 key: {KEYBIND_CLICK_COORD_KEY}")
        return None

    x, y = keybind_pos
    return int(x), int(y)


def configure_keybinding(nav, on_log: Callable[[str, str], None] | None = None) -> bool:
    """配置键位布局。

    Args:
        nav: Navigator 实例。
        on_log: 可选回调 (text, level)，用于 GUI 日志推送。

    Returns:
        bool: 全部步骤成功返回 True，任一步失败返回 False。
    """

    def _emit(text: str, level: str = "info") -> None:
        if on_log:
            on_log(text, level)
        if level == "error":
            log.error(text)
        elif level == "warn":
            log.warning(text)
        else:
            log.info(text)

    _emit("开始键位配置...")

    # ---- Step 1: 点击键位编辑按钮 ----
    if not nav.find_and_click(KEYBIND_EDIT_BTN, timeout=5, max_retries=MAX_RETRIES):
        _emit(f"找不到键位编辑按钮 ({KEYBIND_EDIT_BTN})", "error")
        return False
    _emit(f"已点击键位编辑按钮 ({KEYBIND_EDIT_BTN})", "success")
    time.sleep(CLICK_INTERVAL)

    # ---- Step 2: 坐标粗定位 + 模板精匹配 + 单次点击 ----
    coords = _load_keybind_coords()
    if coords is None:
        _emit("无法读取键位坐标", "error")
        return False

    cx, cy = coords
    vw, vh = nav.viewport_size()
    margin = COORD_SEARCH_MARGIN

    # 以坐标为中心，±margin 搜索区域（夹在视口内）
    bx = max(0, cx - margin)
    by = max(0, cy - margin)
    bw = min(vw, cx + margin) - bx
    bh = min(vh, cy + margin) - by
    search_bounds = (bx, by, bw, bh)

    _emit(
        f"坐标粗定位 ({cx}, {cy}) → 搜索区 {bw}×{bh} @ ({bx},{by})",
        "info",
    )

    # 在限定区域内模板匹配 + 点击
    if nav.find_and_click(
        KEYBIND_POS_TEMPLATE,
        timeout=3,
        max_retries=2,
        bounds=search_bounds,
    ):
        _emit(f"模板匹配命中 → 已点击 ({KEYBIND_POS_TEMPLATE})", "success")
    else:
        # 回退：直接用坐标单点点击
        _emit(
            f"模板未匹配，回退坐标点击 ({cx}, {cy})",
            "warn",
        )
        nav.click_css(cx, cy)

    time.sleep(CLICK_INTERVAL)

    # ---- Step 3: 点击保存键位按钮（右下角） ----
    vw, vh = nav.viewport_size()
    # 右下 1/4 区域
    save_bounds = (vw // 2, vh // 2, vw - vw // 2, vh - vh // 2)
    if not nav.find_and_click(KEYBIND_SAVE_BTN, timeout=5, max_retries=MAX_RETRIES, bounds=save_bounds):
        _emit(f"找不到保存键位按钮 ({KEYBIND_SAVE_BTN})", "error")
        return False
    _emit(f"已点击保存键位按钮 ({KEYBIND_SAVE_BTN})", "success")
    time.sleep(CLICK_INTERVAL)

    # ---- Step 4: 点击"暂不更改"按钮（不存在则跳过） ----
    if nav.find_and_click(KEYBIND_SKIP_BTN, timeout=3, max_retries=2, threshold=0.75):
        _emit(f"已点击暂不更改按钮 ({KEYBIND_SKIP_BTN})", "success")
        time.sleep(CLICK_INTERVAL)
    else:
        _emit(f"未检测到暂不更改按钮 ({KEYBIND_SKIP_BTN})，跳过", "info")

    _emit("键位配置完成", "success")
    return True
