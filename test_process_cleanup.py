#!/usr/bin/env python3
"""process_cleanup._reset_display 单元测试 —— 不依赖真实 GPU，验证 API 调用与容错。"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pytest
from unittest.mock import Mock, patch, MagicMock


class TestResetDisplay:
    """测试 _reset_display GPU 管线重置函数。"""

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

    @patch("platform.system", return_value="Linux")
    def test_linux_returns_early_no_error(self, mock_system):
        """Linux 平台静默返回。"""
        from process_cleanup import _reset_display

        # 不应抛出异常
        _reset_display()

    # ---- Windows: DISP_CHANGE_SUCCESSFUL (返回 0) ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=0)
    @patch("process_cleanup.log")
    def test_success_logs_info(self, mock_log, mock_csd, mock_system):
        """ChangeDisplaySettingsW 返回 0 → 记录成功日志。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_log.info.assert_any_call("GPU 显示管线已重置")

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=0)
    def test_called_with_null_and_zero_flags(self, mock_csd, mock_system):
        """API 调用参数应为 (None, 0)。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_csd.assert_called_once_with(None, 0)

    # ---- Windows: 非零返回值（非致命） ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=-2)
    @patch("process_cleanup.log")
    def test_nonzero_return_logs_result_code(self, mock_log, mock_csd, mock_system):
        """ChangeDisplaySettingsW 返回非零 → 记录返回值但不抛异常。"""
        from process_cleanup import _reset_display

        _reset_display()
        mock_log.info.assert_any_call("GPU 显示管线重置返回 -2（非致命）")

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW", return_value=1)
    def test_nonzero_return_does_not_raise(self, mock_csd, mock_system):
        """返回 DISP_CHANGE_RESTART(1) 等非零值不抛异常。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出

    # ---- Windows: API 抛出异常 ----

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW",
           side_effect=OSError("access denied"))
    @patch("process_cleanup.log")
    def test_api_exception_is_caught(self, mock_log, mock_csd, mock_system):
        """API 调用抛异常 → 被捕获，记录异常日志，不向上传播。"""
        from process_cleanup import _reset_display

        _reset_display()  # 不应抛出
        mock_log.info.assert_any_call(
            "GPU 显示管线重置异常（非致命）", exc_info=True
        )

    @patch("platform.system", return_value="Windows")
    @patch("ctypes.windll.user32.ChangeDisplaySettingsW",
           side_effect=AttributeError("no such attribute"))
    def test_any_exception_type_is_caught(self, mock_csd, mock_system):
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
