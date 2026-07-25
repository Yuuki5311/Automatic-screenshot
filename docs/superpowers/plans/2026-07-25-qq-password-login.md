# QQ 密码登录（半自动）实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**目标:** 在腾讯先锋登录栏新增"QQ 密码登录（手动）"选项——脚本打开浏览器，用户手动完成登录，点击"完成登录"按钮后脚本验证并继续。

**架构:** 两文件改动——`login.py` 新增 `manual_login()` 半自动等待函数，`gui/app.py` 新增 radio 按钮、完成登录按钮、跨线程事件和 `qq_password` 工作流分支。

**技术栈:** Python 3.12, tkinter, Selenium WebDriver, threading.Event

## 全局约束

- 不修改 `web_login()` 函数
- 不修改扫码登录流程
- 不修改 `game_launcher.py`
- 不修改阶段 2/3/4
- 手动登录超时默认 600 秒（10 分钟）

---

### 任务 1: `login.py` — 新增 `manual_login()` 函数

**文件:**
- 修改: `C:\Automatic-screenshot\login.py`: 在 `web_login()` 函数之后添加

**接口:**
- 消费: `WebDriver`, `CLOUD_GAMING_URL`, `PAGE_LOAD_WAIT`, `NoSuchElementException`, `By`, `time`
- 产出: `manual_login(driver, on_status, ready_event, timeout) -> bool`

- [ ] **步骤 1: 运行现有测试确认基线**

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 全部 97 项测试通过。

- [ ] **步骤 2: 在 `login.py` 中新增 `manual_login()` 函数**

在 `web_login()` 函数结束的 `return False` 之后（约第 339 行），`# ---------------------------------------------------------------------------\n# 游戏内登录` 注释之前，插入：

```python
def manual_login(
    driver: WebDriver,
    on_status: Callable[[str], None] | None = None,
    ready_event=None,
    timeout: int = 600,
) -> bool:
    """打开 gamer.qq.com，等待用户手动完成 QQ 密码登录。

    与 web_login 不同：不点击登录按钮、不选平台、不切 iframe。
    打开页面后进入轮询，等待用户在浏览器中自行完成登录。

    Args:
        driver: Selenium WebDriver 实例。
        on_status: 状态更新回调。
        ready_event: threading.Event，用户点击"完成登录"时设置。
        timeout: 等待超时（秒），默认 10 分钟。

    Returns:
        bool: 登录成功返回 True。
    """
    if on_status:
        on_status("请在浏览器中手动完成 QQ 登录...")

    # 1. 打开 gamer.qq.com
    log.info(f"手动登录模式，正在打开: {CLOUD_GAMING_URL}")
    try:
        driver.set_page_load_timeout(60)
        driver.get(CLOUD_GAMING_URL)
    except Exception as e:
        if on_status:
            on_status(f"打开腾讯先锋页面失败: {e}")
        log.exception("手动登录打开 CLOUD_GAMING_URL 失败")
        return False
    log.info(f"页面已打开: {driver.current_url}")
    time.sleep(PAGE_LOAD_WAIT)

    # 2. 轮询等待用户完成登录
    start = time.time()
    while time.time() - start < timeout:

        # 检测登录成功（复用 web_login 的检测逻辑）
        try:
            driver.switch_to.default_content()
        except Exception:
            pass

        # 5a. 检测登录弹窗关闭
        try:
            login_popup = driver.find_element(By.ID, "user_login")
            if not login_popup.is_displayed():
                if on_status:
                    on_status("✅ 腾讯先锋登录成功（弹窗已关闭）")
                time.sleep(PAGE_LOAD_WAIT)
                return True
        except NoSuchElementException:
            if on_status:
                on_status("✅ 腾讯先锋登录成功（已登录）")
            time.sleep(PAGE_LOAD_WAIT)
            return True
        except Exception:
            pass

        # 5b. Cookie 检测
        try:
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie.get("name", "") in (
                    "p_uin", "p_skey", "pt2gguin", "uin", "skey",
                ):
                    if on_status:
                        on_status("✅ 腾讯先锋登录成功（Cookie 检测）")
                    time.sleep(PAGE_LOAD_WAIT)
                    return True
        except Exception:
            pass

        # 5c. JS 检测
        try:
            logged_in = driver.execute_script("""
                if (document.cookie.indexOf('p_uin=') > -1) return true;
                if (document.cookie.indexOf('uin=') > -1) return true;
                if (document.querySelector('[class*="user"]')) return true;
                if (document.querySelector('[class*="avatar"]')) return true;
                return false;
            """)
            if logged_in:
                if on_status:
                    on_status("✅ 腾讯先锋登录成功（JS 检测）")
                time.sleep(PAGE_LOAD_WAIT)
                return True
        except Exception:
            pass

        # 5d. CSS 检测用户元素
        user_selectors = [
            ".user-info", ".user-name", ".user-avatar", ".avatar",
            "img[class*='avatar']", "[class*='user']", "[class*='nickname']",
            ".header-avatar", ".login-user", "#user-info",
        ]
        for sel in user_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, sel)
                for elem in elements:
                    if elem.is_displayed():
                        if on_status:
                            on_status("✅ 腾讯先锋登录成功（用户元素检测）")
                        time.sleep(PAGE_LOAD_WAIT)
                        return True
            except Exception:
                continue

        # 如果 ready_event 被设置，做一次额外验证后给出反馈
        if ready_event is not None and ready_event.is_set():
            if on_status:
                on_status("⚠️ 未检测到登录状态，请确认已登录后再次点击")
            ready_event.clear()

        time.sleep(2)

    if on_status:
        on_status("⚠️ 手动登录超时")
    return False
```

