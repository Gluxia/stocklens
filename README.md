# StockLens

An evidence-first A-share research application for `600519.SH` (Kweichow Moutai).
The journey is **Ask → Plan → Diagnose → Verify → Explore**. Real Fuyao financial
statements become Decimal-calculated metrics, source-linked observations, and
optional bounded AI interpretations. No sample company results are shipped.

## Quickest local launch: one application

Prerequisites: Python 3.10+ (tested with 3.13), Node 22.12+ or 24, and a Fuyao key.
Run these commands from the project root:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements-dev.txt
```

If `.env` already exists, keep it. Otherwise copy `.env.example` to `.env` and set
`FUYAO_API_KEY`. Never paste keys into frontend files or Git. To build the UI:

```sh
npm --prefix frontend ci
npm --prefix frontend run build
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000**. FastAPI serves both the built frontend and API.
Build before starting the server; restart it after the first frontend build so
that static asset routes are registered. No separate production frontend server,
CORS setup, or database is required.

If your npm cache has permission errors, use `npm --prefix frontend ci --cache
/tmp/stocklens-npm-cache` rather than changing ownership of unrelated files.

### Development with hot reload

Terminal 1, from the project root:

```sh
source .venv/bin/activate
python -m uvicorn backend.app.main:app --reload --port 8000
```

Terminal 2, from the project root:

```sh
npm --prefix frontend run dev
```

Open **http://127.0.0.1:5173**. Vite forwards `/api` to `127.0.0.1:8000`.
The Vite proxy is development infrastructure; production uses the same-origin
FastAPI app. The frontend never calls Fuyao or the LLM directly.

## What works

- One supported stock with an English/Chinese natural-language question input.
- Explainable keyword-based dimension selection and annual financial context.
- Revenue growth, consolidated net profit growth, and consolidated net profit margin.
- Positive/negative annual growth observations, genuinely divergent growth signals,
  and explicit unknowns. A positive margin is not automatically labeled favorable.
- Separate observations, bounded interpretations, and data coverage limitations.
- Source drill-down: evidence ID → formula → ordered input IDs → original field,
  JSON path, period, currency/unit, retrieval time, original provider JSON and hash.
- Optional backend-only AI selection/prioritization of Python-validated interpretations.
- Deterministic factual fallback for missing keys, outages, refusal, or invalid output.
- Freshness warnings and explicit missing, partial, unsupported, and failed-request states.
- Follow-up questions that launch a new request and plan.
- Responsive React/TypeScript UI styled with Tailwind and local CSS; no chart is
  used because three standalone percentages do not establish a meaningful time series.

## Optional AI configuration

Set these in the backend `.env` or hosting secret settings, then restart FastAPI:

```dotenv
LLM_API_KEY=your-server-side-key
LLM_MODEL=your-provider-model-id
LLM_BASE_URL=https://api.openai.com/v1
```

Choose an enabled model supporting Chat Completions `response_format=json_schema`.
An HTTPS OpenAI-compatible service can be configured with its base URL and model.
Model/provider incompatibility falls back to facts; no mock AI success is shown.
`LLM_API_KEY` and `LLM_MODEL` must both be populated. No default model is assumed.
See [AI_USAGE_AND_VALIDATION.md](AI_USAGE_AND_VALIDATION.md) for exact boundaries.

## API

- `GET /api/health`: process health; does not spend provider quota.
- `GET /api/diagnosis?stock_code=600519.SH`: preserved Phase 1 response.
- `POST /api/plan`: deterministic plan without a Fuyao request.
- `POST /api/research`: full financial research and optional AI interpretation.
- `GET /docs`: interactive API documentation.

```sh
curl -X POST http://127.0.0.1:8000/api/research \
  -H 'Content-Type: application/json' \
  -d '{"stock_code":"600519.SH","question":"Compare revenue and net profit growth"}'
```

A research response contains `plan`, the original `diagnosis`, `findings`,
`observations`, `interpretations`, mode/status, freshness, and follow-up questions.
Errors preserve Phase 1's status codes and sanitized messages. Empty data returns
an explicit unavailable report; missing metadata/duplicate periods fail validation.

## Exact deployment: Docker

From the project root, with Docker running:

```sh
docker build -t stocklens:latest .
docker run --detach --name stocklens --restart unless-stopped \
  --env-file .env -p 8000:8000 stocklens:latest
curl --fail http://127.0.0.1:8000/api/health
```

Open http://127.0.0.1:8000. The multistage image builds React, installs backend
runtime dependencies, includes timezone data, and runs as a non-root user. `.env`
is excluded from the image; credentials enter only at runtime. No persistent
volume is needed because this MVP does not store reports. `PORT` defaults to 8000.
For a cloud Docker host, upload/push the repository or image, select this Dockerfile,
set the same backend environment variables as hosting secrets, expose the host's
assigned `PORT`, and set the health path to `/api/health`. Use the host's HTTPS URL.

### Render deployment: reviewed configuration

