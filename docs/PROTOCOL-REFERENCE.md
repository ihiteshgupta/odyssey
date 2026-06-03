# Odyssey — Protocol Reference (grounded, mid-2026)

> Source: adversarially-verified research sweep (UCP / A2A / AP2 / ADK / Amadeus),
> 2026-06-02. Every load-bearing assumption below was confirmed against primary
> sources (official docs + GitHub). Corrections to earlier assumptions are flagged.
> Pin exact versions during the build and re-verify dated UCP spec paths.

## 1. Verified stack

| Package | Version / install | Notes |
|---|---|---|
| `google-adk` | `pip install google-adk[a2a]` — pin **2.x** (≥2.1.0, released 2026-05-23) | A2A extras are mandatory for `to_a2a`/`RemoteA2aAgent`. |
| `a2a-sdk` | `pip install a2a-sdk` — pin exact (AP2 samples use `0.3.24`) | Helper locations moved (`a2a.utils` → `a2a.helpers`) in v1.0; pin to avoid import breakage. |
| `ap2` | `uv pip install git+https://github.com/google-agentic-commerce/AP2.git@<SHA>` | **NOT on PyPI** — `pip install ap2` fails. Pin a commit SHA, not `@main`. Import root is `ap2` (under `code/sdk/python`). |
| `ucp-sdk` | `pip install ucp-sdk` (PyPI; v0.3.0 2026-03-31). Import `ucp_sdk`. | **Schema-only** Pydantic models. No client/server/runtime. |
| `google-genai` | pin exact (AP2 samples: `1.66.0`; codelab: `>=1.27.0`) | Coupled to ADK version; do not mix loosely. |
| `fastapi` + `uvicorn` | `fastapi>=0.115.0`, `uvicorn>=0.34.0`, `httpx>=0.28.0` | For hand-written UCP merchant + client (codelab pattern). |
| `cryptography`, `jwcrypto` | `cryptography==46.0.5`, `jwcrypto` | Only if doing real AP2 SD-JWT signing. Skip for stubbed sim. |

**Gemini model ID (exact string for code):** use **`gemini-2.5-flash`** (GA, stable, recommended pinned) or `gemini-2.5-pro`. Avoid the floating `gemini-flash-latest` alias on regional/Vertex endpoints (e.g. us-central1) where it may not resolve. `gemini-3-pro-preview` is **discontinued** (~Mar 2026); `gemini-3.1-pro-preview` is preview-only (not GA as of 2026-06-02) — accept preview risk if used. Note `gemini-2.5-flash` has a published Vertex retirement date of 2026-10-16.

**Run commands:**
```bash
adk web <agents_dir>        # dev UI on http://localhost:8000 (renders confirmation dialogs)
adk run <agent_dir>         # interactive CLI
uvicorn module:a2a_app --host localhost --port 8001   # serve an exposed A2A agent
```
Do **not** confuse `adk web` (port 8000, bundled UI) with the standalone `google/adk-web` Angular dev repo (port 4200).

---

## 2. A2A (planner ↔ merchant agents)

**Agent Card path:** `/.well-known/agent-card.json` (spec v0.3.0, RFC 8615). Legacy `/.well-known/agent.json` (v0.2.5) is kept for back-compat. **Probe both** — ADK's fallback constant `AGENT_CARD_WELL_KNOWN_PATH` is still the legacy `agent.json` if `a2a-sdk` is absent, while current `a2a-sdk` uses `agent-card.json`.

Card fields: `name`, `url`, `description`, `version`, `provider`, `capabilities` (e.g. `streaming`, `pushNotifications`), `skills`, `default_input_modes`, `default_output_modes`, security schemes, `supports_authenticated_extended_card`.

**Expose an ADK agent (server side):**
```python
from google.adk.a2a.utils.agent_to_a2a import to_a2a
a2a_app = to_a2a(root_agent, port=8001)   # returns a Starlette app; auto-serves the card
```

