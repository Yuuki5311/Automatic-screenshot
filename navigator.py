"""游戏内导航模块 —— 基于 OpenCV 模板匹配定位按钮并点击。"""

import time
import cv2
import numpy as np
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from config import MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL


class Navigator:
    """在云游戏画面中通过图像识别找到按钮并点击。"""

    def __init__(
        self,
        driver: WebDriver,
        templates_dir: str = "templates",
        threshold: float = MATCH_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Args:
            driver: Selenium WebDriver 实例。
            templates_dir: 存放按钮模板图的目录。
            threshold: cv2.matchTemplate 匹配置信度阈值 (0~1)。
            max_retries: 单个按钮最大匹配重试次数。
        """
        self.driver = driver
        self.templates_dir = templates_dir
        self.threshold = threshold
        self.max_retries = max_retries

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_screenshot(self) -> np.ndarray:
        """获取当前浏览器画面，返回 OpenCV 格式的 BGR numpy 数组。"""
        png = self.driver.get_screenshot_as_png()
        nparr = np.frombuffer(png, np.uint8)
        return cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    def _template_path(self, template_name: str) -> str:
        """构建模板文件的完整路径。"""
        return f"{self.templates_dir}/{template_name}"

    def _click_at(self, x: int, y: int) -> None:
        """在浏览器画面上 (x, y) 位置模拟鼠标左键点击。

        使用 ActionChains 以 body 元素为锚点偏移点击，
        确保坐标与 Selenium 截图像素对齐。
        """
        body = self.driver.find_element(By.TAG_NAME, "body")
        ActionChains(self.driver) \
            .move_to_element_with_offset(body, x, y) \
            .click() \
            .perform()

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def find_and_click(self, template_name: str, timeout: int = 10) -> bool:
        """在画面中匹配模板图并点击其中心位置。

        Args:
            template_name: 模板文件名（含扩展名），如 "avatar.png"。
            timeout: 单次尝试内的等待时间（暂保留接口，实际由重试控制）。

        Returns:
            bool: 匹配成功并点击返回 True，否则 False。
        """
        template_path = self._template_path(template_name)
        template = cv2.imread(template_path)

        if template is None:
            print(f"[警告] 模板文件不存在: {template_path}")
            return False

        t_h, t_w = template.shape[:2]

        for attempt in range(1, self.max_retries + 1):
            screen = self._get_screenshot()
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            if max_val >= self.threshold:
                center_x = max_loc[0] + t_w // 2
                center_y = max_loc[1] + t_h // 2
                self._click_at(center_x, center_y)
                print(f"[导航] 点击 {template_name} "
                      f"(置信度: {max_val:.2f}, 坐标: {center_x},{center_y})")
                time.sleep(CLICK_INTERVAL)
                return True

            print(f"[导航] 未匹配到 {template_name} "
                  f"(尝试 {attempt}/{self.max_retries}, "
                  f"最高置信度: {max_val:.2f})")
            time.sleep(RETRY_INTERVAL)

        print(f"[警告] 未能找到并点击: {template_name}")
        return False

    def wait_for_template(self, template_name: str, timeout: int = 15) -> bool:
        """轮询等待模板出现（不点击）。

        Args:
            template_name: 模板文件名。
            timeout: 最大等待时间（秒）。

        Returns:
            bool: 在超时前检测到模板返回 True，否则 False。
        """
        template_path = self._template_path(template_name)
        template = cv2.imread(template_path)

        if template is None:
            print(f"[警告] 模板文件不存在: {template_path}")
            return False

        start = time.time()
        while time.time() - start < timeout:
            screen = self._get_screenshot()
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= self.threshold:
                print(f"[导航] 检测到 {template_name}")
                return True
            time.sleep(1)

        print(f"[警告] 超时未检测到: {template_name}")
        return False
