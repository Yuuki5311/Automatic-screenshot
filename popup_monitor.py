"""异步弹窗监控模块。

后台线程定期扫描屏幕，发现弹窗关闭按钮（popup_close.png）自动点击关闭。
关闭后进入冷静期：等待并只检测新弹窗，期间截图主流程应等待。
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

    # 云游戏视频流压缩后，0.85 易在弹窗仍可见时漏检（日志曾出现成功时刚好 0.85）。
    CLOSE_THRESHOLD = 0.78

    CLOSE_TEMPLATES = (
        ("popup_close.png", "X按钮"),
        ("popup_close_small.png", "小弹窗X按钮"),
    )

    def __init__(self, navigator=None, interval: float = 3.0):
        """
        Args:
            navigator: Navigator 实例（用于模板匹配点击）。
            interval: 空闲扫描间隔（秒）。
        """
        self.navigator = navigator
        self.interval = interval
        self._running = False
        self._paused = False
        self._thread = None
        self._closed_count = 0

        # 正在关闭弹窗 / 冷静检测期间为 True；截图主流程应 wait_until_idle
        self._busy = threading.Event()
        self._nav_lock = threading.RLock()

        log.info(f"弹窗监控: 间隔 {interval}s")

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _close_search_bounds(self) -> tuple[int, int, int, int]:
        """弹窗关闭按钮搜索区：右上半屏 (x, y, w, h)。"""
        vw, vh = self.navigator.viewport_size()
        w = max(int(vw), 1)
        h = max(int(vh), 1)
        x0 = w // 2
        return (x0, 0, w - x0, h // 2)

    def _close_button_specs(self) -> list[tuple[str, tuple, str, float]]:
        """返回 [(template, bounds, label, threshold), ...]。"""
        bounds = self._close_search_bounds()
        return [
            (template, bounds, label, self.CLOSE_THRESHOLD)
            for template, label in self.CLOSE_TEMPLATES
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

    def _wait_and_watch(self, seconds: float = 3.0) -> bool:
        """关闭后冷静等待：只检测是否出现新弹窗，不执行截图逻辑。

        Args:
            seconds: 冷静时长（秒）。

        Returns:
            True: 等待期间或结束时仍检测到关闭按钮（需再关一轮）。
            False: 全程无弹窗。
        """
        deadline = time.time() + seconds
        while time.time() < deadline:
            if self._find_close_button() is not None:
                log.info("冷静期内检测到新弹窗，将继续关闭")
                return True
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            time.sleep(min(0.5, remaining))
        return self._find_close_button() is not None

    def _do_scan(self) -> bool:
        """执行一次弹窗扫描+关闭（不检查暂停状态）。"""
        return self._click_one_popup()

    def _scan_once(self) -> bool:
        """后台线程入口：检查暂停状态后执行扫描。"""
        if self._paused:
            return False
        return self._do_scan()

    def _drain_popups(self, max_rounds: int = 10, wait_after: float = 3.0) -> int:
        """关闭弹窗并进入冷静检测循环（持有 busy）。

        点 X → 等待 wait_after 秒只检测新弹窗 → 有则再关；
        无 X 时也再冷静一轮确认。
        """
        self._busy.set()
        closed = 0
        try:
            with self._nav_lock:
                for _ in range(max_rounds):
                    if self._click_one_popup():
                        closed += 1
                        if self._wait_and_watch(wait_after):
                            continue
                        break

                    # 当前无 X：冷静后再确认
                    if self._wait_and_watch(wait_after):
                        continue
                    break

            if closed > 0:
                log.info(f"弹窗清理完成，共关闭 {closed} 个")
        finally:
            self._busy.clear()
        return closed

    def _loop(self):
        """后台循环：发现弹窗则完整清理（关→冷静3s→再查），否则空闲等待。"""
        while self._running:
            if self._paused:
                time.sleep(0.5)
                continue

            if self._busy.is_set():
                time.sleep(0.2)
                continue

            if self._find_close_button() is not None:
                log.info("异步监控发现弹窗，开始关闭并冷静检测")
                self._drain_popups(max_rounds=10, wait_after=3.0)
            else:
                time.sleep(self.interval)

    # ------------------------------------------------------------------
    # 公开接口
    # ------------------------------------------------------------------

    @property
    def is_busy(self) -> bool:
        """是否正在关闭弹窗或冷静检测（截图主流程应等待）。"""
        return self._busy.is_set()

    def wait_until_idle(self, timeout: float | None = None) -> bool:
        """阻塞直到弹窗关闭/冷静流程结束。

        Args:
            timeout: 最长等待秒数；None 表示一直等。

        Returns:
            True: 已空闲；False: 超时仍 busy。
        """
        if not self._busy.is_set():
            return True
        log.info("截图流程等待弹窗冷静结束...")
        if timeout is None:
            while self._busy.is_set():
                time.sleep(0.2)
            return True
        deadline = time.time() + timeout
        while self._busy.is_set() and time.time() < deadline:
            time.sleep(0.2)
        return not self._busy.is_set()

    def close_all_popups(self, max_rounds: int = 10, wait_after: float = 3.0) -> int:
        """同步关闭所有可见弹窗（关 → 冷静检测 → 必要时再关）。"""
        return self._drain_popups(max_rounds=max_rounds, wait_after=wait_after)

    def wait_until_clear(self, seconds: float = 3.0) -> int:
        """同步等待弹窗区域冷静（同 close_all_popups）。"""
        return self.close_all_popups(max_rounds=20, wait_after=seconds)

    def start(self):
        """启动后台弹窗监控。"""
        if self._thread is not None:
            return
        self._running = True
        self._paused = False
        self._busy.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("弹窗监控已启动")

    def pause(self):
        """暂停空闲扫描（导航期间使用）。冷静中的 _drain 仍会跑完。"""
        self._paused = True

    def resume(self):
        """恢复监控。"""
        self._paused = False

    def stop(self):
        """停止后台弹窗监控。"""
        self._running = False
        self._busy.clear()
        if self._thread:
            self._thread.join(timeout=5)
            self._thread = None
        log.info(f"弹窗监控已停止（共关闭 {self._closed_count} 个）")

    @property
    def closed_count(self) -> int:
        return self._closed_count
