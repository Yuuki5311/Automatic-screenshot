# Windows EXE 路径与打包稳定性设计

## 目标

让 Windows 单文件 EXE 将截图和日志稳定保存在 EXE 同级目录，并修复
Windows 路径测试与打包配置问题。Selenium 浏览器截图迁移不在本轮范围内。

## 路径设计

`config.py` 提供两类路径：

- `resource_path(relative_path)`：只用于随程序打包的只读资源。EXE 环境以
  `sys._MEIPASS` 为根目录，开发环境以项目根目录为根目录。
- `writable_path(relative_path)`：用于运行时输出。EXE 环境以
  `os.path.dirname(sys.executable)` 为根目录，开发环境以项目根目录为根目录。

截图写入：

```text
<EXE目录>\screenshots\<账号>\
```

日志写入：

```text
<EXE目录>\logs\
```

程序在首次写入时自动创建目录。若 EXE 所在目录不可写，异常由现有工作流
捕获并显示，不静默切换到用户难以找到的位置。

## 代码改动

1. `config.py`
   - 增加 `app_dir()`，返回 EXE 所在目录或开发环境项目根目录。
   - 增加 `writable_path(relative_path)`。

2. `logger.py`
   - 默认日志目录改为 `writable_path("logs")`。
   - 继续允许调用方显式传入日志文件路径。

3. `gui/app.py`
   - 截图输出由 `resource_path(SCREENSHOTS_DIR)` 改为
     `writable_path(SCREENSHOTS_DIR)`。

4. `test_core.py`
   - 路径断言改用 `os.path.join()`。
   - 增加开发环境与模拟 EXE 环境下的可写路径测试。

5. `.github/workflows/build.yml`
   - 从 `requirements.txt` 安装运行依赖，避免 CI 与本地依赖清单分叉。
   - 保留 Windows 单文件 GUI 打包。
   - 增加构建产物存在性检查；实际浏览器启动仍在 Windows 实机验证。

## 错误处理

- 目录创建失败时保留原始 `OSError`，日志或 GUI 会显示具体路径与系统错误。
- 不将输出写入 `sys._MEIPASS`，避免 EXE 退出后输出随临时目录被删除。
- 不修改当前工作目录，避免影响模板、第三方库和用户启动方式。

## 测试与验收

1. 开发环境中 `writable_path("screenshots")` 指向项目根目录。
2. 模拟 `sys.frozen` 时，可写路径以 `sys.executable` 所在目录为根。
3. 模板缓存测试在 Windows 使用原生路径分隔符通过。
4. 完整单元测试通过。
5. CI 能生成 `dist/AutoScreenshot.exe`。
6. 实机运行后，EXE 同级出现 `logs` 和 `screenshots` 目录。

## 后续工作

Selenium 浏览器截图会单独设计和实施，因为它还涉及浏览器内容坐标、原生鼠标
点击坐标及现有模板尺寸的一致性，不能与路径修复混在同一批修改中。
