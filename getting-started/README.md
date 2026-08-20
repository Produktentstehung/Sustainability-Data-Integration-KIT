# Getting Started

Setting up the Sustainability Data Integration KIT on a new machine.

After these steps the AAS server runs with the sample data, the flows are loaded in Node-RED and the connection to openLCA works. The TRACEpen ballpoint pen serves as the worked example throughout.

For a step-by-step list of every click and command, see
[CHECKLIST.md](CHECKLIST.md); for the explained walkthrough see
[TUTORIAL.md](TUTORIAL.md).

## Prerequisites

The setup script checks these and tells you what is missing.

| Software | Purpose | Source |
| --- | --- | --- |
| Docker Desktop | runs the AAS server and the registries | <https://www.docker.com/products/docker-desktop/> |
| Python 3.10+ | setup, reading the simulation export | <https://www.python.org/> |
| Node.js 18+ | runtime for Node-RED | <https://nodejs.org/> |
| Node-RED | executes the integration flows | `npm install -g node-red` |
| openLCA 2.x | calculates the environmental impacts | <https://www.openlca.org/> |

Two Node-RED add-ons are required as well. Step 5 of the setup installs them
into `getting-started/nodered`, so there is normally nothing to do by hand:

| Add-on | Purpose |
| --- | --- |
| `@flowfuse/node-red-dashboard` | the dashboard the calculation is operated from |
| `node-red-node-base64` | encodes the submodel identifiers for the AAS API |

One Python package is needed to read the simulation exports:

```bash
python -m pip install openpyxl
```

## Setup in one go

```bash
cd getting-started
python setup.py
```

The script works through five steps and stops with a readable message as soon as something is missing. It is repeatable — steps already completed are recognised and skipped.

| Step | What happens |
| --- | --- |
| 1 | check prerequisites |
| 2 | start the AAS server, registries and web interface |
| 3 | import the AASX packages of the product and its parts |
| 4 | check the openLCA connection and model content |
| 5 | assemble the flows for Node-RED |

Individual steps can be run on their own:

```bash
python setup.py --step 3      # only import the sample data
python setup.py --check       # only check, change nothing
```

## The openLCA database

The database is not part of this repository — it is several gigabytes in size and contains licensed background data. It has to be set up once.

**1. Obtain the background database.** The example uses *idemat 2023*, freely available from <https://www.openlca.org/idemat-2023-available-for-openlca/>. Any other database with material datasets works as well; the mappings then have to be adjusted.

**2. Import it into openLCA.** `File → Import → Data package`, then open the database.

**3. Import the process model.** The processes of the example product are provided as an openLCA data package under `getting-started/openlca/`. Import it the same way. It contains one process per part, the assembly process and the product system.

**4. Start the IPC server.** In openLCA: `Tools → Developer tools → IPC Server`, port `8080`, then `Start`. Without this step Node-RED cannot trigger a calculation.

Two properties of the model are easy to miss when building your own, and neither produces an error message:

- **The reference amount of every part process is 1 p.** If a weight in kilograms is used instead, openLCA scales the process by the reciprocal — a reference amount of 0.003 kg means a factor of 333.
- **Every input flow needs a provider in the product system.** An unlinked input is silently calculated as zero, regardless of the value passed in. This affects the electricity input in particular.

## Configuration

The flows read their settings from environment variables. Copy `.env.example` to `.env` and fill it in. The filled-in file is excluded from version control.

The most important entries:

| Variable | Meaning |
| --- | --- |
| `SDI_AAS_URL` | AAS server, `http://localhost:8081` by default |
| `SDI_OPENLCA_URL` | openLCA IPC, `http://localhost:8080` by default |
| `SDI_OPENLCA_PRODUCT_SYSTEM` | identifier of the product system, shown by `setup.py --step 4` |
| `SDI_ODOO_*` | access to the ERP system, if used |
| `SDI_EMA_EXPORT` | path to the simulation export |

Do **not** put the Odoo API key into `.env`. Leave `SDI_ODOO_APIKEY` empty; the
two PowerShell scripts then ask for it at startup, do not echo it and pass it to
the process as an environment variable only.

## Creating the sample data in Odoo

Only needed if you want to run the ERP connection. The script creates the custom
fields, the products with weights and materials, the bill of material and a
manufacturing order, all from the PLM export in `docs/sample_data`:

