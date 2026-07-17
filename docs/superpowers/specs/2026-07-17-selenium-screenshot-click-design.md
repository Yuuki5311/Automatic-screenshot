# Selenium 截图与点击统一设计

## 目标

将游戏内匹配截图与点击从 `pyautogui` 全屏/系统鼠标，统一为 Selenium
浏览器 CSS 像素坐标系，消除 Windows DPI / 窗口位置导致的匹配与点击漂移。

## 非目标

- 不改动腾讯先锋网页阶段的 DOM 登录与搜索（`login.web_login`、`game_launcher`）。
- 不改动 macOS `client_launcher.py` 桌面客户端流程。
- 本轮不批量重做全部模板图（现有模板按浏览器画面采集，优先复用）。
- 不在本轮实现静默移出屏幕外的窗口策略。

## 坐标系

| 量 | 定义 |
|---|---|
| 截图 | `driver.get_screenshot_as_png()`，CSS 像素，目标约 1920×1080 |
| 匹配结果 | 模板中心点，单位 CSS 像素，相对浏览器视口左上角 |
| 点击 | Selenium `ActionChains` / `pointer` 在同一 CSS 坐标点击 |
| bounds | `(x, y, w, h)` 均为 CSS 像素 |
| 兜底坐标 | `calibrated_coords.json` 存 CSS 像素；旧桌面坐标作废，需重标 |

`Navigator._scale` 固定为 `1.0`。删除基于全屏物理像素与逻辑像素比值的
Retina 换算。

## 组件改动

### `navigator.py`

- 构造函数增加必填（或工作流必传）参数 `driver`。
- `_get_screenshot()`：解码 `driver.get_screenshot_as_png()` 为 BGR
  `numpy` 数组。
- `_click_at(x, y)`：在浏览器视口 CSS 坐标点击，不再调用
  `pyautogui.click`。
- 兜底坐标点击同样走 `_click_at`，不再直接 `pyautogui.click`。
- 保留模板缓存、`find_and_click` / `wait_for_template` 对外签名；
  `bounds` 语义改为 CSS。

### `screenshotter.py`

- 构造函数增加 `driver`。
- `take(name)` 保存浏览器内容截图，不再全屏截取。

### `gui/app.py`

- 创建 `Navigator` / `Screenshotter` 时传入同一个 `driver`。
- 阶段 4 的 `__coords__` 点击、百分比/`pyautogui.click` 回退，改为
  Navigator 的 CSS 点击辅助方法（或等价 Selenium 点击）。
- 用 `BROWSER_WIDTH` / `BROWSER_HEIGHT`（或截图像素尺寸）计算
  bounds，不再用 `pyautogui.size() * _scale`。

### `calibrate_coords.py`

- 改为基于已打开的 Edge/Chrome 窗口采集相对视口的 CSS 坐标
  （窗口位置 + 鼠标位置换算，或引导用户在固定 1920×1080 窗口内标定）。
- 写入 `calibrated_coords.json` 的值为 CSS 像素。
- 使用前需用户在目标分辨率下重新跑一遍标定。

### `popup_monitor.py` / `login.game_login`

- 通过已注入 `driver` 的 `Navigator` 间接受益，无独立截图源。
- `game_login` 中基于 `pyautogui.size()` 的 bounds 改为 CSS 视口尺寸。

## 错误处理

- `driver` 缺失或会话失效：匹配/截图立即失败并记日志，由 GUI 工作流捕获。
- 模板匹配失败：行为不变（重试 → 可选 CSS 兜底坐标 → 返回 False）。
- 标定工具在无法解析窗口位置时明确报错，不静默写入错误坐标系。

## 测试与验收

1. 单元测试：mock `driver.get_screenshot_as_png` 与 ActionChains，
   验证匹配坐标不做 `_scale` 除法、点击调用走 Selenium 路径。
2. `Screenshotter` 在传入 mock driver 时写出解码后的 PNG。
3. 现有 PopupMonitor / threshold 测试在 mock `_get_screenshot` 下仍通过。
4. 实机：Windows Edge 1920×1080，模板匹配置信度可用；坐标点击命中；
   保存的截图仅为浏览器内容。
5. 用户重跑 `calibrate_coords.py` 后，兜底坐标在 CSS 下可用。

## 风险

- 个别模板若实际来自含边框/不同缩放的画面，置信度可能下降，需单独重截。
- 旧 `calibrated_coords.json` 在重标前不可信，应在发布说明中提醒。
