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

## Status

Design phase. See:
- **Design spec:** [`docs/superpowers/specs/2026-06-02-odyssey-design.md`](docs/superpowers/specs/2026-06-02-odyssey-design.md)
- **Grounded protocol reference:** [`docs/PROTOCOL-REFERENCE.md`](docs/PROTOCOL-REFERENCE.md)

## Stack

Gemini (`gemini-2.5-flash`) · Agent Development Kit (`google-adk[a2a]`) · Agent2Agent (`a2a-sdk`) ·
Agent Payments Protocol (`ap2`) · Universal Commerce Protocol (`ucp-sdk` schemas) · MCP (JSON-RPC 2.0) ·
FastAPI · Amadeus Self-Service APIs.

## Attribution

Borrows architectural patterns from Google's Apache-2.0 reference code (AP2 samples, the
ADK + AP2 + UCP codelab). Google © for the protocols and reference implementations.
