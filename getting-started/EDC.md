# Publishing into the dataspace

This is the part of the KIT that hands a shell to another company. It writes
the shell into an S3-compatible bucket, registers it on an EDC connector as an
asset with a contract, and lets a partner connector negotiate for it and fetch
it. The partner can write data back the same way, as a `Zuliefererdaten`
submodel on the original shell.

It is optional. Leave `SDI_EDC_MANAGEMENT_URL` empty and the setup does not
load these flows at all; everything else in the KIT works unchanged.

## Read this first

**The bucket is public-read.** Access control rests entirely on the contract
negotiation of the connector: anyone who knows an object's address can read it
without a contract. That is a deliberate shortcut of this reference setup, not
a property of the design, and it is the one thing to change before anything
confidential travels this way. A private bucket with a pre-signed address, or
an S3 data address managed by the connector, closes it.

Say this out loud in any demonstration. A dataspace whose payload lies open
demonstrates the mechanics of sovereign exchange, not sovereign exchange.

## What you need

| | Can you set it up yourself? |
| --- | --- |
| Two EDC connectors with management API and key | **No.** They are operated centrally. Ask whoever runs your Tractus-X infrastructure. |
| A bucket on an S3-compatible service | Usually yes, if you have an account. The reference setup uses Cloudflare R2. |
| The rest of the KIT, running | Yes, see [README.md](README.md) |

The two connectors are called **HNI-01** and **HNI-02** throughout the flows.
Read them as "your own" and "the partner".

## 1. The bucket

On Cloudflare R2, or any service that speaks the S3 API:

1. Create a bucket, for example `aas-bucket`.
2. Enable public read for it. On R2: bucket → Settings → Public Development
   URL → Enable. The resulting address is `SDI_S3_PUBLIC_URL`.
3. Create an API token limited to this bucket, with read and write. Its two
   values are `SDI_S3_ACCESS_KEY_ID` and the secret key.
4. `SDI_S3_ENDPOINT` is the S3 address of your account, on R2
   `https://<account>.r2.cloudflarestorage.com`. The region there is always
   `auto`.

## 2. The two policies

Each connector needs one access policy and one contract policy naming the
other side as the permitted consumer. Without them neither can offer anything
to the other. `edc/edc-bootstrap-policies.ps1` creates both, once per
direction:

```powershell
# On your own connector: allow the partner to see and request your offers
.\edc\edc-bootstrap-policies.ps1 -EdcManagementUrl <your URL> -EdcApiKey <your key> -ConsumerBpn <partner BPN>

# On the partner connector: the same in reverse, for the way back
.\edc\edc-bootstrap-policies.ps1 -EdcManagementUrl <partner URL> -EdcApiKey <partner key> -ConsumerBpn <your BPN>
```

Both policies get fixed names, `aas-bridge-access-policy` and
`aas-bridge-contract-policy`, so the flows can refer to them. Re-run only when
a connector or a permitted BPN changes.

There is a `.sh` of the same script for shells other than PowerShell.

## 3. Configuration

Everything goes into `.env`, in the section *Dataspace*. Addresses, bucket and
policy names belong in the file; the four keys do not. `start-nodered.ps1` asks
for those once `SDI_EDC_MANAGEMENT_URL` is filled in, and they live in that
process only:

| Asked for | What it is |
| --- | --- |
| `SDI_EDC_API_KEY` | key of your own connector |
| `SDI_EDC_PARTNER_API_KEY` | key of the partner connector |
| `SDI_S3_SECRET_ACCESS_KEY` | secret key of the bucket |
| `SDI_EDC_BACKEND_KEY` | shared key of the dashboard's own endpoints; pick any long string, the same on both sides |

The flows also keep their own variables on each tab, which take precedence.
That is how the bridge was configured before it came into the KIT. You do not
need them: a tab variable left empty falls through to the value from `.env`.

After filling in `.env`, run `python setup.py` once. It notices the connector
and adds the three dataspace tabs to the flows.

## 4. One setting in Node-RED

Two function nodes load the S3 client as an npm module. That needs

```js
functionExternalModules: true,
```

in `nodered/settings.js`. `setup.py` writes it into a new file and tells you if
an existing one lacks it. Restart Node-RED afterwards; a deploy is not enough.
With the setting in place, Node-RED installs the module itself on the first
deploy.

## The round trip

Three tabs, two dashboard pages. The tab names say which connector a tab
*talks about*, not which one it *drives*, which is worth knowing before
debugging:

| Tab | Dashboard page | Drives |
| --- | --- | --- |
| AAS to S3 Bridge | none, runs in the background | your own connector |
| EDC Provider HNI-01 | `/provider` | your own connector |
| EDC Consumer HNI-01 | `/consumer` | the **partner** connector |
| EDC Consumer HNI-02 | widgets on `/consumer` | your **own** connector, as consumer |

**Step 1, you publish.** Page `/provider`, panel *Publish AAS Shell*: pick a
shell, press *publish to bucket*. The shell is written to the bucket and
registered on your connector as an asset with a contract definition.

**Step 2, the partner fetches.** Page `/consumer`: pick the provider from the
address book, *create catalog*, pick the asset, *request asset*. Negotiation
takes a moment; the status turns to *ready to download* once the data has
actually arrived. Optionally save it as a file.

**Step 3, the partner answers.** Runs on its own right after step 2. The
received properties are packed into a `Zuliefererdaten` submodel, written to
the local AAS server, attached to the shell, uploaded to the bucket and offered
on the partner connector.

**Step 4, you fetch the answer.** Page `/consumer`, panel *Receive supplier
data*: *request supplier data*, wait, then *fetch & save to Basyx*. The
original shell now carries a `Zuliefererdaten` submodel.

Check it in the AAS browser, or directly:

```
GET <SDI_AAS_URL>/submodels/<base64url(shellId + "/Zuliefererdaten")>
```

## When something goes wrong

| Symptom | Cause |
| --- | --- |
| `Backend not configured` | `SDI_EDC_BACKEND_KEY` is missing, or was entered on the wrong tab |
| `fetch is not defined`, `Cannot destructure` | `functionExternalModules` is not set, or Node-RED was not restarted after setting it |
| `CredentialsProviderError` on upload | the S3 keys did not arrive; the AWS SDK does not read Node-RED variables by itself, the flow passes them explicitly |
| 500 on almost every call to the connector | the connector is down. Not fixable from here |
| 500 only when creating something that exists | this connector answers a repeated create with a crash instead of a conflict; the flows check with GET first |
| `Policy ... not fulfilled` during negotiation | the BPN constraint uses the wrong namespace or the wrong partner BPN. It must be `tx:BusinessPartnerNumber` |
| The list of endpoint data references stays empty | negotiation has not finished. Wait and repeat the step |
| Attachments do not open in the Package Explorer | only the JSON travels, not an AASX package with its files. Not implemented |
| Step 4 brings the wrong shell's data | the flows remember the shell selected in step 2 and look for its offer specifically; if that is missing they fall back to any offer |

## What is not implemented

Only the shell as JSON travels, not an AASX package with attachments. The
exchange covers one shell at a time. And the bucket is public, see the top of
this page.
