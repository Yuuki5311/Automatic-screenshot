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

    def _do_scan(self) -> bool:
        """执行一次弹窗扫描+关闭（不检查暂停状态，供内部和 close_all_popups 复用）。

        一轮内遍历关闭按钮模板，尽可能关闭多个弹窗。
        """
        if self.navigator is None:
            return False
        try:
            from login import top_half_bounds

            vw, vh = self.navigator.viewport_size()
            top_bounds = top_half_bounds(vw, vh)

            buttons = [
                ("popup_close.png", top_bounds, "X按钮", 0.85),
                ("popup_close_small.png", top_bounds, "小弹窗X按钮", 0.85),
            ]

            closed_this_round = 0

            for template, bounds, label, threshold in buttons:
                kwargs = {"threshold": threshold, "bounds": bounds}
                if self.navigator.wait_for_template(template, timeout=1, **kwargs):
                    time.sleep(0.5)
                    if not self.navigator.wait_for_template(
                        template, timeout=0.5, **kwargs
                    ):
                        continue
                    time.sleep(2)
                    if self.navigator.find_and_click(
                        template,
                        timeout=2,
                        bounds=bounds,
                        threshold=threshold,
                        allow_fallback=False,
                    ):
                        time.sleep(1)
                        if not self.navigator.wait_for_template(
                            template, timeout=1, **kwargs
                        ):
                            self._closed_count += 1
                            closed_this_round += 1
                            log.info(
                                f"异步关闭弹窗 #{self._closed_count} ({label})"
                            )
                            break

            return closed_this_round > 0

        except Exception as e:
            log.debug(f"弹窗扫描异常: {e}")
        return False

    def _scan_once(self) -> bool:
        """后台线程入口：检查暂停状态后执行扫描。"""
        if self._paused:
            return False
        return self._do_scan()

    def _loop(self):
        """后台循环。"""
        while self._running:
            self._scan_once()
            time.sleep(self.interval)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    def close_all_popups(self, max_rounds: int = 10) -> int:
        """同步关闭所有可见弹窗。

        循环扫描 → 关闭 → 等待3s → 确认无新弹窗 → 继续执行。
        绕过暂停检查，直接执行扫描，不与后台线程冲突。

        Args:
            max_rounds: 最大清理轮次（防止死循环）。

        Returns:
            int: 关闭的弹窗数量。
        """
        closed = 0
        for _ in range(max_rounds):
            if not self._do_scan():
                # 等待 3s 后二次确认，防止弹窗动画延迟出现
                time.sleep(3)
                if not self._do_scan():
                    break
            closed += 1
            time.sleep(3)
        if closed > 0:
            log.info(f"弹窗清理完成，共关闭 {closed} 个")
        return closed

    def wait_until_clear(self, seconds: float = 3.0) -> int:
        """同步等待弹窗区域冷静。

        持续扫描弹窗，发现后立即关闭，直到连续 ``seconds`` 秒
        没有出现新弹窗才返回。在截图工作流中的每个导航步骤前调用，
        确保弹窗关闭动画和级联弹窗都处理完毕。

        Args:
            seconds: 需要的冷静时长（秒）。

        Returns:
            int: 在此期间关闭的弹窗数量。
        """
        closed = 0
        quiet_since = time.time()

        while time.time() - quiet_since < seconds:
            if self._do_scan():
                closed += 1
                quiet_since = time.time()
            else:
                time.sleep(1)

        # 冷静期结束后再做最后一次扫描，防止弹窗在最后毫秒出现
        if self._do_scan():
            closed += 1

        if closed > 0:
            log.info(f"冷却等待完成，共关闭 {closed} 个弹窗")
        return closed

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
