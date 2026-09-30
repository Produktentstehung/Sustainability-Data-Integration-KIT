# AAS-EDC-S3 Bridge

Publishes AAS (Asset Administration Shell) data from a local Basyx server into an EDC
(Eclipse Dataspace Connector / Tractus-X) data space via a public S3-compatible bucket
(Cloudflare R2), replacing an earlier Cloudflare-tunnel-based approach.

## Why

Exposing a local Basyx server directly (via a tunnel) required routing it through the
organization's website infrastructure, which its operators were reluctant to reconfigure.
Publishing through a public object storage bucket avoids exposing any local infrastructure at
all — the Node-RED flows only need outbound network access.

## How it works

1. A Node-RED flow ("AAS to S3 Bridge") fetches a shell and its submodels from Basyx, wraps them
   as a standard AAS v3 Environment JSON, and uploads it to an R2 bucket.
2. It registers the object as an Asset + ContractDefinition on an EDC provider connector via the
   Management API.
3. A consumer connector queries the catalog, negotiates a contract, and retrieves the data via an
   Endpoint Data Reference (EDR) — standard EDC dataspace protocol, no direct network access to
   the provider's infrastructure required.
4. A second, symmetric round trip lets the consumer publish modified data back to the original
   provider as a new "Zuliefererdaten" (supplier data) submodel, using the same mechanism in
   reverse.

## Getting started

- **New to this project?** Start with [SETUP.md](SETUP.md) — one-time setup, including where
  each credential comes from.
- **Setup already done?** See [USAGE.md](USAGE.md) for the day-to-day workflow and
  troubleshooting.

## Repository contents

| File | Purpose |
|---|---|
| `flows-bridge.json` | Node-RED flow: Basyx → bucket → EDC offer registration |
| `flows-dashboards.json` | Node-RED flows: provider/consumer dashboards |
| `edc-bootstrap-policies.ps1` / `.sh` | One-time script to create shared EDC policies on a connector |
| `credentials.env.example` | Template for the environment variable values described in SETUP.md |

`credentials.env` (your own copy of the template, with real values) is gitignored and must never
be committed.
