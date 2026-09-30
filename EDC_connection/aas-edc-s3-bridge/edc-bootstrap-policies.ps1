<#
One-time bootstrap: creates the shared Access Policy and Contract (usage) Policy
on the EDC provider connector. Run this once; the resulting IDs go into the
Node-RED flow's EDC_ACCESS_POLICY_ID / EDC_CONTRACT_POLICY_ID env vars and are
then reused for every AAS shell asset.

Payload shape (context, "eq" operator, open access policy) mirrors the
existing "EDC Provider HNI-01" Node-RED flow's policy-creation nodes, which
are already validated against this connector.

The BusinessPartnerNumber constraint MUST use the "tx:" prefix (mapped to
https://w3id.org/tractusx/v0.0.1/ns/), not the bare/edc-vocab term - the
consumer side's ContractRequest asserts the tx:-namespaced constraint IRI,
and a mismatch causes negotiation to fail with "Policy ... not fulfilled"
even when the BPN value itself is correct.

Usage:
  .\edc-bootstrap-policies.ps1 -EdcManagementUrl https://hni-01.c-27d7c36.kyma.ondemand.com/management -EdcApiKey M6TEwlJH -ConsumerBpn BPNL000000000000
#>
param(
    [Parameter(Mandatory = $true)][string]$EdcManagementUrl,
    [Parameter(Mandatory = $true)][string]$EdcApiKey,
    [Parameter(Mandatory = $true)][string]$ConsumerBpn
)

$ErrorActionPreference = "Stop"

$AccessPolicyId = "aas-bridge-access-policy"
$ContractPolicyId = "aas-bridge-contract-policy"

$Context = @(
    "https://w3id.org/tractusx/edc/v0.0.1",
    "http://www.w3.org/ns/odrl.jsonld",
    @{ "@vocab" = "https://w3id.org/edc/v0.0.1/ns/"; "tx" = "https://w3id.org/tractusx/v0.0.1/ns/" }
)

# Content-Type must NOT be set via -Headers in Windows PowerShell 5.1 (it's a
# restricted header there) - use the dedicated -ContentType parameter instead,
# otherwise EDC/Jetty rejects the request with an opaque 400 before it even
# reaches the policy validation.
$headers = @{ "X-Api-Key" = $EdcApiKey }

function Invoke-Edc {
    param([string]$Url, [string]$Body)
    try {
        return Invoke-RestMethod -Method Post -Uri $Url -Headers $headers -ContentType "application/json" -Body $Body
    } catch {
        $resp = $_.Exception.Response
        if ($resp) {
            $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
            $respBody = $reader.ReadToEnd()
            Write-Host "EDC responded with an error body:" -ForegroundColor Yellow
            Write-Host $respBody
        }
        throw
    }
}

Write-Host "== Creating access policy (open, no constraint - matches the existing Provider flow's pattern) =="
$accessPolicyBody = @{
    "@context" = $Context
    "@type"    = "PolicyDefinition"
    "@id"      = $AccessPolicyId
    policy     = @{ "@type" = "Set" }
} | ConvertTo-Json -Depth 10

Invoke-Edc -Url "$EdcManagementUrl/v3/policydefinitions" -Body $accessPolicyBody | Out-Null

Write-Host "== Creating contract (usage) policy (restricted to consumer BPN $ConsumerBpn) =="
$contractPolicyBody = @{
    "@context" = $Context
    "@type"    = "PolicyDefinition"
    "@id"      = $ContractPolicyId
    policy     = @{
        "@type"     = "Set"
        permission  = @(@{
            action     = "use"
            constraint = @{
                leftOperand  = "tx:BusinessPartnerNumber"
                operator     = "eq"
                rightOperand = $ConsumerBpn
            }
        })
    }
} | ConvertTo-Json -Depth 10

Invoke-Edc -Url "$EdcManagementUrl/v3/policydefinitions" -Body $contractPolicyBody | Out-Null

Write-Host ""
Write-Host "========================================================================="
Write-Host "Set these in the Node-RED flow's environment variables:"
Write-Host "  EDC_ACCESS_POLICY_ID=$AccessPolicyId"
Write-Host "  EDC_CONTRACT_POLICY_ID=$ContractPolicyId"
Write-Host "========================================================================="
