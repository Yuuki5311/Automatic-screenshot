# GUI 登录启动器设计

日期：2026-07-08
状态：待实现

---

## 1. 概述

将当前终端交互的登录和截图流程，改造为 **Tkinter GUI 控制面板**。

核心变化：
- QQ / 微信登录从"输入密码"改为"截取二维码 → 用户扫码 → 自动继续"
- 扫码流程有两处：腾讯先锋平台登录（仅首次）、游戏内登录（每轮都需要）
- GUI 全程驻留，可多轮执行，退出后完全停止

---

## 2. 流程

```
[启动] → 腾讯先锋扫码(仅一次) → 登录成功 → 搜索王者荣耀 → 秒玩
    → 游戏登录扫码(每轮) → 扫码成功 → 跑截图任务 → 自动退出游戏登录
    → 回到待命页
    → [再跑一轮] → 游戏登录扫码 → 跑截图 → 退出登录 → ...
    → [退出]
```

腾讯先锋扫码首次成功后不重复；游戏登录每轮都需要。

---

## 3. GUI 页面结构

### 3.1 待命页

就绪状态，显示"就绪，点击启动开始新一轮"，一个【启动】按钮。

### 3.2 扫码页

复用同一个二维码组件，标题文字动态切换：
- "第 1/2 步：请扫描腾讯先锋登录二维码"
- "第 2/2 步：请扫描游戏登录二维码"

含二维码图片展示区 + 状态文字（"⏳ 等待扫码中..." / "✅ 扫码成功"）。

### 3.3 进度页

显示实时执行步骤和进度：
- 平台登录状态
- 游戏启动状态
- 游戏登录状态
- 当前截图任务名和进度（如 "英雄 (3/12)"）
- 进度条

### 3.4 完成页

显示本轮结果（"✅ 本轮完成: 12/12 张截图，已退出游戏登录"），
提供【再跑一轮】和【退出】按钮。

底部始终有【退出】按钮，可随时终止。

---

## 4. 二维码展示组件 `gui/widgets/qr_display.py`

可复用组件，接受 PIL Image 即展示。

```python
class QRDisplay(ttk.Frame):
    def show_qr(self, image: Image.Image, title: str) -> None
    def show_qr_from_file(self, path: str, title: str) -> None
    def update_status(self, text: str, color: str = "black") -> None
    def clear(self) -> None
```

- 图片使用 Pillow ImageTk 转换，等比缩放
- `update_status` 支持颜色（扫码中=灰色，成功=绿色，失败=红色）

---

## 5. 登录模块改造 `login.py`

### 5.1 网页登录（腾讯先锋 gamer.qq.com）

```python
def web_login(driver, login_type: str, on_qr, on_status) -> bool:
    """
    Args:
        driver: Selenium WebDriver
        login_type: 'qq' | 'wechat'
        on_qr(image: Image.Image): 截到二维码时的回调
        on_status(text: str): 状态更新回调
    Returns:
        bool: 登录成功 True / 失败 False
    """
```

流程：
1. 打开 gamer.qq.com → 点击登录按钮
2. 根据 login_type 点击对应图标（QQ 或微信）
3. 切换到 OAuth iframe
4. 截取二维码元素 → 回调 `on_qr(image)`
5. 轮询检测 iframe 消失或页面跳转 → 扫码成功
6. 切回主页面 → 返回 True

### 5.2 游戏内登录

新增函数，流程类似但截图来源是 pyautogui 全屏截图 + OpenCV 二维码区域裁剪：

```python
def game_login(nav: Navigator, on_qr, on_status) -> bool:
```

- 等待游戏窗口出现
- 截屏检测二维码区域 → 裁剪 → 回调 `on_qr(image)`
- 轮询检测 avatar.png 出现 → 登录成功

---

## 6. 线程模型

```
主线程 (GUI)                    后台线程 (业务逻辑)
    │                                │
    ├─ 启动 ───────────────────────→ │ web_login() / game_login()
    │                                ├─ on_qr() → queue.put(image)
    ├─ after(100ms, poll) ←───────── │
    ├─ 显示二维码                     │
    │                                ├─ 轮询扫码完成
    │                                ├─ on_status() → queue.put(status)
    ├─ 更新状态 ←──────────────────── │
    │                                ├─ launch_game() / run_screenshot_flow()
    ├─ 更新进度 ←──────────────────── │
    │                                ├─ 退出登录 → on_status("done")
    ├─ 显示完成页                     │
```

- 使用 `queue.Queue` 跨线程通信
- GUI 用 `tkinter.after()` 定时轮询队列，不阻塞主线程
- 后台线程通过回调闭包将数据放入队列

---

## 7. 文件变更概览

| 文件 | 变更 |
|------|------|
| `gui/__init__.py` | 新增 |
| `gui/app.py` | 新增 — Tkinter 主窗口，页面管理 |
| `gui/widgets/__init__.py` | 新增 |
| `gui/widgets/qr_display.py` | 新增 — 可复用二维码展示组件 |
| `gui/widgets/log_view.py` | 新增 — 实时日志/进度组件 |
| `main.py` | 修改 — 入口改为启动 GUI |
| `login.py` | 修改 — 新增 `web_login()` 和 `game_login()` |
| `config.py` | 修改 — 移除 QQ_NUMBER 硬编码，新增登录类型配置 |

---

## 8. 错误处理

- 任何步骤失败 → 显示错误页，提供【重试】和【退出】按钮
- 扫码超时（5分钟）→ 提示超时，提供【重新获取二维码】按钮
- 截图过程中游戏崩溃 → 检测 enter_game.png 尝试恢复，恢复失败则结束本轮
- 用户点击退出 → 发送停止信号给后台线程，driver.quit()，进程退出
