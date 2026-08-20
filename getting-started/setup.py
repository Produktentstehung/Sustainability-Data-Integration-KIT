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
"""Set up the Sustainability Data Integration KIT on a new machine.

The script walks through the setup step by step and stops with a readable
message as soon as a prerequisite is missing. It is repeatable: steps that are
already done are recognised and skipped.

Steps:

  1. Check prerequisites   Docker, Python, Node.js, Node-RED
  2. Start services        AAS server, registries, web interface
  3. Import sample data    AASX packages of the parts into the AAS server
  4. Check openLCA         IPC server reachable, model complete
  5. Provide flows         set up the Node-RED working directory

Usage:

    python setup.py              all steps
    python setup.py --step 3     a single step
    python setup.py --check      only check, change nothing
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))


def load_env():
    """Read .env into the environment.

    The flows and this script take their settings from environment variables.
    Without this, a value written into .env would only reach Node-RED through
    the start script, and the setup would not see it - the PLM flow would
    silently stay out of the generated flows.json, for example.

    Values already present in the environment win, so a variable set on the
    command line still overrides the file.
    """
    pfad = os.path.join(HERE, ".env")
    if not os.path.exists(pfad):
        return
    with open(pfad, encoding="utf-8") as fh:
        for zeile in fh:
            zeile = zeile.strip()
            if not zeile or zeile.startswith("#") or "=" not in zeile:
                continue
            name, _, wert = zeile.partition("=")
            name, wert = name.strip(), wert.strip()
            if name and wert and name not in os.environ:
                os.environ[name] = wert


load_env()
REPO = os.path.dirname(HERE)
AASX_DIR = os.path.join(REPO, "docs", "sample_data", "AASX")
FLOW_DIR = os.path.join(REPO, "src")
NODERED_DIR = os.path.join(HERE, "nodered")

AAS_URL = os.environ.get("SDI_AAS_URL", "http://localhost:8081")
OPENLCA_URL = os.environ.get("SDI_OPENLCA_URL", "http://localhost:8080")

# The flows that together form the processing chain.
# PLM.json is not included: it is a reference implementation for a CONTACT
# Elements PLM system and needs a PLM server reachable from your own network,
# plus the export paths of your installation. Adapt its configuration node and
# add it here once that is in place.
FLOWS = ["Odoo_ERP.json", "EMA.json", "OPCUA_Manufacturing.json", "OpenLCA_to_AAS.json"]

# PLM.json is added only once a PLM system is configured. It is a reference
# implementation for CONTACT Elements and needs a server reachable from your
# own network, plus the script that builds the shell from the PLM data.
if os.environ.get("SDI_PLM_URL"):
    FLOWS.append("PLM.json")

OK, WARN, MISS = "  [ok]   ", "  [!]    ", "  [MISSING]"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def heading(text):
    print("\n" + text)
    print("-" * len(text))


def program_version(name, args=("--version",)):
    """Return the version of a program, or None if it cannot be called."""
    path = shutil.which(name)
    if not path:
        return None
    try:
        out = subprocess.run([path] + list(args), capture_output=True,
                             text=True, timeout=60)
        return (out.stdout or out.stderr).strip().split("\n")[0]
    except Exception:
        return "available"


def http_json(url, data=None, method=None, timeout=30):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body,
                                 method=method or ("POST" if body else "GET"),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        text = r.read().decode("utf-8", "replace")
    return json.loads(text) if text else {}


def reachable(url, timeout=5):
    try:
        urllib.request.urlopen(url, timeout=timeout)
        return True
    except urllib.error.HTTPError:
        return True          # it responds, even if with an error code
    except Exception:
        return False


def olca(method, params, timeout=60):
    return http_json(OPENLCA_URL, {"jsonrpc": "2.0", "id": 1,
                                   "method": method, "params": params},
                     timeout=timeout)


# ---------------------------------------------------------------------------
# Step 1 - prerequisites
# ---------------------------------------------------------------------------
def step_1(check=False):
    heading("Step 1 - prerequisites")
    missing = []

    for name, args, hint in [
        ("docker", ("--version",), "Docker Desktop from docker.com"),
        ("python", ("--version",), "Python 3.10 or newer"),
        ("node", ("--version",), "Node.js 18 or newer"),
        ("node-red", ("--version",), "npm install -g node-red"),
    ]:
        version = program_version(name, args)
        if version:
            print(f"{OK}{name:<10} {version}")
        else:
            print(f"{MISS} {name:<10} not found - {hint}")
            missing.append(name)

    try:
        import openpyxl  # noqa: F401
        print(f"{OK}openpyxl   available (needed to read the simulation export)")
    except ImportError:
        print(f"{WARN}openpyxl   missing - the simulation export cannot be read")
        print("           Fix: python -m pip install openpyxl")

    if shutil.which("docker"):
        try:
            subprocess.run(["docker", "info"], capture_output=True,
                           timeout=30, check=True)
            print(f"{OK}Docker is running")
        except Exception:
            print(f"{MISS} Docker is installed but not running - start Docker Desktop")
            missing.append("docker-daemon")

    return not missing


# ---------------------------------------------------------------------------
# Step 2 - start the services
# ---------------------------------------------------------------------------
def step_2(check=False):
    heading("Step 2 - start the services")

    if reachable(AAS_URL + "/shells"):
        print(f"{OK}AAS server already responds at {AAS_URL}")
        return True
    if check:
        print(f"{MISS} AAS server not reachable at {AAS_URL}")
        return False

    print("  Starting the containers ...")
    try:
        subprocess.run(["docker", "compose", "up", "-d"], cwd=HERE,
                       check=True, timeout=600)
    except subprocess.CalledProcessError as e:
        print(f"{MISS} docker compose failed: {e}")
        return False

    print("  Waiting for the AAS server ", end="", flush=True)
    for _ in range(60):
        if reachable(AAS_URL + "/shells"):
            print(" ready")
            print(f"{OK}AAS server at {AAS_URL}")
            print(f"{OK}Web interface at http://localhost:3000")
            return True
        print(".", end="", flush=True)
        time.sleep(5)
    print()
    print(f"{MISS} The AAS server did not come up - 'docker compose logs aas-env' shows why")
    return False


# ---------------------------------------------------------------------------
# Step 3 - import the sample data
# ---------------------------------------------------------------------------
def step_3(check=False):
    heading("Step 3 - import the sample data")

    if not reachable(AAS_URL + "/shells"):
        print(f"{MISS} AAS server not reachable - run step 2 first")
        return False

    existing = http_json(AAS_URL + "/shells").get("result", [])
    names = {s.get("idShort") for s in existing}
    if names:
        print(f"{OK}Already imported: {', '.join(sorted(n for n in names if n))}")

    # Only the AASX packages of the product and its parts are imported.
    # The files named Submodel_*.aasx are empty submodel templates; importing
    # them would create shells without a name.
    packages = []
    for root, _, files in os.walk(AASX_DIR):
        packages += [os.path.join(root, f) for f in files
                     if f.lower().endswith(".aasx")
                     and not f.startswith("Submodel_")]
    if not packages:
        print(f"{MISS} No AASX packages found under {AASX_DIR}")
        return False

    # The packages have to comply with the OPC specification, otherwise the AAS
    # server rejects them. repair_aasx.py fixes the most common violations.
    repair = os.path.join(FLOW_DIR, "repair_aasx.py")
    if os.path.exists(repair) and not check:
        print("  Checking the packages ...")
        subprocess.run([sys.executable, repair, AASX_DIR], timeout=600)

    if check:
        print(f"  {len(packages)} packages found, {len(names)} shells present")
        return True

    added = 0
    for path in sorted(packages):
        name = os.path.basename(path)
        code = upload_aasx(path)
        if code == 200:
            added += 1
            print(f"{OK}{name}")
        elif code == 409:
            print(f"{OK}{name} (already present)")
        else:
            print(f"{WARN}{name}: HTTP {code}")

    after = http_json(AAS_URL + "/shells").get("result", [])
    print(f"\n  {len(after)} shells on the AAS server, {added} newly imported")
    return len(after) > 0


def upload_aasx(path):
    """Upload an AASX package as multipart/form-data."""
    boundary = "----SDIKitBoundary"
    with open(path, "rb") as fh:
        content = fh.read()
    name = os.path.basename(path)
    body = (f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: application/octet-stream\r\n\r\n").encode() \
        + content + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        AAS_URL + "/upload", data=body, method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Step 4 - check openLCA
# ---------------------------------------------------------------------------
def step_4(check=False):
    heading("Step 4 - check openLCA")

    if not reachable(OPENLCA_URL):
        print(f"{MISS} openLCA does not respond at {OPENLCA_URL}")
        print("           In openLCA: open a database, then")
        print("           Tools -> Developer tools -> IPC Server, port 8080, Start")
        return False
    print(f"{OK}IPC server reachable")

    try:
        methods = olca("data/get/descriptors", {"@type": "ImpactMethod"}).get("result", [])
        systems = olca("data/get/descriptors", {"@type": "ProductSystem"}).get("result", [])
        processes = olca("data/get/descriptors", {"@type": "Process"}).get("result", [])
    except Exception as e:
        print(f"{MISS} Query failed: {e}")
        print("           Is a database open in openLCA?")
        return False

    print(f"{OK}{len(processes)} processes, {len(systems)} product systems, "
          f"{len(methods)} impact methods")

    default = os.environ.get("SDI_OPENLCA_DEFAULT_METHOD",
                             "b4571628-4b7b-3e4f-81b1-9a8cca6cb3f8")
    hit = next((m for m in methods if m.get("@id") == default), None)
    if hit:
        print(f"{OK}Default impact method present: {hit.get('name')}")
    else:
        print(f"{WARN}Default impact method not found ({default})")
        print("           Set a different one via SDI_OPENLCA_DEFAULT_METHOD")

    system = os.environ.get("SDI_OPENLCA_PRODUCT_SYSTEM", "")
    if system:
        hit = next((s for s in systems if s.get("@id") == system), None)
        print((OK + "Product system present: " + hit.get("name")) if hit
              else (WARN + "Product system not found: " + system))
    else:
        print(f"{WARN}SDI_OPENLCA_PRODUCT_SYSTEM is not set")
        if systems:
            print("           Available product systems:")
            for s in systems[:10]:
                print(f"             {s.get('name')}  ->  {s.get('@id')}")

    if not systems:
        print(f"{MISS} The open database contains no product system")
        print("           Import the data package of the KIT and open the database,")
        print("           see getting-started/openlca/README.md")
        return False
    return True


# Nodes the flows use that are not part of the Node-RED core. Without them
# Node-RED loads the flows but shows every affected node as "unknown node
# type", and nothing can be triggered.
EXTRA_NODES = {
    "@flowfuse/node-red-dashboard": "the dashboard the flows are operated from",
    "node-red-node-base64": "encodes the submodel identifiers for the AAS API",
}


def install_extra_nodes():
    """Installs the additional Node-RED nodes into the user directory.

    They are installed locally, next to the flows, not globally - that keeps
    the KIT independent of whatever else is installed on the machine.
    """
    package = os.path.join(NODERED_DIR, "package.json")
    if not os.path.exists(package):
        with open(package, "w", encoding="utf-8") as fh:
            json.dump({"name": "sdi-kit-flows", "version": "1.0.0",
                       "private": True,
                       "dependencies": {n: "*" for n in EXTRA_NODES}}, fh, indent=2)

    installed = os.path.join(NODERED_DIR, "node_modules")
    if all(os.path.exists(os.path.join(installed, *n.split("/")))
           for n in EXTRA_NODES):
        print(f"{OK}additional nodes already installed")
        return True

    print("\n  Installing the additional Node-RED nodes ...")
    for name, purpose in EXTRA_NODES.items():
        print(f"    {name:<34} {purpose}")
    try:
        subprocess.run(["npm", "install", "--no-audit", "--no-fund"],
                       cwd=NODERED_DIR, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                       shell=(os.name == "nt"))
    except (subprocess.CalledProcessError, FileNotFoundError) as err:
        print(f"{MISS} Installation failed: {err}")
        print(f"         Fix: run 'npm install' in {NODERED_DIR}")
        return False
    print(f"{OK}additional nodes installed")
    return True


# ---------------------------------------------------------------------------
# Step 5 - provide the flows
# ---------------------------------------------------------------------------
def step_5(check=False):
    heading("Step 5 - provide the flows")

    missing = [f for f in FLOWS if not os.path.exists(os.path.join(FLOW_DIR, f))]
    if missing:
        print(f"{MISS} Flows not found: {', '.join(missing)}")
        return False

    combined = []
    for name in FLOWS:
        with open(os.path.join(FLOW_DIR, name), encoding="utf-8") as fh:
            nodes = json.load(fh)
        combined += nodes
        print(f"{OK}{name:<24} {len(nodes):>3} nodes")

    if check:
        print(f"  {len(combined)} nodes in total")
        return True

    os.makedirs(NODERED_DIR, exist_ok=True)
    target = os.path.join(NODERED_DIR, "flows.json")
    with open(target, "w", encoding="utf-8") as fh:
        json.dump(combined, fh, ensure_ascii=False, indent=4)
    print(f"\n{OK}{len(combined)} nodes written to {target}")

    settings = os.path.join(NODERED_DIR, "settings.js")
    if not os.path.exists(settings):
        with open(settings, "w", encoding="utf-8") as fh:
            fh.write(SETTINGS_JS)
        print(f"{OK}settings.js created")

    install_extra_nodes()

    print("\n  Start Node-RED with:")
    print(f"    node-red -u \"{NODERED_DIR}\" -s \"{settings}\"")
    print("  Then open http://localhost:1880")
    return True


SETTINGS_JS = """// Node-RED settings for the SDI-KIT.
// Credentials belong in environment variables, not in this file.
module.exports = {
    uiPort: process.env.PORT || 1880,
    flowFile: 'flows.json',
    // Key used to encrypt stored credentials. Without it Node-RED generates
    // one and keeps it next to the credentials file.
    credentialSecret: process.env.SDI_CREDENTIAL_SECRET || false,
    // The PLM flow writes intermediate files and reads the shell template,
    // so it needs fs and path in the global context.
    functionGlobalContext: { fs: require('fs'), path: require('path') },
    logging: { console: { level: 'info', metrics: false, audit: false } },
    editorTheme: { projects: { enabled: false } }
};
"""


# ---------------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(description="Set up the SDI-KIT")
    p.add_argument("--step", type=int, choices=[1, 2, 3, 4, 5],
                   help="run only this step")
    p.add_argument("--check", action="store_true",
                   help="only check, change nothing")
    args = p.parse_args()

    print("Sustainability Data Integration KIT - setup")
    print("=" * 42)
    print(f"Repository : {REPO}")
    print(f"AAS server : {AAS_URL}")
    print(f"openLCA    : {OPENLCA_URL}")

    steps = {1: step_1, 2: step_2, 3: step_3, 4: step_4, 5: step_5}
    order = [args.step] if args.step else [1, 2, 3, 4, 5]

    result = {}
    for nr in order:
        try:
            result[nr] = steps[nr](args.check)
        except Exception as e:
            print(f"{MISS} Step {nr} aborted: {e}")
            result[nr] = False
        if not result[nr] and nr in (1, 2):
            print("\nThe remaining steps depend on this one - stopping here.")
            break

    heading("Summary")
    names = {1: "Prerequisites", 2: "Services", 3: "Sample data",
             4: "openLCA", 5: "Flows"}
    for nr in order:
        if nr in result:
            print(f"  {nr}. {names[nr]:<16} {'ok' if result[nr] else 'open'}")
    if all(result.get(n) for n in order):
        print("\nSetup complete.")
    else:
        print("\nSome points are still open, see the notes above.")


if __name__ == "__main__":
    main()
