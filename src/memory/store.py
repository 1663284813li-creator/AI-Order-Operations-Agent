# -*- coding: utf-8 -*-
"""记忆层。

分层设计（与立项方案第 5 节一致）：
- 短期会话记忆（SessionMemory）：同一 session 内跨轮上下文，带 TTL，可摘要压缩。
- 长期用户画像（UserProfileMemory）：跨会话记住用户/门店偏好，降低重复沟通。

MVP 先用内存实现（接口抽象，便于后续换 Redis / 向量库）。
"""
from __future__ import annotations

import time
from collections import Counter
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
    """单会话短期记忆：带 TTL 的滑动窗口。

    注意：MVP 为单会话（全局实例）；生产环境应按 session_id 分桶隔离。
    """

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

    def summarize(self, max_chars: int = 200) -> str:
        """摘要压缩：把历史压成一段话（简单拼接版，避免 token 膨胀）。"""
        if not self._entries:
            return ""
        # 只取最近 N 条 + 每条的要点，超出 max_chars 截断
        recent = self._entries[-6:]
        parts = []
        for e in recent:
            content = e.content.replace("\n", " ").strip()
            if len(content) > 60:
                content = content[:57] + "..."
            parts.append(f"[{e.role}] {content}")
        text = "；".join(parts)
        return text[:max_chars]


# ----------------------------------------------------------------------
# 长期：用户画像
# ----------------------------------------------------------------------
class UserProfileMemory:
    """跨会话用户/门店画像（长期记忆）。

    MVP 用 dict 存储（内存）；后续可换结构化 DB + 向量检索。
    画像字段是领域相关的结构化数据（不是原始对话），便于注入和检索。
    """

    def __init__(self) -> None:
        self._profiles: dict[str, dict] = {}

    # ---- 领域相关写入 ----
    def record_order(self, user: str, store: str, sku: str, issue_type: str) -> None:
        """记录一次工单处理涉及的门店/商品/问题类型（增量统计）。"""
        p = self._profiles.setdefault(user, {})
        stores: Counter = Counter(p.get("store_counter", {}))
        skus: Counter = Counter(p.get("sku_counter", {}))
        issues: Counter = Counter(p.get("issue_counter", {}))
        stores[store] += 1
        skus[sku] += 1
        issues[issue_type] += 1
        p["store_counter"] = dict(stores)
        p["sku_counter"] = dict(skus)
        p["issue_counter"] = dict(issues)
        p["stores"] = sorted(stores.keys())
        p["last_store"] = store
        p["last_sku"] = sku
        p["last_issue"] = issue_type
        p["updated_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        log.debug("画像更新: user=%s store=%s sku=%s issue=%s", user, store, sku, issue_type)

    # ---- 通用 ----
    def update(self, user: str, **facts) -> None:
        p = self._profiles.setdefault(user, {})
        p.update(facts)

    def get(self, user: str) -> dict:
        return self._profiles.get(user, {})

    def clear(self) -> None:
        """清空全部画像（测试/评测环境隔离用）。"""
        self._profiles.clear()

    def summary_for(self, user: str, max_chars: int = 200) -> str:
        """生成画像摘要（注入上下文用，<=200字）。"""
        p = self.get(user)
        if not p:
            return ""
        parts = []
        if p.get("stores"):
            parts.append(f"常处理门店: {', '.join(p['stores'][:3])}")
        if p.get("sku_counter"):
            top_skus = sorted(p["sku_counter"].items(), key=lambda x: -x[1])[:3]
            parts.append(f"常涉商品: {', '.join(f'{k}({v}次)' for k, v in top_skus)}")
        if p.get("issue_counter"):
            top_issues = sorted(p["issue_counter"].items(), key=lambda x: -x[1])[:3]
            parts.append(f"常见问题: {', '.join(f'{k}({v}次)' for k, v in top_issues)}")
        if p.get("last_issue"):
            parts.append(f"最近诉求: {p['last_issue']}")
        text = "；".join(parts)
        return text[:max_chars]


# 全局实例（MVP：单用户演示；生产换 session/user 维度的持久化存储）
session_memory = SessionMemory()
user_profile = UserProfileMemory()