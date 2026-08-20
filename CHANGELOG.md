# Changelog

All notable changes to this repository will be documented in this file.
Further information can be found on the [README.md](README.md) file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
## [0.2.0]

### Added

- `docs/sample_data/AASX/BaseShell_Template.aasx`, the template shell the PLM
  connection fills. The shell-building script is deliberately not part of the
  repository - it depends on the object model of the PLM system - but without
  the template nobody could see what structure that script has to produce.
  Product data, attached files and the manufacturer of the reference
  installation are removed; the seven submodels and their 188 properties are
  intact.

- A dashboard of its own (`src/Dashboard.json`) at `/dashboard/kit`: the
  footprint with its reference quantity, one button that runs the chain and
  checks every step, the state of each data source, the result split by part,
  and the recorded machine runs. It replaces the operating panel that used to
  sit inside the calculation flow.
- Serial numbers. `setup-odoo.ps1` switches on serial tracking for the parts
  produced in house and tells Odoo how to compose a number; the coding and the
  reasoning are in `getting-started/ODOO.md`.
- `src/Assembly_Booking.json` books an assembly in Odoo - one piece, its
  components with their own numbers - and records it in the shell.
  `src/Assembly_Backfill.json` restores those records from Odoo.
- Machine measurements now carry the serial number of the piece they produced,
  the manufacturing order, their own time window and, where a run covers
  several pieces, a note that the energy per piece is an average.
- A dropdown selects one manufactured piece; the machine table then shows only
  the runs that produced its parts.

- An Industry Extension for discrete manufacturing: what the sector adds to the
  base KIT, the companion specifications an adopter should build against
  (OPC 34100 energy consumption, OPC 40501-1 machine tools), and the three
  decisions - threshold, allocation, piece assignment - that do not follow from
  the data.
- `.github/workflows/checks.yml` and `src/check_flows.py`: the flow files, the
  programs, the sample packages and the documented settings are checked on
  every contribution.
- `.github/CODEOWNERS`, required for a KIT to graduate. The handles are
  placeholders and have to be filled in.

- `check_flows.py` now walks the flows from their entry points and reports
  anything a message can never reach. It found sixteen such nodes in the
  calculation flow, left over from the operating panel that used to sit in it.

### Fixed

- **Every message a user sees is in English.** Ninety-eight `node.error` and
  `node.warn` messages across the eight flows were in German - the very
  sentences an adopter reads when something goes wrong, which is when they
  need them most. The comments in the flows and the design rationale in the
  dashboard stylesheet were translated with them, so that the source is
  readable to anyone who wants to contribute.

  Two things were deliberately left in German: the names of local variables,
  and the keys inside message payloads. Neither is visible to a user, and the
  dashboard reads some of those keys - renaming them would break the display
  without anything reporting an error.
- `TargetOutput` in the ILCD submodel read "1 Stueck". It now reads
  "1 piece", with a plural for larger quantities. The dashboard still
  translates the old spelling, so shells written earlier keep displaying
  correctly.
- The empty containers that the template shell carries - `isCaseOf`,
  `supplementalSemanticIds`, `valueList` and their kin - are removed as well.
  Together with the earlier idShort work this takes a sample package from 94
  findings to 26.
- The table of contents of the README pointed at five headings that do not
  exist: GitHub leaves a double hyphen where punctuation between spaces was
  removed, and the links carried one. `src/check_docs.py` now checks every
  link and image in the documentation, and runs in CI.

- Packages exported from the dashboard carried 114 violations of the
  specification each, while the sample data shipped with the KIT carried
  none - the export reproduced what the template shell contains and never
  cleaned it. `src/export_aasx.py` now applies the same cleaning the PLM
  generator applies, so a package from either route comes out alike.
- `repair_aasx.py` additionally normalises idShorts that hold characters the
  specification forbids (`Weight (g)`) and removes the idShort from direct
  children of a submodel element list (AASd-120). A name is only changed when
  it is referenced nowhere else, so no pointer is broken. Across the sample
  packages this took the count from 750 findings to 396.
- The cleaning repeats until nothing changes. Its last step reserialises the
  document, which writes empty elements in an equivalent but different form,
  and a single pass therefore left work behind - the repair was not
  idempotent and the check that the sample data needs no repair could not
  have passed.

- **The chain stopped writing the result of the product.** Removing the old
  operating panel from the calculation flow cut a path: one of its widgets was
  not the end of a chain but a station in the middle of one. Part results kept
  being written, so nothing looked wrong - the product simply kept the value of
  the previous run. The path is restored, and the check above now catches this
  class of defect.
- Sixteen unreachable nodes removed from the calculation flow.
- The PLM flow for the product referred to a variable before it existed
  (`env.get('SDI_PLM_WORK_DIR') || WORK_DIR`), so it failed for anyone who had
  not set that variable. `.env.example` no longer proposes a Windows path for
  it either.
- Generated AASX packages were rejected outright, for two reasons that had
  nothing to do with their content: a `Thumbs.db` picked up from the template
  folder, and a CAD companion file whose extension had no declared content
  type. Both are handled where the package is built.
- Generated packages inherited the empty placeholders of their template. The
  generator now cleans them at the source, using the same function as
  `repair_aasx.py`, so a package is born valid rather than needing repair.
- The sample packages were regenerated with the shipped script. They now carry
  the serial number pattern of this KIT, and the tutorial's first import is a
  package that passes the check.
- Two further programs answered `--help` with a stack trace. The check runs
  over every program in `src` now rather than over a list that ages.
- The tutorial's overview described a different path than its own steps: the
  table led through the command line, the sections through the dashboard.
- The sample data table promised a file from an ERP system that does not
  exist. Every sample file is now named, with what it is for.

- The use case chapter claimed production data down to instance level as an
  intention; it is implemented, and the chapter now says how - including what
  the KIT does when a piece was never measured.
- Two passages in the Operations View stated that the ERP and OPC UA
  integrations were not implemented, contradicting the status table two pages
  above them.
- The whitepaper section still held the placeholder text of the KIT template.
- The sample AASX packages violated the specification in 143 places: empty
  qualifiers, a description carrying the same language three times, typed
  properties with no value, and the shell pointing at its submodels through
  external instead of model references. `repair_aasx.py` now cleans the content
  of a package, not only its packaging.
- The ERP flow rebuilt its part of the shell and discarded entries written by
  other flows, among them the assembly records. It now keeps what is not its
  own.
- An empty single score was written as a number with no value, which the AASX
  check rejected. It is only written when the impact method provides one, and
  a stale entry from an earlier run is removed.
- Identifiers of manufacturing runs used hyphens, which an idShort does not
  allow, and members of a submodel element list carried an idShort, which the
  specification forbids.
- The PLM flow wrote its scratch files to a fixed Windows path. The directory
  is configurable (`SDI_PLM_JOBDIR`) and defaults to a folder next to the
  working directory.
- `repair_aasx.py` and `ema_export_to_json.py` treated `--help` as a file name
  and ended in a stack trace.
- Nine environment variables were in use without being described in
  `.env.example`.

## [0.1.0]

### Added

- Published first version of the Sustainability-Data-Integration-KIT.

# NOTICE
This work is licensed under the CC-BY-4.0.
* SPDX-License-Identifier: CC-BY-4.0
* SPDX-FileCopyrightText: 2025 Heinz Nixdorf Institute
* SPDX-FileCopyrightText: 2025 Paderborn University
* SPDX-FileCopyrightText: 2025 Contributors to the Eclipse Foundation
* Source URL: https://github.com/Produktentstehung/Sustainability-Data-Integration-KIT
