# -*- coding: utf-8 -*-
"""多模型接入客户端。

设计：走 OpenAI 兼容接口，模型是"插件"不是绑定。
切换模型只需改 .env（MODEL_NAME / MODEL_BASE_URL），
并可配合 evaluation 做多模型对比评测。

TODO: 对每个模型做超时、重试、token 统计（落 observability.trace）。
"""
from __future__ import annotations

from typing import Optional

from src.config import settings
from src.logger import log


class LLMClient:
    """统一模型客户端封装。"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.0,
    ) -> None:
        self.api_key = api_key or settings.model_api_key
        self.base_url = base_url or settings.model_base_url
        self.model = model or settings.model_name
        self.temperature = temperature if temperature != 0 else settings.model_temperature
        # token 用量统计（评测/成本指标用）
        self.total_calls = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

    def usage_stats(self) -> dict:
        """返回累计 token 用量统计。"""
        return {
            "calls": self.total_calls,
            "prompt_tokens": self.total_prompt_tokens,
            "completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }

    def _record_usage(self, resp) -> None:
        """从响应里提取 usage 并累计（平台可能不返回 usage，容错）。"""
        try:
            u = resp.usage
            if u is not None:
                self.total_calls += 1
                self.total_prompt_tokens += u.prompt_tokens or 0
                self.total_completion_tokens += u.completion_tokens or 0
        except Exception:
            self.total_calls += 1  # 无 usage 也计一次调用

    def _client(self):
        """惰性创建 OpenAI 兼容客户端。"""
        try:
            from openai import OpenAI
        except ImportError as e:  # 依赖未安装
            raise RuntimeError(
                "未安装 openai 依赖。请执行: pip install -r requirements.txt"
            ) from e
        if not self.api_key or self.api_key == "sk-xxx":
            raise RuntimeError("未配置 MODEL_API_KEY。请在 .env 中填写。")
        return OpenAI(api_key=self.api_key, base_url=self.base_url)

    def chat(self, messages: list[dict], tools: Optional[list[dict]] = None) -> str:
        """基础对话（非工具调用）。"""
        client = self._client()
        kwargs = {"messages": messages, "model": self.model, "temperature": self.temperature}
        if tools:
            kwargs["tools"] = tools
        resp = client.chat.completions.create(**kwargs)
        self._record_usage(resp)
        return resp.choices[0].message.content or ""

    def chat_with_tools(self, messages: list[dict], tools: list[dict]) -> tuple[Optional[str], Optional[dict]]:
        """带工具调用的对话。

        返回 (content, tool_call)。
        - tool_call 非空时，说明模型请求调用某个工具，由 agent 层执行。
        - 两字段通常会有一个为 None。
        """
        client = self._client()
        resp = client.chat.completions.create(
            messages=messages,
            model=self.model,
            temperature=self.temperature,
            tools=tools,
        )
        self._record_usage(resp)
        msg = resp.choices[0].message
        tool_call = None
        if msg.tool_calls:
            tc = msg.tool_calls[0]
            tool_call = {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
        return msg.content, tool_call
