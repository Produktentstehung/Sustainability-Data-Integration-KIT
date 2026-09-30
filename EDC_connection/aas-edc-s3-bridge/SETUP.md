# Setup

This guide covers the one-time setup required before using this project. It assumes no prior
knowledge of the project. Once setup is complete, day-to-day usage is documented in
[USAGE.md](USAGE.md).

## Architecture

A local AAS shell (Basyx) is exchanged between two EDC (Eclipse Dataspace Connector / Tractus-X)
connectors — referred to here as **HNI-01** and **HNI-02** — via a public S3-compatible bucket
(Cloudflare R2). The bucket replaces a previously used Cloudflare tunnel, avoiding the need to
expose any local infrastructure to the internet.

## Prerequisites

| Requirement | Purpose | Self-service? |
|---|---|---|
| Node-RED and Basyx running locally (`localhost:8081`) | Base runtime for all flows | No — must already be set up |
| Access to a Cloudflare account / the `aas-bucket` R2 bucket | Object storage for AAS data | Bucket may already exist; ask whoever manages it for access |
| Access to the HNI-01 and HNI-02 EDC connectors (management API URL + API key) | The actual dataspace connectors | **No — these are managed externally.** You cannot provision a new connector yourself; request credentials from whoever administers the Kyma/Tractus-X infrastructure |
| PowerShell (Windows) | Runs the setup script | Pre-installed on Windows |

AWS is not used anywhere in this project — object storage runs on Cloudflare R2.

## 1. Cloudflare R2

### 1.1 Bucket

If the `aas-bucket` bucket already exists, skip to 1.2. Otherwise:

1. Log in at [dash.cloudflare.com](https://dash.cloudflare.com).
2. Sidebar → **R2 Object Storage** → **Create bucket**.
3. Name it `aas-bucket`, location "Automatic".
4. In the bucket → **Settings** → **Public Development URL** → **Enable**. The resulting domain
   (`https://pub-XXXXXXXX.r2.dev`) is `R2_PUBLIC_URL`.

The bucket is public-read by design: access control for this workflow is enforced at the EDC
policy/contract-negotiation layer, not at the bucket itself. See the security note in
[USAGE.md](USAGE.md) for the tradeoff this implies.

### 1.2 API token

Each environment needs its own R2 API token: R2 → **Manage R2 API Tokens** → **Create API Token**.

- Permission: **Object Read & Write**
- Scope: **Apply to specific buckets only** → `aas-bucket`

The Access Key ID and Secret Access Key are shown once at creation time — save them immediately.
These are `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`.

`R2_ENDPOINT` (`https://<ACCOUNT_ID>.r2.cloudflarestorage.com`) is shown on the R2 overview page.

## 2. EDC connector credentials

These cannot be self-provisioned. Request the following from whoever administers the EDC
connectors:

- Management API URL for each connector (format: `https://<name>.<cluster>/management`)
- `X-Api-Key` for each connector

## 3. Shared EDC policies

Each connector needs an access policy and a contract policy that name the other connector as an
allowed consumer, before either can offer anything to the other. `edc-bootstrap-policies.ps1`
creates both — run once per connector direction:

```powershell
# On HNI-01: allow HNI-02 to request HNI-01's offers
.\edc-bootstrap-policies.ps1 -EdcManagementUrl <EDC_MANAGEMENT_URL_HNI01> -EdcApiKey <EDC_API_KEY_HNI01> -ConsumerBpn BPNL000000003HN2

# On HNI-02: allow HNI-01 to request HNI-02's offers (for the supplier-data round trip)
.\edc-bootstrap-policies.ps1 -EdcManagementUrl <EDC_MANAGEMENT_URL_HNI02> -EdcApiKey <EDC_API_KEY_HNI02> -ConsumerBpn BPNL000000003HN1
```

The script creates two `PolicyDefinition` resources via the management API: an open access
policy (metadata is visible to anyone) and a contract policy restricted to the given consumer BPN
(`-ConsumerBpn`). Both get fixed IDs (`aas-bridge-access-policy` / `aas-bridge-contract-policy`)
so every flow can reference them by name.

Re-run only when adding a new connector or changing the allowed consumer BPN — not needed for
day-to-day publishing.

If the script won't run directly: `powershell -ExecutionPolicy Bypass -File .\edc-bootstrap-policies.ps1 ...`,
or set the execution policy once with `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 4. Node-RED configuration

1. Install the S3 client module in the Node-RED user directory (typically `%USERPROFILE%\.node-red`):
   ```powershell
   cd $env:USERPROFILE\.node-red
   npm install @aws-sdk/client-s3
   ```
2. In `settings.js` (same directory), ensure `functionExternalModules: true` is set — this lets
   Function nodes load modules via their Setup tab.
3. Restart Node-RED (this setting requires a restart, not just a deploy).

## 5. Import the flows

| File | Contains |
|---|---|
| `flows-bridge.json` | The "AAS to S3 Bridge" tab (background logic) |
| `flows-dashboards.json` | The "EDC Provider HNI-01", "EDC Consumer HNI-01", and "EDC Consumer HNI-02" tabs (dashboards) |

Import via the Node-RED menu → Import → select file → **Replace flows** (not "Add flows", which
would create duplicate tabs running stale code). Deploy afterward.

## 6. Environment variables

Copy `credentials.env.example` to `credentials.env` and fill in the values gathered above
(`credentials.env` is gitignored — never commit it). The table below maps each value to the
Node-RED tab and variable name it belongs in (tab properties: double-click the tab in the editor
→ Environment Variables).

### Tab "AAS to S3 Bridge"

| Variable | Value |
|---|---|
| `BASYX_BASE_URL` | `http://localhost:8081` (pre-filled) |
| `BACKEND_API_KEY` | from `credentials.env` |
| `S3_BUCKET` | `aas-bucket` |
| `S3_REGION` | `auto` (pre-filled) |
| `S3_ENDPOINT` | `R2_ENDPOINT` |
| `S3_PUBLIC_BASE_URL` | `R2_PUBLIC_URL` |
| `AWS_ACCESS_KEY_ID` | `R2_ACCESS_KEY_ID` |
| `AWS_SECRET_ACCESS_KEY` | `R2_SECRET_ACCESS_KEY` |
| `EDC_MANAGEMENT_URL` | `EDC_MANAGEMENT_URL_HNI01` |
| `EDC_API_KEY` | `EDC_API_KEY_HNI01` |
| `EDC_ACCESS_POLICY_ID` | `aas-bridge-access-policy` |
| `EDC_CONTRACT_POLICY_ID` | `aas-bridge-contract-policy` |

### Tab "EDC Provider HNI-01"

| Variable | Value |
|---|---|
| `BACKEND_API_KEY` | same value as above |
| `PUBLISH_BASE_URL` | `http://localhost:1880` (Node-RED's own address) |
| `BASYX_BASE_URL` | `http://localhost:8081` |

### Tab "EDC Consumer HNI-01" *(drives the HNI-02 connector — see the naming note in USAGE.md)*

| Variable | Value |
|---|---|
| `BASYX_BASE_URL` | `http://localhost:8081` |
| `S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT`, `S3_PUBLIC_BASE_URL`, `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY` | same as the bridge tab above |
| `EDC_MANAGEMENT_URL_HNI02` | `EDC_MANAGEMENT_URL_HNI02` |
| `EDC_API_KEY_HNI02` | `EDC_API_KEY_HNI02` |
| `EDC_ACCESS_POLICY_ID_HNI02` | `aas-bridge-access-policy` |
| `EDC_CONTRACT_POLICY_ID_HNI02` | `aas-bridge-contract-policy` |

### Tab "EDC Consumer HNI-02"

| Variable | Value |
|---|---|
| `EDC_MANAGEMENT_URL` | `EDC_MANAGEMENT_URL_HNI01` (pre-filled) |
| `EDC_API_KEY` | `EDC_API_KEY_HNI01` — must be entered manually |
| `PROVIDER_DSP_URL`, `PROVIDER_BPN`, `BASYX_BASE_URL` | pre-filled, do not change |

Deploy after every change. If a value doesn't seem to take effect, confirm you edited the correct
tab (each tab has its own Environment Variables) and that Deploy was actually clicked — see the
troubleshooting table in [USAGE.md](USAGE.md).

## 7. Verify

Once everything above is in place, walk through steps 1–4 in [USAGE.md](USAGE.md) end to end.
