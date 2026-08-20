# Tutorial: Setting up the SDI-KIT

A step-by-step walkthrough from an empty machine to the first calculated result. Allow about 45 minutes, most of which is downloading software and the LCA database.

Every step states what you should see if it worked. If your output differs, the section *When something goes wrong* at the end covers the common cases.

---

A condensed list of the same steps, without the explanations, is in
[CHECKLIST.md](CHECKLIST.md).

## What you will have at the end

An Asset Administration Shell for a ballpoint pen and its parts, filled with data from three sources, and a life cycle assessment calculated from it:

```
Data sources: Simulation, PLM, ERP
Masses from ERP, energy from Simulation | 15 parameters

EF 3.0 Method (adapted)    28 categories   Global warming: 0.123143 kg CO2 eq
```

The ERP and machine connections are optional. Without them the chain still runs
and produces a result, but only the assembly energy comes from your data — the
masses then remain the default values of the openLCA model. Step 8 explains what
that means for the result.

---

<img src="../docs/img/General%20component%20diagram.svg" alt="The parts of the KIT and how they connect" width="720">

*The pieces you will have running: source systems on the left, the data
management tool in the middle, the AAS server holding the result, and the
calculation tool it talks to. The connector on the right is what makes the
data available to others - it is not part of this tutorial.*

## Who this is for

Someone who wants to see the KIT work on their own machine before deciding
whether to adopt it: a developer, an engineer from a sustainability or
manufacturing team, or anyone evaluating the approach. No knowledge of the
Asset Administration Shell is assumed. A terminal and a text editor are.

It is **not** an installation guide for a production deployment. Everything
here runs locally against sample data, without a dataspace connector and
without your own systems. Connecting those comes afterwards, in the optional
sections.

## The whole path at a glance

The nine steps below match the nine sections of this tutorial.

| # | Step | You do | Done when |
| --- | --- | --- | --- |
| 1 | Install the software | Docker Desktop, Node-RED, three Python packages | the whale icon stops animating, both installs finish without error |
| 2 | Get the repository | clone or download it | the folders `src` and `getting-started` are there |
| 3 | Set up the LCA database | openLCA: import the two data packages, open the database, start the IPC server | the product system exists |
| 4 | Run the setup script | `python setup.py` in `getting-started` | five steps ok, seven shells on the server |
| 5 | Configure | put the product system identifier into `.env` | `python setup.py --step 4` confirms it |
| 6 | Start Node-RED | `start-nodered.ps1`, or `node-red -u nodered -s nodered/settings.js` | `http://localhost:1880` shows the tabs |
| 7 | Read in the simulation data | one click in the flow **ema Simulation → AAS** | the debug panel reports five operations |
| 8 | Calculate | **Calculate the footprint** on the dashboard | the result appears, split by part |
| 9 | Export and open the result | `python ../src/export_aasx.py export --split` | the AASX Package Explorer shows `DataSources` and `ILCD` |

> [!TIP]
> Steps 7 to 9 are the everyday loop; everything before them is done once.

