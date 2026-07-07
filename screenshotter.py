"""截图捕获与保存模块。"""

import os
from selenium.webdriver.remote.webdriver import WebDriver


class Screenshotter:
    """从浏览器当前画面截图并保存到本地。"""

    def __init__(self, driver: WebDriver, output_dir: str = "screenshots"):
        """
        Args:
            driver: Selenium WebDriver 实例。
            output_dir: 截图输出目录。
        """
        self.driver = driver
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def take(self, name: str) -> str:
        """截取当前浏览器画面并保存。

        Args:
            name: 截图名称（不含扩展名），如 "主页", "英雄"。

        Returns:
            str: 保存的文件路径。
        """
        filename = f"{name}.png"
        filepath = os.path.join(self.output_dir, filename)
        self.driver.save_screenshot(filepath)
        print(f"[截图] 已保存: {filepath}")
        return filepath
