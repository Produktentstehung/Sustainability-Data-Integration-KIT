"""Exports the content of the AAS server as an AASX package.

The serialisation service of BaSyx returns an internal error for the AASX
format in the version used here, while XML and JSON work. This script
therefore fetches the XML environment and builds the package itself, following
the rules of the AASX format: a ZIP archive with relationship files, as the
AASX Package Explorer expects it.

Usage:
    python export_aasx.py <target directory>
    python export_aasx.py <target directory> --split

The server address is taken from SDI_AAS_URL, default http://localhost:8081.

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
import datetime
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
import urllib.parse
import urllib.request
import zipfile

AAS_URL = os.environ.get('SDI_AAS_URL', 'http://localhost:8081')
NAMESPACE = 'https://admin-shell.io/aas/3/1'
NS = '{%s}' % NAMESPACE


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def fetch(path, accept='application/json'):
    request = urllib.request.Request(AAS_URL + path, headers={'Accept': accept})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.read()


# The schema prescribes a fixed order for the child elements. BaSyx does not
# keep to it everywhere - displayName, for instance, ends up after
# submodelElements. That is well-formed but schema-invalid XML, and a
# validating reader such as the AASX Package Explorer rejects the file.
# The list holds the common header of all elements in the required order.
HEADER_ORDER = [
    'extensions', 'category', 'idShort', 'displayName', 'description',
    'administration', 'id', 'kind', 'semanticId', 'supplementalSemanticIds',
    'qualifiers', 'embeddedDataSpecifications',
]

# Elements that must have children according to the specification. BaSyx
# sometimes writes them out empty inside concept descriptions. A reader then
# does not merely complain, it stops before reaching the shells at all. Empty,
# they carry no information anyway.
MUST_NOT_BE_EMPTY = (
    'valueList', 'valueReferencePairs', 'keys', 'unit',
    'langStringPreferredNameTypeIec61360', 'langStringShortNameTypeIec61360',
    'langStringDefinitionTypeIec61360',
)


def sort_children(element):
    """Puts the children of an element into the order the schema requires.

    Only the header part is sorted; everything after it - submodelElements or
    value, for example - keeps its order, because there the order carries
    meaning.
    """
    children = list(element)
    if not children:
        return
    rank = {name: i for i, name in enumerate(HEADER_ORDER)}
    ordered = sorted(
        children,
        key=lambda c: rank.get(c.tag.replace(NS, ''), len(HEADER_ORDER)))
    if ordered != children:
        element[:] = ordered
    for child in element:
        sort_children(child)


def drop_empty_elements(element):
    """Removes elements that require children but have none."""
    for child in list(element):
        drop_empty_elements(child)
        name = child.tag.replace(NS, '')
        if name in MUST_NOT_BE_EMPTY and len(child) == 0 \
                and not (child.text or '').strip():
            element.remove(child)


def complete_lists(element):
    """Adds the mandatory type of a list where it is missing.

    A SubmodelElementList must state the type of its entries. Without it,
    reading the file fails. The type is derived from the first entry; for an
    empty list a collection is assumed.
    """
    for element_list in element.iter(NS + 'submodelElementList'):
        if element_list.find(NS + 'typeValueListElement') is not None:
            continue
        values = element_list.find(NS + 'value')
        kind = 'SubmodelElementCollection'
        if values is not None and len(values):
            first = values[0].tag.replace(NS, '')
            kind = first[0].upper() + first[1:]
        entry = ET.Element(NS + 'typeValueListElement')
        entry.text = kind
        # The entry belongs before the value field
        position = list(element_list).index(values) if values is not None \
            else len(element_list)
        element_list.insert(position, entry)


def tidy_file_references(element):
    """Brings references to attachments into a valid form.

    The AAS server manages uploaded attachments itself and returns their
    references in varying shapes - sometimes as a path inside its working
    directory, sometimes as an encoded submodel identifier with an element
    path appended. Outside the server neither is a valid address. What remains
    useful is the file name.
    """
    for entry in element.iter(NS + 'file'):
        value = entry.find(NS + 'value')
        if value is None or not (value.text or '').strip():
            continue
        address = value.text.strip()
        if address.startswith(('http://', 'https://', '/aasx/')):
            continue
        name = file_name(address)
        value.text = '/aasx/files/' + name if name else '/aasx/files/unnamed'


def normalise(xml):
    """Brings the serialisation into the form the Package Explorer reads.

    All changes concern notation only, never content:
      - the prefix "aas:" is dropped in favour of the default namespace
      - the version is set to 3/1, as in the Explorer's own packages
      - elements are put into the order required by the schema
      - empty mandatory elements are removed and missing list types added
    """
    text = xml.decode('utf-8')
    text = text.replace('<aas:', '<').replace('</aas:', '</')
    text = re.sub(r'<environment[^>]*>',
                  '<environment xmlns="%s">' % NAMESPACE, text, count=1)

    ET.register_namespace('', NAMESPACE)
    root = ET.fromstring(text)
    sort_children(root)
    drop_empty_elements(root)
    complete_lists(root)
    tidy_file_references(root)
    return ET.tostring(root, encoding='utf-8', xml_declaration=True)


# Content types for the attachments. Every file inside the package needs a
# declared type - a part without one makes the package invalid under rule
# M.1.14, and the Package Explorer then refuses the whole file.
ATTACHMENT_TYPES = {
    'png': 'image/png', 'jpg': 'image/jpeg', 'jpeg': 'image/jpeg',
    'gif': 'image/gif', 'svg': 'image/svg+xml', 'pdf': 'application/pdf',
    'csv': 'text/csv', 'txt': 'text/plain', 'json': 'application/json',
    'step': 'application/step', 'stp': 'application/step',
    'sldprt': 'application/octet-stream', 'sldasm': 'application/octet-stream',
    'appinfo': 'application/octet-stream',
}


def file_name(value):
    """Derives the file name from the reference the server stores.

    The server writes an identifier of three parts, separated by hyphens:
    the encoded submodel id, the path of the element, and the file name -
    for example

        bG9jYWx...SGFuZG92ZXJEb2M-Documents[1].DocumentVersions[0].DigitalFiles[0]-000053-1.SLDPRT

    Cutting at the last hyphen would split the file name itself, because
    "000053-1.SLDPRT" contains one. Everything from the third part onwards
    belongs to the name.
    """
    address = str(value or '').strip()
    if not address:
        return ''
    if address.startswith(('/aasx/', 'http://', 'https://')):
        return address.rsplit('/', 1)[-1]
    parts = address.split('-')
    if len(parts) > 2:
        return '-'.join(parts[2:])
    return parts[-1].rsplit('/', 1)[-1]


def element_paths(elements, prefix=''):
    """Yields (path, element) for every element, the way the server addresses it.

    Children of a list have no short name of their own - the specification
    forbids it - so they are addressed by their position. Collections and
    submodels use the short name. Getting this wrong is the difference between
    an attachment that downloads and a 404.
    """
    for index, element in enumerate(elements or []):
        name = element.get('idShort')
        step = name if name else '[%d]' % index
        path = (prefix + '.' + step) if (prefix and name) else (prefix + step)
        yield path, element
        if isinstance(element.get('value'), list):
            children = element['value']
            if element.get('modelType') == 'SubmodelElementList':
                for position, child in enumerate(children):
                    child_path = '%s[%d]' % (path, position)
                    yield child_path, child
                    if isinstance(child.get('value'), list):
                        for deeper in element_paths(child['value'], child_path):
                            yield deeper
            else:
                for deeper in element_paths(children, path):
                    yield deeper


def collect_attachments(submodels):
    """Downloads the files referenced by the shells.

    The AAS server keeps uploaded attachments itself and puts an internal
    identifier into the reference. That identifier means nothing outside the
    server, so the file itself has to travel with the package - otherwise the
    Package Explorer shows a reference that leads nowhere, and a CAD model
    that is present on the server looks missing to everyone who receives the
    file.
    """
    files = {}
    for submodel in submodels:
        key = b64(submodel['id'])
        for path, element in element_paths(submodel.get('submodelElements')):
            if element.get('modelType') not in ('File', 'Blob'):
                continue
            value = str(element.get('value') or '')
            if not value or value.startswith(('http://', 'https://')):
                continue
            name = file_name(value)
            if not name or name in files:
                continue
            address = '%s/submodels/%s/submodel-elements/%s/attachment' % (
                AAS_URL, key, urllib.parse.quote(path, safe='.'))
            try:
                request = urllib.request.Request(address)
                with urllib.request.urlopen(request, timeout=120) as response:
                    content = response.read()
            except Exception:
                continue
            if content:
                files[name] = content
    return files


def environment_xml(shells, submodels):
    query = urllib.parse.urlencode({
        'aasIds': ','.join(b64(s) for s in shells),
        'submodelIds': ','.join(b64(m) for m in submodels),
        'includeConceptDescriptions': 'true',
    })
    return normalise(fetch('/serialization?' + query, 'application/xml'))



def clean_before_writing(xml):
    """Removes the specification violations the server content still carries.

    The shells on the server were built from a template that violates the
    specification in a handful of places, and reading them back out reproduces
    every one of them. Without this the export was worse than the sample data
    shipped with the KIT: 114 violations per package against none - and it was
    the export, not the sample data, that a user looks at first.

    The same cleaning the PLM generator applies, so a package exported here and
    a package built there come out alike. If the module is missing the export
    still runs; a package with findings is worth more than no package.
    """
    try:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        from repair_aasx import clean_content
    except ImportError:
        print('  [WARN] repair_aasx.py not found next to this script - the '
              'package keeps the violations of the template it came from.')
        return xml
    # The serialiser hands over bytes here and text elsewhere. The cleaner
    # works on text, and the caller must get back what it gave.
    war_bytes = isinstance(xml, bytes)
    text = xml.decode('utf-8') if war_bytes else xml
    cleaned, count = clean_content(text)
    if count:
        print('  %d violations of the specification removed' % count)
    return cleaned.encode('utf-8') if war_bytes else cleaned


def write_package(target, xml, attachments=None):
    """Packs the environment as an AASX file.

    Structure as prescribed by the format: the relationship file in the root
    points to the origin, which in turn points to the file holding the data.

    Four details decide whether the Package Explorer finds the content:
      - the relationship type address contains "www."
      - the targets are relative, without a leading slash
      - the origin file is not empty but carries a note
      - and it needs an explicit content type: it has no file extension a
        default could apply to. Without that entry the package violates the
        OPC rules, and the Explorer aborts with an unhandled exception that
        does not name the cause.
    """
    content_types = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="xml" ContentType="text/xml" />\n'
        '  <Default Extension="rels" '
        'ContentType="application/vnd.openxmlformats-package.relationships+xml" />\n'
        '  <Override PartName="/aasx/aasx-origin" ContentType="text/plain" />\n'
        # Every attachment needs a declared content type as well. A part
        # without one makes the package invalid under rule M.1.14, and the
        # Package Explorer refuses the whole file without naming the cause.
        + ''.join(
            '  <Default Extension="%s" ContentType="%s" />\n'
            % (kind, ATTACHMENT_TYPES.get(kind, 'application/octet-stream'))
            for kind in sorted({name.rsplit('.', 1)[-1].lower()
                                for name in (attachments or {})
                                if '.' in name} - {'xml', 'rels'}))
        + '</Types>')
    root_rels = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Type="http://www.admin-shell.io/aasx/relationships/aasx-origin" '
        'Target="aasx/aasx-origin" Id="r1"/></Relationships>')
    origin_rels = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Type="http://www.admin-shell.io/aasx/relationships/aas-spec" '
        'Target="environment.aas.xml" Id="r1"/></Relationships>')

    xml = clean_before_writing(xml)

    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('[Content_Types].xml', content_types)
        archive.writestr('_rels/.rels', root_rels)
        archive.writestr('aasx/aasx-origin', 'Intentionally empty')
        archive.writestr('aasx/_rels/aasx-origin.rels', origin_rels)
        archive.writestr('aasx/environment.aas.xml', xml)
        for name, content in (attachments or {}).items():
            archive.writestr('aasx/files/' + name, content)
    return os.path.getsize(target)


def main():
    parser = argparse.ArgumentParser(
        description='Export the AAS server content as AASX packages.')
    parser.add_argument('target', help='directory the packages are written to')
    parser.add_argument('--split', action='store_true',
                        help='additionally write one package per shell')
    parser.add_argument('--name', default='complete',
                        help='file name of the combined package')
    parser.add_argument('--no-attachments', action='store_true',
                        help='leave CAD models, drawings and documents out - '
                             'the package stays small but its file references '
                             'lead nowhere')
    args = parser.parse_args()
    os.makedirs(args.target, exist_ok=True)
    # The full path, once, before anything else. The packages are written on
    # this machine, not downloaded through a browser, and "export" alone does
    # not tell anyone where to look for them.
    print('Writing to %s' % os.path.abspath(args.target))

    shells = json.loads(fetch('/shells'))['result']
    submodels = json.loads(fetch('/submodels?limit=500'))['result']
    print('%d shells, %d submodels on the server' % (len(shells), len(submodels)))

    attachments = {}
    if not args.no_attachments:
        attachments = collect_attachments(submodels)
        total = sum(len(c) for c in attachments.values())
        print('%d attachments, %.1f MB' % (len(attachments), total / 1024 / 1024))
        for name in sorted(attachments):
            print('   %9d B  %s' % (len(attachments[name]), name))

    xml = environment_xml([s['id'] for s in shells], [m['id'] for m in submodels])
    combined = os.path.join(args.target, args.name + '.aasx')
    size = write_package(combined, xml, attachments)
    print('\n%-32s %8.2f MB' % (os.path.basename(combined), size / 1024 / 1024))

    if args.split:
        for shell in shells:
            own = [m['id'] for m in submodels
                   if '/' + shell['idShort'] + '/' in str(m['id'])]
            single = environment_xml([shell['id']], own)
            own_files = {}
            if not args.no_attachments:
                own_files = collect_attachments(
                    [m for m in submodels if m['id'] in own])
            path = os.path.join(args.target, shell['idShort'] + '.aasx')
            written = write_package(path, single, own_files)
            print('%-32s %8.0f kB   %d submodels'
                  % (shell['idShort'] + '.aasx', written / 1024, len(own)))

    with open(os.path.join(args.target, 'EXPORT.txt'), 'w', encoding='utf-8') as fh:
        fh.write('Export from %s\n' % AAS_URL)
        fh.write('Time: %s\n\n' % datetime.datetime.now().strftime('%Y-%m-%d %H:%M'))
        fh.write('%d shells, %d submodels\n\n' % (len(shells), len(submodels)))
        for shell in sorted(shells, key=lambda s: s['idShort']):
            fh.write('  %s\n' % shell['idShort'])
        fh.write('\nOpen with the AASX Package Explorer:\n')
        fh.write('  https://github.com/admin-shell-io/aasx-package-explorer\n')
    print('\nSummary written to EXPORT.txt')


if __name__ == '__main__':
    main()
