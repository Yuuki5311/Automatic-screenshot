#!/usr/bin/env python3
"""keybind_config 模块单元测试 —— 不依赖真实浏览器，验证模块导入与逻辑正确性。"""

import os
import sys
import json
import tempfile
from unittest.mock import Mock, patch, MagicMock, call

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np
import pytest

from keybind_config import (
    configure_keybinding,
    _load_keybind_coords,
    KEYBIND_EDIT_BTN,
    KEYBIND_SAVE_BTN,
    KEYBIND_POS_TEMPLATE,
    KEYBIND_CLICK_COORD_KEY,
    COORD_SEARCH_MARGIN,
    MAX_RETRIES,
)


class TestLoadKeybindCoords:
    """测试 _load_keybind_coords 坐标读取。"""

    def test_returns_coords_when_key_exists(self):
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
        with patch("keybind_config.resource_path", return_value="/nonexistent/coords.json"):
            result = _load_keybind_coords()
            assert result is None

    def test_returns_none_when_key_missing(self):
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
        """构造 mock Navigator。

        find_results 控制 find_and_click 返回值顺序：
        [edit_btn, pos_target, save_btn]
        """
        nav = MagicMock()
        nav.viewport_size.return_value = (1920, 1080)
        nav._get_screenshot.return_value = np.zeros((1080, 1920, 3), dtype=np.uint8)
        nav.click_cluster = MagicMock()

        if find_results is None:
            find_results = [True, True, True]  # 全部成功

        nav.find_and_click = MagicMock(side_effect=find_results)
        return nav

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_success_template_matched(self, mock_sleep, mock_load):
        """模板匹配命中 → 3 次 find_and_click，不触发坐标回退。"""
        mock_load.return_value = (1712, 16)

        nav = self._make_nav(find_results=[True, True, True])
        result = configure_keybinding(nav)
        assert result is True
        assert nav.find_and_click.call_count == 3  # edit + pos_target + save
        nav.click_css.assert_not_called()  # 模板命中，无回退

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fallback_click_css_when_template_missed(self, mock_sleep, mock_load):
        """模板未匹配 → 回退 click_css 单点。"""
        mock_load.return_value = (1712, 16)

        nav = self._make_nav(find_results=[True, False, True])
        result = configure_keybinding(nav)
        assert result is True
        assert nav.find_and_click.call_count == 3
        nav.click_css.assert_called_once_with(1712, 16)

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_edit_btn_not_found(self, mock_sleep, mock_load):
        """找不到键位编辑按钮时返回 False。"""
        nav = self._make_nav(find_results=[False])

        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 1
        nav.click_cluster.assert_not_called()

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_coords_missing(self, mock_sleep, mock_load):
        """坐标读取失败时返回 False。"""
        mock_load.return_value = None

        nav = self._make_nav(find_results=[True])
        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 1
        nav.click_cluster.assert_not_called()

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_fails_when_save_btn_not_found(self, mock_sleep, mock_load):
        """编辑和模板成功但保存按钮找不到 → False。"""
        mock_load.return_value = (1712, 16)

        nav = self._make_nav(find_results=[True, True, False])
        result = configure_keybinding(nav)
        assert result is False
        assert nav.find_and_click.call_count == 3

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_search_bounds_clamped_to_viewport(self, mock_sleep, mock_load):
        """坐标在边缘时搜索区夹在视口内。"""
        mock_load.return_value = (30, 20)  # 左上角边缘

        nav = self._make_nav(find_results=[True, True, True])
        configure_keybinding(nav)

        # 第二次调用 (pos_target) 的 bounds
        pos_call = nav.find_and_click.call_args_list[1]
        _, kwargs = pos_call
        bounds = kwargs.get("bounds")
        assert bounds is not None
        bx, by, bw, bh = bounds
        # 左上角坐标小 → bounds 原点被夹在 (0, 0)
        assert bx == 0
        assert by == 0

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_save_uses_bottom_right_bounds(self, mock_sleep, mock_load):
        """保存按钮搜索应限定在右下 1/4 区域。"""
        mock_load.return_value = (1712, 16)

        nav = self._make_nav(find_results=[True, True, True])
        result = configure_keybinding(nav)
        assert result is True

        save_call = nav.find_and_click.call_args_list[2]
        _, kwargs = save_call
        bounds = kwargs.get("bounds")
        assert bounds is not None
        assert bounds == (960, 540, 960, 540)

    @patch("keybind_config._load_keybind_coords")
    @patch("keybind_config.time.sleep", return_value=None)
    def test_on_log_callback_called(self, mock_sleep, mock_load):
        """on_log 回调应被调用。"""
        mock_load.return_value = (1712, 16)

        nav = self._make_nav(find_results=[True, True, True])
        logs = []

        def capture(text, level="info"):
            logs.append((text, level))

        result = configure_keybinding(nav, on_log=capture)
        assert result is True
        assert len(logs) > 0
        assert any("完成" in text for text, _ in logs)


class TestClickCluster:
    """测试 Navigator.click_cluster 簇击方法。"""

    def _make_nav(self):
        nav = MagicMock()
        nav.driver = MagicMock()
        return nav

    @patch("time.sleep", return_value=None)
    @patch("random.randint", return_value=20)
    def test_default_3x3_grid(self, mock_randint, mock_sleep):
        from navigator import Navigator

        nav = self._make_nav()
        Navigator.click_cluster(nav, 100, 200)

        call_count = nav.driver.execute_cdp_cmd.call_count
        assert call_count == 27  # 9 x 3 events

    @patch("time.sleep", return_value=None)
    @patch("random.randint", return_value=15)
    def test_5x5_grid(self, mock_randint, mock_sleep):
        from navigator import Navigator

        nav = self._make_nav()
        Navigator.click_cluster(nav, 100, 200, grid=5, radius=6)

        call_count = nav.driver.execute_cdp_cmd.call_count
        assert call_count == 75  # 25 x 3 events

    @patch("time.sleep", return_value=None)
    @patch("random.randint", return_value=20)
    def test_points_cover_target_center(self, mock_randint, mock_sleep):
        from navigator import Navigator

        nav = self._make_nav()
        Navigator.click_cluster(nav, 500, 300, grid=3, radius=4)

        moved_calls = [
            c for c in nav.driver.execute_cdp_cmd.call_args_list
            if c[0][1].get("type") == "mouseMoved"
        ]
        positions = [(c[0][1]["x"], c[0][1]["y"]) for c in moved_calls]
        assert (500, 300) in positions

    @patch("time.sleep", return_value=None)
    @patch("random.randint", return_value=20)
    def test_corners_correct(self, mock_randint, mock_sleep):
        from navigator import Navigator

        nav = self._make_nav()
        Navigator.click_cluster(nav, 100, 100, grid=3, radius=4)

        moved_calls = [
            c for c in nav.driver.execute_cdp_cmd.call_args_list
            if c[0][1].get("type") == "mouseMoved"
        ]
        positions = [(c[0][1]["x"], c[0][1]["y"]) for c in moved_calls]
        assert (96, 96) in positions
        assert (104, 96) in positions
        assert (96, 104) in positions
        assert (104, 104) in positions


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