- [ ] **步骤 3: 运行测试确认无回归**

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 全部 97 项测试通过。

- [ ] **步骤 4: 提交**

```bash
cd C:\Automatic-screenshot
git add login.py
git commit -m "feat: add manual_login() for semi-automated QQ password login

Opens gamer.qq.com and polls for login success without clicking
buttons or switching iframes. Supports a ready_event for GUI
integration — user manually logs in then clicks 'done' button.

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---

### 任务 2: `gui/app.py` — GUI 控件 + 事件 + 工作流分支

**文件:**
- 修改: `C:\Automatic-screenshot\gui\app.py`

**接口:**
- 消费: `manual_login()` from Task 1, `threading.Event`, `create_browser`
- 产出: `_manual_login_event`, `_manual_login_btn`, `_on_manual_login_done()`, `show_manual_btn`/`hide_manual_btn` 消息, `qq_password` 工作流分支

- [ ] **步骤 1: 运行测试确认基线**

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 全部 97 项测试通过。

- [ ] **步骤 2: 在 `__init__` 中添加 `_manual_login_event`**

将以下内容添加到 `self._account_var = tk.StringVar(value="")` 之后（第 45 行附近）：

```python
        # ---- 手动登录 ----
        self._manual_login_event = threading.Event()
```

- [ ] **步骤 3: 在 `_build_ui` 的待命页中添加 radio button**

将以下内容添加到第 93 行 `ttk.Radiobutton(... text="微信扫码登录" ...)` 之后：

```python
        ttk.Radiobutton(
            login_frame, text="QQ 密码登录（手动）", variable=self._login_type, value="qq_password"
        ).pack(anchor="w", pady=2)
```

- [ ] **步骤 4: 在 `_build_ui` 的底部栏添加"完成登录"按钮**

将以下内容添加到 `self._exit_btn.pack(side="right")` 之前（约第 185 行）：

```python
        self._manual_login_btn = ttk.Button(
            bottom, text="完成登录 →", command=self._on_manual_login_done
        )
        # 初始隐藏，仅手动登录时通过 pack 显示
```

- [ ] **步骤 5: 添加 `_on_manual_login_done` 回调**

在 `_on_close` 方法之后（约第 280 行），在 `# 队列轮询` 注释之前，添加：

```python
    def _on_manual_login_done(self):
        """用户点击完成登录 → 唤醒后台线程。"""
        self._manual_login_event.set()
```

- [ ] **步骤 6: 在 `_handle_message` 中添加按钮显隐消息处理**

在 `_handle_message` 方法中（约第 296 行），在现有的 `if msg_type == ...` 链中添加：

```python
        elif msg_type == "show_manual_btn":
            self._manual_login_btn.pack(side="right", padx=(0, 5))
        elif msg_type == "hide_manual_btn":
            self._manual_login_btn.pack_forget()
```

添加位置建议在 `msg_type == "log"` 处理和 `msg_type == "progress"` 处理之间。

- [ ] **步骤 7: 在 `_run_workflow` 中添加 `qq_password` 分支**

这是最关键的变更。当前阶段 1（约第 372-432 行）的结构是：

```python
if not self._platform_logged_in:
    # 创建浏览器
    driver = create_browser(...)
    login_type = ...
    
    # 扫码登录回调
    def on_qr(...): ...
    def on_status(...): ...
    
    # 调用 web_login
    if not web_login(driver, login_type, on_qr, on_status):
        ...
        return
```

