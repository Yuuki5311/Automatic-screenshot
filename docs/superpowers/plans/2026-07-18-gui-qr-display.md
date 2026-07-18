# GUI 展示登录二维码 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 腾讯先锋与游戏平台登录时，将 OpenCV 裁切的二维码推送到 GUI 扫码页（双通道，原窗口仍可扫）。

**Architecture:** `login.crop_qr_from_bgr` 统一检测裁切；`web_login` / `game_login` 通过 `on_qr(image)` 推送；GUI 有图发 `type:"qr"`，无图回退 `scan_wait`。

**Tech Stack:** Python 3.12、OpenCV、Pillow、Selenium、Tkinter、pytest

## Global Constraints

- 双通道：不隐藏浏览器/游戏窗口。
- 裁切边距约 20%；刷新间隔 8 秒。
- 检测失败返回 `None`，不抛异常；GUI 回退文字提示。
- 不改登录成功判定、不改 `QRDisplay` API、不加「重新获取」按钮。
- `on_qr` 兼容 `on_qr(image)` 与 `on_qr()`。

## File Structure

| 文件 | 职责 |
|------|------|
| `login.py` | `crop_qr_from_bgr`；两处登录推送二维码图 |
| `gui/app.py` | `on_qr` 分支发 `qr` / `scan_wait` |
| `test_core.py` | 裁切辅助函数单测 |

---

### Task 1: `crop_qr_from_bgr` 辅助函数

**Files:**
- Modify: `login.py`
- Modify: `test_core.py`

**Interfaces:**
- Produces: `crop_qr_from_bgr(frame_bgr: np.ndarray) -> Image.Image | None`

- [x] **Step 1: 编写失败测试**

在 `test_core.py` 末尾（或 `TestPlatformBounds` 附近）新增：

```python
class TestCropQrFromBgr:
    def test_blank_image_returns_none(self):
        from login import crop_qr_from_bgr
        import numpy as np

        blank = np.zeros((200, 200, 3), dtype=np.uint8)
        assert crop_qr_from_bgr(blank) is None

    def test_synthetic_qr_returns_pil_image(self):
        from login import crop_qr_from_bgr
        import cv2
        import numpy as np
        from PIL import Image

        # 生成可读二维码
        qr = cv2.QRCodeEncoder_Params() if False else None
        # 用 qrcode 库或 OpenCV 不可用时：用 PIL + 第三方
        # 本项目无 qrcode 依赖时，用 cv2 画框不够；改用：
        try:
            import qrcode
        except ImportError:
            # 无 qrcode：构造足够大的黑白模块图案可能不稳定
            # 改用：写入已知可检测的最小实现
            pass

        img = np.ones((400, 400, 3), dtype=np.uint8) * 255
        # 使用 opencv 无法直接 encode；用 pillow 画 + 若无库则 skip
        # 实际实现：用 segno/qrcode，或 pytest.importorskip("qrcode")
```

更稳妥的测试实现（计划采用）：

```python
class TestCropQrFromBgr:
    def test_blank_image_returns_none(self):
        from login import crop_qr_from_bgr
        import numpy as np

        blank = np.zeros((200, 200, 3), dtype=np.uint8)
        assert crop_qr_from_bgr(blank) is None

    def test_synthetic_qr_returns_pil_image(self):
        qrcode = pytest.importorskip("qrcode")
        from login import crop_qr_from_bgr
        import cv2
        import numpy as np
        from PIL import Image

        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data("https://example.com/login-test")
        qr.make(fit=True)
        pil = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        # 放到白底大图中央
        canvas = Image.new("RGB", (500, 500), "white")
        canvas.paste(pil, (100, 100))
        frame_bgr = cv2.cvtColor(np.array(canvas), cv2.COLOR_RGB2BGR)

        result = crop_qr_from_bgr(frame_bgr)
        assert result is not None
        assert isinstance(result, Image.Image)
        assert result.size[0] > 0 and result.size[1] > 0
```

若环境无 `qrcode`，在测试中用 `pytest.importorskip("qrcode")`；实现阶段若缺依赖，可 `pip install qrcode` 仅作测试依赖，或改用已安装库。备选：用 OpenCV `cv2.imdecode` 加载仓库内一张含真实二维码的 debug 截图（若有）。优先 `qrcode` 合成。

- [ ] **Step 2: 运行确认失败**