[CHECKLIST.md](CHECKLIST.md) holds the same steps as a short reference, with
the commands for the optional data sources. If you would rather run the whole
chain from the command line than from the dashboard, skip to
[Running everything from the command line](#running-everything-from-the-command-line).

---

## Step 1: Install the software

Four programs are needed. The setup script checks them later and tells you what is missing.

| Software | Download | Note |
| --- | --- | --- |
| Docker Desktop | <https://www.docker.com/products/docker-desktop/> | must be **running**, not just installed |
| Python 3.10+ | <https://www.python.org/> | tick "Add python.exe to PATH" during installation |
| Node.js 18+ | <https://nodejs.org/> | the LTS version is fine |
| openLCA 2.x | <https://www.openlca.org/> | |

Then two commands in a terminal:

```bash
npm install -g node-red
python -m pip install openpyxl asyncua aas-core3
```

What the Python packages are for: `openpyxl` reads the simulation export,
`asyncua` talks to the OPC UA server of the machines, and `aas-core3` is the
reference library the package check uses - the same one the AASX Package
Explorer builds on.

**Check:** `node-red --version` prints a version number, and the Docker Desktop window shows the engine as running.

---

## Step 2: Get the repository

```bash
git clone https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT.git
cd Sustainability-Data-Integration-KIT
```

**Check:** the folder contains `README.md`, `src/` and `getting-started/`.

---

## Step 3: Set up the LCA database

This is the only step the setup script cannot do for you. openLCA databases contain licensed background data and are several gigabytes in size, so they are not part of the repository.

**3a — Download the background database.** *idemat 2023* is free: <https://www.openlca.org/idemat-2023-available-for-openlca/>

**3b — Import it.** Start openLCA, then `File → Import → Data package`, select the downloaded file. This takes a few minutes. Afterwards open the database by double-clicking it; the open database is shown in bold.

**3c — Import the model of the example product.** `File → Import → Data package` again, this time `getting-started/openlca/idemat_2023_01_02_SDIKIT.zip` from the repository.

**3d — Start the IPC server.** `Tools → Developer tools → IPC Server`, port `8080`, then `Start`.

**Check:** under `Product Systems` there is an entry `LCA Prozess: Kugelschreiber TRACEpen`, and the IPC server window shows it is running.

---

## Step 4: Run the setup script

```bash
cd getting-started
python setup.py
```

The script works through five steps. It is repeatable — if something goes wrong, fix it and run it again; completed steps are skipped.

Expected output, abbreviated:

```
Step 1 - prerequisites
  [ok]   docker     Docker version 28.x
  [ok]   python     Python 3.x
  [ok]   node       v20.x
  [ok]   node-red   Node-RED v4.x
  [ok]   Docker is running

Step 2 - start the services
  Starting the containers ...
  Waiting for the AAS server .... ready
  [ok]   AAS server at http://localhost:8081
  [ok]   Web interface at http://localhost:3000

Step 3 - import the sample data
  [ok]   000114_Kugelschreiber_TracePEN.aasx
  ...
  7 shells on the AAS server, 7 newly imported

Step 4 - check openLCA
  [ok]   IPC server reachable
  [ok]   1268 processes, 6 product systems, 44 impact methods
  [ok]   Default impact method present: EF 3.0 Method (adapted)
  [!]    SDI_OPENLCA_PRODUCT_SYSTEM is not set
         Available product systems:
           LCA Prozess: Kugelschreiber TRACEpen  ->  9eb5b6f3-...

Step 5 - provide the flows
  [ok]   Odoo_ERP.json             23 nodes
  ...
  112 nodes written to ...\getting-started\nodered\flows.json
```

The warning in step 4 is expected on a first run — you have not told the KIT yet which product system to calculate. The next step fixes that.

**Check:** `http://localhost:3000` opens the AAS web interface and lists seven
shells: the ballpoint pen and its six parts.

---

## Step 5: Configure

Copy the template and open it in an editor:

```bash
copy .env.example .env        # Windows
cp .env.example .env          # macOS, Linux
```

Enter the identifier that step 4 printed:

```
SDI_OPENLCA_PRODUCT_SYSTEM=9eb5b6f3-bf7a-4bf5-a4c5-c2ebe875dac5
```

Everything else can stay as it is for a first run. The ERP section is only needed once you connect Odoo.

**Check:** `python setup.py --step 4` now reports `Product system present: LCA Prozess: Kugelschreiber TRACEpen`.

---

## Step 6: Start Node-RED

On Windows:

```powershell
powershell -ExecutionPolicy Bypass -File start-nodered.ps1
```

On macOS and Linux:

```bash
node-red -u nodered -s nodered/settings.js
```

Then open `http://localhost:1880`. You should see four tabs:

- **Odoo ERP → AAS**
- **ema Simulation → AAS**
- **Machine data → part AAS**
- **openLCA calculation** — the calculation, operated from the dashboard

**Check:** all four tabs are present and no node is shown as *unknown node
type*. If some are, step 5 of the setup could not install the additional nodes;
run `npm install` in `getting-started/nodered` and restart Node-RED.

The dashboard for the calculation is at `http://localhost:1880/dashboard`.

---

## Step 7: Read in the simulation data

Open the tab **ema Simulation → AAS** and click the small square on the left of the node *Read simulation data*.

In the debug panel on the right you should see:

```json
{ "status": "ok", "dataSource": "Simulation",
  "operations": 5, "totalEnergyMJ": 0.014 }
```

What happened: the flow read the simulation export shipped with the KIT, distributed the energy consumption of the workstations across the five operations, and wrote the result into the AAS of the ballpoint pen.

**Check:** in the AAS web interface at `http://localhost:3000`, shell `Kugelschreiber_TracePEN`, submodel `DataSources`, there is now an entry `Simulation` containing `SimulationProcesses`.

---

## Step 8: Calculate

Open **http://localhost:1880/dashboard/kit**, choose the product
`Kugelschreiber_TracePEN` and an impact method — or leave it, then EF 3.0 is
used — and press **Calculate the footprint**.

The button runs ERP, simulation, machine data and the calculation in that
order and checks after each step that the data arrived; a step that delivers
nothing stops the run instead of calculating on the previous values. Machine
data is the exception: nothing is manufactured on a purchased part, so a
missing measurement is noted and the run continues.

> [!NOTE]
> Two things are deliberately not part of the run. **PLM** rebuilds the shells
> from engineering data, takes minutes and writes into a folder, so the page
> cannot see it finish — it sits under *Run a single step*. And the **assembly
> booking** creates a manufacturing order in Odoo; running it on every
> calculation would produce a new pen each time.

The Node-RED log shows:

```
Data sources: Simulation, PLM
Assembly energy from Simulation | 1 parameter
Calculating with 1 parameter, method EF 3.0 Method (adapted)
LCA iteration "Simulation_PLM" written
```

The four data sources are always named the same way, in the shells and in the
result: **PLM**, **ERP**, **Simulation** and **MachineData**. The name of the
iteration is built from the sources that went into it, so you can tell two runs
apart by their name alone.

**Check:** in the AAS web interface, submodel `ILCD`, there is an iteration whose `DataSource` property lists the sources used, and below it the impact categories with their values.

### What this first result does and does not tell you

At this point only the **assembly energy** comes from your data. The material masses are still the default values stored in the openLCA model, because the PLM data source in the sample AAS holds the weight and material of the product as a whole, not a bill of material broken down by part.

That is the honest starting point of the KIT: a result exists, and it is traceable, but it rests largely on assumptions. Each further data source replaces one of those assumptions with a measured or order-specific value:

| Added source | What it replaces |
| --- | --- |
| ERP (Odoo) | the default masses, by the actual bill of material |
| Machine data (OPC UA) | the manufacturing energy, by measurements |

The two optional sections below show both. In the reference setup they move the result from 0.12 to 0.29 kg CO₂ eq — the measured manufacturing energy alone more than doubles it.

---

## Optional: from a type to a piece

Everything so far describes a pen *of this kind*. A product pass has to say
something about the pen someone is holding, and a measurement is only evidence
if it belongs to one piece.

Three steps get you there, and none of them is automatic:

**1. Serial numbers in Odoo.** `setup-odoo.ps1` switches on serial number
tracking for the parts produced in house and tells Odoo how to compose a
number. The coding and the reasoning are in [ODOO.md](ODOO.md).

**2. Book an assembly.** Import `src/Assembly_Booking.json` and press
*Assembly booking*. It creates a manufacturing order over one piece, has Odoo
issue the serial number, gives every tracked component its own number, books
the consumption and writes the result into the shell as `AssemblyRecords`.

> [!WARNING]
> This **writes to Odoo**: each run produces one more piece. It reuses an open
> order rather than starting a new one every time, and it checks afterwards
> whether the order really closed — Odoo answers without an error even when it
> silently opened a dialog instead.

**3. Measure.** From then on, the machine flow attaches its measurements to
the serial numbers of the booked assembly. In the dashboard the dropdown
*Piece* selects one item, and the machine table narrows to the runs that
produced its parts.

A piece whose parts were never measured says so rather than borrowing another
piece's numbers. That is the point of the exercise: the difference between
plausible and documented.

If the assembly records are ever lost — an ERP run used to overwrite them —
`src/Assembly_Backfill.json` reads every completed order from Odoo and
restores them.

---

## Optional: connect the ERP system

Only relevant if you run an Odoo instance. With it the bill of material comes from the ERP system instead of from the PLM baseline, and the masses become order-specific.

**Create the sample data in Odoo:**

```bash
python ../src/setup_odoo_testdata.py
```

The script needs `SDI_ODOO_URL`, `SDI_ODOO_DB`, `SDI_ODOO_USER` and `SDI_ODOO_APIKEY`. Create the API key in Odoo under *Settings → Users → Account Security → New API Key*.

It creates the custom fields, the seven products with weights and materials, the bill of material and a manufacturing order — all taken from the PLM export in the repository.

Afterwards trigger the flow *Odoo ERP → AAS*. Expected:

```json
{ "status": "ok", "dataSource": "ERP",
  "product": "Kugelschreiber_TracePEN", "components": 6 }
```

The next calculation then uses the ERP masses; the log says `Masses from ERP`.

---

## Optional: connect the PLM system

Only relevant with a CONTACT Elements PLM system reachable from your network.
With it the shells themselves come from the PLM system instead of from the
sample packages, and the bill of material, materials and CAD documents are the
ones your engineers maintain.

Fill in the PLM section of `.env` — server address and login name, password left
empty — then run the setup again and start Node-RED:

```bash
python getting-started/setup.py --step 5
```

```powershell
powershell -ExecutionPolicy Bypass -File getting-started/start-nodered.ps1
```

The start script now asks for the PLM password as well. A fifth tab appears,
*PLM flow (product)*. Triggering it produces one AASX package per part in the
directory named in `SDI_PLM_OUTPUT`.

Before importing those packages:

```bash
python src/repair_aasx.py <directory with the packages>
```

Windows likes to leave a `Thumbs.db` inside; the AAS server then rejects the
package with HTTP 400. And note that the upload does not overwrite — a shell
that already exists answers HTTP 409, so import the packages before the other
flows have written anything you want to keep.

---

## Optional: connect the machines

Only relevant with an OPC UA connection in place. The flow *Machine data → part AAS* reads the measurements collected by the OPC UA connection, converts them into energy per piece and writes them into the AAS of the part that was produced.

The assignment of machine to part is at the top of the node *Configuration & assignment* and is the only place to change when the production sequence changes.

In the sample setup the machine data more than doubles the footprint — from 0.12 to 0.29 kg CO₂ eq. Without it the assessment understates the product by more than half.

---

## Step 9: Export the result and open it

The filled shells live on the AAS server. To hand them on — to a colleague, an
auditor, or a partner in the dataspace — they have to become a file. The
export writes one package holding everything and one package per shell:

```bash
python ../src/export_aasx.py export --split
```

```
7 shells, 50 submodels on the server

complete.aasx                        0.21 MB
Bolzen_Aluminium.aasx                  40 kB   7 submodels
Huelse_Aluminium.aasx                  40 kB   7 submodels
...
```

Before passing a package on, check that it can actually be opened. The check
uses the same reference library as the AASX Package Explorer, so its verdict
matches what the Explorer will do:

```bash
python ../src/check_aasx.py --directory export
```

```
  Package structure: in order
  Read: 7 shells, 50 submodels
  Content: in order

  RESULT: can be opened
```

Two outcomes are distinguished on purpose. **"can be opened"** means the file
is readable; findings listed under *Content* are defects, not obstacles — the
sample files published with the specification have some as well. **"is
rejected"** means the package is broken and no tool will read it.

Now open `export/complete.aasx` in the
[AASX Package Explorer](https://github.com/admin-shell-io/aasx-package-explorer).
Under `DataSources` you see where every value came from, under `ILCD` the
assessment with its impact categories.

---

## Running everything from the command line

Once the setup works, the whole chain can run in one go, without clicking in
the editor. This is what you use for a repeatable test, a scheduled run, or
simply to see all steps at once:

```bash
python ../src/run_chain.py
```

Every step checks its own result before the next one starts:

```
Step 3 - ERP: bill of material and order
  Flow started: HTTP 200
  Bill of material: 6 positions | order WH/MO/00001 over 25 pieces

Step 6 - Calculation in openLCA
  Shell                    Data sources                    Climate change
  Kugelschreiber_TracePEN  Simulation, PLM, ERP, MachineData     0.127261
  Bolzen_Aluminium         Simulation, PLM, ERP                  0.036113
  ...
  Sum of the parts                                              0.125624
  Product                                                       0.127261
  Difference                                                    0.001636  (assembly energy)
```

The last three lines are the most useful check you have: the parts plus the
assembly energy must add up to the product. If they do not, a data source was
lost on the way.

Steps can be selected. Machines that are not connected are simply left out —
the run does not depend on them:

```bash
python ../src/run_chain.py --from 3
python ../src/run_chain.py --skip machines --skip erp
python ../src/run_chain.py --import-dir ../docs/sample_data/AASX/TRACEpen_Kugelschreiber
```

If a step fails, the message names what was missing rather than where the
program stopped — for instance *"The bill of material did not arrive in the
shell. Check the ERP credentials in .env."*

A note on the numbers above: they belong to the reference setup, where the
machine data covers one printed part only. With all three machines connected
the result is roughly twice as high. That difference is the point of the KIT —
what is measured replaces what was assumed.

---

## When something goes wrong

**`docker compose` fails, or step 2 hangs.** Docker Desktop is installed but not running. Start it and wait until the whale icon stops animating.

**Step 3 reports HTTP 500 for a package.** An AASX package contains a file without a declared content type — usually `Thumbs.db` left by Windows Explorer. Fix:

```bash
python ../src/repair_aasx.py ../docs/sample_data/AASX
```

**Step 4 says openLCA does not respond.** Either no database is open in openLCA, or the IPC server is not running. Both are needed. After switching databases the IPC server has to be stopped and started again — it stays bound to the database that was open when it started.

**Step 4 says the database contains no product system.** The data package from step 3c has not been imported, or a different database is open.

**The calculation runs but every value is zero.** Two causes, neither of which produces an error in openLCA:

- the reference amount of the part processes is not `1 p` but a weight in kilograms
- an input flow has no provider in the product system, so it is silently ignored

Both are described in `getting-started/openlca/README.md`.

**A flow reads nothing although the file exists.** The path in `.env` is
relative and Node-RED could not resolve it — it runs with its own working
directory. Start Node-RED through `start-nodered.ps1`, which turns relative
paths into absolute ones.

**Node-RED shows `SDI_ODOO_DB ... must be set`.** The ERP flow was triggered without an Odoo configuration. Either fill in the ERP section of `.env`, or simply do not use that flow — the other three work without it.

**The AAS server is empty after a restart.** The containers were started without the `docker-compose.yml` of the KIT, so there is no database behind the AAS server. Stop them and run `python setup.py --step 2` again.

---

## What next

- `README.md` in the repository root describes the concept, the standards used and the data mapping in detail
- `getting-started/README.md` is the condensed reference for people who have been through this tutorial once
- `src/` contains the flows; each node carries comments explaining what it does

The command line tools in `src/`, each with `--help`:

| Tool | What it does |
| --- | --- |
| `run_chain.py` | runs the whole chain and checks every step |
| `export_aasx.py` | writes the filled shells as AASX packages |
| `check_aasx.py` | checks a package the way the Package Explorer does |
| `fix_aas_violations.py` | removes specification violations from the server |
| `record_opcua.py` | records machine operations from an OPC UA server |
| `repair_aasx.py` | repairs packages an AAS server refuses to import |
| `setup_odoo_testdata.py` | creates the sample master data in Odoo |
| `ema_export_to_json.py` | converts a simulation export into the flow's input |

> [!TIP]
> Each data source can be added on its own. You do not need a complete system
> landscape to get started — a PLM export is enough to produce a first
> assessment.
