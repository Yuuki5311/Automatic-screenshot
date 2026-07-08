"""截图捕获与保存模块。"""

import os
import pyautogui
from logger import get_logger

log = get_logger()


class Screenshotter:
    """截取全屏画面并保存到本地。"""

    def __init__(self, output_dir: str = "screenshots"):
        self.output_dir = os.path.abspath(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        log.info(f"截图输出目录: {self.output_dir}")

    def take(self, name: str) -> str:
        """截取当前全屏画面并保存。"""
        filename = f"{name}.png"
        filepath = os.path.join(self.output_dir, filename)

        img = pyautogui.screenshot()
        img.save(filepath, "PNG")

        size_kb = os.path.getsize(filepath) / 1024
        log.info(f"已保存: {filepath} ({size_kb:.0f} KB)")
        return filepath
