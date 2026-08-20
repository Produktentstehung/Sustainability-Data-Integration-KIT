#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright (c) 2025 Heinz Nixdorf Institute
# Copyright (c) 2025 Paderborn University
# Copyright (c) 2025 Contributors to the Eclipse Foundation
#
# See the NOTICE file(s) distributed with this work for additional
# information regarding copyright ownership.
#
# This program and the accompanying materials are made available under the
# terms of the Apache License, Version 2.0 which is available at
# https://www.apache.org/licenses/LICENSE-2.0.
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.
#
# SPDX-License-Identifier: Apache-2.0
"""Legt die Beispieldaten des TRACEpen in einer Odoo-Instanz an.

Creates the product categories, the custom field for the LCA flow UUID,
the six products with weight and category, and the bill of material. The
script is repeatable: existing records are updated rather than duplicated.

Configuration through environment variables (see .env.example):
    SDI_ODOO_URL, SDI_ODOO_DB, SDI_ODOO_USER, SDI_ODOO_APIKEY
    SDI_ODOO_FLOW_FIELD  (optional, Standard: x_studio_lca_flow_uuid)

Aufruf:  python setup_odoo_testdata.py
"""
import csv
import json
import os
import sys
import urllib.request

URL = os.environ.get("SDI_ODOO_URL", "").rstrip("/")
DB = os.environ.get("SDI_ODOO_DB", "")
USER = os.environ.get("SDI_ODOO_USER", "")
APIKEY = os.environ.get("SDI_ODOO_APIKEY", "")
FLOW_FIELD = os.environ.get("SDI_ODOO_FLOW_FIELD", "x_studio_lca_flow_uuid")

# Die Hilfe muss vor der Pruefung der Umgebung kommen: wer wissen will, was
# das Programm tut, hat die Zugangsdaten typischerweise noch nicht gesetzt.
if len(sys.argv) > 1 and sys.argv[1] in ('--help', '-h', '/?'):
    print((__doc__ or '').strip())
    sys.exit(0)

if not all([URL, DB, USER, APIKEY]):
    sys.exit("SDI_ODOO_URL, SDI_ODOO_DB, SDI_ODOO_USER und SDI_ODOO_APIKEY muessen gesetzt sein")

# Source of the bill of material: the PLM export in the repository. That way
# the values in Odoo, in the AAS and in the sample data agree.
BOM_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "..", "docs", "sample_data", "BOM_TRACEpen.csv")

# Final product (not a position of the bill of material itself)
FINAL_PRODUCT = {"name": "Kugelschreiber_TracePEN", "code": "000114",
                 "weight": 0.015, "material": "Mehrmaterial-Baugruppe"}

# Grobe Werkstoffgruppe je Material, dient als Odoo-Produktkategorie
MATERIAL_GROUP = {
    "Aluminiumlegierung AlMg1SiCu": "Aluminium",
    "Edelstahl": "Stahl",
    "Federstahl": "Stahl",
    "PLA Basic BambuLab Filament": "Kunststoff",
    "Polypropylene (PP)": "Kunststoff",
    "Mehrmaterial-Baugruppe": "Fertigprodukte",
}

