# Windows EXE 路径与打包稳定性实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Windows 单文件 EXE 将截图和日志保存在 EXE 同级目录，并确保 Windows 路径测试和 CI 打包配置可靠。

**Architecture:** `config.py` 统一区分只读资源根目录与可写输出根目录。日志和截图只依赖可写路径接口，打包流程统一从依赖清单安装并显式收集 Selenium Manager 二进制文件。

**Tech Stack:** Python 3.12、pytest、Tkinter、PyInstaller、GitHub Actions、Selenium 4

## Global Constraints

- EXE 环境的截图目录固定为 `<EXE目录>\screenshots\<账号>\`。
- EXE 环境的日志目录固定为 `<EXE目录>\logs\`。
- 开发环境继续使用项目根目录下的 `screenshots` 和 `logs`。
- 打包资源继续通过 `resource_path()` 从 `sys._MEIPASS` 读取。
- 本轮不修改 `pyautogui` 截图和点击行为。

---

### Task 1: 统一可写路径

**Files:**
- Modify: `config.py`
- Modify: `test_core.py`

**Interfaces:**
- Produces: `app_dir() -> str`
- Produces: `writable_path(relative_path: str) -> str`

- [ ] **Step 1: 编写失败测试**

在 `test_core.py` 增加：

```python
class TestWritablePath:
    def test_development_path_uses_project_root(self):
        from config import app_dir, writable_path

        expected_root = os.path.dirname(os.path.abspath(__file__))
        assert app_dir() == expected_root
        assert writable_path("screenshots") == os.path.join(
            expected_root, "screenshots"
        )

    def test_frozen_path_uses_executable_directory(self):
        import config

        executable = os.path.join("C:\\", "Tools", "AutoScreenshot.exe")
        with patch.object(config.sys, "frozen", True, create=True), \
             patch.object(config.sys, "executable", executable):
            assert config.app_dir() == os.path.dirname(executable)
            assert config.writable_path("logs") == os.path.join(
                os.path.dirname(executable), "logs"
            )
```

- [ ] **Step 2: 运行测试并确认失败**

运行：

```powershell
python -m pytest test_core.py::TestWritablePath -q
```

预期：因 `app_dir` 和 `writable_path` 尚不存在而失败。

- [ ] **Step 3: 实现可写路径接口**

在 `config.py` 中加入：

```python
def app_dir() -> str:
    """返回运行时可写文件的根目录。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def writable_path(relative_path: str) -> str:
    """获取截图、日志等运行时输出的绝对路径。"""
    return os.path.join(app_dir(), relative_path)
```

- [ ] **Step 4: 修复 Windows 模板缓存测试**

将硬编码路径：

```python
nav.templates_dir + "/avatar.png"
```

替换为：

```python
os.path.join(nav.templates_dir, "avatar.png")
```

- [ ] **Step 5: 运行路径相关测试**

运行：

```powershell
python -m pytest test_core.py::TestWritablePath test_core.py::TestTemplateCache -q
```

预期：全部通过。

---

### Task 2: 将截图和日志写到 EXE 同级目录

**Files:**
- Modify: `logger.py`
- Modify: `gui/app.py`
- Modify: `test_core.py`

**Interfaces:**
- Consumes: `config.writable_path(relative_path: str) -> str`
- Produces: `logger.default_log_file() -> str`

- [ ] **Step 1: 编写失败测试**

在 `test_core.py` 增加：

```python
class TestOutputLocations:
    @patch("logger.writable_path", return_value=os.path.join("C:\\", "App", "logs"))
    def test_default_log_file_uses_writable_logs_directory(self, _mock_path):
        from logger import default_log_file

        path = default_log_file()
        assert os.path.dirname(path) == os.path.join("C:\\", "App", "logs")
        assert path.endswith(".log")
```

- [ ] **Step 2: 运行测试并确认失败**

运行：

```powershell
python -m pytest test_core.py::TestOutputLocations -q
```

预期：因 `logger.default_log_file` 尚不存在而失败。

- [ ] **Step 3: 修改默认日志路径**

在 `logger.py` 顶层导入：

```python
import os
from config import writable_path
```

增加：

```python
def default_log_file() -> str:
    """创建默认日志目录并返回本次运行的日志文件路径。"""
    log_dir = writable_path("logs")
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return os.path.join(log_dir, f"{timestamp}.log")
```

并将 `setup_logger()` 的默认路径分支替换为：

```python
if log_file is None:
    log_file = default_log_file()
```

- [ ] **Step 4: 修改截图输出路径**

在 `gui/app.py` 的工作流配置导入中，将 `resource_path` 扩展为：

```python
from config import ..., resource_path, writable_path
```

将截图器创建改为：

```python
shot = Screenshotter(
    output_dir=os.path.join(writable_path(SCREENSHOTS_DIR), account)
)
```

- [ ] **Step 5: 运行输出路径测试**

运行：

```powershell
python -m pytest test_core.py::TestOutputLocations -q
```

预期：通过。

---

### Task 3: 稳定 Windows CI 打包

**Files:**
- Modify: `.github/workflows/build.yml`

**Interfaces:**
- Consumes: `requirements.txt`
- Produces: `dist/AutoScreenshot.exe`

- [ ] **Step 1: 统一依赖安装**

将分散的运行依赖安装命令替换为：

```yaml
pip install -r requirements.txt
pip install pyinstaller
```

- [ ] **Step 2: 补充 Edge 和 Selenium Manager 打包项**

在 PyInstaller 参数中加入：

```yaml
--hidden-import selenium.webdriver.edge.service `
--hidden-import selenium.webdriver.edge.options `
--collect-binaries selenium `
```

保留 Chrome 和 `webdriver-manager` 项，因为非 Windows 分支仍引用它们。

- [ ] **Step 3: 增加构建产物检查**

在打包步骤后增加：

```yaml
- name: 验证构建产物
  run: |
    if (-not (Test-Path "dist/AutoScreenshot.exe")) {
      throw "未生成 dist/AutoScreenshot.exe"
    }
```

- [ ] **Step 4: 检查工作流 YAML**

运行：

```powershell
python -c "import yaml; yaml.safe_load(open('.github/workflows/build.yml', encoding='utf-8')); print('YAML OK')"
```

预期：输出 `YAML OK`。若本地没有 PyYAML，运行 `python -m pip install PyYAML` 后重试。

---

### Task 4: 完整验证

**Files:**
- Verify: `config.py`
- Verify: `logger.py`
- Verify: `gui/app.py`
- Verify: `test_core.py`
- Verify: `.github/workflows/build.yml`

**Interfaces:**
- Consumes: 前三项任务的全部修改
- Produces: 可审查、可测试的 Windows EXE 稳定性改动

- [ ] **Step 1: 运行完整测试**

运行：

```powershell
python -m pytest -q
```

预期：全部测试通过。

- [ ] **Step 2: 检查 Python 语法**

运行：

```powershell
python -m compileall -q config.py logger.py screenshotter.py browser.py gui
```

预期：退出码为 0。

- [ ] **Step 3: 检查代码诊断**

检查 `config.py`、`logger.py`、`gui/app.py`、`test_core.py`，预期没有新增诊断。

- [ ] **Step 4: 检查最终差异**

运行：

```powershell
git diff --check
git status --short
```

预期：无空白错误，修改范围与设计一致。
