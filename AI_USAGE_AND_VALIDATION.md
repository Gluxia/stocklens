# AI usage and evidence validation

## Actual AI behavior

The backend optionally calls an HTTPS OpenAI-compatible Chat Completions endpoint
using `LLM_API_KEY`, `LLM_MODEL`, and `LLM_BASE_URL`. It requests strict JSON Schema
output. The API pattern follows the official [structured outputs guide](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat).
Provider responses are independently validated; provider schema support alone is
not treated as proof of grounding.

AI **selects and prioritizes** up to three interpretations from a small catalog
whose conditions Python has established. This is deliberately constrained, not
free-form financial generation. The UI labels this “AI-prioritized · validated.”
It never claims a human-level comprehensive review or autonomous investment plan.

The model receives selected dimension IDs, factual observations and candidate
interpretations with evidence IDs. Raw questions, raw response bodies, API keys,
and personal portfolio data are not placed in the prompt. Financial observations
sent to the configured AI provider are the same public-company metrics shown in
the report. Only the backend sends the request; secrets are not bundled by Vite.

The model may return only interpretation IDs and exact ordered evidence IDs.
It cannot supply its own prose, numerical values, category labels, recommendations,
or prices. Display wording comes from backend-owned templates. Thus the model
cannot introduce new financial claims through untrusted generated text.

## Validation and fallback

Validation rejects unknown/duplicate interpretation IDs, unknown evidence IDs,
unavailable evidence, mismatched ordered references, additional fields, empty or
oversized selections, malformed JSON, refusals, and truncated completions. All
interpretations must exist in the catalog built for this exact response.

HTTP errors, timeouts, missing key/model, unsupported schema configuration, or
validation failures preserve the financial report and return a labeled deterministic
factual summary. The UI displays the actual mode and status; it never simulates an
AI-generated result. A live model request is not required for the app to work.

Requests use a 5-second connection and 15-second read timeout, do not follow
redirects with credentials, and do not echo provider bodies or exception strings.
Only HTTPS backend-configured endpoints are accepted. The frontend cannot set the
provider URL, model, or key.

## Question routing and investment-action requests

Routing always uses deterministic English/Chinese keyword rules. It selects growth,
profitability, valuation, price behavior, and/or earnings-quality dimensions with
visible reasons. Unsupported dimensions remain unavailable. Unknown intents default
to an explicit growth/profitability review; full semantic understanding is not claimed.

A conservative keyword filter detects common English/Chinese requests for buy/sell
actions, recommendations, target prices, or guaranteed outcomes. These receive a
factual-research notice and bypass the LLM. This filter is not a complete language
safety classifier. Even if phrasing evades it, the output schema and backend
catalog cannot emit trading instructions or guarantees. User input is rendered as
React text and is not an instruction channel for the model.

## Observations and interpretation

- Positive/negative evidence means the sign of a valid annual growth comparison
  against a positive prior baseline. It does not mean the stock is attractive.
- Opposite revenue/profit growth signs produce a mixed observation with both
  evidence references. No causal explanation is invented.
- Net margin is a numerical observation; its absolute sign does not establish
  relative quality. Missing benchmarks are explicit.
- No directional conclusion is created for missing data or zero growth.
- Missing adapters produce coverage limitations without invented source IDs.
- Stale annual years and unverified recency are explicitly disclosed.

Phase 1's Decimal calculations, positive-baseline rules, unit verification, period
validation, duplicate rejection, and original response hashes remain in force.
The frontend also validates the response schema and evidence-reference graph before
showing any report. It rounds display cards to two decimals using decimal.js;
full-precision strings and original JSON remain available in the evidence panel.

## Validation status and remaining uncertainty

Automated tests exercise successful model selection through mocks, invalid references,
extra unsupported prose, refusal, timeout, malformed responses, compliance-sensitive
questions, and deterministic fallback. Mock success is not a claim of live model
availability. Live provider verification requires configured credentials and a
compatible deployed model. See TESTING.md for the actual checks run.

## Gemini OpenAI-compatible verification (2026-10-20)

Configured target: `gemini-2.5-flash` at
`https://generativelanguage.googleapis.com/v1beta/openai`.
Google documents the same Bearer-authenticated Chat Completions route and
schema-based structured output in its [compatibility guide](https://ai.google.dev/gemini-api/docs/openai#structured-output).
The existing request therefore retains `response_format=json_schema`,
`strict=true`, and `max_completion_tokens=1000`. No schema downgrade, additional
provider call, automatic model replacement, or evidence-validation change was made.

One live call used explicitly marked synthetic test observations, never real
financial statements or the user's original question. It returned HTTP 404 with
an unreadable/non-JSON response. The backend correctly remained in deterministic
mode with zero accepted interpretations. This does not establish successful live
support for either `strict=true` or `max_completion_tokens`; a 404 is insufficient
evidence to change those request parameters. Google Cloud documents
`max_completion_tokens` as an alias for `max_tokens` in its separate
[Vertex-compatible interface](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/multimodal/call-vertex-using-openai-library),
but that alone does not verify this Developer API endpoint.

Google's [model lifecycle notice](https://ai.google.dev/gemini-api/docs/deprecations/)
currently limits 2.5 access to prior active users. A new key/project may therefore
lack model access, but the exact cause of the observed 404 is not established.
Check model access and endpoint/network routing before retrying. Local credentials
were used only for authentication, and neither key values nor sensitive headers
were printed. The local `.env`, model selection, production AI code, financial
logic, and frontend were not changed.

Added mock-based Gemini contract/failure tests verify the exact URL, schema and
token parameters, available evidence references, sanitized HTTP 404 fallback,
malformed output, invented references, and unsupported numerical prose. Mock
success does not imply live provider success.

## Verified replacement model (2026-10-20)

The earlier Gemini 2.5 failure is superseded by successful live verification of
`gemini-3.5-flash-lite`, selected from the authenticated official model listing.
The [official model page](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite)
documents structured-output support. In this environment, basic Chat Completions
and the exact existing strict-schema request both returned HTTP 200.
`max_completion_tokens=1000` and `strict=true` required no parameter adaptation.
This verifies the current StockLens schema, not every possible JSON Schema.

Only after this success was local `LLM_MODEL` updated; the API key and all other
variables remained unchanged. A subsequent full StockLens research request with
real Fuyao data returned `interpretation_mode="llm"`, three validated interpretations,
and complete financial metrics. No provider-specific production code change or
safety relaxation was necessary. Restart any existing backend process to load
the updated `.env`; already exported environment variables still take precedence.
