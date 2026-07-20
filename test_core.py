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

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_close_all_popups_max_rounds(self, _mock_sleep):
        """持续出现新弹窗时，应受 max_rounds 限制。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        monitor = PopupMonitor(navigator=nav)
        monitor._click_one_popup = Mock(return_value=True)
        monitor._wait_and_watch = Mock(return_value=True)

        result = monitor.close_all_popups(max_rounds=5)
        assert result == 5, "应返回 5 次关闭"
        assert monitor._click_one_popup.call_count == 5

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_close_all_popups_no_popups(self, _mock_sleep):
        """当前无 X，冷静确认仍无 X，应退出。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        monitor = PopupMonitor(navigator=nav)
        monitor._click_one_popup = Mock(return_value=False)
        monitor._wait_and_watch = Mock(return_value=False)

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 0, "无弹窗应返回 0"
        assert monitor._click_one_popup.call_count == 1
        assert monitor._wait_and_watch.call_count == 1

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_close_all_popups_waits_then_closes_new_popup(self, _mock_sleep):
        """每次点击后冷静检测；若再出现 X，继续关闭循环。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        monitor = PopupMonitor(navigator=nav)

        # 点第 1 个 → 冷静期内又有 → 点第 2 个 → 冷静干净
        monitor._click_one_popup = Mock(side_effect=[True, True])
        monitor._wait_and_watch = Mock(side_effect=[True, False])

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 2, "应关闭 2 个弹窗"
        assert monitor._click_one_popup.call_count == 2
        assert monitor._wait_and_watch.call_count == 2

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_close_all_popups_retries_when_new_popup_after_wait(self, _mock_sleep):
        """无 X 时冷静期内又出现新 X，应继续关。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        monitor = PopupMonitor(navigator=nav)

        # 先点不到 → 冷静期发现新弹窗 → 点掉 → 冷静干净
        monitor._click_one_popup = Mock(side_effect=[False, True])
        monitor._wait_and_watch = Mock(side_effect=[True, False])

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 1
        assert monitor._click_one_popup.call_count == 2
        assert monitor._wait_and_watch.call_count == 2

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_wait_and_watch_returns_true_when_popup_appears(self, _mock_sleep):
        """冷静等待期间发现关闭按钮应返回 True。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        monitor = PopupMonitor(navigator=nav)
        monitor._find_close_button = Mock(
            side_effect=[None, ("popup_close.png", (0, 0, 1, 1), 0.85)]
        )

        t = {"v": 0.0}

        def _time():
            t["v"] += 0.4
            return t["v"]

        with patch("popup_monitor.time.time", side_effect=_time):
            assert monitor._wait_and_watch(3.0) is True

    def test_wait_until_idle_returns_immediately_when_not_busy(self):
        from popup_monitor import PopupMonitor

        monitor = PopupMonitor(navigator=Mock())
        assert monitor.wait_until_idle(timeout=1) is True

    def test_drain_sets_and_clears_busy(self):
        from popup_monitor import PopupMonitor

        monitor = PopupMonitor(navigator=Mock())
        monitor._click_one_popup = Mock(return_value=False)
        monitor._wait_and_watch = Mock(return_value=False)

        assert not monitor.is_busy
        monitor.close_all_popups(max_rounds=1)
        assert not monitor.is_busy


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

        close_bounds = (1280, 0, 1280, 720)  # 右上半屏
        assert [
            call.args[0] for call in nav.wait_for_template.call_args_list
        ] == ["popup_close.png", "popup_close_small.png"]
        for call in nav.wait_for_template.call_args_list:
            assert call.kwargs["threshold"] == 0.78
            assert call.kwargs["bounds"] == close_bounds
        nav.viewport_size.assert_called()

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_scan_uses_close_only_allowlist_and_disables_fallback(
        self, _mock_sleep
    ):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav.viewport_size.return_value = (2560, 1440)
        nav.wait_for_template.side_effect = [True]
        nav.find_and_click.return_value = True
        monitor = PopupMonitor(navigator=nav)

        assert monitor._do_scan() is True

        close_bounds = (1280, 0, 1280, 720)  # 右上半屏
        nav.find_and_click.assert_called_once_with(
            "popup_close.png",
            timeout=2,
            bounds=close_bounds,
            threshold=0.78,
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
            assert call.kwargs["bounds"] == close_bounds

    @patch("popup_monitor.time.sleep", return_value=None)
    def test_scan_never_uses_blank_area_fallback(self, _mock_sleep):
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav.viewport_size.return_value = (2560, 1440)
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


# ========== 截图点击守卫测试 ==========

class TestScreenshotClickGuard:
    """测试点击解析与生效验证模板选择。"""

    def test_parse_template_only(self):
        from screenshot_click import parse_click_item

        p = parse_click_item(("shop_icon.png", "点击商城"))
        assert p["template"] == "shop_icon.png"
        assert p["bounds"] is None
        assert p["anchor"] is None

    def test_parse_coords_item(self):
        from screenshot_click import parse_click_item

        p = parse_click_item(("__coords__", "点头像", (10, 20), "game_main.png"))
        assert p["template"] == "__coords__"
        assert p["bounds"] == (10, 20)
        assert p["anchor"] == "game_main.png"

    def test_effect_verify_uses_next_template(self):
        from screenshot_click import effect_verify_template

        assert effect_verify_template(("lottery_tab.png", "夺宝")) == "lottery_tab.png"

    def test_effect_verify_last_step_is_none(self):
        from screenshot_click import effect_verify_template

        assert effect_verify_template(None) is None

    def test_effect_verify_next_coords_uses_anchor(self):
        from screenshot_click import effect_verify_template

        nxt = ("__coords__", "小兵", (1, 2), "back_arrow.png")
        assert effect_verify_template(nxt) == "back_arrow.png"


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
                ("天幕", [("tianmu.png", "desc")], 1),
                ("星典藏", [("xingyuan.png", "desc"), ("xing_collection.png", "desc")], 0),
                ("星传说", [("xing_legend.png", "desc")], 1),
                ("皮肤图鉴", [("skin_illustrated.png", "desc")], 0),
                ("珍品无双", [("skin_treasure_wushuang.png", "desc")], 1),
                ("荣耀典藏", [("skin_glory_collection.png", "desc")], 1),
                ("无双", [("skin_wushuang.png", "desc")], 1),
                ("珍品传说", [("skin_treasure_legend.png", "desc")], 1),
                ("传说", [("skin_legend.png", "desc")], 2),
                ("积分夺宝", [("shop_icon.png", "desc"), ("lottery_tab.png", "desc"), ("points_lottery.png", "desc")], 2),
                ("货币背包", [("bag.png", "desc"), ("currency_bag.png", "desc")], 2),
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


# ========== 轻量 FSM：状态分类 ==========

class TestUiClassify:
    """classify_from_scores 优先级：POPUP > LOGIN > MAIN/ON_PATH > UNKNOWN。"""

    def test_popup_wins_over_avatar(self):
        from ui_state import UiState, classify_from_scores, POPUP_CLOSE_THRESHOLD

        state, info = classify_from_scores({
            "popup_close.png": POPUP_CLOSE_THRESHOLD,
            "avatar.png": 0.99,
        })
        assert state == UiState.POPUP
        assert info["scores"]["popup_close.png"] >= POPUP_CLOSE_THRESHOLD

    def test_login_wins_over_main(self):
        from ui_state import UiState, classify_from_scores

        # 无头像 + 高置信度平台图 → LOGIN
        state, _ = classify_from_scores({
            "game_qq_android.png": 0.90,
            "avatar.png": 0.40,
        })
        assert state == UiState.LOGIN

    def test_login_ignored_when_avatar_visible(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores({
            "game_qq_android.png": 0.90,
            "avatar.png": 0.95,
        })
        assert state == UiState.MAIN

    def test_login_mid_score_not_enough(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores({
            "game_qq_android.png": 0.65,
            "avatar.png": 0.40,
        })
        assert state == UiState.UNKNOWN

    def test_main_when_avatar_only(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores({"avatar.png": 0.90})
        assert state == UiState.MAIN

    def test_on_path_when_path_template_hits(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores(
            {"tab_home.png": 0.88, "avatar.png": 0.50},
            path_templates=["tab_home.png"],
        )
        assert state == UiState.ON_PATH

    def test_confirm_ignored_by_default(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores({
            "game_popup_confirm.png": 0.99,
            "avatar.png": 0.90,
        })
        assert state == UiState.MAIN

    def test_confirm_when_allowed(self):
        from ui_state import UiState, classify_from_scores

        state, _ = classify_from_scores(
            {"game_popup_confirm.png": 0.99},
            allow_confirm=True,
        )
        assert state == UiState.CONFIRM

    def test_unknown_when_all_low(self):
        from ui_state import UiState, classify_from_scores

        state, info = classify_from_scores({
            "popup_close.png": 0.40,
            "avatar.png": 0.40,
        })
        assert state == UiState.UNKNOWN
        assert "scores" in info

    def test_popup_close_bounds_is_top_right(self):
        from ui_state import popup_close_bounds

        assert popup_close_bounds(2560, 1440) == (1280, 0, 1280, 720)


# ========== 轻量 FSM：决策与 Goal ==========

class TestUiDecide:
    """decide：POPUP 禁止推进主线；MAIN 才允许点击/截图。"""

    def test_popup_action_is_close_not_click(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        assert decide(UiState.POPUP, g) == Action.CLOSE_POPUP
        assert g.task_index == 0
        assert g.click_index == 0

    def test_main_need_click(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        assert decide(UiState.MAIN, g) == Action.CLICK_STEP

    def test_main_need_shot_after_clicks(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        g.click_index = 1
        assert decide(UiState.MAIN, g) == Action.TAKE_SHOT

    def test_on_path_allows_click(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        assert decide(UiState.ON_PATH, g) == Action.CLICK_STEP

    def test_login_triggers_relogin(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        assert decide(UiState.LOGIN, g) == Action.RELOGIN

    def test_unknown_waits_then_recover(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal
        import time

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        g.unknown_since = time.time()
        assert decide(UiState.UNKNOWN, g) == Action.WAIT
        g.unknown_since = time.time() - 60
        assert decide(UiState.UNKNOWN, g) == Action.RECOVER

    def test_finished_when_all_tasks_done(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("主页", [("tab_home.png", "d")], 0)])
        g.task_index = 1
        assert decide(UiState.MAIN, g) == Action.FINISHED

    def test_go_back_after_shot(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("页", [("x.png", "d")], 2)])
        g.click_index = 1
        g.mark_shot_done()
        assert decide(UiState.MAIN, g) == Action.GO_BACK

    def test_unknown_still_takes_shot_after_clicks(self):
        """进入灵宝等内容页后无头像，UNKNOWN 也必须能截图。"""
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("万象图鉴-灵宝", [("lingbao.png", "点击灵宝")], 1)])
        g.click_index = 1  # 点击已完成
        assert decide(UiState.UNKNOWN, g) == Action.TAKE_SHOT

    def test_unknown_still_goes_back_after_shot(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("万象图鉴-灵宝", [("lingbao.png", "d")], 1)])
        g.click_index = 1
        g.mark_shot_done()
        assert decide(UiState.UNKNOWN, g) == Action.GO_BACK

    def test_popup_still_blocks_shot(self):
        from ui_state import UiState
        from ui_loop import Action, decide, Goal

        g = Goal([("万象图鉴-灵宝", [("lingbao.png", "d")], 1)])
        g.click_index = 1
        assert decide(UiState.POPUP, g) == Action.CLOSE_POPUP


class TestUiLoopRun:
    """UiLoop：有弹窗时先关再点，不硬推进主线。"""

    def test_closes_popup_before_click(self):
        from ui_state import UiState
        from ui_loop import UiLoop, Action

        states = iter([UiState.POPUP, UiState.MAIN, UiState.MAIN, UiState.MAIN])

        def fake_classify(nav, path_templates=None, allow_confirm=False):
            try:
                s = next(states)
            except StopIteration:
                s = UiState.MAIN
            return s, {"scores": {}}

        nav = Mock()
        nav.viewport_size.return_value = (1920, 1080)
        nav.find_and_click.return_value = True
        nav.wait_for_template.return_value = True
        shot = Mock()
        shot.take.return_value = "x.png"

        actions = []

        loop = UiLoop(
            nav=nav,
            shot=shot,
            tasks=[("主页", [("tab_home.png", "点击主页")], 0)],
            tick_s=0,
            classify_fn=fake_classify,
        )
        # speed up sleeps
        with patch("ui_loop.time.sleep", return_value=None), \
             patch("ui_loop.PAGE_LOAD_WAIT", 0), \
             patch("ui_loop.CLICK_INTERVAL", 0), \
             patch("ui_loop.random.uniform", return_value=0):
            # wrap _close_popup / _do_click to record order
            orig_close = loop._close_popup
            orig_click = loop._do_click_step

            def close_wrap():
                actions.append("close")
                return orig_close()

            def click_wrap():
                actions.append("click")
                return orig_click()

            loop._close_popup = close_wrap
            loop._do_click_step = click_wrap
            n = loop.run()

        assert n == 1
        assert actions[0] == "close"
        assert "click" in actions
        assert actions.index("close") < actions.index("click")
        shot.take.assert_called_with("主页")

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
