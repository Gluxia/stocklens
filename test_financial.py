
import os
import json
import requests

API_KEY = os.getenv("FUYAO_API_KEY")

if not API_KEY:
    raise RuntimeError("FUYAO_API_KEY is not set")

url = "https://fuyao.aicubes.cn/api/a-share/financials/income-statements"

params = {
    "thscode": "600519.SH",
    "period": "annual",
    "limit": 4
}

headers = {
    "X-api-key": API_KEY
}

response = requests.get(
    url,
    params=params,
    headers=headers,
    timeout=15
)

response.raise_for_status()
result = response.json()

if result.get("code") != 0:
    raise RuntimeError(f"API error: {result}")

items = result.get("data", {}).get("item", [])

if not items:
    print("No financial data returned.")
else:
    for item in items:
        print("----------------------")
        print("Year:", item.get("fiscal_year"))
        print("Revenue:", item.get("operating_income"))
        print("Net Profit:", item.get("net_profit"))
        print("Currency:", item.get("currency"))
