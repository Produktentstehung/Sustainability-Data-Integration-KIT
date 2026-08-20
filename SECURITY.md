# Security Policy

## Reporting a Vulnerability

Please do **not** report security vulnerabilities through public GitHub issues.

Report them to the Eclipse Foundation security team at <security@eclipse.org>,
or through the Eclipse Foundation vulnerability reporting process described at
<https://www.eclipse.org/security/>. Reports may also be filed as a GitHub
security advisory on this repository.

Please include as much of the following as you can:

- the affected component and version
- the type of issue and how it can be reproduced
- the impact you expect, including how an attacker might exploit it
- any special configuration required to trigger the issue

You will receive an acknowledgement of your report. We will keep you informed
about the progress towards a fix and may ask for additional information.

## Scope

This repository contains the reference implementation of the Sustainability
Data Integration KIT: integration flows, setup scripts and sample data.

Vulnerabilities in the third-party components the KIT builds on are reported to
the respective project, not here:

| Component | Where to report |
| --- | --- |
| Node-RED | <https://nodered.org/about/security/> |
| Eclipse BaSyx | <https://www.eclipse.org/security/> |
| openLCA | <https://www.openlca.org/> |
| Eclipse Tractus-X EDC | <https://www.eclipse.org/security/> |

## Known limitations of the reference implementation

The reference implementation was built as a laboratory demonstrator. The
following properties are known and documented, and MUST be addressed before
productive use. They are not accepted as vulnerability reports:

- components communicate over plain HTTP against `localhost`, without TLS
- the AAS server is addressed without authentication
- the user interface has no authentication layer
- credentials for PLM and ERP are held as environment variables of the Node-RED
  process; they are not stored in the flows, but any operator of that process
  can read them

The section *Guidelines Security* in `README.md` describes what an operator has
to put in place instead.

## NOTICE

This work is licensed under the [CC-BY-4.0](https://creativecommons.org/licenses/by/4.0/legalcode).

- SPDX-License-Identifier: CC-BY-4.0
- SPDX-FileCopyrightText: 2025 Heinz Nixdorf Institute
- SPDX-FileCopyrightText: 2025 Paderborn University
- SPDX-FileCopyrightText: 2025 Contributors to the Eclipse Foundation
- Source URL: <https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT>
