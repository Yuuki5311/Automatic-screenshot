"""可复用的二维码展示组件。

接受 PIL Image，等比缩放后展示在 Tkinter Frame 中，
下方显示标题和状态文字。
"""

import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk


class QRDisplay(ttk.Frame):
    """二维码展示区域，包含标题、图片、状态文字。

    使用方式:
        qr = QRDisplay(parent)
        qr.pack(fill="both", expand=True)
        qr.show_qr(pil_image, "请扫描二维码")
        qr.update_status("⏳ 等待扫码中...", "gray")
        qr.update_status("✅ 扫码成功", "green")
    """

    def __init__(self, parent, qr_size: int = 280):
        """
        Args:
            parent: 父级 Tkinter 容器。
            qr_size: 二维码展示的最大边长（像素），等比缩放。
        """
        super().__init__(parent)
        self.qr_size = qr_size

        # 标题标签
        self._title_label = ttk.Label(
            self, text="", font=("", 13, "bold"), anchor="center"
        )
        self._title_label.pack(pady=(10, 5))

        # 二维码图片标签
        self._image_label = ttk.Label(self)
        self._image_label.pack(pady=10)

        # 状态文字
        self._status_label = ttk.Label(
            self, text="", font=("", 11), anchor="center"
        )
        self._status_label.pack(pady=(0, 10))

        self._tk_image = None  # 持有引用防止被 GC

    def show_qr(self, image: Image.Image, title: str) -> None:
        """展示二维码图片。

        Args:
            image: PIL Image 对象。
            title: 标题文字，如 "第 1/2 步：请扫描腾讯先锋登录二维码"。
        """
        self._title_label.config(text=title)

        # 等比缩放
        w, h = image.size
        scale = min(self.qr_size / w, self.qr_size / h, 1.0)
        new_w, new_h = int(w * scale), int(h * scale)
        resized = image.resize((new_w, new_h), Image.LANCZOS)

        self._tk_image = ImageTk.PhotoImage(resized)
        self._image_label.config(image=self._tk_image)

    def show_qr_from_file(self, path: str, title: str) -> None:
        """从文件路径加载并展示二维码。

        Args:
            path: 图片文件路径。
            title: 标题文字。
        """
        image = Image.open(path)
        self.show_qr(image, title)

    def update_status(self, text: str, color: str = "black") -> None:
        """更新底部状态文字。

        Args:
            text: 状态文字，如 "⏳ 等待扫码中..."。
            color: 文字颜色，如 "gray"、"green"、"red"。
        """
        self._status_label.config(text=text, foreground=color)
        self.update_idletasks()

    def clear(self) -> None:
        """清空展示内容，准备下一次使用。"""
        self._title_label.config(text="")
        self._image_label.config(image="")
        self._tk_image = None
        self._status_label.config(text="")
