#!/usr/bin/env bash
# One-time bootstrap: creates the shared Access Policy and Contract (usage) Policy
# on the EDC provider connector. Run this once; the resulting IDs go into the
# Node-RED flow's EDC_ACCESS_POLICY_ID / EDC_CONTRACT_POLICY_ID env vars and are
# then reused for every AAS shell asset.
#
# Payload shape (context, "eq" operator, open access policy) mirrors the
# existing "EDC Provider HNI-01" Node-RED flow's policy-creation nodes, which
# are already validated against this connector.
#
# The BusinessPartnerNumber constraint MUST use the "tx:" prefix (mapped to
# https://w3id.org/tractusx/v0.0.1/ns/), not the bare/edc-vocab term - the
# consumer side's ContractRequest asserts the tx:-namespaced constraint IRI,
# and a mismatch causes negotiation to fail with "Policy ... not fulfilled"
# even when the BPN value itself is correct.
#
# Usage:
#   EDC_MANAGEMENT_URL=https://hni-01.c-27d7c36.kyma.ondemand.com/management \
#   EDC_API_KEY=M6TEwlJH \
#   CONSUMER_BPN=BPNL000000000000 \
#   ./edc-bootstrap-policies.sh

set -euo pipefail

EDC_MANAGEMENT_URL="${EDC_MANAGEMENT_URL:?Set EDC_MANAGEMENT_URL}"
EDC_API_KEY="${EDC_API_KEY:?Set EDC_API_KEY}"
CONSUMER_BPN="${CONSUMER_BPN:?Set CONSUMER_BPN to the consumer's Business Partner Number}"

ACCESS_POLICY_ID="aas-bridge-access-policy"
CONTRACT_POLICY_ID="aas-bridge-contract-policy"

CTX='["https://w3id.org/tractusx/edc/v0.0.1","http://www.w3.org/ns/odrl.jsonld",{"@vocab":"https://w3id.org/edc/v0.0.1/ns/","tx":"https://w3id.org/tractusx/v0.0.1/ns/"}]'

echo "== Creating access policy (open, no constraint - matches the existing Provider flow's pattern) =="
curl -sf -X POST "$EDC_MANAGEMENT_URL/v3/policydefinitions" \
  -H "Content-Type: application/json" -H "X-Api-Key: $EDC_API_KEY" \
  -d @- <<EOF
{
  "@context": $CTX,
  "@type": "PolicyDefinition",
  "@id": "$ACCESS_POLICY_ID",
  "policy": { "@type": "Set" }
}
EOF

echo
echo "== Creating contract (usage) policy (restricted to consumer BPN $CONSUMER_BPN) =="
curl -sf -X POST "$EDC_MANAGEMENT_URL/v3/policydefinitions" \
  -H "Content-Type: application/json" -H "X-Api-Key: $EDC_API_KEY" \
  -d @- <<EOF
{
  "@context": $CTX,
  "@type": "PolicyDefinition",
  "@id": "$CONTRACT_POLICY_ID",
  "policy": {
    "@type": "Set",
    "permission": [{
      "action": "use",
      "constraint": {
        "leftOperand": "tx:BusinessPartnerNumber",
        "operator": "eq",
        "rightOperand": "$CONSUMER_BPN"
      }
    }]
  }
}
EOF

cat <<SUMMARY

=========================================================================
Set these in the Node-RED flow's environment variables:
  EDC_ACCESS_POLICY_ID=$ACCESS_POLICY_ID
  EDC_CONTRACT_POLICY_ID=$CONTRACT_POLICY_ID
=========================================================================
SUMMARY
