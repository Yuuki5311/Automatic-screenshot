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


# ========== 可写路径测试 ==========

class TestWritablePath:
    """测试 app_dir 和 writable_path 在开发与 EXE 环境下的行为。"""

    def test_dev_app_dir_is_project_root(self):
        """开发环境下 app_dir() 返回项目根目录。"""
        import config

        project_root = os.path.dirname(os.path.abspath(__file__))
        assert config.app_dir() == project_root

    def test_dev_writable_path_screenshots(self):
        """开发环境下 writable_path('screenshots') 返回项目根下的 screenshots。"""
        import config

        expected = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "screenshots"
        )
        assert config.writable_path("screenshots") == expected

    def test_frozen_app_dir_is_exe_directory(self):
        """模拟 EXE 环境时 app_dir() 返回 EXE 所在目录。"""
        import config

        exe_path = r"C:\Tools\AutoScreenshot.exe"
        with patch.object(config.sys, "frozen", True, create=True), \
             patch.object(config.sys, "executable", exe_path, create=True):
            assert config.app_dir() == r"C:\Tools"

    def test_frozen_writable_path_logs(self):
        """模拟 EXE 环境时 writable_path('logs') 返回 EXE 目录下的 logs。"""
        import config

        exe_path = r"C:\Tools\AutoScreenshot.exe"
        with patch.object(config.sys, "frozen", True, create=True), \
             patch.object(config.sys, "executable", exe_path, create=True):
            assert config.writable_path("logs") == r"C:\Tools\logs"


# ========== 输出路径测试 ==========

class TestOutputLocations:
    """测试日志和截图输出路径使用 writable_path。"""

    @patch("logger.writable_path", return_value=os.path.join("C:\\", "App", "logs"))
    def test_default_log_file_uses_writable_path(self, mock_writable_path):
        """default_log_file() 应通过 writable_path 定位日志目录。"""
        from logger import default_log_file

        result = default_log_file()
        mock_writable_path.assert_called_once_with("logs")
        assert os.path.dirname(result) == os.path.join("C:\\", "App", "logs")
        assert result.endswith(".log")


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


# ========== Navigator Selenium 截图与点击测试 ==========

class TestNavigatorSelenium:
    def test_scale_is_one_without_pyautogui_screenshot(self):
        from navigator import Navigator

        driver = Mock()
        with patch("pyautogui.screenshot") as mock_shot:
            nav = Navigator(driver=driver, templates_dir=TEMPLATES_DIR)
            assert nav._scale == 1.0
            mock_shot.assert_not_called()

    @patch("navigator.ActionBuilder")
    def test_click_css_uses_action_builder(self, mock_ab):
        from navigator import Navigator

        driver = Mock()
        builder = mock_ab.return_value
        builder.pointer_action.move_to_location.return_value = builder.pointer_action
        builder.pointer_action.click.return_value = builder.pointer_action
        builder.perform.return_value = None
        nav = Navigator.__new__(Navigator)
        nav.driver = driver
        nav._scale = 1.0
        nav.click_css(100, 200)
        mock_ab.assert_called_once_with(driver)
        builder.pointer_action.move_to_location.assert_called_once_with(100, 200)
        builder.pointer_action.click.assert_called_once()
        builder.perform.assert_called_once()


# ========== Navigator 模板缓存测试 ==========

