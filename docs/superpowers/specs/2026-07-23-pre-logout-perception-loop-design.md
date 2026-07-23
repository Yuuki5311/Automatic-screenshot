# 预退出阶段感知环设计

日期：2026-07-23  
状态：已实现

## 背景

截图阶段已有 `UiLoop` 感知环（弹窗优先：X 关闭 + 确认「确定」）。  
云游戏打开后、点登录页「退出」之前，目前仍用 `PopupMonitor` 同步清弹窗 + 固定 30s 重试找 `game_logout_btn`，与感知环能力脱节，弹窗/确认易漏。

## 目标

新增第二段感知环打开时段：

- **起点**：`launch_game` 成功并切到云游戏标签之后  
- **终点**：成功点击登录页 `game_logout_btn.png`，并完成确认弹窗（或判定无需确认）后结束  

该时段只做「清弹窗 → 点退出 → 确认」，不做截图任务。阶段 4 截图感知环不变。

## 非目标

- 不改阶段 4 `UiLoop` 截图任务表  
- 不把 `PopupMonitor` 后台线程重新引入该时段（与截图环一致：同步 tick）  
- 不扩展到设置页「退出登录」（那是工作流收尾，不在本范围）

## 行为

### Tick 决策（优先级）

1. **弹窗**：同截图环——`popup_close` / `popup_close_small`（右上）或 `game_popup_confirm` / `game_logout_confirm`（下半屏）→ 点击关闭/确定  
2. **退出按钮**：画面无上述弹窗时，尝试匹配并点击 `game_logout_btn.png`  
3. **已点退出后的确认**：若本环已成功点过退出，下一 tick 优先点确认模板；确认成功或短超时无确认 → **结束环**  
4. **等待**：均未命中 → 短 tick 等待后重试  

### 起止细节

| 项 | 约定 |
|----|------|
| 起点缓冲 | 切标签后可保留短暂稳定等待（建议 ≤10s，可配置常量），然后进入环；环内不再空等 30s |
| 成功结束 | 点到退出，且（点到确认 **或** 确认超时未出现） |
| 失败/超时 | 整环超时（建议 90～120s）仍未点到退出：打 warn 日志，**不中断工作流**，进入阶段 3（与现「未检测到退出则继续」一致）；超时前若只点到确认弹窗（云服务器）也可记一次并继续 |
| 停止 | 尊重 `stop_event` |

### 与现逻辑替换关系

阶段 2（首次）与「再跑一轮」中的：

- `PopupMonitor.close_all_popups` ×2 + `wait_until_clear`  
- `LOGOUT_BTN_RETRIES` + `LOGOUT_BTN_WAIT=30` 循环  
- 点退出后的 `click_confirm_dialog`  

→ 替换为上述预退出感知环一次调用。

百分比点击清初始弹窗（`vw/2, vh*0.85`）可保留在环**之前**一次，作为启动后粗清；环内不再依赖该兜底。

## API 草图

```text
run_pre_logout_loop(
    nav,
    *,
    stop_event=None,
    on_log=None,
    timeout_s=120.0,
    tick_s=0.5,
) -> PreLogoutResult
```

`PreLogoutResult` 至少包含：

- `logout_clicked: bool`  
- `confirm_clicked: str | None`（模板名）  
- `timed_out: bool`  

实现位置：优先放在 `ui_loop.py`（复用 `_close_popup` / classify 弹窗路径），或同文件旁的薄封装；`gui/app.py` 阶段 2 / 再跑一轮调用。

## 测试要点

- 先弹窗后退出：关闭模板被点，再点 `game_logout_btn`  
- 点退出后出现确认：点确认后结束  
- 点退出后无确认：短等后结束且 `confirm_clicked is None`  
- 超时未找到退出：`logout_clicked is False`、`timed_out is True`  
- `stop_event` 可中断  

## 风险

- 确认模板阈值较低（0.48），误点「确定」：仅在预退出环与截图环已接受该策略；预退出阶段误点云服务器确认与现 `click_confirm_dialog` 行为一致，可接受  
- 退出按钮与弹窗同屏：必须弹窗优先，避免点穿  

## 验收

1. 云游戏打开后日志出现「预退出感知环启动」类提示  
2. 有弹窗时先关/确认，再点到「退出」  
3. 退出确认完成后进入游戏登录阶段  
4. 截图阶段感知环行为回归通过现有单测  
