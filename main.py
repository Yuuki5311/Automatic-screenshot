#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— GUI 入口。

启动 Tkinter 控制面板，提供 QQ/微信扫码登录、
游戏启动、自动截图等功能。

使用方法:
    python main.py
"""

import multiprocessing
import sys


def _preload_runtime():
    """在主线程预加载重量级依赖。

    PyInstaller 打包后，若在后台线程首次 import cv2/selenium，
    Windows 上可能静默卡死，表现为点启动后无法打开浏览器。
    """
    from logger import setup_logger, get_logger

    setup_logger()
    log = get_logger()
    log.info("预加载运行时依赖（cv2 / selenium 等）...")
    import cv2  # noqa: F401
    import numpy  # noqa: F401
    from PIL import Image  # noqa: F401
    import browser  # noqa: F401
    import login  # noqa: F401
    import navigator  # noqa: F401
    import game_launcher  # noqa: F401
    import screenshotter  # noqa: F401
    import popup_monitor  # noqa: F401
    import ui_state  # noqa: F401
    import ui_loop  # noqa: F401
    log.info("运行时依赖预加载完成")


if __name__ == "__main__":
    multiprocessing.freeze_support()
    try:
        _preload_runtime()
    except Exception:
        # 预加载失败时仍尝试启动 GUI，便于展示错误
        from logger import get_logger

        get_logger().exception("预加载失败")

    from gui.app import App

    app = App()
    app.run()
