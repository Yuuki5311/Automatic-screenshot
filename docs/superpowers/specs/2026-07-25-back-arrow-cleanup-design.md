# 进入游戏后返回箭头清理

**日期:** 2026-07-25
**状态:** 已批准

## 背景

点击"进入游戏"按钮后，云游戏有时不会直接进入主界面，而是停在某个子页面（如活动页、公告页等），此时画面左上角会显示返回箭头 (`back_arrow.png`)。现有流程直接进入弹窗清理，然后验证头像——如果还在子页面，头像检测会失败，导致整个登录流程被判失败。

## 设计

在现有弹窗清理阶段**之前**，插入一个返回箭头清理环。

### 改动

**文件:** `gui/app.py`，在 `_run_workflow()` 第 629-638 行区域。

**改动前流程：**
```
等待 10 秒 → 清理弹窗 → 验证头像
```

**改动后流程：**
```
等待 10 秒 → 清理返回箭头（循环）→ 清理弹窗 → 验证头像
```

### 返回箭头清理环

```python
ARROW_TIMEOUT = 5
while True:
    if nav.find_and_click("back_arrow.png", timeout=ARROW_TIMEOUT, max_retries=1):
        self._send({"type": "log", "text": "已点击返回箭头，继续检查..."})
        time.sleep(1)
        continue
    break
```

每轮最多等待 5 秒检测 `back_arrow.png`——出现则点击并循环（处理嵌套子页面），不出现则退出循环。

### 不修改的范围

- `ui_state.py` 的 `POPUP_CLOSE_TEMPLATES` —— 不添加 back_arrow
- `ui_state.py` 的 `POPUP_CONFIRM_TEMPLATES` —— 不添加 back_arrow
- `ui_state.py` 的 `classify` / `classify_from_scores` —— 不修改
- `popup_monitor.py` —— 完全不修改
- `ui_loop.py` 中现有的 back_arrow 用法 —— 保持不变

### 边界情况

| 场景 | 结果 |
|------|------|
| 已在主界面，无返回箭头 | 最多等 5 秒后退出 |
| 停在 1 层子页面 | 检测 → 点击 → 回到主界面 → 循环退出 |
| 嵌套多层子页面 | 点击箭头 → 回到上一层 → 循环继续检测 → 直到主界面 |
| `find_and_click` 异常 | 返回 False，循环安全退出 |
| 弹窗遮挡返回箭头 | 循环退出 → 后续 `close_all_popups()` 处理 |
