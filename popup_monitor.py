"""异步弹窗监控模块。

后台线程定期扫描屏幕，发现弹窗关闭按钮（popup_close.png）自动点击关闭。
"""

import time
import threading

from logger import get_logger

log = get_logger()


class PopupMonitor:
    """后台线程定期扫描并关闭弹窗。

    通过 Navigator 的模板匹配 + 点击来关闭弹窗，
    确保坐标转换与主线程一致。
    """

    CLOSE_TEMPLATES = (
        ("popup_close.png", "X按钮", 0.85),
        ("popup_close_small.png", "小弹窗X按钮", 0.85),
    )

    def __init__(self, navigator=None, interval: float = 3.0):
        """
        Args:
            navigator: Navigator 实例（用于模板匹配点击）。
            interval: 扫描间隔（秒）。
        """
        self.navigator = navigator
        self.interval = interval
        self._running = False
        self._paused = False
        self._thread = None
        self._closed_count = 0

        log.info(f"弹窗监控: 间隔 {interval}s")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _close_button_specs(self) -> list[tuple[str, tuple, str, float]]:
        """返回 [(template, bounds, label, threshold), ...]。"""
        from login import top_half_bounds

        vw, vh = self.navigator.viewport_size()
        top_bounds = top_half_bounds(vw, vh)
        return [
            (template, top_bounds, label, threshold)
            for template, label, threshold in self.CLOSE_TEMPLATES
        ]

    def _find_close_button(self) -> tuple[str, tuple, float] | None:
        """查找可见的关闭按钮。

        Returns:
            (template, bounds, threshold) 或 None。
        """
        if self.navigator is None:
            return None
        try:
            for template, bounds, _label, threshold in self._close_button_specs():
                if self.navigator.wait_for_template(
                    template, timeout=1, threshold=threshold, bounds=bounds
                ):
                    return (template, bounds, threshold)
        except Exception as e:
            log.debug(f"查找弹窗关闭按钮异常: {e}")
        return None

    def _click_one_popup(self) -> bool:
        """若有关闭按钮则点击一次。

        Returns:
            bool: 成功点击返回 True；未找到或点击失败返回 False。
        """
        if self.navigator is None:
            return False
        try:
            for template, bounds, label, threshold in self._close_button_specs():
                if not self.navigator.wait_for_template(
                    template, timeout=1, threshold=threshold, bounds=bounds
                ):
                    continue
                if self.navigator.find_and_click(
                    template,
                    timeout=2,
                    bounds=bounds,
                    threshold=threshold,
                    allow_fallback=False,
                ):
                    self._closed_count += 1
                    log.info(f"关闭弹窗 #{self._closed_count} ({label})")
                    return True
                log.warning(f"找到 {template} 但点击失败")
                return False
        except Exception as e:
            log.debug(f"弹窗点击异常: {e}")
        return False

    def _do_scan(self) -> bool:
        """执行一次弹窗扫描+关闭（不检查暂停状态）。

        仅点击一个 X；是否还有新弹窗由调用方在等待后再检查。
        """
        return self._click_one_popup()

    def _scan_once(self) -> bool:
        """后台线程入口：检查暂停状态后执行扫描。"""
        if self._paused:
            return False
        return self._do_scan()

    def _loop(self):
        """后台循环：点一次 X 后等待 interval，再检查是否有新弹窗。"""
        while self._running:
            self._scan_once()
            time.sleep(self.interval)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def close_all_popups(self, max_rounds: int = 10, wait_after: float = 3.0) -> int:
        """同步关闭所有可见弹窗。

        流程：点击一次 X → 等待 wait_after 秒 → 检查是否还有新弹窗；
        若有则继续「关闭 → 等待检查」循环。当前无 X 时也会再等一轮确认。

        Args:
            max_rounds: 最大点击次数（防止死循环）。
            wait_after: 每次点击后（或确认前）等待秒数。

        Returns:
            int: 关闭的弹窗数量。
        """
        closed = 0
        for _ in range(max_rounds):
            if self._click_one_popup():
                closed += 1
                time.sleep(wait_after)
                continue

            # 当前没有可点的 X：等待后再确认是否出现新弹窗
            time.sleep(wait_after)
            if self._find_close_button() is None:
                break
            # 等待期间出现了新弹窗，继续下一轮点击

        if closed > 0:
            log.info(f"弹窗清理完成，共关闭 {closed} 个")
        return closed

    def wait_until_clear(self, seconds: float = 3.0) -> int:
        """同步等待弹窗区域冷静。

        与 close_all_popups 相同：点 X → 等 seconds → 再查新弹窗，
        直到连续一轮「无 X + 再等 seconds 仍无 X」。

        Args:
            seconds: 每次点击后 / 确认前的等待时长（秒）。

        Returns:
            int: 在此期间关闭的弹窗数量。
        """
        return self.close_all_popups(max_rounds=20, wait_after=seconds)

    def start(self):
        """启动后台弹窗监控。"""
        if self._thread is not None:
            return
        self._running = True
        self._paused = False
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("弹窗监控已启动")

    def pause(self):
        """暂停监控（导航期间使用）。"""
        self._paused = True

    def resume(self):
        """恢复监控。"""
        self._paused = False

    def stop(self):
        """停止后台弹窗监控。"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info(f"弹窗监控已停止（共关闭 {self._closed_count} 个）")

    @property
    def closed_count(self) -> int:
        return self._closed_count
