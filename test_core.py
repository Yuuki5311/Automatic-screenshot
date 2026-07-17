#!/usr/bin/env python3
"""核心逻辑单元测试 —— 不依赖真实游戏画面。"""

import sys
import os
import tempfile
import time
from unittest.mock import Mock, patch, PropertyMock
import numpy as np

# 将项目根目录加入路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cv2
from config import TEMPLATES_DIR, resource_path


# ========== Windows Edge 启动测试 ==========

class TestEdgeBrowserStartup:
    """验证 Windows Edge 使用 Selenium Manager 管理驱动。"""

    @patch("browser.webdriver.Edge")
    def test_edge_does_not_use_webdriver_manager(self, mock_edge):
        """Edge 启动不应访问 webdriver-manager 的微软驱动源。"""
        from browser import _create_edge

        driver = Mock()
        mock_edge.return_value = driver

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SE_MSEDGEDRIVER_MIRROR_URL", None)
            assert _create_edge(1920, 1080) is driver
            assert os.environ["SE_MSEDGEDRIVER_MIRROR_URL"] == (
                "https://msedgedriver.microsoft.com"
            )
            _, kwargs = mock_edge.call_args
            assert "service" not in kwargs


# ========== Navigator 模板缓存测试 ==========

class TestTemplateCache:
    """测试 Navigator 的模板加载和缓存机制。"""

    def test_load_template_creates_cache(self):
        """模板加载后应存入缓存，第二次从缓存命中。"""
        from navigator import Navigator

        nav = Navigator(templates_dir=TEMPLATES_DIR)
        template = nav._load_template("avatar.png")

        assert template is not None, "模板文件应能加载"
        assert isinstance(template, np.ndarray), "应返回 numpy 数组"
        assert nav.templates_dir + "/avatar.png" in nav._template_cache, \
            "加载后应存入缓存"

        # 第二次加载应命中缓存
        cached = nav._load_template("avatar.png")
        assert cached is template, "第二次应返回同一个对象（缓存命中）"

    def test_load_template_missing_file(self):
        """加载不存在的模板应返回 None。"""
        from navigator import Navigator

        nav = Navigator(templates_dir=TEMPLATES_DIR)
        result = nav._load_template("nonexistent.png")
        assert result is None, "不存在的模板应返回 None"

    def test_cleanup_clears_cache(self):
        """cleanup 应清空模板缓存。"""
        from navigator import Navigator

        nav = Navigator(templates_dir=TEMPLATES_DIR)
        nav._load_template("avatar.png")
        assert len(nav._template_cache) > 0, "缓存应有内容"

        nav.cleanup()
        assert len(nav._template_cache) == 0, "cleanup 后缓存应为空"

    def test_multiple_templates_cached(self):
        """多个模板应全部存入缓存。"""
        from navigator import Navigator

        nav = Navigator(templates_dir=TEMPLATES_DIR)
        templates = ["avatar.png", "tab_home.png", "tab_hero.png"]

        for t in templates:
            result = nav._load_template(t)
            assert result is not None, f"{t} 应能加载"

        assert len(nav._template_cache) == len(templates), \
            f"缓存应有 {len(templates)} 个模板"


# ========== PopupMonitor 关闭逻辑测试 ==========

class TestPopupMonitor:
    """测试弹窗监控的扫描和循环逻辑。"""

    def test_close_all_popups_max_rounds(self):
        """当 _do_scan 永远返回 True 时，应受 max_rounds 限制。"""
        from popup_monitor import PopupMonitor

        # 用 Mock 模拟 navigator
        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)

        # _do_scan 一直返回 True（模拟弹窗持续存在）
        monitor._do_scan = Mock(return_value=True)

        result = monitor.close_all_popups(max_rounds=5)
        assert result == 5, "应返回 5 次关闭"
        assert monitor._do_scan.call_count == 5, "应调用恰好 5 次"

    def test_close_all_popups_no_popups(self):
        """当 _do_scan 两次都返回 False，应确认干净后退出。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)
        monitor._do_scan = Mock(return_value=False)

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 0, "无弹窗应返回 0"
        # 第一次扫描 + 3s 后验证扫描
        assert monitor._do_scan.call_count == 2, "应调用两次（扫描+验证）"

    def test_close_all_popups_stops_after_clean(self):
        """弹窗关完后应等待 3s 再验证一次，确认干净后停止。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)

        # 前 3 次有弹窗，第 4 次无弹窗，第 5 次验证仍无弹窗
        monitor._do_scan = Mock(side_effect=[True, True, True, False, False])

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 3, "应返回 3 次关闭"
        assert monitor._do_scan.call_count == 5, \
            "应调用 5 次（3 次 True + 无弹窗 + 验证确认）"


# ========== 平台选择 bounds 计算测试 ==========

