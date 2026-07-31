#!/usr/bin/env python3
"""探测 (1712, 16) 坐标下是什么 DOM 元素。"""

import os, sys, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from browser import create_browser
from config import BROWSER_WIDTH, BROWSER_HEIGHT, CLOUD_GAMING_URL


def main():
    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
    try:
        driver.get(CLOUD_GAMING_URL)
        print("请手动：登录先锋 → 秒玩 → 进入游戏 → 打开键位编辑页")
        input("准备好后按回车...")

        for x, y in [(1712, 16), (900, 500)]:
            print(f"\n{'='*60}")
            print(f"坐标 ({x}, {y}):")

            # 1. DOM.getNodeForLocation — 该坐标是什么 DOM 节点
            try:
                node = driver.execute_cdp_cmd("DOM.getNodeForLocation", {
                    "x": x, "y": y,
                    "includeUserAgentShadowDOM": True,
                })
                print(f"  DOM.getNodeForLocation: {json.dumps(node, indent=4, ensure_ascii=False)}")
            except Exception as e:
                print(f"  DOM.getNodeForLocation 失败: {e}")

            # 2. Runtime.evaluate — document.elementFromPoint
            try:
                el = driver.execute_cdp_cmd("Runtime.evaluate", {
                    "expression": f"""
                        (() => {{
                            const el = document.elementFromPoint({x}, {y});
                            if (!el) return null;
                            return {{
                                tag: el.tagName,
                                id: el.id || null,
                                className: (typeof el.className === 'string')
                                    ? el.className.substring(0, 120)
                                    : String(el.className).substring(0, 120),
                                rect: (() => {{
                                    const r = el.getBoundingClientRect();
                                    return {{x: r.x, y: r.y, w: r.width, h: r.height}};
                                }})(),
                                computedSize: (() => {{
                                    const s = getComputedStyle(el);
                                    return {{w: s.width, h: s.height}};
                                }}(),
                            }};
                        }})()
                    """,
                    "returnByValue": True,
                })
                print(f"  elementFromPoint: {json.dumps(el, indent=4, ensure_ascii=False)}")
            except Exception as e:
                print(f"  Runtime.evaluate 失败: {e}")

            # 3. 获取 body 下所有子元素概览
            if x == 500:
                try:
                    summary = driver.execute_cdp_cmd("Runtime.evaluate", {
                        "expression": """
                            [...document.querySelectorAll('body *')]
                                .filter(el => {
                                    const r = el.getBoundingClientRect();
                                    return r.width > 50 && r.height > 50;
                                })
                                .slice(0, 15)
                                .map(el => ({
                                    tag: el.tagName,
                                    id: el.id || null,
                                    cls: (el.className?.substring?.(0, 80) || ''),
                                    rect: (() => {
                                        const r = el.getBoundingClientRect();
                                        return {x: Math.round(r.x), y: Math.round(r.y),
                                                w: Math.round(r.width), h: Math.round(r.height)};
                                    })(),
                                }))
                        """,
                        "returnByValue": True,
                    })
                    print(f"\n  页面主要元素 (>50×50):")
                    for item in summary.get("result", {}).get("value", []):
                        print(f"    <{item['tag']}> id={item['id']} "
                              f"pos=({item['rect']['x']},{item['rect']['y']}) "
                              f"size={item['rect']['w']}×{item['rect']['h']}")
                except Exception as e:
                    print(f"  元素扫描失败: {e}")

        input("\n按回车关闭浏览器...")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
