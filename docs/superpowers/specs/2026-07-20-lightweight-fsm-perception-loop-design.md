# 轻量 FSM / 感知环设计

## 背景

当前截图主流程是线性阶段机：登录 → 进游戏 → 清弹窗 → 按任务表依次点击 → 截图 → 返回。  
弹窗清理依赖「卡在某一步时同步/异步扫描」。第二轮实战中出现过：**弹窗一直在画面上，但匹配漏检，流程仍推进点主页**，导致后续全乱。

完整挂机式 FSM（上百状态、战斗/商城全覆盖）对本项目过重。目标是引入**轻量界面驱动环**：保留固定截图任务表作为主线目标，用「每轮看图 → 定状态 → 见招拆招」接管中断与恢复。

## 目标

- 任意时刻出现的弹窗，都能在推进主线前被优先处理。
- 主线仍是有序截图任务（主页 → 英雄 → 万象…），不改成无目标乱点。
- 改造面可控：先覆盖「进游戏后的截图阶段」，登录/启动可暂保持线性。
- 漏检可观测：状态判定失败时打出各模板最高置信度。

## 非目标（本期不做）

- 不实现完整战斗/排位/商城挂机状态机。
- 不废除 `screenshot_tasks` 任务表。
- 不把腾讯先锋网页登录改成 FSM（仍走现有 `web_login` / `launch_game`）。
- 不引入新的视觉模型（仍用 OpenCV 模板匹配）。

## 核心概念

### 感知环（Perception Loop）

一个固定频率的循环（建议 0.5–1.0s/轮）：

1. 截取当前浏览器画面（与 `Navigator` 同源）。
2. **感知**：按优先级匹配一组状态探测模板，得到当前 `UiState`。
3. **决策**：根据 `(UiState, Goal)` 选择一个 `Action`。
4. **执行**：点击 / 截图 / 等待 / 标记任务完成 / 触发恢复。
5. 若未完成全部截图目标且未停止 → 回到 1。

脚本**不再假设**「上一步点完了，现在一定在某页」；每一步都以最新画面为准。

### 轻量 FSM

状态数量控制在个位数级，只描述「截图阶段需要区分的界面类」：

| 状态 ID | 含义 | 典型探测 |
|---------|------|----------|
| `POPUP` | 有可关闭弹窗 | `popup_close.png` / `popup_close_small.png`（右上半屏） |
| `LOGIN` | 游戏登录/选平台 | `game_qq_android.png` 等平台图、或登录相关模板 |
| `CONFIRM` | 需点确定的对话框 | `game_popup_confirm.png`（下半屏，仅在明确上下文启用） |
| `MAIN` | 大厅主界面 | `avatar.png` 可见，且非 POPUP |
| `ON_PATH` | 已在某截图目标相关页 | 当前任务的「到达验证」模板（如 `tab_home.png`） |
| `UNKNOWN` | 以上都不像 | 全部低于阈值 |

`Goal`（目标）仍是任务表游标：`current_task_index` + 任务内 `click_step`。

## 优先级（见招拆招的顺序）

每轮感知时**从高到低**判定，命中即停：

1. `POPUP` — 永远最高；有 X 先关，不推进主线。
2. `LOGIN` — 掉登录则走重登（复用现有 `game_login`），不继续截图。
3. `CONFIRM` — 仅当上一动作是「退出/需确认」或策略显式允许时处理；默认截图阶段**不**自动点确认（避免误确认购）。
4. `MAIN` / `ON_PATH` — 可执行当前主线动作（点击下一步或截图）。
5. `UNKNOWN` — 累计超时则恢复策略（返回/等头像/重登），禁止盲点主页。

线性思维对比：

- 旧：做完 A 再做 B；中间弹窗靠运气被监控扫到。  
- 新：想做 B 时先问「现在是不是 POPUP？」是 → 关；不是 → 再问能不能做 B。

## 与现有模块的关系

```
gui/app.py          仍负责：先锋登录、启游戏、游戏登录、启动截图阶段
ui_loop.py (新)     感知环：截图阶段的主循环
ui_state.py (新)    状态探测与优先级
screenshot_tasks    仍是目标列表（可抽到独立配置模块）
navigator.py        仍负责 match / click / screenshot
popup_monitor.py    演进选项见下
screenshotter.py    不变
```

### PopupMonitor 演进（二选一，推荐 A）

**A. 感知环内同步处理弹窗（推荐）**  
截图阶段不再依赖后台异步 `PopupMonitor` 与主线程抢点击。每轮先判 `POPUP` 再动作，逻辑单一，易测。

**B. 保留异步监控作辅助**  
感知环判 `POPUP` 为主；异步监控仅在环 sleep 时补刀。实现复杂，易双重点击，本期不推荐。

本期采用 **A**：进入截图感知环后 `monitor.stop()`（若已启动），由环统一关弹窗。

## 主线 Goal 如何推进

任务表结构保持现有三元组：`(name, clicks[], back_count)`。

每个任务在环中拆成子目标：

