# openLCA data package

`idemat_2023_01_02_SDIKIT.zip` contains the calculation model of the example product as an openLCA data package in JSON-LD format.

## Contents

| Object type | Count | Content |
| --- | --- | --- |
| Product system | 1 | `LCA Prozess: Kugelschreiber TRACEpen`, reference amount 1 p, 98 processes, 191 links |
| Processes | 98 | 7 belonging to the product, 91 upstream from idemat |
| Flows | 785 | 6 part flows, electricity, materials and their upstream chain |
| Flow properties | 15 | including `Amount` and one `ERP product mass` per part |
| Unit groups | 15 | |

The seven processes of the product:

| Process | Identifier | Mass parameters | Energy parameter |
| --- | --- | --- | --- |
| `LCA Prozess: Kugelschreiber TRACEpen` | `5c609b0a` | — | `Energieverbrauch_Montage_Kugelschreiber` |
| `LCA Prozess: Bolzen` | `90291baa` | `Menge_Aluminium_Bolzen`, `Menge_Stahl_Bolzen` | `Energieverbrauch_Bolzen` |
| `LCA Prozess: Hülse` | `57c37380` | `Menge_Aluminium_Huelse`, `Menge_Stahl_Huelse` | `Energieverbrauch_Huelse` |
| `LCA Prozess: Stiftspitze` | `5043f2ab` | `Menge_Stiftspitze_PLA`, `_Polypropylene`, `_ABS` | `Energieverbrauch_Stiftspitze` |
| `LCA Prozess: Mine` | `98446bf7` | `Menge_Polypropylene_Mine`, `Menge_Stahl_Mine` | `Energieverbrauch_Mine` |
| `LCA Prozess: Druckfeder` | `b3ba806e` | `Menge_Stahl_Druckfeder` | `Energieverbrauch_Druckfeder` |
| `Schraube M4` | `0b5fd7c7` | `Menge_Stahl_Schraube` | — |

Each part process carries several materials at once. This is deliberate: it lets you switch the material of a part without changing the model. The material that does not apply is set to zero on every calculation — the flows do this using the `LCAZeroParameters` entry stored in the AAS.

The package has been checked for completeness: all 1079 references it contains resolve within the package.

## Importing

1. **Obtain the background database.** The model refers to datasets from *idemat 2023*, freely available from <https://www.openlca.org/idemat-2023-available-for-openlca/>
2. Import it into openLCA and open it
3. `File → Import → Data package`, select this file
4. Start the IPC server: `Tools → Developer tools → IPC Server`, port `8080`

During the import openLCA recognises the idemat datasets that are already present by their identifier and does not duplicate them.

Afterwards `python ../setup.py --step 4` shows the identifier of the product system. Put it into `.env` under `SDI_OPENLCA_PRODUCT_SYSTEM`.

## Two properties that are easy to miss

Neither produces an error message in openLCA, but both lead to unusable results.

**The reference amount of every part process is 1 p.** If a weight in kilograms is used instead, openLCA scales the process by the reciprocal of that amount — a reference of 0.003 kg means a factor of 333.

**Every input flow needs a provider in the product system.** An unlinked input is calculated as zero regardless of the parameter value passed in. This affects the electricity input in particular: if the process has no default provider, `Build supply chain` will not create the link.

## NOTICE

This work is licensed under the [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/legalcode).

- SPDX-License-Identifier: CC-BY-4.0
- SPDX-FileCopyrightText: 2025 Heinz Nixdorf Institute
- SPDX-FileCopyrightText: 2025 Paderborn University
- SPDX-FileCopyrightText: 2025 Contributors to the Eclipse Foundation
- Source URL: <https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT>