**Consume a remote A2A agent (client side):**
```python
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent, AGENT_CARD_WELL_KNOWN_PATH
flight_agent = RemoteA2aAgent(
    name="flight_merchant",
    description="...",
    agent_card=f"http://host:8001/a2a/flight{AGENT_CARD_WELL_KNOWN_PATH}",
    use_legacy=False,            # quickstart sets this; constructor default is True
)
```
**Import precision (flagged):** `RemoteA2aAgent` is **not** re-exported from `google.adk.agents` — import from `google.adk.agents.remote_a2a_agent`. `from google.adk.agents import RemoteA2aAgent` will fail.

**Lower-level client (if not using ADK wrapper):** `A2ACardResolver.get_agent_card()` → `ClientFactory(ClientConfig(...)).create(card)` → `await Client.send_message(req)` (async iterator of events).

**Task lifecycle:** JSON-RPC methods `message/send`, `message/stream` (SSE), `tasks/get`, `tasks/cancel`, `tasks/resubscribe`, `tasks/pushNotificationConfig/{set,get,list,delete}`. `TaskState`: `submitted, working, input-required, auth-required, completed, canceled, failed, rejected, unknown`. Terminal = `completed/canceled/failed/rejected`; resumable = `input-required/auth-required`. Streaming emits `TaskStatusUpdateEvent`/`TaskArtifactUpdateEvent` and MUST close at a terminal state.

