# 阶段 3 游戏登录流程重构

**日期:** 2026-07-25
**状态:** 已批准

## 背景

当前 `game_login()` 基于扫码流程（选平台 → 等二维码 → 扫码 → 等头像 → 点进入游戏）。用户需要改为授权登录流程：弹窗优先清理，然后点平台、点两次授权登录按钮、点进入游戏。

## 设计

### 改动范围

仅修改 `login.py` 的 `game_login()` 函数内部逻辑。不修改其他文件。

### 新流程

```
game_login(nav, platform)
    │
    ├── 1. 快速检测 enter_game.png (2s)
    │       └── 出现 → 点击 → 返回 True
    │
    └── 2. 未出现:
            ├── 2a. 感知环清弹窗 (close_perception_popup, 最多 3 轮)
            ├── 2b. 点击平台按钮 (现有逻辑保留, 含退出回退)
            ├── 2c. 点 game_auth_login_1.png (下半屏, 10s 超时)
            ├── 2d. 点 game_auth_login_2.png (下半屏, 10s 超时)
            └── 2e. 点 enter_game.png (10s 超时) → 返回 True
```

### 新增模板

| 文件 | 用途 | 搜索区域 |
|------|------|---------|
| `game_auth_login_1.png` | 第一个授权登录按钮 | 下半屏 |
| `game_auth_login_2.png` | 弹窗中第二个授权登录按钮 | 下半屏 |

### 删除的代码

从 `game_login()` 中移除：
- 二维码检测循环（`qr_appeared` / `QR_CODE_TIMEOUT` 整个 while 循环）
- `on_qr` 回调相关调用
- `avatar.png` 等待检测
- 扫码后回到平台页的重试逻辑
- `game_login_other.png` 检测
- `avatar_detected_at` 超时重试
- `POST_QR_PLATFORM_GRACE_S` / `POST_QR_PLATFORM_STUCK_S` 常量（可保留不动）

### 保留的代码

- 平台按钮搜索 + 点击（含退出回退 `run_pre_logout_loop`）
- `PLATFORM_TEMPLATES` 常量
- `bottom_half_bounds()` / `platform_select_bounds()`
- `platform_template_visible()`

### 不修改的范围

- `gui/app.py` — 调用 `game_login()` 的方式不变（仍传 `platform`, `on_qr`, `on_status`）
- `click_confirm.py` — 不变
- `ui_loop.py` / `ui_state.py` — 不变
- 阶段 2、阶段 4 — 不变

### 边界情况

| 场景 | 结果 |
|------|------|
| enter_game 立即可见 | 直接点击进入, 跳过所有步骤 |
| 弹窗遮盖平台按钮 | 感知环先清弹窗 |
| 找不到授权登录 1 | 超时 10s → 返回 False |
| 找不到授权登录 2 | 超时 10s → 返回 False |
| 授权登录后找不到 enter_game | 超时 10s → 返回 False |
| 退出按钮可见（已登录态） | 回退预退出环 → 再点平台 |
