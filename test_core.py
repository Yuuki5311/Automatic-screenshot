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
    @patch("browser.time.sleep", return_value=None)
    def test_edge_does_not_use_webdriver_manager(self, _sleep, mock_edge):
        """Edge 启动不应访问 webdriver-manager 的微软驱动源。"""
        from browser import _create_edge

        driver = Mock()
        mock_edge.return_value = driver

        def _js(script):
            if "innerWidth" in script:
                return 1920
            if "innerHeight" in script:
                return 1080
            return None

        driver.execute_script.side_effect = _js

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("SE_MSEDGEDRIVER_MIRROR_URL", None)
            assert _create_edge(1920, 1080) is driver
            assert os.environ["SE_MSEDGEDRIVER_MIRROR_URL"] == (
                "https://msedgedriver.microsoft.com"
            )
            _, kwargs = mock_edge.call_args
            assert "service" not in kwargs
            # 不再最大化，改为锁定视口
            driver.maximize_window.assert_not_called()
            driver.set_window_size.assert_called()

    @patch("browser.time.sleep", return_value=None)
    def test_lock_viewport_adjusts_until_target(self, _sleep):
        from browser import lock_viewport

        driver = Mock()
        calls = {"n": 0}
        sequence = [(1800, 1000), (1920, 1080)]

        def _js(script):
            i = min(calls["n"] // 2, len(sequence) - 1)
            w, h = sequence[i]
            if "innerWidth" in script:
                calls["n"] += 1
                return w
            if "innerHeight" in script:
                calls["n"] += 1
                return h
            return None

        driver.execute_script.side_effect = _js
        iw, ih = lock_viewport(driver, 1920, 1080)
        assert (iw, ih) == (1920, 1080)
        assert driver.set_window_size.call_count >= 1

    def test_browser_target_viewport_config(self):
        import config

        assert config.BROWSER_WIDTH == 1920
        assert config.BROWSER_HEIGHT == 1080


# ========== Navigator Selenium 截图与点击测试 ==========

class TestNavigatorSelenium:
    def test_scale_is_one_without_pyautogui_screenshot(self):
        from navigator import Navigator

        driver = Mock()
        with patch("pyautogui.screenshot") as mock_shot:
            nav = Navigator(driver=driver, templates_dir=TEMPLATES_DIR)
            assert nav._scale == 1.0
            mock_shot.assert_not_called()

    def test_click_css_uses_cdp_mouse_events(self):
        from navigator import Navigator

        driver = Mock()
        nav = Navigator.__new__(Navigator)
        nav.driver = driver
        nav._scale = 1.0
        nav.click_css(100, 200)

        assert driver.execute_cdp_cmd.call_count == 3
        moved, pressed, released = driver.execute_cdp_cmd.call_args_list
        assert moved.args[0] == "Input.dispatchMouseEvent"
        assert moved.args[1]["type"] == "mouseMoved"
        assert moved.args[1]["x"] == 100
        assert moved.args[1]["y"] == 200
        assert pressed.args[0] == "Input.dispatchMouseEvent"
        assert pressed.args[1]["type"] == "mousePressed"
        assert pressed.args[1]["x"] == 100
        assert pressed.args[1]["y"] == 200
        assert pressed.args[1]["button"] == "left"
        assert pressed.args[1]["clickCount"] == 1
        assert released.args[0] == "Input.dispatchMouseEvent"
        assert released.args[1]["type"] == "mouseReleased"
        assert released.args[1]["x"] == 100
        assert released.args[1]["y"] == 200

    def test_get_screenshot_uses_cdp_jpeg(self):
        """感知/匹配用截屏走 CDP JPEG，减轻云游戏 tab 压力。"""
        import base64
        from navigator import Navigator

        bgr = np.zeros((24, 32, 3), dtype=np.uint8)
        bgr[:] = (10, 20, 30)
        ok, enc = cv2.imencode(".jpg", bgr, [int(cv2.IMWRITE_JPEG_QUALITY), 70])
        assert ok
        driver = Mock()
        driver.execute_cdp_cmd.return_value = {
            "data": base64.b64encode(enc.tobytes()).decode("ascii"),
        }
        nav = Navigator.__new__(Navigator)
        nav.driver = driver

        out = nav._get_screenshot()

        driver.execute_cdp_cmd.assert_called_once()
        cmd, params = driver.execute_cdp_cmd.call_args.args
        assert cmd == "Page.captureScreenshot"
        assert params["format"] == "jpeg"
        assert 1 <= int(params["quality"]) <= 100
        driver.get_screenshot_as_png.assert_not_called()
        assert out.shape[0] == 24 and out.shape[1] == 32
        assert out.dtype == np.uint8


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

    def test_load_template_unicode_path(self):
        """含非 ASCII 的路径也应能加载（EXE 解压到中文用户 TEMP 时必需）。"""
        import shutil
        import tempfile
        from navigator import Navigator

        src = os.path.join(resource_path(TEMPLATES_DIR), "game_logout_btn.png")
        assert os.path.isfile(src), "源模板应存在"

        root = os.path.join(tempfile.gettempdir(), "用户_MEIprobe_test")
        tpl_dir = os.path.join(root, "templates")
        os.makedirs(tpl_dir, exist_ok=True)
        dst = os.path.join(tpl_dir, "game_logout_btn.png")
        try:
            shutil.copy2(src, dst)
            nav = Navigator(driver=Mock(), templates_dir=tpl_dir)
            template = nav._load_template("game_logout_btn.png")
            assert template is not None, f"Unicode 路径应能加载: {dst}"
            assert isinstance(template, np.ndarray)
        finally:
            shutil.rmtree(root, ignore_errors=True)

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
        assert first.kwargs["threshold"] == 0.60
        assert first.kwargs["bounds"] == (0, 720, 2560, 720)


class TestGameLoginPlatformFallback:
    """找不到平台按钮时，若退出仍在则回退预退出再重试。"""

    @patch("login.time.sleep", return_value=None)
    @patch("ui_loop.run_pre_logout_loop")
    def test_missing_platform_rewinds_logout_then_retries(self, mock_pre, _sleep):
        from login import game_login
        from ui_loop import PreLogoutResult

        mock_pre.return_value = PreLogoutResult(
            logout_clicked=True, confirm_clicked="game_popup_confirm.png", timed_out=False
        )
        nav = Mock()
        nav.viewport_size.return_value = (1920, 1080)
        platform_hits = {"n": 0}

        def find_and_click(tpl, **kwargs):
            if tpl == "game_qq_ios.png":
                platform_hits["n"] += 1
                return platform_hits["n"] >= 2
            if tpl == "enter_game.png":
                return True
            return False

        nav.find_and_click.side_effect = find_and_click

        def wait_for_template(tpl, **kwargs):
            if tpl == "game_logout_btn.png":
                return True
            if tpl == "avatar.png":
                return True
            if tpl == "enter_game.png":
                return True
            return False

        nav.wait_for_template.side_effect = wait_for_template
        statuses = []

        assert game_login(nav, "qq_ios", on_status=statuses.append) is True
        mock_pre.assert_called_once()
        assert platform_hits["n"] == 2
        assert any("退出" in s for s in statuses)

    @patch("login.time.sleep", return_value=None)
    @patch("ui_loop.run_pre_logout_loop")
    def test_missing_platform_without_logout_fails(self, mock_pre, _sleep):
        from login import game_login

        nav = Mock()
        nav.viewport_size.return_value = (1920, 1080)
        nav.find_and_click.return_value = False
        nav.wait_for_template.return_value = False
        statuses = []

        assert game_login(nav, "qq_ios", on_status=statuses.append) is False
        mock_pre.assert_not_called()
        assert any("找不到" in s for s in statuses)


class TestGameLoginAfterQrBackToPlatform:
    """扫码后二维码消失、回到平台页时，应再点平台而不是空等到超时。"""

    @patch("login.crop_qr_from_bgr")
    @patch("login.platform_template_visible")
    def test_reclicks_platform_after_qr_then_enters(
        self, mock_plat_vis, mock_crop
    ):
        from login import game_login
        from PIL import Image

        mock_crop.return_value = Image.new("RGB", (40, 40), color=(0, 0, 0))
        nav = Mock()
        nav.viewport_size.return_value = (1920, 1080)
        clicks = {"platform": 0}

        def find_and_click(tpl, **kwargs):
            if tpl == "game_qq_ios.png":
                clicks["platform"] += 1
                return True
            if tpl == "enter_game.png":
                return clicks["platform"] >= 2
            return False

        nav.find_and_click.side_effect = find_and_click
        # 再点平台之前平台按钮仍可见；点第二次后消失
        mock_plat_vis.side_effect = lambda *a, **k: clicks["platform"] < 2

        def wait_for_template(tpl, **kwargs):
            if tpl == "enter_game.png":
                return clicks["platform"] >= 2
            return False

        nav.wait_for_template.side_effect = wait_for_template

        clock = {"t": 1000.0}

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds=0):
            clock["t"] += max(float(seconds or 0), 0.5)

        with patch("login.time.time", side_effect=fake_time), \
             patch("login.time.sleep", side_effect=fake_sleep), \
             patch("login.POST_QR_PLATFORM_GRACE_S", 5.0), \
             patch(
                 "login.capture_viewport_bgr",
                 return_value=np.zeros((120, 120, 3), dtype=np.uint8),
             ):
            statuses = []
            ok = game_login(nav, "qq_ios", on_status=statuses.append, timeout=60)

        assert ok is True
        assert clicks["platform"] >= 2
        assert any("回到平台" in s or "重新点击平台" in s for s in statuses)

    @patch("login.crop_qr_from_bgr")
    @patch("login.platform_template_visible")
    def test_still_on_platform_after_reclick_fails_fast(
        self, mock_plat_vis, mock_crop
    ):
        from login import game_login
        from PIL import Image

        mock_crop.return_value = Image.new("RGB", (40, 40), color=(0, 0, 0))
        mock_plat_vis.return_value = True

        nav = Mock()
        nav.viewport_size.return_value = (1920, 1080)
        nav.find_and_click.return_value = True
        nav.wait_for_template.return_value = False

        clock = {"t": 1000.0}

        def fake_time():
            return clock["t"]

        def fake_sleep(seconds=0):
            clock["t"] += max(float(seconds or 0), 1.0)

        with patch("login.time.time", side_effect=fake_time), \
             patch("login.time.sleep", side_effect=fake_sleep), \
             patch("login.POST_QR_PLATFORM_GRACE_S", 2.0), \
             patch("login.POST_QR_PLATFORM_STUCK_S", 3.0), \
             patch(
                 "login.capture_viewport_bgr",
                 return_value=np.zeros((120, 120, 3), dtype=np.uint8),
             ):
            statuses = []
            ok = game_login(nav, "qq_ios", on_status=statuses.append, timeout=300)

        assert ok is False
        assert any("仍停在平台" in s or "将重试" in s for s in statuses)
        assert clock["t"] < 1000 + 80


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
                ("按键", [
                    ("in_game_btn.png", "desc"),
                    ("keybind_btn.png", "desc"),
                ], 1),
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

    def test_anjian_follows_lingbao(self):
        names = [
            "主页", "英雄", "万象图鉴首页", "万象图鉴-灵宝", "按键", "天幕",
        ]
        # 最小检查：按键紧跟灵宝
        tasks = [
            ("万象图鉴-灵宝", [("lingbao.png", "d")], 1),
            ("按键", [("in_game_btn.png", "d"), ("keybind_btn.png", "d")], 1),
            ("天幕", [("tianmu.png", "d")], 1),
        ]
        assert [t[0] for t in tasks] == ["万象图鉴-灵宝", "按键", "天幕"]
        assert tasks[1][2] == 1
        assert [c[0] for c in tasks[1][1]] == ["in_game_btn.png", "keybind_btn.png"]

    def test_expected_anjian_task_tuple(self):
        task = ("按键", [
            ("in_game_btn.png", "点击局内按钮"),
            ("keybind_btn.png", "点击按键按钮"),
        ], 1)
        assert task[0] == "按键"
        assert task[2] == 1


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

    def test_popup_small_can_classify_popup(self):
        """真实小弹窗用 popup_close_small，应能判为 POPUP。"""
        from ui_state import UiState, classify_from_scores, POPUP_CLOSE_THRESHOLD

        state, _ = classify_from_scores({
            "popup_close_small.png": POPUP_CLOSE_THRESHOLD,
            "popup_close.png": 0.50,
            "avatar.png": 0.40,
        })
        assert state == UiState.POPUP

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

    def test_confirm_templates_count_as_popup(self):
        """感知环弹窗检测含确认「确定」模板，优先于 MAIN。"""
        from ui_state import (
            UiState,
            classify_from_scores,
            CONFIRM_THRESHOLD,
            POPUP_CONFIRM_TEMPLATES,
        )

        assert POPUP_CONFIRM_TEMPLATES == (
            "game_popup_confirm.png",
            "game_logout_confirm.png",
        )
        for tpl in POPUP_CONFIRM_TEMPLATES:
            state, info = classify_from_scores({
                tpl: CONFIRM_THRESHOLD,
                "avatar.png": 0.90,
            })
            assert state == UiState.POPUP, tpl
            assert info["hit"] == "popup_confirm"

    def test_confirm_when_allowed(self):
        from ui_state import UiState, classify_from_scores

        state, info = classify_from_scores(
            {"game_popup_confirm.png": 0.99},
            allow_confirm=True,
        )
        assert state == UiState.CONFIRM
        assert info["hit"] == "confirm"

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

    def test_match_score_uses_provided_screen_without_resnap(self):
        from ui_state import match_score

        tpl = np.zeros((10, 10, 3), dtype=np.uint8)
        tpl[2:8, 2:8] = 255
        screen = np.zeros((50, 50, 3), dtype=np.uint8)
        screen[5:15, 5:15] = tpl

        nav = Mock()
        nav._load_template.return_value = tpl
        score = match_score(nav, "avatar.png", screen=screen)
        nav._get_screenshot.assert_not_called()
        assert score > 0.9

    def test_classify_captures_screenshot_only_once(self):
        from ui_state import classify, UiState

        rng = np.random.default_rng(0)
        screen = rng.integers(0, 40, (100, 200, 3), dtype=np.uint8)
        tpl = rng.integers(200, 255, (8, 8, 3), dtype=np.uint8)
        nav = Mock()
        nav._get_screenshot.return_value = screen
        nav._load_template.return_value = tpl

        state, _ = classify(nav, path_templates=["tab_home.png"])
        assert nav._get_screenshot.call_count == 1
        assert state == UiState.UNKNOWN


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


