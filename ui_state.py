"""轻量 UI 状态分类：按优先级从截图分数判定当前界面。"""

from __future__ import annotations

from enum import Enum
from typing import Any

from logger import get_logger

log = get_logger()

# 与弹窗关闭按钮匹配共用（云游戏压缩下 0.85 易漏检）
POPUP_CLOSE_THRESHOLD = 0.78
POPUP_CLOSE_TEMPLATES = (
    "popup_close.png",
    "popup_close_small.png",
)

LOGIN_TEMPLATES = (
    "game_wx_ios.png",
    "game_wx_android.png",
    "game_qq_ios.png",
    "game_qq_android.png",
)

MAIN_TEMPLATE = "avatar.png"
MAIN_THRESHOLD = 0.53
# 平台登录图在大厅易误匹配；真登录页通常 >0.90，门槛提高到 0.80
LOGIN_THRESHOLD = 0.80
PATH_THRESHOLD = 0.53
CONFIRM_TEMPLATE = "game_popup_confirm.png"
CONFIRM_THRESHOLD = 0.48


class UiState(Enum):
    POPUP = "popup"
    LOGIN = "login"
    CONFIRM = "confirm"
    MAIN = "main"
    ON_PATH = "on_path"
    UNKNOWN = "unknown"


def popup_close_bounds(viewport_w: int, viewport_h: int) -> tuple[int, int, int, int]:
    """弹窗关闭按钮搜索区：右上半屏 (x, y, w, h)。"""
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)
    x0 = w // 2
    return (x0, 0, w - x0, h // 2)


def avatar_bounds(viewport_w: int, viewport_h: int) -> tuple[int, int, int, int]:
    """主界面头像搜索区：左上区域。"""
    w = max(int(viewport_w), 1)
    h = max(int(viewport_h), 1)
    return (0, 0, max(1, int(w * 0.4)), max(1, int(h * 0.5)))


def _best(scores: dict[str, float], keys: tuple[str, ...] | list[str]) -> float:
    best = -1.0
    for k in keys:
        v = scores.get(k)
        if v is not None and v > best:
            best = v
    return best


def classify_from_scores(
    scores: dict[str, float],
    *,
    path_templates: list[str] | None = None,
    allow_confirm: bool = False,
) -> tuple[UiState, dict[str, Any]]:
    """根据模板置信度字典按优先级判定状态。

    优先级：POPUP > LOGIN（且需达较高阈值）> CONFIRM(可选) > ON_PATH > MAIN > UNKNOWN。
    """
    path_templates = path_templates or []
    info: dict[str, Any] = {"scores": dict(scores)}

    popup_score = _best(scores, POPUP_CLOSE_TEMPLATES)
    if popup_score >= POPUP_CLOSE_THRESHOLD:
        info["hit"] = "popup"
        return UiState.POPUP, info

    login_score = _best(scores, LOGIN_TEMPLATES)
    main_score = scores.get(MAIN_TEMPLATE, -1.0)
    # 已有头像说明在局内，即使平台模板误匹配也不判 LOGIN
    if login_score >= LOGIN_THRESHOLD and main_score < MAIN_THRESHOLD:
        info["hit"] = "login"
        return UiState.LOGIN, info

    if allow_confirm:
        confirm_score = scores.get(CONFIRM_TEMPLATE, -1.0)
        if confirm_score >= CONFIRM_THRESHOLD:
            info["hit"] = "confirm"
            return UiState.CONFIRM, info

    path_score = _best(scores, path_templates) if path_templates else -1.0
    if path_templates and path_score >= PATH_THRESHOLD:
        info["hit"] = "on_path"
        return UiState.ON_PATH, info

    if main_score >= MAIN_THRESHOLD:
        info["hit"] = "main"
        return UiState.MAIN, info

    info["hit"] = None
    return UiState.UNKNOWN, info


def match_score(nav, template_name: str, bounds=None, threshold: float | None = None) -> float:
    """对单模板做一次匹配，返回最高置信度（不做等待循环）。"""
    import cv2

    template = nav._load_template(template_name)
    if template is None:
        return -1.0

    screen = nav._get_screenshot()
    if bounds is not None:
        x, y, w, h = bounds
        search_area = screen[y : y + h, x : x + w]
    else:
        search_area = screen

    if search_area.size == 0 or search_area.shape[0] < template.shape[0] or search_area.shape[1] < template.shape[1]:
        return -1.0

    result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
    _, max_val, _, _ = cv2.minMaxLoc(result)
    return float(max_val)


def classify(
    nav,
    path_templates: list[str] | None = None,
    *,
    allow_confirm: bool = False,
) -> tuple[UiState, dict[str, Any]]:
    """截取当前画面相关模板分数并分类。"""
    path_templates = path_templates or []
    vw, vh = nav.viewport_size()
    popup_bounds = popup_close_bounds(vw, vh)
    av_bounds = avatar_bounds(vw, vh)

    scores: dict[str, float] = {}
    for tpl in POPUP_CLOSE_TEMPLATES:
        scores[tpl] = match_score(nav, tpl, bounds=popup_bounds)

    for tpl in LOGIN_TEMPLATES:
        scores[tpl] = match_score(nav, tpl)

    scores[MAIN_TEMPLATE] = match_score(nav, MAIN_TEMPLATE, bounds=av_bounds)

    for tpl in path_templates:
        if tpl == "__coords__":
            continue
        scores[tpl] = match_score(nav, tpl)

    if allow_confirm:
        from login import bottom_half_bounds

        scores[CONFIRM_TEMPLATE] = match_score(
            nav, CONFIRM_TEMPLATE, bounds=bottom_half_bounds(vw, vh)
        )

    state, info = classify_from_scores(
        scores, path_templates=path_templates, allow_confirm=allow_confirm
    )
    if state == UiState.UNKNOWN:
        log.info(
            "UI classify UNKNOWN scores=%s",
            {k: round(v, 3) for k, v in scores.items() if v >= 0},
        )
    else:
        log.debug("UI classify %s hit=%s", state.value, info.get("hit"))
    return state, info