1. `NEED_CLICK`：按序完成 `clicks`（每步仍可做「点击生效验证」：下一步模板出现）。
2. `NEED_SHOT`：`clicks` 完成后截图保存。
3. `NEED_BACK`：按 `back_count` 点返回。
4. `DONE`：游标 +1。

**硬规则：** 仅当本轮状态为 `MAIN` 或 `ON_PATH`（且非 `POPUP`）时，才允许执行 `NEED_CLICK` / `NEED_SHOT` / `NEED_BACK`。

这样「弹窗一直在却点主页」在架构上被禁止：只要判为 `POPUP`，动作只能是关 X。

## 感知实现细节

### 单帧多模板探测

每轮一次截屏（或短缓存），对候选模板做 `matchTemplate`，记录最高分：

- `POPUP`：右上半屏，阈值沿用 `PopupMonitor.CLOSE_THRESHOLD`（当前 0.78）。
- `MAIN`：`avatar.png`，可用左上区域缩小误匹配。
- `ON_PATH`：仅探测「当前任务下一步相关」的 1–2 个模板，避免每轮扫全库。

日志：若最终为 `UNKNOWN` 或某高优先级接近阈值未过，输出各候选 `最高置信度`（延续现有 navigator 改进）。

### 防抖

同一状态连续 N 帧（如 2 帧）才采纳，避免视频流单帧闪断。  
`POPUP` 可 N=1（出现立刻关）。

### 未知超时

`UNKNOWN` 连续超过 T 秒（建议 30–60s）：

1. 尝试点 `back_arrow.png` 最多 2 次；  
2. 仍未知则等 `avatar.png`；  
3. 再失败则走现有 `_do_recover` / `game_login`；  
4. 恢复成功后**从当前任务重试**（不必整表重来，可配置）。

## 截图阶段流程（替换现有 for 任务表循环）

```
game_login 成功且 avatar 可见
        │
        ▼
创建 UiLoop(goal=tasks, nav, shot)
        │
        ▼
┌──── perception tick ────┐
│  shot → classify state  │
│  pick action by prio    │
│  execute                │
│  update goal cursor     │
└──────────┬──────────────┘
           │ all tasks done?
           ├─ no → tick
           └─ yes → 退出登录（可暂保持线性）→ 完成页
```

进入环之前仍可保留「进游戏后等 10 秒」；环内不再依赖「清完一轮弹窗就一劳永逸」。

## API 草图

```python
# ui_state.py
class UiState(Enum):
    POPUP = "popup"
    LOGIN = "login"
    CONFIRM = "confirm"
    MAIN = "main"
    ON_PATH = "on_path"
    UNKNOWN = "unknown"

def classify(frame_or_nav, goal) -> tuple[UiState, dict]:
    """返回状态 + 诊断信息（各模板分数）。"""
    ...

# ui_loop.py
class UiLoop:
    def __init__(self, nav, shot, tasks, stop_event, on_log): ...
    def run(self) -> int:
        """跑完返回成功截图数。"""
        ...
```

`gui/app.py` 阶段 4 变为：构造 `UiLoop(...).run()`，删除（或旁路）原 `for screenshot_tasks` 大段点击逻辑；点击生效验证、回退、恢复策略迁入 loop 的 action 处理器。

## 测试计划

- 单元：给定假分数表，`classify` 优先级正确（有 popup 分数过线 → 必为 POPUP）。  
- 单元：`POPUP` 状态下 Goal 游标不变。  
- 单元：无 POPUP + MAIN + 当前任务需点击 → 发出 click action。  
- 单元：UNKNOWN 超时触发恢复动作序列。  
- 回归：现有 `TestScreenshotTasks` / `TestPopupSafety` 仍通过；弹窗 bounds/阈值单测迁到 `ui_state` 或保留 `PopupMonitor` 共用常量。

## 分阶段落地

| 阶段 | 内容 | 验收 |
|------|------|------|
| P0 | `UiState` + `classify` + 单测 | 优先级与分数日志正确 |
| P1 | `UiLoop` 仅支持：关弹窗 + 跑通「主页」一页 | 人为弹窗插入不点错主页 |
| P2 | 迁入全部 `screenshot_tasks` | 单账号全流程截图成功 |
| P3 | 第二轮复用浏览器回归 | 弹窗漏检不再导致硬推主线 |
| P4 |（可选）去掉截图阶段异步 PopupMonitor | 无双重点击 |

## 风险与对策

| 风险 | 对策 |
|------|------|
| 状态误判（主界面当 UNKNOWN） | 防抖 + 置信度日志 + 超时恢复，勿盲点 |
| CONFIRM 误点造成买号/同意 | 截图阶段默认不自动点确认 |
| 每轮全模板太慢 | 按 Goal 只探当前相关模板 + POPUP/MAIN |
| 改造一次性过大 | 严格按 P0→P3；P1 可 feature flag 切换旧循环 |

## 成功标准

- 截图阶段任意插入活动弹窗，环会先关弹窗再继续任务，不出现「未关窗就点头像进主页」。  
- 第二轮换号进入后，同样遵守优先级。  
- 主线路程与现有任务表顺序一致，输出文件名不变。  
- 相关单测通过；关键路径有状态切换日志可复盘。