class TestPreLogoutLoop:
    """云游戏打开后 → 点登录页退出 的预退出感知环。"""

    def test_closes_popup_before_logout(self):
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop, PreLogoutResult

        calls = []
        states = iter([UiState.POPUP, UiState.UNKNOWN, UiState.UNKNOWN])

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            try:
                return next(states), {}
            except StopIteration:
                return UiState.UNKNOWN, {}

        def fake_close(nav, on_log=None):
            calls.append("close")
            return "popup_close.png"

        nav = Mock()
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        def fake_find(template, **kwargs):
            calls.append(("click", template))
            return template == "game_logout_btn.png"

        nav.find_and_click.side_effect = fake_find

        result = run_pre_logout_loop(
            nav,
            timeout_s=5.0,
            tick_s=0.01,
            confirm_wait_s=0.05,
            classify_fn=fake_classify,
            close_popup_fn=fake_close,
            platform_visible_fn=lambda n, screen=None: False,
        )
        assert isinstance(result, PreLogoutResult)
        assert result.logout_clicked is True
        assert calls[0] == "close"
        assert ("click", "game_logout_btn.png") in calls

    def test_logout_then_confirm_ends(self):
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop

        # UNKNOWN → click logout; then POPUP confirm → end
        phase = {"n": 0}

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            phase["n"] += 1
            if phase["n"] == 1:
                return UiState.UNKNOWN, {}
            return UiState.POPUP, {}

        def fake_close(nav, on_log=None):
            return "game_popup_confirm.png"

        nav = Mock()
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        nav.find_and_click.return_value = True

        result = run_pre_logout_loop(
            nav,
            timeout_s=5.0,
            tick_s=0.01,
            confirm_wait_s=2.0,
            classify_fn=fake_classify,
            close_popup_fn=fake_close,
            platform_visible_fn=lambda n, screen=None: False,
        )
        assert result.logout_clicked is True
        assert result.confirm_clicked == "game_popup_confirm.png"
        assert result.timed_out is False

    def test_logout_without_confirm_ends_after_wait(self):
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            return UiState.UNKNOWN, {}

        nav = Mock()
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        nav.find_and_click.return_value = True

        result = run_pre_logout_loop(
            nav,
            timeout_s=5.0,
            tick_s=0.01,
            confirm_wait_s=0.05,
            classify_fn=fake_classify,
            close_popup_fn=lambda *a, **k: None,
            platform_visible_fn=lambda n, screen=None: False,
        )
        assert result.logout_clicked is True
        assert result.confirm_clicked is None
        assert result.timed_out is False

    def test_timeout_without_logout(self):
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            return UiState.UNKNOWN, {}

        nav = Mock()
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        nav.find_and_click.return_value = False

        result = run_pre_logout_loop(
            nav,
            timeout_s=0.08,
            tick_s=0.05,
            confirm_wait_s=1.0,
            classify_fn=fake_classify,
            close_popup_fn=lambda *a, **k: None,
            platform_visible_fn=lambda n, screen=None: False,
        )
        assert result.logout_clicked is False
        assert result.ready_for_platform is True

    def test_no_logout_on_platform_page_exits_immediately(self):
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            return UiState.UNKNOWN, {}

        nav = Mock()
        nav.find_and_click.return_value = False
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)

        result = run_pre_logout_loop(
            nav,
            timeout_s=30.0,
            tick_s=0.01,
            classify_fn=fake_classify,
            close_popup_fn=lambda *a, **k: None,
            platform_visible_fn=lambda n, screen=None: True,
        )
        assert result.logout_clicked is False
        assert result.timed_out is False
        assert result.ready_for_platform is True
        # 认出平台页后直接关环，不再反复 find_and_click
        assert nav.find_and_click.call_count == 0

    def test_stop_event_aborts(self):
        import threading
        from ui_state import UiState
        from ui_loop import run_pre_logout_loop

        stop = threading.Event()
        stop.set()

        def fake_classify(nav, path_templates=None, allow_confirm=False, screen=None):
            return UiState.UNKNOWN, {}

        nav = Mock()
        nav._get_screenshot.return_value = np.zeros((10, 10, 3), dtype=np.uint8)
        nav.find_and_click.return_value = False

        result = run_pre_logout_loop(
            nav,
            stop_event=stop,
            timeout_s=5.0,
            tick_s=0.01,
            classify_fn=fake_classify,
            close_popup_fn=lambda *a, **k: None,
            platform_visible_fn=lambda n, screen=None: False,
        )
        assert result.logout_clicked is False
        assert result.timed_out is False


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
        nav._get_screenshot.return_value = np.zeros((100, 100, 3), dtype=np.uint8)
        shot = Mock()
        shot.take.return_value = "x.png"

        actions = []

        from click_confirm import ClickPlan
        plan = ClickPlan(
            x=1, y=1,
            roi_ref=np.zeros((10, 10, 3), dtype=np.uint8),
            template_name="tab_home.png",
            score=0.99,
            roi_box=(0, 0, 10, 10),
        )

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
             patch("ui_loop.random.uniform", return_value=0), \
             patch.object(loop, "_ensure_clear_for_click", return_value=True), \
             patch("click_confirm.plan_template_click", return_value=plan), \
             patch("click_confirm.execute_click_with_confirm", return_value=True):
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

    def test_ensure_clear_for_click_closes_and_blocks(self):
        from ui_loop import UiLoop

        nav = Mock()
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[("主页", [("tab_home.png", "d")], 0)],
            tick_s=0,
        )
        with patch.object(loop, "_popup_pending", return_value=True), \
             patch.object(loop, "_close_popup") as close_mock:
            assert loop._ensure_clear_for_click() is False
            close_mock.assert_called_once()

    def test_do_click_step_skips_when_popup_pending(self):
        from ui_loop import UiLoop

        nav = Mock()
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[("主页", [("tab_home.png", "d")], 0)],
            tick_s=0,
        )
        with patch.object(loop, "_ensure_clear_for_click", return_value=False):
            loop._do_click_step()
        nav.find_and_click.assert_not_called()
        assert loop.goal.click_index == 0

    def test_do_back_skips_when_popup_pending(self):
        from ui_loop import UiLoop

        nav = Mock()
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[("页", [("x.png", "d")], 1)],
            tick_s=0,
        )
        loop.goal.click_index = 1
        loop.goal.mark_shot_done()
        with patch.object(loop, "_ensure_clear_for_click", return_value=False):
            loop._do_back()
        nav.find_and_click.assert_not_called()
        assert loop.goal.backs_done == 0

    def test_do_back_does_not_advance_when_verify_fails(self):
        """返回未生效 → 回退到本任务上一步（重新点击），而非卡在 go_back。"""
        from ui_loop import UiLoop
        from click_confirm import ClickPlan
        import numpy as np

        nav = Mock()
        nav.wait_for_template.return_value = False
        plan = ClickPlan(
            x=10, y=10,
            roi_ref=np.zeros((20, 20, 3), dtype=np.uint8),
            template_name="back_arrow.png",
            score=0.99,
            roi_box=(0, 0, 20, 20),
        )
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[
                ("灵宝", [("lingbao.png", "d")], 1),
                ("天幕", [("tianmu.png", "d")], 1),
            ],
            tick_s=0,
        )
        loop.goal.click_index = 1
        loop.goal.mark_shot_done()
        assert loop.goal.success == 1
        assert loop.goal.phase_need_back()
        with patch("ui_loop.time.sleep", return_value=None), \
             patch.object(loop, "_ensure_clear_for_click", return_value=True), \
             patch.object(loop, "_drain_popups_briefly"), \
             patch.object(loop, "_recover_toward_current_step") as recover, \
             patch("click_confirm.plan_template_click", return_value=plan), \
             patch("click_confirm.execute_click_with_confirm", return_value=True):
            loop._do_back()
        assert loop.goal.task_index == 0
        assert loop.goal.backs_done == 0
        assert loop.goal.click_index == 0
        assert getattr(loop.goal, "_shot_done", False) is False
        assert loop.goal.success == 0
        assert loop.goal.phase_need_click()
        recover.assert_called_once()
        nav.wait_for_template.assert_any_call("tianmu.png", timeout=5)

    def test_rewind_to_previous_step_from_shot(self):
        from ui_loop import Goal

        g = Goal([
            ("首页", [("a.png", "d")], 0),
            ("灵宝", [("lingbao.png", "d")], 1),
        ])
        g.task_index = 1
        g.click_index = 1
        g.mark_shot_done()
        msg = g.rewind_to_previous_step()
        assert "点击步骤" in msg
        assert g.task_index == 1
        assert g.click_index == 0
        assert g.success == 0
        assert not getattr(g, "_shot_done", False)

    def test_do_back_advances_when_verify_ok(self):
        from ui_loop import UiLoop
        from click_confirm import ClickPlan
        import numpy as np

        nav = Mock()
        nav.wait_for_template.return_value = True
        plan = ClickPlan(
            x=10, y=10,
            roi_ref=np.zeros((20, 20, 3), dtype=np.uint8),
            template_name="back_arrow.png",
            score=0.99,
            roi_box=(0, 0, 20, 20),
        )
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[
                ("灵宝", [("lingbao.png", "d")], 1),
                ("天幕", [("tianmu.png", "d")], 1),
            ],
            tick_s=0,
        )
        loop.goal.click_index = 1
        loop.goal.mark_shot_done()
        with patch("ui_loop.time.sleep", return_value=None), \
             patch("ui_loop.random.uniform", return_value=0), \
             patch.object(loop, "_ensure_clear_for_click", return_value=True), \
             patch.object(loop, "_drain_popups_briefly"), \
             patch("click_confirm.plan_template_click", return_value=plan), \
             patch("click_confirm.execute_click_with_confirm", return_value=True):
            loop._do_back()
        assert loop.goal.task_index == 1
        assert loop.goal.backs_done == 0

    def test_do_back_roi_fail_does_not_rewind(self):
        """ROI 未确认：点击未发出，游标保持待返回，不回退上一步。"""
        from ui_loop import UiLoop
        from click_confirm import ClickPlan
        import numpy as np

        nav = Mock()
        plan = ClickPlan(
            x=10, y=10,
            roi_ref=np.zeros((20, 20, 3), dtype=np.uint8),
            template_name="back_arrow.png",
            score=0.99,
            roi_box=(0, 0, 20, 20),
        )
        loop = UiLoop(
            nav=nav,
            shot=Mock(),
            tasks=[
                ("灵宝", [("lingbao.png", "d")], 1),
                ("天幕", [("tianmu.png", "d")], 1),
            ],
            tick_s=0,
        )
        loop.goal.click_index = 1
        loop.goal.mark_shot_done()
        with patch("ui_loop.time.sleep", return_value=None), \
             patch.object(loop, "_ensure_clear_for_click", return_value=True), \
             patch("click_confirm.plan_template_click", return_value=plan), \
             patch("click_confirm.execute_click_with_confirm", return_value=False), \
             patch.object(loop, "_recover_toward_current_step") as recover:
            loop._do_back()
        assert loop.goal.task_index == 0
        assert loop.goal.phase_need_back()
        assert loop.goal.success == 1
        recover.assert_not_called()
        nav.wait_for_template.assert_not_called()


class TestClickConfirm:
    """ROI 双重确认。"""

    def test_roi_similar_same_image_passes(self):
        from click_confirm import roi_similar

        img = np.random.default_rng(1).integers(0, 255, (40, 40, 3), dtype=np.uint8)
        ok, score = roi_similar(img, img.copy())
        assert ok
        assert score >= 0.90

    def test_roi_similar_blocked_fails(self):
        from click_confirm import roi_similar

        ref = np.random.default_rng(2).integers(0, 255, (40, 40, 3), dtype=np.uint8)
        now = ref.copy()
        now[10:30, 10:30] = 0
        ok, score = roi_similar(ref, now)
        assert not ok

    def test_execute_click_skips_when_confirm_fails(self):
        from click_confirm import ClickPlan, execute_click_with_confirm

        nav = Mock()
        nav.grab_roi.return_value = np.zeros((30, 30, 3), dtype=np.uint8)
        ref = np.random.default_rng(3).integers(0, 255, (30, 30, 3), dtype=np.uint8)
        plan = ClickPlan(
            x=15, y=15, roi_ref=ref, template_name="t.png",
            score=0.99, roi_box=(0, 0, 30, 30),
        )
        with patch("click_confirm.time.sleep", return_value=None):
            assert execute_click_with_confirm(nav, plan) is False
        nav.click_css.assert_not_called()

    def test_execute_click_when_confirm_passes(self):
        from click_confirm import ClickPlan, execute_click_with_confirm

        ref = np.random.default_rng(4).integers(0, 255, (30, 30, 3), dtype=np.uint8)
        nav = Mock()
        nav.grab_roi.return_value = ref.copy()
        plan = ClickPlan(
            x=15, y=15, roi_ref=ref, template_name="t.png",
            score=0.99, roi_box=(0, 0, 30, 30),
        )
        with patch("click_confirm.time.sleep", return_value=None):
            assert execute_click_with_confirm(nav, plan) is True
        nav.click_css.assert_called_once_with(15, 15)


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