```powershell
powershell -ExecutionPolicy Bypass -File getting-started/setup-odoo.ps1
```

It also switches on serial number tracking for the parts produced in house and
tells Odoo how to compose a serial number. What exactly it sets up, and why, is
described in [ODOO.md](ODOO.md) - worth reading before rebuilding the instance,
because none of it was done by hand in the Odoo interface.

It is repeatable - existing records are updated rather than duplicated. Create
the API key in Odoo under *Settings -> Users -> Account Security -> New API Key*.

Note the server address: `SDI_ODOO_URL` is the bare host, not the address shown
in the browser. A trailing `/odoo` or `/web` is removed automatically.

## The dashboard

The page is at **http://localhost:1880/dashboard/kit** once `Dashboard.json` is
imported. Each flow file can be imported on its own; the dashboard brings its
own user interface base, so the order does not matter.

What the page shows, from top to bottom: the footprint with its reference
quantity, the piece it belongs to, the button that runs the chain, the choice
of product, method and piece, the result split by part, the state of each data
source, and the recorded machine runs.

**One button does the work.** *Calculate the footprint* runs ERP, simulation,
machine data and the calculation, in that order, and checks after every step
that the data actually arrived. It takes well under a minute.

Three things it deliberately does **not** do:

- **PLM** is not part of the run. It rebuilds the shells from engineering data,
  takes minutes and writes packages into a folder, so the page cannot tell when
  it has finished. It sits under *Run a single step*.
- **Assembly booking** is not part of the run either. It creates a
  manufacturing order in Odoo and would produce a new piece on every click.
- The **export** is its own button. It writes AASX packages into the `export`
  folder on the machine running Node-RED - not a browser download.

A run stops rather than calculating on missing data. Machine data is the one
exception: nothing is manufactured on a purchased part, so a missing
measurement is noted and the run continues.

## Pieces instead of types

The dropdown *Piece* selects one manufactured item. This is what a product pass
is about: not "a pen of this kind", but the pen in your hand.

Selecting a piece narrows the machine table to the runs that produced its
parts. A piece whose parts were never measured says so - *0 of 9 recorded runs
belong to this piece* - rather than showing measurements from another piece.

The list comes from the assembly records in the shell, which
`Assembly_Booking.json` writes when a manufacturing order is completed. Select
a single part instead of the product, and the list shows that part's own
serial numbers.

The serial numbers themselves are described in [ODOO.md](ODOO.md).

## Starting Node-RED

```bash
node-red -u getting-started/nodered -s getting-started/nodered/settings.js
```

Then open `http://localhost:1880` in a browser. The flows are already loaded.

On Windows, `start-nodered.ps1` additionally sets the environment variables and asks for the Odoo key without echoing it:

```powershell
powershell -ExecutionPolicy Bypass -File getting-started/start-nodered.ps1
```

## The processing chain

Four flows that build on each other. Each writes into the Asset Administration Shell; none requires another one to have run before.

| Flow | reads | writes |
| --- | --- | --- |
| `Odoo_ERP.json` | bill of material and order from Odoo | `DataSources → ERP` of the product AAS |
| `EMA.json` | simulation export of the assembly | `DataSources → Simulation` of the product AAS |
| `OPCUA_Manufacturing.json` | measurements from the OPC UA connection | `DataSources → Manufacturing` of the part AAS |
| `OpenLCA_to_AAS.json` | all data sources | `ILCD` with the results |
| `Dashboard.json` | the shells and openLCA | the web page at `/dashboard/kit` |
| `Assembly_Booking.json` | Odoo | serial numbers, and `DataSources → ERP → AssemblyRecords` |
| `Assembly_Backfill.json` | Odoo | the same records, restored after a rebuild |

For each quantity the calculation flow takes the best available source:

```
Masses : MachineData → ERP → PLM
Energy : MachineData → Simulation
```

When a better source becomes available it displaces the weaker one. Earlier
results remain in the `ILCD` submodel as separate iterations, so different data
quality levels stay comparable.

The flows are independent of one another. A source that is never connected
simply does not appear; the calculation then runs on what is there and records
in the result which sources it used.

## Connecting the PLM system

`PLM.json` reads a part with its bill of material, technical data and documents
from a CONTACT Elements PLM system, downloads the CAD file and its preview, and
hands everything to a script that builds one AASX package per part.

