"""进程清理模块：确保浏览器驱动进程在任何退出方式下都被可靠清理。

三层保障：
  1. Windows Job Object — 内核级：Python 进程死亡时 OS 自动终止子进程
  2. 启动时孤儿清扫 — 上一次运行残留的 msedgedriver.exe
  3. 退出时三级降级清理 — quit → taskkill/PID → taskkill/IM
"""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess
import time
from ctypes import wintypes

from logger import get_logger

log = get_logger()

# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


def _run_hidden(args, **kwargs):
    """subprocess.run 包装：添加 CREATE_NO_WINDOW 防止弹窗闪烁。"""
    if platform.system() == "Windows":
        kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(args, **kwargs)


# ---------------------------------------------------------------------------
# 状态
# ---------------------------------------------------------------------------

_job_handle: int | None = None
_drivers: dict[int, dict] = {}  # driver_pid → {"driver": WebDriver, "browser_pids": [int, ...]}

# Win32 API 常量
_JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
_PROCESS_SET_QUOTA = 0x0100
_PROCESS_TERMINATE = 0x0001

# ---------------------------------------------------------------------------
# Windows Job Object (内核级保障)
# ---------------------------------------------------------------------------


def create_job_object() -> int | None:
    """创建 Windows Job Object，设置 KILL_ON_JOB_CLOSE。

    当创建该 Job 的进程（即 Python）死亡时，内核自动终止 Job 内所有进程。
    非 Windows 平台返回 None。多次调用幂等，复用已创建的 Job。
    """
    global _job_handle

    if _job_handle is not None:
        return _job_handle

    if platform.system() != "Windows":
        log.debug("非 Windows 平台，跳过 Job Object")
        return None

    # 定义必要的结构体
    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_ulonglong),
            ("PriorityClass", wintypes.DWORD),
            ("SchedulingClass", wintypes.DWORD),
        ]

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount", ctypes.c_uint64),
            ("WriteTransferCount", ctypes.c_uint64),
            ("OtherTransferCount", ctypes.c_uint64),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo", IO_COUNTERS),
            ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t),
            ("PeakProcessMemoryUsed", ctypes.c_size_t),
            ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.windll.kernel32

    # 创建 Job Object
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        err = ctypes.get_last_error()
        log.warning(f"CreateJobObject 失败 (错误码 {err})，回退到 atexit 清理")
        return None

    # 设置 KILL_ON_JOB_CLOSE
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    if not kernel32.SetInformationJobObject(
        wintypes.HANDLE(handle),
        wintypes.DWORD(_JOB_OBJECT_EXTENDED_LIMIT_INFORMATION),
        ctypes.byref(info),
        wintypes.DWORD(ctypes.sizeof(info)),
    ):
        err = ctypes.get_last_error()
        log.warning(f"SetInformationJobObject 失败 (错误码 {err})")
        kernel32.CloseHandle(wintypes.HANDLE(handle))
        return None

    _job_handle = handle
    log.info("Windows Job Object 已创建 (KILL_ON_JOB_CLOSE)")
    return handle


def assign_to_job(job_handle: int, pid: int) -> bool:
    """将指定 PID 的进程关联到 Job Object。

    Args:
        job_handle: create_job_object() 返回的句柄。
        pid: 目标进程 PID。

    Returns:
        bool: 成功返回 True。
    """
    if job_handle is None or pid <= 0:
        return False

    kernel32 = ctypes.windll.kernel32

    h_process = kernel32.OpenProcess(
        wintypes.DWORD(_PROCESS_SET_QUOTA | _PROCESS_TERMINATE),
        wintypes.BOOL(False),
        wintypes.DWORD(pid),
    )
    if not h_process:
        err = ctypes.get_last_error()
        log.debug(f"OpenProcess({pid}) 失败 (错误码 {err})")
        return False

    result = kernel32.AssignProcessToJobObject(
        wintypes.HANDLE(job_handle),
        wintypes.HANDLE(h_process),
    )
    kernel32.CloseHandle(wintypes.HANDLE(h_process))

    if not result:
        err = ctypes.get_last_error()
        log.debug(f"AssignProcessToJobObject({pid}) 失败 (错误码 {err})")
        return False

    log.debug(f"PID {pid} 已加入 Job Object")
    return True


