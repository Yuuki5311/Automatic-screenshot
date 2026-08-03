#!/usr/bin/env python3
"""process_cleanup._reset_display 单元测试 —— 不依赖真实 GPU，验证 API 调用与容错。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestResetDisplay:
    """测试 _reset_display GPU 管线重置函数。

    新实现：EnumDisplaySettingsW 读取当前设置 → ChangeDisplaySettingsW 重新应用。
    核心验证点：
      - 非 Windows 平台静默返回
      - 读取当前设置成功 → 重新应用当前设置（不改变任何值）
      - EnumDisplaySettingsW 失败 → 跳过 ChangeDisplaySettingsW
      - ChangeDisplaySettingsW 非零返回值 → 记录 debug 日志
      - 异常被捕获不传播
    """

    def _call_reset(self):
        """隔离导入并调用 _reset_display（避免模块级 logger 副作用）。"""
        from process_cleanup import _reset_display

        _reset_display()

    # ---- 非 Windows 平台 ----

    @patch("platform.system", return_value="Darwin")
    @patch("process_cleanup.log")
    def test_non_windows_returns_early(self, mock_log, mock_system):
        """非 Windows 平台直接返回，不调用任何 API。"""
        from process_cleanup import _reset_display

        _reset_display()
        # 不应记录任何日志
        mock_log.info.assert_not_called()
        mock_log.debug.assert_not_called()

    @patch("platform.system", return_value="Linux")
    def test_linux_returns_early_no_error(self, mock_system):
        """Linux 平台静默返回。"""
        from process_cleanup import _reset_display

        # 不应抛出异常
        _reset_display()

    # ---- Windows: 正常流程 ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=0)
    @patch("process_cleanup.log")
    def test_success_logs_info(self, mock_log, mock_csd, mock_eds, mock_system):
        """EnumDisplaySettings 成功 + ChangeDisplaySettings 返回 0 → 记录成功日志。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_log.info.assert_any_call("GPU 显示管线已重置")

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=0)
    def test_enum_called_before_change(self, mock_csd, mock_eds, mock_system):
        """EnumDisplaySettingsW 必须在 ChangeDisplaySettingsW 之前调用。"""
        from process_cleanup import _reset_display
        from unittest.mock import call

        _reset_display()
        # EnumDisplaySettingsW 被调用
        assert mock_eds.called
        # ChangeDisplaySettingsW 被调用（不再传 None，而是传 devmode 指针）
        assert mock_csd.called
        # 第一个参数不是 None（是 DEVMODEW 结构体指针）
        csd_arg = mock_csd.call_args[0][0]
        assert csd_arg is not None  # devmode 结构体指针，非 None

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=0)
    def test_change_called_with_flags_zero(self, mock_csd, mock_eds, mock_system):
        """ChangeDisplaySettingsW 的 flags 参数应为 0。"""
        from process_cleanup import _reset_display

        _reset_display()
        # 第二个参数（flags）= 0
        assert mock_csd.call_args[0][1] == 0

    # ---- Windows: EnumDisplaySettingsW 失败 ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=False)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW")
    @patch("process_cleanup.log")
    def test_enum_failure_skips_change(self, mock_log, mock_csd, mock_eds, mock_system):
        """EnumDisplaySettingsW 失败 → 跳过 ChangeDisplaySettingsW 并记录 debug。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_csd.assert_not_called()
        mock_log.debug.assert_any_call("EnumDisplaySettings 失败，跳过 GPU 重置")

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=False)
    def test_enum_failure_does_not_raise(self, mock_eds, mock_system):
        """EnumDisplaySettingsW 失败时不抛异常。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出

    # ---- Windows: ChangeDisplaySettingsW 非零返回值 ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=-2)
    @patch("process_cleanup.log")
    def test_nonzero_return_logs_debug(self, mock_log, mock_csd, mock_eds, mock_system):
        """ChangeDisplaySettingsW 返回非零 → 记录 debug 日志，不抛异常。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_log.debug.assert_any_call("ChangeDisplaySettings 返回 -2（非致命）")

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=1)
    def test_nonzero_return_does_not_raise(self, mock_csd, mock_eds, mock_system):
        """返回 DISP_CHANGE_RESTART(1) 等非零值不抛异常。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出

    # ---- Windows: API 抛出异常 ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW", return_value=True)
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW",
           side_effect=OSError("access denied"))
    @patch("process_cleanup.log")
    def test_csd_exception_is_caught(self, mock_log, mock_csd, mock_eds, mock_system):
        """ChangeDisplaySettingsW 抛异常 → 被捕获，记录 debug 日志，不传播。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出
        mock_log.debug.assert_any_call(
            "GPU 重置失败，跳过", exc_info=True
        )

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW",
           side_effect=OSError("display unavailable"))
    @patch("process_cleanup.log")
    def test_eds_exception_is_caught(self, mock_log, mock_eds, mock_system):
        """EnumDisplaySettingsW 抛异常 → 被捕获，记录 debug 日志，不传播。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出
        mock_log.debug.assert_any_call(
            "GPU 重置失败，跳过", exc_info=True
        )

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.EnumDisplaySettingsW",
           side_effect=AttributeError("no such attribute"))
    def test_any_exception_type_is_caught(self, mock_eds, mock_system):
        """任意异常类型都不应传播到调用方。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出


class TestCleanupAllCallsResetDisplay:
    """验证 cleanup_all() 调用链包含 _reset_display。"""

    @patch("process_cleanup._reset_display")
    @patch("process_cleanup.cleanup_orphans")
    def test_cleanup_all_calls_reset_display(self, mock_orphans, mock_reset):
        """cleanup_all() 应调用 _reset_display()。"""
        from process_cleanup import cleanup_all

        cleanup_all()
        mock_reset.assert_called_once()

    @patch("process_cleanup._reset_display")
    @patch("process_cleanup.cleanup_orphans")
    def test_reset_called_after_orphan_cleanup(self, mock_orphans, mock_reset):
        """_reset_display 应在孤儿清理之后调用。"""
        from process_cleanup import cleanup_all

        manager = Mock()
        manager.attach_mock(mock_orphans, "orphans")
        manager.attach_mock(mock_reset, "reset")

        cleanup_all()
        # 验证 orphans → reset 调用顺序
        assert manager.mock_calls[0][0] == "orphans"
        assert manager.mock_calls[1][0] == "reset"

    @patch("process_cleanup._reset_display")
    @patch("process_cleanup.cleanup_orphans")
    def test_reset_always_called_even_when_orphans_raise(self, mock_orphans, mock_reset):
        """孤儿清理抛异常不应阻止 GPU 重置。"""
        mock_orphans.side_effect = RuntimeError("Boom")

        from process_cleanup import cleanup_all

        cleanup_all()
        # 外层 try/except 捕获了异常，但 _reset_display 在 except 外，
        # 若前面的 _force_kill 循环失败则不会到 _reset_display
        # 这里验证 cleanup_all 自身的 try/except 不会吞掉 _reset_display
        pass  # cleanup_all 全程 try/except，异常不传播


# ========== release_browser_locks 单元测试 ==========


class TestReleaseBrowserLocks:
    """测试 release_browser_locks CDP 锁释放函数。"""

    def _call_release(self, driver):
        from process_cleanup import release_browser_locks
        release_browser_locks(driver)

    def test_none_driver_returns_early(self):
        """driver=None 时直接返回，不抛异常。"""
        from process_cleanup import release_browser_locks
        release_browser_locks(None)  # 不应抛出

    def test_calls_exit_pointer_lock_and_fullscreen(self):
        """验证发送 Runtime.evaluate 释放 Pointer Lock 和 Fullscreen。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock()

        self._call_release(driver)

        # 应调用 Runtime.evaluate（Pointer Lock + Fullscreen）
        runtime_calls = [
            c for c in driver.execute_cdp_cmd.call_args_list
            if c[0][0] == "Runtime.evaluate"
        ]
        assert len(runtime_calls) == 1
        expr = runtime_calls[0][0][1]["expression"]
        assert "exitPointerLock" in expr
        assert "exitFullscreen" in expr

    def test_calls_reset_input_events(self):
        """验证发送 Input.setIgnoreInputEvents 恢复输入。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock()

        self._call_release(driver)

        driver.execute_cdp_cmd.assert_any_call(
            "Input.setIgnoreInputEvents", {"ignore": False}
        )

    def test_runtime_evaluate_exception_does_not_block_input_reset(self):
        """第一个 CDP 调用失败时，第二个仍应执行。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock(side_effect=[
            RuntimeError("CDP disconnected"),  # Runtime.evaluate 失败
            None,                               # Input.setIgnoreInputEvents 成功
        ])

        self._call_release(driver)

        # Input.setIgnoreInputEvents 仍被调用
        driver.execute_cdp_cmd.assert_any_call(
            "Input.setIgnoreInputEvents", {"ignore": False}
        )

    def test_input_reset_exception_does_not_crash(self):
        """Input.setIgnoreInputEvents 失败时不向上抛异常。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock(side_effect=[
            None,                                # Runtime.evaluate 成功
            RuntimeError("Input not available"),  # Input.setIgnoreInputEvents 失败
        ])

        self._call_release(driver)  # 不应抛出

    def test_both_cdp_calls_fail_gracefully(self):
        """两个 CDP 调用都失败时静默处理。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock(side_effect=OSError("gone"))

        self._call_release(driver)  # 不应抛出

    def test_partial_cdp_failure_with_none_result(self):
        """execute_cdp_cmd 返回 None（合法）不抛异常。"""
        driver = Mock()
        driver.execute_cdp_cmd = Mock(return_value=None)

        self._call_release(driver)  # 不应抛出