**Modeling negotiation (we MUST own this):** A2A has **NO native offer/counter-offer primitive**. We define our own offer schema and carry it in **`DataPart`** parts of a `Message` (not `TextPart`/`FilePart`). A negotiation thread = one `contextId` grouping multiple Tasks/Messages. Convention to standardize on:
- **(A)** Counter-offer = follow-up `Message` reusing the **same `taskId` + `contextId`** while the task sits in `input-required` — *chosen for Odyssey* (single bargaining round-trip).
- (B) Counter-offer = a new Task under the same `contextId` (spec's "refinement" example), optionally with `referenceTaskIds` — fallback if a task goes terminal.

Once a task reaches a terminal state it cannot resume, so a stalled negotiation must stay in `input-required` or be reopened as a new task under the same `contextId`.

---

## 3. UCP (commerce, merchant side)

**Discovery doc:** `GET /.well-known/ucp` — **public, no auth**. Top-level shape:
- `ucp` object: `version`, `services`, `capabilities`
- sibling `payment_handlers` (e.g. `com.google.pay`)
- sibling `signing_keys` (array of JWK public keys)

Services keyed by reverse-DNS (`dev.ucp.shopping`); capabilities by IDs `dev.ucp.shopping.{catalog,cart,checkout,order}`, `dev.ucp.common.identity_linking`. Each entry carries `version`, `spec`, `schema`, `transport`, `endpoint`, optional `extends` + `config`.

**Five capabilities:** Catalog, Cart, Checkout, Order, Identity Linking. **Fulfillment and Discount are Checkout extensions, not standalone.** Identity Linking is **OAuth 2.0**, not an MCP tool. Order is webhook/async (no confirmed synchronous MCP tool).

**MCP binding (JSON-RPC 2.0):** every UCP op is invoked via method **`tools/call`** with the op name in **`params.name`** and payload in **`params.arguments`**. Transport failures → JSON-RPC error; app outcomes → successful result wrapping the UCP envelope.

**Operation names a merchant MUST expose** (the assumed 5-method list was **incomplete** — it is 8):

| Capability | Operations | Key args |
|---|---|---|
| Catalog | `search_catalog`, `lookup_catalog`, `get_product` | search: `{query?, context?, signals?, filters?, pagination?}`; lookup: `{ids[]}`; get_product: `{id, selected?, preferences?}` |
| Checkout | `create_checkout`, `get_checkout`, `update_checkout`, `complete_checkout`, `cancel_checkout` | create: `{meta(ucp-agent), checkout}`; get: `{id}`; update: `{meta, id, checkout}`; complete: `{meta(ucp-agent + idempotency-key), id, checkout(payment creds)}`; cancel: `{meta(idempotency-key), id}` |

Existing-checkout ops use a top-level `id`; the `checkout` payload omits its own id. `create_checkout` returns the assigned `checkout.id`. **`complete_checkout`/`cancel_checkout` REQUIRE `meta.idempotency-key`.**

**SDK status (corrected assumption):** an official UCP Python SDK **does exist** (`ucp-sdk`, from `Universal-Commerce-Protocol/python-sdk`). But it ships **only Pydantic schema models** (`ucp_sdk.models.schemas.shopping.*`, `.transports`). **Use it for typed validation** (`Checkout.model_validate(...)`), but **hand-write the merchant server** (`GET /.well-known/ucp` + `POST /mcp` JSON-RPC handler) **and the `UCPClient`** yourself, exactly as the CineAgent codelab does. There is no `UCPClient`, FastAPI server, or transport layer in the package.

**No travel/lodging schema exists.** Lodging is roadmap-only behind a Google waitlist. Model hotels/flights/activities on the **generic `dev.ucp.shopping` catalog + checkout** primitives.

---

## 4. AP2 (signed payment mandates)

Three Pydantic mandate types in `ap2.models.mandate` (module constants: `INTENT_MANDATE_DATA_KEY='ap2.mandates.IntentMandate'`, `CART_MANDATE_DATA_KEY='ap2.mandates.CartMandate'`, `PAYMENT_MANDATE_DATA_KEY='ap2.mandates.PaymentMandate'`):

- **IntentMandate** — `user_cart_confirmation_required: bool=True`, `natural_language_description: str` (req), `merchants: list[str]|None`, `skus: list[str]|None`, `requires_refundability: bool|None=False`, `intent_expiry: str` (req).
- **CartMandate** — `contents: CartContents` (req), **`merchant_authorization: str|None`** (merchant signature). `CartContents`: `id`, `user_cart_confirmation_required`, `payment_request: PaymentRequest`, `cart_expiry`, `merchant_name` (all req).
- **PaymentMandate** — `payment_mandate_contents: PaymentMandateContents` (req), **`user_authorization: str|None`** (user signature). `PaymentMandateContents`: `payment_mandate_id`, `payment_details_id`, `payment_details_total: PaymentItem`, `payment_response: PaymentResponse`, `merchant_agent: str`, `timestamp` (defaults to UTC ISO-8601).

Payload reuses **W3C Payment Request** shapes (`ap2.models.payment_request`): `PaymentRequest{method_data, details, options?, shipping_address?}`, `PaymentItem{label, amount: PaymentCurrencyAmount, pending, refund_period:int=30}`, `PaymentCurrencyAmount{currency, value}`, `PaymentResponse`, `PaymentDetailsInit`, `PaymentMethodData`.

**Signing model:** CartMandate signed by merchant (`merchant_authorization`), PaymentMandate signed by user (`user_authorization`). Real signing uses **SD-JWT / KB-SD-JWT** delegation chains (joined by `~~`), **ES256 over SECP256R1 (P-256)** JWK keys, via the `MandateClient` class in `ap2.sdk.mandate` (`create / present / verify / get_closed_mandate_jwt`). Integrity binding via `compute_sha256_b64url` (`ap2.sdk.utils`).

**TWO incompatible layers exist — pick ONE up front:** the stable **types layer** (`IntentMandate/CartMandate/PaymentMandate` over W3C PaymentRequest, plain string auth fields) vs the newer **generated SDK** (`OpenCheckoutMandate/CheckoutMandate/PaymentMandate` + `MandateClient` + SD-JWT). Mixing causes field-name/signing mismatches.

**What Odyssey does:** target the **stable types layer** (string auth fields over the W3C PaymentRequest payload) but sign with **real ECDSA P-256**, not placeholder hashes. Build `IntentMandate → CartMandate → PaymentMandate`; `merchant_authorization` is a real ECDSA signature over the canonical CartMandate payload and `user_authorization` a real ECDSA signature over the PaymentMandate (see `odyssey/protocols/ap2_adapter.py`, `ECDSA-P256:` prefix). Verification recomputes the digest and checks the signature, so a tampered cart fails closed. **Honest caveat (documented loudly):** a single demo keypair derived from a fixed seed — this gives real cryptographic integrity / tamper-evidence, but is **not** a per-user PKI and **not** a live payment rail; no money moves. Watch `intent_expiry`/`cart_expiry` (required timestamps) — a long booking session can expire mid-checkout; build refresh/re-prompt logic.

Licensing: Apache-2.0 (AP2, a2a-x402, ucp-sdk). Codelab code = Apache-2.0; codelab prose = CC-BY-4.0 (don't copy prose verbatim). Retain LICENSE/NOTICE, attribute Google.

**Reference flow to borrow:** AP2 repo `code/samples/python/src/roles/shopping_agent_v2` wires mandates as ADK function tools (`assemble_and_sign_mandates_tool`, `check_constraints_against_mandate`, `create_checkout_presentation`, `create_payment_presentation`) on `google.adk.agents.Agent`. The CineAgent **scaffold (`UCPClient`, `AP2Handler`, mock FastAPI merchant) exists only in the codelab** — reproduce from the codelab text/download, it is **not** in any public GitHub repo.

---

## 5. Amadeus (real read-only inventory)

**Auth (single OAuth2 client_credentials key reaches all three APIs):**
```
POST https://test.api.amadeus.com/v1/security/oauth2/token
Content-Type: application/x-www-form-urlencoded
grant_type=client_credentials&client_id=<KEY>&client_secret=<SECRET>
→ access_token, expires_in ≈1799s (~30 min)
Use: Authorization: Bearer <access_token>
```
**Cache and reuse the token** — do not fetch one per call. Test host `test.api.amadeus.com` (free, cached/limited); prod `api.amadeus.com` (live, billed above free quota). Both share identical paths.

**The 3 read endpoints:**
1. **Flights:** `GET/POST /v2/shopping/flight-offers` — params `originLocationCode`, `destinationLocationCode`, `departureDate`, `adults` (+ `returnDate`, `currencyCode`, `max`, `nonStop`, `travelClass`). Response: `data[].id`, `data[].price.{total,currency,grandTotal}`, `itineraries[].segments[]`, `validatingAirlineCodes[]`, `travelerPricings[]`.
2. **Hotels (mandatory 2-step flow):** (a) **Hotel List** `GET /v1/reference-data/locations/hotels/by-geocode|by-city|by-hotels` → 8-char `hotelIds`; (b) **Hotel Search v3** `GET /v3/shopping/hotel-offers` with `hotelIds` (req), `adults` (req), `checkInDate`, `checkOutDate`, `roomQuantity`, `currency`. Single offer: `GET /v3/shopping/hotel-offers/{offerId}`. **v2.1 `/shopping/hotel-offers/by-hotel` and IATA/location params on hotel-offers are RETIRED** — do not use.
3. **Activities:** `GET /v1/shopping/activities` (`latitude`, `longitude`, `radius`), `GET /v1/shopping/activities/by-square` (`north/west/south/east`), `GET /v1/shopping/activities/{activityId}`. Response: `id`, `name`, `geoCode`, `rating`, `price.{amount,currencyCode}`, `bookingLink` (deep link only — no in-API booking on self-service).

**Limits:** test **10 TPS** (1 req/100ms), prod **40 TPS**; per-API monthly free-call quota (varies per API, summed across all your apps); **429** when exceeded. Add client-side throttling + backoff. Currency field differs per API (`currencyCode` flights / `currency` hotels / `price.currencyCode` activities) — normalize in a domain layer.

**Fallbacks (thinner, separate adapters):** Aviationstack (flights, ~100 live req/mo), Makcorps (hotel price compare), OpenTripMap (POIs).

---

## 6. Design adjustments — MUST change (vs. the initial Section 1/2 sketch)

1. **Orchestration primitive:** the Odyssey planner aggregates flight/hotel/activity results and composes an itinerary — use **`AgentTool`** (call-and-return), **NOT `sub_agents` transfer**. `sub_agents` hands off control and the coordinator does not automatically regain it. Import: `from google.adk.tools.agent_tool import AgentTool`. For remote merchants over A2A, `RemoteA2aAgent` is plugged in as a `sub_agent`/wrapped by `AgentTool` — verify session/`contextId` propagation across that boundary (open ADK issue #2956).
2. **UCP method set is larger than assumed:** design state machines/error handling for **all 8** of `search_catalog, lookup_catalog, get_product, create_checkout, get_checkout, update_checkout, complete_checkout, cancel_checkout`. Add `meta.idempotency-key` to complete/cancel to prevent double-booking/double-charge. Order is async/webhook — no synchronous fetch tool.
3. **Use `ucp-sdk` for schemas but still hand-write the transport.** The "no UCP SDK" assumption was wrong, but the conclusion (hand-write merchant + client) stands — the SDK has no runtime.
4. **AP2: pick ONE mandate layer** (the stable types layer for simulation) and isolate it behind an adapter — FIDO standardization (donated 2026-04-28) may rename `ap2.mandates.*` keys/fields.
5. **`ap2` is git-only:** pin a **commit SHA** in `pyproject.toml`, never `@main`.
6. **A2A negotiation schema is ours to define** — fix the offer/counter-offer convention (same-task `input-required`) before merchant agents diverge; carry payloads in `DataPart`.
7. **Hotels need a 2-call flow** — budget the extra round-trip and chunk `hotelIds`.
8. **Model pin:** use `gemini-2.5-flash` (GA), not `gemini-flash-latest` on Vertex regional endpoints, not the discontinued `gemini-3-pro-preview`.
9. **Probe both Agent Card paths** (`agent-card.json` and legacy `agent.json`).

---

## 7. Open risks to validate during build

- **HITL pause/resume reliability:** `FunctionTool(func, require_confirmation=True)` / `tool_context.request_confirmation(hint, payload)` (response read via `tool_context.tool_confirmation.{confirmed,payload}`; client returns a `function_response` named `adk_request_confirmation` with matching call `id`). Confirmed working in `adk web`, but open issues #3184/#3567 report it **not pausing/resuming inside `SequentialAgent`/custom orchestrators** and live streaming. **Test the exact agent tree you ship.** Also: `require_confirmation` does not yet apply to MCP tools (issue #3008). Feature is flagged `@experimental`.
- **Version coherence:** codelab pins loose ranges + FastAPI; AP2 samples pin exact + Flask/MCP/fastmcp. These are **not interchangeable** — pin one coherent set early. Validate `AgentTool`/confirmation APIs against the actual installed `google-adk` 2.x.
- **`a2a-sdk` version semantics:** confirm the pinned version exports `AGENT_CARD_WELL_KNOWN_PATH` as `agent-card.json`; helper imports moved to `a2a.helpers` in v1.0.
- **UCP spec versioning:** dated paths (`/2026-01-11/`, `/2026-04-08/`, `/latest/`) — pin one dated version and re-verify field/method names; confirm exact `meta` (ucp-agent) shape and response envelope.
- **AP2 layer details:** confirm whether the human-present demo verifies signatures cryptographically or accepts any non-empty auth string; reconcile `ap2.sdk.mandate` vs generated imports.
- **Amadeus:** test data is cached/non-live (not bookable); confirm per-API free quota, `hotelIds` comma-list limit + pagination, activities `radius`/`by-square` caps.
- **AP2 Mandates extension under UCP:** verify Buyer Consent / AP2 mandate requirements for agent-initiated (unattended) booking before relying on `complete_checkout` payment credentials.
