# 阶段 3 游戏登录流程重构 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 将 `game_login()` 从扫码流程改为授权登录流程——快速检测 enter_game、清弹窗、点平台、点两次授权登录、点进入游戏。

**架构:** 单文件单函数改动——`login.py` 的 `game_login()`，从第 576 行起替换整个扫码循环为新流程。

**技术栈:** Python 3.12, Selenium (Navigator 模板匹配), OpenCV

## 全局约束

- 仅修改 `login.py` 的 `game_login()` 函数内部
- 不修改 `gui/app.py` — `game_login()` 调用方式不变
- 不修改 `ui_loop.py` / `ui_state.py` / `click_confirm.py`
- 不修改阶段 2 / 阶段 4
- 新增模板: `game_auth_login_1.png`, `game_auth_login_2.png`
- 授权登录按钮搜索区域: 下半屏 (`bottom_half_bounds`)

---

### 任务 1: 重写 `game_login()` — 替换扫码循环为授权登录流程

**文件:**
- 修改: `C:\Automatic-screenshot\login.py`: 第 576-685 行（从 `# ---- 1a. 检查「登录其他账号」弹窗 ----` 到函数末尾）

**接口:**
- 消费: `Navigator.find_and_click()`, `Navigator.wait_for_template()`, `Navigator.viewport_size()`, `close_perception_popup()`, `bottom_half_bounds()`, `platform_select_bounds()`, `PLATFORM_TEMPLATES`
- 产出: `game_login(nav, platform, on_qr, on_status, timeout) -> bool` — 签名不变

- [ ] **步骤 1: 运行现有测试确认基线**

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 全部 97 项测试通过。注意: 有关于 `game_login` 的测试（如 `TestGameLoginPlatformFallback`、`TestGameLoginAfterQrBackToPlatform`）可能会失败，因为它们测试旧的扫码逻辑。如果失败，这些测试需要在步骤 3 中更新。

- [ ] **步骤 2: 替换 `game_login()` 第 576 行到函数末尾**

删除从 `# ---- 1a. 检查「登录其他账号」弹窗 ----`（第 576 行）到函数末尾 `return False`（第 685 行）的全部代码。

替换为：

```python
    # ---- 1a. 快速检测 enter_game ----
    if nav.wait_for_template("enter_game.png", timeout=2):
        on_status("检测到进入游戏按钮，直接进入...")
        if nav.find_and_click("enter_game.png", timeout=5):
            on_status("✅ 已点击进入游戏")
            time.sleep(3)
            return True

    # ---- 2. 感知环清弹窗 ----
    on_status("清理弹窗...")
    from ui_loop import close_perception_popup
    for _ in range(3):
        close_perception_popup(nav)
        time.sleep(1)

    # ---- 3. 点击平台登录按钮 ----
    on_status(f"选择登录平台: {platform_name}...")
    time.sleep(2)

    if not nav.find_and_click(template_file, timeout=10, bounds=platform_bounds, max_retries=5):
        on_status(f"找不到 {platform_name} 登录按钮 ({template_file})")
        if nav.wait_for_template("game_logout_btn.png", timeout=3):
            on_status("检测到退出按钮，回退到退出登录步骤...")
            from ui_loop import run_pre_logout_loop

            pre = run_pre_logout_loop(nav, on_log=lambda text, level="info": on_status(text))
            if pre.logout_clicked:
                on_status("已回退退出，重新选择登录平台...")
            elif pre.timed_out:
                on_status("回退退出超时，仍尝试选择平台...")
            time.sleep(2)
            vw, vh = nav.viewport_size()
            platform_bounds = platform_select_bounds(vw, vh, platform)
            if not nav.find_and_click(
                template_file, timeout=10, bounds=platform_bounds, max_retries=5
            ):
                on_status(f"回退后仍找不到 {platform_name} 登录按钮")
                return False
        else:
            return False

    on_status(f"已选择 {platform_name} 登录")

    # ---- 4. 点击授权登录按钮 1 ----
    time.sleep(2)
    auth_bounds = bottom_half_bounds(vw, vh)
    if not nav.find_and_click("game_auth_login_1.png", timeout=10, bounds=auth_bounds, max_retries=3):
        on_status("⚠️ 找不到授权登录按钮 1，将重试")
        return False
    on_status("已点击授权登录 1")

    # ---- 5. 点击授权登录按钮 2 ----
    time.sleep(2)
    vw, vh = nav.viewport_size()
    auth_bounds = bottom_half_bounds(vw, vh)
    if not nav.find_and_click("game_auth_login_2.png", timeout=10, bounds=auth_bounds, max_retries=3):
        on_status("⚠️ 找不到授权登录按钮 2，将重试")
        return False
    on_status("已点击授权登录 2")

    # ---- 6. 点击进入游戏 ----
    time.sleep(2)
    if nav.find_and_click("enter_game.png", timeout=10):
        on_status("✅ 已点击进入游戏")
        time.sleep(3)
        return True

    on_status("⚠️ 未找到进入游戏按钮")
    return False
```

- [ ] **步骤 3: 更新测试**

旧的 `TestGameLoginPlatformFallback` 和 `TestGameLoginAfterQrBackToPlatform` 测试旧扫码逻辑。将这些测试更新为测试新授权登录流程。检查 `test_core.py` 中所有引用 `game_login` 的测试。

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 所有与新流程一致的测试通过。

- [ ] **步骤 4: 提交**

```bash
cd C:\Automatic-screenshot
git add login.py test_core.py
git commit -m "feat: replace QR scan flow with auth login flow in game_login

New flow: quick-check enter_game → clear popups → click platform →
click auth_login_1 → click auth_login_2 → click enter_game.
Removes QR detection loop, avatar polling, and QR platform reclick logic.

Co-Authored-By: Claude <noreply@anthropic.com>"
```