```bash
python -m pytest test_core.py::TestCropQrFromBgr -q
```

Expected: FAIL（`crop_qr_from_bgr` 未定义）

- [ ] **Step 3: 实现 `crop_qr_from_bgr`**

在 `login.py` 顶部 imports 增加：

```python
from PIL import Image
```

在 bounds 辅助函数之后新增：

```python
def crop_qr_from_bgr(frame_bgr: np.ndarray) -> Image.Image | None:
    """从 BGR 截图中检测二维码并裁切为 PIL Image。

    四周加约 20% 边距；检测失败返回 None。
    """
    if frame_bgr is None or frame_bgr.size == 0:
        return None
    try:
        detector = cv2.QRCodeDetector()
        _data, bbox, _ = detector.detectAndDecode(frame_bgr)
        if bbox is None or len(bbox) == 0:
            return None
        pts = np.array(bbox, dtype=np.float32).reshape(-1, 2)
        x_min, y_min = pts.min(axis=0)
        x_max, y_max = pts.max(axis=0)
        w = max(x_max - x_min, 1.0)
        h = max(y_max - y_min, 1.0)
        pad_x = w * 0.2
        pad_y = h * 0.2
        h_img, w_img = frame_bgr.shape[:2]
        x0 = max(int(x_min - pad_x), 0)
        y0 = max(int(y_min - pad_y), 0)
        x1 = min(int(x_max + pad_x), w_img)
        y1 = min(int(y_max + pad_y), h_img)
        if x1 <= x0 or y1 <= y0:
            return None
        crop_bgr = frame_bgr[y0:y1, x0:x1]
        crop_rgb = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2RGB)
        return Image.fromarray(crop_rgb)
    except Exception:
        log.debug("crop_qr_from_bgr 失败", exc_info=True)
        return None
```

- [ ] **Step 4: 运行确认通过**

```bash
python -m pytest test_core.py::TestCropQrFromBgr -q
```

Expected: PASS（若缺 `qrcode`：`pip install qrcode[pil]` 后重跑，或仅跑 `test_blank_image_returns_none`）

- [ ] **Step 5: Commit**

```bash
git add login.py test_core.py
git commit -m "feat: add crop_qr_from_bgr helper for login QR display"
```

---

### Task 2: `web_login` 截取并推送二维码

**Files:**
- Modify: `login.py`（`web_login`）

**Interfaces:**
- Consumes: `crop_qr_from_bgr`
- Produces: `on_qr(image)` 或 `on_qr()`；轮询期间每 8 秒更新

- [ ] **Step 1: 改 `on_qr` 类型注释与首次推送**

将签名改为：

```python
on_qr: Callable[..., None] | None = None,
```

在 iframe 切换成功后，替换「通知 GUI 等待扫码（不截取二维码）」为：

```python
def _capture_and_push_qr() -> None:
    if not on_qr:
        return
    try:
        png = driver.get_screenshot_as_png()
        frame_bgr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
        image = crop_qr_from_bgr(frame_bgr) if frame_bgr is not None else None
        if image is not None:
            on_qr(image)
        else:
            on_qr()
    except Exception:
        log.debug("web_login 截取二维码失败", exc_info=True)
        on_qr()

driver.switch_to.default_content()  # 截全页更稳：含 iframe 渲染内容
# 注意：Selenium 全页截图通常包含 iframe 内容，无需停在 iframe 内
_capture_and_push_qr()
on_status("请使用手机扫描二维码登录...")
```

实现注意：轮询前已 `switch_to.frame`。截图前应 `driver.switch_to.default_content()` 再截，避免只截到 iframe 内局部；随后轮询逻辑本身会 `default_content`。

- [ ] **Step 2: 轮询中每 8 秒刷新二维码**

在 `while time.time() - start < timeout:` 循环内，用变量记录上次推送时间：

```python
last_qr_push = time.time()
# 首次已在循环外推送

while time.time() - start < timeout:
    ...
    if time.time() - last_qr_push >= 8:
        _capture_and_push_qr()
        last_qr_push = time.time()
    time.sleep(2)
```

成功判定分支保持不变。

- [ ] **Step 3: 语法检查**

```bash
python -m compileall -q login.py
```

Expected: 无输出、exit 0

- [ ] **Step 4: Commit**

```bash
git add login.py
git commit -m "feat: web_login pushes cropped QR to GUI every 8s"
```

---

### Task 3: `game_login` 检测到二维码时推送裁切图