# ---------------------------------------------------------------------------
# 子进程发现
# ---------------------------------------------------------------------------


def _find_direct_children(parent_pid: int) -> list[int]:
    """通过 WMIC 查找指定 PID 的直接子进程 PID。"""
    if platform.system() != "Windows":
        return []
    try:
        result = _run_hidden(
            [
                "wmic", "process", "where",
                f"ParentProcessId={parent_pid}",
                "get", "ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        pids: list[int] = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if text.isdigit():
                pids.append(int(text))
        return pids
    except Exception:
        log.debug(f"WMIC 查询子进程失败 (parent_pid={parent_pid})", exc_info=True)
        return []


def _find_all_descendant_pids(root_pid: int) -> list[int]:
    """递归查找指定 PID 的整个进程树（所有子孙进程）。

    Edge 进程树示例:
        msedgedriver.exe (root)
          ├── msedge.exe           ← 直接子进程
          │     ├── msedge.exe     ← 孙进程（渲染器）
          │     ├── msedge.exe     ← 孙进程（GPU）
          │     └── msedge.exe     ← 孙进程（网络）
          └── msedge.exe           ← 直接子进程

    仅查直接子进程会漏掉孙进程，导致退出时残留。

    Args:
        root_pid: 进程树的根 PID。

    Returns:
        list[int]: 整个进程树中所有 PID（含根自身）。
    """
    if platform.system() != "Windows":
        return [root_pid] if root_pid > 0 else []

    all_pids: set[int] = {root_pid}
    frontier = [root_pid]
    depth = 0
    max_depth = 10  # 安全上限，Edge 进程树通常 ≤4 层

    while frontier and depth < max_depth:
        next_frontier: list[int] = []
        for pid in frontier:
            children = _find_direct_children(pid)
            for child in children:
                if child not in all_pids:
                    all_pids.add(child)
                    next_frontier.append(child)
        frontier = next_frontier
        depth += 1

    result = list(all_pids)
    log.debug(f"进程树 root={root_pid}: {result} (深度={depth})")
    return result


# ---------------------------------------------------------------------------
# 注册 / 反注册
# ---------------------------------------------------------------------------


def register_driver(driver) -> None:
    """记录 WebDriver 进程信息，并将其整个进程树加入 Job Object。

    Args:
        driver: Selenium WebDriver 实例 (webdriver.Edge 或 webdriver.Chrome)。
    """
    try:
        driver_pid = driver.service.process.pid
    except Exception:
        log.warning("无法获取 driver 进程 PID，跳过注册")
        return

    if driver_pid is None or driver_pid <= 0:
        return

    # 等待子进程出现
    time.sleep(1.0)

    # 递归获取整个进程树（含孙进程——Edge 渲染/GPU/网络进程等）
    all_pids = _find_all_descendant_pids(driver_pid)
    log.info(
        f"注册 driver PID={driver_pid}, 进程树={all_pids}"
    )

    _drivers[driver_pid] = {
        "driver": driver,
        "all_pids": all_pids,
    }

    # 整个进程树加入 Job Object（内核级保障）
    job = _job_handle
    if job is not None:
        for pid in all_pids:
            assign_to_job(job, pid)


def unregister_driver(driver) -> None:
    """从追踪列表中移除 driver（quit 成功后调用）。

    Args:
        driver: Selenium WebDriver 实例。
    """
    if driver is None:
        return
    try:
        driver_pid = driver.service.process.pid
    except Exception:
        return
    removed = _drivers.pop(driver_pid, None)
    if removed is not None:
        log.debug(f"已取消注册 driver PID={driver_pid}")


# ---------------------------------------------------------------------------
# 启动时孤儿进程清扫
# ---------------------------------------------------------------------------


def cleanup_orphans() -> None:
    """启动时扫描并清理上一次运行可能残留的驱动和浏览器进程。

    两轮扫描：
      1. 找到所有孤儿 msedgedriver.exe → 杀整个进程树
      2. 找到所有父进程已死的孤儿 msedge.exe → 逐个强杀

    非 Windows 平台直接返回。失败静默忽略，不阻止程序启动。
    """
    if platform.system() != "Windows":
        return

    try:
        killed_any = False

        # ---- 第 1 轮：孤儿 msedgedriver.exe ----
        orphan_drivers = _all_pids_by_name("msedgedriver.exe")
        if orphan_drivers:
            log.info(f"发现孤儿 msedgedriver.exe: {orphan_drivers}")
            # 收集整个进程树再杀
            all_pids: set[int] = set(orphan_drivers)
            for pid in orphan_drivers:
                for tpid in _find_all_descendant_pids(pid):
                    all_pids.add(tpid)
            for pid in all_pids:
                _kill_pid(pid)
            killed_any = True

        # ---- 第 2 轮：孤儿 msedge.exe（递归查祖先，防止漏掉孙进程） ----
        # Edge 进程树可能有多层，只看直接父进程不够：
        #   msedge.exe A (父=dead msedgedriver) → 孤儿 ✓
        #   msedge.exe B (父=A, 仍存活)         → 未标记 ✗ → A 被杀后 B 残留
        # 解法：向上追溯祖先链，找不到活着的 msedgedriver.exe 就是孤儿。
        # 杀完一轮后重扫，直到没有新孤儿为止。
        live_drivers = set(_all_pids_by_name("msedgedriver.exe"))
        for _round in range(3):  # 最多 3 轮，Edge 进程树通常 ≤4 层
            all_edge = _all_pids_by_name("msedge.exe")
            orphan_edge: list[int] = []
            for pid in all_edge:
                # 追溯祖先链：向上最多 10 层
                ancestor = pid
                is_orphan = True
                for _depth in range(10):
                    ppid = _get_parent_pid(ancestor)
                    if ppid is None or ppid <= 0:
                        break  # 到达进程树根节点，无更多祖先
                    if ppid in live_drivers:
                        is_orphan = False  # 属于活着的 driver → 合法进程
                        break
                    if not _process_exists(ppid):
                        break  # 祖先已死 → 孤儿
                    ancestor = ppid
                if is_orphan:
                    orphan_edge.append(pid)

            if not orphan_edge:
                break

            log.info(f"发现孤儿 msedge.exe (第{_round + 1}轮): {orphan_edge}")
            for pid in orphan_edge:
                _kill_pid(pid)
            killed_any = True
            time.sleep(0.5)  # 等进程退出后再重扫

        if not killed_any:
            log.debug("启动扫描：未发现孤儿进程")
    except Exception:
        pass  # 清理失败不应阻止启动


# ---------------------------------------------------------------------------
# 三级降级清理
# ---------------------------------------------------------------------------


def _process_exists(pid: int) -> bool:
    """检查指定 PID 的进程是否存在（Windows）。"""
    if platform.system() != "Windows":
        return False
    kernel32 = ctypes.windll.kernel32
    SYNCHRONIZE = 0x100000
    h = kernel32.OpenProcess(
        wintypes.DWORD(SYNCHRONIZE), wintypes.BOOL(False), wintypes.DWORD(pid),
    )
    if h:
        kernel32.CloseHandle(wintypes.HANDLE(h))
        return True
    return False


def _all_pids_by_name(name: str) -> list[int]:
    """通过 WMIC 查找指定名称的所有进程 PID。"""
    if platform.system() != "Windows":
        return []
    try:
        result = _run_hidden(
            ["wmic", "process", "where", f"name='{name}'", "get", "ProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        pids: list[int] = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if text.isdigit():
                pids.append(int(text))
        return pids
    except Exception:
        return []


def _get_parent_pid(pid: int) -> int | None:
    """查询指定 PID 的父进程 PID。"""
    if platform.system() != "Windows":
        return None
    try:
        result = _run_hidden(
            ["wmic", "process", "where", f"ProcessId={pid}",
             "get", "ParentProcessId"],
            capture_output=True, text=True, timeout=10,
        )
        for line in result.stdout.splitlines():
            text = line.strip()
            if text.isdigit():
                return int(text)
        return None
    except Exception:
        return None


def _kill_pid(pid: int) -> bool:
    """按 PID 强杀进程。

    Args:
        pid: 目标进程 PID。

    Returns:
        bool: 成功返回 True。
    """
    if platform.system() != "Windows":
        try:
            os.kill(pid, 9)  # SIGKILL on macOS/Linux
            return True
        except Exception:
            return False

    try:
        result = _run_hidden(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _kill_by_name(name: str) -> bool:
    """按镜像名全局强杀（仅 Windows）。

    Args:
        name: 进程名，如 "msedgedriver.exe"。

    Returns:
        bool: 成功返回 True。
    """
    if platform.system() != "Windows":
        return False
    try:
        result = _run_hidden(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


def _quit_with_timeout(driver, timeout_s: float = 5.0) -> bool:
    """带超时的 driver.quit()。

    Selenium driver.quit() 发送 HTTP DELETE /session。如果 msedgedriver
    进程已挂起，请求可能阻塞 120s（Selenium 默认超时），导致整个清理流程卡死。
    用线程包装，超时后直接放弃 Level 1，进入 Level 2 强杀。

    Returns:
        True: quit 成功完成
        False: 超时或异常
    """
    import threading

    result: dict = {"done": False, "error": None}

    def _do_quit():
        try:
            driver.quit()
            result["done"] = True
        except Exception as e:
            result["error"] = e

    t = threading.Thread(target=_do_quit, daemon=True)
    t.start()
    t.join(timeout=timeout_s)

    if t.is_alive():
        log.warning(f"driver.quit() 超时 ({timeout_s}s)，放弃优雅退出，进入强杀")
        return False
    if result["error"] is not None:
        log.debug(f"driver.quit() 异常: {result['error']}")
        return False
    return result["done"]


def _force_kill(driver_pid: int, info: dict) -> None:
    """对单个 driver 执行三级降级清理。

    Level 1: driver.quit() (优雅退出) → 验证进程是否真正退出
    Level 2: 实时扫描整个进程树 → taskkill /F /PID (精确强杀所有子孙)
    Level 3: taskkill /F /IM msedgedriver.exe + msedge.exe (全局兜底)
    """
    driver = info.get("driver")

    # Level 1: 优雅退出，然后验证进程是否真正终止
    if driver is not None:
        _quit_with_timeout(driver, timeout_s=5.0)

        # 关键：quit() 返回只说明命令已发送，窗口可能已关，
        # 但进程可能还活着（卡在 GPU/网络/IO）。验证进程树是否真的死了。
        time.sleep(1)
        if driver_pid is not None and driver_pid > 0:
            survivors = _find_all_descendant_pids(driver_pid)
            alive = [p for p in survivors if p != driver_pid]
            if not alive and not _process_exists(driver_pid):
                log.debug("Level 1 完成，进程已全部退出")
                return
            log.warning(
                f"quit 后仍有 {len(alive)} 个进程存活: {alive}，"
                f"进入 Level 2"
            )

    # Level 2: 重新扫描整个进程树并强杀
    # （不依赖注册时的快照——Edge 后续会不断创建新渲染进程）
    if driver_pid is not None and driver_pid > 0:
        all_pids = _find_all_descendant_pids(driver_pid)
        log.info(f"Level 2: 强杀进程树 root={driver_pid}, pids={all_pids}")
        for pid in all_pids:
            _kill_pid(pid)

        # 等待进程退出
        if all_pids:
            time.sleep(2)

        # 复查：还有存活的子孙进程吗？
        survivors = _find_all_descendant_pids(driver_pid)
        alive = [p for p in survivors if p != driver_pid]
        if alive:
            log.warning(f"Level 2 后仍有残留进程: {alive}，进入 Level 3")
        else:
            log.info("Level 2 进程树清理完成")
            return

    # Level 3: 镜像名全局兜底
    if platform.system() == "Windows":
        log.warning("执行 Level 3 全局兜底（msedgedriver.exe + msedge.exe）")
        _kill_by_name("msedgedriver.exe")
        _kill_by_name("msedge.exe")


# ---------------------------------------------------------------------------
# GPU 显示重置
# ---------------------------------------------------------------------------


def _reset_display() -> None:
    """重新应用当前显示模式，强制 GPU 渲染管线复位。

    Edge CDP 自动化密集的截图 + 鼠标注入操作后，DWM/GPU 渲染管
    线可能进入异常状态，表现为脚本结束后鼠标延迟/无响应。
    重新应用当前显示模式等效于 Win+Ctrl+Shift+B，但不闪烁。
    """
    if platform.system() != "Windows":
        return
    try:
        import ctypes
        from ctypes import wintypes

        # DEVMODEW 结构体 — 仅定义 EnumDisplaySettings 会写入的关键字段
        # 实际结构 ~220 字节，用 padding 补齐
        class _DEVMODEW(ctypes.Structure):
            _fields_ = [
                ("dmDeviceName", wintypes.WCHAR * 32),       # offset 0
                ("dmSpecVersion", wintypes.WORD),            # offset 64
                ("dmDriverVersion", wintypes.WORD),          # offset 66
                ("dmSize", wintypes.WORD),                   # offset 68
                ("dmDriverExtra", wintypes.WORD),            # offset 70
                ("dmFields", wintypes.DWORD),                # offset 72
                ("_pad0", ctypes.c_byte * 8),                # position/orientation
                ("dmColor", wintypes.SHORT),                 # offset 84
                ("dmDuplex", wintypes.SHORT),
                ("dmYResolution", wintypes.SHORT),
                ("dmTTOption", wintypes.SHORT),
                ("dmCollate", wintypes.SHORT),
                ("dmFormName", wintypes.WCHAR * 32),
                ("dmLogPixels", wintypes.WORD),
                ("dmBitsPerPel", wintypes.DWORD),
                ("dmPelsWidth", wintypes.DWORD),
                ("dmPelsHeight", wintypes.DWORD),
                ("dmDisplayFlags", wintypes.DWORD),
                ("dmDisplayFrequency", wintypes.DWORD),
                ("dmICMMethod", wintypes.DWORD),
                ("dmICMIntent", wintypes.DWORD),
                ("dmMediaType", wintypes.DWORD),
                ("dmDitherType", wintypes.DWORD),
                ("dmReserved1", wintypes.DWORD),
                ("dmReserved2", wintypes.DWORD),
                ("dmPanningWidth", wintypes.DWORD),
                ("dmPanningHeight", wintypes.DWORD),
            ]

        ENUM_CURRENT_SETTINGS = -1
        user32 = ctypes.windll.user32

        devmode = _DEVMODEW()
        devmode.dmSize = ctypes.sizeof(_DEVMODEW)

        # 读取当前显示设置
        if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
            log.debug("EnumDisplaySettings 失败，跳过 GPU 重置")
            return

        # 重新应用 — flags=0 使 Windows 走完整 mode set 管线
        result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), 0)
        if result == 0:  # DISP_CHANGE_SUCCESSFUL
            log.info("GPU 显示管线已重置")
        else:
            log.debug(f"ChangeDisplaySettings 返回 {result}（非致命）")
    except Exception:
        log.debug("GPU 重置失败，跳过", exc_info=True)


def cleanup_all() -> None:
    """清理所有已注册的 driver 及其子进程，外加兜底孤儿扫描。

    幂等：可被多次安全调用（atexit + _on_close + finally 可能叠加）。
    全程 try/except，失败不阻塞退出。
    """
    try:
        # 1. 清理已注册的 driver
        for driver_pid in list(_drivers.keys()):
            info = _drivers.pop(driver_pid, None)
            if info is None:
                continue
            _force_kill(driver_pid, info)

        # 2. 兜底：即使 _drivers 已空（如 finally 已 unregister），
        #    也扫描一次孤儿进程，防止 driver.quit() 窗口关了但进程残留
        cleanup_orphans()

        # 3. 重置 GPU 显示管线（修复 CDP 自动化后鼠标异常）
        _reset_display()
    except Exception:
        log.error("cleanup_all 异常", exc_info=True)
