# Odyssey

**A conversational AI agent that plans and books an entire trip in one conversation.**

Built for the **Google for Startups AI Agents Challenge** (Track 1 — Build / Net-New Agents).
Odyssey is a travel concierge on **Google ADK + Gemini** that captures a traveller's intent in
plain language, **negotiates over A2A** with specialist flight / hotel / activities merchant agents
(each a **UCP** merchant over real Amadeus inventory), assembles a single budget-respecting trip
cart, and — only after explicit user confirmation — completes every booking via **AP2** signed
Intent / Cart / Payment mandates. The whole trip is booked without leaving the chat.

> ⚠️ **Demo / hackathon project.** Payments are **simulated** — AP2 signatures are stubbed and
> clearly labelled; **no real money moves** and no live payment rail is called.

## Quickstart

```bash
# 1. Create virtualenv and install all dependencies (including dev extras)
uv venv --python 3.12 && uv pip install -e ".[dev]"

# 2. Copy env template — the default ODYSSEY_DATA_MODE=SEED needs NO API keys
cp .env.example .env
#    (edit .env only if you want live Amadeus data or the adk web concierge)

# 3. Terminal 1 — start the three merchant servers
./scripts/run_merchants.sh

# 4. Terminal 2 — start the ADK concierge UI
#    Requires GOOGLE_API_KEY (free Google AI Studio key) set in .env
./scripts/run_web.sh
```

Then open **http://localhost:8000**, select **`odyssey_concierge`**, and try:

> "Plan a 5-day trip to Bali (DPS) from JFK, 2 people, Sep 1–6 2026, total budget $2500, beachy and foodie."

**Key notes:**

- `GOOGLE_API_KEY` (from [Google AI Studio](https://aistudio.google.com/)) is required **only** to run the live
  LLM concierge (`./scripts/run_web.sh`). The merchant servers and the full test suite run
  **fully offline** in SEED mode — no API key needed.
- Run tests offline at any time: `uv run pytest`

> ⚠️ **Payments are SIMULATED.** AP2 signatures are stubbed and clearly labelled throughout
> the code. **No real money moves and no live payment rail is called.**

## Testing access

For judges evaluating Odyssey without credentials:

| What | How | Keys needed? |
|------|-----|:---:|
| Merchant servers (flight / hotel / activity inventory + UCP/A2A endpoints) | `./scripts/run_merchants.sh` | None — uses `ODYSSEY_DATA_MODE=SEED` |
| Full offline test suite (41 tests, 2 skipped) | `uv run pytest -q` | None |
| Live concierge chat UI (`adk web`) | `./scripts/run_web.sh` | Free [Google AI Studio key](https://aistudio.google.com/) in `.env` |

**Recommended judge flow (zero-cost):**

1. `cp .env.example .env` — defaults are already correct for SEED mode.
2. `./scripts/run_merchants.sh` — brings up all three merchant agents.
3. `uv run pytest -q` — confirm the full suite is green (no keys required).
4. (Optional) Add a free `GOOGLE_API_KEY` to `.env`, then `./scripts/run_web.sh` → open http://localhost:8000.

## Status

**MVP implemented** — a full flight + hotel + activities trip books end-to-end in SEED mode
(intent → A2A negotiation → UCP `create_checkout` → confirmation-gated UCP `complete_checkout`).
**41 tests passing, 2 skipped** (the 2 skips are the live-LLM tests that need a `GOOGLE_API_KEY`).
Consciously deferred to Phase 2: CartMandate-expiry re-quote, merchant-timeout re-plan, multi-round
counter-offers, dual agent-card-path probing.

See:
- **Design spec:** [`docs/superpowers/specs/2026-06-02-odyssey-design.md`](docs/superpowers/specs/2026-06-02-odyssey-design.md)
- **Grounded protocol reference:** [`docs/PROTOCOL-REFERENCE.md`](docs/PROTOCOL-REFERENCE.md)
- **Implementation plan:** [`docs/superpowers/plans/2026-06-02-odyssey-build.md`](docs/superpowers/plans/2026-06-02-odyssey-build.md)

## Stack

Gemini (`gemini-2.5-flash`) · Agent Development Kit (`google-adk[a2a]`) · Agent2Agent (`a2a-sdk`) ·
Agent Payments Protocol (`ap2`) · Universal Commerce Protocol (`ucp-sdk` schemas) · MCP (JSON-RPC 2.0) ·
FastAPI · Amadeus Self-Service APIs.

## Attribution

Borrows architectural patterns from Google's Apache-2.0 reference code (AP2 samples, the
ADK + AP2 + UCP codelab). Google © for the protocols and reference implementations.
