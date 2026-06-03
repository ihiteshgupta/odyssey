# Odyssey — Business Case

**Google for Startups AI Agents Challenge · Track 2: Optimize (Existing Agents) · Region: APAC**

---

## The Problem: Unmanaged Corporate Travel Leakage

APAC SMB and mid-market companies — too small for a legacy Travel Management Company
(TMC) yet large enough to run significant travel budgets — overwhelmingly buy travel
through consumer OTAs (Expedia, Booking.com, Google Flights). The result is *unmanaged
travel*: bookings made outside any policy, on personal cards or corporate cards with
no pre-approval gate, generating receipts that arrive in expense reports days later.
Industry research consistently estimates that unmanaged-travel programmes leak
**10–20% of total travel spend** to out-of-policy purchases — booked at consumer prices,
with zero enforcement at the point of sale.[^1]

Finance leaders cannot fix this with legacy tooling. Enterprise TMCs (Concur, Navan,
TravelPerk) require IT implementation, per-seat licensing, and minimum-commitment
contracts that don't fit a 20-person regional office or a 200-person scale-up. The
gap between "too small for a TMC" and "too big to ignore the waste" is exactly where
the leakage lives.

---

## The Buyer and Beachhead

**Primary buyer:** Finance / ops leads at APAC SMBs and mid-market firms
(~50–500 employees, $250K–$5M annual travel spend).

**Beachhead:** Singapore, India, and Australia-based tech and professional-services
firms that already transact in USD/SGD/AUD, travel frequently to regional hubs
(Bali, Bangkok, Tokyo, Seoul), and are early adopters of AI-native tooling — the same
cohort that adopted Notion, Linear, and Ramp before their legacy peers.

**Decision driver:** The buyer is not looking for a travel chatbot. They want a
**governance artefact** — a non-repudiable record showing that every booking was
pre-approved against a budget, that the agent could not have spent more than
authorised, and that finance can pull a cryptographic audit trail at any time.
This is the insurance policy that makes the CFO comfortable letting AI touch the
card.

---

## Why Now: The Protocol Rails Just Arrived

Three converging protocol launches create a narrow first-mover window:

| Date | Event |
|------|-------|
| **Sept 2025** | Google launches **Agent Payments Protocol (AP2)** with 60+ partners including Mastercard, Amex, and PayPal — the first production-ready signed-mandate payment rail for AI agents.[^2] |
| **2026 (announced)** | Google announces **Universal Commerce Protocol (UCP) for Lodging** — extending the vendor-neutral checkout abstraction to hotels, the largest single line-item in corporate travel.[^3] |
| **Now** | **Agent2Agent (A2A)** is live and open — enabling multi-vendor negotiation across independent merchant agents without a single platform owning the inventory. |

Odyssey is a **first-mover native implementation** of all three protocols in combination —
A2A negotiation + UCP checkout + AP2 signed mandates — applied to the exact vertical
(corporate travel) that Google's own launch partners (Mastercard, Amex) serve.
No incumbent TMC is rebuilding on this stack; legacy tools are locked into per-OTA
partnerships and proprietary checkout flows.

---

## The Solution

Odyssey is a multi-agent concierge that plans and books a complete multi-vendor
business trip in one conversation. A planner agent (Google ADK + Gemini 2.5 Flash
on Vertex AI) accepts a natural-language brief ("Bali, 2 people, $2,500, Sep 1–6"),
splits the budget algorithmically across flights, hotel, and activities, and
**negotiates each slice independently** with a separate specialist merchant agent
over A2A — cross-process, not in-memory. The merchants return offers; the concierge
assembles the lowest-cost compliant itinerary; and then — and only then — asks the
traveller for explicit confirmation.

Two gates block every checkout: a **deny-by-default budget/cart guardrail**
(`before_tool_callback`) that hard-blocks any checkout if the cart total exceeds
the authorised budget or if no cart exists, and a **non-skippable human confirmation**
(ADK `require_confirmation`) that the agent cannot bypass. Only after both gates pass
does the concierge complete each booking via AP2 signed Intent → Cart → Payment mandates
— a tamper-evident chain that records *what was authorised, by whom, within what
budget*. The mandate is verified server-side by the merchant before the booking
confirms.

This is not a trip-planning chatbot. The governance layer — the signed mandate chain
plus the deny-by-default guardrail — is the product thesis. Research consistently
shows that a large share of enterprise buyers distrust fully-autonomous purchasing;[^4]
**friction is a feature** here, not a bug.

---

## Moat

1. **Cryptographic audit trail.** AP2 signed mandates produce a non-repudiable record
   that single-OTA chatbots (which complete a consumer transaction and email a receipt)
   structurally cannot replicate. Finance gets the proof the auditor asks for.

2. **Vendor-neutral multi-vendor negotiation.** A2A lets Odyssey negotiate across any
   merchant that publishes an A2A agent card + UCP endpoint — without being locked to
   one OTA's inventory. As the protocol ecosystem grows (60+ AP2 partners in Sept 2025),
   Odyssey's negotiation surface grows for free.

