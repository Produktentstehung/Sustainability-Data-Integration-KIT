"""Checks an AASX file the way the AASX Package Explorer does.

The Explorer builds on the reference implementation aas-core. The same library
is used here: first the XML is read, then the rules of the specification are
verified. What passes here, the Explorer opens; what fails here, it rejects
without giving a reason.

The package rules themselves are checked as well - relationship files, content
types - because an invalid package fails before the XML is ever reached.

Two outcomes are distinguished on purpose:

    "can be opened"   the file is readable; findings of the rule check are
                      defects, not obstacles
    "is rejected"     the package is broken or the XML cannot be read

Requires the reference library:  pip install aas-core3.0

Usage:
    python check_aasx.py <file.aasx> [more.aasx ...]
    python check_aasx.py --directory <directory>

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
import os
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

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
    import aas_core3.verification as verification
    import aas_core3.xmlization as xmlization
except ImportError:
    print('The reference library is missing. Install it with:')
    print('    pip install aas-core3.0')
    sys.exit(2)


def check_package(path):
    """Checks the structure of the package.

    Returns the XML data and the list of findings. The data is None when the
    package is broken beyond the point where the content could be reached.
    """
    findings = []
    try:
        archive = zipfile.ZipFile(path)
    except Exception as error:
        return None, ['not a valid ZIP archive: %s' % error]

    names = archive.namelist()
    if '[Content_Types].xml' not in names:
        findings.append('[Content_Types].xml is missing')
    if '_rels/.rels' not in names:
        findings.append('_rels/.rels is missing')

    # Every part needs a content type, either through its extension or
    # declared explicitly. A part without one makes the package invalid.
    if '[Content_Types].xml' in names:
        declared = archive.read('[Content_Types].xml').decode('utf-8', 'replace')
        extensions = {e.lower() for e in re.findall(r'Extension="([^"]+)"', declared)}
        explicit = {p.lstrip('/').lower() for p in re.findall(r'PartName="([^"]+)"', declared)}
        for name in names:
            if name.endswith('/'):
                continue
            # For names such as "_rels/.rels" splitext yields no extension,
            # so the part after the last dot is taken.
            base = os.path.basename(name)
            extension = base.rsplit('.', 1)[-1].lower() if '.' in base else ''
            if extension and extension in extensions:
                continue
            if name.lower() in explicit:
                continue
            findings.append('part without content type: %s' % name)

    # The path from the root through the origin to the data file
    data_file = None
    if '_rels/.rels' in names:
        rels = archive.read('_rels/.rels').decode('utf-8', 'replace')
        if 'aasx-origin' not in rels:
            findings.append('_rels/.rels does not point to the origin')
        target = re.search(r'Target="([^"]*aasx-origin)"', rels)
        origin = target.group(1).lstrip('/') if target else 'aasx/aasx-origin'
        if origin not in names:
            findings.append('origin file is missing: %s' % origin)
        rels_path = '%s/_rels/%s.rels' % (os.path.dirname(origin),
                                          os.path.basename(origin))
        if rels_path not in names:
            findings.append('relationship file of the origin is missing: %s' % rels_path)
        else:
            second = archive.read(rels_path).decode('utf-8', 'replace')
            match = re.search(r'Target="([^"]+)"', second)
            if not match:
                findings.append('the origin points to no data file')
            else:
                relative = match.group(1).lstrip('/')
                for candidate in (relative, os.path.dirname(origin) + '/' + relative):
                    if candidate in names:
                        data_file = candidate
                        break
                if not data_file:
                    findings.append('data file not found: %s' % relative)

    return (archive.read(data_file) if data_file else None), findings


def check_content(raw):
    """Reads the XML with the reference library and verifies the rules."""
    findings = []
    text = raw.decode('utf-8', 'replace')

    # aas-core reads the namespace 3/0. Older and newer versions are mapped
    # onto it for the check; that changes notation, not content.
    version = None
    root = ET.fromstring(text)
    if '}' in root.tag:
        version = root.tag.split('}')[0].lstrip('{')
    if version and version != 'https://admin-shell.io/aas/3/0':
        text = text.replace(version, 'https://admin-shell.io/aas/3/0')

    try:
        environment = xmlization.environment_from_str(text)
    except Exception as error:
        return None, ['XML cannot be read: %s' % str(error)[:300]], version

    for violation in verification.verify(environment):
        path = '/'.join(str(segment) for segment in violation.path.segments)
        findings.append('%s: %s' % (path or '(root)', violation.cause))
        if len(findings) >= 2000:
            findings.append('... further violations omitted')
            break
    return environment, findings, version


def check_file(path):
    print('=' * 78)
    print(os.path.basename(path))
    print('=' * 78)
    raw, package_findings = check_package(path)
    if package_findings:
        print('  Package structure: %d findings' % len(package_findings))
        for finding in package_findings[:12]:
            print('     %s' % finding)
    else:
        print('  Package structure: in order')

    if raw is None:
        print('  Content: cannot be checked, the data file is missing')
        return False

    environment, content_findings, version = check_content(raw)
    print('  Namespace: %s' % (version or 'none'))
    if environment is not None:
        print('  Read: %d shells, %d submodels'
              % (len(environment.asset_administration_shells or []),
                 len(environment.submodels or [])))
    if content_findings:
        print('  Content: %d findings' % len(content_findings))
        for finding in content_findings[:40]:
            print('     %s' % finding[:150])
    else:
        print('  Content: in order')

    # What matters is whether the file can be read at all. Findings of the
    # rule check are defects but no obstacle - the sample files shipped with
    # the specification have some as well and still open.
    readable = environment is not None and not package_findings
    print('\n  RESULT: %s' % ('can be opened' if readable else 'is rejected'))
    if readable and content_findings:
        print('  (with %d defects that do not prevent opening)' % len(content_findings))
    print()
    return readable


def main():
    parser = argparse.ArgumentParser(
        description='Check AASX packages for readability and conformity.')
    parser.add_argument('files', nargs='*', help='packages to check')
    parser.add_argument('--directory', help='check every .aasx in this directory')
    args = parser.parse_args()

    # Ein Ordner als einfaches Argument ist gemeint wie --directory. Ohne das
    # versucht das Programm, das Verzeichnis als Paket zu oeffnen, und meldet
    # einen Zugriffsfehler - eine Antwort, die niemandem sagt, was zu tun ist.
    files = []
    for eintrag in args.files:
        if os.path.isdir(eintrag):
            files += [os.path.join(eintrag, name)
                      for name in sorted(os.listdir(eintrag))
                      if name.lower().endswith('.aasx')]
        else:
            files.append(eintrag)
    if args.directory:
        files += [os.path.join(args.directory, name)
                  for name in sorted(os.listdir(args.directory))
                  if name.lower().endswith('.aasx')]
    if not files:
        parser.print_help()
        return 1

    all_readable = True
    for path in files:
        all_readable &= check_file(path)
    return 0 if all_readable else 1


if __name__ == '__main__':
    sys.exit(main())
