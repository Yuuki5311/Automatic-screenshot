"""Tests for __optional__ popup handling in _do_click_step."""

import numpy as np
from unittest.mock import MagicMock, patch

from ui_loop import Goal, UiLoop, parse_click_item


def test_parse_optional_format():
    """parse_click_item correctly handles __optional__ 4-tuple."""
    item = ("__optional__", "congrats_popup.png", (379, 249), "test popup")
    result = parse_click_item(item)
    assert result["template"] == "__optional__"
    assert result["desc"] == "congrats_popup.png"
    assert result["bounds"] == (379, 249)
    assert result["anchor"] == "test popup"


def test_goal_advances_after_optional():
    """Goal.advance_after_click advances past optional step."""
    tasks = [("Test Task", [
        ("tab1.png", "click tab1"),
        ("__optional__", "popup.png", (100, 200), "optional popup"),
        ("tab2.png", "click tab2"),
    ], 0)]
    goal = Goal(tasks)
    assert goal.click_index == 0
    goal.advance_after_click()
    assert goal.click_index == 1
    goal.advance_after_click()
    assert goal.click_index == 2


def test_optional_popup_found():
    """__optional__ popup FOUND -> click dismiss coords -> advance."""
    nav = MagicMock()
    nav.viewport_size.return_value = (1920, 1080)

    mock_plan = MagicMock()
    mock_plan.x = 500
    mock_plan.y = 300
    mock_plan.score = 0.85
    mock_plan.roi_box = (490, 290, 20, 20)
    mock_plan.roi_ref = np.zeros((20, 20, 3), dtype=np.uint8)
    mock_plan.template_name = "congrats_popup.png"

    with patch("click_confirm.plan_template_click", return_value=mock_plan), \
         patch.object(UiLoop, "_popup_pending", return_value=False):
        tasks = [("Test", [
            ("__optional__", "congrats_popup.png", (379, 249), "test"),
        ], 0)]
        loop = UiLoop(
            nav=nav, shot=MagicMock(), tasks=tasks,
            on_log=lambda text, level="info": None,
            on_progress=lambda cur, tot: None,
        )
        loop._do_click_step()

        assert loop.goal.click_index == 1
        nav.click_css.assert_called_once_with(379, 249)


def test_optional_popup_not_found():
    """__optional__ popup NOT FOUND -> skip -> still advance."""
    nav = MagicMock()
    nav.viewport_size.return_value = (1920, 1080)

    with patch("click_confirm.plan_template_click", return_value=None), \
         patch.object(UiLoop, "_popup_pending", return_value=False):
        tasks = [("Test", [
            ("__optional__", "missing.png", (379, 249), "not found"),
        ], 0)]
        loop = UiLoop(
            nav=nav, shot=MagicMock(), tasks=tasks,
            on_log=lambda text, level="info": None,
            on_progress=lambda cur, tot: None,
        )
        loop._do_click_step()

        assert loop.goal.click_index == 1
        nav.click_css.assert_not_called()


def test_normal_click_then_optional():
    """Normal template click then optional -- both work in sequence."""
    nav = MagicMock()
    nav.viewport_size.return_value = (1920, 1080)

    mock_plan = MagicMock()
    mock_plan.x = 600
    mock_plan.y = 400
    mock_plan.score = 0.90
    mock_plan.roi_box = (590, 390, 20, 20)
    mock_plan.roi_ref = np.zeros((20, 20, 3), dtype=np.uint8)
    mock_plan.template_name = "tab1.png"

    with patch("click_confirm.plan_template_click", return_value=mock_plan), \
         patch("click_confirm.confirm_roi", return_value=(True, 0.95)), \
         patch("click_confirm.execute_click_with_confirm", return_value=True), \
         patch.object(UiLoop, "_popup_pending", return_value=False):

        tasks = [("Test", [
            ("tab1.png", "click tab1"),
            ("__optional__", "popup.png", (100, 200), "optional"),
        ], 0)]
        loop = UiLoop(
            nav=nav, shot=MagicMock(), tasks=tasks,
            on_log=lambda text, level="info": None,
            on_progress=lambda cur, tot: None,
        )

        # First click: normal template
        loop._do_click_step()
        assert loop.goal.click_index == 1

        # Second click: optional popup not found -> still advance
        with patch("click_confirm.plan_template_click", return_value=None), \
             patch.object(UiLoop, "_popup_pending", return_value=False):
            loop._do_click_step()
        assert loop.goal.click_index == 2


def test_path_templates_includes_optional():
    """path_templates includes the optional template for ON_PATH detection."""
    tasks = [("Test", [
        ("__optional__", "popup.png", (100, 200), "optional"),
    ], 0)]
    goal = Goal(tasks)
    templates = goal.path_templates()
    assert "popup.png" in templates


def test_optional_no_retry():
    """__optional__ does NOT retry -- returns immediately."""
    nav = MagicMock()
    nav.viewport_size.return_value = (1920, 1080)

    call_count = [0]

    def fake_plan(n, screen, template_name, bounds=None, threshold=None):
        call_count[0] += 1
        return None

    with patch("click_confirm.plan_template_click", side_effect=fake_plan), \
         patch.object(UiLoop, "_popup_pending", return_value=False):
        tasks = [("Test", [
            ("__optional__", "popup.png", (100, 200), "test"),
        ], 0)]
        loop = UiLoop(
            nav=nav, shot=MagicMock(), tasks=tasks,
            on_log=lambda text, level="info": None,
            on_progress=lambda cur, tot: None,
        )
        loop._do_click_step()

        assert call_count[0] == 1, \
            f"Optional should call plan_template_click once, got {call_count[0]}"
        assert loop.goal.click_index == 1
