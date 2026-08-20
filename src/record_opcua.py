"""Records manufacturing operations from an OPC UA server and writes them to the AAS.

The OPC UA server of a shop floor usually provides instantaneous power only.
The flow OPCUA_Manufacturing.json of this KIT needs evaluated operations
instead: average power, process duration and piece count. This script closes
the gap between the two.

Per machine:

  1. read the power once a second
  2. when it rises above the threshold, an operation begins
  3. when it stays below for a set time, the operation ends
  4. energy is summed over the whole operation, low values included
  5. the result is written as submodel SAL-OPC-UA-Daten

Two settings decide whether a measurement is usable, and both must come from
the machine, not from a guess:

  threshold   must sit above the idle power. A 3D printer idles at some tens
              of watts and works at hundreds; the gap is wide. A lathe idles
              at about 290 W and cuts at 600 to 800 W with peaks above
              2000 W - a threshold of 1000 W would catch the peaks only and
              miss most of the work. Use --baseload and --raw to find it.
  cooldown    how long the power may stay below the threshold without ending
              the operation. A printer heats in cycles and needs minutes; a
              machine tool needs about a minute to bridge a tool change.

Usage:

    python record_opcua.py --baseload 60
        measures 60 seconds and proposes thresholds

    python record_opcua.py --watch
        shows the live values, writes nothing

    python record_opcua.py --record
        records until every operation has ended, then writes to the AAS.
        The piece count per machine comes from PIECES below; override it
        with --pieces Drucker3D=40 or a bare --pieces 5 for all machines

    python record_opcua.py --record --threshold Drehprozess=400 --raw curve.csv
        records with an adjusted threshold and keeps the power curve

Only one client at a time: the OPC UA server accepts a single session, and a
second program running alongside terminates the recording. That is why the raw
values are written from within this same session.

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
import asyncio
import base64
import datetime
import json
import os
import sys
import urllib.request

# "--help" muss ohne das Fremdpaket funktionieren.
#
# Die Pruefung "jedes Programm beantwortet --help" laeuft auf einem
# Rechner, auf dem nichts installiert ist - und genau das ist ihr Zweck.
# Ein Programm, das dort nicht einmal sagen kann, wozu es da ist, hilft
# niemandem, der das Repository gerade geklont hat.
if __name__ == '__main__' and set(sys.argv[1:]) & {'--help', '-h', '/?'}:
    print(__doc__.strip())
    sys.exit(0)

try:
    from asyncua import Client
except ImportError:
    print('The OPC UA library is missing. Install it with:')
    print('    pip install asyncua')
    sys.exit(2)

OPCUA_URL = os.environ.get('SDI_OPCUA_URL', 'opc.tcp://localhost:4840')
AAS_URL = os.environ.get('SDI_AAS_URL', 'http://localhost:8081')
SUBMODEL_ID = os.environ.get('SDI_OPCUA_SUBMODEL_ID',
                             'localhost/demo/SubmodelTemplate/SAL-OPC-UA-Daten')

# The name on the left is the one the flow knows the machine by and assigns to
# a part - it must match the assignment in the configuration node of
# OPCUA_Manufacturing.json. The node id is the address of the power value on
# the OPC UA server.
MACHINES = {
    'Drucker3D':    {'node': 'ns=2;i=2', 'source': 'Leistung_Drucker'},
    'Fraesprozess': {'node': 'ns=2;i=5', 'source': 'Leistung_Fraese'},
    'Drehprozess':  {'node': 'ns=2;i=6', 'source': 'Leistung_Drehmasch'},
}

# Defaults of the reference installation, determined with --baseload and
# verified against a recorded power curve.
# Thresholds of the reference installation, taken from measured power
# curves rather than from experience:
#
#   printer   idles at some tens of watts, prints at 150 to 1700 W
#   lathe     idles at 290 W, cuts at 600 to 800 W with peaks above 2000
#   mill      switched on 670 W, ready with the stepper running about
#             2500 W, machining 2900 to 3200 W over 48 recorded parts
#
# The mill is the difficult one: only about 20 percent separate its
# ready state from its machining, so its threshold has to be measured
# for the installation rather than assumed.
THRESHOLD = {'Drucker3D': 300.0, 'Fraesprozess': 650.0, 'Drehprozess': 400.0}
COOLDOWN = {'Drucker3D': 300, 'Fraesprozess': 60, 'Drehprozess': 60}
COOLDOWN_DEFAULT = 60

# How many parts one run of a machine produces. A print job holds the
# whole batch on the build plate, a machine tool makes one part per run.
# The number cannot be derived from the power values, so it is stated
# here and can be overridden per machine on the command line.
PIECES = {'Drucker3D': 25, 'Fraesprozess': 1, 'Drehprozess': 1}
PIECES_DEFAULT = 1

# Shortest operation that counts as manufacturing. Machines produce brief
# spikes while idling - a spindle starting, a pump switching on - and one
# of them can exceed the threshold for a second or two. Counted as an
# operation it would end up in the footprint of a part that was never
# made. Nothing real is lost: no part is machined in ten seconds.
MIN_DURATION_S = 10


def now():
    return datetime.datetime.now(datetime.timezone.utc)


def stamp(moment):
    return moment.strftime('%Y-%m-%dT%H:%M:%SZ')


class Recording:
    """Holds the state of one machine during an operation."""

    def __init__(self, name, threshold):
        self.name = name
        self.threshold = threshold
        self.running = False
        self.values = []
        self.start = None
        self.end = None
        self.below_since = None
        self.result = None
        # Result of an earlier operation of the same machine, merged into the
        # next one
        self.earlier = None

    def sample(self, power, moment):
        if not self.running:
            if power > self.threshold:
                self.running = True
                self.start = moment
                self.values = [power]
                self.below_since = None
                print('   %-14s operation begins at %.0f W' % (self.name, power))
            return

        self.values.append(power)
        if power > self.threshold:
            self.below_since = None
            return

        # Below the threshold: wait out the cooldown before ending
        if self.below_since is None:
            self.below_since = moment
        elif (moment - self.below_since).total_seconds() >= \
                COOLDOWN.get(self.name, COOLDOWN_DEFAULT):
            self.finish(self.below_since)

    def finish(self, end):
        # Energy is summed over every sample of the operation, the low ones
        # included. A printer draws power between two heating cycles, a lathe
        # between two cuts; that time belongs to the part. Taking the mean of
        # the high samples and multiplying by the total duration would
        # overstate the energy considerably.
        if not self.values:
            self.running = False
            return
        # Count only up to the beginning of the cooldown, not beyond
        count = len(self.values)
        if self.below_since is not None:
            spare = int((end - self.below_since).total_seconds())
            count = max(1, count - max(0, spare))
        counted = self.values[:count]
        self.end = end
        duration = max((self.end - self.start).total_seconds(), 1.0)
        # Watt times second gives joule. The factor duration over count
        # compensates for gaps: where samples are missing because the
        # connection dropped, the average power of the operation is assumed.
        energy_ws = sum(counted) * (duration / len(counted))
        above = [v for v in counted if v > self.threshold]
        self.result = {
            'average_power': energy_ws / duration,
            'energy_ws': energy_ws,
            'duration_s': duration,
            'start': self.start,
            'end': self.end,
            'samples': len(counted),
            'peak': max(counted),
            'peaks_above': len(above),
        }
        if duration < MIN_DURATION_S:
            print('   %-14s brief spike of %.0f s ignored (peak %.0f W)'
                  % (self.name, duration, self.result['peak']))
            self.result = self.earlier
            self.running = False
            return

        # Several operations of the same machine belong together: a machine
        # tool may produce one order in several bursts, and a recording can be
        # split by a dropped connection. Keeping only the last would silently
        # discard the rest - the result would be too low without anyone
        # noticing.
        if self.earlier is not None:
            previous = self.earlier
            self.result['energy_ws'] += previous['energy_ws']
            self.result['duration_s'] += previous['duration_s']
            self.result['start'] = min(self.result['start'], previous['start'])
            self.result['samples'] += previous['samples']
            self.result['peak'] = max(self.result['peak'], previous['peak'])
            self.result['peaks_above'] += previous['peaks_above']
            self.result['segments'] = previous.get('segments', 1) + 1
            self.result['average_power'] = (self.result['energy_ws']
                                            / self.result['duration_s'])
        self.earlier = self.result

        self.running = False
        print('   %-14s operation ends: %.0f Ws over %.0f s '
              '(average %.0f W, peak %.0f W)'
              % (self.name, self.result['energy_ws'], self.result['duration_s'],
                 self.result['average_power'], self.result['peak']))


def prop(id_short, value, value_type='xs:string'):
    return {'modelType': 'Property', 'idShort': id_short,
            'valueType': value_type, 'value': str(value)}


def machine_entry(name, result, pieces, source):
    return {'modelType': 'SubmodelElementCollection', 'idShort': name, 'value': [
        prop('LowThreshold', THRESHOLD[name], 'xs:double'),
        prop('HighThreshold', round(result['peak'], 1), 'xs:double'),
        prop('AveragePower', round(result['average_power'], 2), 'xs:double'),
        prop('AveragePowerUnit', 'W'),
        prop('ProcessDuration', round(result['duration_s'], 1), 'xs:double'),
        prop('ProcessDurationUnit', 's'),
        prop('TimeManufacturingStart', stamp(result['start']), 'xs:dateTime'),
        prop('TimeManufacturingEnd', stamp(result['end']), 'xs:dateTime'),
        prop('PieceCount', pieces, 'xs:double'),
        prop('ServerIP', OPCUA_URL),
        prop('SourceNode', source),
        prop('SampleCount', result['samples'], 'xs:double'),
    ]}


def existing_entries():
    """Reads the machine entries already present in the submodel.

    Needed for --keep: measurements of machines not recorded in this run then
    survive. Without the option a recording replaces the whole set - correct
    when all machines of one order are recorded together, wrong when they are
    measured one after another.
    """
    key = base64.urlsafe_b64encode(SUBMODEL_ID.encode()).decode().rstrip('=')
    try:
        request = urllib.request.Request(
            '%s/submodels/%s' % (AAS_URL, key),
            headers={'Accept': 'application/json'})
        with urllib.request.urlopen(request, timeout=30) as response:
            present = json.loads(response.read())
    except Exception:
        return []
    for element in present.get('submodelElements') or []:
        if element.get('idShort') == 'ManufacturingProcesses':
            return element.get('value') or []
    return []


def write_to_aas(entries, keep=False):
    if keep:
        recorded = {e.get('idShort') for e in entries}
        kept = [e for e in existing_entries() if e.get('idShort') not in recorded]
        if kept:
            print('   Kept from earlier recordings: %s'
                  % ', '.join(sorted(e.get('idShort') for e in kept)))
        entries = entries + kept
    submodel = {
        'modelType': 'Submodel',
        'id': SUBMODEL_ID,
        'idShort': 'SAL_OPC_UA_Daten',
        'kind': 'Instance',
        'submodelElements': [{
            # The entries carry names - one per machine. Named things belong
            # in a collection; children of a list must not carry a short name
            # according to AASd-120.
            'modelType': 'SubmodelElementCollection',
            'idShort': 'ManufacturingProcesses',
            'value': entries,
        }],
    }
    key = base64.urlsafe_b64encode(SUBMODEL_ID.encode()).decode().rstrip('=')
    body = json.dumps(submodel).encode()

    # Try to replace first, create otherwise
    for method, address in (('PUT', '%s/submodels/%s' % (AAS_URL, key)),
                            ('POST', '%s/submodels' % AAS_URL)):
        request = urllib.request.Request(
            address, data=body, method=method,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return method, response.status
        except urllib.error.HTTPError as error:
            if method == 'POST':
                return method, error.code
        except Exception as error:
            return method, str(error)
    return None, None


async def baseload(seconds):
    print('Measuring %d seconds of idle power ...' % seconds)
    async with Client(url=OPCUA_URL, timeout=15) as client:
        nodes = {n: client.get_node(d['node']) for n, d in MACHINES.items()}
        values = {n: [] for n in nodes}
        for _ in range(seconds):
            for name, node in nodes.items():
                values[name].append(float(await node.read_value()))
            await asyncio.sleep(1)
    print()
    print('%-14s %8s %8s %8s   proposed threshold'
          % ('machine', 'min', 'max', 'mean'))
    for name, series in values.items():
        proposal = max(50.0, round(max(series) * 1.3, -1))
        print('%-14s %8.0f %8.0f %8.1f   %.0f W'
              % (name, min(series), max(series),
                 sum(series) / len(series), proposal))
    print()
    print('Note: if a machine runs during the measurement, the proposal is'
          ' too high.')


async def watch():
    async with Client(url=OPCUA_URL, timeout=15) as client:
        nodes = {n: client.get_node(d['node']) for n, d in MACHINES.items()}
        print('%-9s %12s %12s %12s' % ('time', *nodes))
        while True:
            row = [float(await node.read_value()) for node in nodes.values()]
            marks = ['*' if value > THRESHOLD[name] else ' '
                     for name, value in zip(nodes, row)]
            print('%-9s %11.0f%s %11.0f%s %11.0f%s'
                  % (datetime.datetime.now().strftime('%H:%M:%S'),
                     row[0], marks[0], row[1], marks[1], row[2], marks[2]))
            await asyncio.sleep(1)


async def measure_loop(state, began, max_seconds, raw=None):
    """Reads the values once a second. Returns True when everything is done.

    The raw values are written from within this same session on request. A
    second program alongside would not work: the OPC UA server accepts only
    one client, and a second one ends the running recording.
    """
    async with Client(url=OPCUA_URL, timeout=15) as client:
        nodes = {n: client.get_node(d['node']) for n, d in MACHINES.items()}
        table = None
        if raw:
            fresh = not os.path.exists(raw)
            table = open(raw, 'a', encoding='utf-8')
            if fresh:
                table.write('time;' + ';'.join(MACHINES) + chr(10))
        while (now() - began).total_seconds() < max_seconds:
            moment = now()
            read = {}
            for name, node in nodes.items():
                value = float(await node.read_value())
                read[name] = value
                state[name].sample(value, moment)
            if table:
                table.write('%s;%s' % (
                    moment.strftime('%H:%M:%S'),
                    ';'.join('%.1f' % read[n] for n in MACHINES)) + chr(10))
                table.flush()
            started = [s for s in state.values() if s.result or s.running]
            if started and all(s.result for s in started):
                return True
            await asyncio.sleep(1)
    return False


async def record(max_seconds, dry_run=False, keep=False, raw=None):
    state = {n: Recording(n, THRESHOLD[n]) for n in MACHINES}
    print('Recording. Thresholds: %s'
          % ', '.join('%s %.0f W' % (n, t) for n, t in THRESHOLD.items()))
    print('Cooldown per machine: %s'
          % ', '.join('%s %d s' % (n, t) for n, t in COOLDOWN.items()))
    print('Pieces per run: %s'
          % ', '.join('%s %d' % (n, c) for n, c in PIECES.items()))
    print('Maximum duration %d s.' % max_seconds)
    print()

    began = now()
    done = False
    drops = 0
    # A recording runs for hours. If the connection breaks, it is rebuilt and
    # measuring continues - the history survives because the state is kept
    # outside the connection.
    while not done and (now() - began).total_seconds() < max_seconds:
        try:
            done = await measure_loop(state, began, max_seconds, raw)
        except Exception as error:
            drops += 1
            print('   connection lost (%s), attempt %d - reconnecting in 5 s'
                  % (type(error).__name__, drops))
            if drops > 60:
                print('   too many drops, recording is ended.')
                break
            await asyncio.sleep(5)

    for recording in state.values():
        if recording.running:
            print('   %-14s still running, closed at the end of the measurement'
                  % recording.name)
            recording.finish(now())

    if drops:
        print()
        print('Note: %d connection drops. Samples are missing for that time;'
              ' the average power of the operation is assumed for it.' % drops)

    entries = []
    print()
    print('Result:')
    for name, recording in state.items():
        if not recording.result:
            print('   %-14s no operation detected' % name)
            continue
        result = recording.result
        pieces = PIECES.get(name, PIECES_DEFAULT)
        energy = result['energy_ws'] / 1e6 / pieces
        print('   %-14s %.0f Ws over %.0f s / %d pieces = %.6f MJ per piece'
              % (name, result['energy_ws'], result['duration_s'], pieces, energy))
        print('   %-14s   average %.0f W, peak %.0f W, %d samples above threshold'
              % ('', result['average_power'], result['peak'],
                 result.get('peaks_above', 0)))
        entries.append(machine_entry(name, result, pieces,
                                     MACHINES[name]['source']))

    if not entries:
        print()
        print('Nothing recorded, nothing is written.')
        return 1

    if dry_run:
        print()
        print('Dry run: measured and calculated, nothing written to the AAS.')
        return 0

    method, status = write_to_aas(entries, keep)
    print()
    print('Submodel written: %s -> HTTP %s' % (method, status))
    return 0


async def mark(machine, pieces, aas_name, keep, raw):
    """Measures one operation whose start and end the operator marks.

    Some machines cannot be recognised from their power at all. A milling
    machine that draws 3076 W ready and 3102 W while cutting differs by less
    than its own fluctuation - no threshold can separate the two. What such a
    machine does offer is a very steady power, and that makes the simple way
    the accurate one: the operator states when the operation begins and ends,
    the script measures the power in between.

    The reading includes the ready power during the operation. That is the
    usual convention for machine time: the machine runs for this part, so its
    base load belongs to it.
    """
    if machine not in MACHINES:
        print('Unknown machine: %s. Known: %s' % (machine, ', '.join(MACHINES)))
        return 2

    print('Machine     %s' % machine)
    print('Written as  %s' % (aas_name or machine))
    print('Pieces      %d' % pieces)
    print()
    input('Press Enter when the operation STARTS ... ')
    begin = now()
    values, table = [], None
    if raw:
        fresh = not os.path.exists(raw)
        table = open(raw, 'a', encoding='utf-8')
        if fresh:
            table.write('Zeit;' + machine + chr(10))

    stop = asyncio.Event()

    async def wait_for_enter():
        await asyncio.get_running_loop().run_in_executor(
            None, input, 'Press Enter when the operation ENDS ... ')
        stop.set()

    asyncio.ensure_future(wait_for_enter())
    async with Client(url=OPCUA_URL, timeout=15) as client:
        node = client.get_node(MACHINES[machine]['node'])
        while not stop.is_set():
            try:
                value = float(await node.read_value())
                values.append(value)
                if table:
                    table.write('%s;%.1f%s' % (now().strftime('%H:%M:%S'),
                                               value, chr(10)))
                    table.flush()
            except Exception as error:
                print('   reading failed (%s)' % type(error).__name__)
            await asyncio.sleep(1)
    end = now()

    if not values:
        print('No readings taken, nothing is written.')
        return 1

    duration = max((end - begin).total_seconds(), 1.0)
    # Sum of the readings, not mean times duration: gaps then carry the
    # average of the operation instead of nothing.
    energy = sum(values) * (duration / len(values))
    print()
    print('  Duration          %.0f s   (%d readings, %.0f %% coverage)'
          % (duration, len(values), 100.0 * len(values) / duration))
    print('  Average power     %.0f W   (min %.0f, max %.0f)'
          % (energy / duration, min(values), max(values)))
    print('  Energy            %.0f Ws = %.4f MJ per piece'
          % (energy, energy / 1e6 / pieces))
    if len(values) < 0.9 * duration:
        print()
        print('  More than a tenth of the readings are missing. Check the'
              ' connection before using this measurement.')

    result = {
        'average_power': energy / duration, 'energy_ws': energy,
        'duration_s': duration, 'start': begin, 'end': end,
        'samples': len(values), 'peak': max(values),
        'peaks_above': 0,
    }
    entry = machine_entry(aas_name or machine, result, pieces,
                          MACHINES[machine]['source'])
    entry['value'].append({
        'modelType': 'Property', 'idShort': 'Comment', 'valueType': 'xs:string',
        'value': 'Duration marked by the operator: ready state and machining '
                 'cannot be told apart from the power of this machine. The '
                 'ready power during the operation is included.'})
    method, status = write_to_aas([entry], keep)
    print()
    print('Submodel written: %s -> HTTP %s' % (method, status))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description='Record manufacturing operations from an OPC UA server.')
    parser.add_argument('--baseload', type=int, metavar='SECONDS',
                        help='measure the idle power and propose thresholds')
    parser.add_argument('--watch', action='store_true',
                        help='show the live values, write nothing')
    parser.add_argument('--record', action='store_true',
                        help='record operations and write them to the AAS')
    parser.add_argument('--pieces', action='append', metavar='[NAME=]COUNT',
                        help='pieces produced in this run. A bare number '
                             'applies to every machine, NAME=COUNT to one of '
                             'them. Defaults: '
                             + ', '.join('%s %d' % (n, c)
                                         for n, c in PIECES.items()))
    parser.add_argument('--dry-run', action='store_true',
                        help='measure only, write nothing to the AAS')
    parser.add_argument('--max-seconds', type=int, default=3600,
                        help='stop the recording after this time')
    parser.add_argument('--raw', metavar='FILE',
                        help='also write every sample to a table, for '
                             'determining the thresholds')
    parser.add_argument('--keep', action='store_true',
                        help='keep measurements of machines not recorded now')
    parser.add_argument('--mark', metavar='MACHINE',
                        help='measure one operation of this machine, start and '
                             'end marked with Enter. For machines whose '
                             'machining cannot be told from their idle power')
    parser.add_argument('--as-name', metavar='NAME',
                        help='short name the measurement is stored under, for '
                             'a machine that makes more than one part, e.g. '
                             'Drehprozess_Huelse')
    parser.add_argument('--threshold', action='append', metavar='NAME=WATT',
                        help='override the threshold of one machine')
    args = parser.parse_args()

    for entry in (args.pieces or []):
        name, sign, count = entry.partition('=')
        if not sign:
            for machine in PIECES:
                PIECES[machine] = int(name)
        elif name in PIECES:
            PIECES[name] = int(count)
        else:
            print('Unknown machine: %s. Known: %s' % (name, ', '.join(MACHINES)))
            return 2

    for entry in (args.threshold or []):
        name, _, value = entry.partition('=')
        if name in THRESHOLD:
            THRESHOLD[name] = float(value)
        else:
            print('Unknown machine: %s. Known: %s' % (name, ', '.join(MACHINES)))
            return 2

    if args.baseload:
        asyncio.run(baseload(args.baseload))
    elif args.watch:
        asyncio.run(watch())
    elif args.mark:
        counts = [int(e.split('=')[-1]) for e in (args.pieces or [])]
        sys.exit(asyncio.run(mark(args.mark, counts[0] if counts else
                                  PIECES.get(args.mark, PIECES_DEFAULT),
                                  args.as_name, args.keep, args.raw)))
    elif args.record:
        sys.exit(asyncio.run(record(args.max_seconds, args.dry_run,
                                    args.keep, args.raw)))
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
