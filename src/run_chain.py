"""Runs the whole processing chain from the command line and checks each step.

The flows can be started by hand in the Node-RED editor. For a repeatable run -
in a test, on a schedule, or simply to see everything at once - this script
drives them through the Node-RED admin interface instead, and verifies after
every step that the data actually arrived in the shells.

Steps, in the order in which they depend on each other:

  1. import      read AASX packages into the AAS server
  2. fix         remove the specification violations of the imported shells
  3. erp         bill of material and manufacturing order
  4. simulation  assembly energy per operation
  5. machines    measured production energy, where measurements exist
  6. calculate   openLCA, overall result and the share of each part
  7. export      AASX packages, checked for readability

Each step verifies its own result before the next one begins. A step that
fails ends the run with a message naming what was missing.

Usage:
    python run_chain.py                     all steps
    python run_chain.py --from 3            start at step 3
    python run_chain.py --skip machines     leave single steps out
    python run_chain.py --import-dir ../docs/sample_data/AASX/TRACEpen_Kugelschreiber

Addresses come from the environment: SDI_AAS_URL, SDI_NODERED_URL, SDI_AAS_BASE.

Copyright (c) 2025 Heinz Nixdorf Institute
Copyright (c) 2025 Paderborn University
Copyright (c) 2025 Contributors to the Eclipse Foundation

See the NOTICE file(s) distributed with this work for additional
information regarding copyright ownership.

This program and the accompanying materials are made available under the
terms of the Apache License, Version 2.0 which is available at
https://www.apache.org/licenses/LICENSE-2.0.

SPDX-License-Identifier: Apache-2.0
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))

AAS_URL = os.environ.get('SDI_AAS_URL', 'http://localhost:8081')
NODERED_URL = os.environ.get('SDI_NODERED_URL', 'http://localhost:1880')
BASE = os.environ.get('SDI_AAS_BASE', 'localhost/demo/aas')
PRODUCT = os.environ.get('SDI_LCA_PRODUCT', 'Kugelschreiber_TracePEN')

# The inject nodes are found by name, not by identifier: names are visible in
# the editor, identifiers are not. Several spellings are accepted per step, so
# that a renamed node does not break the run.
TRIGGERS = {
    'erp': ['erp'],
    'simulation': ['simulation'],
    'machines': ['machine', 'maschinen'],
    'calculate': ['chain', 'kette', 'calculation'],
}

# Both spellings are accepted. Since the data sources were unified they are
# called PLM, ERP, Simulation and MachineData; shells created earlier still
# carry the previous names, and a run should not fail over that.
SYNONYMS = {
    'PLM': ['PLM', 'EngineeringData_PLM', 'Engineering Data / PLM'],
    'ERP': ['ERP', 'ERPData'],
    'Simulation': ['Simulation'],
    'MachineData': ['MachineData', 'Manufacturing'],
}


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def fetch(path, server=None):
    request = urllib.request.Request((server or AAS_URL) + path,
                                     headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        raw = response.read()
    return json.loads(raw) if raw else {}


def heading(number, text):
    print()
    print('=' * 74)
    print('Step %s - %s' % (number, text))
    print('=' * 74)


def give_up(text):
    print()
    print('STOPPED: %s' % text)
    sys.exit(1)


def inject_nodes():
    """Reads the inject nodes of the deployed flows, keyed by their name."""
    try:
        flows = fetch('/flows', NODERED_URL)
    except Exception as error:
        give_up('Node-RED is not reachable at %s (%s). Is it running?'
                % (NODERED_URL, type(error).__name__))
    found = {}
    for node in flows if isinstance(flows, list) else []:
        if node.get('type') == 'inject':
            found[node.get('name') or ''] = node.get('id')
    return found


def trigger(name):
    """Starts the flow whose inject node carries the given word in its name."""
    nodes = inject_nodes()
    for needle in TRIGGERS[name]:
        for label, node_id in nodes.items():
            if needle in label.lower():
                request = urllib.request.Request(
                    '%s/inject/%s' % (NODERED_URL, node_id), data=b'',
                    method='POST')
                try:
                    with urllib.request.urlopen(request, timeout=60) as response:
                        return response.status
                except urllib.error.HTTPError as error:
                    return error.code
    give_up('No inject node found for step "%s". Expected a name containing '
            'one of: %s. Known inject nodes: %s. Are the flows deployed?'
            % (name, ', '.join(TRIGGERS[name]),
               ', '.join(sorted(n for n in nodes if n)) or 'none'))


def wait_for(check, seconds, description):
    """Waits until the check becomes true. Returns whether it did."""
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            if check():
                return True
        except Exception:
            pass
        time.sleep(5)
    print('   Timed out waiting for: %s' % description)
    return False


def data_source(shell, name):
    """Returns a data source from the submodel DataSources of a shell."""
    submodel = fetch('/submodels/' + b64('%s/%s/DataSources' % (BASE, shell)))
    container = None
    for element in submodel.get('submodelElements') or []:
        if element.get('idShort') == 'DataSources':
            container = element
    for wanted in SYNONYMS.get(name, [name]):
        for source in (container or {}).get('value') or []:
            if source.get('idShort') == wanted:
                return source
    return None


def child(collection, name):
    for element in (collection or {}).get('value') or []:
        if element.get('idShort') == name:
            return element
    return None


def value_of(collection, name):
    element = child(collection, name)
    return element.get('value') if element else None


# --------------------------------------------------------------------------
def step_import(directory):
    heading(1, 'Import the AASX packages')
    if not os.path.isdir(directory):
        give_up('Import directory not found: %s' % directory)
    packages = sorted(f for f in os.listdir(directory) if f.endswith('.aasx'))
    if not packages:
        give_up('No AASX packages in %s' % directory)

    existing = fetch('/shells').get('result') or []
    for shell in existing:
        urllib.request.urlopen(urllib.request.Request(
            AAS_URL + '/shells/' + b64(shell['id']), method='DELETE'), timeout=60)
    removed = 0
    for submodel in fetch('/submodels?limit=500').get('result') or []:
        if str(submodel['id']).startswith(BASE + '/'):
            urllib.request.urlopen(urllib.request.Request(
                AAS_URL + '/submodels/' + b64(submodel['id']), method='DELETE'),
                timeout=60)
            removed += 1
    print('  Removed beforehand: %d shells, %d submodels' % (len(existing), removed))

    for name in packages:
        result = subprocess.run(
            ['curl', '-s', '-m', '300', '-X', 'POST', AAS_URL + '/upload',
             '-F', 'file=@' + os.path.join(directory, name), '-o', os.devnull,
             '-w', '%{http_code}'], capture_output=True, text=True)
        if result.stdout.strip() != '200':
            give_up('Import of %s failed: HTTP %s. A package that the server '
                    'rejects can usually be repaired with repair_aasx.py.'
                    % (name, result.stdout))
    shells = fetch('/shells').get('result') or []
    print('  Imported: %d shells from %d packages' % (len(shells), len(packages)))
    if not shells:
        give_up('No shell arrived on the server.')


def step_fix():
    heading(2, 'Remove specification violations')
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, 'fix_aas_violations.py'), '--apply'],
        capture_output=True, text=True, env=dict(os.environ, SDI_AAS_URL=AAS_URL))
    for line in result.stdout.split('\n'):
        if line.startswith('total') or line.startswith('Done') \
                or line.startswith('Nothing'):
            print('  %s' % line)
    if result.returncode != 0:
        give_up('The correction failed: %s' % result.stderr.strip()[:200])


def step_erp():
    heading(3, 'ERP: bill of material and order')
    print('  Flow started: HTTP %s' % trigger('erp'))
    ok = wait_for(
        lambda: len((child(data_source(PRODUCT, 'ERP'), 'BillOfMaterial')
                     or {}).get('value') or []) > 0,
        180, 'the bill of material')
    if not ok:
        give_up('The bill of material did not arrive in the shell. '
                'Check the ERP credentials in .env.')
    erp = data_source(PRODUCT, 'ERP')
    positions = (child(erp, 'BillOfMaterial') or {}).get('value') or []
    order = child(erp, 'ManufacturingOrder')
    print('  Bill of material: %d positions%s' % (
        len(positions),
        ' | order %s over %s pieces' % (value_of(order, 'OrderNumber'),
                                        value_of(order, 'OrderQuantity'))
        if order else ''))


def step_simulation():
    heading(4, 'Simulation: assembly energy')
    print('  Flow started: HTTP %s' % trigger('simulation'))
    ok = wait_for(
        lambda: len((child(data_source(PRODUCT, 'Simulation'), 'SimulationProcesses')
                     or {}).get('value') or []) > 0,
        180, 'the simulation operations')
    if not ok:
        give_up('No operations arrived. Check SDI_EMA_EXPORT in .env.')
    operations = (child(data_source(PRODUCT, 'Simulation'), 'SimulationProcesses')
                  or {}).get('value') or []
    total = sum(float(value_of(o, 'EnergyPerUnit') or 0) for o in operations)
    print('  Simulation: %d operations, %.4f MJ in total' % (len(operations), total))


def step_machines(parts):
    heading(5, 'Machine data: measured production energy')
    print('  Flow started: HTTP %s' % trigger('machines'))
    time.sleep(20)
    written = []
    for part in parts:
        machine = data_source(part, 'MachineData')
        processes = (child(machine, 'ManufacturingProcesses') or {}).get('value') or []
        for process in processes:
            written.append('  %s: %s = %s MJ' % (
                part, process.get('idShort'), value_of(process, 'EnergyPerUnit')))
    if written:
        print('\n'.join(written))
    else:
        print('  No measurements present - the step is skipped without effect.')
        print('  This is the normal case as long as no machine is connected.')


def step_calculate(parts):
    heading(6, 'Calculation in openLCA')
    print('  Chain started: HTTP %s' % trigger('calculate'))

    def result_of(shell):
        """Returns the iterations that actually hold a calculated result.

        A freshly imported shell already carries a template iteration from the
        base shell. Counting it as a result would end the wait before anything
        was calculated, and the table would show nothing but zeros. Only an
        iteration with impact categories counts.
        """
        submodel = fetch('/submodels/' + b64('%s/%s/ILCD' % (BASE, shell)))
        container = (submodel.get('submodelElements') or [{}])[0]
        calculated = []
        for iteration in container.get('value') or []:
            methods = child(iteration, 'LCIAMethods')
            if any((m.get('value') or []) for m in (methods or {}).get('value') or []):
                calculated.append(iteration)
        return calculated

    # Wait for all shells: the shares of the parts are written after the
    # overall result, and reading too early mistakes them for missing.
    ok = wait_for(lambda: all(result_of(s) for s in [PRODUCT] + parts),
                  600, 'results in every shell')

    print()
    print('  %-24s %-42s %s' % ('Shell', 'Data sources', 'Climate change'))
    print('  ' + '-' * 80)
    total_parts = 0.0
    product_value = 0.0
    for shell in [PRODUCT] + parts:
        iterations = result_of(shell)
        if not iterations:
            print('  %-24s %s' % (shell, 'no result'))
            continue
        last = iterations[-1]
        sources = value_of(last, 'DataSource') or ''
        methods = child(last, 'LCIAMethods')
        climate = None
        # The exact category, not merely one starting with "Climate": the
        # method also carries Climate_change_Biogenic and _Land_use, both zero
        # here. Matching loosely would report the last of them and make a
        # correct result look empty.
        for method in (methods or {}).get('value') or []:
            for category in method.get('value') or []:
                if category.get('idShort') == 'Climate_change':
                    climate = float(value_of(category, 'Value') or 0)
        print('  %-24s %-42s %12.6f' % (shell, sources[:42], climate or 0))
        if shell == PRODUCT:
            product_value = climate or 0
        else:
            total_parts += climate or 0
    print('  ' + '-' * 80)
    print('  %-67s %12.6f' % ('Sum of the parts', total_parts))
    print('  %-67s %12.6f' % ('Product', product_value))
    print('  %-67s %12.6f  (assembly energy)'
          % ('Difference', product_value - total_parts))
    if not ok:
        give_up('Not every shell received a result. Is the openLCA IPC server '
                'running, and does SDI_OPENLCA_PRODUCT_SYSTEM match?')


def step_export(target):
    heading(7, 'Export and check')
    result = subprocess.run(
        [sys.executable, os.path.join(HERE, 'export_aasx.py'), target, '--split'],
        capture_output=True, text=True, env=dict(os.environ, SDI_AAS_URL=AAS_URL))
    if result.returncode != 0:
        give_up('The export failed: %s' % result.stderr.strip()[:200])
    for line in result.stdout.split('\n'):
        if '.aasx' in line:
            print('  %s' % line.strip())

    check = subprocess.run(
        [sys.executable, os.path.join(HERE, 'check_aasx.py'), '--directory', target],
        capture_output=True, text=True)
    readable = check.stdout.count('can be opened')
    rejected = check.stdout.count('is rejected')
    defective = check.stdout.count('defects that do not prevent opening')
    print('  %d packages readable, %d rejected, %d with defects'
          % (readable, rejected, defective))
    if rejected:
        give_up('Not every package can be opened. Run check_aasx.py for details.')


def main():
    parser = argparse.ArgumentParser(
        description='Run the whole processing chain and check every step.')
    parser.add_argument('--from', dest='start', type=int, default=1,
                        help='start at this step (1-7)')
    parser.add_argument('--skip', action='append', default=[],
                        choices=['import', 'fix', 'erp', 'simulation',
                                 'machines', 'calculate', 'export'],
                        help='leave a step out, may be given several times')
    parser.add_argument('--import-dir',
                        default=os.path.join(HERE, '..', 'docs', 'sample_data',
                                             'AASX', 'TRACEpen_Kugelschreiber'),
                        help='directory holding the AASX packages to import')
    parser.add_argument('--export-dir', default='export',
                        help='directory the finished packages are written to')
    parser.add_argument('--parts', default='Bolzen_Aluminium,Huelse_Aluminium,'
                                           'Stiftspitze_Helix_PLA,Mine,'
                                           'Schraube_M4,Druckfeder',
                        help='short names of the part shells, comma separated')
    args = parser.parse_args()
    parts = [p.strip() for p in args.parts.split(',') if p.strip()]

    print('Processing chain')
    print('  AAS server : %s' % AAS_URL)
    print('  Node-RED   : %s' % NODERED_URL)
    print('  Product    : %s' % PRODUCT)

    began = time.time()
    steps = [
        ('import', lambda: step_import(args.import_dir)),
        ('fix', step_fix),
        ('erp', step_erp),
        ('simulation', step_simulation),
        ('machines', lambda: step_machines(parts)),
        ('calculate', lambda: step_calculate(parts)),
        ('export', lambda: step_export(args.export_dir)),
    ]
    for number, (name, run) in enumerate(steps, start=1):
        if number < args.start or name in args.skip:
            continue
        run()

    print()
    print('=' * 74)
    print('Run complete, %d seconds.' % (time.time() - began))
    print('=' * 74)


if __name__ == '__main__':
    main()
