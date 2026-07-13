# Windows EXE 打包修复设计

## 背景

当前项目通过 GitHub Actions 在 `windows-latest` 上使用 PyInstaller 打包成 `AutoScreenshot.exe`。
国内 Windows 用户运行 exe 后，GUI 可以启动，但在"打开浏览器"步骤卡住，无法继续。

## 根因（3 个）

1. **`webdriver-manager` 下载 ChromeDriver 走 Google CDN** — 国内被墙，`ChromeDriverManager().install()` 挂起
2. **PyInstaller 缺少 `--hidden-import`** — tkinter / cv2 / numpy / selenium 等核心模块未被自动检测，导致 exe 控制台窗口都不出现
3. **`navigator.py:81` 路径分隔符硬编码 `/`** — Windows + PyInstaller `sys._MEIPASS` 下 `cv2.imread()` 处理 `/` 不可靠

## 用户约束

- 目标用户均在国内使用
- Windows 机器上已安装 Chrome 浏览器
- 用户不应需要手动下载额外依赖

## 方案：最小化修复（方案 A）

### 改动 1：`browser.py` — ChromeDriver 走国内镜像

给 `ChromeDriverManager` 指定 npmmirror 镜像源，自动匹配用户本机 Chrome 版本并下载驱动。

```python
from webdriver_manager.chrome import ChromeDriverManager

service = Service(ChromeDriverManager(
    driver_repository_url="https://registry.npmmirror.com/-/binary/chrome-for-testing"
).install())
```

首次下载 ~15MB 缓存到 `%USERPROFILE%\.wdm\`，后续启动秒开。

### 改动 2：`navigator.py` — 路径兼容 Windows

```python
# 之前：return f"{self.templates_dir}/{template_name}"
# 之后：
import os
return os.path.join(self.templates_dir, template_name)
```

### 改动 3：`build.yml` — PyInstaller 参数补全

- `--console` 改为 `--windowed`（GUI 应用不需要黑窗口）
- 添加 `--hidden-import` 覆盖所有核心模块：tkinter, tkinter.ttk, cv2, numpy, PIL, PIL.Image, selenium, webdriver_manager 及其子模块

### 改动 4：（无需额外改动）

`browser.py` 的 `--no-sandbox` 和 Windows 平台分支已是 `pass`，无需修改。

## 边界考虑

- **Chrome 未安装**：首次运行 `ChromeDriverManager` 会抛出异常，需在 GUI 中捕获并给出中文提示
- **镜像不可用**：npmmirror 已稳定运行多年，风险低。若失效，可后续切换为淘宝镜像或腾讯云镜像
- **版本不匹配**：`webdriver-manager` 自动匹配本机 Chrome 版本，不会出现不匹配

## 测试验证

1. CI 构建通过，生成 exe
2. 在 Windows 10/11 虚拟机或实体机上运行 exe
3. 确认：GUI 正常启动 → 点击启动 → Chrome 被打开 → 正常进入 gamer.qq.com
4. 确认：第二次运行不再下载 ChromeDriver，直接打开浏览器
