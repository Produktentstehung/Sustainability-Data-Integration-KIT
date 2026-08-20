# Installation

The KIT is not a deployable service. It consists of integration flows that run
in Node-RED, an AAS server that holds the data, and an LCA tool that performs
the calculation. Installing it means bringing those three together.

## Quick start

```bash
git clone https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT.git
cd Sustainability-Data-Integration-KIT/getting-started
python setup.py
```

The script works through five steps and stops with a readable message as soon as
something is missing:

| Step | What happens |
| --- | --- |
| 1 | check prerequisites — Docker, Python, Node.js, Node-RED |
| 2 | start the AAS server, the registries and the web interface |
| 3 | import the AASX packages of the product and its parts |
| 4 | check the openLCA connection and the model content |
| 5 | assemble the flows and install the Node-RED add-ons |

It is repeatable: steps already completed are recognised and skipped.

## Prerequisites

| Software | Purpose |
| --- | --- |
| Docker Desktop | runs the AAS server, the registries and MongoDB |
| Python 3.10+ | setup, reading the simulation export |
| Node.js 18+ and Node-RED | executes the integration flows |
| openLCA 2.x | calculates the environmental impacts |

One Python package is needed to read the simulation exports:

```bash
python -m pip install openpyxl
```

## The LCA database

The only step the setup script cannot do for you. openLCA databases contain
licensed background data and are several gigabytes in size, so they are not part
of this repository. `getting-started/openlca/README.md` describes how to obtain
the background database and import the model of the example product.

## Configuration

Copy `getting-started/.env.example` to `getting-started/.env` and fill it in.
Credentials do not belong in that file — leave `SDI_ODOO_APIKEY` and
`SDI_PLM_PASSWORD` empty and let `start-nodered.ps1` ask for them at startup.

## Optional tools

| Tool | Purpose |
| --- | --- |
| [AASX Package Explorer](https://github.com/admin-shell-io/aasx-package-explorer) | opens the AASX packages of the sample data, useful for inspecting a shell without a running server |
| OPC UA server | needed only for the machine-data connection |
| PLM or ERP system with an API | needed only for those two connections; the chain runs without them |

## Where to go next

- `getting-started/TUTORIAL.md` — step by step from an empty machine to the
  first calculated result, with a check after every step
- `getting-started/README.md` — the condensed reference, including the common
  pitfalls
- `README.md` — the KIT itself: concept, standards, data mapping and the
  operational guidelines

## NOTICE

This work is licensed under the [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/legalcode).

- SPDX-License-Identifier: CC-BY-4.0
- SPDX-FileCopyrightText: 2025 Heinz Nixdorf Institute
- SPDX-FileCopyrightText: 2025 Paderborn University
- SPDX-FileCopyrightText: 2025 Contributors to the Eclipse Foundation
- Source URL: <https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT>
