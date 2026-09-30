# Usage

This document covers the day-to-day workflow, assuming setup is already complete (see
[SETUP.md](SETUP.md) if not).

The workflow: HNI-01 publishes an AAS shell, HNI-02 retrieves it via EDC, modifies it, and sends
the result back to HNI-01 as a new "Zuliefererdaten" ("supplier data") submodel.

## Node-RED tabs and dashboard pages

Tab names (in the Node-RED editor) and dashboard page names/URLs differ:

| Flow tab (Node-RED editor) | Dashboard page | URL path |
|---|---|---|
| AAS to S3 Bridge | *(no dashboard — runs in the background)* | — |
| EDC Provider HNI-01 | **HNI-01 Provider** | `/provider` |
| EDC Consumer HNI-01 | **HNI-01 Consumer** | `/consumer` |
| EDC Consumer HNI-02 | *(widgets are on the "HNI-01 Consumer" page)* | `/consumer` |

> **Naming note:** "EDC Consumer HNI-01" is the tab whose *counterparty* is HNI-01 — it actually
> drives the HNI-02 connector's management API. Similarly "EDC Consumer HNI-02" drives HNI-01's
> own management API, acting as consumer against HNI-02.

## Step 1 — HNI-01: publish a shell

**Dashboard page "HNI-01 Provider" (`/provider`) → "Publish AAS Shell" panel**

1. Select a shell from the **existing shells** dropdown, or click **refresh** if a new shell is
   missing. Alternatively, enter a shell ID manually (e.g. `localhost/demo/aas/Kugelschreiber_TracePEN`).
2. Click **publish to bucket**.
3. Watch the status:
   - ⏳ *Publishing "..." ...*
   - ✅ *Published successfully: aas/....json (EDC offer registered)*
   - ❌ *Error (HTTP xxx): ...* — see Troubleshooting below

The shell is now in the R2 bucket and registered as an Asset + ContractDefinition on HNI-01.

## Step 2 — HNI-02: query the catalog and download the shell

**Dashboard page "HNI-01 Consumer" (`/consumer`)**

1. Select the provider: address-book dropdown → **HNI-01** (or manually: BPN
   `BPNL000000003HN1`, DSP URL `https://hni-01-dsp.c-27d7c36.kyma.ondemand.com/api/v1/dsp`).
2. Click **create catalog** — the published shell appears as an asset in the table
   (`aas-shell-<shellName>`).
3. Select the asset from the dropdown.
4. Click **request asset**.
5. Wait a few seconds (contract negotiation takes a moment) — status changes from *"asset
   requested"* to **"ready to download ✔"** once the data has actually been retrieved. If it
   hangs, check the debug sidebar (`debug edr1/2/3`).
6. Optional: enter a filename and click **download** to save the AAS JSON locally.

> Step 3 runs automatically in the background as soon as step 5 completes — no extra click
> needed.

## Step 3 — HNI-02: publish changes back as "Zuliefererdaten" *(automatic)*

Runs automatically right after the data is retrieved in step 2:

1. The received shell's properties are packed into a new **"Zuliefererdaten"** submodel (each
   property gets a prefix/timestamp to avoid collisions).
2. That submodel is written to local Basyx and attached to the original shell
   (`POST /submodels` + `submodel-refs`).
3. It is also uploaded to the bucket (`zuliefererdaten/<shellName>.json`) and registered as an
   Asset + ContractDefinition **on HNI-02's own EDC connector** — HNI-02 now acts as a provider.

Check: the `debug Zuliefererdaten publish` node should show `edcOfferRegistered: true`.

## Step 4 — HNI-01: retrieve the supplier data

**Dashboard page "HNI-01 Consumer" (`/consumer`) → "Receive supplier data (from HNI-02)" panel**

1. Click **"1. request supplier data"** — queries HNI-02's catalog, finds the
   `zuliefererdaten-*` offer, negotiates.
