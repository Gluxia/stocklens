# StockLens Backend Phase 1

The financial core documented here is preserved. The application now also has
question routing, `/api/plan`, `/api/research`, optional bounded AI interpretation,
and a compiled React frontend served by FastAPI. See the root [README](../README.md)
for the current full application and deployment instructions.

The original three scripts remain unchanged. This backend reuses their Fuyao
request contract and calculation formulas as reusable functions. No investment
recommendations or hardcoded financial results are included.

## Local setup

Run from the project root using Python 3.10 or later:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
cp .env.example .env
```

Set `FUYAO_API_KEY` in `.env`, then run:

```sh
python -m uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000
```

Environment variables take precedence over `.env`. The application loads only
the root project `.env`; keys never enter response metadata or error messages.
Do not commit populated environment files. No API key is needed to run tests.

```sh
curl 'http://127.0.0.1:8000/api/diagnosis?stock_code=600519.SH'
python -m pytest -q
```

Interactive API documentation: <http://127.0.0.1:8000/docs>.
Health check: `GET /api/health` (process health, not provider connectivity).
Only `600519.SH` is supported by the diagnosis route in Phase 1. The data client
accepts a stock argument for subsequent expansion. A reusable snapshot method
also preserves `test_api.py`'s request contract but is not used by diagnosis.

## Source verification and calculation policy

Contract checked on 2026-10-20:
<https://fuyao.aicubes.cn/docs/api-reference/financials/>

The provider documents consolidated statements, original-currency yuan amounts,
CNY for A-shares, natural-calendar fiscal years, and Shanghai-time millisecond
period-end timestamps. `operating_income` is revenue; `net_profit` is consolidated
net profit, not the distinct `parent_holder_net_profit` field.

Each record must match the requested stock, have `period=annual`, `fiscal_period`
of FY or Q4, integer fiscal year, a matching December 31 period end, and CNY
currency. Missing or conflicting metadata is rejected rather than inferred.
Documentation examples are not used as real company results.

The newest returned annual year is selected independent of response order.
Growth requires that year's immediately preceding calendar year; a gap never
becomes a multiyear growth figure. Duplicate years are rejected even if identical:
Phase 1 does not assume a revision-selection rule. Invalid records are not
silently skipped to select an older supposedly current period.

Formulas:

- Revenue growth: `(current operating_income - previous operating_income) / previous operating_income * 100`.
- Net profit growth: `(current net_profit - previous net_profit) / previous net_profit * 100`.
- Net profit margin: `current net_profit / current operating_income * 100`.

JSON fractional numbers are parsed directly into Decimal. Calculations use
38 significant digits and half-even rounding; values are serialized as decimal
strings to avoid JSON float precision loss. No display rounding is applied.
Missing values, booleans, nonnumeric/nonfinite values, values exceeding 38 digits
or exponent bounds, and zero denominators yield unavailable metrics with reasons.
Growth with a negative baseline is unavailable because ordinary percentage-growth
interpretation is misleading; negative profit can still produce a valid margin.
Margin requires positive revenue. Finite negative source amounts remain visible.

## Response and evidence

Responses contain `metrics`, `evidence`, `sources`, selected years, and `issues`.
Status is `complete`, `partial`, or `unavailable` based on metric availability.
Source evidence records include UUIDs, endpoint, original field and JSON path,
reporting period, period end, value, unit, metadata field paths, and UTC retrieval
timestamp. Calculation evidence links ordered input evidence IDs (numerator or
current first, denominator or previous second), formula, and result. Each metric
references its calculation evidence.

The response includes the original JSON text and its SHA-256 checksum in a source
object so paths remain independently inspectable and original precision is kept.
Keep this response if you need to revisit it: Phase 1 does not persist responses
or provide retrieval by ID. Retrieval time is not a publication date. Disclosure
dates are available through raw fields when the provider supplies them.

## Failure behavior

- `200`: valid data response, including partial/unavailable metrics or an empty list.
- `422`: missing/malformed stock code or a stock outside the Phase 1 scope.
- `503`: missing backend key.
- `504`: upstream request timeout (15-second requests timeout).
- `429`: upstream provider rate limit or quota reached.
- `502`: HTTP/network/business errors, malformed envelopes, invalid reporting
  metadata, unverified currency/unit, or duplicate periods.

Errors use `error.code` and `error.message`; FastAPI query validation uses its
standard `detail` structure. Provider error bodies are not echoed. Redirects are
not followed with the credential header. Tests use synthetic financial inputs
and mock transport; they do not verify live credentials, quota, or availability.
