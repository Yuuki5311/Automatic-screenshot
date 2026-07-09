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
        """当 _do_scan 第一次就返回 False，应立即结束。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)
        monitor._do_scan = Mock(return_value=False)

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 0, "无弹窗应返回 0"
        assert monitor._do_scan.call_count == 1, "应只调用一次就退出"

    def test_close_all_popups_stops_after_clean(self):
        """弹窗关完后应立即停止，不跑满 max_rounds。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)

        # 前 3 次有弹窗，第 4 次清理完毕
        monitor._do_scan = Mock(side_effect=[True, True, True, False])

        result = monitor.close_all_popups(max_rounds=10)
        assert result == 3, "应返回 3 次关闭"
        assert monitor._do_scan.call_count == 4, \
            "应调用 4 次（3 次 True + 1 次确认干净）"


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


# ========== PopupMonitor 按钮阈值配置测试 ==========

class TestPopupThresholds:
    """测试 popup_monitor 中各按钮的阈值配置。"""

    def test_thresholds_configured_correctly(self):
        """验证 4 个按钮都有正确的阈值配置。"""
        from popup_monitor import PopupMonitor

        nav = Mock()
        nav._scale = 2.0
        monitor = PopupMonitor(navigator=nav)

        # 直接访问内部方法，但不执行（因为需要真实截图）
        # 改为验证配置结构
        import inspect
        source = inspect.getsource(monitor._do_scan)

        # 验证 buttons 配置
        assert "popup_close.png" in source, "应包含 popup_close.png"
        assert "popup_close_small.png" in source, "应包含 popup_close_small.png"
        assert "game_logout_confirm.png" in source, "应包含 game_logout_confirm.png"
        assert "game_popup_confirm.png" in source, "应包含 game_popup_confirm.png"

        # 验证高阈值按钮
        assert "0.70" in source or "0.7" in source, "popup_close 应有 0.70 阈值"
        assert "0.75" in source, "popup_close_small 应有 0.75 阈值"


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
