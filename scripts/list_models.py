# -*- coding: utf-8 -*-
"""查询 InternAI 平台可用模型列表（带重试，不打印 key 明文）。"""
import sys
import time
import json
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import settings  # noqa: E402

url = settings.model_base_url.rstrip("/") + "/models"
models = None
last_err = None

for attempt in range(1, 6):
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {settings.model_api_key}"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = data.get("data", [])
        print(f"第 {attempt} 次尝试成功，平台返回 {len(models)} 个可用模型：")
        for m in models:
            print(f"  - {m.get('id', '')}  (owned_by: {m.get('owned_by', '')})")
        break
    except urllib.error.HTTPError as e:
        last_err = f"{e.code}: {e.read().decode('utf-8')[:200]}"
        print(f"第 {attempt} 次尝试: HTTP {e.code} -> {last_err}")
        time.sleep(8 * attempt)  # 指数退避
    except Exception as e:
        last_err = f"{type(e).__name__}: {e}"
        print(f"第 {attempt} 次尝试: {last_err}")
        time.sleep(5)

if models is None:
    print("\n❌ 最终未能获取模型列表。")
    print("提示：该平台可能不支持 /v1/models 接口，或频控较严。")
    print("常见 InternAI 模型名可尝试：internlm3.5 / internlm2.5-latest / internlm2.5-20b-chat 等。")
    print("如需帮助，请告知你在平台控制台看到的模型名。")