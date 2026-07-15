"""截图捕获与保存模块。"""

import os
import pyautogui
from logger import get_logger

log = get_logger()


class Screenshotter:
    """截取浏览器页面画面并保存到本地。

    优先使用 Selenium 截图（CSS 像素），若 driver 不可用则回退到 PyAutoGUI 全屏截图。
    """

    def __init__(self, output_dir: str = "screenshots", driver=None):
        self.output_dir = os.path.abspath(output_dir)
        self.driver = driver
        os.makedirs(self.output_dir, exist_ok=True)
        log.info(f"截图输出目录: {self.output_dir}")

    def take(self, name: str) -> str:
        """截取当前画面并保存。"""
        filename = f"{name}.png"
        filepath = os.path.join(self.output_dir, filename)

        if self.driver is not None:
            png_bytes = self.driver.get_screenshot_as_png()
            with open(filepath, "wb") as f:
                f.write(png_bytes)
        else:
            img = pyautogui.screenshot()
            img.save(filepath, "PNG")

        size_kb = os.path.getsize(filepath) / 1024
        log.info(f"已保存: {filepath} ({size_kb:.0f} KB)")
        return filepath
