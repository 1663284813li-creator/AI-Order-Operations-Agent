# -*- coding: utf-8 -*-
"""工具注册表：集中注册 + 暴露给 LLM 的 JSON Schema。

关键点：
- 每个工具是一个 (name, handler, schema) 三元组。
- schema 是 OpenAI 兼容的 function 描述，Agent 层据此做 Tool Calling。
- 新增业务 = 新增注册条目，不动编排层（工具即业务边界）。
"""
from __future__ import annotations

from typing import Any, Callable

from src.logger import log


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}

    def register(self, name: str, handler: Callable[..., Any], schema: dict) -> None:
        self._tools[name] = {"handler": handler, "schema": schema}
        log.debug("注册工具: %s", name)

    def get(self, name: str) -> Callable[..., Any]:
        if name not in self._tools:
            raise KeyError(f"未知工具: {name}")
        return self._tools[name]["handler"]

    def openai_schemas(self) -> list[dict]:
        """返回给 LLM 的 tools 列表（OpenAI 兼容格式）。"""
        return [t["schema"] for t in self._tools.values()]

    def names(self) -> list[str]:
        return list(self._tools.keys())


# 全局工具注册表
registry = ToolRegistry()


def make_schema(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """构造一个 OpenAI 兼容的 function schema。"""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }
