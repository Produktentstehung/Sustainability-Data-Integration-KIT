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
"""Checks and repairs AASX packages.

An AASX package is an OPC container. Rule M.1.14 of the specification requires
a declared content type for every file it contains - either through the file
extension in [Content_Types].xml or through an override entry. Without it, AAS
servers refuse to load the package with a message such as:

    InvalidFormatException: The part /aasx/files/xyz does not have any
    content type! Rule: Package require content types [M.1.14]

The script finds such files and fixes them in two ways:

* operating system artefacts (Thumbs.db, .DS_Store, desktop.ini) are removed
* for all remaining extensions a default entry is added

The most common case by far is Thumbs.db, which Windows Explorer leaves behind
in a folder whose contents were viewed as thumbnails. It travels into the
package unnoticed and makes the import fail with an error that names the file
but not the reason.

Usage:
    python repair_aasx.py <file or directory> [--check]

    --check  only report, change nothing
"""
import os
import re
import shutil
import sys
import zipfile

ARTEFACTS = ("thumbs.db", ".ds_store", "desktop.ini", "ehthumbs.db")

# Known extensions with their content type; everything else is declared as
# application/octet-stream.
TYPES = {
    "xml": "text/xml",
    "json": "application/json",
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "gif": "image/gif",
    "svg": "image/svg+xml",
    "pdf": "application/pdf",
    "csv": "text/csv",
    "txt": "text/plain",
    "step": "application/step",
    "stp": "application/step",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
CT_NAME = "[Content_Types].xml"


def extension(path):
    name = path.rsplit("/", 1)[-1]
    return name.rsplit(".", 1)[-1].lower() if "." in name else ""


def declared(ct_xml):
    defaults = {m.lower() for m in re.findall(r'Extension="([^"]+)"', ct_xml)}
    overrides = {m for m in re.findall(r'PartName="([^"]+)"', ct_xml)}
    return defaults, overrides


def inspect(path):
    """Returns (artefacts, missing extensions, content types present)."""
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if CT_NAME not in names:
            return [], [], False
        content_types = archive.read(CT_NAME).decode("utf-8", "replace")
    defaults, overrides = declared(content_types)

    artefacts, missing = [], set()
    for name in names:
        if name.endswith("/") or name == CT_NAME:
            continue
        if name.rsplit("/", 1)[-1].lower() in ARTEFACTS:
            artefacts.append(name)
            continue
        if "/" + name in overrides or name in overrides:
            continue
        found = extension(name)
        if not found or found not in defaults:
            missing.add(found or name)
    return artefacts, sorted(missing), True


# ---------------------------------------------------------------------------
# Content of the shell
# ---------------------------------------------------------------------------
# The package structure can be correct while the content still violates the
# specification. Four things come out of the template the PLM builds from and
# survive into every generated package, because the generator fills values in
# but never removes what stayed empty:
#
#   <qualifiers/>            an element that must be absent or hold an entry
#   duplicate languages      a description carrying "en" three times
#   empty typed values       a date or a number with no value at all
#   illegal idShort          "Weight (g)" - a name may hold only letters,
#                            digits and underscore
#   idShort inside a list    AASd-120 - a direct child of a submodel element
#                            list must not carry a name at all
#
# None of this keeps a package from opening, which is why it goes unnoticed -
# the AASX Package Explorer shows it, a strict reader rejects it.


AAS_NAMESPACE = 'https://admin-shell.io/aas/3/1'


def _sauberer_name(name):
    """Turns a name into a permitted idShort, or returns None.

    Permitted are letters, digits and underscore, starting with a letter.
    Angle brackets around a placeholder name are dropped rather than turned
    into underscores, so "<DataSource>" becomes "DataSource".
    """
    entschaerft = name.replace('&lt;', '').replace('&gt;', '')
    neu = re.sub(r'[^A-Za-z0-9_]', '_', entschaerft).strip('_')
    neu = re.sub(r'_+', '_', neu)
    if not neu or not neu[0].isalpha():
        return None
    return neu


def normalise_idshorts(text):
    """Renames idShorts that hold characters the specification forbids.

    A name is only renamed when it appears nowhere else in the document. An
    idShort can be the target of a model reference, and renaming one that is
    pointed at would trade a cosmetic finding for a broken pointer. The
    longest name is handled first: "Technical Specification" is a substring of
    "Technical Specifications", and replacing the short one first would eat
    into the long one.
    """
    count = 0
    namen = {n for n in re.findall(r'<idShort>([^<]*)</idShort>', text)
             if not re.match(r'^[A-Za-z][A-Za-z0-9_]*$', n)}
    for name in sorted(namen, key=len, reverse=True):
        neu = _sauberer_name(name)
        if neu is None or neu == name:
            continue
        als_idshort = len(re.findall(
            r'<idShort>%s</idShort>' % re.escape(name), text))
        # Occurrences of this exact string that are not the idShort itself.
        anderswo = len(re.findall(re.escape(name), text)) - als_idshort
        # A longer name that contains this one is not a reference to it.
        for laenger in namen:
            if laenger != name and name in laenger:
                anderswo -= len(re.findall(re.escape(laenger), text))
        if anderswo > 0:
            continue
        text = text.replace('<idShort>%s</idShort>' % name,
                            '<idShort>%s</idShort>' % neu)
        count += als_idshort
    # A name that is there but empty is not a name.
    text, hits = re.subn(r'\s*<idShort>\s*</idShort>', '', text)
    count += hits
    text, hits = re.subn(r'\s*<idShort\s*/>', '', text)
    count += hits
    return text, count


def strip_list_child_idshorts(text):
    """AASd-120: a direct child of a submodel element list carries no idShort.

    Parsed rather than matched. Lists sit inside one another, and a pattern
    cannot tell which idShort belongs to which level - it would strip names
    from grandchildren that are allowed to keep them.
    """
    import xml.etree.ElementTree as ET
    ET.register_namespace('', AAS_NAMESPACE)
    try:
        baum = ET.fromstring(text)
    except ET.ParseError:
        # Not our business to guess at a broken document.
        return text, 0
    count = 0
    for liste in baum.iter('{%s}submodelElementList' % AAS_NAMESPACE):
        for wert in liste.findall('{%s}value' % AAS_NAMESPACE):
            for kind in list(wert):
                for name in kind.findall('{%s}idShort' % AAS_NAMESPACE):
                    kind.remove(name)
                    count += 1
    if not count:
        return text, 0
    kopf = '<?xml version="1.0" encoding="UTF-8"?>' + chr(10)
    return kopf + ET.tostring(baum, encoding='unicode'), count


def clean_content(text):
    """Removes the violations above from an .aas.xml. Returns text and count.

    Repeats until nothing changes. The last step reserialises the
    document through an XML parser, and that writes some elements in a
    different but equivalent form - an empty element as <qualifiers />
    rather than <qualifiers/>. The text steps above would miss those on
    the first pass, so a single run left work behind and the repair was
    not idempotent: running it twice kept reporting findings, and the
    check that the sample data needs no repair would never pass.
    """
    gesamt = 0
    for _ in range(5):
        text, hits = _clean_once(text)
        gesamt += hits
        if not hits:
            break
    return text, gesamt


def _clean_once(text):
    """One pass. See clean_content."""
    count = 0

    # An empty qualifiers element must not be there at all.
    cleaned, hits = re.subn(r'\s*<qualifiers\s*/>', '', text)
    count += hits
    cleaned, hits = re.subn(r'\s*<qualifiers>\s*</qualifiers>', '', cleaned)
    count += hits

    # Within one description every language may appear once.
    def unique_languages(match):
        nonlocal count
        block = match.group(1)
        seen = set()
        kept = []
        for entry in re.findall(r'<langStringTextType>.*?</langStringTextType>',
                                block, re.S):
            language = re.search(r'<language>([^<]*)</language>', entry)
            key = language.group(1) if language else ''
            if key in seen:
                count += 1
                continue
            seen.add(key)
            kept.append(entry)
        return '<description>' + ''.join(kept) + '</description>'

    cleaned = re.sub(r'<description>(.*?)</description>', unique_languages,
                     cleaned, flags=re.S)

    # Derselbe Fehler steckt im Anzeigenamen.
    def unique_display(match):
        nonlocal count
        block = match.group(1)
        seen = set()
        kept = []
        for entry in re.findall(r'<langStringNameType>.*?</langStringNameType>',
                                block, re.S):
            language = re.search(r'<language>([^<]*)</language>', entry)
            key = language.group(1) if language else ''
            if key in seen:
                count += 1
                continue
            seen.add(key)
            kept.append(entry)
        return '<displayName>' + ''.join(kept) + '</displayName>'

    cleaned = re.sub(r'<displayName>(.*?)</displayName>', unique_display,
                     cleaned, flags=re.S)

    # A typed property without a value is invalid for everything but text.
    def drop_empty_value(match):
        nonlocal count
        value_type = match.group(1)
        # Auch bei Text: ein Property darf ohne Wert stehen, aber nicht mit
        # einem leeren. Das Element ganz wegzulassen ist zulaessig.
        pass
        count += 1
        return '<valueType>%s</valueType>' % value_type

    cleaned = re.sub(r'<valueType>([^<]+)</valueType>\s*<value\s*/>',
                     drop_empty_value, cleaned)

    # An empty short name is worse than none: for a member of a list the
    # specification forbids one entirely, and elsewhere it must carry a name.
    cleaned, hits = re.subn(r'\s*<idShort\s*/>', '', cleaned)
    count += hits

    # A text in no language says nothing. The entry goes, and with it the
    # wrapper if nothing is left.
    cleaned, hits = re.subn(
        r'\s*<langStringTextType>\s*<language>[^<]*</language>\s*'
        r'<text\s*/>\s*</langStringTextType>', '', cleaned)
    count += hits
    cleaned, hits = re.subn(
        r'\s*<langStringNameType>\s*<language>[^<]*</language>\s*'
        r'<text\s*/>\s*</langStringNameType>', '', cleaned)
    count += hits
    # Containers that are present but hold nothing. The specification allows
    # each of them to be absent, and requires that if present it holds at
    # least one entry - an empty one is the only form that is wrong. They come
    # out of the template shell, where a field was foreseen and never filled.
    #
    # <value> is deliberately not in this list. It carries the content of a
    # property, where an empty one is a different matter, and stripping it
    # everywhere would empty out properties that legitimately hold nothing.
    for leer in ('description', 'displayName', 'isCaseOf',
                 'supplementalSemanticIds', 'valueReferencePairTypes',
                 'valueList', 'embeddedDataSpecifications',
                 'specificAssetIds'):
        cleaned, hits = re.subn(r'\s*<%s>\s*</%s>' % (leer, leer), '', cleaned)
        count += hits
        cleaned, hits = re.subn(r'\s*<%s\s*/>' % leer, '', cleaned)
        count += hits

    # The shell points at its submodels, and those pointers are model
    # references rather than external ones.
    #
    # Only inside the shell. The element <submodels> occurs twice: once as the
    # list of pointers in the shell, once as the container holding every
    # submodel of the environment. Rewriting both turned six hundred semantic
    # identifiers into model references and made the package far worse than it
    # was - the check went from 143 findings to 711.
    def als_modellverweis(match):
        nonlocal count
        kopf, block = match.group(1), match.group(2)
        neu_block, treffer = re.subn(
            r'<type>ExternalReference</type>', '<type>ModelReference</type>',
            block)
        count += treffer
        return kopf + neu_block + '</submodels>'

    cleaned = re.sub(
        r'(<assetAdministrationShell>.*?<submodels>)(.*?)</submodels>',
        als_modellverweis, cleaned, flags=re.S)

    cleaned, hits = normalise_idshorts(cleaned)
    count += hits

    # Last, because it reserialises the document: every step above works on
    # the text and would have to be repeated on the new formatting.
    cleaned, hits = strip_list_child_idshorts(cleaned)
    count += hits
    return cleaned, count


def count_content_violations(path):
    """How many content violations the package holds. Reads only."""
    gesamt = 0
    with zipfile.ZipFile(path) as archive:
        for item in archive.namelist():
            if item.endswith('.aas.xml'):
                text = archive.read(item).decode('utf-8', 'replace')
                gesamt += clean_content(text)[1]
    return gesamt


def repair(path, check=False):
    artefacts, missing, has_content_types = inspect(path)
    name = os.path.basename(path)
    if not has_content_types:
        print(f"  {name}: no {CT_NAME} inside - not a valid AASX package")
        return False
    # The content counts too. Deciding on the package structure alone let a
    # package pass as "in order" while holding a hundred content violations -
    # the repair never ran because the question was never asked.
    violations = count_content_violations(path)
    if not artefacts and not missing and not violations:
        print(f"  {name}: in order")
        return False
    print(f"  {name}:")
    for artefact in artefacts:
        print(f"     artefact      {artefact}")
    for found in missing:
        print(f"     no type       .{found}")
    if violations:
        print(f"     content       {violations} violations of the specification")
    if check:
        return True

    cleaned_total = 0
    temporary = path + ".tmp"
    with zipfile.ZipFile(path) as source, \
            zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as target:
        content_types = source.read(CT_NAME).decode("utf-8", "replace")
        added = "".join(
            f'  <Default Extension="{found}" '
            f'ContentType="{TYPES.get(found, "application/octet-stream")}" />\n'
            for found in missing if found and "." not in found)
        if added:
            content_types = content_types.replace("</Types>", added + "</Types>")
        for item in source.infolist():
            if item.filename.rsplit("/", 1)[-1].lower() in ARTEFACTS:
                continue
            if item.filename == CT_NAME:
                target.writestr(item, content_types)
            elif item.filename.endswith('.aas.xml'):
                text = source.read(item.filename).decode('utf-8', 'replace')
                text, removed = clean_content(text)
                cleaned_total += removed
                target.writestr(item, text.encode('utf-8'))
            else:
                target.writestr(item, source.read(item.filename))
    shutil.move(temporary, path)
    print(f"     -> repaired ({len(artefacts)} removed, "
          f"{len(missing)} types added, {cleaned_total} content violations)")
    return True


def main():
    # "--help" ist keine Datei. Ohne diese Abfrage versucht das Programm, eine
    # Datei dieses Namens zu oeffnen, und bricht mit einem Abbild ab.
    if len(sys.argv) < 2 or sys.argv[1] in ('--help', '-h', '/?'):
        print(__doc__.strip())
        return
    target = sys.argv[1]
    check = "--check" in sys.argv

    files = []
    if os.path.isdir(target):
        for root, _, names in os.walk(target):
            files += [os.path.join(root, name) for name in names
                      if name.lower().endswith(".aasx")]
    else:
        files = [target]

    print(("Checking" if check else "Repairing") + f" {len(files)} AASX packages:")
    affected = sum(1 for path in sorted(files) if repair(path, check))
    print(f"\n{affected} of {len(files)} packages affected.")


if __name__ == "__main__":
    main()
