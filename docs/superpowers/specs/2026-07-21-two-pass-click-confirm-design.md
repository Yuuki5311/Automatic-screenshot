# 感知环双重确认（Two-Pass Click Guard）设计

## 背景

感知环主线点击（`CLICK_STEP` / `GO_BACK`）当前链路大致为：

1. Pass 分类：截屏 → 多模板打分 → `decide`
2. 点前弹窗模板扫描（`_ensure_clear_for_click`）
3. `find_and_click` **再截屏**匹配 → `click_css` 派发点击
4. （仅返回）点后生效校验；失败则游标回退上一步

实战中仍可能出现：分类/匹配时目标按钮可见，派发点击前（或匹配与点击之间）落下小弹窗，点击被吃掉或点偏，游标却曾误以为动作成功。

已有手段的缺口：

| 手段 | 缺口 |
|------|------|
| 同帧分类 | 不覆盖「分类之后 → 真正点击」窗口 |
| 点前扫 `popup_close*` | 只认识已知 X；遮挡形态变化则漏 |
| 点后生效校验 + 回退 | 事后补救，不能阻止脏点击发出 |

需要在 **CDP/Action 派发点击前**再加一道与模板库无关的短窗口校验。

## 目标

- 对会改变 UI 的主线点击：在算出落点 \((X,Y)\) 之后、调用 `click_css` 之前，做一次 **第二 pass（局部校验）**。
- 校验失败则 **丢弃本次点击**，不推进游标，回到环的下一 tick 重新捕获。
- 与现有弹窗优先、返回生效校验、失败回退共存，不互相替代。
- 改造面可控：截图阶段感知环为主；不改登录/启游戏任务表语义。

## 非目标

- 不承诺字面「毫秒级」；在 Selenium 环境下追求 **尽量短的二次采样**，优先正确性。
- 本期不引入视觉模型 / OCR。
- 不把第二 pass 做成全图再分类（那会回到慢路径）。
- 不取消点后生效校验（第二 pass 防脏点击；点后校验防「点了没生效」）。
- `TAKE_SHOT` / `WAIT` / `RECOVER` / `RELOGIN` 不做第二 pass。
- `CLOSE_POPUP` 不做 ROI 双确认（关 X 本身就是在处理突变 UI；仍可用现有匹配点击）。

## 方案概述

### 核心思想

**第一 pass（全量）**：在同一帧上完成状态裁决，并解析出「若要点谁、点哪里、基准长什么样」。  
**第二 pass（局部）**：派发点击前，只对落点附近 ROI 再采一小块画面，与第一 pass 的基准比对；变化过大则判定画面已脏，取消点击。

```text
classify / 同帧匹配
        │
        ▼
  decide → CLICK_STEP | GO_BACK
        │
        ▼
  _ensure_clear_for_click（已知 X）
        │
        ▼
  Pass1: 同帧定位目标 → (X,Y) + roi_ref
        │
        ▼
  Pass2: 再采 ROI → 与 roi_ref 相似度
        │
   ┌────┴────┐
   │通过      │失败
   ▼          ▼
click_css   丢弃点击，打日志，下 tick 重来
   │
   ▼
（GO_BACK 另有点后生效校验 / 失败回退）
```

### 第二 pass 比对算法（推荐）

**不采用严格哈希**（云游戏压缩/抖动下误杀过高）。

推荐 **ROI 归一化相关系数**（与现有 `cv2.TM_CCOEFF_NORMED` 同族）：

1. Pass1 在全图匹配到模板中心 \((X,Y)\) 后，从该帧裁切 ROI 作为 `roi_ref`（见尺寸定义）。
2. Pass2 再获取当前 ROI 图像 `roi_now`（优先局部截取，见下节）。
3. 若尺寸一致：对 `roi_ref` 与 `roi_now` 做相关系数，或把较小块当模板在 ROI 内 `matchTemplate`。
4. `score >= ROI_CONFIRM_THRESHOLD`（建议初值 **0.90**，可配置）→ 通过；否则失败。

备选（实现复杂度更高，本期不做）：感知哈希 + 汉明距离；仅作后续优化项。

### ROI 几何

设模板宽高为 \(T_w, T_h\)，点击中心为 \((X,Y)\)：

- ROI 边长：\(\max(T_w, T_h)\) 向外扩 `ROI_PAD_PX`（建议 **12**）的正方形，再与视口裁剪。
- 坐标点击（`__coords__`）：无模板时用固定边长（建议 **48×48**）以 \((X,Y)\) 为中心。

ROI 必须覆盖「手指要落的那一块」；过大易纳入无关动画，过小对压缩噪声过敏——用阈值吸收。

### Pass2 如何取图

优先级：

1. **首选（若实现成本可接受）**：CDP `Page.captureScreenshot`，`clip` 为 ROI 的 CSS/设备像素矩形，减少全图编解码。
2. **回退**：再 `get_screenshot_as_png()` 全图后裁 ROI（行为正确，窗口更长；作为兼容路径）。

设计要求：Navigator 提供统一接口，例如：

```text
grab_roi(x, y, w, h) -> BGR ndarray
```

内部先试 CDP clip，失败则全图裁切。调用方不关心实现。

设备像素与 CSS 像素若存在缩放，clip 与 `click_css` 必须使用同一套坐标空间（与现有 `Navigator` 点击一致，当前按截图像素 ≈ CSS 视口约定）。

## 与现有动作的衔接

### 哪些动作启用