It is not part of the setup by default, because it needs a PLM server reachable
from your own network. Fill in the PLM section of `.env`, and step 5 of the
setup picks the flow up automatically:

| Variable | Meaning |
| --- | --- |
| `SDI_PLM_URL` | bare server address of the PLM system |
| `SDI_PLM_USER` | login name |
| `SDI_PLM_PASSWORD` | leave empty; `start-nodered.ps1` asks for it |
| `SDI_PLM_WORK_DIR` | directory for intermediate files |
| `SDI_PLM_BASE_SHELL` | template of the administration shell |
| `SDI_PLM_OUTPUT` | where the finished packages are written |
| `SDI_PLM_SCRIPT` | script that builds the shell from the PLM data |

The last three point at artefacts of your own installation. The script that
builds the shell is **not** part of this repository - it depends on the object
model of your PLM system and has to be written for it. The flow calls it with
the collected data as a JSON file, so the interface is small: read the JSON,
write an AASX package.

Paths may be written relative to `getting-started/`. The start script resolves
them; Node-RED runs with its own working directory, so an unresolved relative
path would read nothing.

Parts without a CAD document - purchased parts, typically - still get a shell,
just without a model file.

### Importing the generated packages

```bash
python src/repair_aasx.py <directory with the packages>
```

Run this first. If a package contains a Windows artefact such as `Thumbs.db`,
the AAS server rejects it with HTTP 400.

The upload does not overwrite: importing a shell that already exists answers
HTTP 409. Delete the shell and its submodels first - and note that this also
removes what the other flows have written into `DataSources` and `ILCD`. Either
import before the other sources run, or save those two submodels and write them
back afterwards.

## First run

1. `python setup.py` — services and data
2. Start Node-RED
3. In the flow *ema Simulation → AAS*, click the inject button
4. In the flow *OpenLCA_to_AAS*, select the shell and start the calculation
5. Inspect the result at `http://localhost:3000`, submodel `ILCD`

Without Odoo and without the machine connection the chain already runs end to end and produces a result. Be aware of what that first result rests on: only the assembly energy comes from the simulation data. The masses remain the default values of the openLCA model, because the PLM data source of the sample holds the weight of the product as a whole rather than a bill of material per part. Connecting the ERP system replaces those defaults, and the machine connection replaces the manufacturing energy — in the reference setup the two together move the result from 0.12 to 0.29 kg CO₂ eq.

## Common pitfalls

**The AAS server is empty after a restart.** Storage in MongoDB is configured in `docker-compose.yml`. A container started without that file keeps everything in memory only.

**An AASX package will not load.** Message: `does not have any content type`. The cause is a file inside the package without a declared content type, often `Thumbs.db` left by Windows Explorer. Fix:

```bash
python src/repair_aasx.py docs/sample_data/AASX
```

**A flow reads nothing although the file exists.** The path in `.env` is
relative and Node-RED could not resolve it. Start Node-RED through
`start-nodered.ps1`, which turns relative paths into absolute ones.

**A request to the PLM system runs into a two-minute timeout.** Requests are
sent one per second on purpose; the PLM system of the reference installation
does not answer the bill-of-material lookups when they arrive in parallel.

**Node-RED shows nodes as "unknown node type".** The two add-ons above are
missing. Run `npm install` in `getting-started/nodered` and restart Node-RED.

**The calculation writes nothing and the log says there are no results.** The
IPC server in openLCA is not running, or a different database is open. The flow
deliberately writes no iteration in that case, so that the AAS never contains an
empty result that looks like a real one.

**Values passed to the calculation have no effect.** In openLCA 2.x the field in the calculation setup is called `parameters`. The earlier name `parameterRedefs` is ignored without an error message.

**Weights coming from the ERP system are zero.** Odoo rounds weights to two decimal places by default, so parts weighing a few grams become 0.00 kg. The decimal precision for *Stock Weight* has to be increased; `src/setup_odoo_testdata.py` does this.

## NOTICE

This work is licensed under the [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/legalcode).

- SPDX-License-Identifier: CC-BY-4.0
- SPDX-FileCopyrightText: 2025 Heinz Nixdorf Institute
- SPDX-FileCopyrightText: 2025 Paderborn University
- SPDX-FileCopyrightText: 2025 Contributors to the Eclipse Foundation
- Source URL: <https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT>
