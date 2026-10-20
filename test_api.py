import json
import os

import requests

API_KEY = os.getenv("FUYAO_API_KEY")

url = "https://fuyao.aicubes.cn/api/a-share/prices/snapshot"

params = {"thscodes": "600519.SH"}

headers = {"X-api-key": API_KEY}

response = requests.get(url, params=params, headers=headers, timeout=15)

result = response.json()

print(json.dumps(result, indent=4, ensure_ascii=False))