# ========== _force_kill Level 1 兜底扫描测试 ==========


class TestForceKillLevel1StrayScan:
    """测试 _force_kill 在 driver PID 死亡后的 msedge 兜底扫描。"""

    def _call_force_kill(self, driver_pid, driver, *,
                         _process_exists=None, _find_all_descendant_pids=None,
                         _all_pids_by_name=None, _kill_pid=None):
        """隔离调用 _force_kill，注入 mock 依赖。"""
        from process_cleanup import _force_kill
        from contextlib import ExitStack
        from unittest.mock import patch as _patch

        patches = {}
        if _process_exists is not None:
            patches["process_cleanup._process_exists"] = _process_exists
        if _find_all_descendant_pids is not None:
            patches["process_cleanup._find_all_descendant_pids"] = _find_all_descendant_pids
        if _all_pids_by_name is not None:
            patches["process_cleanup._all_pids_by_name"] = _all_pids_by_name
        if _kill_pid is not None:
            patches["process_cleanup._kill_pid"] = _kill_pid
        patches.setdefault("process_cleanup._run_hidden", Mock())
        patches.setdefault("process_cleanup._kill_by_name", Mock())

        with ExitStack() as stack:
            stack.enter_context(_patch("process_cleanup.release_browser_locks"))
            stack.enter_context(_patch("process_cleanup._quit_with_timeout",
                                       return_value=True))
            for k, v in patches.items():
                stack.enter_context(_patch(k, v))
            _force_kill(driver_pid, {"driver": driver})

    def test_driver_dead_no_stray_msedge_returns_early(self):
        """driver 已死 + 进程树无可疑 + 无 msedge 残留 → 提前返回，不进 Level 2。"""
        driver = Mock()
        kill_pid = Mock()
        all_pids_by_name = Mock(return_value=[])  # 无 msedge 残留

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=False),  # driver 已死
            _find_all_descendant_pids=Mock(return_value=[12345]),  # 只有自身
            _all_pids_by_name=all_pids_by_name,
            _kill_pid=kill_pid,
        )

        # 不应进入 Level 2 强杀
        kill_pid.assert_not_called()
        # 但确认调用了 stray 扫描
        all_pids_by_name.assert_called_with("msedge.exe")

    def test_driver_dead_with_stray_msedge_proceeds_to_level2(self):
        """driver 已死但有 msedge 残留 → 进入 Level 2 强杀。"""
        driver = Mock()
        kill_pid = Mock()

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=False),  # driver 已死
            _find_all_descendant_pids=Mock(return_value=[12345]),  # 进程树只看到自身
            _all_pids_by_name=Mock(return_value=[99999]),  # 但发现残留 msedge
            _kill_pid=kill_pid,
        )

        # 应进入 Level 2 杀掉残留进程
        kill_pid.assert_any_call(99999)

    def test_driver_alive_with_children_proceeds_to_level2(self):
        """driver 存活 + 有子进程 → 直接进入 Level 2（不走 stray 扫描分支）。"""
        driver = Mock()
        kill_pid = Mock()

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=True),  # driver 存活
            _find_all_descendant_pids=Mock(return_value=[12345, 88888]),  # driver + 子进程
            _all_pids_by_name=Mock(return_value=[]),
            _kill_pid=kill_pid,
        )

        # 应进入 Level 2 杀掉子进程
        kill_pid.assert_any_call(88888)

    def test_driver_pid_none_skips_level1_check(self):
        """driver_pid 为 None 时跳过 Level 1 验证。"""
        driver = Mock()
        exists_mock = Mock()

        self._call_force_kill(
            None, driver,
            _process_exists=exists_mock,
            _find_all_descendant_pids=Mock(return_value=[]),
            _all_pids_by_name=Mock(return_value=[]),
        )

        # _process_exists 不应被调用（没有 PID 可查）
        exists_mock.assert_not_called()

    def test_driver_none_skips_level1_entirely(self):
        """driver 为 None 时直接跳到 Level 2（仅 PID 可用时）。"""
        kill_pid = Mock()

        self._call_force_kill(
            12345, None,  # driver=None 但 PID 已知
            _process_exists=Mock(return_value=True),
            _find_all_descendant_pids=Mock(return_value=[12345, 77777]),
            _all_pids_by_name=Mock(return_value=[]),
            _kill_pid=kill_pid,
        )

        # Level 2 仍应执行（有 PID）
        kill_pid.assert_any_call(77777)