| 动作 | Pass1 定位 | Pass2 | 失败时 |
|------|------------|-------|--------|
| `CLICK_STEP` 模板点击 | 同帧 `match` 得中心 | 是 | 不 `advance_after_click` |
| `CLICK_STEP` `__coords__` | 直接用配置坐标 | 是（固定 ROI） | 同上 |
| `GO_BACK` | 同帧匹配 `back_arrow.png` | 是 | 不 `advance_after_back`；**不**在此步做「回退上一步」（尚未认定返回已发出） |
| `CLOSE_POPUP` | 现有逻辑 | 否 | — |
| `TAKE_SHOT` 等 | — | 否 | — |

说明：Pass2 失败表示 **点击未发出**（或不应发出），游标应保持不变，下一 tick 重新 classify。  
「返回未生效 → 游标回退上一步」仍只适用于：**Pass2 通过且已 click 之后**，点后校验失败的路径。

### 与点前弹窗扫描的顺序

保持：

1. `_ensure_clear_for_click`（已知 X）
2. Pass1 定位 + 缓存 `roi_ref`
3. Pass2 ROI 确认
4. `click_css`

若 1 发现弹窗：关弹窗并取消，不做 Pass1/2。  
若 3 失败：可能是未知遮挡或剧变——**本轮不点击**；可选地触发一次 `_close_popup` 尝试（非必须，避免在不确定时乱点 X）。推荐：仅打日志 `ROI 确认失败，取消点击`，下 tick 交给 classify（若已是 POPUP 会走关窗）。

### 重构点击路径（关键）

今日 `find_and_click` 内「截屏→匹配→点击」耦合太紧，双确认难以插入。

本期改为感知环主路径显式两段（Navigator 可提供原语）：

```text
# 伪代码
screen = grab_full()          # 或复用本 tick 已有帧
hit = match_on(screen, tpl)   # → score, (x,y), roi_ref
if score < thr: fail
roi_now = grab_roi(...)
if not roi_similar(roi_ref, roi_now):
    log cancel; return False
click_css(x, y)
return True
```

`PopupMonitor` / 登录等仍可继续用旧 `find_and_click`（内部可逐步改为「无 Pass2」的兼容封装），避免大爆炸。

## API 草图

```text
# 例如 ui_confirm.py 或 navigator / ui_state 旁路模块

ROI_PAD_PX = 12
ROI_CONFIRM_THRESHOLD = 0.90
COORDS_ROI_SIZE = 48

@dataclass
class ClickPlan:
    x: int
    y: int
    roi_ref: np.ndarray          # BGR
    template_name: str | None
    score: float

def plan_click_from_screen(screen, template, bounds=None, threshold=...) -> ClickPlan | None: ...
def plan_click_coords(screen, x, y) -> ClickPlan: ...
def confirm_roi(nav, plan: ClickPlan) -> bool: ...
def execute_click_with_confirm(nav, plan: ClickPlan) -> bool:
    """confirm_roi 通过才 click_css；失败返回 False。"""
```

`UiLoop._do_click_step` / `_do_back`：用上述 API 替代直接 `find_and_click`（主线路径）。

## 模块改动

| 文件 | 变更 |
|------|------|
| 新：`click_confirm.py`（名可议） | `ClickPlan`、ROI 裁切、相似度、`execute_click_with_confirm` |
| `navigator.py` | `grab_roi`（CDP clip + 全图回退）；保持 `click_css` |
| `ui_loop.py` | `_do_click_step` / `_do_back` 走双确认；日志 |
| `test_core.py` | ROI 通过/失败；失败不推进游标；坐标点击 ROI |
| 文档 | 本 spec；实现计划另文 |

## 日志

- 通过：可 DEBUG `ROI 确认通过 score=...`
- 失败：WARN `ROI 确认失败 score=...，取消点击`（含任务名/模板名）
- CDP clip 失败回退全图：DEBUG 一次即可，避免刷屏

## 成功标准

1. 单测：构造 `roi_ref` 与篡改后的 `roi_now`（中间画黑块模拟弹窗）→ `confirm_roi` 为 False，且 mock `click_css` 未被调用。
2. 单测：`roi_now ≈ roi_ref` → 调用 `click_css` 一次。
3. 单测：`GO_BACK` 在 ROI 失败时 `backs_done` / `task_index` 不变，且不触发 `rewind_to_previous_step`。
4. 实战：返回前弹窗遮挡返回键附近时，日志出现 ROI 取消，而非「已点击 back_arrow」后迷路；若点击已发出但未返回，仍由点后校验 + 回退兜底。

## 风险与缓解

| 风险 | 缓解 |
|------|------|
| 云游戏噪声导致误杀 | 阈值 0.90 起步；ROI 略 pad；实战可调 |
| 弹窗不覆盖 ROI 仍拦点击 | 保留点前 X 扫描 + 点后生效校验 |
| CDP clip 坐标不一致 | 与截图/点击同一像素空间；单测 + 实战点校准页 |
| 每步多一次采样变慢 | 仅主线点击；优先局部截取 |
| 与 `find_and_click` 双轨 | 环内主路径走新 API；旧 API 保留给监控/登录 |

## 测试计划

- 单元：`roi_similar` 相同图 / 遮挡图 / 尺寸不匹配。
- 单元：`execute_click_with_confirm` 与 `click_css` 调用关系。
- 单元：UiLoop 点击步、返回步在 confirm 失败时游标不变。
- 回归：现有 classify / decide / 返回回退单测保持通过。

## 实现分期（建议）

| 期 | 内容 |
|----|------|
| P0 | 全图裁 ROI + 相关系数 + 环内 CLICK/BACK 接入（不依赖 CDP） |
| P1 | `grab_roi` CDP clip 加速 |
| P2 | 阈值配置化、实战调参、可选把 CLOSE 路径也纳入（若有需要） |

本期设计默认交付 **P0**；P1 作为同一 spec 的增强项，接口预留 `grab_roi`。
