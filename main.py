#!/usr/bin/env python3
"""王者荣耀云游戏自动截图 —— GUI 入口。

启动 Tkinter 控制面板，提供 QQ/微信扫码登录、
游戏启动、自动截图等功能。

使用方法:
    python main.py
"""

import sys

if __name__ == "__main__":
    from gui.app import App
    app = App()
    app.run()
