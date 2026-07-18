# GUI 展示登录二维码设计

日期：2026-07-18
状态：已确认

---

## 1. 概述

在可视化 UI 的扫码页展示腾讯先锋登录与游戏平台登录的二维码，用户可直接在 GUI 扫码；浏览器/游戏窗口中的原二维码仍保留（双通道）。

当前实现只发 `scan_wait` 文字提示，不推送二维码图片。本设计恢复并落实原 GUI 设计中的「截取二维码 → GUI 展示」路径。

---

## 2. 目标与非目标

**目标**
- 腾讯先锋网页登录（`web_login`）检测到二维码后，裁切并推送到 GUI
- 游戏平台选择登录（`game_login`）检测到二维码后，裁切并推送到 GUI
- 检测失败时回退为文字提示，原窗口仍可扫码
- 二维码刷新后周期性更新 GUI 图片

**非目标**
- 不隐藏/最小化浏览器窗口
- 不改登录成功判定逻辑
- 不新增「重新获取二维码」按钮
- 不改 `QRDisplay` 组件布局/API

---

## 3. 方案选择

采用 **双通道展示（方案 B）** + **统一 OpenCV 检测裁切（方案 1）**。

| 备选 | 结论 |
|------|------|
| GUI 为主（仅扫 GUI） | 拒绝：完全依赖截图质量，更脆 |
| Selenium 元素截图（先锋）+ OpenCV（游戏） | 拒绝：两套路径，iframe DOM 易碎 |
| 固定区域裁切 | 拒绝：分辨率变化易偏 |

---

## 4. 架构与数据流

```
login.py                          GUI (主线程)
────────                          ───────────
截图 → QRCodeDetector
  → 按 bbox 裁切 (+边距)
  → on_qr(PIL.Image)  ──queue──→  type:"qr" → QRDisplay.show_qr()
  → on_status(...)    ──queue──→  type:"qr_status"
原窗口二维码保持不变（双通道）
```

### 文件变更

| 文件 | 变更 |
|------|------|
| `login.py` | 新增 `crop_qr_from_bgr`；`web_login` / `game_login` 真正传图给 `on_qr` |
| `gui/app.py` | `on_qr` 有图发 `qr`，无图回退 `scan_wait` |
| `gui/widgets/qr_display.py` | 不改（已有 `show_qr`） |
| `test_core.py` | 补 `crop_qr_from_bgr` 单测 |

---

## 5. `login.py` 行为

### 5.1 公共辅助

```python
def crop_qr_from_bgr(frame_bgr) -> Image.Image | None:
```

- 使用 `cv2.QRCodeDetector().detectAndDecode`
- 有 `bbox` 则裁切，四周加约 **20% 边距**，转 RGB PIL
- 检测失败返回 `None`，不抛异常

回调签名兼容无参/有参：

```python
on_qr: Callable[..., None] | None  # on_qr(image) 或 on_qr()
```

### 5.2 `web_login`（腾讯先锋）

1. 进入登录 iframe 后，对当前页截图并尝试裁切
2. 成功 → `on_qr(image)`；失败 → `on_qr()`（无参）
3. 轮询登录成功期间：每 **8 秒**再截一次并更新 GUI（应对二维码过期）
4. 成功判定逻辑不变

### 5.3 `game_login`（平台选择登录）

1. 点击平台 /「登录其他账号」后进入等待环
2. 保留现有「15 秒内必须检测到二维码」
3. **首次检测到 `bbox` 时**：裁切 → `on_qr(image)`（替代当前空的 `on_qr()`）
4. 之后每 **8 秒**若仍能检测到，再推一次更新图
5. 登录成功 / 超时 / 重试逻辑不变

---

## 6. GUI 接线

两处 `on_qr`（腾讯先锋、游戏登录）统一：

```python
def on_qr(image=None):
    if image is not None:
        self._send({
            "type": "qr",
            "image": image,
            "title": "<场景标题>",
            "status": "⏳ 请扫描下方二维码（也可在浏览器/游戏窗口扫）...",
        })
    else:
        self._send({
            "type": "scan_wait",
            "title": "<场景标题>",
            "text": "⏳ 未截到二维码，请直接在浏览器/游戏窗口扫码...",
        })
```

- 复用已有 `type:"qr"` → `QRDisplay.show_qr` 路径
- 文案明确双通道

### 失败与边界

| 情况 | 行为 |
|------|------|
| OpenCV 检测不到 | `scan_wait` 回退，原窗口仍可扫 |
| 二维码过期刷新 | 周期性重截更新 GUI 图 |
| 登录成功 | 现有 `qr_status` 绿字 + 切进度页，不变 |
| 超时 / 重试 | 现有超时与 `game_login` 3 次重试不变 |

---

## 7. 测试

- `crop_qr_from_bgr`：合成带码图 → 返回非空 PIL；空白图 → `None`
- 可选：mock `on_qr` 确认检测到时传入 `Image`
- 不引入真实浏览器 E2E

---

## 8. 验收标准

1. 腾讯先锋登录时，GUI 扫码页出现可扫的二维码图（或明确回退文案）
2. 游戏平台登录时，同上
3. 用户可在 GUI 或原窗口任一处完成扫码
4. 现有登录成功/失败/重试行为不被破坏
5. 相关单测通过
