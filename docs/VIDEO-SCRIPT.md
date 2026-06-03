# Odyssey — 3-Minute Demo Shooting Script (Track 2 · Optimize)

**Goal:** win the "prove it got more reliable" contest. Every beat lands a **screenshot-able number** or a **visible reliability behaviour**. No "isn't this cool" filler.

**Target length:** ≤ 3:00 (hard cap). **Format:** screen-capture (OBS) + voiceover. Mark **"Not for Kids"**, upload **unlisted/public** (never private).

---

## Pre-stage checklist (do BEFORE recording — never gamble on live latency)

- [ ] Terminal 1: `ODYSSEY_DATA_MODE=SEED uv run pytest -q` ready to run (shows **75 passed, 3 skipped**).
- [ ] Terminal 2: `uv run pytest tests/test_safety_eval.py -v -s` ready (prints the safety-metrics ASCII table).
- [ ] Terminal 3: `uv run adk eval odyssey/concierge evals/odyssey.evalset.json --config_file_path test_config.json` (or the pytest path) ready, creds exported — pre-run once so it's warm.
- [ ] Browser tab A: the **live concierge URL** (public access restored — policy lifted), a Bali brief pre-typed but not sent.
- [ ] Browser tab B: **Cloud Trace / Agent Engine** Traces view of a prior run, zoomed to the A2A spans.
- [ ] Browser tab C: VAPO `optimized_results.json` (original → optimized score) open.
- [ ] Concierge + merchant logs tailing in a visible pane — confirm a prior run shows `negotiate[hotel] via A2A slice=1000 fits=True`, `a2a_roundtrip_ms=…`, and `cost[hotel] … cost_usd=… estimated=…`.
- [ ] One **adaptive re-negotiation** scenario rehearsed: a budget so tight one merchant's cheapest doesn't fit → concierge re-allocates the slice → books in budget.
- [ ] Metric title-card rendered (see 0:00).

---

## The script

| Time | Visual (screen) | On-screen text / overlay | Voiceover |
|------|-----------------|--------------------------|-----------|
| **0:00–0:15** | Full-bleed **metric title card**, then hard-cut to the running `test_safety_eval.py` table. | `100% guardrail block-rate · 0 false bookings · 0 over-budget checkouts`  +  `A2A trajectory: falsely-green → honest → 1.0` | "Odyssey is autonomous corporate travel that finance will actually approve — and I'll prove it with numbers, not adjectives. 100% of unsafe checkouts blocked. Zero false bookings. And a trajectory eval that went from lying-green to genuinely passing." |
| **0:15–0:35** | `docs/architecture.png` — pan across the 4 services + A2A/UCP/AP2 edges. | Lower-third: `4 Cloud Run services · A2A · UCP · AP2 · Gemini 2.5 Flash on Vertex` | "Four agents negotiate a real multi-vendor trip cross-process over Google's own A2A protocol, settle over UCP, and gate every booking behind a signed AP2 mandate chain. It already runs in production. For Track 2, I made it *provably* reliable." |
| **0:35–1:05** | Run the **ADK eval** live; the trajectory table resolves to **1.0**. Cut to the cascade-fix commit log (`88988d8 → 24d7030 → 1b80d5e`). | `tool_trajectory_avg_score = 1.0`  ·  `the "A2A 3-bug cascade"` | "Here's the headline. An in-process fallback was silently masking real cross-service failures — my tests were green while the agents never actually talked. I made the eval catch the lie first, then fixed the root cause. Honest-tests-first: falsely-green, to honest, to genuinely 1.0." |
| **1:05–1:25** | Browser tab C: VAPO before/after scores side by side. | `Vertex Prompt Optimizer (VAPO)` · `system instruction: ‹X%› → ‹Y%›` (judged by Gemini) | "Then I ran Google's own optimization stack — Vertex Prompt Optimizer data-drove the concierge's budget-negotiation instruction, and the Gen AI Eval Service scored the lift. The instruction got measurably better, automatically." |
| **1:25–1:55** | **The adaptive re-negotiation, live.** Tight-budget Bali brief → one merchant doesn't fit → logs show the slice re-allocated → trip books in budget. | Highlight log lines: `via A2A … fits=False` → re-allocate → `fits=True` · `a2a_roundtrip_ms=…` · `cost_usd=… estimated=…` | "This is the agent being an agent. The hotel slice doesn't fit the budget — so the concierge re-allocates across vendors and re-negotiates until the whole trip fits. Real cross-process A2A, with per-turn latency and cost logged for every call." |
| **1:55–2:20** | Trigger an **over-budget checkout** → guardrail **DENIES** on screen. Then a real booking → **HITL gate** blocks until you click approve. | `deny-by-default · fails CLOSED on missing budget` · `non-skippable human confirmation` | "And the trust spine. Try to check out over budget — denied, fail-closed. Try a real booking — it stops dead at a human-confirmation gate the agent cannot skip. It literally cannot spend money it wasn't authorized to." |
| **2:20–2:35** | ~3-second montage: Cloud Trace **A2A span DAG** → token/cost/latency dashboard → CI green with the test count. | `Cloud Trace · 75 passed / 3 skipped · ruff clean` | "Every tool call and Gemini invocation is traced; cost and latency are on a dashboard; the whole thing is gated in CI. Production-grade, not a notebook." |
| **2:35–3:00** | Business slide: TAM/wedge + the live public URL on screen. End on the AP2 audit-trail line. | `APAC SMB travel · protocol-native first-mover on A2A+UCP+AP2` · lower-third disclosure (below) | "The buyer isn't shopping for a travel bot — they want a governance artefact: a non-repudiable record that every booking was pre-approved against a budget the agent couldn't exceed. That's the product. Friction is the feature. Thanks for watching." |

---

## Persistent lower-third (last 5 seconds, AP2 honesty)

> *AP2 signatures are simulated (`STUB-SIG:` SHA-256, not ECDSA P-256) — no real money moves. Server-side mandate verification genuinely runs (recompute-and-compare); real ECDSA signing is a roadmap library swap.*

(Matches the corrected `DEVPOST.md` disclosure and the code in `odyssey/protocols/ap2_adapter.py` — say nothing the code doesn't back.)

---

## Production notes

- **Pace:** 0:00–0:15 is the whole game — lead with the number, never with "hi, this is…". If a judge stops at 15 seconds they should already know the thesis.
- **No live-latency gambles:** the Bali brief in tab A should be pre-typed; if a live model call is slow, cut to the pre-recorded log pane. Pre-warm the eval run so it returns fast on camera.
- **Show, don't tell agency:** the 1:25 re-negotiation is the single most important behavioural beat — it's what separates "agent" from "prompt chain." If you only nail one live moment, nail that one.
- **Honesty reads as strength:** keep the AP2 disclosure visible — disclosed-stub builds trust; hidden-stub is a DQ risk.
- **Captions:** burn in the metric overlays; judges often watch muted on first pass.
- **Fallback cut:** if the live URL ever misbehaves, SEED mode runs the entire system offline with zero keys — you can record the whole thing locally and it's still "real."
