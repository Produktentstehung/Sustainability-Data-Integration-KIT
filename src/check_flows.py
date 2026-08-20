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
"""Checks the Node-RED flow files before they are imported.

Usage:  python src/check_flows.py [directory]

Reads every .json in the directory (src by default) and reports what would
break on import or at runtime. Exit code 1 means at least one finding.

Four things are checked, each of which has actually gone wrong here:

    Valid JSON              a truncated file imports as nothing at all
    Unique identifiers      two nodes with the same id overwrite each other
    No dangling references  Node-RED refuses the whole import for one of these
    Function syntax         a broken function fails silently at runtime; the
                            flow simply stops writing, with no error in sight

The function check needs Node.js. Without it that part is skipped and said so
rather than passed over in silence.
"""
import collections
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

# Fields that point at another node by its identifier.
VERWEISE = ('group', 'ui', 'page', 'theme', 'z')

# Node types that start a message on their own. Everything else has to be
# reached from somewhere, or it will never run.
#
# This check exists because of a real defect: an old dashboard widget was
# removed from the calculation flow, and it turned out not to be the end of a
# chain but a station in the middle of one. The flow kept running, the part
# results were still written, and the result of the product silently stayed at
# the previous day's value. Nothing reported an error - the branch simply had
# no way in any more.
EINSTIEGE = {
    'inject', 'http in', 'mqtt in', 'websocket in', 'tcp in', 'udp in',
    'serial in', 'watch', 'catch', 'status', 'link in', 'file in', 'cron-plus',
    'ui-button', 'ui-dropdown', 'ui-switch', 'ui-slider', 'ui-text-input',
    'ui-form', 'ui-template', 'ui-control', 'ui-event', 'ui_button',
    'ui_dropdown', 'ui_switch', 'ui_text_input', 'ui_form',
}

# Types that are configuration rather than a step in a flow.
KEINE_KNOTEN = {
    'tab', 'subflow', 'comment', 'ui-base', 'ui-page', 'ui-group', 'ui-theme',
    'ui_base', 'ui_tab', 'ui_group', 'global-config', 'group',
}


def lade(pfad):
    with open(pfad, encoding='utf-8') as fh:
        return json.load(fh)


def pruefe_datei(pfad, node_da):
    """Returns a list of findings for one flow file."""
    funde = []
    try:
        knoten = lade(pfad)
    except Exception as exc:
        return ['not readable as JSON: %s' % exc]
    if not isinstance(knoten, list):
        return ['not a flow export: the top level is not a list']

    eigene = {n.get('id') for n in knoten if isinstance(n, dict)}

    doppelt = [k for k, z in collections.Counter(
        n.get('id') for n in knoten if isinstance(n, dict)).items() if z > 1]
    for k in doppelt:
        funde.append('identifier appears more than once: %s' % k)

    for n in knoten:
        if not isinstance(n, dict):
            funde.append('entry is not an object')
            continue
        name = n.get('name') or n.get('label') or n.get('id')
        for leitung in (n.get('wires') or []):
            for ziel in leitung:
                if ziel not in eigene:
                    funde.append('%s points at %s, which is not in this file'
                                 % (name, ziel))
        for feld in VERWEISE:
            wert = n.get(feld)
            if isinstance(wert, str) and wert and wert not in eigene:
                funde.append('%s refers to %s=%s, which is not in this file'
                             % (name, feld, wert))

    # Nodes no message can ever reach.
    #
    # Walking outward from the entry points rather than asking "does anything
    # point at this node": a chain of three dead nodes points at each other
    # perfectly well and still never runs. That is what an orphaned branch
    # looks like after a widget in the middle of it was deleted.
    dicts = [n for n in knoten if isinstance(n, dict)]
    ziele = {n['id']: [z for w in (n.get('wires') or []) for z in w]
             for n in dicts if n.get('id')}
    offen = [n['id'] for n in dicts
             if n.get('type') in EINSTIEGE and n.get('id')]
    erreichbar = set(offen)
    while offen:
        aktuell = offen.pop()
        for z in ziele.get(aktuell, []):
            if z not in erreichbar:
                erreichbar.add(z)
                offen.append(z)

    for n in dicts:
        typ = n.get('type')
        if typ in KEINE_KNOTEN or typ in EINSTIEGE:
            continue
        # A link-call target is addressed by name rather than by a wire.
        if typ in ('link out', 'link call'):
            continue
        if n.get('id') in erreichbar:
            continue
        funde.append('%s (%s) can never be reached from an entry point'
                     % (n.get('name') or n.get('id'), typ))

    if node_da:
        for n in knoten:
            if not isinstance(n, dict) or not n.get('func'):
                continue
            # Node-RED wraps the code in a function; a bare "return" outside
            # one would be a syntax error otherwise.
            huelle = ('async function __check(msg, node, flow, global, env, '
                      'context, RED) {\n%s\n}' % n['func'])
            with tempfile.NamedTemporaryFile('w', suffix='.js', delete=False,
                                             encoding='utf-8') as fh:
                fh.write(huelle)
                tmp = fh.name
            try:
                ergebnis = subprocess.run(['node', '--check', tmp],
                                          capture_output=True, text=True)
            finally:
                os.unlink(tmp)
            if ergebnis.returncode != 0:
                zeile = [z for z in ergebnis.stderr.splitlines()
                         if 'Error' in z]
                funde.append('function "%s" does not compile: %s'
                             % (n.get('name') or n.get('id'),
                                zeile[0].strip() if zeile else 'see node --check'))
    return funde


def main():
    ordner = sys.argv[1] if len(sys.argv) > 1 else 'src'
    if ordner in ('--help', '-h', '/?'):
        print(__doc__.strip())
        return 0

    dateien = sorted(glob.glob(os.path.join(ordner, '*.json')))
    if not dateien:
        print('No flow files in %s' % ordner)
        return 1

    node_da = shutil.which('node') is not None
    if not node_da:
        print('Node.js not found - the function check is skipped.\n')

    # Identifiers have to be unique across all files as well: the files are
    # imported into one Node-RED, and a collision there silently replaces a
    # node from another flow.
    ueberall = collections.defaultdict(list)
    gesamt = 0

    for pfad in dateien:
        funde = pruefe_datei(pfad, node_da)
        gesamt += len(funde)
        print('%-32s %s' % (os.path.basename(pfad),
                            'in order' if not funde else '%d findings' % len(funde)))
        for f in funde:
            print('    %s' % f)
        try:
            for n in lade(pfad):
                if isinstance(n, dict):
                    ueberall[n.get('id')].append(os.path.basename(pfad))
        except Exception:
            pass

    mehrfach = {k: v for k, v in ueberall.items() if len(set(v)) > 1}
    if mehrfach:
        print('\nIdentifiers used in more than one file:')
        for k, v in sorted(mehrfach.items()):
            print('    %s  %s' % (k, ', '.join(sorted(set(v)))))
        gesamt += len(mehrfach)

    print('\n%d files, %d findings' % (len(dateien), gesamt))
    return 1 if gesamt else 0


if __name__ == '__main__':
    sys.exit(main())
