# -*- coding: utf-8 -*-
"""日志工具：统一格式，写入 logs/，控制台 UTF-8。"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from src.config import settings


def setup_logger(name: str = "ticket-agent", level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:  # 已初始化则复用
        return logger
    logger.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # 文件
    settings.log_dir.mkdir(parents=True, exist_ok=True)
    fh = logging.FileHandler(settings.log_dir / "agent.log", encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)

    logger.propagate = False
    return logger


log = setup_logger()