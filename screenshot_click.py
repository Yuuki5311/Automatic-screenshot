"""截图导航点击守卫：弹窗避让 + 点击生效验证。"""

from __future__ import annotations

from typing import Any


def parse_click_item(item: tuple) -> dict[str, Any]:
    """解析 screenshot_tasks 中的一步点击配置。"""
    if len(item) == 4:
        template, desc, coords, anchor = item
        return {
            "template": template,
            "desc": desc,
            "bounds": coords,
            "anchor": anchor,
        }
    if len(item) == 3:
        template, desc, bounds = item
        return {
            "template": template,
            "desc": desc,
            "bounds": bounds,
            "anchor": None,
        }
    template, desc = item
    return {
        "template": template,
        "desc": desc,
        "bounds": None,
        "anchor": None,
    }


def effect_verify_template(next_item: tuple | None) -> str | None:
    """根据下一步配置，返回「当前点击生效」后应出现的模板。

    - 无下一步（本任务最后一击）→ None（不强制验证）
    - 下一步是普通模板 → 等该模板出现
    - 下一步是坐标点击 → 用其 anchor（若有）
    """
    if next_item is None:
        return None
    parsed = parse_click_item(next_item)
    if parsed["template"] == "__coords__":
        return parsed["anchor"]
    return parsed["template"]
