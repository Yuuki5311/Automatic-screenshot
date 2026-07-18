"""Tkinter GUI 主应用。

管理页面切换、后台任务调度、跨线程通信。
"""

import tkinter as tk
from tkinter import ttk
import threading
import queue
import time
import random

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
        self._is_rerun = False            # 是否为再跑一轮

        # ---- 平台选择（首页直接选定） ----
        self._platform_choice = None
        self._platform_var = tk.StringVar(value="qq_ios")

        # ---- 账号输入 ----
        self._account_var = tk.StringVar(value="")

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

        # ---- 页面 4: 完成页 ----
        self._page_done = ttk.Frame(self._page_container)
        self._done_summary = ttk.Label(
            self._page_done, text="", font=("", 12)
        )
        self._done_summary.pack(pady=(30, 5))

        # 下一轮确认区
        self._next_round_frame = ttk.LabelFrame(self._page_done, text="是否执行下一轮？", padding=10)
        self._next_round_frame.pack(pady=10, fill="x", padx=20)

        # 登录方式
        ttk.Label(self._next_round_frame, text="登录方式：").pack(anchor="w")
        self._next_login_type = tk.StringVar(value="qq")
        next_login_frame = ttk.Frame(self._next_round_frame)
        next_login_frame.pack(anchor="w", pady=(0, 8))
        ttk.Radiobutton(next_login_frame, text="QQ", variable=self._next_login_type, value="qq").pack(side="left", padx=(0, 10))
        ttk.Radiobutton(next_login_frame, text="微信", variable=self._next_login_type, value="wechat").pack(side="left")

        ttk.Label(self._next_round_frame, text="账号：").pack(anchor="w")
        self._next_account_var = tk.StringVar()
        ttk.Entry(self._next_round_frame, textvariable=self._next_account_var, width=30).pack(fill="x", pady=(0, 8))

        ttk.Label(self._next_round_frame, text="平台：").pack(anchor="w")
        self._next_platform_var = tk.StringVar(value="qq_ios")
        next_platforms = [
            ("🟢 微信 iOS", "wx_ios"),
            ("🟢 微信安卓", "wx_android"),
            ("🔵 QQ iOS", "qq_ios"),
            ("🔵 QQ 安卓", "qq_android"),
        ]
        for text, value in next_platforms:
            ttk.Radiobutton(
                self._next_round_frame, text=text,
                variable=self._next_platform_var, value=value
            ).pack(anchor="w", pady=1)

        next_btn_frame = ttk.Frame(self._page_done)
        next_btn_frame.pack(pady=10)
        ttk.Button(
            next_btn_frame, text="确认执行下一轮",
            command=self._on_next_round, width=18
        ).pack(side="left", padx=5)
        ttk.Button(
            next_btn_frame, text="退 出",
            command=self._on_close, width=15
        ).pack(side="left", padx=5)

        # ---- 底部退出按钮 ----
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 10))
        self._exit_btn = ttk.Button(
            bottom, text="退 出", command=self._on_close
        )
        self._exit_btn.pack(side="right")

        # 默认显示待命页
        self._show_page("idle")

    # ------------------------------------------------------------------
    # 页面切换
    # ------------------------------------------------------------------

    def _show_page(self, name: str):
        """显示指定页面，隐藏其余。"""
        for page in [self._page_idle, self._page_qr,
                     self._page_progress, self._page_done]:
            page.pack_forget()

        mapping = {
            "idle": self._page_idle,
            "qr": self._page_qr,
            "progress": self._page_progress,
            "done": self._page_done,
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

        # 启动前锁定平台选择
        self._platform_choice = self._platform_var.get()
        self._log_view.add_log(f"游戏平台: {self._platform_choice}", "info")

        self._worker_thread = threading.Thread(
            target=self._run_workflow, daemon=True
        )
        self._worker_thread.start()

    def _on_next_round(self):
        """完成页点击「确认执行下一轮」—— 用新设置开始。"""
        old_login_type = self._login_type.get()
        new_login_type = self._next_login_type.get()

        # 更新登录方式、账号、平台
        self._login_type.set(new_login_type)
        new_account = self._next_account_var.get().strip()
        if new_account:
            self._account_var.set(new_account)
        new_platform = self._next_platform_var.get()
        self._platform_var.set(new_platform)
        self._platform_choice = new_platform

        # 登录方式变化 → 需要重新登录腾讯先锋
        if new_login_type != old_login_type:
            self._platform_logged_in = False

        self._is_rerun = True
        self._on_start()

    def _on_close(self):
        """关闭窗口。"""
        self._stop_event.set()
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)
        self.destroy()

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
            self._show_page("done")
            self._done_summary.config(text=msg["text"])
            # 预填新一轮的选项（沿用当前选择）
            self._next_login_type.set(self._login_type.get())
            self._next_account_var.set("")
            self._next_platform_var.set(self._platform_var.get())

    # ------------------------------------------------------------------
    # 后台工作流
    # ------------------------------------------------------------------

    def _send(self, msg: dict):
        """线程安全地向 GUI 队列发送消息。"""
        self._queue.put(msg)

    def _run_workflow(self):
        """后台线程：执行完整的登录 → 截图工作流。"""
        from browser import create_browser
        from config import BROWSER_WIDTH, BROWSER_HEIGHT, PAGE_LOAD_WAIT, CLICK_INTERVAL, TEMPLATES_DIR, SCREENSHOTS_DIR, SCREENSHOT_DELAY_MIN, SCREENSHOT_DELAY_MAX, resource_path, writable_path
        from login import web_login, game_login, click_confirm_dialog
        from game_launcher import launch_game
        from navigator import Navigator
        from screenshotter import Screenshotter
        from popup_monitor import PopupMonitor
        from logger import get_logger
        import os
        import json

        _log = get_logger()
        driver = None
        _nav = None
        nav = None
        monitor = None

        try:
            # ====== 阶段 1: 腾讯先锋登录（仅一次） ======
            if not self._platform_logged_in:
                if self._stop_event.is_set():
                    return

                _log.info("[阶段1] 开始腾讯先锋登录")
                self._send({"type": "log", "text": "正在打开浏览器..."})

                driver = create_browser(BROWSER_WIDTH, BROWSER_HEIGHT)

                login_type = self._login_type.get()
                _log.info(f"[阶段1] 登录方式: {login_type}")

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

                # ---- 清除游戏启动后的弹窗（仅首次） ----
                self._send({"type": "log", "text": "等待 10 秒后清除初始弹窗..."})
                time.sleep(10)
                _nav = Navigator(driver=driver, templates_dir=resource_path(TEMPLATES_DIR))
                vw, vh = _nav.viewport_size()
                _nav.click_css(vw // 2, int(vh * 0.85))
                self._send({"type": "log", "text": "已尝试清除弹窗"})

                # ---- 3a. 退出当前登录（仅首次，防止自动登录残留） ----
                self._send({"type": "log", "text": "等待游戏窗口..."})
                time.sleep(2)
                monitor = PopupMonitor(navigator=_nav)

                # 同步清理弹窗 → 等3s → 再次确认无弹窗 → 冷却等待
                monitor.close_all_popups()
                time.sleep(3)
                monitor.close_all_popups()
                monitor.wait_until_clear(3)

                # 有退出按钮 → 退出并确认；无退出按钮 → 处理云服务器确认弹窗
                LOGOUT_BTN_RETRIES = 2
                LOGOUT_BTN_WAIT = 30
                logout_btn_found = False
                for logout_try in range(1, LOGOUT_BTN_RETRIES + 1):
                    if _nav.find_and_click("game_logout_btn.png", timeout=5, max_retries=3):
                        logout_btn_found = True
                        break
                    if logout_try < LOGOUT_BTN_RETRIES:
                        self._send({"type": "log", "text": f"未检测到退出按钮，{LOGOUT_BTN_WAIT}s后重试 ({logout_try}/{LOGOUT_BTN_RETRIES})...", "level": "warn"})
                        time.sleep(LOGOUT_BTN_WAIT)

                if logout_btn_found:
                    self._send({"type": "log", "text": "已点击退出登录"})
                    hit = click_confirm_dialog(_nav, wait_after=3.0)
                    if hit:
                        self._send({"type": "log", "text": f"已确认退出登录（{hit}）"})
                    else:
                        self._send({"type": "log", "text": "未找到退出确认按钮", "level": "warn"})
                else:
                    self._send({"type": "log", "text": "未检测到退出按钮，检查云服务器确认弹窗...", "level": "warn"})
                    hit = click_confirm_dialog(_nav, wait_after=1.0)
                    if hit:
                        self._send({"type": "log", "text": f"已点击云服务器确认弹窗（{hit}）"})
                    else:
                        self._send({"type": "log", "text": "未发现确认弹窗，继续游戏登录", "level": "info"})

                monitor = None

            elif self._is_rerun:
                # 再跑一轮：跳过阶段 1-2，直接从退出当前登录开始
                self._is_rerun = False
                if self._stop_event.is_set():
                    return

                self._send({"type": "log", "text": "正在退出当前游戏登录...", "level": "info"})
                _nav = Navigator(driver=driver, templates_dir=resource_path(TEMPLATES_DIR))
                monitor = PopupMonitor(navigator=_nav)

                # 同步清理弹窗 → 等3s → 再次确认无弹窗 → 冷却等待
                monitor.close_all_popups()
                time.sleep(3)
                monitor.close_all_popups()
                monitor.wait_until_clear(3)

                # 有退出按钮 → 退出并确认；无退出按钮 → 处理云服务器确认弹窗
                LOGOUT_BTN_RETRIES = 2
                LOGOUT_BTN_WAIT = 30
                logout_btn_found = False
                for logout_try in range(1, LOGOUT_BTN_RETRIES + 1):
                    if _nav.find_and_click("game_logout_btn.png", timeout=5, max_retries=3):
                        logout_btn_found = True
                        break
                    if logout_try < LOGOUT_BTN_RETRIES:
                        self._send({"type": "log", "text": f"未检测到退出按钮，{LOGOUT_BTN_WAIT}s后重试 ({logout_try}/{LOGOUT_BTN_RETRIES})...", "level": "warn"})
                        time.sleep(LOGOUT_BTN_WAIT)

                if logout_btn_found:
                    self._send({"type": "log", "text": "已点击退出登录"})
                    hit = click_confirm_dialog(_nav, wait_after=3.0)
                    if hit:
                        self._send({"type": "log", "text": f"已确认退出登录（{hit}）"})
                    else:
                        self._send({"type": "log", "text": "未找到退出确认按钮", "level": "warn"})
                else:
                    self._send({"type": "log", "text": "未检测到退出按钮，检查云服务器确认弹窗...", "level": "warn"})
                    hit = click_confirm_dialog(_nav, wait_after=1.0)
                    if hit:
                        self._send({"type": "log", "text": f"已点击云服务器确认弹窗（{hit}）"})
                    else:
                        self._send({"type": "log", "text": "未发现确认弹窗，继续游戏登录", "level": "info"})

                monitor = None

            # ====== 阶段 3: 游戏内登录 + 截图 ======
            if self._stop_event.is_set():
                return

            # 释放上一个 Navigator 的模板缓存
            if _nav is not None:
                _nav.cleanup()

            self._send({"type": "log", "text": "等待游戏窗口..."})
            nav = Navigator(driver=driver, templates_dir=resource_path(TEMPLATES_DIR))

            # ====== 阶段 3: 游戏登录（最多重试 3 次） ======
            GAME_LOGIN_MAX_RETRIES = 3
            game_login_ok = False

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
            self._send({"type": "log", "text": "✅ 游戏登录成功", "level": "success"})

            # ---- 验证：确认已进入游戏主界面 ----
            self._send({"type": "log", "text": "验证游戏主界面..."})
            time.sleep(3)
            if not nav.wait_for_template("avatar.png", timeout=10):
                _log.error("[阶段3] 游戏登录验证失败：未检测到主界面头像")
                self._send({"type": "log", "text": "❌ 未进入游戏主界面，登录可能失败", "level": "error"})
                self._send({"type": "done", "text": "❌ 未进入游戏主界面"})
                return

            # ====== 阶段 4: 截图 ======
            self._send({"type": "log", "text": "等待 10 秒后处理弹窗..."})
            time.sleep(10)

            # ---- 弹窗监控配置（阶段 4 全程异步） ----
            # 修改弹窗检测逻辑：编辑 popup_monitor.py 的 _do_scan() 中 buttons 列表
            monitor = PopupMonitor(navigator=nav)
            self._send({"type": "log", "text": "正在清理弹窗..."})
            monitor.close_all_popups()
            self._send({"type": "log", "text": "弹窗清理完毕，等待 3 秒..."})
            time.sleep(3)
            monitor.close_all_popups()
            monitor.wait_until_clear(3)
            self._send({"type": "log", "text": "冷却完成，确认无弹窗..."})
            # 启动异步弹窗监控，截图全程后台扫描
            monitor.start()
            _log.info("阶段 4 异步弹窗监控已启动")

            avatar_bounds = None
            nobility_bounds = None

            account = self._account_var.get().strip()
            if not account:
                account = f"unknown_{time.strftime('%H%M%S')}"
            shot = Screenshotter(
                output_dir=os.path.join(writable_path(SCREENSHOTS_DIR), account),
                driver=driver,
            )

            vw, vh = nav.viewport_size()
            avatar_bounds = (0, 0, int(vw * 0.4), int(vh * 0.5))
            nobility_bounds = (0, 0, vw, int(vh * 0.5))

            # 仅主页头像 / 小兵使用显式坐标点击（其余按钮不做 calibrated_coords 兜底）
            _coords = {}
            try:
                with open(resource_path("calibrated_coords.json"), "r") as f:
                    _coords = json.load(f)
            except Exception:
                pass
            _avatar_xy = tuple(_coords.get("avatar", [379, 249]))
            _minion_xy = tuple(_coords.get("minion", [1377, 366]))
            _log.info(f"坐标点击仅保留: avatar={_avatar_xy}, minion={_minion_xy}")

            # 截图任务（和 main.py 一致）
            # __coords__ 格式: ("__coords__", 描述, (x, y), 锚点模板)
            screenshot_tasks = [
                ("主页", [
                    ("__coords__", "点击左上角头像", _avatar_xy, "avatar.png"),
                    ("tab_home.png", "点击主页标签"),
                ], 0),
                ("英雄", [
                    ("tab_hero.png", "点击英雄标签"),
                ], 0),
                ("万象图鉴首页", [
                    ("tab_illustrated.png", "点击图鉴标签"),
                    ("universal_illustrated.png", "点击万象图鉴"),
                ], 0),
                ("万象图鉴-灵宝", [
                    ("lingbao.png", "点击灵宝"),
                ], 1),
                ("皮肤图鉴", [
                    ("skin_illustrated.png", "点击皮肤图鉴"),
                ], 1),
                ("积分夺宝", [
                    ("shop_icon.png", "点击商城"),
                    ("lottery_tab.png", "点击夺宝"),
                    ("points_lottery.png", "点击积分夺宝"),
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
            success = 0

            def _do_recover():
                """尝试从游戏重启中恢复。返回 True 表示恢复成功。"""
                self._send({"type": "log", "text": "等待游戏恢复（最多 60s）...", "level": "warn"})
                monitor.pause()

                start = time.time()
                game_templates = [
                    "game_wx_ios.png", "game_wx_android.png",
                    "game_qq_ios.png", "game_qq_android.png",
                ]

                while time.time() - start < 60:
                    if self._stop_event.is_set():
                        monitor.resume()
                        return False

                    # 检测是否已在主界面
                    if nav.wait_for_template("avatar.png", timeout=2):
                        monitor.resume()
                        self._send({"type": "log", "text": "检测到游戏主界面，无需重新登录", "level": "info"})
                        return True

                    # 检测是否在登录界面
                    for tpl in game_templates:
                        if nav.wait_for_template(tpl, timeout=1, threshold=0.6):
                            self._send({"type": "log", "text": f"检测到登录界面，重新登录...", "level": "info"})
                            if game_login(nav, platform, on_game_qr, on_game_status):
                                monitor.resume()
                                return True
                            else:
                                monitor.resume()
                                self._send({"type": "log", "text": "游戏登录失败", "level": "error"})
                                return False

                    time.sleep(2)

                monitor.resume()
                self._send({"type": "log", "text": "等待游戏恢复超时", "level": "error"})
                return False

            restart_loop = True
            while restart_loop:
                restart_loop = False
                consecutive_failures = 0
                success = 0

                for idx, (name, clicks, back_count) in enumerate(screenshot_tasks, 1):
                    if self._stop_event.is_set():
                        return

                    self._send({"type": "log", "text": f"[{idx}/{total}] {name}"})
                    self._send({"type": "progress", "current": idx - 1, "total": total})

                    # 异步监控全程在线，不再由主线程同步关闭弹窗

                    all_ok = True
                    last_step = None  # (verify_template, rollback_action)
                    rollback_count = 0  # 防止同一节点反复回退

                    for item in clicks:
                        anchor = None
                        if len(item) == 4:
                            # __coords__ 格式: (template, desc, coords, anchor)
                            template, desc, coords, anchor = item
                            bounds = coords
                        elif len(item) == 3:
                            template, desc, bounds = item
                        else:
                            template, desc = item
                            bounds = None

                        # 等待弹窗冷却（关闭后 3s 无新弹窗）
                        if monitor is not None:
                            monitor.wait_until_clear(3)

                        # 坐标点击
                        if template == "__coords__":
                            x, y = bounds
                            nav.click_css(x, y)
                            self._send({"type": "log", "text": f"  🖱 坐标点击 ({x}, {y})"})
                            _log.info(f"坐标点击 ({x}, {y})")
                            time.sleep(CLICK_INTERVAL)
                            consecutive_failures = 0
                            last_step = (anchor, lambda _x=x, _y=y: nav.click_css(_x, _y))

                        elif not nav.find_and_click(template, bounds=bounds):
                            consecutive_failures += 1
                            all_ok = False
                            self._send({"type": "log", "text": f"  ⚠ 找不到 {template}", "level": "warn"})

                            # 有上一步锚点 → 立即检查是否页面还在，在则回退重试
                            if last_step is not None and rollback_count == 0:
                                verify_template, rollback = last_step
                                if nav.wait_for_template(verify_template, timeout=2):
                                    self._send({"type": "log", "text": f"  ↩ 回退：{verify_template} 可见，重试上一步", "level": "warn"})
                                    rollback()
                                    time.sleep(CLICK_INTERVAL)
                                    consecutive_failures = 0
                                    rollback_count += 1
                                    all_ok = True
                                    continue

                            # 连续失败 ≥2 且主界面头像消失 → 游戏可能崩溃
                            if consecutive_failures >= 2 and not nav.wait_for_template("avatar.png", timeout=2):
                                self._send({"type": "log", "text": "⚠️ 游戏可能已重启，尝试恢复...", "level": "warn"})
                                if _do_recover():
                                    self._send({"type": "log", "text": "✅ 游戏已恢复，重新开始截图", "level": "success"})
                                    restart_loop = True
                                else:
                                    self._send({"type": "log", "text": "❌ 游戏恢复失败", "level": "error"})
                            break

                        else:
                            consecutive_failures = 0
                            _t = template
                            _b = bounds
                            last_step = (_t, lambda _t=_t, _b=_b: nav.find_and_click(_t, bounds=_b))

                        # 贵族：点击图标后无需同步清理，异步监控处理

                    if restart_loop:
                        break

                    if all_ok:
                        time.sleep(PAGE_LOAD_WAIT)
                        shot.take(name)
                        success += 1
                        self._send({"type": "log", "text": f"  已截图: {name}", "level": "success"})

                        for _ in range(back_count):
                            nav.find_and_click("back_arrow.png", timeout=3)
                            time.sleep(3)

                        # 异步监控在间隔期间自动处理弹窗

                        delay = random.uniform(SCREENSHOT_DELAY_MIN, SCREENSHOT_DELAY_MAX)
                        self._send({"type": "log", "text": f"  等待 {delay:.1f}s...", "level": "info"})
                        time.sleep(delay)
                    else:
                        self._send({"type": "log", "text": f"  ❌ 截图失败: {name}", "level": "error"})

                if restart_loop:
                    continue

            self._send({"type": "progress", "current": total, "total": total})
            self._send({"type": "log", "text": f"完成: {success}/{total} 张截图成功", "level": "success"})

            # ====== 退出游戏登录 ======
            self._send({"type": "log", "text": "正在退出游戏登录...", "level": "info"})
            LOGOUT_MAX_RETRIES = 3

            for logout_attempt in range(1, LOGOUT_MAX_RETRIES + 1):
                if self._stop_event.is_set():
                    return

                # 1. 点击右上角设置按钮（bounds 按实际截图像素）
                vw, vh = nav.viewport_size()
                settings_bounds = (
                    int(vw * 0.8), 0,
                    int(vw * 0.2), int(vh * 0.3),
                )
                if not nav.find_and_click("settings_icon.png", timeout=5, bounds=settings_bounds):
                    self._send({"type": "log", "text": f"未找到设置按钮，重试 ({logout_attempt}/{LOGOUT_MAX_RETRIES})...", "level": "warn"})
                    time.sleep(2)
                    continue

                self._send({"type": "log", "text": "已点击设置"})
                time.sleep(2)

                # 2. 点击右下角「退出登录」
                vw, vh = nav.viewport_size()
                logout_bounds = (
                    0, int(vh * 0.6),
                    vw, int(vh * 0.4),
                )
                if not nav.find_and_click("settings_logout.png", timeout=5, bounds=logout_bounds):
                    # settings_logout 未匹配则点屏幕下方
                    nav.click_css(vw // 2, int(vh * 0.8))
                    self._send({"type": "log", "text": f"未找到退出登录按钮，重试 ({logout_attempt}/{LOGOUT_MAX_RETRIES})...", "level": "warn"})
                    time.sleep(2)
                    continue

                self._send({"type": "log", "text": "已点击退出登录"})
                time.sleep(2)

                # 3. 确认退出（确定 / 同意）
                hit = click_confirm_dialog(nav, wait_after=2.0)
                if hit:
                    self._send({"type": "log", "text": f"已确认退出登录（{hit}）"})
                else:
                    self._send({"type": "log", "text": "未找到退出确认按钮", "level": "warn"})
                break

            self._send({"type": "log", "text": "已退出游戏登录", "level": "info"})

            self._send({
                "type": "done",
                "text": f"✅ 本轮完成: {success}/{total} 张截图\n已退出游戏登录"
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
            # 浏览器保持打开，方便下一轮直接复用

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def run(self):
        """启动 GUI 主循环。"""
        self.mainloop()
