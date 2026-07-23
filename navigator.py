"""游戏内导航模块 —— 基于 OpenCV 模板匹配 + Selenium 浏览器点击。

在浏览器游戏画面中定位按钮并点击。
使用 Selenium 截取浏览器视口，经 CDP 注入 CSS 坐标点击。
"""

import os
import time
import cv2
import numpy as np

from config import MATCH_THRESHOLD, MAX_RETRIES, RETRY_INTERVAL, CLICK_INTERVAL, resource_path
from logger import get_logger

log = get_logger()


class Navigator:
    """在浏览器游戏画面中通过图像识别找到按钮并点击。"""

    def __init__(
        self,
        driver,
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
        self.templates_dir = resource_path(templates_dir)
        self.threshold = threshold
        self.max_retries = max_retries

        # 模板缓存：避免每次匹配都从磁盘加载
        self._template_cache: dict[str, np.ndarray] = {}

        # CSS 像素坐标系，不做 Retina 物理/逻辑换算
        self._scale = 1.0

        # 兜底坐标：模板匹配失败后直接坐标点击（首次使用时懒加载）
        self._coords: dict | None = None

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _get_screenshot(self) -> np.ndarray:
        """截取当前浏览器视口，返回 OpenCV 格式的 BGR numpy 数组。"""
        png = self.driver.get_screenshot_as_png()
        arr = np.frombuffer(png, dtype=np.uint8)
        bgr = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return bgr

    def _template_path(self, template_name: str) -> str:
        """构建模板文件的完整路径。"""
        return os.path.join(self.templates_dir, template_name)

    def _load_template(self, template_name: str) -> np.ndarray | None:
        """加载模板图片，优先从缓存获取。

        使用 np.fromfile + imdecode，避免 cv2.imread 在含非 ASCII
        路径（如中文用户名下的 %TEMP%\\_MEI*）上失败。
        """
        path = self._template_path(template_name)
        if path not in self._template_cache:
            if not os.path.isfile(path):
                return None
            try:
                data = np.fromfile(path, dtype=np.uint8)
                template = cv2.imdecode(data, cv2.IMREAD_COLOR) if data.size else None
            except OSError as e:
                log.error(f"模板读取异常: {path} ({e})")
                return None
            if template is None:
                log.error(f"模板解码失败(路径可能含非ASCII): {path}")
                return None
            self._template_cache[path] = template
        return self._template_cache[path]

    def _physical_to_logical(self, x: int, y: int) -> tuple:
        """将物理像素坐标转换为逻辑坐标（_scale=1.0 时为恒等映射）。"""
        return (int(x / self._scale), int(y / self._scale))

    def click_css(self, x: int, y: int) -> None:
        """在浏览器视口 CSS 坐标 (x, y) 处点击（CDP 注入，减少系统光标拖动）。"""
        x_i, y_i = int(x), int(y)
        self.driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {"type": "mouseMoved", "x": x_i, "y": y_i},
        )
        self.driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": "mousePressed",
                "x": x_i,
                "y": y_i,
                "button": "left",
                "buttons": 1,
                "clickCount": 1,
            },
        )
        self.driver.execute_cdp_cmd(
            "Input.dispatchMouseEvent",
            {
                "type": "mouseReleased",
                "x": x_i,
                "y": y_i,
                "button": "left",
                "buttons": 0,
                "clickCount": 1,
            },
        )

    def grab_roi(self, x: int, y: int, w: int, h: int) -> np.ndarray:
        """截取视口后裁切 ROI（P0：全图再裁；后续可换 CDP clip）。"""
        screen = self._get_screenshot()
        vh, vw = screen.shape[:2]
        x0 = max(0, int(x))
        y0 = max(0, int(y))
        x1 = min(vw, x0 + max(1, int(w)))
        y1 = min(vh, y0 + max(1, int(h)))
        if x1 <= x0 or y1 <= y0:
            return np.zeros((1, 1, 3), dtype=np.uint8)
        return screen[y0:y1, x0:x1].copy()

    def _click_at(self, x: int, y: int) -> None:
        """在浏览器视口 CSS 坐标 (x, y) 处点击。"""
        self.click_css(x, y)

    def viewport_size(self) -> tuple[int, int]:
        """返回当前匹配用截图的宽高（与 bounds / 点击同一像素空间）。"""
        screen = self._get_screenshot()
        h, w = screen.shape[:2]
        return int(w), int(h)

    def _load_coords(self) -> dict:
        """懒加载 calibrated_coords.json，仅在首次兜底点击时触发。

        返回 dict 映射模板名(无后缀) → [x, y] CSS 坐标。
        文件不存在或损坏则返回空 dict，后续不再重试。
        """
        if self._coords is not None:
            return self._coords
        try:
            import json
            path = resource_path("calibrated_coords.json")
            with open(path, "r") as f:
                self._coords = json.load(f)
            log.info(f"已加载 {len(self._coords)} 个兜底坐标")
        except Exception:
            log.warning("兜底坐标加载失败，将跳过坐标点击兜底")
            self._coords = {}
        return self._coords

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def find_and_click(
        self, template_name: str, timeout: int = 10,
        bounds: tuple = None, max_retries: int = None,
        threshold: float = None, allow_fallback: bool = False,
    ) -> bool:
        """在浏览器画面中匹配模板图并点击其中心位置。

        Args:
            template_name: 模板文件名。
            timeout: 保留参数。
            bounds: 可选 (x, y, w, h) 限制搜索区域（CSS 像素）。
            max_retries: 最大重试次数，默认使用 self.max_retries。
            threshold: 匹配置信度阈值，默认使用 self.threshold。
            allow_fallback: 模板匹配失败时是否使用坐标兜底点击。
                默认 False（诊断：仅主页头像/小兵通过 GUI ``__coords__`` 走坐标点击）。

        Returns:
            bool: 匹配成功并点击返回 True，否则 False。
        """
        template = self._load_template(template_name)

        if template is None:
            log.error(f"模板文件不存在或无法读取: {self._template_path(template_name)}")
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
                self._click_at(center_x, center_y)
                log.info(f"点击 {template_name} (置信度 {max_val:.2f})")
                time.sleep(CLICK_INTERVAL)
                return True

            time.sleep(RETRY_INTERVAL)

        # 诊断模式：find_and_click 默认不做坐标兜底。
        # 主页头像 / 小兵仅由 GUI 的 __coords__ 显式坐标点击保留。
        if allow_fallback:
            coords = self._load_coords()
            key = template_name.replace(".png", "")
            if key in coords:
                x, y = coords[key]
                self._click_at(x, y)
                log.info(f"兜底点击 {template_name} @ ({x}, {y})")
                time.sleep(CLICK_INTERVAL)
                return True

        log.warning(f"未能找到: {template_name}")
        return False

    def wait_for_template(self, template_name: str, timeout: int = 15,
                          threshold: float = None, bounds: tuple = None) -> bool:
        """轮询等待模板出现（不点击）。

        Args:
            template_name: 模板文件名。
            timeout: 最大等待时间（秒）。
            threshold: 匹配置信度阈值，默认使用 self.threshold。
            bounds: 可选 (x, y, w, h) 限制搜索区域（CSS 像素）。

        Returns:
            bool: 在超时前检测到模板返回 True，否则 False。
        """
        template = self._load_template(template_name)

        if template is None:
            log.error(f"模板文件不存在或无法读取: {self._template_path(template_name)}")
            return False

        _threshold = threshold if threshold is not None else self.threshold

        start = time.time()
        best_val = -1.0
        while time.time() - start < timeout:
            screen = self._get_screenshot()
            if bounds is not None:
                x, y, w, h = bounds
                search_area = screen[y:y+h, x:x+w]
            else:
                search_area = screen
            result = cv2.matchTemplate(search_area, template, cv2.TM_CCOEFF_NORMED)
            _, max_val, _, _ = cv2.minMaxLoc(result)
            if max_val > best_val:
                best_val = max_val
            if max_val >= _threshold:
                log.info(f"检测到 {template_name} (置信度 {max_val:.2f})")
                return True
            time.sleep(1)

        if best_val >= 0:
            log.warning(
                f"超时未检测到: {template_name} "
                f"(最高置信度 {best_val:.3f}, 阈值 {_threshold})"
            )
        else:
            log.warning(f"超时未检测到: {template_name}")
        return False

    def cleanup(self) -> None:
        """释放模板缓存，回收内存。"""
        self._template_cache.clear()
        log.debug("模板缓存已释放")
