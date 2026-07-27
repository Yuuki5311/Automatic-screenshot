# 王者荣耀云游戏自动截图 — 项目工作流

> 本文档详细描述项目的三层工作流：开发流程 (SDD)、运行时截图流程、CI/CD 构建流程。

---

## 目录

1. [项目概述](#1-项目概述)
2. [开发工作流：SDD 规范驱动开发](#2-开发工作流-sdd-规范驱动开发)
3. [运行时工作流：App 截图执行流程](#3-运行时工作流-app-截图执行流程)
4. [CI/CD 构建工作流](#4-cicd-构建工作流)
5. [关键模块详解](#5-关键模块详解)
6. [模板图管理体系](#6-模板图管理体系)
7. [反检测体系](#7-反检测体系)
8. [线程安全与跨线程通信](#8-线程安全与跨线程通信)
9. [开发历史与功能演进](#9-开发历史与功能演进)

---

## 1. 项目概述

### 1.1 项目目标

自动化操作腾讯先锋云游戏平台，完成：
1. 登录腾讯先锋（QQ 扫码 / 微信扫码 / QQ 密码）
2. 启动王者荣耀云游戏
3. 选择登录平台进入游戏
4. 遍历游戏内 30+ 个页面并截图保存

### 1.2 技术栈

| 层次 | 技术 |
|------|------|
| 语言 | Python 3.12 |
| GUI | Tkinter |
| 浏览器驱动 | Selenium WebDriver + Edge/Chrome |
| 图像匹配 | OpenCV `cv2.matchTemplate` (TM_CCOEFF_NORMED) |
| 反检测 | CDP 注入 + Selenium Stealth 特征掩盖 |
| 打包 | PyInstaller (`--onefile --windowed`) |
| CI/CD | GitHub Actions (`windows-latest` runner) |
| 开发方法 | SDD (Spec-Driven Development) |

### 1.3 项目文件结构

```
C:\Automatic-screenshot/
├── main.py                  # GUI 入口，预加载依赖
├── browser.py               # 反检测浏览器创建
├── config.py                # 全局配置常量
├── login.py                 # 腾讯先锋登录 + 游戏内登录
├── game_launcher.py         # 云游戏启动
├── navigator.py             # OpenCV 模板匹配 + CDP 点击
├── ui_state.py              # UI 状态分类器
├── ui_loop.py               # FSM 感知环（截图阶段主循环）
├── screenshot_click.py      # 点击守卫（弹窗避让 + 生效验证）
├── screenshotter.py         # 截图保存
├── popup_monitor.py         # 弹窗检测与关闭
├── capture_templates.py     # 模板图采集工具
├── click_confirm.py         # 两次确认点击（ROI 校验）
├── client_launcher.py       # 客户端启动器
├── calibrate_coords.py      # 坐标校准
├── test_core.py             # 核心功能测试
├── logger.py                # 日志模块
│
├── gui/
│   ├── app.py               # Tkinter 主应用（4 页面）
│   └── widgets/
│       ├── qr_display.py     # 二维码展示组件
│       └── log_view.py       # 日志视图组件
│
├── templates/                # 40+ 模板图（运行时匹配用）
├── screenshots/              # 截图输出目录（按账号分组）
├── logs/                     # 运行日志
│
├── .github/workflows/
│   └── build.yml             # GitHub Actions 自动构建
│
├── docs/superpowers/
│   ├── specs/                # 设计文档
│   └── plans/                # 实现计划
│
└── .superpowers/sdd/         # SDD 任务跟踪
    ├── progress.md           # 进度总账
    ├── task-N-brief.md       # 任务摘要
    ├── task-N-report.md      # 任务报告
    ├── task-N-review.md      # 任务审查
    └── final-review.md       # 最终集成验证
```

---

## 2. 开发工作流：SDD 规范驱动开发

### 2.1 总体流程

项目严格遵循 **Spec-Driven Development (SDD)** 方法论，每个功能走 6 个阶段：

```
 📝 Spec 设计  →  📋 Plan 计划  →  🔨 Task 实现  →  🔍 Review 审查  →  ✅ Final Review 集成验证
 (1 天)          (1 天)           (1-N 天)         (每个 Task)       (全部 Task 完成后)
```

### 2.2 阶段 1: Spec 设计文档

**文件位置:** `docs/superpowers/specs/YYYY-MM-DD-<feature>-design.md`

**内容结构:**
- 目标：要解决什么问题
- 背景：为什么需要这个功能
- 设计决策：技术选型与 tradeoff
- 接口定义：函数签名、参数、返回值
- 约束条件：不修改哪些模块、性能要求
- 风险与边界情况

**示例 — QQ 密码登录设计文档 (`2026-07-25-qq-password-login-design.md`):**
```
目标: 新增"QQ 密码登录（手动）"选项
  - 脚本打开浏览器
  - 用户手动完成登录
  - 点击"完成登录"按钮
  - 脚本验证并继续

全局约束:
  - 不修改 web_login() 函数
  - 不修改扫码登录流程
  - 不修改 game_launcher.py
  - 不修改阶段 2/3/4
```

### 2.3 阶段 2: Plan 实现计划

**文件位置:** `docs/superpowers/plans/YYYY-MM-DD-<feature>.md`

**内容结构:**
- 任务拆解（Task 1, Task 2, ...）
- 每个 Task 包含：
  - 修改的文件列表
  - 接口定义（消费/产出）
  - 详细步骤（checkbox 格式）
  - 预期测试结果

**示例 — QQ 密码登录实现计划:**

```
任务 1: login.py — 新增 manual_login() 函数
  文件: C:\Automatic-screenshot\login.py
  接口: manual_login(driver, on_status, ready_event, timeout) -> bool
  步骤:
    - [ ] 运行现有测试确认基线（97 项通过）
    - [ ] 在 web_login() 函数之后插入 manual_login()
    - [ ] 4 种检测方法：登录弹窗 / Cookie / JS / CSS
    - [ ] 支持 ready_event 跨线程同步
    - [ ] 提交 (commit message 格式匹配计划)

  任务 2: gui/app.py — 集成 QQ 密码登录 UI
  文件: C:\Automatic-screenshot\gui\app.py
  步骤:
    - [ ] 新增 radio 按钮"QQ 密码登录（手动）"
    - [ ] 新增"完成登录"按钮
    - [ ] threading.Event 跨线程信号
    - [ ] _run_workflow 新增 qq_password 分支
    - [ ] 提交
```

### 2.4 阶段 3: Task 实现

**文件位置:** `.superpowers/sdd/task-N-brief.md` （任务摘要）
**工具链:** Agent 子代理执行，每个 Task 独立提交

**执行流程:**
1. **任务摘要** (`.superpowers/sdd/task-N-brief.md`) — 从 Plan 提取单 Task 步骤
2. **代码实现** — 在隔离工作树中编写代码
3. **运行测试** — `python -m pytest test_core.py -q`
4. **提交** — commit message 匹配 Plan 中的描述
5. **任务报告** (`.superpowers/sdd/task-N-report.md`) — 记录 commit hash、测试结果、改动范围

**任务报告结构:**
```markdown
# Task N Report: <标题>

## Status: DONE

## Commits Made
- commit_hash: 描述

## Changes
- 具体改动内容

### Test Results
- pytest 结果 (e.g., "97 passed in 1.09s")

## Concerns
- 无 / 有（列出潜在问题）
```

### 2.5 阶段 4: Task Review

**文件位置:** `.superpowers/sdd/task-N-review.md`

**审查三要素:**

| 维度 | 检查内容 |
|------|----------|
| **Spec Compliance** | 逐条对照 Plan 需求，用表格 ✅/❌ 检查 |
| **Code Quality** | Important Issues / Minor Issues 分级 |
| **Verdict** | `Approved` 或 `Changes Requested` |

**Spec Compliance 检查表示例:**
```markdown
| Requirement | Status | Evidence |
|-------------|--------|----------|
| 函数签名匹配 Plan | ✅ | login.py:342-347 完全一致 |
| 4 种检测方法 | ✅ | 弹窗/Cookie/JS/CSS 全部实现 |
| 不修改 web_login() | ✅ | web_login() 内部无任何改动 |
| 97 项测试无回归 | ✅ | 确认通过 |
```

**Code Quality 分级:**
- **Important Issues**: 必须修复的 bug、逻辑错误、线程安全问题
- **Minor Issues**: 代码风格、静默异常、缺失日志（可接受）

### 2.6 阶段 5: Final Review 集成验证

**文件位置:** `.superpowers/sdd/final-review.md`

**检查维度:**

1. **Integration Check (集成检查)**
   - Import 链完整性
   - 事件/回调连线
   - 跨文件数据流
   - 状态机一致性

2. **Regression Safety (回归安全)**
   - 已有流程无改动
   - 仅新增代码，零删除/重排序
   - 测试全量通过

3. **Thread Safety (线程安全)**
   - threading.Event 生命周期
   - queue.Queue 消息类型完整性
   - Daemon 线程生命周期
   - Driver 所有权与关闭顺序

4. **Edge Cases (边界情况)**
   - 表格形式列出所有边界情景
   - 每个情景标注：行为 → 评估 (Safe/Minor UX gap/Clean)
   - 示例：用户关闭浏览器 → silent 10 分钟 timeout → Minor UX gap

5. **Minor Findings Triage (遗留问题分类)**
   - 表格列出所有 Minor Finding
   - 每个标注：Severity / Fix Required? / 原因

6. **Verdict**
   - `Ready to Merge` / `Needs Fixes`
   - 可选修复建议（不阻塞合并）

### 2.7 进度总账

**文件位置:** `.superpowers/sdd/progress.md`

记录所有 Plan 的完成状态，格式：
```markdown
Plan: docs/superpowers/plans/<plan-file>.md
Worktree: in-place

Task 1: complete (commits xxx..yyy, review Approved; findings...)
Task 2: complete (commits yyy..zzz, review Approved; findings...)
Final review: Ready / Needs Fixes
```

### 2.8 审查规范

| 规则 | 说明 |
|------|------|
| 不自动提交 | 用户规则：所有提交由用户手动执行 |
| 审查用工作树 diff | 使用 `git diff` 范围而非工作目录文件 |
| 每个 Task 独立提交 | 一个 Task 一个 commit，便于审查和回滚 |
| 审查意见不阻塞时可 Approve | Minor 问题记录但不阻塞合并 |

---

## 3. 运行时工作流：App 截图执行流程

### 3.1 GUI 四页面对话

```
┌────────────────────────────────────────────────────────────────┐
│                     王者荣耀云游戏自动截图                        │
├────────────────────────────────────────────────────────────────┤
│                                                                │
│  Page 1: 待命页 (idle)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  腾讯先锋平台: [QQ iOS] [微信 iOS] [QQ 安卓] [微信 安卓]    │   │
│  │  登录方式:     [QQ 扫码] [微信扫码] [QQ 密码登录（手动）]    │   │
│  │  游戏账号:     [________________]                          │   │
│  │                      [开始截图]                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  Page 2: 扫码页 (qr)                                            │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              腾讯先锋 QQ 登录                               │   │
│  │         ┌─────────────────────┐                           │   │
│  │         │                     │                           │   │
│  │         │   二维码图片区域      │                           │   │
│  │         │                     │                           │   │
│  │         └─────────────────────┘                           │   │
│  │           ⏳ 请扫描下方二维码                                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  Page 3: 进度页 (progress)                                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  启动任务...                                               │   │
│  │  ✅ 浏览器已打开                                           │   │
│  │  ✅ 腾讯先锋登录成功                                        │   │
│  │  状态=main 动作=click_step 任务[1/18] 主页                  │   │
│  │    已截图: 主页                                            │   │
│  │  状态=on_path 动作=click_step 任务[3/18] 万象图鉴首页        │   │
│  │  ...                                                      │   │
│  │  进度条: [████████████░░░░░░░░] 3/18                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                │
│  Page 4: 完成页 (done)                                          │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │  ✅ 本轮完成: 18/18 张截图                                  │   │
│  │  已退出游戏登录                                            │   │
│  │                                                            │   │
│  │  下一轮登录方式: [QQ 扫码] [微信扫码]                        │   │
│  │  下一轮账号:     [________________]                        │   │
│  │  下一轮平台:     [QQ iOS] [微信 iOS] ...                    │   │
│  │          [确认执行下一轮]                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────┘
```

### 3.2 后台工作流四阶段

`gui/app.py:_run_workflow()` 在后台线程执行完整流程：

```
┌─────────────────────────────────────────────────────────────────────┐
│                         _run_workflow()                              │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段 1: 腾讯先锋平台登录                                       │   │
│  │                                                               │   │
│  │  if qq_password:                                              │   │
│  │    ┌──────────────────────────────────────────────────────┐  │   │
│  │    │  create_browser() → 打开 Edge                         │  │   │
│  │    │  manual_login(driver, on_status, ready_event)         │  │   │
│  │    │    ├─ driver.get("gamer.qq.com")                      │  │   │
│  │    │    ├─ 不点任何登录按钮，不做 iframe 切换                │  │   │
│  │    │    ├─ 轮询 4 种检测（每 2s）：                          │  │   │
│  │    │    │   ① 登录弹窗消失 (ID "user_login")                │  │   │
│  │    │    │   ② Cookie 检测 (p_uin/p_skey/pt2gguin/uin/skey) │  │   │
│  │    │    │   ③ JS 注入检测 (cookie + DOM 类选择器)           │  │   │
│  │    │    │   ④ CSS 选择器检测 (9 种 user 元素)               │  │   │
│  │    │    ├─ ready_event 跨线程信号（GUI "完成登录" 按钮）      │  │   │
│  │    │    └─ 超时 600s 返回 False                             │  │   │
│  │    └──────────────────────────────────────────────────────┘  │   │
│  │                                                                │   │
│  │  else (扫码登录):                                              │   │
│  │    ┌──────────────────────────────────────────────────────┐  │   │
│  │    │  create_browser() → 打开 Edge                         │  │   │
│  │    │  web_login(driver, login_type, on_qr, on_status)      │  │   │
│  │    │    ├─ driver.get("gamer.qq.com")                      │  │   │
│  │    │    ├─ 点击 QQ/微信 登录按钮，切换到对应 iframe          │  │   │
│  │    │    ├─ 截取二维码 → on_qr(image) → GUI 展示             │  │   │
│  │    │    ├─ 轮询 4 种检测（同上）                             │  │   │
│  │    │    └─ 超时 300s 返回 False                             │  │   │
│  │    └──────────────────────────────────────────────────────┘  │   │
│  │  输出: self._platform_logged_in = True                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段 2: 启动游戏                                              │   │
│  │                                                               │   │
│  │  launch_game(driver)                                          │   │
│  │    ├─ 在 gamer.qq.com 搜索"王者荣耀"                           │   │
│  │    ├─ 点击"秒玩"按钮                                           │   │
│  │    ├─ 等待云游戏标签页打开                                      │   │
│  │    └─ switch_to 云游戏标签页                                    │   │
│  │                                                               │   │
│  │  Navigator(driver, templates_dir) 初始化                      │   │
│  │                                                               │   │
│  │  粗清初始弹窗:                                                │   │
│  │    ├─ sleep(10)                                               │   │
│  │    ├─ click_css(viewport_width/2, viewport_height*0.85)      │   │
│  │    └─ "已尝试清除弹窗"                                         │   │
│  │                                                               │   │
│  │  run_pre_logout_loop() — 预退出感知环                         │   │
│  │    ├─ 每 2s 截一帧 (tick_s=2.0，刻意少截屏防 tab crash)       │   │
│  │    ├─ 弹窗优先: 检测 X 关闭/确认 → 关闭                        │   │
│  │    ├─ 检测退出按钮 (game_logout_btn.png) → 点击                │   │
│  │    ├─ 检测确认弹窗 → 点击确定                                  │   │
│  │    ├─ 已在平台选择页 → 立即关环 ready_for_platform=True       │   │
│  │    ├─ timeout=30s → timed_out=True                           │   │
│  │    └─ 返回 PreLogoutResult(logout_clicked, confirm_clicked)  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段 3: 游戏内登录 + 截图                                      │   │
│  │                                                               │   │
│  │  game_login(nav, platform, on_qr, on_status)                 │   │
│  │    ├─ 最多重试 3 次 (GAME_LOGIN_MAX_RETRIES=3)               │   │
│  │    │                                                          │   │
│  │    ├─ 1. 检测 enter_game → 直接跳过 (已在游戏中)               │   │
│  │    │                                                          │   │
│  │    ├─ 2. 感知环清弹窗 (close_perception_popup × 3)            │   │
│  │    │                                                          │   │
│  │    ├─ 3. 点击平台登录按钮 (template matching)                  │   │
│  │    │    bounds: platform_select_bounds(vw, vh, platform)     │   │
│  │    │    失败 → 检测退出按钮 → 执行预退出 → 重试               │   │
│  │    │                                                          │   │
│  │    ├─ 4. 点击 game_auth_login_1.png（授权登录按钮 1）         │   │
│  │    │    bounds: 下半屏                                        │   │
│  │    │                                                          │   │
│  │    ├─ 5. 点击 game_auth_login_2.png（授权登录按钮 2）         │   │
│  │    │    bounds: 下半屏                                        │   │
│  │    │                                                          │   │
│  │    └─ 6. 点击 enter_game.png（进入游戏）                       │   │
│  │                                                               │   │
│  │  登录成功后的清理:                                             │   │
│  │    ├─ sleep(10)                                               │   │
│  │    ├─ 返回箭头循环清理 (while find_and_click back_arrow)      │   │
│  │    ├─ PopupMonitor.close_all_popups() × 2                    │   │
│  │    └─ wait_for_template("avatar.png") → 确认进入主界面        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 阶段 4: 感知环截图                                            │   │
│  │                                                               │   │
│  │  UiLoop(nav, shot, screenshot_tasks, stop_event, ...)        │   │
│  │                                                               │   │
│  │  screenshot_tasks = [                                         │   │
│  │    ("主页",              [(coords: 头像, tab_home)],      0),  │   │
│  │    ("英雄",              [(tab_hero)],                    0),  │   │
│  │    ("万象图鉴首页",       [(tab_illustrated, universal)],  0),  │   │
│  │    ("万象图鉴-灵宝",      [(lingbao)],                     1),  │   │
│  │    ("按键",              [(in_game_btn, keybind_btn)],    1),  │   │
│  │    ("天幕",              [(tianmu)],                       1),  │   │
│  │    ("星典藏",            [(xingyuan, xing_collection)],   0),  │   │
│  │    ("星传说",            [(xing_legend)],                  1),  │   │
│  │    ("皮肤图鉴",          [(skin_illustrated)],             0),  │   │
│  │    ("珍品无双",          [(skin_treasure_wushuang)],       1),  │   │
│  │    ("荣耀典藏",          [(skin_glory_collection)],        1),  │   │
│  │    ("无双",              [(skin_wushuang)],                1),  │   │
│  │    ("珍品传说",          [(skin_treasure_legend)],         1),  │   │
│  │    ("传说",              [(skin_legend)],                  2),  │   │
│  │    ("积分夺宝",          [(shop, lottery, points)],       2),  │   │
│  │    ("货币背包",          [(bag, currency_bag)],            2),  │   │
│  │    ("小兵",              [(customize, skin, coords:n),    1),  │   │
│  │    ("个性戳戳",          [(customize, personal, poke)],   1),  │   │
│  │    ("贵族",              [(nobility_icon)],                1),  │   │
│  │  ]                                                           │   │
│  │                                                               │   │
│  │  每轮 tick (0.5s):                                            │   │
│  │    ┌──────────────────────────────────────────────────────┐  │   │
│  │    │  classify(nav, path_templates) → UiState              │  │   │
│  │    │    ├─ POPUP:   弹窗检测 → CLOSE_POPUP                  │  │   │
│  │    │    ├─ CONFIRM: 确认弹窗 → CLOSE_POPUP                  │  │   │
│  │    │    ├─ LOGIN:   登录页   → RELOGIN                      │  │   │
│  │    │    ├─ MAIN:    主界面   → CLICK_STEP (有剩余点击)       │  │   │
│  │    │    ├─ ON_PATH: 路径入口  → CLICK_STEP                  │  │   │
│  │    │    └─ UNKNOWN: 未知     → WAIT / RECOVER (超时 45s)   │  │   │
│  │    │                                                        │  │   │
│  │    │  decide(state, goal) → Action                         │  │   │
│  │    └──────────────────────────────────────────────────────┘  │   │
│  │                                                               │   │
│  │  点击前守卫 (_ensure_clear_for_click):                        │   │
│  │    └─ 再截一帧 → 有弹窗则关闭，取消本轮主线点击               │   │
│  │                                                               │   │
│  │  点击生效验证 (effect_verify):                                 │   │
│  │    └─ 点击后等下一步模板出现，最多重试 CLICK_EFFECT_RETRIES+1  │   │
│  │                                                               │   │
│  │  返回生效校验 (_do_back):                                      │   │
│  │    ├─ 返回前弹窗守卫                                          │   │
│  │    ├─ 点击 back_arrow                                         │   │
│  │    ├─ 弹窗排空 (_drain_popups_briefly)                        │   │
│  │    ├─ 用下一任务入口模板做生效校验                              │   │
│  │    └─ 失败 → rewind_to_previous_step() + recover 重试        │   │
│  │                                                               │   │
│  │  RECOVER 恢复策略:                                            │   │
│  │    ├─ 先检测 avatar.png (60s) → 已在主界面                    │   │
│  │    ├─ 检测平台登录模板 → re-login                              │   │
│  │    └─ 超时 60s → 失败                                         │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                              │                                      │
│                              ▼                                      │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │ 清理: 退出登录                                               │   │
│  │                                                               │   │
│  │  for attempt in 1..3:                                        │   │
│  │    ├─ find_and_click("settings_icon.png")                    │   │
│  │    ├─ sleep(2)                                               │   │
│  │    ├─ find_and_click("settings_logout.png")                  │   │
│  │    ├─ click_confirm_dialog(nav)                              │   │
│  │    └─ break                                                  │   │
│  │                                                               │   │
│  │  PopupMonitor.close_all_popups() × 2 清理残留弹窗            │   │
│  │                                                               │   │
│  │  send({"type": "done", "text": "✅ 本轮完成: N/18 张截图"})   │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.3 FSM 感知环决策表

`ui_loop.py:decide()` 函数实现 (UiState, Goal) → Action 映射：

| UiState | Goal 状态 | Action | 说明 |
|---------|-----------|--------|------|
| POPUP | 任意 | CLOSE_POPUP | 弹窗优先关闭 |
| CONFIRM | 任意 | CLOSE_POPUP | 确认弹窗优先关闭 |
| LOGIN | 任意 | RELOGIN | 重新登录 |
| MAIN | phase_need_click() | CLICK_STEP | 可导航，执行点击 |
| ON_PATH | phase_need_click() | CLICK_STEP | 路径入口可见，执行点击 |
| MAIN/ON_PATH | phase_need_shot() | TAKE_SHOT | 点击完成，执行截图 |
| MAIN/ON_PATH | phase_need_back() | GO_BACK | 截图完成，执行返回 |
| UNKNOWN | phase_need_shot/back | TAKE_SHOT/GO_BACK | 内容子页允许未知状态 |
| UNKNOWN | phase_need_click | WAIT/RECOVER | 超时 45s 触发恢复 |
| 任意 | done | FINISHED | 全部任务完成 |

### 3.4 Goal 游标状态机

```
Goal 对象追踪每个截图任务的进度:

  Task["主页", clicks=[头像, tab_home], back_count=0]
      │
      ├── click_index=0: 点击坐标(头像) ──等 effect_verify──→ click_index=1
      ├── click_index=1: 点击 tab_home ──等 effect_verify──→ click_index=2
      │
      ├── phase_need_shot(): ✓ 截图 → mark_shot_done()
      │
      ├── phase_need_back(): back_count=0 → _next_task()
      │
      ▼
  Task["英雄", clicks=[tab_hero], back_count=0]
      │
      └── ... 同上 ...

  回退机制 (rewind_to_previous_step):
    - 已截图/待返回 → 重置到本任务最后一次点击
    - 仍有前置点击 → click_index -= 1
    - 已在第一步 → task_index -= 1 (回到上一任务)
```

### 3.5 跨线程通信机制

```
┌─────────────────────────────────┐     ┌──────────────────────────────┐
│      后台 Worker 线程            │     │        GUI 主线程              │
│      (daemon=True)              │     │                              │
│                                 │     │                              │
│  queue.Queue (线程安全)          │     │  _poll_queue() 每 100ms 轮询  │
│  ┌───────────────────────────┐  │     │  ┌────────────────────────┐   │
│  │ type: "log"               │──┼──►──┼──│ LogView.add_log()      │   │
│  │ type: "qr"                │──┼──►──┼──│ QRDisplay.show_qr()    │   │
│  │ type: "scan_wait"         │──┼──►──┼──│ QRDisplay 无二维码提示   │   │
│  │ type: "qr_status"         │──┼──►──┼──│ QRDisplay.update_status│   │
│  │ type: "progress"          │──┼──►──┼──│ LogView.update_progress│   │
│  │ type: "show_manual_btn"   │──┼──►──┼──│ pack() 手动登录按钮      │   │
│  │ type: "hide_manual_btn"   │──┼──►──┼──│ pack_forget() 隐藏      │   │
│  │ type: "page"              │──┼──►──┼──│ _show_page() 页面切换    │   │
│  │ type: "done"              │──┼──►──┼──│ _on_done() 完成处理      │   │
│  └───────────────────────────┘  │     │  └────────────────────────┘   │
│                                 │     │                              │
│  threading.Event (线程安全)      │     │                              │
│  ┌───────────────────────────┐  │     │  ┌────────────────────────┐   │
│  │ _manual_login_event       │◄──┼─────┼─│ _on_manual_login_done()│   │
│  │ (后台轮询检查)              │  │     │  │ (用户点击 "完成登录"     │   │
│  │ manual_login() polling    │  │     │  │  → event.set())        │   │
│  └───────────────────────────┘  │     │  └────────────────────────┘   │
│                                 │     │                              │
│  Stop Event                     │     │                              │
│  ┌───────────────────────────┐  │     │  ┌────────────────────────┐   │
│  │ _stop_event.is_set()      │◄──┼─────┼─│ _on_close()            │   │
│  │ (各阶段循环检查)             │  │     │  │ (关闭窗口 → set + join) │   │
│  └───────────────────────────┘  │     │  └────────────────────────┘   │
└─────────────────────────────────┘     └──────────────────────────────┘
```

---

## 4. CI/CD 构建工作流

### 4.1 触发条件

```yaml
# .github/workflows/build.yml
on:
  push:
    branches: [main]
  workflow_dispatch:  # 手动触发
```

### 4.2 构建流程

```
push to main / 手动触发
    │
    ▼
┌──────────────────────────────────────────────────────┐
│  windows-latest runner                               │
│                                                      │
│  1. actions/checkout@v4    → 检出代码                  │
│                                                      │
│  2. actions/setup-python@v5 → Python 3.12            │
│                                                      │
│  3. pip install 依赖                                  │
│     ├─ -r requirements.txt                           │
│     └─ pyinstaller                                   │
│                                                      │
│  4. PyInstaller 打包                                  │
│     pyinstaller --onefile --windowed                 │
│       --name AutoScreenshot                          │
│       --hidden-import tkinter tkinter.ttk            │
│       --hidden-import cv2 cv2._core                  │
│       --collect-all cv2                              │
│       --hidden-import numpy numpy._core              │
│       --hidden-import PIL PIL.Image PIL.ImageTk      │
│       --hidden-import selenium + webdriver_manager   │
│       --collect-all selenium                         │
│       --add-data "templates;templates"               │
│       --add-data "calibrated_coords.json;."          │
│       main.py                                        │
│                                                      │
│  5. 验证 dist/AutoScreenshot.exe 存在                 │
│                                                      │
│  6. actions/upload-artifact@v4                       │
│     └─ 保留 90 天                                     │
│                                                      │
│  7. softprops/action-gh-release@v2                   │
│     ├─ tag: nightly                                  │
│     ├─ name: "Nightly Build"                         │
│     └─ prerelease: true                              │
└──────────────────────────────────────────────────────┘
```

### 4.3 打包特性

| 特性 | 说明 |
|------|------|
| `--onefile` | 单个 EXE 文件，方便分发 |
| `--windowed` | 无控制台窗口（后台运行时不显示 cmd） |
| `--add-data` | 内嵌 templates/ 和 calibrated_coords.json |
| hidden-imports | 显式声明所有隐式依赖（cv2, numpy, selenium 等） |
| prerelease | Nightly Build 标记为预发布版本 |

---

## 5. 关键模块详解

### 5.1 Navigator（导航器）

**文件:** `navigator.py`

核心能力：
- `capture_viewport_bgr()`: CDP 截取视口为 BGR (JPEG quality=70，减负云游戏 tab)
- `find_and_click(template, bounds, threshold)`: 模板匹配 → CDP 鼠标事件注入点击
- `wait_for_template(template, timeout)`: 轮询等待模板出现（不点击）
- `_load_template()`: 模板缓存 + `np.fromfile` 路径兼容（中文路径安全）
- `click_css(x, y)`: CDP `Input.dispatchMouseEvent` 三步点击（moved → pressed → released）
- `grab_roi(x, y, w, h)`: 截取视口后裁切 ROI

**模板匹配流水线:**
```
1. _load_template(template_name)
   └─ 缓存命中 → 直接返回
   └─ 缓存未命中 → np.fromfile(path) → cv2.imdecode → 缓存

2. for attempt in 1..max_retries:
     _get_screenshot() → CDP captureScreenshot (JPEG)
     └─ bounds? → 裁切 search_area
     └─ cv2.matchTemplate(search_area, template, TM_CCOEFF_NORMED)
        └─ max_val >= threshold → click_css(center_x, center_y) → return True
        └─ sleep(RETRY_INTERVAL) → 重试

3. allow_fallback? → 读取 calibrated_coords.json 兜底坐标点击
```

### 5.2 UiState 分类器

**文件:** `ui_state.py`

**优先级判定链:**
```
截取一帧画面
  │
  ├─ 1. 弹窗 X 关闭 (popup_close / popup_close_small)
  │      bounds: 右上半屏, threshold=0.78
  │      → UiState.POPUP
  │
  ├─ 2. 确认弹窗 (game_popup_confirm / game_logout_confirm)
  │      bounds: 下半屏, threshold=0.60
  │      → UiState.POPUP (默认) / CONFIRM (allow_confirm=True)
  │
  ├─ 3. 登录页 (game_{wx,qq}_{ios,android})
  │      threshold=0.80
  │      且 avatar < MAIN_THRESHOLD（避免大厅误匹配）
  │      → UiState.LOGIN
  │
  ├─ 4. 路径入口 (path_templates 中任意模板)
  │      threshold=0.53
  │      → UiState.ON_PATH
  │
  ├─ 5. 主界面 (avatar)
  │      bounds: 左上 40%×50%, threshold=0.53
  │      → UiState.MAIN
  │
  └─ 6. 都不满足
        → UiState.UNKNOWN
```

### 5.3 两次确认点击体系

**文件:** `click_confirm.py` + `screenshot_click.py`

每次点击执行两步确认：

```
Pass 1: 定位 → 计划 (Plan)
  ├─ 模板匹配 → 找到位置 (x, y, score)
  └─ 生成 ClickPlan(x, y, expected_roi_area, description)

Pass 2: ROI 校验 → 派发 (Execute)
  ├─ 截取点击位置周围 ROI
  ├─ 与模板尺寸比对 (area 偏差 < 50%)
  ├─ ROI 中心色差检查
  └─ 校验通过 → CDP dispatchMouseEvent 三部曲
     校验失败 → 跳过（"ROI 未确认"）
```

**点击生效验证 (effect_verify):**
```
点击完成
  ├─ 无下一步? → 直接 advance (最后一击不需要验证)
  ├─ 下一步是普通模板 → wait_for_template(next_template, timeout=5s)
  │   ├─ 出现 → advance_after_click()
  │   └─ 未出现 → 重试 (最多 CLICK_EFFECT_RETRIES+1 次)
  └─ 下一步是坐标点击 → 等 anchor 模板出现
```

---

## 6. 模板图管理体系

### 6.1 模板图分类

| 分类 | 模板文件 | 数量 |
|------|----------|------|
| 登录界面 | `game_wx_ios/android`, `game_qq_ios/android`, `game_auth_login_1/2`, `enter_game`, `game_logout_btn/confirm`, `game_popup_confirm` | 11 |
| 弹窗 | `popup_close`, `popup_close_small` | 2 |
| 主界面 | `avatar`, `shop_icon`, `customize_icon`, `nobility_icon`, `game_main`, `back_arrow`, `settings_icon` | 7 |
| 个人主页 | `tab_home`, `tab_hero`, `tab_illustrated` | 3 |
| 图鉴 | `universal_illustrated`, `lingbao`, `in_game_btn`, `keybind_btn`, `tianmu`, `xingyuan`, `xing_collection`, `xing_legend`, `skin_illustrated`, `skin_treasure_wushuang`, `skin_glory_collection`, `skin_wushuang`, `skin_treasure_legend`, `skin_legend` | 14 |
| 背包 | `bag`, `currency_bag` | 2 |
| 商城 | `lottery_tab`, `points_lottery` | 2 |
| 定制 | `skin_customize`, `my_tab`, `minion`, `personal_customize`, `poke` | 5 |
| 设置 | `settings_logout` | 1 |
| 可选 | `honor_of_kings` | 1 |
| **总计** | | **47** |

### 6.2 模板图采集

**工具:** `capture_templates.py`

```bash
# 采集全部 47 个模板（交互式，逐个确认）
python capture_templates.py

# 只采集指定模板
python capture_templates.py --only tianmu.png xingyuan.png

# 强制重截全部
python capture_templates.py --all

# 从指定位置开始
python capture_templates.py --from 10
python capture_templates.py --from popup_close.png
```

**采集流程:**
1. 启动浏览器 → 登录腾讯先锋 → 手动进入对应游戏页面
2. 脚本自动切换到云游戏标签页（URL 含 `/v2/game/`）
3. 视口截图 → 拖拽框选 ROI → 预览裁剪结果
4. 确认保存 / 重截 / 跳过 / 退出

---

## 7. 反检测体系

### 7.1 CDP 预注入

**文件:** `browser.py` — `PRELOAD_SCRIPT`

在页面加载前通过 `Page.addScriptToEvaluateOnNewDocument` 注入：

```javascript
// 1. 隐藏 navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });

// 2. 伪造 plugins 数组
Object.defineProperty(navigator, 'plugins', { get: () => [Chrome PDF Plugin, ...] });

// 3. 伪造 mimeTypes
Object.defineProperty(navigator, 'mimeTypes', { get: () => [application/pdf, ...] });

// 4. 移除 chrome 对象自动化标记
// 5. 伪造 permissions API
// 6. 伪造 languages
```

### 7.2 浏览器启动参数

Edge/Chrome 启动参数：
```python
--disable-blink-features=AutomationControlled
--disable-infobars
--no-sandbox
--disable-dev-shm-usage
--disable-gpu
--disable-setuid-sandbox
--disable-extensions
--disable-logging
--log-level=3
--silent
--disable-default-apps
--disable-component-update
--disable-background-networking
--disable-sync
--disable-translate
--mute-audio
--force-device-scale-factor=1
--use-gl=angle / --use-angle=swiftshader
--use-angle=d3d9 / --disable-features=VizDisplayCompositor
```

### 7.3 反检测注入时机

```
Edge:
  _inject_anti_detect(driver)        ← 页面级注入（frame context）
    → lock_viewport(driver)          ← 锁定 CSS 视口 1920×1080

Chrome:
  Page.addScriptToEvaluateOnNewDocument  ← 全局预注入
  _inject_anti_detect(driver)            ← 页面级注入
    → lock_viewport(driver)
```

### 7.4 CDP 点击优势

所有点击操作通过 CDP `Input.dispatchMouseEvent` 而非 Selenium `click()`：
- 不触发系统级鼠标移动（减少检测风险）
- 直接操作渲染层的输入事件
- 跨 iframe 边界无感

---

## 8. 线程安全与跨线程通信

### 8.1 线程模型

```
┌──────────────────────────────────────────────────────────┐
│  main.py: 主进程                                          │
│                                                          │
│  ┌──────────────────┐    ┌─────────────────────────────┐ │
│  │  GUI 主线程        │    │  Worker 后台线程 (daemon)     │ │
│  │                    │    │                             │ │
│  │  - Tk mainloop     │    │  - _run_workflow()         │ │
│  │  - _poll_queue     │◄───│  - Selenium WebDriver 操作  │ │
│  │    (每 100ms)      │Queue│  - OpenCV 模板匹配          │ │
│  │  - UI 更新          │    │  - 截图保存                 │ │
│  │                    │    │                             │ │
│  │  - 用户交互         │    │  - 检查 _stop_event        │ │
│  │    └─ Event.set() ──┼───►│  - 检查 _manual_login_event│ │
│  └──────────────────┘    └─────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

### 8.2 线程安全规则

| 规则 | 说明 |
|------|------|
| 主线程锁定 Tk 变量 | `_on_start()` 中将 `_login_type`, `_platform_var` 等复制到实例属性 |
| 后台线程不触碰 Tk | 通过 `queue.Queue` 发送消息给主线程更新 UI |
| Daemon 线程 | Worker 线程设 `daemon=True`，窗口关闭时不阻塞进程退出 |
| Stop Event | `_on_close()` 设 `_stop_event` → 各阶段循环 `is_set()` 检查 |
| Driver 所有权 | 后台线程创建，`_on_close()` quit（最多 join 3s） |
| 模板缓存隔离 | Navigator 实例化后不跨线程共享 |

---

## 9. 开发历史与功能演进

| 日期 | 功能 | 关键提交 |
|------|------|----------|
| 07-07 | 王者荣耀自动截图（初始功能） | 基础 FSM 导航 + 截图 |
| 07-08 | GUI 登录界面 | Tkinter 4 页面对话框 |
| 07-13 | Windows EXE 打包修复 | PyInstaller `--windowed` + hidden-imports |
| 07-16 | 坐标回退机制 | `calibrated_coords.json` 兜底点击 |
| 07-17 | 弹窗监控 / Selenium 点击 / 预登录 | `popup_monitor.py` + `click_confirm.py` |
| 07-18 | GUI 二维码展示 | `gui/widgets/qr_display.py` |
| 07-20 | 轻量级 FSM 感知循环 | `ui_loop.py` + `ui_state.py` 替代大 FSM |
| 07-21 | 安吉拉截图任务 / 两次确认点击 | `screenshot_click.py` + ROI 校验 |
| 07-23 | 退出前感知循环 | `run_pre_logout_loop()` |
| 07-25 | 返回箭头清理 + QQ 密码登录 + 游戏登录授权流程 | 清理循环 + `manual_login()` + `game_auth_login_1/2` |
| 07-25 | 反检测强化 | CDP 点击替代系统光标、JS 注入、DrissionPage 评估 |
| 07-25 | `game_login` 授权登录流 | QR 扫码流 → 授权登录按钮流 (`game_auth_login_1→2→enter`) |
