# 感知环同帧分类 + 点击前弹窗确认

## 背景

截图阶段感知环按「截屏 → 分类 → 决策 → 执行」推进。实战中出现：

- 分类所用画面尚无弹窗，判为 `MAIN` / `ON_PATH`；
- 随后弹窗弹出，脚本仍按旧结论去点主线按钮，造成误点与后续迷路。

另有实现问题：当前 `classify()` 对每个模板各自调用 `_get_screenshot()`，**同一轮状态分数可能来自不同帧**，弹窗若在扫模板中途出现，更容易漏检弹窗、仍判成可导航。

## 目标

- 单轮分类的所有模板分数来自**同一张截图**。
- 执行会改变 UI 的点击前，再确认一次是否出现弹窗；有则优先关弹窗，取消本轮主线点击。
- 改造面可控：只动感知/匹配路径，不改任务表与登录流程。

## 非目标

- 不做状态防抖（连续 N 帧同态才动作）；可后续单独加。
- 不改 `screenshot_tasks`、先锋登录、游戏登录。
- 不引入视觉模型；仍用现有 OpenCV 模板与弹窗阈值/搜索区。
- 不恢复异步 `PopupMonitor` 与环抢点击。

## 方案（已选 A）

### 1. 同帧分类

- `classify(nav, path_templates, ...)` 流程改为：
  1. 截取一帧 `screen`（或接受调用方传入的已截帧）；
  2. 在该帧上对 `POPUP` / `LOGIN` / `MAIN` / path 等模板计算分数；
  3. 再调用现有 `classify_from_scores`。
- `match_score` 增加可选参数：在已有 `screen` 上匹配，不再内部截屏；无 `screen` 时保持可单独截屏（兼容调试）。
- `viewport_size` 若仅为取宽高，可继续截一帧；分类主路径应避免为每个模板重复截屏。

### 2. 点击前弹窗二次确认

在 `UiLoop` 中，执行以下动作**之前**调用 `recheck_popup`：

| 动作 | 是否二次确认 |
|------|----------------|
| `CLICK_STEP`（含坐标点击） | 是 |
| `GO_BACK` | 是 |
| `CLOSE_POPUP` | 否（本身在关） |
| `TAKE_SHOT` | 否 |
| `WAIT` / `RECOVER` / `RELOGIN` | 否 |

`recheck_popup` 行为：

1. 新截一帧（或短超时内匹配）；
2. 仅用 `POPUP_CLOSE_TEMPLATES` + 现有 `popup_close_bounds` + `POPUP_CLOSE_THRESHOLD`；
3. 若命中 → 执行与 `_close_popup` 相同的关闭逻辑，**本轮不再执行原主线动作**，回到环的下一 tick；
4. 若未命中 → 继续原动作。

日志：二次确认命中时打 `点击前检测到弹窗，取消主线动作`（或等价文案），便于对照竞态问题是否消失。

### 3. 模块改动

| 文件 | 变更 |
|------|------|
| `ui_state.py` | 同帧打分；`match_score(..., screen=None)`；`classify` 单次截屏 |
| `ui_loop.py` | `_ensure_no_popup_before_click()`；`CLICK_STEP` / `GO_BACK` 前调用 |
| `test_core.py` | 同帧 API 行为；点前发现弹窗则不推进 click / 不点返回 |
| `navigator.py` | 仅当需要为「传入 screen 匹配」提供薄封装时再改；优先在 `ui_state` 内用现有截屏完成 |

### 4. 优先级与不变式

- 全局仍：`POPUP` > `LOGIN` > path/`MAIN` > `UNKNOWN`。
- 二次确认是对「分类→点击」时间窗的补丁，不改变 `decide()` 的优先级表。
- 假阳性关钮、迷路回退等不在本期范围。

## 成功标准

1. 单测或可观测日志证明：一轮 `classify` 内各模板分数来自同一 `screen` 对象（或等价：匹配路径不再对每个模板截屏）。
2. 单测：模拟「decide 为 click，但点前 popup 分数过线」→ 调用关弹窗，且 `click_index` / `backs_done` 不因该次误点推进。
3. 实战：弹窗在分类后、点击前出现时，应关 X 而非点主线入口。

## 风险

| 风险 | 缓解 |
|------|------|
| 每步点击多一次截屏，略增耗时 | 仅对点击类动作；可接受 |
| 二次确认仍可能与点击之间再插一帧弹窗 | 窗口已从「整轮分类+决策」缩短到「确认→点击」；足够覆盖当前竞态 |
| `popup_close_small` 假阳性 | 本期不处理；若确认后误关，另开议题 |

## 测试计划

- 单元：`match_score`/`classify` 传入固定 `screen` 时不调用 `nav._get_screenshot`（或调用次数为 1）。
- 单元：`UiLoop` 在 `_do_click_step` / `_do_back` 前若 recheck 为弹窗，则不 `advance_after_click` / 不 `advance_after_back`。
- 回归：现有 `classify_from_scores` 优先级单测保持通过。