# Zuordnung Komponente -> Datensaetze in der openLCA-Datenbank.
# Ermittelt aus der Datenbank idemat_2023_01_02_Kugelschreiber_2026_06_23
# through the IPC server.
#
# flow      = Produktfluss, den der Montageprozess des TRACEpen verbraucht
# process   = the process producing this flow
# parameter = quantity parameter of the material stated in the PLM
# zero      = the remaining quantity parameters of the same process
#
# The processes are modelled as templates: they carry several materials
# gleichzeitig, damit sich der Werkstoff eines Bauteils wechseln laesst, ohne
# without changing the model. The material that does not apply is set to 0.
# Therefore all quantity parameters must always be passed.
LCA_MAPPING = {
    "000115": {  # Mine, Polypropylene (PP)
        "flow": "a85a89b7-91f1-4134-8a16-a27c2734e243",
        "process": "98446bf7-e23a-454a-9e33-67cf55533b8c",
        "parameter": "Menge_Polypropylene_Mine",
        "zero": ["Menge_Stahl_Mine"],
    },
    "000116": {  # Bolzen Aluminium, AlMg1SiCu
        "flow": "9acbc449-b38e-461d-8168-c27856495fc5",
        "process": "90291baa-d449-4afc-9d2a-01e8e650afd8",
        "parameter": "Menge_Aluminium_Bolzen",
        "zero": ["Menge_Stahl_Bolzen"],
    },
    "000117": {  # Huelse Aluminium, AlMg1SiCu
        "flow": "8fbcdc22-28b4-4519-8c04-e6501e3656ce",
        "process": "57c37380-e320-4712-b605-48dca9472829",
        "parameter": "Menge_Aluminium_Huelse",
        "zero": ["Menge_Stahl_Huelse"],
    },
    "000118": {  # Schraube M4, Edelstahl
        "flow": "7f610c56-046c-4607-99f0-4f8fca7c60c8",
        "process": "0b5fd7c7-29c7-446b-8ed9-8ed75b5a07ee",
        "parameter": "Menge_Stahl_Schraube",
        "zero": [],
    },
    "000119": {  # Druckfeder, Federstahl
        "flow": "607bebae-306e-448b-8f05-2d406ae30166",
        "process": "b3ba806e-e296-4943-8bc7-01858c5ab333",
        "parameter": "Menge_Stahl_Druckfeder",
        "zero": [],
    },
    "000120": {  # Stiftspitze Helix PLA, PLA
        "flow": "87e61321-53bc-4ff1-9860-000182f50d78",
        "process": "5043f2ab-9463-470d-888e-1855c805b042",
        "parameter": "Menge_Stiftspitze_PLA",
        "zero": ["Menge_Stiftspitze_Polypropylene", "Menge_Stiftspitze_ABS"],
    },
}

# Produktsystem und Montageprozess des Endprodukts
PRODUCT_SYSTEM = "dc5bf90b-5ad5-4808-934f-f7a863ae1453"   # LCA Prozess: Kugelschreiber TRACEpen
ASSEMBLY_PROCESS = "5c609b0a-d929-4789-9024-e3dc11aff29f"

MATERIAL_FIELD = "x_lca_material"
PROCESS_FIELD = "x_lca_process_id"
PARAMETER_FIELD = "x_lca_parameter"
ZERO_FIELD = "x_lca_zero_parameters"

# --- Serial numbers ----------------------------------------------------------
# Which articles are produced in house and therefore carry a serial number.
# The PLM category does not tell reliably: it marks only one part as purchased
# although three of them are. So the list is configured, not guessed.
#
# The serial number is coded as ASSEMBLY-INSTANCE-PART-INSTANCE:
#
#     000114-001-000116-038   the 38th bolt, sitting in pen number one
#     000114-001-000000-000   the pen itself; it sits in nothing
#
# Six digits for the article number from the PLM, three for a running instance.
# Odoo composes the number from a prefix, a running number and a suffix, so a
# manufacturing order created by hand gets a correct number as well.
ASSEMBLY_ARTICLE = os.environ.get("SDI_ASSEMBLY_ARTICLE", "000114")
SERIAL_ARTICLES = [a.strip() for a in os.environ.get(
    "SDI_SERIAL_ARTICLES", "000114,000116,000117,000120").split(",") if a.strip()]
SERIAL_DIGITS = int(os.environ.get("SDI_SERIAL_DIGITS", "3"))


