# Odyssey — the trust-and-control layer for autonomous business travel

**Google for Startups AI Agents Challenge · Track 2: Optimize (Existing Agents) · Region: APAC**

> Live demo: https://odyssey-concierge-4ha6ffo6hq-el.a.run.app (Cloud Run, asia-south1, scale-to-zero)
> Repo: github.com/ihiteshgupta/odyssey

---

## The one-paragraph story

Odyssey is a production multi-agent corporate-travel concierge: a planner agent (Google ADK + Gemini 2.5 Flash on Vertex AI) negotiates a budget-respecting, multi-vendor trip — flights, hotel, activities — over **A2A** with three independent merchant agents, assembles the cheapest compliant itinerary over **UCP**, and books nothing without passing two gates: a deny-by-default budget guardrail and a non-skippable human confirmation, settled as a signed **AP2** Intent→Cart→Payment mandate chain. For **Track 2 (Optimize)** we did not add features — we made the agent *provably* reliable. The headline optimization is the **A2A 3-bug cascade fix**: an in-process fallback was silently masking real cross-process A2A failures, so the agent looked "green" while never actually negotiating between services. We adopted an honest-tests-first discipline — make the eval catch the lie, fix the root cause, then prove the real cross-service trajectory — and wired that into the new Google reliability toolchain (ADK `adk eval` + evalset in CI, Vertex Prompt Optimizer / VAPO, Gen AI Eval Service, and Cloud Trace / Agent Engine for per-turn cost & latency). The result: a falsely-green agent became an honestly-tested one, and then a genuinely-passing one.

---

## Before → After (the optimization scoreboard)

This is the first screen. Numbers marked `‹…›` are placeholders for artifacts still being captured from the live runs; everything else is asserted today by `tests/test_safety_eval.py` (runs fully offline, in CI).

| Metric | Before (pre-optimization) | After (current) | Source |
|---|---|---|---|
| Real cross-process A2A negotiation | **Masked** — in-process fallback ran; looked green, never crossed services | **Live & verified** — `negotiate[hotel] via A2A slice=1000 fits=True` (not fallback) | `docs/DEPLOYMENT.md`; commits `88988d8` → `24d7030` → `1b80d5e` |
| A2A trajectory eval | Falsely green (fallback hid the failure) | Honest → genuinely **1.0** on the happy-path trajectory | `evals/odyssey.evalset.json` (`adk eval`) |
| Guardrail block-rate (unsafe checkouts denied) | `‹before-capture›` | **100% (6/6)** unsafe calls denied | `tests/test_safety_eval.py` |
| False bookings (within-budget mismatch + empty cart) | `‹before-capture›` | **0** | `tests/test_safety_eval.py` |
| Over-budget checkouts allowed | `‹before-capture›` | **0** (fail-closed on missing budget) | `odyssey/concierge/guardrail.py` |
| Safe calls wrongly blocked (false positives) | `‹before-capture›` | **0** (3/3 safe calls allowed) | `tests/test_safety_eval.py` |
| Offline test suite | `‹before-capture›` | **75 passed, 3 skipped** (skips need a Gemini key) | `uv run pytest -q` |
| Prompt-optimized success (Vertex Prompt Optimizer / VAPO) | `‹VAPO before X%›` | `‹VAPO after Y%›` | VAPO run — pending |
| Cost / full multi-agent turn | `‹before-capture›` | ~**$0.02** / turn (Vertex `gemini-2.5-flash`) | `docs/DEPLOYMENT.md` |
| Idle infra cost | n/a | ~**$0** (scale-to-zero, `--min-instances=0`) | `docs/DEPLOYMENT.md` |

The deterministic safety eval prints this judge-legible table (`uv run pytest tests/test_safety_eval.py -v -s`):