No push or deployment was performed during the readiness review. This workspace
currently has no `.git` directory, so it must first become a repository before
Render can build from it. These are manual next steps after review:

1. Create a private GitHub repository. Initialize this project locally, stage the
   intended source files, and inspect `git diff --cached --name-only` before your
   first commit. `.env`, databases, logs, keys, and local credential directories
   must not appear. Keep `frontend/package-lock.json` in the repository. Push to
   your repository only when you are ready. Ignore rules do not remove secrets
   from an existing repository's tracking or history.
2. In Render, choose **New → Blueprint**, connect your repository, select the
   deployment branch, and use the root `render.yaml`. It defines one Docker web
   service, repository-root build context, `./Dockerfile`, and `/api/health`.
   If you instead choose **New → Web Service**, select **Docker**, leave Root
   Directory blank (repository root), set Dockerfile Path to `./Dockerfile`,
   Docker Build Context Directory to `.`, and Health Check Path to `/api/health`.
   Leave the Docker Command override blank. Choose an available plan; the
   Blueprint currently requests Free. No database or persistent disk is needed.
3. Enter these environment values **only in Render's environment settings**:

   | Variable | Value |
   | --- | --- |
   | `FUYAO_API_KEY` | Your existing Fuyao key, entered privately |
   | `LLM_API_KEY` | Your existing Gemini key, entered privately |
   | `LLM_MODEL` | `gemini-3.5-flash-lite` |
   | `LLM_BASE_URL` | `https://generativelanguage.googleapis.com/v1beta/openai` |

   The Blueprint prompts for both secrets with `sync: false`; it stores only
   public model/endpoint values in YAML. For existing services, manually add
   new secrets in **Environment**; Blueprint sync does not prompt again. Do not
   upload `.env` or use `VITE_*` for keys. Do not add secret-bearing Docker build
   arguments. Render supplies `PORT`; no frontend API URL variable is required.
4. When ready, select **Deploy Blueprint** / **Create Web Service**. The Dockerfile
   runs `npm ci`, type-checks/builds Vite, copies `frontend/dist` into the Python
   image, installs backend dependencies, and starts the combined app as a non-root
   user. There is no separate frontend deployment or custom build command.
5. Confirm the deployment becomes healthy. Open `https://YOUR-SERVICE.onrender.com/`
   and verify:

   ```sh
   curl --fail https://YOUR-SERVICE.onrender.com/api/health
   ```

   Expected body: `{"status":"ok"}`. This is a process-health check, not a paid
   provider check. Ask a Chinese growth/profitability question, inspect evidence
   and calculation inputs, then click a follow-up. A successful real AI response
   has `interpretation_mode="llm"`; unavailable AI must be labeled as factual
   fallback. Fuyao quota errors must show a clear error without sample data.

The production Docker command is equivalent to:

```sh
exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
```

Docker `EXPOSE 8000` is metadata; the process and its container health check both
read the actual `PORT`. Do not use Vite's development server or `--reload` in
production. Render uses the image's CMD when no Docker Command override is set.

### Public demo request budget (recommended, not implemented)

The app currently has **no server-side rate limiter or response cache**. Disabling
buttons while a request runs only protects normal UI use; public callers can invoke
the API directly. Before broad public sharing, a small starting policy is:

- Limit each client to 5 provider-backed requests/minute and cap global
  provider-backed traffic at 20/minute with 2 concurrent research operations.
  Protect both `/api/research` and `/api/diagnosis`; exempt health and static assets.
  These are proposed demo limits, not provider entitlements. Adjust to your actual
  key quotas and implement at a trusted ingress or in the app; this YAML does not
  configure a Render-native per-IP rate limiter.
- Cache successful annual statement responses for 10 minutes by provider, stock,
  period and request parameters. Preserve the original retrieval timestamp and
  response hash; do not cache errors or represent cached data as newly retrieved.
- If caching AI selections later, tie them to the exact evidence snapshot/IDs,
  model and interpretation-catalog version. Never reuse old evidence IDs against
  a newly generated report. Bound cache size and expiry.
- A single-instance in-memory limiter/cache needs no paid service or disk but
  resets on restart. Multiple workers/instances require coordinated limits.
  Keep the default single worker for the challenge demo.

No request limits, paid services, billing settings, or financial behavior were
changed by this configuration-only review. Provider errors still fail safely,
but failure handling does not prevent quota consumption by repeated requests.

### Readiness limits

The React production build, frontend tests, backend tests, static serving, and
provider-free health endpoint passed local checks. Git ignore rules were checked
against representative sensitive paths, and configured key values were absent
from checked publishable source/configuration and compiled frontend files. Docker
ignore rules now cover nested environment files, databases, logs and common key
files. The local Docker daemon is unavailable, so an actual image build/run remains
unverified; the first Render build must confirm container packaging. No Git
repository/history was available to audit, and no cloud release was performed.

