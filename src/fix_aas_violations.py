"""Removes violations of the AAS specification from an AAS server.

Administration shells exported from a PLM system commonly violate the
specification in several hundred places. The AASX Package Explorer is lenient
and opens them regardless, other tools are not - and for a Tractus-X KIT the
data should be conformant.

This script works on the JSON representation served by the AAS server and
addresses each cause at its root:

  AASd-002   short names may only contain letters, digits and underscore and
             must begin with a letter
  AASd-120   children of a SubmodelElementList must not carry a short name
  AASd-118   supplemental semantic references without a main reference
  AASd-129   qualifiers of kind Template outside a template
  AASd-021   several qualifiers of the same kind on one element
  AASd-122   references to submodels must be model references
  Languages  identifiers such as "en?" instead of "en"; the same language twice
  Values     empty texts, values that do not match their declared type
  Qualifiers empty lists, which must either be absent or hold content

Usage:
    python fix_aas_violations.py            show what would be changed
    python fix_aas_violations.py --apply    write the changes back

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
import collections
import json
import os
import re
import urllib.request

AAS_URL = os.environ.get('SDI_AAS_URL', 'http://localhost:8081')

ALLOWED = re.compile(r'^[a-zA-Z][a-zA-Z0-9_]*$')

# These structures of the KIT hold named entries - the data sources, the
# calculation runs, the impact methods, the machines. Modelled as a list they
# violate AASd-120, because children of a list must not carry a short name.
# Here the name carries meaning: the flows find their data source through it.
# The correct construct is therefore the collection, not the list.
TO_COLLECTION = {'DataSources', 'LCAIteration', 'LCIAMethods',
                 'ManufacturingProcesses'}

# Short names that must not simply be rewritten, because the flows read them.
# The target spelling is the one the flows already expect.
RENAME = {
    'Engineering Data / PLM': 'PLM',
    'EngineeringData_PLM': 'PLM',
    'Manufacturing': 'MachineData',
    'ERPData': 'ERP',
    '<DataSource>': 'DataSourceTemplate',
    '<LCIAMethodName>': 'LCIAMethodTemplate',
}

XSD_NUMERIC = ('xs:double', 'xs:float', 'xs:decimal', 'xs:integer', 'xs:int',
               'xs:long', 'xs:short', 'xs:byte', 'xs:unsignedInt',
               'xs:unsignedLong')

counter = collections.Counter()


def b64(text):
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip('=')


def fetch(path):
    request = urllib.request.Request(AAS_URL + path,
                                     headers={'Accept': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def put(path, content):
    request = urllib.request.Request(
        AAS_URL + path, data=json.dumps(content).encode(), method='PUT',
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=120) as response:
        return response.status


def clean_short_name(name):
    """Turns a short name into a permitted one.

    Umlauts are transcribed, forbidden characters become underscores, and a
    name starting with a digit gets a letter in front. Names the flows read
    keep their agreed spelling.
    """
    if name in RENAME:
        return RENAME[name]
    text = (name.replace('ä', 'ae').replace('ö', 'oe').replace('ü', 'ue')
                .replace('Ä', 'Ae').replace('Ö', 'Oe').replace('Ü', 'Ue')
                .replace('ß', 'ss'))
    text = re.sub(r'[^A-Za-z0-9_]', '_', text)
    text = re.sub(r'_+', '_', text).strip('_')
    if not text:
        text = 'Element'
    if text[0].isdigit():
        text = 'N' + text
    return text


def clean_language(tag):
    """Brings a language identifier into the form of BCP 47."""
    cleaned = re.sub(r'[^A-Za-z-]', '', str(tag or ''))
    return cleaned.split('-')[0][:2].lower() or 'en'


def clean_texts(entries, kind):
    """Cleans language texts: identifier, empty texts, duplicate languages."""
    cleaned, seen = [], set()
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        language = clean_language(entry.get('language'))
        if language != entry.get('language'):
            counter['language identifier corrected'] += 1
        text = (entry.get('text') or '').strip()
        if not text:
            counter['empty text removed'] += 1
            continue
        if language in seen:
            counter['duplicate language in %s removed' % kind] += 1
            continue
        seen.add(language)
        cleaned.append({'language': language, 'text': text})
    return cleaned


def clean_qualifiers(element):
    """Removes empty lists and repeated qualifiers of the same kind."""
    qualifiers = element.get('qualifiers')
    if qualifiers is None:
        return
    if not qualifiers:
        del element['qualifiers']
        counter['empty qualifier list removed'] += 1
        return
    cleaned, kinds = [], set()
    for entry in qualifiers:
        kind = entry.get('type')
        if kind in kinds:
            counter['duplicate qualifier removed'] += 1
            continue
        kinds.add(kind)
        # The kind "template" belongs in a template, not in an instance
        if entry.get('kind') == 'TemplateQualifier':
            entry['kind'] = 'ConceptQualifier'
            counter['qualifier kind corrected'] += 1
        cleaned.append(entry)
    element['qualifiers'] = cleaned


def clean_element(element, inside_list=False):
    """Walks an element and its children and removes the violations."""
    if not isinstance(element, dict):
        return

    # AASd-120: children of a list must not carry a short name
    if inside_list and 'idShort' in element:
        del element['idShort']
        counter['short name inside list removed'] += 1
    elif element.get('idShort') in RENAME:
        # Data sources of an earlier naming, for example "Manufacturing"
        # instead of "MachineData". These names are permitted, so the check
        # above never touches them - they would silently remain and the flows
        # would then find the same source under two names.
        element['idShort'] = RENAME[element['idShort']]
        counter['data source renamed'] += 1
    elif 'idShort' in element and element['idShort'] \
            and not ALLOWED.match(element['idShort']):
        element['idShort'] = clean_short_name(element['idShort'])
        counter['short name corrected'] += 1

    for field, kind in (('description', 'description'),
                        ('displayName', 'display name')):
        if field in element:
            cleaned = clean_texts(element[field], kind)
            if cleaned:
                element[field] = cleaned
            else:
                del element[field]

    clean_qualifiers(element)

    # AASd-118: supplemental references without a main reference are invalid
    if element.get('supplementalSemanticIds') and not element.get('semanticId'):
        del element['supplementalSemanticIds']
        counter['supplemental semantic reference removed'] += 1

    # Values must match their declared type. An empty string is a valid value
    # only for xs:string; for numbers and dates it means "not set" - then the
    # field belongs away entirely.
    if element.get('modelType') == 'Property':
        value_type, value = element.get('valueType'), element.get('value')
        if value_type and value_type != 'xs:string' and value == '':
            del element['value']
            counter['empty value on non-text removed'] += 1
        elif value_type in XSD_NUMERIC and value is not None:
            try:
                float(str(value).replace(',', '.'))
            except ValueError:
                del element['value']
                counter['unsuitable numeric value removed'] += 1
        elif value_type in ('xs:dateTime', 'xs:date') and value:
            if not re.match(r'^\d{4}-\d{2}-\d{2}', str(value)):
                del element['value']
                counter['unsuitable date removed'] += 1

    if element.get('modelType') == 'MultiLanguageProperty' and 'value' in element:
        cleaned = clean_texts(element['value'], 'value')
        if cleaned:
            element['value'] = cleaned
        else:
            del element['value']
        return

    # Lists with named entries become collections. Their children may then
    # keep the name through which the flows find them.
    if (element.get('modelType') == 'SubmodelElementList'
            and element.get('idShort') in TO_COLLECTION):
        element['modelType'] = 'SubmodelElementCollection'
        for field in ('typeValueListElement', 'orderRelevant',
                      'semanticIdListElement', 'valueTypeListElement'):
            element.pop(field, None)
        counter['list converted to collection'] += 1

    # A file reference without a target is invalid: the value must be an
    # address. Without one the field is removed; the reference itself remains
    # as a placeholder, only without an empty address.
    if element.get('modelType') in ('File', 'Blob'):
        value = element.get('value')
        if value == '':
            del element['value']
            counter['empty file address removed'] += 1
        elif value and '/basyx-temp' in str(value):
            # On upload the server places attachments in a working directory
            # of its own and writes that path into the reference. Outside the
            # server that is not a valid address, so the file name is restored.
            name = str(value).rsplit('-', 1)[-1].rsplit('/', 1)[-1]
            element['value'] = '/aasx/files/' + name
            counter['file address reset'] += 1

    children_in_list = element.get('modelType') == 'SubmodelElementList'
    if children_in_list and not element.get('typeValueListElement'):
        element['typeValueListElement'] = 'SubmodelElementCollection'
        counter['list type added'] += 1

    # AASd-109: a list holding properties or ranges must also state their
    # data type.
    if (children_in_list
            and element.get('typeValueListElement') in ('Property', 'Range')
            and not element.get('valueTypeListElement')):
        types = {child.get('valueType') for child in (element.get('value') or [])
                 if isinstance(child, dict) and child.get('valueType')}
        element['valueTypeListElement'] = types.pop() if len(types) == 1 else 'xs:string'
        counter['data type of list added'] += 1

    if isinstance(element.get('value'), list):
        for child in element['value']:
            clean_element(child, children_in_list)


def clean_shell(shell):
    """Corrects the references of a shell to its submodels."""
    for reference in shell.get('submodels') or []:
        if reference.get('type') != 'ModelReference':
            reference['type'] = 'ModelReference'
            counter['reference type corrected'] += 1
        for key in reference.get('keys') or []:
            if key.get('type') != 'Submodel':
                key['type'] = 'Submodel'
                counter['reference key corrected'] += 1
    for field, kind in (('description', 'description'),
                        ('displayName', 'display name')):
        if field in shell:
            cleaned = clean_texts(shell[field], kind)
            if cleaned:
                shell[field] = cleaned
            else:
                del shell[field]


def main():
    parser = argparse.ArgumentParser(
        description='Remove specification violations from the AAS server.')
    parser.add_argument('--apply', action='store_true',
                        help='write the corrections back to the server')
    args = parser.parse_args()

    shells = fetch('/shells')['result']
    submodels = fetch('/submodels?limit=500')['result']
    print('%d shells, %d submodels\n' % (len(shells), len(submodels)))

    for shell in shells:
        clean_shell(shell)
    for submodel in submodels:
        clean_element(submodel)
        for element in submodel.get('submodelElements') or []:
            clean_element(element)

    if not counter:
        print('Nothing to correct.')
        return

    print('%-46s %s' % ('Correction', 'Count'))
    print('-' * 56)
    for name, count in counter.most_common():
        print('%-46s %6d' % (name, count))
    print('-' * 56)
    print('%-46s %6d' % ('total', sum(counter.values())))

    if not args.apply:
        print('\nShown only. Use --apply to write the changes.')
        return

    print('\nWriting back ...')
    failures = 0
    for shell in shells:
        try:
            put('/shells/' + b64(shell['id']), shell)
        except Exception as error:
            failures += 1
            print('   shell %s: %s' % (shell.get('idShort'), str(error)[:90]))
    for submodel in submodels:
        try:
            put('/submodels/' + b64(submodel['id']), submodel)
        except Exception as error:
            failures += 1
            print('   submodel %s: %s' % (submodel.get('idShort'), str(error)[:90]))
    print('Done, %d write errors.' % failures)


if __name__ == '__main__':
    main()