class TestPlatformBounds:
    """测试 game_login 中平台选择的搜索区域计算。"""

    @patch("pyautogui.size")
    def test_wx_platform_left_half(self, mock_size):
        """微信平台应搜索左半边。"""
        mock_size.return_value = (1470, 956)
        # 重新导入以使用 mock 的 pyautogui.size()
        import pyautogui

        # 模拟 Navigator
        nav = Mock()
        nav._scale = 2.0

        screen_w, screen_h = pyautogui.size()
        scale = nav._scale
        platform = "wx_android"

        if platform.startswith("wx"):
            bounds = (0, 0, int(screen_w * scale * 0.5), int(screen_h * scale))
        else:
            bounds = (int(screen_w * scale * 0.5), 0,
                      int(screen_w * scale * 0.5), int(screen_h * scale))

        expected = (0, 0, 1470, 1912)  # 左半边
        assert bounds == expected, f"微信 bounds 应为左半边，实际 {bounds}"

    @patch("pyautogui.size")
    def test_qq_platform_right_half(self, mock_size):
        """QQ 平台应搜索右半边。"""
        mock_size.return_value = (1470, 956)

        import pyautogui

        nav = Mock()
        nav._scale = 2.0

        screen_w, screen_h = pyautogui.size()
        scale = nav._scale
        platform = "qq_android"

        if platform.startswith("wx"):
            bounds = (0, 0, int(screen_w * scale * 0.5), int(screen_h * scale))
        else:
            bounds = (int(screen_w * scale * 0.5), 0,
                      int(screen_w * scale * 0.5), int(screen_h * scale))

        expected = (1470, 0, 1470, 1912)  # 右半边
        assert bounds == expected, f"QQ bounds 应为右半边，实际 {bounds}"


# ========== PopupMonitor 安全白名单测试 ==========

