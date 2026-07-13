# Windows EXE 打包修复实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AutoScreenshot.exe 在 Windows 上无法打开浏览器的问题（3 个根因）。

**Architecture:** 3 个文件的定向修复 — browser.py 的 ChromeDriver 走国内镜像；navigator.py 路径分隔符改为 os.path.join；build.yml 补全 PyInstaller hidden-imports 并改为 --windowed 模式。

**Tech Stack:** Python 3.12, PyInstaller, Selenium, webdriver-manager, OpenCV

## Global Constraints

- 目标用户均在国内，ChromeDriver 下载必须走国内镜像
- 用户本机已安装 Chrome，不需预装其他依赖
- 首次运行自动下载 ChromeDriver（~15MB），后续使用缓存
- PyInstaller 生成单文件 exe（--onefile）

---

### Task 1: 修复 browser.py — ChromeDriver 走 npmmirror 镜像

**Files:**
- Modify: `browser.py:113`

- [ ] **Step 1: 修改 ChromeDriverManager 构造函数**

将 `browser.py` 第 113 行的 `ChromeDriverManager()` 调用添加 `driver_repository_url` 参数：

```python
# 行 113，修改前：
service = Service(ChromeDriverManager().install())

# 修改后：
service = Service(ChromeDriverManager(
    driver_repository_url="https://registry.npmmirror.com/-/binary/chrome-for-testing"
).install())
```

- [ ] **Step 2: 本地验证语法**

```bash
python -c "from browser import create_browser; print('browser module OK')"
```

- [ ] **Step 3: Commit**

```bash
git add browser.py
git commit -m "fix: ChromeDriver 下载走 npmmirror 镜像，修复国内被墙卡住的问题"
```

---

### Task 2: 修复 navigator.py — 路径分隔符改为 os.path.join

**Files:**
- Modify: `navigator.py:81`

- [ ] **Step 1: 添加 import os**

`navigator.py` 头部目前 import 了 `time`, `cv2`, `numpy`, `pyautogui`，但没有 `os`。在第 8 行添加：

```python
# 在 "import time" 之后添加
import os
```

- [ ] **Step 2: 修改 _template_path 方法**

将第 81 行的硬编码路径分隔符改为 `os.path.join`：

```python
# 修改前：
return f"{self.templates_dir}/{template_name}"

# 修改后：
return os.path.join(self.templates_dir, template_name)
```

- [ ] **Step 3: 本地验证语法**

```bash
python -c "from navigator import Navigator; print('navigator module OK')"
```

- [ ] **Step 4: Commit**

```bash
git add navigator.py
git commit -m "fix: 路径分隔符改为 os.path.join，兼容 Windows PyInstaller"
```

---

### Task 3: 修复 build.yml — 补全 PyInstaller 参数

**Files:**
- Modify: `.github/workflows/build.yml:32-35`

- [ ] **Step 1: 替换打包命令**

将第 32-35 行的 `pyinstaller` 命令替换为以下完整版本：

```yaml
      - name: 打包 exe
        run: |
          pyinstaller --onefile --windowed --name AutoScreenshot `
            --hidden-import tkinter `
            --hidden-import tkinter.ttk `
            --hidden-import cv2 `
            --hidden-import cv2._core `
            --hidden-import numpy `
            --hidden-import numpy._core `
            --hidden-import PIL `
            --hidden-import PIL.Image `
            --hidden-import PIL.ImageTk `
            --hidden-import selenium `
            --hidden-import selenium.webdriver.chrome.service `
            --hidden-import selenium.webdriver.chrome.options `
            --hidden-import webdriver_manager `
            --hidden-import webdriver_manager.chrome `
            --hidden-import webdriver_manager.core.os_manager `
            --hidden-import urllib3 `
            --hidden-import requests `
            --hidden-import certifi `
            --add-data "templates;templates" `
            --add-data "calibrated_coords.json;." `
            main.py
```

**变更要点：**
- `--console` → `--windowed`：GUI 应用不需要命令行黑窗口
- 新增 15 个 `--hidden-import`：覆盖 tkinter / cv2 / numpy / PIL / selenium / webdriver-manager / 网络库

- [ ] **Step 2: 本地验证 YAML 语法**

```bash
python -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml')); print('YAML OK')"
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/build.yml
git commit -m "fix: PyInstaller 补全 hidden-imports，--windowed 模式打包 GUI"
```

---

### Task 4: 推送并验证 CI 构建

- [ ] **Step 1: 推送所有 commits**

```bash
git push origin main
```

- [ ] **Step 2: 等待 GitHub Actions 构建**

前往 https://github.com 仓库 Actions 页面，确认 `Build Windows EXE` workflow 通过。

- [ ] **Step 3: 下载构建产物**

从 Actions 的 Artifacts 或 Release (nightly tag) 下载 `AutoScreenshot.exe`。

- [ ] **Step 4: Windows 上验证**

在 Windows 10/11 实体机或虚拟机上：
1. 双击 `AutoScreenshot.exe` → 应出现 GUI 窗口（无黑窗口）
2. 点击「启动」→ 自动下载 ChromeDriver（首次）→ Chrome 打开
3. 确认浏览器正常加载 gamer.qq.com
4. 关闭后再启动 → ChromeDriver 走缓存，直接打开浏览器