3. **First-mover on Google's 2026 commerce stack.** A2A + UCP + AP2 is Google's bet
   on how agentic commerce settles. Odyssey is a reference implementation of that stack
   in a vertical Google's own payment partners serve. This creates an early-partner
   flywheel with card networks and travel merchants that will be costly for later
   entrants to replicate.

---

## Monetization

**Primary revenue: take-rate on Gross Booking Value (GBV).**
Target blended take-rate 2–4% of GBV — consistent with modern B2B travel platforms.
At $500K average annual travel spend per account and a 50-account design-partner
cohort, that is $500K–$1M ARR at the Series-A gate, entirely usage-based and
directly correlated with value delivered.

**Secondary revenue: per-seat governance SaaS.**
A $10–25/seat/month governance module (audit dashboard, policy configuration,
budget allocation UI) sold to the finance buyer — decoupled from booking volume,
providing a recurring floor.

**Comparable:** Navan (formerly TripActions) went public in 2025 at approximately
**$6.2B valuation, ~90% usage-based revenue**.[^5] Navan serves the mid-enterprise
segment; Odyssey targets the underserved SMB/lower-mid-market that Navan's minimum
commitments price out — and does so natively on the 2026 AI-agent commerce stack.

---

## Market Sizing

| Level | Figure | Basis |
|-------|--------|-------|
| **TAM** — global corporate travel market | ~$1.4 trillion (2024, recovering to pre-pandemic trajectory) | GBTA Global Business Travel Forecast 2024[^6] |
| **SAM** — APAC corporate travel, unmanaged-leakage pool | APAC corporate travel is estimated at ~$700 billion by 2027 (GBTA); unmanaged-travel leakage is the 10–20% slice without a policy enforcement point — implying a **serviceable spend pool of ~$70–140B** in APAC alone | GBTA Asia Pacific[^7]; leakage rate is industry-range estimate |
| **SOM** — reachable via design-partner SMB accounts | Take-rate on GBV from a 50–200 account beachhead cohort; at 2–4% blended rate on a $25–50M GBV base = **$500K–$2M ARR** in Year 1–2 | Internal estimate |

> Numbers are estimates. TAM/SAM figures cite published industry sources; SOM is modelled
> from first-principles assumptions about account size and take-rate — not a commitment.

---

## Honesty Box: What's Real Today vs. Roadmap

| Capability | Status |
|------------|--------|
| Multi-agent A2A negotiation across 3 merchant Cloud Run services | **Live** (verified cross-process, 2026-06-02) |
| UCP checkout (create + complete) via MCP/JSON-RPC | **Live** |
| Deny-by-default guardrail + non-skippable HITL confirmation | **Live** (59 tests, safety eval block-rate 100%) |
| AP2 Intent → Cart → Payment mandate chain | **Live structure; signatures simulated** (`STUB-SIG:` SHA-256 — NOT real ECDSA) |
| Public demo on Google Cloud Run (asia-south1) | **Live** at https://odyssey-concierge-4ha6ffo6hq-el.a.run.app |
| Real payment cryptography (ECDSA P-256) | **Roadmap** — design is correct, real signing is a library swap |
| Live Amadeus inventory (flights / hotels / activities) | **Roadmap** — connector built, SEED fallback active by default |
| Multi-round counter-offer negotiation | **Roadmap** (Phase 2) |
| CartMandate expiry / re-quote | **Roadmap** (Phase 2) |
| Policy configuration UI + audit dashboard | **Roadmap** (governance SaaS line) |

---

## Footnotes

[^1]: GBTA / BTN industry surveys consistently report 10–20% of unmanaged corporate
travel spend goes to out-of-policy bookings. No single public number — this is a
widely-cited industry range used by TMCs in their marketing and by GBTA in member
research. Treat as an estimate.

[^2]: Google AP2 (Agent Payments Protocol) public launch, Sept 2025.
https://developers.google.com/agent-payments

[^3]: UCP for Lodging announced at Google I/O 2025 / Cloud Next 2026 cadence.
https://developers.google.com/commerce/ucp

[^4]: Edelman Trust Barometer 2025 and multiple enterprise-AI adoption surveys
(McKinsey Global Survey on AI, 2024–25) report that buyer concern about autonomous
AI taking financial actions without human approval remains the top trust barrier for
enterprise AI adoption.

[^5]: Navan (TripActions) IPO/valuation reporting, 2025. Revenue structure from
S-1/investor materials. ~$6.2B figure is from public reporting; verify against
current filings before citing in a regulated context.

[^6]: GBTA (Global Business Travel Association) Global Business Travel Forecast 2024.
https://www.gbta.org/blog/gbta-releases-2024-business-travel-forecast/

[^7]: GBTA Asia Pacific regional data; ~$700B estimate for APAC corporate travel
by 2027 is from GBTA regional reporting and is widely re-cited by travel industry
analysts. Treat as an estimate pending latest GBTA release.
