# -*- coding: utf-8 -*-
"""全局配置：优先读取环境变量 / .env 文件。"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # 未装 python-dotenv 时静默降级
    pass

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Settings:
    """集中式配置，避免散落魔法数字。"""

    # ---- 模型 ----
    model_api_key: str = field(default_factory=lambda: os.getenv("MODEL_API_KEY", ""))
    model_base_url: str = field(
        default_factory=lambda: os.getenv("MODEL_BASE_URL", "https://api.deepseek.com")
    )
    model_name: str = field(default_factory=lambda: os.getenv("MODEL_NAME", "deepseek-chat"))
    model_temperature: float = 0.0

    # ---- 运行 ----
    max_rounds: int = 8          # Agent 每任务最多工具轮次
    session_ttl_seconds: int = int(os.getenv("SESSION_TTL_SECONDS", "1800"))

    # ---- 路径 ----
    data_dir: Path = ROOT / "data"
    mock_dir: Path = ROOT / "data" / "mock"
    log_dir: Path = ROOT / "logs"
    output_dir: Path = ROOT / "outputs"

    # ---- 安全 ----
    refund_max_amount: float = 5000.0      # 单笔退款上限（超限走人工）
    reissue_max_qty: int = 10              # 单笔补发数量上限
    batch_action_limit: int = 20           # 单批操作上限（防批量误操作）

    def ensure_dirs(self) -> None:
        for p in (self.data_dir, self.mock_dir, self.log_dir, self.output_dir):
            p.mkdir(parents=True, exist_ok=True)

    @property
    def has_model_key(self) -> bool:
        return bool(self.model_api_key) and self.model_api_key != "sk-xxx"


# 全局唯一配置实例
settings = Settings()
settings.ensure_dirs()