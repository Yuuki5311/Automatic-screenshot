"""截图导航点击守卫：弹窗避让 + 点击生效验证。"""

from __future__ import annotations

from typing import Any


def parse_click_item(item: tuple) -> dict[str, Any]:
    """解析 screenshot_tasks 中的一步点击配置。"""
    if len(item) == 5:
        template, desc, coords, anchor, verify_timeout = item
        return {
            "template": template,
            "desc": desc,
            "bounds": coords,
            "anchor": anchor,
            "verify_timeout": verify_timeout,
        }
    if len(item) == 4:
        template, desc, coords, anchor = item
        return {
            "template": template,
            "desc": desc,
            "bounds": coords,
            "anchor": anchor,
            "verify_timeout": None,
        }
    if len(item) == 3:
        template, desc, bounds = item
        return {
            "template": template,
            "desc": desc,
            "bounds": bounds,
            "anchor": None,
            "verify_timeout": None,
        }
    if len(item) == 2:
        template, desc = item
        return {
            "template": template,
            "desc": desc,
            "bounds": None,
            "anchor": None,
            "verify_timeout": None,
        }
    # __guard__ / __optional__ 等特殊类型可能只传 1 个元素占位
    return {
        "template": item[0] if len(item) >= 1 else "",
        "desc": "",
        "bounds": None,
        "anchor": None,
        "verify_timeout": None,
    }


def effect_verify_template(next_item: tuple | None) -> str | None:
    """根据下一步配置，返回「当前点击生效」后应出现的模板。

    - 无下一步（本任务最后一击）→ None（不强制验证）
    - 下一步是普通模板 → 等该模板出现
    - 下一步是坐标点击 → 用其 anchor（若有）
    - 下一步是可选弹窗 → 返回 None（弹窗不一定出现，不强制验证）
    """
    if next_item is None:
        return None
    parsed = parse_click_item(next_item)
    if parsed["template"] == "__coords__":
        return parsed["anchor"]
    if parsed["template"] in ("__optional__", "__guard__"):
        return None  # 可选弹窗/守卫步骤不强制验证，直接进入下一步
    return parsed["template"]