```
╔══════════════════════════════════════════════════════════════════════╗
║                     ODYSSEY  SAFETY  EVAL                          ║
╠══════════════════════════════════════════════════════════════════════╣
║  guardrail_block_rate  =  100%  (6/6 unsafe calls denied)          ║
║  unsafe_allowed        =  0   (safe calls incorrectly blocked: False)   ║
║  false_bookings        =  0   (within_budget mismatches + empty-cart)  ║
║  simulated_only        =  PASS  (no real charges in finalize_trip)     ║
╚══════════════════════════════════════════════════════════════════════╝
```

---

## Five production properties (each tied to a real artifact)

**1. Observability — you can see every negotiation and what it cost.**
The concierge emits INFO-level traces of the live A2A round-trip — e.g. `negotiate[hotel] via A2A slice=1000 fits=True` (concierge side) and `POST / 200` + `convert_event_to_a2a_message` (merchant side) — which is exactly how the masked-fallback bug was finally caught: the log proves the call crossed a process boundary instead of short-circuiting in-memory. Per-turn cost (~$0.02 for a full multi-agent turn on Vertex `gemini-2.5-flash`) and latency are observable, with opt-in Cloud Trace on the concierge (`ODYSSEY_TRACE_TO_CLOUD`, commit `11cbd95`) feeding Agent Engine. *Files:* `odyssey/concierge/negotiate.py`, `docs/DEPLOYMENT.md`.

**2. Guardrails — deny-by-default, fail-closed.**
`before_tool_callback` in `odyssey/concierge/guardrail.py` intercepts every tool dispatch. A checkout tool (`complete_trip` / `complete_purchase` / `complete_checkout`) is refused unless a non-empty cart exists AND `sum(cart prices) ≤ total_budget`. Critically, **missing `total_budget` denies the checkout** — "this is a payment gate, so we must not allow a checkout to proceed when we cannot verify the spend is within the user's budget." Combined with the HITL gate, the agent literally cannot spend money it wasn't authorized to. *Files:* `odyssey/concierge/guardrail.py`, `odyssey/concierge/agent.py` (`require_confirmation=True` on `complete_trip`).

**3. Evals — adversarial, deterministic, and in CI.**
`tests/test_safety_eval.py` runs fully offline in SEED mode (no LLM, no network, no key): 6 adversarial guardrail-block scenarios (all must DENY), 3 safe calls (all must ALLOW — zero false positives), 3 budget-level plan assertions, and a simulated-only check. It is the primary CI gate (`.github/workflows/ci.yml` runs ruff + full pytest on every push). The LLM-trajectory layer is `evals/odyssey.evalset.json` via `adk eval` — two cases: Bali $2500 happy-path (`plan_trip` fires first, `complete_trip` only after the user says "yes") and the infeasible $700 budget (`plan_trip` fires, `complete_trip` must NOT). *Files:* `tests/test_safety_eval.py`, `evals/odyssey.evalset.json`, `docs/EVAL.md`, `.github/workflows/ci.yml`.

**4. Cost — cheap per turn, free at rest.**
A full multi-agent turn (concierge + 3 merchant Gemini calls + UCP assemble/book) costs ~$0.02 on Vertex `gemini-2.5-flash`. All four services are `--min-instances=0` (scale-to-zero), so idle cost is ~$0 — a complete demo stays far under the hackathon credit. *Files:* `docs/DEPLOYMENT.md`.

**5. Deploy — four real Cloud Run services in asia-south1.**
`odyssey-concierge`, `odyssey-flight`, `odyssey-hotel`, `odyssey-activity` run on Google Cloud Run (Mumbai), one shared image, Gemini via Vertex AI on a runtime service account (no API key on the server). The full runbook — image build, go-public script, org-policy steps, isolated gcloud config — is reproducible. *Files:* `docs/DEPLOYMENT.md`, `scripts/go_public.sh`, `Dockerfile`.

---

## The headline Track-2 narrative: the A2A 3-bug cascade

**Incident.** The agent's eval and demo looked green — trips planned, budgets split, bookings "confirmed." But the multi-agent claim (concierge negotiates with *separate* merchant services over A2A) was not actually happening end-to-end on Cloud Run.

