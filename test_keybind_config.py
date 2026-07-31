#!/usr/bin/env python3
"""keybind_config 模块单元测试 —— 不依赖真实浏览器，验证模块导入与逻辑正确性。"""

import os
import sys
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pytest

from keybind_config import (
    configure_keybinding,
    _load_keybind_coords,
    KEYBIND_EDIT_BTN,
    KEYBIND_SAVE_BTN,
    KEYBIND_CLICK_COORD_KEY,
    MAX_RETRIES,
)


class TestLoadKeybindCoords:
    """测试 _load_keybind_coords 坐标读取。"""

    def test_returns_coords_when_key_exists(self):
        """坐标文件中存在 keybind_pos 时返回正确坐标。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"keybind_pos": [123, 456]}, f)
            tmp_path = f.name

        try:
            with patch("keybind_config.resource_path", return_value=tmp_path):
                result = _load_keybind_coords()
                assert result == (123, 456)
        finally:
            os.unlink(tmp_path)

    def test_returns_none_when_file_missing(self):
        """坐标文件不存在时返回 None。"""
        with patch("keybind_config.resource_path", return_value="/nonexistent/coords.json"):
            result = _load_keybind_coords()
            assert result is None

    def test_returns_none_when_key_missing(self):
        """坐标文件中缺少 keybind_pos 时返回 None。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"other_key": [1, 2]}, f)
            tmp_path = f.name

        try:
            with patch("keybind_config.resource_path", return_value=tmp_path):
                result = _load_keybind_coords()
                assert result is None
        finally:
            os.unlink(tmp_path)


class TestConfigureKeybinding:
    """测试 configure_keybinding 主函数的各条分支。"""

    def _make_nav(self, find_results=None):
        """构造 mock Navigator，find_and_click 按顺序返回结果。"""
        nav = MagicMock()
        nav.viewport_size.return_value = (1920, 1080)
        nav._get_screenshot.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)

        if find_results is None:
            find_results = [True, True]  # edit_btn, save_btn 都成功

        nav.find_and_click = MagicMock(side_effect=find_results)
        return nav

    @patch("keybind_config._load_keybind_coords")
    @patch("click_confirm.execute_click_with_confirm")
    @patch("click_confirm.plan_coords_click")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_success_path(self, mock_sleep, mock_plan, mock_exec, mock_load):
        """三步全成功时返回 True。"""
        mock_load.return_value = (1712, 16)
        mock_exec.return_value = True

        nav = self._make_nav(find_results=[True, True])
        result = configure_keybinding(nav)
        assert result is True
        assert nav.find_and_click.call_count == 2  # edit + save

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_edit_btn_not_found(self, mock_sleep, mock_load):
        """找不到键位编辑按钮时返回 False。"""
        nav = self._make_nav(find_results=[False])

        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 1  # 只调了一次，第 2 步没走到

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_coords_missing(self, mock_sleep, mock_load):
        """坐标读取失败时返回 False。"""
        mock_load.return_value = None

        nav = self._make_nav(find_results=[True])
        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 1  # 走到了第 1 步（成功），第 2 步失败

    @patch("keybind_config._load_keybind_coords")
    @patch("click_confirm.execute_click_with_confirm")
    @patch("click_confirm.plan_coords_click")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_roi_confirm_fails(self, mock_sleep, mock_plan, mock_exec, mock_load):
        """ROI 确认失败时返回 False（不继续点保存按钮）。"""
        mock_load.return_value = (1712, 16)
        mock_exec.return_value = False

        nav = self._make_nav(find_results=[True])
        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 1  # 第 1 步成功，第 2 步失败，不到第 3 步

    @patch("keybind_config._load_keybind_coords")
    @patch("click_confirm.execute_click_with_confirm")
    @patch("click_confirm.plan_coords_click")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_save_btn_not_found(self, mock_sleep, mock_plan, mock_exec, mock_load):
        """保存键位按钮找不到时返回 False。"""
        mock_load.return_value = (1712, 16)
        mock_exec.return_value = True

        nav = self._make_nav(find_results=[True, False])
        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 2

    @patch("keybind_config._load_keybind_coords")
    @patch("click_confirm.execute_click_with_confirm")
    @patch("click_confirm.plan_coords_click")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_save_uses_bottom_right_bounds(self, mock_sleep, mock_plan, mock_exec, mock_load):
        """保存按钮搜索应限定在右下 1/4 区域。"""
        mock_load.return_value = (1712, 16)
        mock_exec.return_value = True

        nav = self._make_nav(find_results=[True, True])
        result = configure_keybinding(nav)
        assert result is True

        # 验证 save_btn 调用带了 bounds
        save_call = nav.find_and_click.call_args_list[1]
        _, kwargs = save_call
        bounds = kwargs.get("bounds")
        assert bounds is not None
        assert bounds == (960, 540, 960, 540)  # vw//2, vh//2, vw-vw//2, vh-vh//2

    @patch("keybind_config._load_keybind_coords")
    @patch("click_confirm.execute_click_with_confirm")
    @patch("click_confirm.plan_coords_click")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_on_log_callback_called(self, mock_sleep, mock_plan, mock_exec, mock_load):
        """on_log 回调应被调用。"""
        mock_load.return_value = (1712, 16)
        mock_exec.return_value = True

        nav = self._make_nav(find_results=[True, True])
        logs = []

        def capture(text, level="info"):
            logs.append((text, level))

        result = configure_keybinding(nav, on_log=capture)
        assert result is True
        assert len(logs) > 0
        assert any("完成" in text for text, _ in logs)


class TestConstants:
    """测试模块常量定义。"""

    def test_template_names(self):
        assert KEYBIND_EDIT_BTN == "keybind_edit.png"
        assert KEYBIND_SAVE_BTN == "keybind_save.png"

    def test_coord_key(self):
        assert KEYBIND_CLICK_COORD_KEY == "keybind_pos"

    def test_max_retries(self):
        assert MAX_RETRIES == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
