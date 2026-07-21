"""点击前 ROI 双重确认：Pass1 定坐标与基准块，Pass2 再采局部比对后再 click。"""

from __future__ import annotations

import time
from dataclasses import dataclass

import cv2
import numpy as np

from config import CLICK_INTERVAL
from logger import get_logger

log = get_logger()

ROI_PAD_PX = 12
ROI_CONFIRM_THRESHOLD = 0.90
COORDS_ROI_SIZE = 48


@dataclass
class ClickPlan:
    x: int
    y: int
    roi_ref: np.ndarray
    template_name: str | None
    score: float
    roi_box: tuple[int, int, int, int]  # x, y, w, h on full frame


def roi_bounds_around(
    cx: int,
    cy: int,
    tw: int,
    th: int,
    vw: int,
    vh: int,
    pad: int = ROI_PAD_PX,
) -> tuple[int, int, int, int]:
    """以点击中心为基准的正方形 ROI，夹在视口内。返回 (x, y, w, h)。"""
    side = max(int(tw), int(th), 1) + 2 * int(pad)
    half = side // 2
    x0 = max(0, int(cx) - half)
    y0 = max(0, int(cy) - half)
    x1 = min(int(vw), x0 + side)
    y1 = min(int(vh), y0 + side)
    x0 = max(0, x1 - side)
    y0 = max(0, y1 - side)
    w = max(1, x1 - x0)
    h = max(1, y1 - y0)
    return (x0, y0, w, h)


def crop_roi(screen: np.ndarray, x: int, y: int, w: int, h: int) -> np.ndarray:
    return screen[y : y + h, x : x + w].copy()


def roi_similar(
    ref: np.ndarray,
    now: np.ndarray,
    threshold: float = ROI_CONFIRM_THRESHOLD,
) -> tuple[bool, float]:
    """比较两块 ROI。返回 (是否通过, 相似度)。"""
    if ref is None or now is None or ref.size == 0 or now.size == 0:
        return False, -1.0
    if ref.shape[0] < 2 or ref.shape[1] < 2 or now.shape[0] < 2 or now.shape[1] < 2:
        return False, -1.0

    a = ref
    b = now
    if a.shape[:2] != b.shape[:2]:
        b = cv2.resize(b, (a.shape[1], a.shape[0]), interpolation=cv2.INTER_AREA)

    # 用较小块当模板：取中心 80% 降低边缘抖动
    th, tw = a.shape[:2]
    mh, mw = max(2, int(th * 0.8)), max(2, int(tw * 0.8))
    y0, x0 = (th - mh) // 2, (tw - mw) // 2
    patch = a[y0 : y0 + mh, x0 : x0 + mw]
    if b.shape[0] < patch.shape[0] or b.shape[1] < patch.shape[1]:
        return False, -1.0

    result = cv2.matchTemplate(b, patch, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    score = float(max_val)
    return score >= threshold, score


def plan_template_click(
    nav,
    screen: np.ndarray,
    template_name: str,
    bounds: tuple | None = None,
    threshold: float | None = None,
) -> ClickPlan | None:
    """在已有全图上匹配模板，生成 ClickPlan（含 roi_ref）。"""
    template = nav._load_template(template_name)
    if template is None or screen is None or screen.size == 0:
        return None

    thr = threshold if threshold is not None else nav.threshold
    t_h, t_w = template.shape[:2]
    vh, vw = screen.shape[:2]

    if bounds is not None:
        bx, by, bw, bh = bounds
        search = screen[by : by + bh, bx : bx + bw]
        offset_x, offset_y = bx, by
    else:
        search = screen
        offset_x, offset_y = 0, 0

    if (
        search.size == 0
        or search.shape[0] < t_h
        or search.shape[1] < t_w
    ):
        return None

    result = cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, max_loc = cv2.minMaxLoc(result)
    score = float(max_val)
    if score < thr:
        return None

    cx = offset_x + max_loc[0] + t_w // 2
    cy = offset_y + max_loc[1] + t_h // 2
    box = roi_bounds_around(cx, cy, t_w, t_h, vw, vh)
    roi_ref = crop_roi(screen, *box)
    return ClickPlan(
        x=cx,
        y=cy,
        roi_ref=roi_ref,
        template_name=template_name,
        score=score,
        roi_box=box,
    )


def plan_coords_click(screen: np.ndarray, x: int, y: int) -> ClickPlan:
    vh, vw = screen.shape[:2]
    box = roi_bounds_around(x, y, COORDS_ROI_SIZE, COORDS_ROI_SIZE, vw, vh)
    roi_ref = crop_roi(screen, *box)
    return ClickPlan(
        x=int(x),
        y=int(y),
        roi_ref=roi_ref,
        template_name=None,
        score=1.0,
        roi_box=box,
    )


def confirm_roi(nav, plan: ClickPlan) -> tuple[bool, float]:
    x, y, w, h = plan.roi_box
    now = nav.grab_roi(x, y, w, h)
    return roi_similar(plan.roi_ref, now)


def execute_click_with_confirm(nav, plan: ClickPlan) -> bool:
    """Pass2 通过才 click_css。失败返回 False（未点击）。"""
    ok, score = confirm_roi(nav, plan)
    if not ok:
        name = plan.template_name or "coords"
        log.warning(
            "ROI 确认失败 score=%.3f（阈值 %.2f），取消点击 %s @ (%d,%d)",
            score,
            ROI_CONFIRM_THRESHOLD,
            name,
            plan.x,
            plan.y,
        )
        return False

    log.debug(
        "ROI 确认通过 score=%.3f，点击 %s @ (%d,%d)",
        score,
        plan.template_name or "coords",
        plan.x,
        plan.y,
    )
    nav.click_css(plan.x, plan.y)
    time.sleep(CLICK_INTERVAL)
    return True