**Root cause.** `request_offers` had a convenience design: A2A is the primary path, but on *any* exception it falls back to an **in-process** `negotiate_offers` call (`odyssey/concierge/negotiate.py`). That fallback was masking three stacked, real cross-process bugs:
1. **`asyncio.run` inside ADK's running event loop** → "cannot be called from a running event loop" (the concierge calls A2A from inside ADK's loop). *Fixed in `88988d8`* by running the coroutine on a fresh loop in a worker thread — so the real cross-service call actually fires instead of silently falling back.
2. **Erroneous `await` on an async generator** → `a2a-sdk`'s `send_message` returns an async generator, not an awaitable; `async for event in await client.send_message(msg)` threw. *Fixed in `24d7030`* (drop the `await`).
3. **`find_offers` result nested under `.response`** → ADK surfaces the merchant tool result as an A2A DataPart wrapped one level deeper than the parser expected. *Fixed in `1b80d5e`* (unwrap `.response`). (Two earlier loop-safety fixes — `82f6755`, `88988d8` — got the A2A *card build* and *negotiate* to run inside the live loop in the first place.)

**Why honest-tests-first mattered.** Each bug, on its own, would have been hidden by the fallback: the agent kept "working" by quietly doing the in-process thing. The optimization discipline was to make the failure *visible* — surface the negotiation path in logs (`via A2A` vs `in-process`, commit `b0c8175`) and require the eval/deployment check to prove the call crossed a process boundary — before fixing anything.

**Measured result.** From **falsely-green** (fallback hid the failure) → **honest** (the path is logged and the eval can tell A2A from fallback) → **genuinely passing**: on 2026-06-02 the concierge planned a $1507 Bali trip across three separate Cloud Run merchant services, the HITL gate fired and was honored, and the booking completed with 3 UCP confirmation codes — concierge logs showing `negotiate[hotel] via A2A slice=1000 fits=True` and merchant logs showing the inbound `POST / 200`. The happy-path trajectory eval now scores 1.0 because it's measuring the real thing.

---

## Business case (the 30% pillar)

**Problem.** APAC SMB / mid-market companies (~50–500 employees, $250K–$5M annual travel spend) are too small for a legacy TMC (Concur, Navan, TravelPerk) yet large enough to leak budget. They buy travel on consumer OTAs with no pre-approval gate — *unmanaged travel* that industry research puts at **10–20% of total travel spend** lost to out-of-policy bookings.

**Market.**
- **TAM** — global corporate travel: **~$1.4 trillion** (2024, GBTA Global Business Travel Forecast).
- **SAM** — APAC corporate travel ~**$700B by 2027** (GBTA); the unmanaged-leakage slice (10–20%) implies a **~$70–140B serviceable spend pool** in APAC alone.
- **SOM** — a 50–200-account design-partner beachhead at a 2–4% blended take-rate on a $25–50M GBV base → **$500K–$2M ARR** in Year 1–2.

**APAC-SMB wedge.** Beachhead: Singapore / India / Australia tech and professional-services firms that already transact in USD/SGD/AUD, travel to regional hubs (Bali, Bangkok, Tokyo, Seoul), and adopt AI-native tooling early — the cohort that took Notion, Linear, and Ramp before their peers.

**Why-now moat — protocol-native first-mover on Google's OWN stack.** Three rails just arrived: **AP2** (Sept 2025, 60+ partners incl. Mastercard, Amex, PayPal), **UCP-for-Lodging** (announced 2026), and **A2A** (live, open). Odyssey is a first-mover native implementation of **A2A + UCP + AP2 combined** in corporate travel — the exact vertical Google's own payment partners serve. No incumbent TMC is rebuilding on this stack; they're locked into per-OTA partnerships and proprietary checkout flows.

