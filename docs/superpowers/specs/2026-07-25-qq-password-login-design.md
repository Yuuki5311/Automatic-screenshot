# QQ 密码登录（半自动）

**日期:** 2026-07-25
**状态:** 已批准

## 背景

当前腾讯先锋登录仅支持 QQ/微信扫码。用户需要一个半自动选项：脚本打开浏览器到 gamer.qq.com，用户在浏览器中自行完成 QQ 密码登录，然后在 GUI 点击"完成登录"，脚本验证后继续执行。

## 设计

### GUI 变更

**待命页（`_page_idle`）** — 在腾讯先锋登录栏新增第三个选项：

```
🔘 QQ 扫码登录
🔘 微信扫码登录
🔘 QQ 密码登录（手动）    ← 新增
```

**新增控件** — 底部栏添加"完成登录"按钮，默认隐藏，仅手动登录时显示：

```python
self._manual_login_btn = ttk.Button(
    bottom, text="完成登录 →", command=self._on_manual_login_done
)
```

**跨线程通信** — 新增 `threading.Event`：

```python
self._manual_login_event = threading.Event()
```

**消息队列** — 新增两种消息类型控制按钮显隐：

```
"show_manual_btn"  → 显示"完成登录"按钮
"hide_manual_btn"  → 隐藏"完成登录"按钮
```

### login.py 变更

新增 `manual_login()` 函数：

```python
def manual_login(
    driver: WebDriver,
    on_status: Callable[[str], None] | None = None,
    ready_event: threading.Event | None = None,
    timeout: int = 600,
) -> bool:
```

**流程：**
1. 打开 `gamer.qq.com`
2. 进入轮询循环（每 2 秒一次）：
   - 检测登录状态（弹窗关闭 / Cookie / JS / CSS 用户元素）
   - 如果登录已成功 → 返回 True（用户点按钮之前就已登录）
   - 如果 `ready_event` 已设置 → 做一次验证：
     - 已登录 → 返回 True
     - 未登录 → 重置 event，通知用户再试，继续循环
3. 超时（默认 10 分钟）返回 False

**与 `web_login()` 的区别：**
- 不点击登录按钮
- 不选择 QQ/微信图标
- 不切换 iframe
- 不检测/推送二维码
- 仅打开页面 + 轮询等待登录成功

### 工作流集成

`_run_workflow()` 阶段 1 新增 `qq_password` 分支：

```
login_type == "qq_password":
  1. 创建浏览器 → 打开 gamer.qq.com
  2. 显示"完成登录"按钮
  3. 调用 manual_login(driver, ..., ready_event=self._manual_login_event)
  4. 隐藏按钮
  5. 成功后 → 继续阶段 2（启动游戏）
```

### 不修改的范围

- `web_login()` 函数 — 完全不变
- 扫码登录流程 — 完全不变
- 游戏内登录 — 完全不变
- `game_launcher.py` — 完全不变
- 阶段 2/3/4 — 完全不变

### 边界情况

| 场景 | 结果 |
|------|------|
| 用户在浏览器登录后点"完成登录" | 验证通过 → 继续执行 |
| 用户未登录就点"完成登录" | 提示"未检测到登录"→ 重置 event → 等待再次点击 |
| 脚本检测到登录成功（用户未点按钮） | 自动跳过等待 → 直接继续 |
| 10 分钟超时 | 返回失败 |
| 用户关闭窗口 (stop_event) | 退出 |
| 登录方式切换为扫码 → 再跑一轮选密码登录 | 正常创建新浏览器 |
