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

    def _scan_once(self) -> bool:
        """扫描一次：检测弹窗 → 等2秒动画 → 关闭。"""
        if self._paused or self.navigator is None:
            return False
        try:
            # 方式 1: 右上角 X 关闭按钮
            if self.navigator.wait_for_template("popup_close.png", timeout=1):
                time.sleep(2)
                if self.navigator.find_and_click("popup_close.png", timeout=2):
                    self._closed_count += 1
                    log.info(f"异步关闭弹窗 #{self._closed_count} (X按钮)")
                    return True

            # 方式 2: 弹窗下方确认按钮
            if self.navigator.wait_for_template("game_logout_confirm.png", timeout=1):
                time.sleep(2)
                if self.navigator.find_and_click("game_logout_confirm.png", timeout=2):
                    self._closed_count += 1
                    log.info(f"异步关闭弹窗 #{self._closed_count} (确认按钮)")
                    return True

        except Exception as e:
            log.debug(f"弹窗扫描异常: {e}")
        return False

    def _loop(self):
        """后台循环。"""
        while self._running:
            self._scan_once()
            time.sleep(self.interval)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

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
