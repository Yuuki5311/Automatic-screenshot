"""轻量感知环：按 UI 状态决策并推进截图任务 Goal。"""

from __future__ import annotations

import random
import time
from enum import Enum
from typing import Any, Callable

from config import CLICK_INTERVAL, PAGE_LOAD_WAIT, SCREENSHOT_DELAY_MIN, SCREENSHOT_DELAY_MAX
from logger import get_logger
from screenshot_click import effect_verify_template, parse_click_item
from ui_state import (
    POPUP_CLOSE_TEMPLATES,
    POPUP_CLOSE_THRESHOLD,
    UiState,
    classify,
    popup_close_bounds,
)

log = get_logger()

UNKNOWN_TIMEOUT_S = 45.0
CLICK_EFFECT_RETRIES = 2
EFFECT_VERIFY_TIMEOUT = 5


class Action(Enum):
    CLOSE_POPUP = "close_popup"
    RELOGIN = "relogin"
    CLICK_STEP = "click_step"
    TAKE_SHOT = "take_shot"
    GO_BACK = "go_back"
    WAIT = "wait"
    RECOVER = "recover"
    FINISHED = "finished"


class Goal:
    """截图任务游标：task_index + click_index + backs_done。"""

    def __init__(self, tasks: list[tuple[str, list, int]]):
        self.tasks = tasks
        self.task_index = 0
        self.click_index = 0
        self.backs_done = 0
        self.success = 0
        self.unknown_since: float | None = None

    @property
    def done(self) -> bool:
        return self.task_index >= len(self.tasks)

    @property
    def current(self) -> tuple[str, list, int] | None:
        if self.done:
            return None
        return self.tasks[self.task_index]

    @property
    def name(self) -> str:
        cur = self.current
        return cur[0] if cur else ""

    @property
    def clicks(self) -> list:
        cur = self.current
        return cur[1] if cur else []

    @property
    def back_count(self) -> int:
        cur = self.current
        return cur[2] if cur else 0

    def phase_need_click(self) -> bool:
        return not self.done and self.click_index < len(self.clicks)

    def phase_need_shot(self) -> bool:
        return (
            not self.done
            and self.click_index >= len(self.clicks)
            and self.backs_done == 0
            and not getattr(self, "_shot_done", False)
        )

    def phase_need_back(self) -> bool:
        return (
            not self.done
            and getattr(self, "_shot_done", False)
            and self.backs_done < self.back_count
        )

    def path_templates(self) -> list[str]:
        """当前步骤相关模板（供 ON_PATH 探测）。"""
        if self.done:
            return []
        if self.phase_need_click():
            item = self.clicks[self.click_index]
            parsed = parse_click_item(item)
            if parsed["template"] == "__coords__":
                return [parsed["anchor"]] if parsed["anchor"] else []
            return [parsed["template"]]
        if self.phase_need_back():
            return ["back_arrow.png"]
        # shot 阶段：用本任务最后一击模板或 tab
        if self.clicks:
            last = parse_click_item(self.clicks[-1])
            if last["template"] != "__coords__":
                return [last["template"]]
            if last["anchor"]:
                return [last["anchor"]]
        return []

    def mark_shot_done(self) -> None:
        self._shot_done = True
        self.success += 1

    def advance_after_click(self) -> None:
        self.click_index += 1

    def advance_after_back(self) -> None:
        self.backs_done += 1
        if self.backs_done >= self.back_count:
            self._next_task()

    def advance_after_shot_no_back(self) -> None:
        if self.back_count <= 0:
            self._next_task()

    def rewind_to_previous_step(self) -> str:
        """游标回退到上一步，供返回未生效等场景重试。

        优先级：待返回/已截图 → 回到本任务最后一次点击；
        仍有前置点击 → click_index-1；否则回到上一任务重做。
        """
        if getattr(self, "_shot_done", False) or self.backs_done > 0:
            self._shot_done = False
            self.backs_done = 0
            if self.success > 0:
                self.success -= 1
            self.click_index = max(0, len(self.clicks) - 1) if self.clicks else 0
            return f"回退到本任务点击步骤: {self.name}"

        if self.click_index > 0:
            self.click_index -= 1
            return f"回退到点击[{self.click_index}]: {self.name}"

        if self.task_index > 0:
            self.task_index -= 1
            self.click_index = 0
            self.backs_done = 0
            self._shot_done = False
            return f"回退到上一任务: {self.name}"

        self.click_index = 0
        self.backs_done = 0
        self._shot_done = False
        return f"已在首步，重置: {self.name}"

    def _next_task(self) -> None:
        self.task_index += 1
        self.click_index = 0
        self.backs_done = 0
        self._shot_done = False

    def note_unknown(self, now: float | None = None) -> None:
        now = time.time() if now is None else now
        if self.unknown_since is None:
            self.unknown_since = now

    def clear_unknown(self) -> None:
        self.unknown_since = None

    def unknown_timed_out(self, now: float | None = None) -> bool:
        if self.unknown_since is None:
            return False
        now = time.time() if now is None else now
        return (now - self.unknown_since) >= UNKNOWN_TIMEOUT_S


