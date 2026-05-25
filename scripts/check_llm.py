# -*- coding: utf-8 -*-
"""验证：.env 配置加载 + 真实 LLM 连通性测试（不打印 key 明文）。"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402

print("=== 配置加载检查 ===")
print("has_model_key:", settings.has_model_key)
print("model_name:", settings.model_name)
print("model_base_url:", settings.model_base_url)
print("model_api_key 尾部(脱敏): ****" + settings.model_api_key[-4:] if settings.model_api_key else "(空)")

print()
print("=== 真实 LLM 连通性测试 ===")
from src.models.client import LLMClient  # noqa: E402

llm = LLMClient()
try:
    reply = llm.chat(
        [{"role": "user", "content": "请只回答四个字：连通成功"}],
        tools=None,
    )
    print("LLM 回复:", reply)
    print("✅ 连通成功")
except Exception as e:
    print("❌ 连通失败:", type(e).__name__, str(e))
    print("提示：InternAI 等平台可能要求特定的认证头或模型名，请检查 .env 配置。")