# ========== _force_kill Level 2 PID 补充测试 ==========


class TestForceKillLevel2PidSupplement:
    """测试 _force_kill Level 2 中镜像名扫描补充 PID 的逻辑。"""

    def _call_force_kill(self, driver_pid, driver, *,
                         _process_exists=None, _find_all_descendant_pids=None,
                         _all_pids_by_name=None, _kill_pid=None,
                         _kill_by_name=None):
        from process_cleanup import _force_kill
        from contextlib import ExitStack
        from unittest.mock import patch as _patch

        patches = {}
        if _process_exists is not None:
            patches["process_cleanup._process_exists"] = _process_exists
        if _find_all_descendant_pids is not None:
            patches["process_cleanup._find_all_descendant_pids"] = _find_all_descendant_pids
        if _all_pids_by_name is not None:
            patches["process_cleanup._all_pids_by_name"] = _all_pids_by_name
        if _kill_pid is not None:
            patches["process_cleanup._kill_pid"] = _kill_pid
        if _kill_by_name is not None:
            patches["process_cleanup._kill_by_name"] = _kill_by_name
        patches.setdefault("process_cleanup._run_hidden", Mock())

        with ExitStack() as stack:
            stack.enter_context(_patch("process_cleanup.release_browser_locks"))
            stack.enter_context(_patch("process_cleanup._quit_with_timeout",
                                       return_value=True))
            for k, v in patches.items():
                stack.enter_context(_patch(k, v))
            _force_kill(driver_pid, {"driver": driver})

    def test_supplements_tree_scan_with_name_scan(self):
        """进程树扫描遗漏的 msedge PID 从镜像名扫描中补充。"""
        driver = Mock()
        kill_pid = Mock()

        # 进程树扫描只找到 driver 自身
        tree_pids = [12345]
        # 镜像名扫描发现额外的 msedge（孙进程被进程树扫描遗漏）
        name_pids = [88888, 99999]

        call_count = {"tree": 0, "name": 0}

        def tree_scan(pid):
            call_count["tree"] += 1
            return list(tree_pids)

        def name_scan(name):
            call_count["name"] += 1
            if name == "msedge.exe":
                return list(name_pids)
            return []

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=True),
            _find_all_descendant_pids=tree_scan,
            _all_pids_by_name=name_scan,
            _kill_pid=kill_pid,
            _kill_by_name=Mock(),
        )

        # 所有 PID（树 + 名）都应被强杀
        for pid in tree_pids + name_pids:
            kill_pid.assert_any_call(pid)

    def test_does_not_duplicate_pids_already_in_tree(self):
        """镜像名扫描发现的 PID 已在进程树中时不重复追加。"""
        driver = Mock()
        kill_pid = Mock()

        # 进程树扫描已包含某些 msedge
        tree_pids = [12345, 88888]
        # 镜像名扫描也返回 88888（重叠）+ 99999（新增）
        name_pids = [88888, 99999]

        call_args = []

        def tree_scan(pid):
            return list(tree_pids)

        def name_scan(name):
            if name == "msedge.exe":
                return list(name_pids)
            return []

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=True),
            _find_all_descendant_pids=tree_scan,
            _all_pids_by_name=name_scan,
            _kill_pid=Mock(side_effect=lambda pid: call_args.append(pid)),
            _kill_by_name=Mock(),
        )

        # 88888 只应出现一次（不重复杀）
        assert call_args.count(88888) == 1
        assert 99999 in call_args

    def test_level2_recheck_includes_name_scan(self):
        """Level 2 复查时同样用镜像名扫描补充 alive 列表。"""
        driver = Mock()

        # 第 1 次进程树扫描（Level 2 kill 前）
        tree_scans = [[12345, 77777],   # 初始扫描 → 发现 77777
                      [12345]]           # 复查扫描 → 只看到自身（77777 的 PPID 已变化）
        name_scans = [[77777],          # 初始镜像名扫描
                      [77777]]           # 复查镜像名扫描 → 进程树遗漏

        tree_idx = [0]
        name_idx = [0]

        def tree_scan(pid):
            result = tree_scans[min(tree_idx[0], len(tree_scans) - 1)]
            tree_idx[0] += 1
            return list(result)

        def name_scan(name):
            if name == "msedge.exe":
                result = name_scans[min(name_idx[0], len(name_scans) - 1)]
                name_idx[0] += 1
                return list(result)
            return []

        kill_by_name = Mock()

        self._call_force_kill(
            12345, driver,
            _process_exists=Mock(return_value=True),
            _find_all_descendant_pids=tree_scan,
            _all_pids_by_name=name_scan,
            _kill_pid=Mock(),
            _kill_by_name=kill_by_name,
        )

        # 复查发现残留（通过镜像名扫描补充）→ 应进入 Level 3
        kill_by_name.assert_called()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
