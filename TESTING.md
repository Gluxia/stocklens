# Testing StockLens

All automated financial fixtures are synthetic test values, not Kweichow Moutai
results. No automated test calls a paid provider. The original root smoke scripts
remain untouched and are excluded by `pytest.ini`.

## Run

From the project root after installing dependencies:

```sh
source .venv/bin/activate
python -m pytest -q
python -m pip check
npm --prefix frontend test
npm --prefix frontend run build
```

Build the frontend before the backend test run to include production asset-serving
checks. `npm run build` performs strict TypeScript checking and a Vite production
build. Frontend interaction tests use Vitest, Testing Library and jsdom.

## Coverage

Backend tests cover Decimal calculations and parsing, missing/zero/negative inputs,
invalid numeric types, annual period validation, units, stock mismatches, duplicate
years, nonconsecutive years, empty statements, response envelopes, business/HTTP
errors, sanitized failures, and query validation. New tests cover question routing
in English/Chinese, mixed evidence, unknown dimensions, stale periods, buy/sell and
guarantee requests, valid/invalid model selections, injection-resistant prompt inputs,
fallback on timeout/refusal/truncation, full research/follow-up endpoint calls, and
production static-asset serving.

Frontend tests cover an empty initial page, suggested questions, Ask → Plan →
Diagnose → Verify → Explore navigation, source input drill-down, deterministic vs
AI mode labels, missing data, empty evidence, invalid references, server errors,
network failure, unsupported-stock responses, retry, and loading.

## Manual/live smoke checks

1. Start the built app and open its root URL.
2. Ask “Compare revenue and profit growth.” Verify actual API-derived values,
   periods, source, retrieval time, and financial report status.
3. Click revenue growth, inspect the formula, then click each input. Confirm the
   field, JSON path, original value/unit, period, timestamp, and raw JSON.
4. Ask about valuation; verify its unavailability is explicit rather than filled
   with assumed multiples or price judgments.
5. Click a follow-up and verify the question and plan change.
6. Ask “Should I buy? Guarantee a return.” Verify factual-only reframing.
7. Test missing provider credentials or a stopped backend; verify an error and no
   invented report. Test no AI key; verify deterministic mode.
8. Test keyboard focus, Escape/close in the native modal, and narrow screens.

## Results for this implementation

- Backend: 107 tests passed (includes the original 64 tests).
- Frontend: 21 tests passed (13 interaction tests and 8 localization/formatting checks).
- Strict TypeScript check and production build passed.
- Additional live/schema/deployment checks are recorded below after validation.

Known non-failing warnings: the installed Starlette TestClient deprecates its httpx
adapter; Vite/Rollup removes two unrecognized purity annotations from dependency
comments. These do not fail the checks. Browser plugin discovery returned no
connected browsers, so visual browser QA and real-browser keyboard/mobile checks
could not be completed in this session. jsdom interaction tests are not a substitute
for rendered visual QA. A cloud deployment is prepared, not performed.

### Live checks in this session

- The combined FastAPI process served `/api/health` and the built root HTML.
- An authenticated read-only Fuyao check returned HTTP **429** and business code
  **429** (provider rate limit/quota). No financial values were substituted.
- An explicit `upstream_rate_limited` response was added for that condition.
- Live AI was not exercised: the optional key/model pair is not configured.
- Docker CLI exists, but its daemon socket is unavailable. The image build/run
  was therefore not validated here; application static serving was tested directly.
- Installed dependency consistency check passed. A scan against configured local
  credential values found zero matches in compiled frontend assets, and example
  API-key values are blank.

### Simplified Chinese localization checks

The frontend suite verifies Chinese navigation, terminology, planning, errors,
follow-up requests, compliance notices, constrained interpretation translation,
unknown-template fallback, UTF-8 metadata and `zh-CN`. Precision tests cover negative,
zero, small and large Decimal values, rounded narrative text, exact evidence values,
and unmodified API objects. All original research, retry, loading, missing-data,
reference-validation, and drill-down interactions remain covered. TypeScript
checking and the production build also pass. CJK font fallbacks, wrapping, flexible
card headers and responsive heading sizing were added without changing the palette
or layout structure. Browser discovery still returned no connected browsers, so
rendered desktop/mobile overflow cannot be visually certified in this session.

### Gemini compatibility verification

Five Gemini-specific contract/failure tests were added; the full backend suite
passed with 104 tests. Exactly one live LLM call used explicitly marked synthetic
evidence and returned HTTP 404 with no parseable response.
`interpretation_mode="llm"` was **not achieved** in the live call. The report
remained deterministic with zero accepted interpretations. No production request
parameters were changed based on this inconclusive failure. See
AI_USAGE_AND_VALIDATION.md for provider documentation and verification limits.

### Confirmed Gemini model migration (2026-10-20)

This follow-up supersedes the earlier unsuccessful Gemini 2.5 live check.
Google's official `/v1beta/models` returned HTTP 200 with 63 models, including
`gemini-3.5-flash-lite`. That model passed a minimal unstructured Chat Completions
request (HTTP 200, expected OK response). Only after that succeeded was the
unchanged StockLens strict JSON Schema request exercised: HTTP 200,
`finish_reason=stop`, `strict=true`, `max_completion_tokens=1000`, and three
accepted interpretations with `interpretation_mode="llm"`.

The local `.env` then changed only `LLM_MODEL` to `gemini-3.5-flash-lite`; all
other parsed variables and key values were verified unchanged. The Gemini
request-contract regression test now covers both the legacy and selected model.
The full backend suite passed: **105 tests**.

Finally, one complete `POST /api/research` request used **real Fuyao financial
data** and the selected Gemini model. The research endpoint and LLM both returned
HTTP 200. Financial status was `complete`, `interpretation_mode="llm"`, and all
three accepted interpretations referenced available evidence. No financial values,
credentials, sensitive headers, or raw provider errors were printed. No billing
settings, production request parameters, financial formulas, frontend components,
evidence validation, or fallback rules changed.

### Render readiness review

- 107 backend tests passed, including new provider-free health and HTTP 429
  research-flow tests. The quota failure does not call the model. Existing model
  timeout/refusal/malformed-output/evidence-validation fallback tests passed.
- 21 frontend tests and the TypeScript/Vite production build passed.
- `pip check` found no broken requirements.
- Git ignore rules passed 15 representative sensitive-path checks in an isolated
  temporary repository; the project itself was not initialized, committed or pushed.
- Configured local API-key values had zero matches in checked backend/frontend
  source, compiled frontend assets, README, example environment file, Dockerfile
  and Render configuration. Example key values remain blank.
- Dockerfile inspection confirmed the multistage frontend build, copied dist
  assets, dynamic PORT, 0.0.0.0 binding, non-root runtime and health command.
  Docker daemon was unavailable; no actual container build/run was claimed.
- The Render Blueprint now uses the live-verified Gemini model and endpoint and
  prompts privately for both keys. No Render deployment or push was performed.