**Files:**
- Modify: `login.py`（`game_login`）

**Interfaces:**
- Consumes: `crop_qr_from_bgr`
- Produces: 首次检测成功时 `on_qr(image)`；之后每 8 秒更新

- [ ] **Step 1: 移除提前空 `on_qr()`，改为检测时推送**

删除「通知 GUI 并等待扫码」里的立即 `on_qr()`，改为在检测到 bbox 时推送：

```python
# 进入等待环前可先 on_status，不调用 on_qr
on_status(f"请在游戏窗口中扫描 {platform_name} 登录二维码...")
time.sleep(3)

start = time.time()
qr_appeared = False
last_qr_push = 0.0
QR_CODE_TIMEOUT = 15
...
while ...:
    ...
    if not qr_appeared:
        try:
            png = nav.driver.get_screenshot_as_png()
            frame_bgr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
            del png
            image = crop_qr_from_bgr(frame_bgr)
            if image is not None:
                qr_appeared = True
                if on_qr:
                    on_qr(image)
                last_qr_push = time.time()
                on_status("✅ 检测到登录二维码")
            del frame_bgr
        except Exception:
            log.debug("二维码检测异常", exc_info=True)
        ...
    else:
        # 已出现：每 8 秒刷新
        if on_qr and time.time() - last_qr_push >= 8:
            try:
                png = nav.driver.get_screenshot_as_png()
                frame_bgr = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_COLOR)
                image = crop_qr_from_bgr(frame_bgr)
                if image is not None:
                    on_qr(image)
                    last_qr_push = time.time()
            except Exception:
                log.debug("刷新游戏二维码失败", exc_info=True)
```

保留 15 秒未出现则失败、avatar/enter_game 成功逻辑不变。

- [ ] **Step 2: 语法检查**

```bash
python -m compileall -q login.py
```

- [ ] **Step 3: Commit**

```bash
git add login.py
git commit -m "feat: game_login pushes cropped QR image to GUI"
```

---

### Task 4: GUI `on_qr` 接线

**Files:**
- Modify: `gui/app.py`（腾讯先锋与游戏登录两处 `on_qr`）

**Interfaces:**
- Consumes: `on_qr(image=None)`；消息 `type:"qr"` / `type:"scan_wait"`

- [ ] **Step 1: 改腾讯先锋 `on_qr`**

```python
def on_qr(image=None):
    title = f"腾讯先锋{'QQ' if login_type == 'qq' else '微信'}登录"
    if image is not None:
        self._send({
            "type": "qr",
            "image": image,
            "title": title,
            "status": "⏳ 请扫描下方二维码（也可在浏览器窗口扫）...",
        })
    else:
        self._send({
            "type": "scan_wait",
            "title": title,
            "text": "⏳ 未截到二维码，请直接在浏览器窗口扫码...",
        })
```

- [ ] **Step 2: 改游戏登录 `on_game_qr`**

```python
def on_game_qr(image=None):
    title = f"游戏 {platform_display} 登录"
    if image is not None:
        self._send({
            "type": "qr",
            "image": image,
            "title": title,
            "status": "⏳ 请扫描下方二维码（也可在游戏窗口扫）...",
        })
    else:
        self._send({
            "type": "scan_wait",
            "title": title,
            "text": "⏳ 未截到二维码，请直接在游戏窗口扫码...",
        })
```

若 `gui/app.py` 中另有重试路径的 `on_game_qr`（约 687 行），同样改法。

- [ ] **Step 3: 跑相关测试 + 编译**

```bash
python -m pytest test_core.py::TestCropQrFromBgr test_core.py::TestPlatformBounds -q
python -m compileall -q login.py gui/app.py
```

Expected: PASS / exit 0

- [ ] **Step 4: Commit**

```bash
git add gui/app.py
git commit -m "feat: GUI shows login QR images with scan_wait fallback"
```

---

## Spec Coverage Checklist

| Spec 要求 | Task |
|-----------|------|
| `crop_qr_from_bgr` + 20% 边距 | Task 1 |
| `web_login` 推送 + 8s 刷新 | Task 2 |
| `game_login` 检测时推送 + 8s 刷新 | Task 3 |
| GUI `qr` / `scan_wait` 双通道文案 | Task 4 |
| 单测 blank / synthetic QR | Task 1 |
| 不改成功判定 / QRDisplay API | 全任务遵守 |