**The trust layer IS the product.** The buyer isn't shopping for a travel chatbot — they want a **governance artefact**: a non-repudiable record that every booking was pre-approved against a budget the agent *could not* exceed, with a cryptographic audit trail finance can pull on demand. The deny-by-default guardrail + non-skippable HITL + signed AP2 mandate chain are first-class components, not afterthoughts — the insurance policy that makes a CFO comfortable letting AI touch the card. **Friction is the feature.** This is what makes autonomous travel procurement/finance *actually approve*.

**Monetization.** Primary: take-rate on Gross Booking Value (target blended 2–4%, usage-based, value-correlated). Secondary: a $10–25/seat/month governance SaaS (audit dashboard, policy config, budget UI) for the finance buyer, decoupled from booking volume. Comparable: Navan (TripActions) went public in 2025 at ~**$6.2B valuation, ~90% usage-based revenue** — serving the mid-enterprise that prices out the SMB segment Odyssey targets.

*Full detail and citations: `docs/BUSINESS-CASE.md`.*

---

## Tools used / tech list

| Layer | Tech |
|---|---|
| Agent framework | **Google ADK** — `before_tool_callback` (guardrail), `require_confirmation` (HITL), `adk eval` |
| Reasoning | **Gemini 2.5 Flash on Vertex AI** (`gemini-2.5-flash`, runtime service account) |
| Agents talking | **A2A** (Agent2Agent) — cross-process `NegotiationRequest` DataParts between Cloud Run services (`a2a-sdk`) |
| Commerce | **UCP** (Universal Commerce Protocol) — `/.well-known/ucp` + `search_catalog` / `create_checkout` / `complete_checkout` |
| Money trust | **AP2** (Agent Payments Protocol) — signed Intent → Cart → Payment mandate chain (signatures simulated) |
| Tool binding | **MCP** (JSON-RPC 2.0) — UCP ops via `tools/call` |
| Reliability toolchain | **ADK eval + evalset in CI**, **Vertex Prompt Optimizer (VAPO)**, **Gen AI Eval Service**, **Cloud Trace / Agent Engine** |
| Runtime | **Google Cloud Run × 4** (asia-south1), FastAPI, scale-to-zero |
| Inventory | Amadeus Self-Service APIs (LIVE / SEED fallback) |

---

## Testing access

- **Live cloud demo (preferred):** https://odyssey-concierge-4ha6ffo6hq-el.a.run.app — pick `concierge`, ask for a trip ("Plan a 5-day Bali trip from JFK for 2, Sep 1–6 2026, budget $2500, beachy and foodie"). All four Cloud Run services (asia-south1) back it; Gemini via Vertex AI.
  - **Access note:** the services were made public for the verified 2026-06-02 run; public access requires relaxing the Workspace org policy `iam.allowedPolicyMemberDomains`. If the URL is behind auth at judging time, an org admin lifting that policy (or running `./scripts/go_public.sh`) restores public access with **no code change** — the steps are in `docs/DEPLOYMENT.md`.
- **Self-contained video fallback:** a recorded end-to-end walkthrough (plan → both gates fire → 3 UCP confirmations) is provided so judging never depends on the live policy state.
- **Reproducible runbook (zero keys):** `docs/DEPLOYMENT.md` plus the README judge flow —
  ```bash
  uv venv --python 3.12 && uv pip install -e ".[dev]"
  cp .env.example .env                 # ODYSSEY_DATA_MODE=SEED is default — no keys
  ./scripts/run_merchants.sh           # 3 merchant agents (A2A + UCP, SEED inventory)
  uv run pytest -q                     # 75 passed, 3 skipped, no API keys
  uv run pytest tests/test_safety_eval.py -v -s   # prints the safety metrics table
  ```

---

## Honesty disclosure

**AP2 mandate signing is simulated.** Signatures use a `STUB-SIG:` SHA-256 placeholder — **not** real ECDSA P-256 cryptography — and the merchant-side mandate **verification path is stubbed**, so no real money moves and no live payment rail is called. The mandate *structure* (Intent → Cart → Payment) and the server-side verification *logic shape* are in place; swapping in real ECDSA signing and a real verifier is a roadmap library swap, not a redesign.