class TestTemplateCache:
    """测试 Navigator 的模板加载和缓存机制。"""

    def test_load_template_creates_cache(self):
        """模板加载后应存入缓存，第二次从缓存命中。"""
        from navigator import Navigator

        nav = Navigator(driver=Mock(), templates_dir=TEMPLATES_DIR)
        template = nav._load_template("avatar.png")

        assert template is not None, "模板文件应能加载"
        assert isinstance(template, np.ndarray), "应返回 numpy 数组"
        assert os.path.join(nav.templates_dir, "avatar.png") in nav._template_cache, \
            "加载后应存入缓存"

        # 第二次加载应命中缓存
        cached = nav._load_template("avatar.png")
        assert cached is template, "第二次应返回同一个对象（缓存命中）"

    def test_load_template_missing_file(self):
        """加载不存在的模板应返回 None。"""
        from navigator import Navigator

        nav = Navigator(driver=Mock(), templates_dir=TEMPLATES_DIR)
        result = nav._load_template("nonexistent.png")
        assert result is None, "不存在的模板应返回 None"

    def test_cleanup_clears_cache(self):
        """cleanup 应清空模板缓存。"""
        from navigator import Navigator

        nav = Navigator(driver=Mock(), templates_dir=TEMPLATES_DIR)
        nav._load_template("avatar.png")
        assert len(nav._template_cache) > 0, "缓存应有内容"

        nav.cleanup()
        assert len(nav._template_cache) == 0, "cleanup 后缓存应为空"

    def test_multiple_templates_cached(self):
        """多个模板应全部存入缓存。"""
        from navigator import Navigator

        nav = Navigator(driver=Mock(), templates_dir=TEMPLATES_DIR)
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
    """测试平台选择搜索区：按真实视口、下半屏、左右分栏。"""

    def test_wx_platform_bottom_left_uses_actual_viewport(self):
        from login import platform_select_bounds

        # 模拟最大化后大于 1920×1080 的截图
        bounds = platform_select_bounds(2560, 1440, "wx_android")
        assert bounds == (0, 720, 1280, 720)

    def test_qq_platform_bottom_right_uses_actual_viewport(self):
        from login import platform_select_bounds

        bounds = platform_select_bounds(2560, 1440, "qq_android")
        assert bounds == (1280, 720, 1280, 720)

    def test_odd_width_covers_full_right_half(self):
        from login import platform_select_bounds

        bounds = platform_select_bounds(1921, 1080, "qq_ios")
        assert bounds[0] == 960
        assert bounds[0] + bounds[2] == 1921

    def test_bottom_half_bounds_uses_actual_viewport(self):
        from login import bottom_half_bounds

        assert bottom_half_bounds(2560, 1440) == (0, 720, 2560, 720)

    def test_top_half_bounds_uses_actual_viewport(self):
        from login import top_half_bounds

        assert top_half_bounds(2560, 1440) == (0, 0, 2560, 720)

    @patch("login.time.sleep", return_value=None)
    def test_click_confirm_dialog_tries_both_templates(self, _mock_sleep):
        from login import click_confirm_dialog

        nav = Mock()
        nav.viewport_size.return_value = (2560, 1440)
        nav.find_and_click.side_effect = [False, True]

        assert click_confirm_dialog(nav, wait_after=0) == "game_logout_confirm.png"
        assert nav.find_and_click.call_count == 2
        first = nav.find_and_click.call_args_list[0]
        assert first.args[0] == "game_popup_confirm.png"
        assert first.kwargs["threshold"] == 0.48
        assert first.kwargs["bounds"] == (0, 720, 2560, 720)


# ========== PopupMonitor 安全白名单测试 ==========

