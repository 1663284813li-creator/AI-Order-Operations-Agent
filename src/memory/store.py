# -*- coding: utf-8 -*-
"""记忆层。

分层设计（与立项方案第 5 节一致）：
- 短期会话记忆（SessionMemory）：同一 session 内跨轮上下文，带 TTL，可摘要压缩。
- 长期用户画像（UserProfile）：跨会话记住用户/门店偏好，降低重复沟通。

MVP 先用内存实现（接口抽象，便于后续换 Redis / 向量库）。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.config import settings
from src.logger import log


# ----------------------------------------------------------------------
# 短期：会话记忆
# ----------------------------------------------------------------------
@dataclass
class _Entry:
    role: str
    content: str
    ts: float = field(default_factory=time.time)


class SessionMemory:
    """单会话短期记忆：带 TTL 的滑动窗口。"""

    def __init__(self, ttl: int | None = None, max_entries: int = 20) -> None:
        self.ttl = ttl or settings.session_ttl_seconds
        self.max_entries = max_entries
        self._entries: list[_Entry] = []

    def add(self, role: str, content: str) -> None:
        self._entries.append(_Entry(role=role, content=content))
        self._prune()

    def _prune(self) -> None:
        now = time.time()
        self._entries = [e for e in self._entries if now - e.ts <= self.ttl]
        # 滑动窗口：只保留最近 max_entries 条
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries:]

    def messages(self) -> list[dict]:
        return [{"role": e.role, "content": e.content} for e in self._entries]

    def clear(self) -> None:
        self._entries.clear()

    def summarize(self) -> str:
        """摘要压缩（W2 实现）：把历史压成一句话，避免 token 膨胀。"""
        # TODO(W2): 用 LLM 把历史摘要压缩；MVP 先简单拼接
        return "；".join(f"{e.role}: {e.content[:40]}" for e in self._entries)


# ----------------------------------------------------------------------
# 长期：用户画像
# ----------------------------------------------------------------------
class UserProfileMemory:
    """跨会话用户/门店画像（长期记忆）。

    MVP 用 dict 存储；后续可换结构化 DB + 向量检索。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, dict] = {}

    def update(self, user: str, **facts) -> None:
        p = self._profiles.setdefault(user, {})
        p.update(facts)
        log.debug("更新用户画像: %s", user)

    def get(self, user: str) -> dict:
        return self._profiles.get(user, {})

    def summary_for(self, user: str) -> str:
        """注入到上下文前，生成一段画像摘要（<=200字）。"""
        p = self.get(user)
        if not p:
            return ""
        parts = [f"{k}: {v}" for k, v in p.items()]
        text = "，".join(parts)
        return text[:200]


# 全局实例（MVP）
session_memory = SessionMemory()
user_profile = UserProfileMemory()