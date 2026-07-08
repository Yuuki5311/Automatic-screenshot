"""实时日志和进度展示组件。

包含可滚动的日志区域和进度条，用于展示执行过程中的
每一步状态和截图进度。
"""

import tkinter as tk
from tkinter import ttk
from datetime import datetime


class LogView(ttk.Frame):
    """日志 + 进度条组合组件。

    使用方式:
        log_view = LogView(parent)
        log_view.pack(fill="both", expand=True)
        log_view.add_log("✅ 腾讯先锋登录成功")
        log_view.update_progress(3, 12)
    """

    def __init__(self, parent):
        super().__init__(parent)

        # ---- 日志区域 ----
        log_frame = ttk.LabelFrame(self, text="执行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=10, pady=5)

        self._log_text = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            font=("", 10),
            bg="#1e1e1e",
            fg="#d4d4d4",
            insertbackground="white",
            relief="flat",
            borderwidth=0,
        )
        scrollbar = ttk.Scrollbar(
            log_frame, orient="vertical", command=self._log_text.yview
        )
        self._log_text.configure(yscrollcommand=scrollbar.set)
        self._log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 配置 tag 颜色
        self._log_text.tag_configure("success", foreground="#4ec94e")
        self._log_text.tag_configure("error", foreground="#f44747")
        self._log_text.tag_configure("info", foreground="#d4d4d4")
        self._log_text.tag_configure("warn", foreground="#cca700")

        # ---- 进度区域 ----
        progress_frame = ttk.Frame(self)
        progress_frame.pack(fill="x", padx=10, pady=(0, 5))

        self._progress_label = ttk.Label(
            progress_frame, text="截图进度: 0/0", font=("", 10)
        )
        self._progress_label.pack(anchor="w")

        self._progress_bar = ttk.Progressbar(
            progress_frame, mode="determinate", length=400
        )
        self._progress_bar.pack(fill="x", pady=(2, 5))

    def add_log(self, text: str, level: str = "info") -> None:
        """添加一行日志。

        Args:
            text: 日志内容。
            level: 'info' | 'success' | 'error' | 'warn'
        """
        self._log_text.configure(state="normal")
        timestamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{timestamp}] {text}\n"
        self._log_text.insert("end", line, level)
        self._log_text.see("end")
        self._log_text.configure(state="disabled")
        self.update_idletasks()

    def update_progress(self, current: int, total: int) -> None:
        """更新截图进度。

        Args:
            current: 当前已完成数量。
            total: 总数。
        """
        self._progress_label.config(text=f"截图进度: {current}/{total}")
        if total > 0:
            self._progress_bar["maximum"] = total
            self._progress_bar["value"] = current
        self.update_idletasks()

    def reset_progress(self) -> None:
        """重置进度为零。"""
        self._progress_bar["value"] = 0
        self._progress_label.config(text="截图进度: 0/0")
        self.update_idletasks()

    def clear(self) -> None:
        """清空日志和进度。"""
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0", "end")
        self._log_text.configure(state="disabled")
        self.reset_progress()
