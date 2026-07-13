"""游戏内导航模块 —— 基于 OpenCV 模板匹配 + 原生鼠标点击。

在 macOS 桌面客户端游戏画面中定位按钮并点击。
使用 pyautogui 截取全屏并模拟鼠标操作，
自动处理 Retina 显示的坐标缩放。
"""

import os
import time
import cv2
import numpy as np
import pyautogui

from config import MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL, resource_path
from logger import get_logger

log = get_logger()


class Navigator:
    """在桌面客户端游戏画面中通过图像识别找到按钮并点击。"""

    def __init__(
        self,
        templates_dir: str = "templates",
        threshold: float = MATCH_THRESHOLD,
        max_retries: int = MAX_RETRIES,
    ):
        """
        Args:
            templates_dir: 存放按钮模板图的目录。
            threshold: cv2.matchTemplate 匹配置信度阈值 (0~1)。
            max_retries: 单个按钮最大匹配重试次数。
        """
        self.templates_dir = resource_path(templates_dir)
        self.threshold = threshold
        self.max_retries = max_retries

        # 模板缓存：避免每次匹配都从磁盘加载
        self._template_cache: dict[str, np.ndarray] = {}

        # Retina 缩放因子
        # pyautogui.screenshot() 返回物理像素，pyautogui.click() 使用逻辑坐标
        self._scale = self._detect_scale()

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    @staticmethod
    def _detect_scale() -> float:
        """检测 Retina 显示缩放因子。

        pyautogui.size() 返回逻辑分辨率 (points)，
        pyautogui.screenshot() 返回物理像素分辨率。
        两者之比即为缩放因子（Retina 通常为 2.0）。
        """
        logical_w, _ = pyautogui.size()
        screenshot = pyautogui.screenshot()
        physical_w, _ = screenshot.size
        scale = physical_w / logical_w
        log.info(f"屏幕: 逻辑 {logical_w}x{pyautogui.size().height}, "
                 f"物理 {physical_w}x{screenshot.height}, 缩放 {scale:.1f}")
        return scale

    def _get_screenshot(self) -> np.ndarray:
        """截取当前全屏画面，返回 OpenCV 格式的 BGR numpy 数组。

        返回的是物理像素分辨率的截图。
        """
        pil_image = pyautogui.screenshot()
        # PIL Image (RGB) → numpy array → BGR for OpenCV
        rgb = np.array(pil_image)
        bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
        # 显式释放中间对象，降低内存峰值
        del pil_image
        del rgb
        return bgr

    def _template_path(self, template_name: str) -> str:
        """构建模板文件的完整路径。"""
        return os.path.join(self.templates_dir, template_name)

    def _load_template(self, template_name: str) -> np.ndarray | None:
        """加载模板图片，优先从缓存获取。

        模板是小文件（几十 KB），缓存后避免重复磁盘 I/O
        和反复分配/释放 numpy 数组。
        """
        path = self._template_path(template_name)
        if path not in self._template_cache:
            template = cv2.imread(path)
            if template is None:
                return None
            self._template_cache[path] = template
        return self._template_cache[path]

    def _physical_to_logical(self, x: int, y: int) -> tuple:
        """将物理像素坐标转换为逻辑坐标（用于鼠标点击）。"""
        return (int(x / self._scale), int(y / self._scale))

    def _click_at(self, x: int, y: int) -> None:
        """在屏幕上 (x, y) 物理像素位置模拟鼠标点击。

        自动将物理像素坐标转换为逻辑坐标。
        """
        logical_x, logical_y = self._physical_to_logical(x, y)
        pyautogui.click(logical_x, logical_y)

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def find_and_click(
        self, template_name: str, timeout: int = 10,
        bounds: tuple = None, max_retries: int = None,
        threshold: float = None,
    ) -> bool:
        """在全屏幕画面中匹配模板图并点击其中心位置。

        Args:
            template_name: 模板文件名。
            timeout: 保留参数。
            bounds: 可选 (x, y, w, h) 限制搜索区域（物理像素）。
            max_retries: 最大重试次数，默认使用 self.max_retries。
            threshold: 匹配置信度阈值，默认使用 self.threshold。

        Returns:
            bool: 匹配成功并点击返回 True，否则 False。
        """
        template = self._load_template(template_name)

        if template is None:
            log.error(f"模板文件不存在: {self._template_path(template_name)}")
            return False

        t_h, t_w = template.shape[:2]
        retries = max_retries if max_retries is not None else self.max_retries
        _threshold = threshold if threshold is not None else self.threshold

        for attempt in range(1, retries + 1):
            screen = self._get_screenshot()

            if bounds is not None:
                x, y, w, h = bounds
                search_area = screen[y:y+h, x:x+w]
                offset_x, offset_y = x, y
            else:
                search_area = screen
                offset_x, offset_y = 0, 0

            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, max_loc = cv2.minMaxLoc(result)

            log.debug(f"匹配 {template_name} 尝试 {attempt}/{retries}: "
                      f"置信度 {max_val:.3f} (阈值 {_threshold})")

            if max_val >= _threshold:
                center_x = offset_x + max_loc[0] + t_w // 2
                center_y = offset_y + max_loc[1] + t_h // 2
                logical_x, logical_y = self._physical_to_logical(center_x, center_y)
                self._click_at(center_x, center_y)
                log.info(f"点击 {template_name} (置信度 {max_val:.2f})")
                time.sleep(CLICK_INTERVAL)
                return True

            time.sleep(RETRY_INTERVAL)

        log.warning(f"未能找到: {template_name}")
        return False

    def wait_for_template(self, template_name: str, timeout: int = 15,
                          threshold: float = None) -> bool:
        """轮询等待模板出现（不点击）。

        Args:
            template_name: 模板文件名。
            timeout: 最大等待时间（秒）。
            threshold: 匹配置信度阈值，默认使用 self.threshold。

        Returns:
            bool: 在超时前检测到模板返回 True，否则 False。
        """
        template = self._load_template(template_name)

        if template is None:
            log.error(f"模板文件不存在: {self._template_path(template_name)}")
            return False

        _threshold = threshold if threshold is not None else self.threshold

        start = time.time()
        while time.time() - start < timeout:
            screen = self._get_screenshot()
            result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val >= _threshold:
                log.info(f"检测到 {template_name} (置信度 {max_val:.2f})")
                return True
            time.sleep(1)

        log.warning(f"超时未检测到: {template_name}")
        return False

    def cleanup(self) -> None:
        """释放模板缓存，回收内存。"""
        self._template_cache.clear()
        log.debug("模板缓存已释放")
