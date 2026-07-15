"""异步弹窗监控模块。

后台线程定期扫描屏幕，发现弹窗关闭按钮（popup_close.png）自动点击关闭。
"""

import time
import threading

import pyautogui

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

        一轮内遍历所有按钮模板，尽可能关闭多个弹窗。
        如果点击 X 按钮无效，兜底点击屏幕空白区域。
        """
        if self.navigator is None:
            return False
        try:
            if self.navigator.driver is not None:
                # Selenium 截图：CSS 像素固定尺寸
                from config import BROWSER_WIDTH, BROWSER_HEIGHT
                css_w, css_h = BROWSER_WIDTH, BROWSER_HEIGHT
                top_bounds = (0, 0, css_w, css_h // 2)
                bottom_bounds = (0, css_h // 2, css_w, css_h // 2)
            else:
                # 回退：PyAutoGUI 物理像素
                sw, sh = pyautogui.size()
                scale = self.navigator._scale
                top_bounds = (0, 0, int(sw * scale), int(sh * scale * 0.5))
                bottom_bounds = (0, int(sh * scale * 0.5), int(sw * scale), int(sh * scale * 0.5))

            # (模板文件, 搜索区域, 标签, 置信度阈值)
            # 阈值None则使用Navigator默认值(0.53)
            buttons = [
                ("popup_close.png", top_bounds, "X按钮", 0.85),
                ("popup_close_small.png", top_bounds, "小弹窗X按钮", 0.85),
                ("game_logout_confirm.png", bottom_bounds, "确认按钮", None),
                ("game_popup_confirm.png", bottom_bounds, "通用确认", None),
            ]

            found_any = False
            closed_this_round = 0

            for template, bounds, label, threshold in buttons:
                kwargs = {}
                if threshold is not None:
                    kwargs["threshold"] = threshold

                if self.navigator.wait_for_template(template, timeout=1, **kwargs):
                    # 双重校验：等待 0.5s 后再次确认
                    # 按钮在弹窗出现后 0.5~1s 内处于禁用状态
                    time.sleep(0.5)
                    if not self.navigator.wait_for_template(template, timeout=0.5, **kwargs):
                        continue
                    found_any = True
                    # 等待按钮完全可点击（距首次检测至少 1s）
                    time.sleep(2)
                    if self.navigator.find_and_click(template, timeout=2, bounds=bounds, **kwargs):
                        # 关闭后等待 0.5s 冷却期
                        time.sleep(1)
                        if not self.navigator.wait_for_template(template, timeout=1, **kwargs):
                            self._closed_count += 1
                            closed_this_round += 1
                            log.info(f"异步关闭弹窗 #{self._closed_count} ({label})")
                            break  # 关一个就退出，多的由外层循环处理
                        else:
                            log.debug(f"点击 {label} 后仍在，尝试下一个")

            # 兜底：有弹窗但本轮一个都没关掉时，点击屏幕空白区域
            if found_any and closed_this_round == 0:
                log.debug("兜底：点击空白区域尝试消除弹窗")
                pyautogui.click(int(sw * 0.5), int(sh * 0.85))

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
