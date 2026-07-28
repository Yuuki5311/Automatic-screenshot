"""Tkinter GUI 主应用。

管理页面切换、后台任务调度、跨线程通信。
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import time

from gui.widgets.qr_display import QRDisplay
from gui.widgets.log_view import LogView


class App(tk.Tk):
    """GUI 主窗口，4 个页面：待命、扫码、进度、完成。"""

    def __init__(self):
        super().__init__()

        self.title("王者荣耀云游戏自动截图")
        self.geometry("480x620")
        self.resizable(True, True)
        self.minsize(400, 500)

        # 禁止直接关闭窗口时残留进程
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # ---- 跨线程通信 ----
        self._queue = queue.Queue()
        self._stop_event = threading.Event()
        self._worker_thread = None

        # ---- 状态 ----
        self._platform_logged_in = False  # 腾讯先锋是否已登录
        self._driver = None               # WebDriver 实例

        # ---- 平台选择（首页直接选定） ----
        self._platform_choice = None
        self._platform_var = tk.StringVar(value="qq_ios")

        # ---- 账号输入 ----
        self._account_var = tk.StringVar(value="")

        # ---- 手动登录 ----
        self._manual_login_event = threading.Event()

        # ---- 构建 UI ----
        self._build_ui()

        # ---- 启动队列轮询 ----
        self._poll_queue()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _build_ui(self):
        """构建所有页面框架。"""

        # ---- 顶部标题栏 ----
        header = ttk.Frame(self)
        header.pack(fill="x", padx=10, pady=(10, 0))
        ttk.Label(
            header, text="王者荣耀云游戏自动截图",
            font=("", 16, "bold")
        ).pack(side="left")

        # ---- 页面容器 ----
        self._page_container = ttk.Frame(self)
        self._page_container.pack(fill="both", expand=True, padx=10, pady=5)

        # ---- 页面 1: 待命页 ----
        self._page_idle = ttk.Frame(self._page_container)
        ttk.Label(
            self._page_idle, text="就绪",
            font=("", 14, "bold")
        ).pack(pady=(20, 5))
        ttk.Label(
            self._page_idle,
            text="选择登录方式并启动",
            font=("", 11)
        ).pack(pady=(0, 10))

        # 腾讯先锋登录方式
        login_frame = ttk.LabelFrame(self._page_idle, text="腾讯先锋登录", padding=10)
        login_frame.pack(pady=5, fill="x", padx=10)
        self._login_type = tk.StringVar(value="qq")
        ttk.Radiobutton(
            login_frame, text="QQ 扫码登录", variable=self._login_type, value="qq"
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            login_frame, text="微信扫码登录", variable=self._login_type, value="wechat"
        ).pack(anchor="w", pady=2)
        ttk.Radiobutton(
            login_frame, text="QQ 密码登录（手动）", variable=self._login_type, value="qq_password"
        ).pack(anchor="w", pady=2)

        # 游戏内登录平台
        platform_frame = ttk.LabelFrame(self._page_idle, text="游戏登录平台", padding=10)
        platform_frame.pack(pady=5, fill="x", padx=10)

        platforms = [
            ("🟢 微信 iOS 好友", "wx_ios"),
            ("🟢 微信安卓好友", "wx_android"),
            ("🔵 QQ iOS 好友", "qq_ios"),
            ("🔵 QQ 安卓好友", "qq_android"),
        ]
        for text, value in platforms:
            ttk.Radiobutton(
                platform_frame, text=text,
                variable=self._platform_var, value=value
            ).pack(anchor="w", pady=2)

        # 账号输入
        account_frame = ttk.LabelFrame(self._page_idle, text="账号（作为截图文件夹名）", padding=10)
        account_frame.pack(pady=5, fill="x", padx=10)
        ttk.Entry(account_frame, textvariable=self._account_var, width=30).pack(fill="x")

        ttk.Button(
            self._page_idle, text="启 动",
            command=self._on_start, width=20
        ).pack(pady=10)

        # ---- 页面 2: 扫码页 ----
        self._page_qr = ttk.Frame(self._page_container)
        self._qr_display = QRDisplay(self._page_qr, qr_size=260)
        self._qr_display.pack(fill="both", expand=True, pady=20)

        # ---- 页面 3: 进度页 ----
        self._page_progress = ttk.Frame(self._page_container)
        self._log_view = LogView(self._page_progress)
        self._log_view.pack(fill="both", expand=True)

        # ---- 页面 4: 完成页（已移除，完成后回到待命页） ----

        # ---- 底部按钮 ----
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._rerun_btn = ttk.Button(
            bottom, text="再执行一轮", command=self._on_start
        )
        self._exit_btn = ttk.Button(
            bottom, text="退 出", command=self._on_close
        )
        self._manual_login_btn = ttk.Button(
            bottom, text="完成登录 →", command=self._on_manual_login_done
        )
        # 初始显示退出按钮，再执行一轮按钮在完成前隐藏
        self._exit_btn.pack(side="right")

        # 默认显示待命页
        self._show_page("idle")

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------

    def _show_page(self, name: str):
        """显示指定页面，隐藏其余。"""
        for page in [self._page_idle, self._page_qr,
                     self._page_progress]:
            page.pack_forget()

        mapping = {
            "idle": self._page_idle,
            "qr": self._page_qr,
            "progress": self._page_progress,
        }
        page = mapping.get(name)
        if page:
            page.pack(fill="both", expand=True)

        # 扫码页的特殊处理：底部退出按钮在扫码时可用
        if name == "qr":
            self._exit_btn.config(state="normal")

    # ------------------------------------------------------------------
    # 按钮事件
    # ------------------------------------------------------------------

    def _on_start(self):
        """点击启动按钮。"""
        if self._worker_thread and self._worker_thread.is_alive():
            return
        self._stop_event.clear()
        self._log_view.clear()
        self._show_page("progress")
        self._log_view.add_log("启动任务...", "info")
        self._exit_btn.config(state="normal")
        self._rerun_btn.pack_forget()  # 运行时隐藏再执行一轮按钮

        # 启动前在主线程锁定选项（避免后台线程读 Tk 变量）
        self._platform_choice = self._platform_var.get()
        self._selected_login_type = self._login_type.get()
        self._log_view.add_log(f"游戏平台: {self._platform_choice}", "info")
        _login_labels = {"qq": "QQ 扫码", "wechat": "微信扫码", "qq_password": "QQ 密码"}
        self._log_view.add_log(
            f"腾讯先锋登录: {_login_labels.get(self._selected_login_type, self._selected_login_type)}",
            "info",
        )

        self._worker_thread = threading.Thread(
            target=self._run_workflow, daemon=True
        )
        self._worker_thread.start()

    def _on_close(self):
        """关闭窗口。"""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=5)
        # 统一清理：cleanup_all() 内部做 quit → 验证 → taskkill 三级降级
        import process_cleanup
        process_cleanup.cleanup_all()
        self.destroy()

    def _on_manual_login_done(self):
        """用户点击完成登录 → 唤醒后台线程。"""
        self._manual_login_event.set()

    # ------------------------------------------------------------------
    # 队列轮询
    # ------------------------------------------------------------------

    def _poll_queue(self):
        """定时从队列取出消息并更新 UI。"""
        try:
            while True:
                msg = self._queue.get_nowait()
                self._handle_message(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _handle_message(self, msg: dict):
        """处理来自后台线程的消息。"""
        msg_type = msg.get("type")

        if msg_type == "log":
            self._log_view.add_log(msg["text"], msg.get("level", "info"))

        elif msg_type == "show_manual_btn":
            self._manual_login_btn.pack(side="right", padx=(0, 5))
        elif msg_type == "hide_manual_btn":
            self._manual_login_btn.pack_forget()

        elif msg_type == "progress":
            self._log_view.update_progress(msg["current"], msg["total"])

        elif msg_type == "qr":
            self._show_page("qr")
            self._qr_display.show_qr(msg["image"], msg["title"])
            self._qr_display.update_status(
                msg.get("status", "⏳ 等待扫码中..."), "gray"
            )

        elif msg_type == "scan_wait":
            self._show_page("qr")
            self._qr_display._title_label.config(text=msg.get("title", ""))
            self._qr_display._image_label.config(image="")
            self._qr_display._tk_image = None
            self._qr_display.update_status(
                msg.get("text", "⏳ 请在浏览器/游戏中扫码..."), "gray"
            )

        elif msg_type == "qr_status":
            self._qr_display.update_status(
                msg["text"], msg.get("color", "black")
            )

        elif msg_type == "page":
            self._show_page(msg["name"])

        elif msg_type == "done":
            self._send({"type": "log", "text": msg["text"], "level": "success"})
            self._show_page("idle")
            self._rerun_btn.pack(side="left", padx=(0, 5))

    # ------------------------------------------------------------------
    # 后台工作流
    # ------------------------------------------------------------------

    def _send(self, msg: dict):
        """线程安全地向 GUI 队列发送消息。"""
        self._queue.put(msg)

    def _run_workflow(self):
        """后台线程：执行完整的登录 → 截图工作流。"""
        from logger import get_logger
        import os
        import json

        _log = get_logger()
        driver = self._driver
        _nav = None
        nav = None
        monitor = None

        try:
            _log.info("工作流线程启动")
            self._send({"type": "log", "text": "正在加载组件..."})
            _entered_via_fast_path = False
            # 依赖应已在 main 主线程预加载；此处再导入以便开发模式懒加载
            from browser import create_browser
            from config import BROWSER_WIDTH, BROWSER_HEIGHT, TEMPLATES_DIR, SCREENSHOTS_DIR, resource_path, writable_path
            from login import web_login, game_login, click_confirm_dialog, manual_login
            from game_launcher import launch_game
            from navigator import Navigator
            from screenshotter import Screenshotter
            from popup_monitor import PopupMonitor
            from ui_loop import UiLoop, run_pre_logout_loop
            _log.info("工作流模块就绪")

            # ====== 阶段 1: 腾讯先锋登录（仅一次） ======
            if not self._platform_logged_in:
                if self._stop_event.is_set():
                    return

                _log.info("[阶段1] 开始腾讯先锋登录")
                login_type = getattr(self, "_selected_login_type", None) or "qq"

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
                    # ---- 扫码登录（原有代码不变，仅删除 login_type = getattr(...) 行） ----
                    self._send({
                        "type": "log",
                        "text": "正在打开 Edge 浏览器（首次需联网下载驱动，可能需 1～2 分钟）...",
                    })

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
                    _log.info(f"[阶段1] 登录方式: {login_type}，浏览器已就绪")
                    self._send({"type": "log", "text": "✅ 浏览器已打开", "level": "success"})

                    def on_qr(image=None):
                        title = f"腾讯先锋{'QQ' if login_type == 'qq' else '微信'}登录"
                        if image is not None:
                            self._send({
                                "type": "qr",
                                "image": image,
                                "title": title,
                                "status": "⏳ 请扫描下方二维码（也可在浏览器窗口扫）...",
                            })
                        else:
                            self._send({
                                "type": "scan_wait",
                                "title": title,
                                "text": "⏳ 未截到二维码，请直接在浏览器窗口扫码...",
                            })

                    def on_status(text):
                        if "成功" in text:
                            self._send({"type": "qr_status", "text": text, "color": "green"})
                        elif "失败" in text or "超时" in text or "⚠" in text:
                            self._send({"type": "qr_status", "text": text, "color": "red"})
                        else:
                            self._send({"type": "qr_status", "text": text})
                        self._send({"type": "log", "text": text,
                                    "level": "success" if "成功" in text else ("error" if "失败" in text or "超时" in text else "info")})

                    self._send({"type": "log", "text": f"开始腾讯先锋{'QQ' if login_type == 'qq' else '微信'}扫码登录..."})

                    if not web_login(driver, login_type, on_qr, on_status):
                        _log.error("[阶段1] 腾讯先锋登录失败")
                        self._send({"type": "log", "text": "❌ 腾讯先锋登录失败", "level": "error"})
                        self._send({"type": "done", "text": "❌ 腾讯先锋登录失败"})
                        return

                    _log.info("[阶段1] 腾讯先锋登录成功")
                    self._platform_logged_in = True
                    self._send({"type": "page", "name": "progress"})
                    self._send({"type": "log", "text": "✅ 腾讯先锋登录成功", "level": "success"})

                # ====== 阶段 2: 搜索游戏并启动 ======
                if self._stop_event.is_set():
                    return

                _log.info("[阶段2] 开始搜索游戏")
                self._send({"type": "log", "text": "正在搜索王者荣耀..."})
                if not launch_game(driver):
                    _log.error("[阶段2] 搜索/启动游戏失败")
                    self._send({"type": "log", "text": "❌ 搜索/启动游戏失败", "level": "error"})
                    self._send({"type": "done", "text": "❌ 启动游戏失败"})
                    return

                _log.info(f"[阶段2] 游戏启动完成，当前 URL: {driver.current_url}")

                self._send({"type": "log", "text": "✅ 已切换到云游戏标签页", "level": "success"})

                # ---- 粗清初始弹窗 → enter_game 快速通道 → 预退出感知环 ----
                self._send({"type": "log", "text": "等待 10 秒后清除初始弹窗..."})
                time.sleep(10)
                _nav = Navigator(driver=driver, templates_dir=resource_path(TEMPLATES_DIR))
                vw, vh = _nav.viewport_size()
                _nav.click_css(vw // 2, int(vh * 0.85))
                self._send({"type": "log", "text": "已尝试清除弹窗"})

                # 优先检查 enter_game：已登录的游戏会话直接进入即可，无需退出重登
                _entered_via_fast_path = False
                if _nav.wait_for_template("enter_game.png", timeout=5):
                    self._send({
                        "type": "log",
                        "text": "检测到进入游戏按钮，跳过预退出环，点击进入...",
                        "level": "success",
                    })
                    _nav.find_and_click("enter_game.png", timeout=5)
                    self._send({
                        "type": "log",
                        "text": "✅ 已点击进入游戏",
                        "level": "success",
                    })
                    time.sleep(3)
                    _nav.cleanup()
                    _entered_via_fast_path = True
                else:
                    self._send({"type": "log", "text": "未检测到进入游戏按钮，启动预退出感知环..."})
                    pre = run_pre_logout_loop(
                        _nav,
                        stop_event=self._stop_event,
                        timeout_s=30.0,
                        tick_s=2.0,
                        on_log=lambda text, level="info": self._send(
                            {"type": "log", "text": text, "level": level}
                        ),
                    )
                    _nav.cleanup()
                    if pre.logout_clicked:
                        self._send({
                            "type": "log",
                            "text": (
                                f"预退出完成（确认: {pre.confirm_clicked}）"
                                if pre.confirm_clicked
                                else "预退出完成（未检测到确认弹窗）"
                            ),
                            "level": "success",
                        })
                    elif pre.timed_out:
                        self._send({
                            "type": "log",
                            "text": "未检测到退出按钮（已超时），关闭预退出环，继续选择平台",
                            "level": "warn",
                        })
                    else:
                        self._send({
                            "type": "log",
                            "text": "未检测到退出按钮（已在平台页），关闭预退出环，继续选择平台",
                            "level": "info",
                        })
                    self._send({"type": "log", "text": "预退出感知环已关闭，开始选择登录平台"})
                monitor = None

            # ====== 阶段 3: 游戏内登录 + 截图 ======
            if self._stop_event.is_set():
                return

            if driver is None:
                _log.error("[阶段3] 浏览器实例不可用")
                self._send({"type": "log", "text": "❌ 浏览器实例不可用，请重新启动", "level": "error"})
                self._send({"type": "done", "text": "❌ 浏览器实例不可用"})
                self._platform_logged_in = False
                return

            # 释放上一个 Navigator 的模板缓存
            if _nav is not None:
                _nav.cleanup()

            self._send({"type": "log", "text": "等待游戏窗口..."})
            nav = Navigator(driver=driver, templates_dir=resource_path(TEMPLATES_DIR))

            # ====== 阶段 3: 游戏登录（最多重试 3 次） ======
            # 若阶段 2 快速通道已点击 enter_game，跳过 game_login 直接进入清理流程
            if _entered_via_fast_path:
                self._send({"type": "log", "text": "快速通道已进入游戏，跳过游戏登录阶段", "level": "info"})
                game_login_ok = True
            else:
                game_login_ok = False

            GAME_LOGIN_MAX_RETRIES = 3

            platform = self._platform_choice or "qq_ios"

            platform_display = {
                "wx_ios": "微信 iOS", "wx_android": "微信安卓",
                "qq_ios": "QQ iOS", "qq_android": "QQ 安卓",
            }.get(platform, platform)
            self._send({"type": "log", "text": f"已选择游戏登录平台: {platform_display}"})

            def on_game_qr(image=None):
                title = f"游戏 {platform_display} 登录"
                if image is not None:
                    self._send({
                        "type": "qr",
                        "image": image,
                        "title": title,
                        "status": "⏳ 请扫描下方二维码（也可在游戏窗口扫）...",
                    })
                else:
                    self._send({
                        "type": "scan_wait",
                        "title": title,
                        "text": "⏳ 未截到二维码，请直接在游戏窗口扫码...",
                    })

            def on_game_status(text):
                if "成功" in text:
                    self._send({"type": "qr_status", "text": text, "color": "green"})
                else:
                    self._send({"type": "qr_status", "text": text})
                self._send({"type": "log", "text": text,
                            "level": "success" if "成功" in text else "info"})

            if not game_login_ok:
                for attempt in range(1, GAME_LOGIN_MAX_RETRIES + 1):
                    if attempt > 1:
                        self._send({"type": "log", "text": f"游戏登录重试 ({attempt}/{GAME_LOGIN_MAX_RETRIES})...", "level": "warn"})

                    # 停止旧的弹窗监控（如有），阶段3不启动后台监控
                    if monitor is not None:
                        monitor.stop()
                        monitor = None

                    _log.info(f"[阶段3] 尝试 {attempt}/{GAME_LOGIN_MAX_RETRIES}, platform={platform}")
                    if game_login(nav, platform, on_game_qr, on_game_status):
                        game_login_ok = True
                        break
                    else:
                        _log.warning(f"[阶段3] 尝试 {attempt}/{GAME_LOGIN_MAX_RETRIES} 失败")

            if not game_login_ok:
                _log.error("[阶段3] 游戏登录失败（3次重试已用完）")
                self._send({"type": "log", "text": "❌ 游戏登录失败（已重试3次）", "level": "error"})
                self._send({"type": "done", "text": "❌ 游戏登录失败"})
                return

            _log.info("[阶段3] 游戏登录成功")
            self._send({"type": "page", "name": "progress"})
            self._send({"type": "log", "text": "✅ 游戏登录成功（已点进入游戏）", "level": "success"})

            # ---- 进入游戏后先等 10 秒，再清返回箭头 + 弹窗，然后验证是否进入主界面 ----
            self._send({"type": "log", "text": "等待 10 秒后处理弹窗..."})
            time.sleep(10)

            # 先处理返回箭头：点进入游戏后可能停在子页面
            ARROW_TIMEOUT = 5
            ARROW_THRESHOLD = 0.75
            while True:
                if nav.find_and_click("back_arrow.png", timeout=ARROW_TIMEOUT, max_retries=1, threshold=ARROW_THRESHOLD):
                    self._send({"type": "log", "text": "已点击返回箭头，继续检查..."})
                    time.sleep(1)
                    continue
                break
            self._send({"type": "log", "text": "返回箭头检查完毕"})

            # 再清弹窗
            self._send({"type": "log", "text": "进入游戏后清理弹窗..."})
            monitor = PopupMonitor(navigator=nav)
            monitor.close_all_popups()
            time.sleep(3)
            monitor.close_all_popups()
            monitor.wait_until_clear(3)
            self._send({"type": "log", "text": "弹窗清理完毕，验证游戏主界面..."})

            if not nav.wait_for_template("game_main.png", timeout=15):
                _log.error("[阶段3] 游戏登录验证失败：未检测到游戏主界面")
                self._send({"type": "log", "text": "❌ 未进入游戏主界面，登录可能失败", "level": "error"})
                self._send({"type": "done", "text": "❌ 未进入游戏主界面"})
                return

            # ====== 阶段 4: 感知环截图（弹窗优先，不再异步 PopupMonitor） ======
            # 设计选项 A：环内同步处理弹窗，避免与主线程抢点击
            account = self._account_var.get().strip()
            if not account:
                account = f"unknown_{time.strftime('%H%M%S')}"
            shot = Screenshotter(
                output_dir=os.path.join(writable_path(SCREENSHOTS_DIR), account),
                driver=driver,
            )

            vw, vh = nav.viewport_size()
            nobility_bounds = (0, 0, vw, int(vh * 0.5))

            _coords = {}
            try:
                with open(resource_path("calibrated_coords.json"), "r") as f:
                    _coords = json.load(f)
            except Exception:
                pass
            _avatar_xy = tuple(_coords.get("avatar", [379, 249]))
            _minion_xy = tuple(_coords.get("minion", [1377, 366]))
            _log.info(f"坐标点击仅保留: avatar={_avatar_xy}, minion={_minion_xy}")

            screenshot_tasks = [
                ("主页", [
                    ("__coords__", "点击左上角头像", _avatar_xy, "game_main.png"),
                    ("tab_home.png", "点击主页标签"),
                ], 0),
                ("英雄", [
                    ("tab_hero.png", "点击英雄标签"),
                ], 0),
                ("万象图鉴首页", [
                    ("tab_illustrated.png", "点击图鉴标签"),
                    ("universal_illustrated.png", "点击万象图鉴"),
                    ("__optional__", "congrats_popup.png", _avatar_xy, "恭贺弹窗"),
                ], 0),
                ("万象图鉴-灵宝", [
                    ("lingbao.png", "点击灵宝"),
                ], 1),
                ("按键", [
                    ("in_game_btn.png", "点击局内按钮"),
                    ("keybind_btn.png", "点击按键按钮"),
                ], 1),
                ("天幕", [
                    ("tianmu.png", "点击天幕"),
                ], 1),
                ("星典藏", [
                    ("xingyuan.png", "点击星元"),
                    ("xing_collection.png", "点击星典藏"),
                ], 0),
                ("星传说", [
                    ("xing_legend.png", "点击星传说"),
                ], 1),
                ("皮肤图鉴", [
                    ("skin_illustrated.png", "点击皮肤图鉴"),
                ], 0),
                ("珍品无双", [
                    ("skin_treasure_wushuang.png", "点击珍品无双"),
                ], 1),
                ("荣耀典藏", [
                    ("skin_glory_collection.png", "点击荣耀典藏"),
                ], 1),
                ("无双", [
                    ("skin_wushuang.png", "点击无双"),
                ], 1),
                ("珍品传说", [
                    ("skin_treasure_legend.png", "点击珍品传说"),
                ], 1),
                ("传说", [
                    ("skin_legend.png", "点击传说"),
                ], 2),
                ("积分夺宝", [
                    ("shop_icon.png", "点击商城"),
                    ("lottery_tab.png", "点击夺宝"),
                    ("points_lottery.png", "点击积分夺宝"),
                ], 2),
                ("货币背包", [
                    ("bag.png", "点击背包"),
                    ("currency_bag.png", "点击货币背包"),
                ], 2),
                ("小兵", [
                    ("customize_icon.png", "点击定制"),
                    ("skin_customize.png", "点击皮肤定制"),
                    ("__coords__", "点击小兵", _minion_xy, "back_arrow.png"),
                ], 1),
                ("个性戳戳", [
                    ("customize_icon.png", "点击定制"),
                    ("personal_customize.png", "点击个性定制"),
                    ("poke.png", "点击个性戳戳"),
                ], 1),
                ("贵族", [
                    ("nobility_icon.png", "点击贵族图标", nobility_bounds),
                ], 1),
            ]

            total = len(screenshot_tasks)

            def _do_recover():
                """尝试从游戏重启中恢复。返回 True 表示恢复成功。"""
                self._send({"type": "log", "text": "等待游戏恢复（最多 60s）...", "level": "warn"})
                start = time.time()
                game_templates = [
                    "game_wx_ios.png", "game_wx_android.png",
                    "game_qq_ios.png", "game_qq_android.png",
                ]
                while time.time() - start < 60:
                    if self._stop_event.is_set():
                        return False
                    if nav.wait_for_template("game_main.png", timeout=2):
                        self._send({"type": "log", "text": "检测到游戏主界面，无需重新登录", "level": "info"})
                        return True
                    for tpl in game_templates:
                        if nav.wait_for_template(tpl, timeout=1, threshold=0.6):
                            self._send({"type": "log", "text": "检测到登录界面，重新登录...", "level": "info"})
                            return bool(game_login(nav, platform, on_game_qr, on_game_status))
                    time.sleep(2)
                self._send({"type": "log", "text": "等待游戏恢复超时", "level": "error"})
                return False

            def _on_log(text, level="info"):
                self._send({"type": "log", "text": text, "level": level})

            def _on_progress(cur, tot):
                self._send({"type": "progress", "current": cur, "total": tot})

            self._send({"type": "log", "text": "启动感知环截图（弹窗优先）"})
            _log.info("阶段 4 感知环启动")
            success = UiLoop(
                nav=nav,
                shot=shot,
                tasks=screenshot_tasks,
                stop_event=self._stop_event,
                on_log=_on_log,
                on_progress=_on_progress,
                recover=_do_recover,
                relogin=lambda: game_login(nav, platform, on_game_qr, on_game_status),
                avatar_coords=_avatar_xy,
            ).run()

            if self._stop_event.is_set():
                return

            self._send({"type": "progress", "current": total, "total": total})
            self._send({"type": "log", "text": f"完成: {success}/{total} 张截图成功", "level": "success"})

            # ====== 截图完成，关闭云游戏并退出浏览器 ======
            self._send({"type": "log", "text": "正在关闭云游戏标签页...", "level": "info"})
            try:
                handles = driver.window_handles
                if len(handles) > 1:
                    # Step 1: 关闭云游戏标签页（触发 TCP RST，服务端回收容器）
                    driver.close()
                    # Step 2: 切回先锋首页，清 Storage 破坏重连上下文
                    driver.switch_to.window(handles[0])
                    try:
                        driver.execute_script(
                            "localStorage.clear(); sessionStorage.clear();")
                    except Exception:
                        pass
                    self._send({"type": "log", "text": "云游戏标签页已关闭，Storage 已清理", "level": "success"})
            except Exception:
                self._send({"type": "log", "text": "关闭云游戏标签页失败", "level": "warn"})

            # Step 3: 关闭整个浏览器
            self._send({"type": "log", "text": "正在关闭浏览器...", "level": "info"})
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
                driver = None
            self._driver = None
            self._platform_logged_in = False
            self._send({"type": "log", "text": "浏览器已关闭", "level": "success"})

            self._send({
                "type": "done",
                "text": f"✅ 本轮完成: {success}/{total} 张截图"
            })

        except Exception as e:
            import traceback
            _log.exception(f"工作流异常: {e}")
            self._send({"type": "log", "text": f"异常: {e}", "level": "error"})
            self._send({"type": "done", "text": f"❌ 运行异常: {e}"})
            traceback.print_exc()
        finally:
            if monitor is not None:
                monitor.stop()
            if _nav is not None:
                _nav.cleanup()
            if nav is not None:
                nav.cleanup()
            # 兜底：确保浏览器已关闭
            if driver is not None:
                try:
                    driver.quit()
                except Exception:
                    pass
                # quit 后移出追踪（无论成功失败都移出，失败由 cleanup_all 兜底）
                import process_cleanup
                process_cleanup.unregister_driver(driver)
                driver = None
            self._driver = None

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def run(self):
        """启动 GUI 主循环。"""
        self.mainloop()
