# Checklist: from an empty machine to a filled AAS

Every step in the order in which it has to happen, with the exact command.
Steps marked *optional* concern a data source you may not have — the chain
runs without them and simply uses fewer sources.

`TUTORIAL.md` explains what happens in each step and what to do when
something goes wrong. This page is the short form for the second run and for
looking things up.

---

## A. Install, once

| # | What you do | Where |
| --- | --- | --- |
| 1 | Install Docker Desktop and **start it** | <https://www.docker.com/products/docker-desktop/> |
| 2 | Install Python 3.10 or newer, tick *Add python.exe to PATH* | <https://www.python.org/> |
| 3 | Install Node.js 18 or newer | <https://nodejs.org/> |
| 4 | Install openLCA 2.x | <https://www.openlca.org/> |
| 5 | Install Node-RED and the Python packages | terminal, see below |

```bash
npm install -g node-red
python -m pip install openpyxl asyncua aas-core3.0
```

---

## B. Prepare the data, once

| # | What you do | Where |
| --- | --- | --- |
| 6 | Clone the repository | terminal |
| 7 | Download the background database *idemat 2023* | <https://www.openlca.org/idemat-2023-available-for-openlca/> |
| 8 | openLCA: `File → Import → Data package`, select the download | openLCA |
| 9 | Open the database by double-clicking it (the open one is shown in bold) | openLCA |
| 10 | openLCA: `File → Import → Data package`, this time `getting-started/openlca/idemat_2023_01_02_SDIKIT.zip` | openLCA |
| 11 | openLCA: `Tools → Developer tools → IPC Server`, port `8080`, `Start` | openLCA |

```bash
git clone https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT.git
cd Sustainability-Data-Integration-KIT
```

After step 11 openLCA must show the product system
`LCA Prozess: Kugelschreiber TRACEpen` under *Product Systems*.

---

## C. Set up the KIT, once

| # | What you do | Where |
| --- | --- | --- |
| 12 | Run the setup script — it starts the containers, imports the sample shells and writes the flows | terminal |
| 13 | Copy `.env.example` to `.env` and open it in an editor | file |
| 14 | Enter `SDI_OPENLCA_PRODUCT_SYSTEM=` with the identifier that step 12 printed | file `.env` |
| 15 | *Optional:* fill in the ERP section (Odoo), the PLM section, and the machine section | file `.env` |
| 16 | Check that the setup is complete | terminal |

```bash
cd getting-started
python setup.py
```

```bash
copy .env.example .env
```

```bash
python setup.py --step 4
```

---

## D. Start the services, every time

| # | What you do | Where |
| --- | --- | --- |
| 17 | Start Docker Desktop, wait until the engine is running | Docker Desktop |
| 18 | Start openLCA, open the database, start the IPC server on port 8080 | openLCA |
| 19 | Start Node-RED. On Windows the script also asks for the credentials, which are then never stored on disk | terminal |
| 20 | Open the editor and check that every tab is present | <http://localhost:1880> |

```bash
powershell -ExecutionPolicy Bypass -File start-nodered.ps1
```

On macOS and Linux:

```bash
node-red -u nodered -s nodered/settings.js
```

---

## E. Collect the data

| # | What you do | Where | Optional |
| --- | --- | --- | --- |
| 21 | *Machines:* record an operation while the machine produces. `--pieces` is the number of parts made in that run | terminal | yes |
| 22 | *ERP:* create the sample master data in Odoo, once per installation | terminal | yes |
| 23 | *PLM:* enter the PLM section in `.env`, then start the flow *PLM flow (product)* in the editor | Node-RED | yes |
| 23b | *Serial numbers:* switch on tracking in Odoo and let it compose the numbers | terminal | yes |
| 23c | *Assembly:* book one piece so the measurements belong to it. **Writes to Odoo** | Node-RED, flow *Assembly booking* | yes |

```bash
python ../src/record_opcua.py --baseload 60
python ../src/record_opcua.py --record --pieces 25
```

```bash
powershell -ExecutionPolicy Bypass -File setup-odoo.ps1
```

The idle measurement in step 21 is worth the minute it takes: the threshold
must sit above the idle power of the machine, and that differs widely. A
printer idles at some tens of watts, a lathe at about 290 W while cutting at
600 to 800 W. A threshold that is too high catches the peaks only and
understates the energy by a factor of ten or more.

Some machines cannot be recognised from their power at all. A mill drawing
3076 W in its ready state and 3102 W while cutting differs by less than its own
fluctuation, and no threshold separates the two. For those, mark the operation
by hand:

```bash
python ../src/record_opcua.py --mark Fraesprozess
python ../src/record_opcua.py --mark Drehprozess --as-name Drehprozess_Huelse --keep
```

You press Enter at the start and at the end; the script measures the power in
between. `--as-name` matters when one machine makes more than one part: stored
under separate names, both measurements survive - under one name the later
measurement replaces the earlier, and a part silently loses its energy.
`--keep` preserves the measurements of the other machines.

---

## F. Run the chain

Two ways, same chain. The dashboard is the shorter one; the command line is
the one to use when you want to skip steps or run it from a script.

| # | What you do | Where |
| --- | --- | --- |
| 24 | Open the dashboard, choose product and method, press **Calculate the footprint** | <http://localhost:1880/dashboard/kit> |
| 25 | Read the result: parts plus assembly energy must add up to the product | dashboard, or terminal output |

The same from the command line:

```bash
python ../src/run_chain.py
```

Single steps, when you do not want to repeat everything:

```bash
python ../src/run_chain.py --from 3
python ../src/run_chain.py --skip machines --skip erp
```

---

## G. Take the result out

| # | What you do | Where |
| --- | --- | --- |
| 26 | The chain has already written the packages to `export/`. To export again separately | terminal |
| 27 | Check that the packages can be opened | terminal |
| 28 | Open `export/complete.aasx` | AASX Package Explorer |
| 29 | Look at `DataSources` — every value with the source it came from | Package Explorer |
| 30 | Look at `ILCD` — the assessment with its impact categories | Package Explorer |

```bash
python ../src/export_aasx.py export --split
python ../src/check_aasx.py --directory export
```

The Package Explorer is available at
<https://github.com/admin-shell-io/aasx-package-explorer>.

---

## What a complete run looks like

```
Step 3 - ERP: bill of material and order
  Bill of material: 6 positions | order WH/MO/00001 over 25 pieces

Step 5 - Machine data: measured production energy
  Bolzen_Aluminium: Drehprozess = 0.051512 MJ
  Stiftspitze_Helix_PLA: Drucker3D = 0.041006 MJ

Step 6 - Calculation in openLCA
  Kugelschreiber_TracePEN  Simulation, PLM, ERP, MachineData     0.133958
  ...
  Sum of the parts                                              0.132321
  Product                                                       0.133958
  Difference                                                    0.001636  (assembly energy)

Step 7 - Export and check
  8 packages readable, 0 rejected, 0 with defects
```

The last three lines of step 6 are the check that matters: the parts plus the
assembly energy must add up to the product. If they do not, a data source was
lost on the way.
