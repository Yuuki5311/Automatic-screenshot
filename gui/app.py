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

        # ---- 平台选择（阶段 3） ----
        self._platform_event = threading.Event()
        self._platform_choice = None
        self._platform_var = tk.StringVar(value="qq_ios")

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
        ).pack(pady=(40, 5))
        ttk.Label(
            self._page_idle,
            text="选择登录方式并启动",
            font=("", 11)
        ).pack(pady=(0, 15))

        # 登录方式选择
        login_frame = ttk.LabelFrame(self._page_idle, text="登录方式", padding=10)
        login_frame.pack(pady=10)
        self._login_type = tk.StringVar(value="qq")
        ttk.Radiobutton(
            login_frame, text="QQ 扫码登录", variable=self._login_type, value="qq"
        ).pack(anchor="w", pady=3)
        ttk.Radiobutton(
            login_frame, text="微信扫码登录", variable=self._login_type, value="wechat"
        ).pack(anchor="w", pady=3)

        ttk.Button(
            self._page_idle, text="启 动",
            command=self._on_start, width=20
        ).pack(pady=15)

        # ---- 页面 2: 扫码页 ----
        self._page_qr = ttk.Frame(self._page_container)
        self._qr_display = QRDisplay(self._page_qr, qr_size=260)
        self._qr_display.pack(fill="both", expand=True, pady=20)

        # ---- 页面 2.5: 游戏平台选择页 ----
        self._page_platform = ttk.Frame(self._page_container)
        ttk.Label(
            self._page_platform, text="选择游戏登录平台",
            font=("", 14, "bold")
        ).pack(pady=(30, 5))
        ttk.Label(
            self._page_platform,
            text="请选择要在游戏内登录的平台和区服：",
            font=("", 11)
        ).pack(pady=(0, 15))

        platform_frame = ttk.LabelFrame(self._page_platform, text="登录平台", padding=10)
        platform_frame.pack(pady=10)

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
            ).pack(anchor="w", pady=4)

        ttk.Button(
            self._page_platform, text="确认选择",
            command=self._on_platform_confirm, width=20
        ).pack(pady=20)

        # ---- 页面 3: 进度页 ----
        self._page_progress = ttk.Frame(self._page_container)
        self._log_view = LogView(self._page_progress)
        self._log_view.pack(fill="both", expand=True)

        # ---- 页面 4: 完成页 ----
        self._page_done = ttk.Frame(self._page_container)
        self._done_summary = ttk.Label(
            self._page_done, text="", font=("", 12)
        )
        self._done_summary.pack(pady=(40, 10))
        btn_frame = ttk.Frame(self._page_done)
        btn_frame.pack(pady=10)
        ttk.Button(
            btn_frame, text="再跑一轮",
            command=self._on_rerun, width=15
        ).pack(side="left", padx=5)
        ttk.Button(
            btn_frame, text="退 出",
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
        for page in [self._page_idle, self._page_qr, self._page_platform,
                     self._page_progress, self._page_done]:
            page.pack_forget()

        mapping = {
            "idle": self._page_idle,
            "qr": self._page_qr,
            "platform": self._page_platform,
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

        self._worker_thread = threading.Thread(
            target=self._run_workflow, daemon=True
        )
        self._worker_thread.start()

    def _on_rerun(self):
        """完成页点击「再跑一轮」。"""
        self._on_start()

    def _on_platform_confirm(self):
        """平台选择页点击确认。"""
        self._platform_choice = self._platform_var.get()
        self._platform_event.set()
        self._show_page("progress")
        self._log_view.add_log(
            f"已选择: {self._platform_choice}", "info"
        )

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

        elif msg_type == "platform_select":
            self._platform_event.clear()
            self._platform_choice = None
            self._show_page("platform")

        elif msg_type == "page":
            self._show_page(msg["name"])

        elif msg_type == "done":
            self._show_page("done")
            self._done_summary.config(text=msg["text"])

    # ------------------------------------------------------------------
    # 后台工作流
    # ------------------------------------------------------------------

    def _send(self, msg: dict):
        """线程安全地向 GUI 队列发送消息。"""
        self._queue.put(msg)

    def _run_workflow(self):
        """后台线程：执行完整的登录 → 截图工作流。"""
        from browser import create_browser
        from config import BROWSER_WIDTH, BROWSER_HEIGHT, PAGE_LOAD_WAIT, TEMPLATES_DIR, SCREENSHOTS_DIR, resource_path
        from login import web_login, game_login
        from game_launcher import launch_game
        from navigator import Navigator
        from screenshotter import Screenshotter
        from popup_monitor import PopupMonitor
        from logger import get_logger
        import pyautogui
        import os

        _log = get_logger()
        driver = None
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
                    self._send({
                        "type": "scan_wait",
                        "title": f"腾讯先锋{'QQ' if login_type == 'qq' else '微信'}登录",
                        "text": "⏳ 请在打开的浏览器窗口中扫码...",
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

                _log.info("[阶段2] 游戏启动完成")

                self._send({"type": "log", "text": "✅ 已点击秒玩，等待游戏启动...", "level": "success"})

                # ---- 清除游戏启动后的弹窗（仅首次） ----
                self._send({"type": "log", "text": "等待 10 秒后清除初始弹窗..."})
                time.sleep(10)
                # 点击屏幕空白区域消除弹窗
                sw, sh = pyautogui.size()
                pyautogui.click(int(sw * 0.5), int(sh * 0.85))
                self._send({"type": "log", "text": "已尝试清除弹窗"})

                # ---- 3a. 退出当前登录（仅首次，防止自动登录残留） ----
                self._send({"type": "log", "text": "等待游戏窗口..."})
                time.sleep(2)
                _nav = Navigator(templates_dir=resource_path(TEMPLATES_DIR))

                # 启动弹窗监控（有真实 Navigator）
                monitor = PopupMonitor(navigator=_nav)
                monitor.start()
                _log.info("弹窗监控已启动")

                self._send({"type": "log", "text": "正在退出当前游戏登录..."})
                time.sleep(3)
                if _nav.find_and_click("game_logout_btn.png", timeout=5, max_retries=7):
                    self._send({"type": "log", "text": "已点击退出登录"})
                    time.sleep(2)
                    # 点击确认弹窗中的「确定」按钮（屏幕下方 30% 区域搜索）
                    sw, sh = pyautogui.size()
                    confirm_bounds = (0, int(sh * _nav._scale * 0.5), int(sw * _nav._scale), int(sh * _nav._scale * 0.5))
                    if not _nav.find_and_click("game_logout_confirm.png", timeout=3, bounds=confirm_bounds):
                        # 模板未匹配则点击屏幕下方
                        pyautogui.click(int(sw * 0.5), int(sh * 0.75))
                else:
                    self._send({"type": "log", "text": "未检测到退出按钮，可能已是未登录状态"})

            # ====== 阶段 3: 游戏内登录 + 截图 ======
            if self._stop_event.is_set():
                return

            self._send({"type": "log", "text": "等待游戏窗口..."})
            nav = Navigator(templates_dir=resource_path(TEMPLATES_DIR))

            # 启动弹窗监控（如有旧的先停）
            if monitor is not None:
                monitor.stop()
            monitor = PopupMonitor(navigator=nav)
            monitor.start()
            _log.info("阶段 3 弹窗监控已启动")

            # ---- 3b. 让用户选择登录平台 ----
            self._platform_event.clear()
            self._platform_choice = None
            self._send({"type": "platform_select"})
            self._send({"type": "log", "text": "请在 GUI 中选择游戏登录平台..."})

            # 等待用户确认（最多等 2 分钟）
            if not self._platform_event.wait(timeout=120):
                self._send({"type": "log", "text": "❌ 平台选择超时", "level": "error"})
                self._send({"type": "done", "text": "❌ 平台选择超时"})
                return

            if self._stop_event.is_set():
                return

            platform = self._platform_choice or "qq_ios"
            platform_display = {
                "wx_ios": "微信 iOS", "wx_android": "微信安卓",
                "qq_ios": "QQ iOS", "qq_android": "QQ 安卓",
            }.get(platform, platform)
            self._send({"type": "log", "text": f"已选择游戏登录平台: {platform_display}"})

            # ---- 3b. 执行游戏内登录 ----
            def on_game_qr(image=None):
                self._send({
                    "type": "scan_wait",
                    "title": f"游戏 {platform_display} 登录",
                    "text": "⏳ 请在游戏窗口中扫码...",
                })

            def on_game_status(text):
                if "成功" in text:
                    self._send({"type": "qr_status", "text": text, "color": "green"})
                else:
                    self._send({"type": "qr_status", "text": text})
                self._send({"type": "log", "text": text,
                            "level": "success" if "成功" in text else "info"})

            _log.info(f"[阶段3] 开始游戏登录, platform={platform}")
            monitor.stop()
            if not game_login(nav, platform, on_game_qr, on_game_status):
                _log.error("[阶段3] 游戏登录失败")
                self._send({"type": "log", "text": "❌ 游戏登录失败", "level": "error"})
                self._send({"type": "done", "text": "❌ 游戏登录失败"})
                return

            _log.info("[阶段3] 游戏登录成功")
            self._send({"type": "page", "name": "progress"})
            self._send({"type": "log", "text": "✅ 游戏登录成功", "level": "success"})

            # ====== 阶段 4: 截图（带弹窗监控） ======
            # 启动阶段 4 专属弹窗监控
            monitor = PopupMonitor(navigator=nav)
            monitor.start()
            _log.info("阶段 4 弹窗监控已启动")

            avatar_bounds = None
            nobility_bounds = None

            shot = Screenshotter(output_dir=os.path.join(resource_path(SCREENSHOTS_DIR), "screenshots"))

            screen_w, screen_h = pyautogui.size()
            # Intentional private attr access (avoids public API change to Navigator in this task)
            avatar_bounds = (0, 0, int(screen_w * nav._scale * 0.4), int(screen_h * nav._scale * 0.5))
            nobility_bounds = (0, 0, int(screen_w * nav._scale), int(screen_h * nav._scale * 0.5))

            # 截图任务（和 main.py 一致）
            screenshot_tasks = [
                ("主页", [
                    ("avatar.png", "点击左上角头像", avatar_bounds),
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
                    ("skin_illustrated.png", ""),
                ], 1),
                ("积分夺宝", [
                    ("shop_icon.png", "点击商城"),
                    ("lottery_tab.png", "点击夺宝"),
                    ("points_lottery.png", "点击积分夺宝"),
                ], 2),
                ("天幕", [
                    ("customize_icon.png", "点击定制"),
                    ("skin_customize.png", "点击皮肤定制"),
                    ("my_tab.png", "点击我的"),
                    ("sky_curtain.png", "点击天幕"),
                ], 1),
                ("小兵", [
                    ("minion.png", "点击小兵"),
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

            for idx, (name, clicks, back_count) in enumerate(screenshot_tasks, 1):
                if self._stop_event.is_set():
                    return

                self._send({"type": "log", "text": f"[{idx}/{total}] {name}"})
                self._send({"type": "progress", "current": idx - 1, "total": total})

                all_ok = True
                for item in clicks:
                    if len(item) == 3:
                        template, desc, bounds = item
                    else:
                        template, desc = item
                        bounds = None

                    if not nav.find_and_click(template, bounds=bounds):
                        self._send({"type": "log", "text": f"  ⚠ 找不到 {template}，跳过 {name}", "level": "warn"})
                        all_ok = False
                        break

                if all_ok:
                    time.sleep(PAGE_LOAD_WAIT)
                    shot.take(name)
                    success += 1
                    self._send({"type": "log", "text": f"  已截图: {name}", "level": "success"})

                    for _ in range(back_count):
                        nav.find_and_click("back_arrow.png", timeout=3)
                        time.sleep(3)
                else:
                    self._send({"type": "log", "text": f"  ❌ 截图失败: {name}", "level": "error"})

            self._send({"type": "progress", "current": total, "total": total})
            self._send({"type": "log", "text": f"完成: {success}/{total} 张截图成功", "level": "success"})

            # ====== 退出游戏登录 ======
            self._send({"type": "log", "text": "正在退出游戏登录...", "level": "info"})
            # 返回主界面 → 设置 → 退出登录
            for _ in range(3):
                nav.find_and_click("back_arrow.png", timeout=3)
                time.sleep(2)
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
            if driver is not None:
                driver.quit()

    # ------------------------------------------------------------------
    # 启动
    # ------------------------------------------------------------------

    def run(self):
        """启动 GUI 主循环。"""
        self.mainloop()