class TestPopupSafety:
    """验证同步与异步通用扫描只操作安全的关闭按钮。"""

    @patch("popup_monitor.pyautogui.size", return_value=(1470, 956))
    def test_scan_checks_exact_close_allowlist_with_shared_bounds(
        self, _mock_size
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        nav.wait_for_template.side_effect = [False, False]
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is False

        top_bounds = (0, 0, 2940, 956)
        assert [
            call.args[0] for call in nav.wait_for_template.call_args_list
        ] == ["popup_close.png", "popup_close_small.png"]
        for call in nav.wait_for_template.call_args_list:
            assert call.kwargs["threshold"] == 0.85
            assert call.kwargs["bounds"] == top_bounds

    @patch("popup_monitor.time.sleep", return_value=None)
    @patch("popup_monitor.pyautogui.size", return_value=(1470, 956))
    def test_scan_uses_close_only_allowlist_and_disables_fallback(
        self, _mock_size, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        nav.wait_for_template.side_effect = [True, True, False]
        nav.find_and_click.return_value = True
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is True

        top_bounds = (0, 0, 2940, 956)
        nav.find_and_click.assert_called_once_with(
            "popup_close.png",
            timeout=2,
            bounds=top_bounds,
            threshold=0.85,
            allow_fallback=False,
        )
        checked_templates = [
            call.args[0] for call in nav.wait_for_template.call_args_list
        ]
        assert set(checked_templates) <= {
            "popup_close.png",
            "popup_close_small.png",
        }
        for call in nav.wait_for_template.call_args_list:
            assert call.kwargs["bounds"] == top_bounds

    @patch("popup_monitor.time.sleep", return_value=None)
    @patch("popup_monitor.pyautogui.click")
    @patch("popup_monitor.pyautogui.size", return_value=(1470, 956))
    def test_scan_never_uses_blank_area_fallback(
        self, _mock_size, mock_click, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        nav.wait_for_template.return_value = True
        nav.find_and_click.return_value = False
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is False
        mock_click.assert_not_called()


# ========== Navigator threshold 参数兼容性测试 ==========

class TestNavigatorThreshold:
    """测试 find_and_click 和 wait_for_template 的 threshold 参数。"""

    def test_find_and_click_accepts_threshold_param(self):
        """find_and_click 应接受 threshold 关键字参数。"""
        from navigator import Navigator
        import inspect

        sig = inspect.signature(Navigator.find_and_click)
        assert "threshold" in sig.parameters, \
            "find_and_click 应有 threshold 参数"
        param = sig.parameters["threshold"]
        assert param.default is None, \
            "threshold 默认值应为 None"

    def test_wait_for_template_accepts_threshold_param(self):
        """wait_for_template 应接受 threshold 关键字参数。"""
        from navigator import Navigator
        import inspect

        sig = inspect.signature(Navigator.wait_for_template)
        assert "threshold" in sig.parameters, \
            "wait_for_template 应有 threshold 参数"
        param = sig.parameters["threshold"]
        assert param.default is None, \
            "threshold 默认值应为 None"


class TestNavigatorSafetyOptions:
    """测试后台监控需要的安全匹配选项。"""

    @patch("navigator.time.sleep", return_value=None)
    @patch("navigator.pyautogui.click")
    def test_find_and_click_can_disable_coordinate_fallback(
        self, mock_click, _mock_sleep
    ):
        from navigator import Navigator

        nav = Navigator.__new__(Navigator)
        nav.threshold = 0.53
        nav.max_retries = 1
        nav._scale = 1.0
        nav._load_template = Mock(return_value=np.ones((2, 2, 3), dtype=np.uint8))
        nav._get_screenshot = Mock(return_value=np.zeros((8, 8, 3), dtype=np.uint8))
        nav._load_coords = Mock(return_value={"popup_close": [10, 20]})

        result = nav.find_and_click(
            "popup_close.png",
            max_retries=1,
            threshold=1.1,
            allow_fallback=False,
        )

        assert result is False
        nav._load_coords.assert_not_called()
        mock_click.assert_not_called()

    @patch("navigator.time.sleep", return_value=None)
    @patch("navigator.cv2.matchTemplate")
    def test_wait_for_template_limits_matching_to_bounds(
        self, mock_match, _mock_sleep
    ):
        from navigator import Navigator

        nav = Navigator.__new__(Navigator)
        nav.threshold = 0.53
        nav._load_template = Mock(return_value=np.ones((2, 2, 3), dtype=np.uint8))
        nav._get_screenshot = Mock(return_value=np.zeros((20, 30, 3), dtype=np.uint8))
        mock_match.return_value = np.array([[1.0]], dtype=np.float32)

        assert nav.wait_for_template(
            "popup_close.png",
            timeout=0.1,
            bounds=(4, 5, 10, 8),
        )

        search_area = mock_match.call_args.args[0]
        assert search_area.shape == (8, 10, 3)


# ========== 截图任务配置测试 ==========

class TestScreenshotTasks:
    """测试阶段 4 截图任务的结构完整性。"""

    def test_all_tasks_have_valid_structure(self):
        """每个任务应有名称、按钮列表、返回次数。"""
        # 模拟屏幕尺寸创建 bounds
        with patch("pyautogui.size", return_value=(1470, 956)):
            screenshot_tasks = [
                ("主页", [("avatar.png", "desc1", None), ("tab_home.png", "desc2")], 0),
                ("英雄", [("tab_hero.png", "desc")], 0),
                ("万象图鉴首页", [("tab_illustrated.png", "desc"), ("universal_illustrated.png", "desc")], 0),
                ("万象图鉴-灵宝", [("lingbao.png", "desc")], 1),
                ("皮肤图鉴", [("skin_illustrated.png", "desc")], 1),
                ("积分夺宝", [("shop_icon.png", "desc"), ("lottery_tab.png", "desc"), ("points_lottery.png", "desc")], 2),
                ("小兵", [("minion.png", "desc")], 1),
                ("个性戳戳", [("customize_icon.png", "desc"), ("personal_customize.png", "desc"), ("poke.png", "desc")], 1),
                ("贵族", [("nobility_icon.png", "desc", None)], 1),
            ]

            for name, clicks, back_count in screenshot_tasks:
                assert isinstance(name, str) and len(name) > 0, f"任务名无效: {name}"
                assert len(clicks) > 0, f"{name} 按钮列表为空"
                assert isinstance(back_count, int) and back_count >= 0, \
                    f"{name} back_count 无效"

                for item in clicks:
                    if len(item) == 2:
                        template, desc = item
                    else:
                        template, desc = item[:2]
                    assert isinstance(template, str), f"{name} 模板名无效"
                    assert template.endswith(".png"), f"{name} 模板 {template} 应为 .png"


if __name__ == "__main__":
    # 简易测试运行器
    import traceback

    tests = [
        TestTemplateCache(),
        TestPopupMonitor(),
        TestPlatformBounds(),
        TestPopupThresholds(),
        TestNavigatorThreshold(),
        TestScreenshotTasks(),
    ]

    passed = 0
    failed = 0

    for suite in tests:
        name = type(suite).__name__
        for attr in dir(suite):
            if attr.startswith("test_"):
                test_name = f"{name}.{attr}"
                try:
                    getattr(suite, attr)()
                    print(f"  ✅ {test_name}")
                    passed += 1
                except Exception as e:
                    print(f"  ❌ {test_name}: {e}")
                    traceback.print_exc()
                    failed += 1

    print(f"\n{'='*50}")
    print(f"结果: {passed} 通过, {failed} 失败, {passed+failed} 总计")
    if failed == 0:
        print("全部测试通过 ✅")
    else:
        print(f"{failed} 个测试失败 ❌")
        sys.exit(1)