def read_bom():
    """Reads the PLM export and returns the bill of material positions."""
    with open(BOM_CSV, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    items = []
    for r in rows:
        code = r["Komponentennummer"].strip()
        items.append({
            "position": int(r["Position"]),
            "code": code,
            "name": r["Name"].strip(),
            "qty": float(r["Menge"]),
            "weight": float(r["Gewicht(kg)"]),
            "material": r["Material"].strip(),
            "lca": LCA_MAPPING.get(code, {}),
        })
    items.sort(key=lambda x: x["position"])
    return items

_uid = None


def rpc(service, method, args):
    payload = {"jsonrpc": "2.0", "method": "call", "id": 1,
               "params": {"service": service, "method": method, "args": args}}
    req = urllib.request.Request(URL + "/jsonrpc", data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        body = json.loads(resp.read())
    if "error" in body:
        err = body["error"].get("data", {})
        raise RuntimeError(f"{err.get('name', 'error')}: {err.get('message', body['error'])}")
    return body["result"]


def kw(model, method, args, kwargs=None):
    return rpc("object", "execute_kw", [DB, _uid, APIKEY, model, method, args, kwargs or {}])


_field_cache = {}


def available_fields(model):
    """Field names of the model. Odoo versions differ considerably here
    (z. B. entfiel uom_po_id in Odoo 19, type wurde durch is_storable ersetzt),
    so only fields that actually exist are sent."""
    if model not in _field_cache:
        _field_cache[model] = set(kw(model, "fields_get", [[], ["type"]]).keys())
    return _field_cache[model]


def filter_values(model, values):
    allowed = available_fields(model)
    kept = {k: v for k, v in values.items() if k in allowed}
    dropped = [k for k in values if k not in allowed]
    return kept, dropped


def find_or_create(model, domain, values, label):
    values, dropped = filter_values(model, values)
    if dropped:
        print(f"    note: not present in this Odoo version: {', '.join(dropped)}")
    ids = kw(model, "search", [domain], {"limit": 1})
    if ids:
        kw(model, "write", [ids, values])
        print(f"    aktualisiert: {label}")
        return ids[0]
    new_id = kw(model, "create", [values])
    print(f"    created:      {label}")
    return new_id


def main():
    global _uid
    print(f"Verbinde mit {URL} (DB {DB})")
    version = rpc("common", "version", [])
    print(f"  Serverversion: {version.get('server_version')}")

    _uid = rpc("common", "authenticate", [DB, USER, APIKEY, {}])
    if not _uid:
        sys.exit("  Anmeldung fehlgeschlagen - Benutzer oder API-Schluessel pruefen")
    print(f"  Angemeldet als uid={_uid}")

    # --- Custom fields ------------------------------------------------------
    print("\n1. Custom fields")
    model_ids = kw("ir.model", "search", [[["model", "=", "product.template"]]], {"limit": 1})
    felder = ((FLOW_FIELD, "LCA Flow UUID"), (MATERIAL_FIELD, "Werkstoff"),
              (PROCESS_FIELD, "LCA process id"), (PARAMETER_FIELD, "LCA quantity parameter"),
              (ZERO_FIELD, "LCA Parameter auf Null"))
    for fname, flabel in felder:
        existing = kw("ir.model.fields", "search",
                      [[["name", "=", fname], ["model", "=", "product.template"]]], {"limit": 1})
        if existing:
            print(f"    present:      {fname}")
            continue
        try:
            kw("ir.model.fields", "create", [{
                "name": fname, "field_description": flabel,
                "model_id": model_ids[0], "ttype": "char", "store": True,
            }])
            print(f"    created:      {fname}")
        except RuntimeError as exc:
            print(f"    FEHLER beim Anlegen von {fname}: {exc}")
            print("    -> please create the field manually in Odoo Studio (type: text)")

    # --- Decimal places for weights -----------------------------------------
    # By default Odoo rounds the weight field to two decimal places.
    # Part weights in the gram range then become 0.00, which is useless for
    # eine Oekobilanz unbrauchbar.
    print("\n1b. Decimal places for weights")
    try:
        prec_ids = kw("decimal.precision", "search", [[["name", "=", "Stock Weight"]]], {"limit": 1})
        if prec_ids:
            current = kw("decimal.precision", "read", [prec_ids], {"fields": ["digits"]})[0]["digits"]
            if current < 6:
                kw("decimal.precision", "write", [prec_ids, {"digits": 6}])
                print(f"    raised:       Stock Weight from {current} to 6 decimal places")
            else:
                print(f"    present:      Stock Weight with {current} decimal places")
        else:
            print("    note: entry 'Stock Weight' not found")
    except RuntimeError as exc:
        print(f"    FEHLER: {exc}")
        print("    -> otherwise weights below 0.01 kg are rounded to 0.")

    # --- Bill of material from the PLM export -------------------------------
    bom_items = read_bom()
    print(f"\n2. Bill of material from {os.path.basename(BOM_CSV)}")
    print(f"    {len(bom_items)} Positionen gelesen")
    ohne_uuid = [i["name"] for i in bom_items if not i["lca"].get("flow")]
    if ohne_uuid:
        print(f"    ohne Flow-UUID: {', '.join(ohne_uuid)}")
        print("    -> these positions are skipped by the flow.")

    # --- Produktkategorien --------------------------------------------------
    print("\n2b. Produktkategorien")
    groups = {MATERIAL_GROUP.get(i["material"], "Sonstige") for i in bom_items}
    groups.add(MATERIAL_GROUP.get(FINAL_PRODUCT["material"], "Fertigprodukte"))
    categories = {}
    for name in sorted(groups):
        categories[name] = find_or_create("product.category", [["name", "=", name]],
                                          {"name": name}, name)

    # --- Unit of measure ----------------------------------------------------
    uom_ids = kw("uom.uom", "search", [[["name", "in", ["Units", "Einheiten", "Stück", "Stueck"]]]],
                 {"limit": 1})
    uom_id = uom_ids[0] if uom_ids else None

    # --- Produkte -----------------------------------------------------------
    print("\n3. Produkte")
    entries = [(FINAL_PRODUCT["name"], FINAL_PRODUCT["code"], FINAL_PRODUCT["weight"],
                FINAL_PRODUCT["material"], {}, True)]
    entries += [(i["name"], i["code"], i["weight"], i["material"], i["lca"], False)
                for i in bom_items]

    product_ids = {}
    for name, code, weight, material, lca, is_final in entries:
        categ = MATERIAL_GROUP.get(material, "Sonstige")
        values = {
            "name": name,
            "default_code": code,
            "weight": weight,
            "categ_id": categories[categ],
            MATERIAL_FIELD: material,
            # In Odoo 19 is_storable replaces the earlier field type; both are
            # offered and reduced by filter_values to the one that exists.
            "is_storable": True,
            "type": "consu",
            "purchase_ok": not is_final,
            "sale_ok": is_final,
        }
        if uom_id:
            values["uom_id"] = uom_id
            values["uom_po_id"] = uom_id  # bis Odoo 18
        # The UUID is always written, even when empty. Otherwise a value from an
        # bei einem umbenannten Produkt der Wert des Vorgaengers stehen und
        # eine Komponente wuerde mit einem fremden Materialdatensatz gerechnet.
        values[FLOW_FIELD] = (lca or {}).get("flow", "")
        values[PROCESS_FIELD] = (lca or {}).get("process", "")
        values[PARAMETER_FIELD] = (lca or {}).get("parameter", "")
        values[ZERO_FIELD] = ", ".join((lca or {}).get("zero", []))
        pid = find_or_create("product.template", [["default_code", "=", code]], values,
                             f"{name} ({code}, {weight} kg, {material})")
        product_ids[name] = pid

    # Verify the stored weights - this reveals rounding losses
    print("\n3b. Checking the stored weights")
    stored = kw("product.template", "read", [list(product_ids.values())],
                {"fields": ["name", "weight"]})
    soll = {e[0]: e[2] for e in entries}
    for row in stored:
        ist = row.get("weight") or 0.0
        erwartet = soll.get(row["name"], 0.0)
        ok = abs(ist - erwartet) < 1e-9
        marke = "ok" if ok else "ABWEICHUNG"
        print(f"    {row['name']:14} soll {erwartet:<10} ist {ist:<10} {marke}")
        if not ok:
            print("      -> check the decimal places of the weight field "
                  "(Einstellungen -> Technisch -> Dezimalgenauigkeit)")

    # Flow-UUIDs auf Eindeutigkeit pruefen. Zwei Komponenten mit derselben UUID
    # wuerden auf denselben Materialdatensatz rechnen.
    print("\n3c. Kontrolle der Flow-UUIDs")
    uuids = kw("product.template", "read", [list(product_ids.values())],
               {"fields": ["name", "default_code", FLOW_FIELD, PARAMETER_FIELD]})
    seen = {}
    for row in uuids:
        val = row.get(FLOW_FIELD) or ""
        marke = "ohne UUID" if not val else ("DOPPELT mit " + seen[val] if val in seen else "ok")
        if val and val not in seen:
            seen[val] = row["name"]
        par = row.get(PARAMETER_FIELD) or "-"
        print(f"    {row['name']:24} {(val[:8] + '...') if val else '-':<12} {marke:<24} {par}")

    # --- Bill of material ---------------------------------------------------
    print(f"\n4. Bill of material {FINAL_PRODUCT['name']}")
    tmpl_id = product_ids[FINAL_PRODUCT["name"]]
    bom_ids = kw("mrp.bom", "search", [[["product_tmpl_id", "=", tmpl_id]]], {"limit": 1})
    lines = []
    for item in bom_items:
        comp_tmpl = product_ids[item["name"]]
        variant = kw("product.product", "search",
                     [[["product_tmpl_id", "=", comp_tmpl]]], {"limit": 1})
        line = {"product_qty": item["qty"]}
        if variant:
            line["product_id"] = variant[0]
        lines.append((0, 0, line))

    bom_values = {"product_tmpl_id": tmpl_id, "product_qty": 1.0, "type": "normal",
                  "bom_line_ids": [(5, 0, 0)] + lines}
    if bom_ids:
        kw("mrp.bom", "write", [bom_ids, bom_values])
        bom_id = bom_ids[0]
        print(f"    updated:      bill of material with {len(lines)} positions")
    else:
        bom_id = kw("mrp.bom", "create", [bom_values])
        print(f"    created:      bill of material with {len(lines)} positions")

    # --- Manufacturing order (optional) -------------------------------------
    print("\n5. Manufacturing order")
    try:
        variant = kw("product.product", "search", [[["product_tmpl_id", "=", tmpl_id]]], {"limit": 1})
        mo_ids = kw("mrp.production", "search",
                    [[["product_id", "=", variant[0]], ["state", "not in", ["cancel", "done"]]]],
                    {"limit": 1})
        if mo_ids:
            print("    present:      manufacturing order already exists")
        else:
            mo_id = kw("mrp.production", "create", [{
                "product_id": variant[0], "product_qty": 25.0, "bom_id": bom_id,
            }])
            kw("mrp.production", "action_confirm", [[mo_id]])
            print("    created:      manufacturing order over 25 pieces")
    except RuntimeError as exc:
        print(f"    skipped:      {exc}")
        print("    -> the flow also runs without a manufacturing order.")

    # --- Serial numbers -----------------------------------------------------
    print(chr(10) + "6. Serial numbers")
    if not SERIAL_ARTICLES:
        print("    skipped:      SDI_SERIAL_ARTICLES is empty")
    else:
        tmpls = kw("product.template", "search_read",
                   [[["default_code", "in", SERIAL_ARTICLES]]],
                   {"fields": ["default_code", "tracking",
                               "serial_prefix_format"]})
        for tmpl in tmpls:
            code = tmpl["default_code"]
            # The prefix carries everything left of the running number. For a
            # component the assembly is still unknown while it is being made,
            # so those blocks stay zero until assembly fills them in.
            prefix = (code + "-" if code == ASSEMBLY_ARTICLE
                      else "000000-000-" + code + "-")
            werte = {}
            if tmpl.get("tracking") != "serial":
                werte["tracking"] = "serial"
            if tmpl.get("serial_prefix_format") != prefix:
                werte["serial_prefix_format"] = prefix
            if werte:
                kw("product.template", "write", [[tmpl["id"]], werte])
                print("    set:          " + code + " " + ", ".join(werte))
            else:
                print("    present:      " + code)

        # Odoo keeps a dedicated number range per prefix. Digits and suffix
        # belong to that range, not to the product.
        tmpls = kw("product.template", "search_read",
                   [[["default_code", "in", SERIAL_ARTICLES]]],
                   {"fields": ["default_code", "lot_sequence_id"]})
        for tmpl in tmpls:
            kreis = tmpl.get("lot_sequence_id")
            code = tmpl["default_code"]
            if not kreis:
                print("    note:         " + code + " has no own number range "
                      "yet; Odoo creates it with the first serial number")
                continue
            suffix = "-000000-000" if code == ASSEMBLY_ARTICLE else ""
            kw("ir.sequence", "write", [[kreis[0]], {
                "padding": SERIAL_DIGITS, "suffix": suffix}])
            print("    range set:    " + code + " -> "
                  + str(SERIAL_DIGITS) + " digits"
                  + (", suffix " + suffix if suffix else ""))

    print("\nDone. The flow Odoo_ERP.json can now be run.")


if __name__ == "__main__":
    main()
