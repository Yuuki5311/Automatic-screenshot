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
        result = subprocess.run(
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

    杀掉所有孤儿 msedgedriver.exe 及其子孙 msedge.exe 进程。
    非 Windows 平台直接返回。
    失败静默忽略，不阻止程序启动。
    """
    if platform.system() != "Windows":
        return

    try:
        # 1. 找到所有孤儿 msedgedriver.exe
        result = subprocess.run(
            [
                "wmic", "process", "where", "name='msedgedriver.exe'",
                "get", "ProcessId",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        orphan_drivers: list[str] = []
        for line in result.stdout.splitlines():
            text = line.strip()
            if text.isdigit():
                orphan_drivers.append(text)

        if not orphan_drivers:
            return

        log.info(f"启动时清理孤儿进程: msedgedriver.exe={orphan_drivers}")

        # 2. 先收集所有孤儿 driver 的进程树（在杀之前）
        all_orphan_pids: set[str] = set(orphan_drivers)
        for pid_str in orphan_drivers:
            tree = _find_all_descendant_pids(int(pid_str))
            for tpid in tree:
                all_orphan_pids.add(str(tpid))

        # 3. 杀进程树中所有 PID
        for pid_str in all_orphan_pids:
            subprocess.run(
                ["taskkill", "/F", "/PID", pid_str],
                capture_output=True,
                timeout=10,
            )

        # 4. 全局兜底
        subprocess.run(
            ["taskkill", "/F", "/IM", "msedgedriver.exe"],
            capture_output=True, timeout=10,
        )
        subprocess.run(
            ["taskkill", "/F", "/IM", "msedge.exe"],
            capture_output=True, timeout=10,
        )
    except Exception:
        pass  # 清理失败不应阻止启动


# ---------------------------------------------------------------------------
# 三级降级清理
# ---------------------------------------------------------------------------


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
        subprocess.run(
            ["taskkill", "/F", "/PID", str(pid)],
            capture_output=True,
            timeout=10,
        )
        return True
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
        subprocess.run(
            ["taskkill", "/F", "/IM", name],
            capture_output=True,
            timeout=10,
        )
        return True
    except Exception:
        return False


def _force_kill(driver_pid: int, info: dict) -> None:
    """对单个 driver 执行三级降级清理。

    Level 1: driver.quit() (优雅退出)
    Level 2: 实时扫描整个进程树 → taskkill /F /PID (精确强杀所有子孙)
    Level 3: taskkill /F /IM msedgedriver.exe + msedge.exe (全局兜底)
    """
    driver = info.get("driver")

    # Level 1: 优雅退出
    if driver is not None:
        try:
            driver.quit()
            log.debug("driver.quit() 成功")
            return  # 成功，无需后续强杀
        except Exception:
            log.debug("driver.quit() 失败，进入 Level 2", exc_info=True)

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
        # msedge.exe 也做全局清理：此时已确认是残留，且 Level 2 已尽力精确杀
        _kill_by_name("msedge.exe")


def cleanup_all() -> None:
    """清理所有已注册的 driver 及其子进程。

    幂等：可被多次安全调用（atexit + _on_close + finally 可能叠加）。
    全程 try/except，失败不阻塞退出。
    """
    try:
        for driver_pid in list(_drivers.keys()):
            info = _drivers.pop(driver_pid, None)
            if info is None:
                continue
            _force_kill(driver_pid, info)
    except Exception:
        log.error("cleanup_all 异常", exc_info=True)
