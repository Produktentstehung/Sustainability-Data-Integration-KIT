# What each file in `src/` is for

This folder holds the working parts of the KIT: ten Node-RED flow files and
eleven Python scripts. This page says, for each one, what it does and where the
main [README](../README.md) explains the reasoning behind it.

It is a map, not a second manual. Where a chapter of the README already
describes something properly, this page points at it instead of repeating it in
shorter and worse words.

**How the pieces fit together.** Five flows each fetch data from one system and
write it into the `DataSources` submodel of an administration shell. A sixth
runs the life-cycle calculation over whatever is in there and writes the result
into the `ILCD` submodel. The dashboard operates all of them and shows what each
source delivered. That division is the whole idea of the KIT, and it is
explained in
[Data Sources and Their Effect on the Assessment](../README.md#data-sources-and-their-effect-on-the-assessment).

---

## The flows

`setup.py` assembles these files into one `flows.json`, in this order. They are
not imported by hand — see
[Starting Node-RED](../getting-started/README.md).

| File | Tab in the editor | Runs on |
| --- | --- | --- |
| `PLM.json` | PLM flow (product), PLM flow (part) | demand, per part |
| `Odoo_ERP.json` | Odoo ERP → AAS | demand or dashboard |
| `EMA.json` | ema Simulation → AAS | demand or dashboard |
| `OPCUA_Manufacturing.json` | Machine data → part AAS | demand or dashboard |
| `OpenLCA_to_AAS.json` | openLCA calculation | dashboard |
| `Dashboard.json` | SDI Dashboard | the web page |
| `Assembly_Booking.json` | Assembly booking | demand, per piece |
| `Assembly_Backfill.json` | Assembly backfill | repair only |
| `EDC_Bridge.json` | AAS to S3 Bridge | called by the EDC dashboard |
| `EDC_Dashboard.json` | EDC Provider / Consumer HNI-01, Consumer HNI-02 | two further web pages |

The last two are loaded only when `SDI_EDC_MANAGEMENT_URL` is configured.

### `PLM.json` — the shells come into existence here

Fetches part and document data from the PLM system (CONTACT Elements) and builds
an AASX package per part from it: name, article number, weight, material,
category, the link back into the PLM user interface, and the bill of material
resolved position by position. Everything downstream needs a shell to write
into, so this is the first step of a fresh installation.

Two tabs, because a product and a single part are fetched differently — the
product has a bill of material to resolve, a part does not.

One detail that looks like a mistake and is not: the material lookups are sent
deliberately **one per second**. The reference installation does not answer them
when they arrive in parallel.

> [PLM Connection (CONTACT Elements)](../README.md#plm-connection-contact-elements)
> — what the flow does, how it is configured, and the behaviour worth knowing.
> [Stage 1](../README.md#stage-1-plm-system--intermediate-json) and
> [Stage 2](../README.md#stage-2-intermediate-json--aas-submodels) of the data
> mapping follow the values from the PLM system into the submodels.

### `Odoo_ERP.json` — bill of material and order quantities

Reads product, bill-of-material and order data from Odoo over JSON-RPC and
writes them as the data source **ERP** into `DataSources`. This is the source
that says how much of what goes into the product, and in which quantity it is
actually built.

The KIT runs without it. If no ERP is configured the chain looks for a bill of
material elsewhere, marks the ERP row red and carries on.

> [ERP Connection (Odoo)](../README.md#erp-connection-odoo) — which Odoo
> records are read, what they become in the AAS, and
> [Experience from building the connection](../README.md#experience-from-building-the-connection),
> which is worth reading before connecting a different ERP.
> Setting it up: [ODOO.md](../getting-started/ODOO.md).

### `EMA.json` — the planned process

Reads an export of the ema Plant Designer simulation and writes its operations
— cycle times, processing times, energy per operation — as the data source
**Simulation**. It is the best data available before anything has been
manufactured.

> [Stage 3: Simulation Export → `DataSources`](../README.md#stage-3-simulation-export--datasources).
> The export is parsed by [`ema_export_to_json.py`](#ema_export_to_jsonpy), not
> by the flow itself.

### `OPCUA_Manufacturing.json` — what the machines actually used

Reads the recorded measurements, forms the energy per piece from them and writes
it as the data source **MachineData** into the shell of the part that was
produced — not into the product shell. A single screw has machine data; the
assembled pen does not.

This is the source that replaces an estimate with a measurement, and it is the
reason the KIT keeps every iteration rather than overwriting the previous
result.

> [Division by origin](../README.md#division-by-origin) and
> [Precedence](../README.md#precedence) — which source wins when two of them
> describe the same value, and why.

### `OpenLCA_to_AAS.json` — the calculation

Takes whatever is in `DataSources`, hands it to openLCA over its IPC interface,
and writes the result into the `ILCD` submodel: one iteration per data source,
one collection per impact assessment method, with a timestamp and the list of
sources that fed it.

It calculates the product and each part separately, so a result can be traced
down to the single component.

> [Stage 4: LCA Results → `ILCD`](../README.md#stage-4-lca-results--ilcd),
> [Three entries per value](../README.md#three-entries-per-value) and
> [Effect on the result](../README.md#effect-on-the-result).
> What the openLCA model has to provide for this to work at all:
> [Prerequisites in the openLCA model](../README.md#prerequisites-in-the-openlca-model).

### `Dashboard.json` — the page everything is operated from

One web page at `/dashboard/kit`. It starts the other flows through the Node-RED
admin interface, shows per source whether it delivered, and displays the
footprint with its method, its timestamp and a link into the AAS browser.

It also carries the `ui-base` node that the EDC pages attach to, so it has to be
present before them.

> [Dashboards for decision support](../README.md#dashboards-for-decision-support)
> — what the page is meant to answer, and for whom.

### `Assembly_Booking.json` — from a type to a piece

Creates a manufacturing order in Odoo for one piece, assigns serial numbers to
the product and to the components consumed, and records the assembly in the
shell. A product passport applies to a piece, not to a type; this is what makes
the difference visible.

### `Assembly_Backfill.json` — repair only

Reads every completed manufacturing order from Odoo and restores the assembly
records in the shell. Needed after the ERP data was rebuilt or a shell was
recreated. Not part of normal operation.

### `EDC_Bridge.json` and `EDC_Dashboard.json` — out into the dataspace

The bridge opens an HTTP endpoint inside Node-RED
(`POST /dsp-backend/shells/:shellId/publish`) which writes a shell into an
S3-compatible bucket and registers it on the EDC connector as an asset with a
contract. The dashboard adds two pages, `/provider` and `/consumer`, that drive
the round trip: publish, negotiate, fetch, answer with a `Zuliefererdaten`
submodel.

**The bucket of the reference setup is public-read.** What the contract
negotiation protects is the catalogue entry, not the payload.

> [Connection with the data space, the S3 bridge to the EDC](../README.md#connection-with-the-data-space-the-s3-bridge-to-the-edc)
> — the concept, with the provider and consumer diagrams.
> [EDC.md](../getting-started/EDC.md) — setting it up and running it.
> [Interfaces and the dataspace](../README.md#interfaces-and-the-dataspace)
> and [Implementation Status](../README.md#implementation-status) — what is
> implemented and what is not.

---

## The scripts

Four of them are called by the flows, four check things, three are operated by
hand.

### Called by the flows

#### `ema_export_to_json.py`
Reads the Excel export of the ema Plant Designer and writes the process data as
JSON to standard output. Two sheets are evaluated: the cycle times and the
energy values. `EMA.json` calls it and takes the result.

> [Stage 3: Simulation Export → `DataSources`](../README.md#stage-3-simulation-export--datasources)

#### `export_aasx.py`
Builds an AASX package from the content of the AAS server. BaSyx returns an
internal error for the AASX format in the version used here, so the script
fetches the XML environment and assembles the ZIP container itself, following
the rules of the AASX format. The export button of the dashboard calls it.

#### `repair_aasx.py`
Checks and repairs AASX packages. Rule M.1.14 of the specification requires a
declared content type for every file in the container; without it AAS servers
refuse to load the package. `setup.py` runs this over the sample data before
importing it.

#### `record_opcua.py`
Records manufacturing operations from an OPC UA server. The shop floor provides
instantaneous power; `OPCUA_Manufacturing.json` needs evaluated operations —
average power, duration, piece count. This script closes that gap.

### Checks

These are what the repository is checked with before anything is published; the
CI workflow runs them.

#### `check_flows.py`
Reads every flow file and reports what would break on import or at runtime:
references into nothing, nodes no message can reach, duplicate identifiers.
Exit code 1 means at least one finding. Run it after editing a flow.

#### `check_aasx.py`
Verifies an AASX file the way the AASX Package Explorer does, using the same
reference library (`aas-core3.0`). What passes here, the Explorer opens; what
fails here, it rejects without saying why.

#### `check_docs.py`
Checks the links and images of the documentation. A table of contents that
leads nowhere is the first thing a reader meets and is invisible to every other
check.

#### `fix_aas_violations.py`
Removes specification violations from an AAS server. Shells exported from a PLM
system commonly violate the specification in several hundred places — the
Package Explorer is lenient, other tools are not, and for a Tractus-X KIT the
data should be conformant.

### Operated by hand

#### `run_chain.py`
Runs the whole chain from the command line and verifies after every step that
the data actually arrived in the shells. The flows can be started in the editor;
this is for a repeatable run, in a test or on a schedule.

> [Running everything from the command line](../getting-started/TUTORIAL.md)

#### `setup_odoo_testdata.py`
Creates the TRACEpen sample data in an Odoo instance: categories, the custom
field for the LCA flow identifier, the six products with weight and category,
and the bill of material. Repeatable — existing records are updated, not
duplicated.

> [Setting up the sample data](../README.md#setting-up-the-sample-data)

#### `create_set_number_of_aas_instances.py`
Creates a defined number of instance shells from a configured type shell.
Used to produce the sample data, not needed in normal operation.

> [Sample Data: TRACEpen](../README.md#sample-data-tracepen)

---

## Importing a flow by hand

Don't. `setup.py` assembles the files, and an import through the Node-RED menu
with *Replace flows* deletes every tab that is already there. If you do need to
look at a single flow in the editor, use *Add flows* and remove it again
afterwards.