需要将其包装为：当 `login_type == "qq_password"` 时走不同路径。

在第 396 行 `login_type = getattr(self, "_selected_login_type", None) or "qq"` 之后，将现有的扫码登录流程（创建浏览器 → on_qr/on_status → web_login）包装在 `if login_type != "qq_password":` 分支中，然后新增 `else:` 分支。

具体做法：在 `login_type` 赋值行之后，浏览器创建之前，添加条件分支。

**改动前（第 383-396 行附近）：**
```python
                try:
                    driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
                except Exception as e:
                    ...
                    return

                self._driver = driver
                login_type = getattr(self, "_selected_login_type", None) or "qq"
                _log.info(f"[阶段1] 登录方式: {login_type}，浏览器已就绪")
                self._send({"type": "log", "text": "✅ 浏览器已打开", "level": "success"})
                # ... on_qr, on_status, web_login ...
```

**改动后：**
```python
                login_type = getattr(self, "_selected_login_type", None) or "qq"

                # ---- 半自动密码登录分支 ----
                if login_type == "qq_password":
                    _log.info("[阶段1] 手动密码登录模式")
                    try:
                        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
                    except Exception as e:
                        _log.exception("[阶段1] 打开浏览器失败")
                        self._send({
                            "type": "log",
                            "text": f"❌ 打开浏览器失败: {e}",
                            "level": "error",
                        })
                        self._send({"type": "done", "text": f"❌ 打开浏览器失败:\n{e}"})
                        return

                    self._driver = driver
                    self._send({"type": "log", "text": "✅ 浏览器已打开", "level": "success"})

                    def _on_status(text):
                        if "成功" in text:
                            self._send({"type": "log", "text": text, "level": "success"})
                        elif "失败" in text or "超时" in text or "⚠" in text:
                            self._send({"type": "log", "text": text, "level": "error" if "失败" in text else "warn"})
                        else:
                            self._send({"type": "log", "text": text})

                    self._send({"type": "log", "text": "请在浏览器中手动完成 QQ 登录..."})
                    self._send({"type": "page", "name": "progress"})
                    self._queue.put({"type": "show_manual_btn"})

                    if not manual_login(driver, _on_status, ready_event=self._manual_login_event):
                        self._queue.put({"type": "hide_manual_btn"})
                        self._send({"type": "done", "text": "❌ 手动登录失败或超时"})
                        return

                    self._queue.put({"type": "hide_manual_btn"})
                    self._platform_logged_in = True
                    self._send({"type": "page", "name": "progress"})
                    self._send({"type": "log", "text": "✅ 腾讯先锋登录成功", "level": "success"})
                    # 跳到阶段 2 之前（跳过扫码登录流程）
                    # 注意：下面的阶段 2 代码在 if not self._platform_logged_in 块之外，
                    # 所以需要确保 login_type == "qq_password" 时不进入扫码分支

                else:
                    # ---- 扫码登录分支（原有代码） ----
                    try:
                        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
                    except Exception as e:
                        ...  # 保持原有错误处理不变
```

实际上，查看完整的阶段 1 代码结构（第 372-432 行），整个阶段 1 都在 `if not self._platform_logged_in:` 块内。阶段 2（`launch_game`）在 `if not self._platform_logged_in:` 块之后（第 439 行附近）。

最简单的做法是：在阶段 1 块内，将创建浏览器到 `web_login` 调用之间的代码（第 383-432 行）用 `if login_type == "qq_password":` / `else:` 分支包装。

让我重新阅读精确的行号范围。之前阅读时看到了第 372 行开始的阶段 1 代码和 `web_login` 调用。扫码登录分支中 `if not web_login(...)` 在第 428 行左右。阶段 1 块在第 435 行 `self._platform_logged_in = True` 结束。

正确的重构方式：将现有扫码登录的整个代码（浏览器创建 → on_qr/on_status → web_login → 错误处理）包裹在 `else:` 中，在 `if login_type == "qq_password":` 分支中写半自动流程。

由于 `login_type` 变量需要在创建浏览器之前确定，我们需要调整代码顺序——把 `login_type` 的赋值移到 `create_browser` 之前。

查看当前顺序：
```python
if not self._platform_logged_in:          # 373
    ...
    try:                                   # 383
        driver = create_browser(...)       # 384
    except: ...
    self._driver = driver                  # 395
    login_type = getattr(...)              # 396
    ...
    # on_qr, on_status 回调                 # 400-421
    ...
    if not web_login(driver, login_type, on_qr, on_status):  # 428
```

