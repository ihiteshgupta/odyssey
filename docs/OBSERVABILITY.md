# Odyssey — Observability (Track 2 production-grade signal)

Three complementary signals make every Odyssey run inspectable. For the demo you
only need #1 and #2 (zero deploy risk); #3 is the Cloud Console "production-grade"
shot worth grabbing once.

## 1. Structured logs (always on)

Every negotiation emits machine-greppable lines (`server.py` raises `odyssey.*`
loggers to INFO; visible in `stdout` / Cloud Run logs):

| Signal | Example line | Source |
|---|---|---|
| Real A2A vs fallback | `negotiate[hotel] via A2A slice=1000 fits=True` | `odyssey/concierge/negotiate.py` |
| A2A round-trip latency | `a2a_roundtrip_ms=412.7 merchant=hotel slice=1000` | `odyssey/concierge/a2a_client.py` |
| Cost / turn | `cost[hotel] in_tokens=731 out_tokens=88 cost_usd=0.00044 estimated=False` | `odyssey/concierge/negotiate.py` |
| Merchant LLM usage (server-side) | `merchant_llm[hotel] prompt_tokens=731 output_tokens=88 total_tokens=819` | `odyssey/merchants/agents.py` |

`estimated=False` means the merchant threaded its real `usage_metadata` across A2A;
`estimated=True` is the honest ~4-chars/token fallback when the framework dropped it;
the in-process path logs a genuine `cost_usd=0.0` (no LLM call).

## 2. ADK dev-UI span tree (no deploy, recommended for the video)

The concierge serves the ADK dev UI (`get_fast_api_app(..., web=True)` in `server.py`).
Open the live concierge URL, run a trip, then the **Trace** / **Events** tab shows the
full multi-agent span tree — the coordinator's Gemini calls, each A2A negotiation, and
the UCP checkout — with timings. This is the cleanest "show the agency" shot and needs
no extra setup.

## 3. Cloud Trace Explorer (enable once for the production-grade shot)

ADK exports OpenTelemetry spans to **Cloud Trace** when `trace_to_cloud=True`
(`server.py:30`, gated by `ODYSSEY_TRACE_TO_CLOUD`). It's off by default because the
import-time exporter can delay Cloud Run's startup probe. To enable on the live services:

```bash
./scripts/enable_tracing.sh        # grants roles/cloudtrace.agent + flips the env (+ CPU boost)
# run a trip from the concierge, then:
#   https://console.cloud.google.com/traces/list?project=odyssey-hackathon-498211
./scripts/enable_tracing.sh --off  # revert if a service is slow to start
```

What you get: per-trip trace = a DAG of spans (Gemini invocations + A2A tool calls
across the separate `odyssey-concierge` / `odyssey-*` services), with latency per span —
the literal cross-process A2A negotiation, visualised. Pair it with Cloud Run's built-in
**Metrics** tab (request latency, instance count) for the token/latency/cost dashboard beat.

> On **Vertex AI Agent Engine** (not used here — Odyssey runs on Cloud Run) the
> equivalent is `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true` +
> `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`; the Unified Trace Viewer
> renders the same span tree. Listed here only as the migration path.

## Video shots to grab (maps to `docs/VIDEO-SCRIPT.md` 2:20–2:35)

1. The log pane mid-trip: `via A2A … fits=True`, `a2a_roundtrip_ms=…`, `cost_usd=… estimated=…`.
2. The ADK dev-UI Trace tab span tree (or Cloud Trace Explorer DAG).
3. Cloud Run Metrics latency chart + CI green with the test count (`75 passed, 3 skipped`).