class TestPopupSafety:
    """验证同步与异步通用扫描只操作安全的关闭按钮。"""

    def test_scan_checks_exact_close_allowlist_with_shared_bounds(self):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav.viewport_size.return_value = (2560, 1440)
        nav.wait_for_template.side_effect = [False, False]
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is False

        top_bounds = (0, 0, 2560, 720)
        assert [
            call.args[0] for call in nav.wait_for_template.call_args_list
        ] == ["popup_close.png", "popup_close_small.png"]
        for call in nav.wait_for_template.call_args_list:
            assert call.kwargs["threshold"] == 0.85
            assert call.kwargs["bounds"] == top_bounds
        nav.viewport_size.assert_called()

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_scan_uses_close_only_allowlist_and_disables_fallback(
        self, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav.viewport_size.return_value = (2560, 1440)
        nav.wait_for_template.side_effect = [True, True, False]
        nav.find_and_click.return_value = True
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is True

        top_bounds = (0, 0, 2560, 720)
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
    def test_scan_never_uses_blank_area_fallback(self, _mock_sleep):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav.wait_for_template.return_value = True
        nav.find_and_click.return_value = False
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is False


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
    @patch("navigator.Navigator.click_css")
    def test_find_and_click_can_disable_coordinate_fallback(
        self, mock_click_css, _mock_sleep
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
        mock_click_css.assert_not_called()

    @patch("navigator.time.sleep", return_value=None)
    @patch("navigator.Navigator.click_css")
    def test_find_and_click_default_disables_fallback(
        self, mock_click_css, _mock_sleep
    ):
        """默认不允许坐标兜底，匹配失败应直接返回 False。"""
        from navigator import Navigator

        nav = Navigator.__new__(Navigator)
        nav.threshold = 0.53
        nav.max_retries = 1
        nav._scale = 1.0
        nav._load_template = Mock(return_value=np.ones((2, 2, 3), dtype=np.uint8))
        nav._get_screenshot = Mock(return_value=np.zeros((8, 8, 3), dtype=np.uint8))
        nav._load_coords = Mock(return_value={"game_logout_btn": [10, 20]})

        result = nav.find_and_click("game_logout_btn.png", max_retries=1, threshold=1.1)

        assert result is False
        nav._load_coords.assert_not_called()
        mock_click_css.assert_not_called()

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


# ========== Screenshotter 浏览器截图测试 ==========

class TestScreenshotterDriver:
    def test_take_saves_browser_screenshot(self):
        from screenshotter import Screenshotter

        img = np.zeros((10, 10, 3), dtype=np.uint8)
        _, png_bytes = cv2.imencode(".png", img)
        png_data = png_bytes.tobytes()

        driver = Mock()
        driver.get_screenshot_as_png.return_value = png_data

        with tempfile.TemporaryDirectory() as tmpdir:
            shot = Screenshotter(tmpdir, driver=driver)
            path = shot.take("test_shot")

            assert os.path.isfile(path)
            assert os.path.getsize(path) > 0
            driver.get_screenshot_as_png.assert_called_once()


# ========== 云游戏新标签页切换测试 ==========

class TestSwitchToNewTab:
    """秒玩后切换到云游戏标签页。"""

    @patch("game_launcher.time.sleep", return_value=None)
    def test_switches_to_newest_non_original_handle(self, _mock_sleep):
        from game_launcher import switch_to_new_tab

        driver = Mock()
        driver.window_handles = ["home", "game"]
        driver.current_url = "https://play.example/game"

        assert switch_to_new_tab(driver, "home", timeout=1) is True
        driver.switch_to.window.assert_called_once_with("game")

    @patch("game_launcher.time.sleep", return_value=None)
    def test_timeout_when_no_new_tab(self, _mock_sleep):
        from game_launcher import switch_to_new_tab

        driver = Mock()
        driver.window_handles = ["home"]

        # 第一次构造 deadline，之后始终超过 deadline
        times = iter([100.0, 101.5, 101.6, 101.7, 101.8])
        with patch("game_launcher.time.time", side_effect=lambda: next(times, 102.0)):
            assert switch_to_new_tab(driver, "home", timeout=1) is False
        driver.switch_to.window.assert_not_called()

    @patch("game_launcher.time.sleep", return_value=None)
    def test_waits_until_new_tab_appears(self, _mock_sleep):
        from game_launcher import switch_to_new_tab

        driver = Mock()
        driver.current_url = "https://play.example/game"
        polls = {"n": 0}

        def _handles(_self=None):
            polls["n"] += 1
            if polls["n"] == 1:
                return ["home"]
            return ["home", "game"]

        type(driver).window_handles = property(_handles)

        with patch("game_launcher.time.time", side_effect=[0.0, 0.1, 0.2, 0.3]):
            assert switch_to_new_tab(driver, "home", timeout=5) is True
        driver.switch_to.window.assert_called_once_with("game")


# ========== 截图任务配置测试 ==========

class TestScreenshotTasks:
    """测试阶段 4 截图任务的结构完整性。"""

    def test_all_tasks_have_valid_structure(self):
        """每个任务应有名称、按钮列表、返回次数。"""
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


# ========== 二维码裁切辅助测试 ==========

class TestCropQrFromBgr:
    """测试 login.crop_qr_from_bgr：检测并裁切二维码区域。"""

    def test_blank_image_returns_none(self):
        from login import crop_qr_from_bgr

        blank = np.zeros((200, 200, 3), dtype=np.uint8)
        assert crop_qr_from_bgr(blank) is None

    def test_synthetic_qr_returns_pil_image(self):
        from login import crop_qr_from_bgr
        from PIL import Image

        encoder = cv2.QRCodeEncoder.create()
        qr = encoder.encode("https://example.com/login-test")
        qr_big = cv2.resize(qr, (200, 200), interpolation=cv2.INTER_NEAREST)
        canvas = np.ones((500, 500), dtype=np.uint8) * 255
        canvas[150:350, 150:350] = qr_big
        frame_bgr = cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)

        result = crop_qr_from_bgr(frame_bgr)
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.size[0] > 0 and result.size[1] > 0


if __name__ == "__main__":
    # 简易测试运行器
    import traceback

    tests = [
        TestTemplateCache(),
        TestPopupMonitor(),
        TestPlatformBounds(),
        TestPopupThresholds(),
        TestNavigatorThreshold(),
        TestSwitchToNewTab(),
        TestScreenshotTasks(),
        TestCropQrFromBgr(),
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
