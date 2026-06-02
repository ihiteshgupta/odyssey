# Odyssey — GCP Deployment (Cloud Run + Vertex AI)

Deployed to a hackathon-credit GCP project on **2026-06-02**. Region **asia-south1** (Mumbai),
Gemini via **Vertex AI** (no API key — uses the runtime service account).

## What's live — **PUBLIC** ✅

**Try it:** **https://odyssey-concierge-4ha6ffo6hq-el.a.run.app** (ADK chat UI — pick `concierge`, ask for a trip).

| Service | URL | Access | Notes |
|---|---|---|---|
| `odyssey-flight` | https://odyssey-flight-4ha6ffo6hq-el.a.run.app | **public** | A2A card + UCP routes; card advertises its public URL |
| `odyssey-hotel` | https://odyssey-hotel-4ha6ffo6hq-el.a.run.app | **public** | same |
| `odyssey-activity` | https://odyssey-activity-4ha6ffo6hq-el.a.run.app | **public** | same |
| `odyssey-concierge` | https://odyssey-concierge-4ha6ffo6hq-el.a.run.app | **public** | ADK dev chat UI (`server:app` → `get_fast_api_app`) |

**Verified live (unauthenticated, 2026-06-02):** the concierge planned a $1507 Bali trip, the HITL
confirmation gate fired and was honored, and the booking completed with 3 UCP confirmation codes.
Public access required relaxing the org policy `iam.allowedPolicyMemberDomains` (Allow-All,
project-scoped) + `allUsers` run.invoker on all 4 services.

**Real cross-process A2A negotiation (verified):** the concierge splits the budget (45/40/15) and
negotiates each slice with a *separate* merchant Cloud Run service over A2A. Concierge logs show
`negotiate[hotel] via A2A slice=1000 fits=True` (not the in-process fallback), and merchant logs show
the inbound A2A message endpoint `POST / 200` + `convert_event_to_a2a_message`. The merchant agent runs
its own Gemini call, returns the `find_offers` result as an A2A DataPart, and the concierge assembles +
books over UCP (`POST /mcp`). This required fixing a 3-bug cascade the fallback had masked (asyncio.run
inside ADK's loop → erroneous `await` on the send_message async-generator → find_offers result nested
under `.response`).

- **Project:** `odyssey-hackathon-498211` · **Region:** `asia-south1` · **Billing:** linked (credit account).
- **Image:** one shared image `asia-south1-docker.pkg.dev/odyssey-hackathon-498211/odyssey/merchants:latest`
  — merchants set `MERCHANT_MODULE=odyssey.merchants.agents:<vertical>_app`; concierge sets `MERCHANT_MODULE=server:app`.
- **Runtime SA:** `odyssey-run@odyssey-hackathon-498211.iam.gserviceaccount.com` (has `roles/aiplatform.user`).
- **Data:** `ODYSSEY_DATA_MODE=SEED` (seeded inventory; no Amadeus key needed).

### Verified
- ✅ Merchant containers healthy (`/.well-known/ucp` serves; A2A card `url` = the public run.app URL — the Cloud Run A2A fix works).
- ✅ Concierge boots; `/list-apps` → `["concierge"]`.
- ✅ Vertex `gemini-2.5-flash` responds in `asia-south1` with this project's credentials.
- ⛔ **Public access blocked** by an inherited org policy `iam.allowedPolicyMemberDomains` (Domain-Restricted-Sharing) → all services currently require auth. End-to-end multi-agent test is deferred until public (below).

## Going public (one org-admin action + one script)

Services are private because the Workspace org policy blocks `allUsers`. The deployer SA (project Owner)
**cannot** override an org-level policy. An **org admin** of the hackathon account must do **one** of:

**A.** Console → IAM & Admin → **Organization Policies** → *Domain restricted sharing*
(`iam.allowedPolicyMemberDomains`) → Manage policy → **scope to project `odyssey-hackathon-498211`** →
set **Allow All** → Save. **— or —**

**B.** Grant the deployer SA org-level policy admin, then it sets the project override itself:
```bash
gcloud organizations add-iam-policy-binding <ORG_ID> \
  --member="serviceAccount:odyssey-deployer@odyssey-hackathon-498211.iam.gserviceaccount.com" \
  --role="roles/orgpolicy.policyAdmin"
# then: gcloud org-policies set-policy docs/gcp/allow-all-domains.yaml --project=odyssey-hackathon-498211
```

Then make all four services publicly invokable:
```bash
./scripts/go_public.sh      # adds allUsers run.invoker to all 4 services
```
After that, the **concierge URL is the public demo** (it calls the now-public merchants over A2A with no
auth change, and Gemini via Vertex). No code change is required to go public.

## Cost
Scale-to-zero (`--min-instances=0`) → ~$0 idle. Only real cost is Vertex `gemini-2.5-flash`
(~$0.02 per full multi-agent turn). A demo stays far under the $500 credit. Set a budget alert in
Billing → Budgets & alerts (recommended $50). For a live demo, optionally `--min-instances=1` on the
concierge to avoid cold-start, then set back to 0.

## Operator notes
- All gcloud work used an **isolated config** `CLOUDSDK_CONFIG=$HOME/.config/gcloud-odyssey` with the
  service-account key at `~/Projects/personal/.keys/odyssey-deployer.json` — the machine's default
  gcloud account/config was never touched. To resume:
  ```bash
  export CLOUDSDK_CONFIG="$HOME/.config/gcloud-odyssey"
  gcloud config set project odyssey-hackathon-498211
  ```
- Redeploy after a code change: rebuild the image (`gcloud builds submit --tag <IMG> .`) then
  `gcloud run deploy <svc> --image <IMG> ...` (or just `--image` update).