Official references: [Docker deployment](https://render.com/docs/docker),
[web service setup](https://render.com/docs/web-services),
[Blueprint secrets](https://render.com/docs/blueprint-spec#prompting-for-secret-values).

## Project layout

```text
backend/app/       existing data client and calculation core; new research + AI orchestration
backend/tests/     calculation, provider, routing, AI validation, and API tests
frontend/src/      React UI, runtime schemas, evidence drawer, and interaction tests
frontend/          Vite/Tailwind configuration, package.json and lockfile
Dockerfile         frontend build + single FastAPI runtime
render.yaml        optional cloud Blueprint
```

The original `test_api.py`, `test_financial.py`, and `calculate_metrics.py` are
unchanged. Root pytest configuration deliberately avoids collecting these live
smoke scripts. See [TESTING.md](TESTING.md) for checks and limitations and
[backend/README.md](backend/README.md) for the financial contract and formulas.

## Deliberate scope limits

Historical prices, valuation adapters, peers, news, exports, accounts, saved
reports, broad industry classification, and streaming are not implemented.
Valuation/price/cash-flow questions visibly return missing-evidence limitations
plus available annual context. The company type is a reviewed single-company
MVP policy, not a live profile-classification API. Keyword routing is transparent
but does not fully understand arbitrary questions. The primary UI is Simplified Chinese; English and Chinese
research keywords are recognized. No personalized investment advice or guaranteed outcomes.

Reports are regenerated, not cached or persisted. A newly retrieved annual report
can still describe old operations. Current freshness policy flags years older
than the previous calendar year as stale, and does not verify interim filings.
This is a challenge demo with no authentication or distributed rate limiting;
use hosting request/spend limits for a public demonstration. Tests and packaging
are not a claim of production-scale hardening.

If Fuyao returns `429`, the UI explicitly reports a provider rate limit or quota
condition. Wait for the provider allowance to reset or check the key's quota;
repeated follow-up requests consume real API calls. The app does not bypass quota
or substitute synthetic data. Current implementation-session live checks hit this
condition; the earlier user-verified real-data backend remains the data foundation.

Render configuration references: [Docker deployment](https://render.com/docs/docker)
and [Blueprint specification](https://render.com/docs/blueprint-spec).

## Simplified Chinese presentation

The interface uses `zh-CN`, Chinese financial terminology, and the slogan
“看清企业经营，追溯每条结论。”. `frontend/src/zh-CN.ts` provides a constrained
presentation layer for backend plans, findings, known interpretation templates,
freshness, and follow-up questions. Unknown generated prose is not translated
into an assumed conclusion; it is explicitly marked unverified. User-entered
questions, original field names, JSON paths, formulas, IDs, and raw JSON remain
unchanged. Cards and narrative metrics use decimal.js to show two decimal places;
the evidence drawer preserves full precision. No backend contract or formula is
changed by localization.

## Phase 2: historical price research

Ask **“贵州茅台过去一个月的股价表现如何？”**. Price keywords select the
price dimension first; annual statements remain separately labeled context.
`POST /api/research` adds `price_analysis` only when prices are requested. The
existing `/api/diagnosis` financial contract and calculations are unchanged.
No new key or deployment configuration is needed; install the updated frontend
lockfile with `npm --prefix frontend ci` and rebuild normally.

The adapter uses Fuyao's documented `GET /api/a-share/prices/historical`, with
one `thscode`, `interval=1d`, Unix-millisecond `start`/`end` and explicit
`adjust=none`. The official contract is at
[Fuyao prices documentation](https://fuyao.aicubes.cn/docs/api-reference/prices/)
(and its official [full documentation](https://fuyao.aicubes.cn/llms-full.txt)).
A successful real response verified `data.item[].date_ms`, OHLC fields, and
`data.thscode`, `interval`, `adjust`. The adapter requires the identity metadata;
missing/mismatched metadata fails safely rather than assuming an adjustment.
CNY pricing and Shanghai dates follow the documented contract.

The default requested window runs from the same calendar date last month
(clamped at month-end) through yesterday in Shanghai, excluding today's
unfinished daily bar. Other question-specified windows are not parsed yet; the
UI always shows this default window. Return is `(last_close / first_close - 1)
* 100`, not total shareholder return. High/low use daily highs/lows. Calculations
use valid, unique observations and Decimal precision 38. Exact source strings,
JSON paths, date paths, formulas, ordered inputs, timestamps and raw response
hashes are available in the evidence drawer. Only chart coordinates use Number.

Trading-calendar completeness is **unverified**, so available results are marked
`partial`; requested dates are distinct from actual observation dates. Invalid
rows are excluded with warnings, duplicate dates reject the series, fewer than
two observations suppress return, and zero observations suppress the chart.
Latest observations more than seven calendar days before the request end trigger
a possible-staleness warning; this is not an exchange-calendar determination.
Provider errors, including 429, produce an unavailable price section while
preserving available financial results. Financial failures likewise do not
prevent an otherwise valid price report. No automatic retries or interpolation
are used. Public request limits and provider caching remain future work.
