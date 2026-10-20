import os
import requests

API_KEY = os.getenv("FUYAO_API_KEY")

if not API_KEY:
    raise RuntimeError("FUYAO_API_KEY is not set")

url = "https://fuyao.aicubes.cn/api/a-share/financials/income-statements"

response = requests.get(
    url,
    params={
        "thscode": "600519.SH",
        "period": "annual",
        "limit": 4
    },
    headers={"X-api-key": API_KEY},
    timeout=15
)

response.raise_for_status()
result = response.json()

if result.get("code") != 0:
    raise RuntimeError(f"API error: {result}")

items = result.get("data", {}).get("item", [])
data = {int(item["fiscal_year"]): item for item in items}

current = data[2025]
previous = data[2024]

def growth_rate(current_value, previous_value):
    if current_value is None or previous_value in (None, 0):
        return None
    return (current_value - previous_value) / previous_value * 100

revenue_growth = growth_rate(
    current["operating_income"],
    previous["operating_income"]
)

profit_growth = growth_rate(
    current["net_profit"],
    previous["net_profit"]
)

profit_margin = (
    current["net_profit"] / current["operating_income"] * 100
)

print("Company: 600519.SH")
print("Period: 2025 vs 2024")
print(f"Revenue Growth: {revenue_growth:.2f}%")
print(f"Net Profit Growth: {profit_growth:.2f}%")
print(f"Net Profit Margin: {profit_margin:.2f}%")