需要改为：
```python
if not self._platform_logged_in:
    ...
    login_type = getattr(...)              # 移到前面
    
    if login_type == "qq_password":
        # 半自动流程
        ...
    else:
        # 扫码流程（原有代码）
        ...
```

这是一个结构性的调整。让我确保计划中的代码是完整、正确的。

由于这个重构涉及几十行代码的缩进调整，在计划中标记为需要将原有扫码代码包裹在 `else:` 中。我会在步骤 7 中给出完整的前后对比。

但完整的代码太长了。让我在实际步骤中给出关键的结构变化，并附带解释。

实际上，对于计划来说，我应该给出精确的代码。但是整个阶段 1 的代码有约 60 行，全部重写太冗长。让我改用简洁但精确的方式：说明结构调整，给出新增分支的完整代码，并说明原有代码保持不变（仅被包裹在 else 中）。

对于步骤 7，我给出：
1. 移动 `login_type` 赋值到阶段 1 块开头
2. 新增 `if login_type == "qq_password":` 分支的完整代码
3. 将原有代码包裹在 `else:` 中的说明

让我写出这个步骤。

- [ ] **步骤 7: 在 `_run_workflow` 阶段 1 中添加 `qq_password` 分支**

**7a. 将 `login_type` 赋值提前：**

在阶段 1 的 `if not self._platform_logged_in:` 块内，紧接着（第 374 行 stop_event 检查之后），将：

```python
                _log.info("[阶段1] 开始腾讯先锋登录")
```

之后、浏览器创建 `try: driver = create_browser(...)` 之前，添加：

```python
                login_type = getattr(self, "_selected_login_type", None) or "qq"
```

同时删除第 396 行原有的 `login_type = getattr(...)` 行。

**7b. 在浏览器创建前插入分支：**

将浏览器创建和扫码登录的整个代码块（约第 383-432 行：从 `try: driver = create_browser` 到 `if not web_login(...)` 错误处理的末尾）包裹为：

```python
                if login_type == "qq_password":
                    # ---- 半自动密码登录 ----
                    _log.info("[阶段1] 手动密码登录模式")
                    try:
                        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
                    except Exception as e:
                        _log.exception("[阶段1] 打开浏览器失败")
                        self._send({"type": "log", "text": f"❌ 打开浏览器失败: {e}", "level": "error"})
                        self._send({"type": "done", "text": f"❌ 打开浏览器失败:\n{e}"})
                        return

                    self._driver = driver
                    self._send({"type": "log", "text": "✅ 浏览器已打开", "level": "success"})

                    def _on_status(text):
                        if "成功" in text:
                            self._send({"type": "log", "text": text, "level": "success"})
                        elif "失败" in text or "超时" in text or "⚠" in text:
                            self._send({"type": "log", "text": text,
                                        "level": "error" if "失败" in text else "warn"})
                        else:
                            self._send({"type": "log", "text": text})

                    self._send({"type": "log", "text": "请在浏览器中手动完成 QQ 登录..."})
                    self._send({"type": "page", "name": "progress"})
                    self._queue.put({"type": "show_manual_btn"})

                    if not manual_login(driver, _on_status, ready_event=self._manual_login_event):
                        self._queue.put({"type": "hide_manual_btn"})
                        self._send({"type": "done", "text": "❌ 手动登录失败或超时"})
                        return

                    self._queue.put({"type": "hide_manual_btn"})
                    self._platform_logged_in = True
                    self._send({"type": "page", "name": "progress"})
                    self._send({"type": "log", "text": "✅ 腾讯先锋登录成功", "level": "success"})

                else:
                    # ---- 扫码登录（原有代码不变） ----
                    try:
                        driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)
                    except Exception as e:
                        ...  # 保持原有
                    # ... 所有原有扫码登录代码保持不变 ...
```

注意：原有扫码分支中需要删除 `login_type = getattr(...)` 行（因为已提前），其余完全不变。
```

- [ ] **步骤 8: 运行测试确认无回归**

```bash
cd C:\Automatic-screenshot && python -m pytest test_core.py -q --tb=short
```

预期: 全部 97 项测试通过。

- [ ] **步骤 9: 提交**

```bash
cd C:\Automatic-screenshot
git add gui/app.py
git commit -m "feat: add QQ password login option with manual login flow

- Add 'QQ 密码登录（手动）' radio button to idle page
- Add '完成登录 →' button (hidden by default, shown during manual login)
- Add _manual_login_event for cross-thread coordination
- Add qq_password branch in _run_workflow stage 1

Co-Authored-By: Claude <noreply@anthropic.com>"
```
