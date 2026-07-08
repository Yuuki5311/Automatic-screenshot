"""日志模块：同时输出到终端和文件。"""

import logging
import sys
from datetime import datetime

_logger = None


def setup_logger(log_file: str = None) -> logging.Logger:
    """初始化日志，同时输出到终端和文件。

    Args:
        log_file: 日志文件路径，默认为 logs/YYYY-MM-DD_HH-MM-SS.log

    Returns:
        logging.Logger 实例。
    """
    global _logger

    if _logger is not None:
        return _logger

    if log_file is None:
        import os
        os.makedirs("logs", exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_file = f"logs/{timestamp}.log"

    _logger = logging.getLogger("auto_screenshot")
    _logger.setLevel(logging.DEBUG)

    # 格式
    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)-5s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # 文件输出（详细）
    fh = logging.FileHandler(log_file, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    _logger.addHandler(fh)

    # 终端输出（简洁）
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    _logger.addHandler(ch)

    _logger.info(f"日志文件: {log_file}")
    return _logger


def get_logger() -> logging.Logger:
    """获取已初始化的 logger 实例。"""
    if _logger is None:
        return setup_logger()
    return _logger