def decide(state: UiState, goal: Goal) -> Action:
    """根据 (UiState, Goal) 选择动作。

    - POPUP / LOGIN 永远优先。
    - 点击导航需要 MAIN/ON_PATH（大厅或路径入口可见）。
    - 截图/返回在内容子页进行：此时头像与入口按钮常消失，
      UNKNOWN 也允许 TAKE_SHOT / GO_BACK（否则进灵宝等页会卡死）。
    """
    if goal.done:
        return Action.FINISHED

    if state == UiState.POPUP:
        return Action.CLOSE_POPUP

    if state == UiState.LOGIN:
        return Action.RELOGIN

    # 本任务点击已完成：优先截图 / 返回，不要求仍识别为主界面
    if not goal.phase_need_click():
        if not getattr(goal, "_shot_done", False):
            return Action.TAKE_SHOT
        if goal.phase_need_back():
            return Action.GO_BACK
        return Action.WAIT

    # 还需要点击入口：必须在可导航界面
    if state in (UiState.MAIN, UiState.ON_PATH):
        return Action.CLICK_STEP

    if state == UiState.UNKNOWN:
        if goal.unknown_timed_out():
            return Action.RECOVER
        return Action.WAIT

    return Action.WAIT


class UiLoop:
    """截图阶段感知环。"""

    def __init__(
        self,
        nav,
        shot,
        tasks: list[tuple[str, list, int]],
        stop_event=None,
        on_log: Callable[[str, str], None] | None = None,
        on_progress: Callable[[int, int], None] | None = None,
        recover: Callable[[], bool] | None = None,
        relogin: Callable[[], bool] | None = None,
        tick_s: float = 0.5,
        classify_fn=None,
    ):
        self.nav = nav
        self.shot = shot
        self.goal = Goal(tasks)
        self.stop_event = stop_event
        self.on_log = on_log or (lambda text, level="info": None)
        self.on_progress = on_progress or (lambda cur, total: None)
        self.recover = recover
        self.relogin = relogin
        self.tick_s = tick_s
        self.classify_fn = classify_fn or classify
        self._total = len(tasks)

    def _stopped(self) -> bool:
        return bool(self.stop_event is not None and self.stop_event.is_set())

    def _log(self, text: str, level: str = "info") -> None:
        self.on_log(text, level)
        if level == "error":
            log.error(text)
        elif level == "warn":
            log.warning(text)
        else:
            log.info(text)

    def run(self) -> int:
        """跑完返回成功截图数。"""
        self._log("感知环启动（截图阶段）")
        while not self._stopped():
            if self.goal.done:
                break

            path_tpls = [
                t for t in self.goal.path_templates() if t and t.endswith(".png")
            ]
            state, info = self.classify_fn(self.nav, path_tpls)
            action = decide(state, self.goal)

            if state == UiState.UNKNOWN:
                self.goal.note_unknown()
            else:
                self.goal.clear_unknown()

            if action == Action.FINISHED:
                break

            self._log(
                f"状态={state.value} 动作={action.value} "
                f"任务[{self.goal.task_index + 1}/{self._total}] {self.goal.name}"
            )
            self.on_progress(self.goal.task_index, self._total)

            if action == Action.CLOSE_POPUP:
                self._close_popup()
            elif action == Action.CLICK_STEP:
                self._do_click_step()
            elif action == Action.TAKE_SHOT:
                self._do_shot()
            elif action == Action.GO_BACK:
                self._do_back()
            elif action == Action.WAIT:
                time.sleep(self.tick_s)
            elif action == Action.RELOGIN:
                ok = self.relogin() if self.relogin else False
                if not ok:
                    self._log("游戏重登失败", "error")
                    break
            elif action == Action.RECOVER:
                ok = self.recover() if self.recover else False
                if not ok:
                    self._log("恢复失败", "error")
                    break
                # 从当前任务重试
                self.goal.click_index = 0
                self.goal.backs_done = 0
                self.goal._shot_done = False
                self.goal.clear_unknown()
            else:
                time.sleep(self.tick_s)

            if action not in (Action.WAIT,):
                time.sleep(self.tick_s)

        self._log(f"感知环结束: {self.goal.success}/{self._total} 张成功", "success")
        return self.goal.success

    def _close_popup(self) -> None:
        vw, vh = self.nav.viewport_size()
        bounds = popup_close_bounds(vw, vh)
        for tpl in POPUP_CLOSE_TEMPLATES:
            if self.nav.find_and_click(
                tpl,
                timeout=2,
                bounds=bounds,
                threshold=POPUP_CLOSE_THRESHOLD,
                allow_fallback=False,
            ):
                self._log(f"已关闭弹窗 ({tpl})", "success")
                time.sleep(CLICK_INTERVAL)
                return
        self._log("判为弹窗但未点到关闭按钮", "warn")

    def _popup_pending(self) -> bool:
        """点击前再截一帧，检测关闭按钮是否出现。"""
        from ui_state import match_score

        screen = self.nav._get_screenshot()
        vh, vw = screen.shape[:2]
        bounds = popup_close_bounds(vw, vh)
        for tpl in POPUP_CLOSE_TEMPLATES:
            if match_score(self.nav, tpl, bounds=bounds, screen=screen) >= POPUP_CLOSE_THRESHOLD:
                return True
        return False

    def _ensure_clear_for_click(self) -> bool:
        """有弹窗则关闭并取消本轮主线点击；返回是否可继续点击。"""
        if self._popup_pending():
            self._log("点击前检测到弹窗，取消主线动作", "warn")
            self._close_popup()
            return False
        return True

    def _back_verify_template(self) -> str | None:
        """本次返回若会结束当前任务，用下一任务首个入口模板做生效校验。"""
        if self.goal.backs_done + 1 < self.goal.back_count:
            return None
        next_i = self.goal.task_index + 1
        if next_i >= len(self.goal.tasks):
            return None
        clicks = self.goal.tasks[next_i][1]
        if not clicks:
            return None
        parsed = parse_click_item(clicks[0])
        if parsed["template"] == "__coords__":
            return parsed["anchor"] if parsed["anchor"] else None
        return parsed["template"]

    def _drain_popups_briefly(self, rounds: int = 3) -> None:
        """返回点击后可能立刻弹窗；先清掉再做生效校验。"""
        for _ in range(rounds):
            if self._stopped():
                return
            if not self._popup_pending():
                return
            self._close_popup()
            time.sleep(CLICK_INTERVAL)

    def _do_click_step(self) -> None:
        if not self.goal.phase_need_click():
            return
        if not self._ensure_clear_for_click():
            return
        self._log(f"[{self.goal.task_index + 1}/{self._total}] {self.goal.name}")
        item = self.goal.clicks[self.goal.click_index]
        parsed = parse_click_item(item)
        template = parsed["template"]
        desc = parsed["desc"]
        bounds = parsed["bounds"]
        next_item = (
            self.goal.clicks[self.goal.click_index + 1]
            if self.goal.click_index + 1 < len(self.goal.clicks)
            else None
        )
        verify_tpl = effect_verify_template(next_item)

        from click_confirm import (
            execute_click_with_confirm,
            plan_coords_click,
            plan_template_click,
        )

        for attempt in range(1, CLICK_EFFECT_RETRIES + 2):
            if self._stopped():
                return
            screen = self.nav._get_screenshot()
            if template == "__coords__":
                x, y = bounds
                plan = plan_coords_click(screen, x, y)
                clicked = execute_click_with_confirm(self.nav, plan)
                if clicked:
                    self._log(f"  坐标点击 ({x}, {y})")
            else:
                plan = plan_template_click(
                    self.nav, screen, template, bounds=bounds
                )
                if plan is None:
                    self._log(f"  找不到 {template}", "warn")
                    return
                self._log(
                    f"  计划点击 {template} @ ({plan.x},{plan.y}) "
                    f"置信度 {plan.score:.2f}"
                )
                clicked = execute_click_with_confirm(self.nav, plan)

            if not clicked:
                self._log(f"  点击已取消（ROI 未确认）: {desc}", "warn")
                return

            if verify_tpl is None:
                self.goal.advance_after_click()
                return

            if self.nav.wait_for_template(verify_tpl, timeout=EFFECT_VERIFY_TIMEOUT):
                self.goal.advance_after_click()
                return

            self._log(
                f"  点击后未出现 {verify_tpl}，重试 ({attempt}/{CLICK_EFFECT_RETRIES + 1})",
                "warn",
            )
            self._close_popup()

        self._log(f"  点击未生效: {desc}", "warn")

    def _do_shot(self) -> None:
        time.sleep(PAGE_LOAD_WAIT)
        name = self.goal.name
        self.shot.take(name)
        self.goal.mark_shot_done()
        self._log(f"  已截图: {name}", "success")
        if self.goal.back_count <= 0:
            delay = random.uniform(SCREENSHOT_DELAY_MIN, SCREENSHOT_DELAY_MAX)
            self._log(f"  等待 {delay:.1f}s...")
            time.sleep(delay)
            self.goal.advance_after_shot_no_back()

    def _do_back(self) -> None:
        """点击返回；Pass2 ROI 确认后才派发；点后再生效校验。"""
        if not self._ensure_clear_for_click():
            return
        prev_index = self.goal.task_index
        verify_tpl = self._back_verify_template()

        from click_confirm import execute_click_with_confirm, plan_template_click

        screen = self.nav._get_screenshot()
        plan = plan_template_click(self.nav, screen, "back_arrow.png")
        if plan is None:
            self._log("  未找到返回箭头", "warn")
            return
        self._log(
            f"  计划返回 @ ({plan.x},{plan.y}) 置信度 {plan.score:.2f}"
        )
        if not execute_click_with_confirm(self.nav, plan):
            self._log("  返回点击已取消（ROI 未确认）", "warn")
            return

        time.sleep(1.0)
        self._drain_popups_briefly()

        if verify_tpl:
            if not self.nav.wait_for_template(verify_tpl, timeout=EFFECT_VERIFY_TIMEOUT):
                msg = self.goal.rewind_to_previous_step()
                self._log(
                    f"  返回未生效（未出现 {verify_tpl}），{msg}",
                    "warn",
                )
                self._recover_toward_current_step()
                return

        self.goal.advance_after_back()
        if self.goal.task_index > prev_index:
            delay = random.uniform(SCREENSHOT_DELAY_MIN, SCREENSHOT_DELAY_MAX)
            self._log(f"  等待 {delay:.1f}s...")
            time.sleep(delay)

    def _recover_toward_current_step(self) -> None:
        """回退游标后，尽量点返回/关弹窗直到当前步骤入口可见。"""
        path = [
            t for t in self.goal.path_templates() if t and t.endswith(".png")
        ]
        target = path[0] if path else None
        for _ in range(3):
            if self._stopped():
                return
            self._drain_popups_briefly(rounds=1)
            if target and self.nav.wait_for_template(target, timeout=2):
                return
            self.nav.find_and_click("back_arrow.png", timeout=2)
            time.sleep(CLICK_INTERVAL)