2. Wait a few seconds.
3. Click **"2. fetch & save to Basyx"**.
   - If the status shows *"not ready yet..."*: wait, click again.
   - On success: **"✅ supplier data saved to Basyx (shell: ...)"**

The round trip is complete: the original shell on HNI-01 now has an additional "Zuliefererdaten"
submodel containing the property values that passed through HNI-02 (unchanged in this demo
setup).

## Verifying the result

- AASX Package Explorer: reload the shell (`GET /shells/<id>`, or via the Provider dashboard
  download) — the "Zuliefererdaten" submodel should be visible.
- Or directly: `GET http://localhost:8081/submodels/<base64url(shellId + "/Zuliefererdaten")>`

## Project files

| File | Purpose |
|---|---|
| [SETUP.md](SETUP.md) | One-time setup from scratch |
| USAGE.md | This file — day-to-day workflow |
| `edc-bootstrap-policies.ps1` | Creates the access/contract policy on a connector (see SETUP.md, section 3) |
| `credentials.env.example` / `credentials.env` | Environment variable values (`credentials.env` is gitignored, never commit it) |
| `flows-bridge.json` / `flows-dashboards.json` | The importable flows |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Backend not configured` | `BACKEND_API_KEY` not set, or set on the wrong tab | Check the env var on the relevant tab; remember to deploy |
| `fetch is not defined` / `Cannot destructure ... of undefined` | Node-RED's Function-node sandbox blocks `require`/`fetch` | Load the module via the Function node's **Setup** tab (already configured; re-import if missing) |
| `CredentialsProviderError` on S3 upload | The AWS SDK doesn't read Node-RED env vars automatically | Already fixed — credentials are passed explicitly |
| 500 Internal Server Error on almost every EDC call | Connector outage (infrastructure) | Report to whoever administers the connector — not fixable from this project |
| 500 only when re-creating an Asset/Policy that already exists | This connector crashes instead of returning a clean 409 when re-POSTing an existing, already-referenced resource | Already fixed — the flow checks via GET first and only creates if missing |
| `Policy ... not fulfilled` during contract negotiation | The BPN constraint uses the wrong namespace (missing `tx:` prefix) or the wrong consumer BPN | Recreate the policy with `tx:BusinessPartnerNumber` and the correct consumer BPN |
| EDR list stays empty / `Cannot read properties of undefined (reading 'transferProcessId')` | Negotiation not finished yet | Wait, retry the step; check negotiation status via `POST .../contractnegotiations/request` |
| File attachments (thumbnails etc.) don't open in Package Explorer | Only JSON is transferred, not a real `.aasx` (OPC) package with embedded binaries | Known limitation, not implemented |
| "No Zuliefererdaten offer found in catalog" despite the Asset/ContractDefinition existing | Catalog response came back double JSON-encoded (a string instead of an object) | Already fixed — catalog and EDR parsing now re-parse the string case too |
| Step 4 retrieves supplier data for the wrong shell | Step 4 used to grab whichever `zuliefererdaten-*` offer came first in the catalog, regardless of which shell was selected in step 2 | Already fixed — step 4 remembers the last-selected shell (via `global` context, shared across tabs) and looks for the matching offer specifically; falls back to "any offer" only if that's not found |
| Zuliefererdaten publish chain (after "Merge AASs") shows no debug output at all | The error happens before the first `node.send()` (e.g. missing env vars) — it only shows as a red warning triangle on the node / in the Node-RED log, never in the debug sidebar | Click the node in the editor for the error tooltip, or check the Node-RED terminal log; verify env vars on the **"EDC Consumer HNI-01"** tab |

## Security note

The R2 bucket is public-read (see SETUP.md). Access control for this workflow relies entirely on
the EDC policy/contract-negotiation layer — anyone with a direct object URL can read it, bypassing
EDC. This is an accepted tradeoff for the current test setup; switching to a private,
access-controlled S3 `DataAddress` is a possible future improvement.
