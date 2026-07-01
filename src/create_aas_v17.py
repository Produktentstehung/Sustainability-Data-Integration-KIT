#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_aas_v17.py - Fixes for [Content_Types].xml, HandoverDoc enhancements, and Models3D styling.
"""
import json, sys, os, shutil, zipfile
from pathlib import Path
from datetime import datetime
import xml.etree.ElementTree as ET

import io as _io
sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import re
import unicodedata

def sanitize_id(name):
    """Wandelt einen (Part-)Namen in eine AAS-ID/idShort-konforme Zeichenkette um.
    AAS 3.1 erlaubt für idShort nur [a-zA-Z_][a-zA-Z0-9_]* - also keine Leerzeichen,
    Umlaute oder sonstigen Sonderzeichen. Wird sowohl für die Shell-idShort/id als
    auch für die Submodel-IDs verwendet.
    """
    if not name:
        return name
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue',
        'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
        'ß': 'ss',
    }
    for k, v in replacements.items():
        name = name.replace(k, v)
    # verbleibende diakritische Zeichen (é, à, ç, ...) auf Basisbuchstaben reduzieren
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    # Leerzeichen (auch mehrfach/Tabs) -> Unterstrich
    name = re.sub(r'\s+', '_', name.strip())
    # alle übrigen nicht erlaubten Zeichen -> Unterstrich
    name = re.sub(r'[^A-Za-z0-9_]', '_', name)
    # idShort darf nicht mit einer Ziffer beginnen
    if name and name[0].isdigit():
        name = '_' + name
    return name or 'Undefined'

def indent_xml(elem, level=0):
    i = "\n" + level*"  "
    if len(elem):
        if not elem.text or not elem.text.strip():
            elem.text = i + "  "
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
        for el in elem:
            indent_xml(el, level+1)
        if not elem.tail or not elem.tail.strip():
            elem.tail = i
    else:
        if level and (not elem.tail or not elem.tail.strip()):
            elem.tail = i

with open(sys.argv[1], encoding='utf-8') as f:
    data = json.load(f)

part         = data['part']
bom_items    = [b for b in data['bomItems'] if b]
doc          = data.get('docData') or {}
file_name    = data.get('fileName') or 'model.sldasm'
preview_name = data.get('previewName') or 'preview.jpg'
base_path    = Path(data['basePath'])
output_path  = Path(data['outputPath'])
cad_bin      = data.get('cadBinPath')
preview_bin  = data.get('previewBinPath')

part_weight   = part.get('weight', 0.0)
part_material = part.get('material', '')
part_name  = part.get('name', 'Undefined')
part_name_id = sanitize_id(part_name)  # für AAS-/Submodel-IDs und idShort (keine Leerzeichen/Umlaute)
article_nr = part.get('articleNumber', '000000')
erp_nr     = part.get('erpNumber') or article_nr
status     = part.get('status', '')
created_at = (part.get('createdAt') or '')[:10]
unit       = part.get('unit', '')
category   = part.get('category', '')
ui_link    = part.get('uiLink', '')

file_id    = doc.get('fileId', '')
file_ver   = doc.get('fileVersion', '')
file_class = doc.get('fileClassification', '') or ''
consuming  = doc.get('consumingApp', '') or ''
cad_title  = doc.get('title', '') or file_name
csv_name   = f'BOM_{article_nr}.csv'
today_str  = datetime.now().strftime('%Y-%m-%d')

format_name    = file_class.split(':')[0] if ':' in file_class else file_class
format_version = file_class.split(':')[1] if ':' in file_class else ''
app_parts = consuming.split(' ', 1)
app_name    = app_parts[0] if app_parts else consuming
app_version = app_parts[1] if len(app_parts) > 1 else ''

print(f"Part: {part_name} ({article_nr})")
print(f"CAD: {file_name} | Format: {format_name}:{format_version} | App: {app_name} {app_version}")

# -- Ordnerstruktur ------------------------------------------------------------
shell_dir = output_path / f"{article_nr}_{part_name}"
root_rels_dir = shell_dir / '_rels'
aasx_dir      = shell_dir / 'aasx'
aasx_rels_dir = aasx_dir / '_rels'
files_dir     = aasx_dir / 'files'
new_sub       = aasx_dir / part_name_id  # ID-taugliche Variante, da Teil der Package-URIs/Rels
rels_sub      = new_sub / '_rels'

for d in [shell_dir,root_rels_dir,aasx_dir,aasx_rels_dir,files_dir,new_sub,rels_sub]:
    d.mkdir(parents=True, exist_ok=True)

# -- FIX 1: [Content_Types].xml exakt nach Vorlage aufbauen --------------------
found_ct = list(base_path.rglob('[Content_Types].xml'))
if found_ct:
    shutil.copy2(found_ct[0], shell_dir/'[Content_Types].xml')
else:
    print("  [INFO] Keine [Content_Types].xml gefunden. Generiere Original-Schema...")
    # Bereinigter Nachbau deiner Vorlage (ohne doppelten JPG-Key, da der Package Explorer Case-Insensitive parst)
    default_ct = (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">\n'
        '  <Default Extension="xml" ContentType="text/xml" />\n'
        '  <Default Extension="png" ContentType="image/png" />\n'
        '  <Default Extension="svg" ContentType="text/plain" />\n'
        '  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml" />\n'
        '  <Default Extension="pdf" ContentType="application/pdf" />\n'
        '  <Default Extension="step" ContentType="application/step" />\n'
        '  <Default Extension="JPG" ContentType="image/jpeg" />\n'
        '  <Default Extension="xlsx" ContentType="text/plain" />\n'
        '  <Default Extension="csv" ContentType="text/csv" />\n'
        '  <Default Extension="sldasm" ContentType="application/octet-stream" />\n'
        '  <Default Extension="sldprt" ContentType="application/octet-stream" />\n'
        '  <Override PartName="/aasx/aasx-origin" ContentType="text/plain" />\n'
        '</Types>'
    )
    (shell_dir / '[Content_Types].xml').write_text(default_ct, encoding='utf-8')

(root_rels_dir/'.rels').write_text(
    '<?xml version="1.0" encoding="utf-8"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Type="http://www.admin-shell.io/aasx/relationships/aasx-origin" '
    'Target="aasx/aasx-origin" Id="r1"/></Relationships>', encoding='utf-8')

found_origin = list(base_path.rglob('aasx-origin'))
if found_origin and found_origin[0].is_file():
    shutil.copy2(found_origin[0], aasx_dir/'aasx-origin')
else:
    (aasx_dir/'aasx-origin').write_text('Intentionally empty', encoding='utf-8')

for src_files_dir in [base_path/'aasx'/'files', base_path/'files']:
    if src_files_dir.exists():
        for item in src_files_dir.iterdir():
            if item.is_file() and not (files_dir/item.name).exists():
                shutil.copy2(item, files_dir/item.name)
        break

# Aasx-Altdaten schützen
aasx_out = output_path / f"{article_nr}_{part_name}.aasx"

if aasx_out.exists():
    try:
        with zipfile.ZipFile(aasx_out, 'r') as z:
            for fi in z.infolist():
                if fi.filename.startswith('aasx/files/') and not fi.is_dir():
                    rel = Path(fi.filename).relative_to('aasx/files')
                    tgt = files_dir/rel
                    if not tgt.exists():
                        with z.open(fi) as src, open(tgt,'wb') as dst:
                            shutil.copyfileobj(src, dst)
    except Exception:
        pass

if cad_bin and os.path.exists(cad_bin):
    shutil.copy2(cad_bin, files_dir/file_name)
    print(f"CAD: {file_name} ({os.path.getsize(cad_bin)//1024} KB)")
if preview_bin and os.path.exists(preview_bin):
    shutil.copy2(preview_bin, files_dir/preview_name)

# BOM CSV
lines = ['Position,Komponentennummer,Name,Menge,Einheit,Gewicht(kg),Material,Baugruppenart,Kategorie']
for i, item in enumerate(bom_items):
    lines.append(','.join([
        str(item.get('position', i+1)),
        str(item.get('partNumber','')),
        '"' + str(item.get('name','')).replace('"','""') + '"',
        str(item.get('quantity','')),
        str(item.get('unit','')),        
        str(item.get('weight','')),
        str(item.get('material','')),
        str(item.get('assemblyType','')),
        str(item.get('category','')),
    ]))
(files_dir/csv_name).write_text('\n'.join(lines), encoding='utf-8-sig')

# ============================================================================
# XML Template laden
# ============================================================================
NS = 'https://admin-shell.io/aas/3/1'
ET.register_namespace('', NS)

found_xmls = list(base_path.rglob('*.aas.xml'))
if not found_xmls:
    print(f"FEHLER: Kein *.aas.xml Template in {base_path}")
    sys.exit(1)
src_xml = found_xmls[0]

tree = ET.parse(src_xml)
root = tree.getroot()

def find_typed(parent, tag, id_short):
    if parent is None: return None
    for elem in parent.iter(f'{{{NS}}}{tag}'):
        ids = elem.find(f'{{{NS}}}idShort')
        if ids is not None and ids.text == id_short:
            return elem
    return None

def find_sc(parent, id_short):
    return find_typed(parent, 'submodelElementCollection', id_short)

def set_prop(parent, id_short, value):
    elem = find_typed(parent, 'property', id_short)
    if elem is None: return False
    vn = elem.find(f'{{{NS}}}value')
    if vn is None: vn = ET.SubElement(elem, f'{{{NS}}}value')
    vn.text = str(value) if value is not None else ''
    return True

def set_mlp(parent, id_short, text, lang='de'):
    elem = find_typed(parent, 'multiLanguageProperty', id_short)
    if elem is None: return False
    vb = elem.find(f'{{{NS}}}value')
    if vb is None: vb = ET.SubElement(elem, f'{{{NS}}}value')
    for ls in vb.findall(f'{{{NS}}}langStringTextType'):
        ln = ls.find(f'{{{NS}}}language')
        if ln is not None and ln.text == lang:
            tn = ls.find(f'{{{NS}}}text')
            if tn is not None: tn.text = str(text)
            return True
    ls = ET.SubElement(vb, f'{{{NS}}}langStringTextType')
    ET.SubElement(ls, f'{{{NS}}}language').text = lang
    ET.SubElement(ls, f'{{{NS}}}text').text = str(text)
    return True

def set_file(parent, id_short, path, mime):
    elem = find_typed(parent, 'file', id_short)
    if elem is None:
        return False
    vn = elem.find(f'{{{NS}}}value')
    if vn is None: vn = ET.SubElement(elem, f'{{{NS}}}value')
    vn.text = str(path)
    ct = elem.find(f'{{{NS}}}contentType')
    if ct is None: ct = ET.SubElement(elem, f'{{{NS}}}contentType')
    ct.text = str(mime)
    return True

submodels = {}
for sm in root.iter(f'{{{NS}}}submodel'):
    ids = sm.find(f'{{{NS}}}idShort')
    if ids is not None and ids.text:
        submodels[ids.text] = sm

# ── Nameplate ─────────────────────────────────────────────────────────────────
if 'Nameplate' in submodels:
    sm = submodels['Nameplate']
    set_mlp(sm, 'ManufacturerProductDesignation', part_name, 'de')
    set_prop(sm, 'ProductArticleNumberOfManufacturer', article_nr)
    set_prop(sm, 'SerialNumber', f'{article_nr}-00-000000-00')
    set_prop(sm, 'YearOfConstruction', created_at[:4] if created_at else '')
    set_prop(sm, 'URIOfTheProduct', ui_link)
    set_mlp(sm, 'ManufacturerProductFamily', 'Lehrstuhl-Produkte', 'de')

# ── DataSources ────────────────────────────────────────────────────────────────
if 'DataSources' in submodels:
    sm = submodels['DataSources']
    ed = find_sc(sm, 'Engineering Data / PLM')
    if ed is not None:
        set_prop(ed, 'Material', part_material)
        set_prop(ed, 'Weight', part_weight)

# ── Models3D ──────────────────────────────────────────────────────────────────
if 'Models3D' in submodels:
    sm = submodels['Models3D']
    set_mlp(sm, 'Title', cad_title, 'de')
    set_prop(sm, 'FileName', file_name)
    set_prop(sm, 'FileVersionId', file_ver)
    set_prop(sm, 'SetDate', today_str)
    set_prop(sm, 'StatusValue', 'released')
    set_file(sm, 'DigitalFile', f'/aasx/files/{file_name}', 'application/octet-stream')
    set_file(sm, 'PreviewFile', f'/aasx/files/{preview_name}', 'image/jpeg')

    ff = find_sc(sm, 'FileFormat')
    if ff is not None:
        set_prop(ff, 'FormatName',    format_name)
        set_prop(ff, 'FormatVersion', format_version)
        set_prop(ff, 'FormatQualifier', '')

    sa = find_sc(sm, 'SourceApplication')
    if sa is not None:
        set_prop(sa, 'ApplicationName',      app_name)
        set_prop(sa, 'ApplicationVersion',   app_version)
        set_prop(sa, 'ApplicationQualifier', '')
        vo = find_sc(sa, 'VendorOrganization')
        if vo is not None:
            set_prop(vo, 'OrganizationName',         'Dassault Systemes')
            set_prop(vo, 'OrganizationOfficialName',  'Dassault Systemes SE')

    ca_list = find_typed(sm, 'submodelElementList', 'ConsumingApplication')
    if ca_list is not None:
        ca_val = ca_list.find(f'{{{NS}}}value')
        if ca_val is not None:
            ca_colls = list(ca_val)
            if ca_colls:
                ca = ca_colls[0]
                set_prop(ca, 'ApplicationName',      app_name)
                set_prop(ca, 'ApplicationVersion',   app_version)
                set_prop(ca, 'ApplicationQualifier', '')
                vo2 = find_sc(ca, 'VendorOrganization')
                if vo2 is not None:
                    set_prop(vo2, 'OrganizationName',        'Dassault Systemes')
                    set_prop(vo2, 'OrganizationOfficialName', 'Dassault Systemes SE')

# ── FIX 2: HandoverDocumentation Anpassungen ──────────────────────────────────
if 'HandoverDocumentation' in submodels:
    sm = submodels['HandoverDocumentation']

    # 2.1) DocumentVersion_de (BOM CSV)
    dv_de = find_sc(sm, 'DocumentVersion_de')
    if dv_de is not None:
        set_mlp(dv_de, 'Title', csv_name, 'de')
        set_mlp(dv_de, 'Subtitle', '', 'de') 
        
        set_prop(dv_de, 'StatusSetDate', today_str)
        set_prop(dv_de, 'StatusValue', 'released')
        set_prop(dv_de, 'OrganizationOfficialName', 'HNI Produktentstehung')
        set_prop(dv_de, 'OrganizationShortName', 'HNI')
        set_file(dv_de, 'DigitalFile', f'/aasx/files/{csv_name}', 'text/csv')

    # 2.2) DocumentVersion_file (CAD-Modell)
    dv_file = find_sc(sm, 'DocumentVersion_file')
    if dv_file is not None:
        set_mlp(dv_file, 'Title', cad_title, 'de')
        set_prop(dv_file, 'StatusSetDate', today_str)
        set_prop(dv_file, 'StatusValue', 'released')
        set_prop(dv_file, 'OrganizationOfficialName', 'HNI Produktentstehung')
        
        # OrganizationShortName zu "HNI" ändern
        set_prop(dv_file, 'OrganizationShortName', 'HNI')
        
        set_file(dv_file, 'DigitalFile', f'/aasx/files/{file_name}', 'application/octet-stream')
        
        # PreviewFile an der zugehörigen Stelle in der SMC ablegen
        set_file(dv_file, 'PreviewFile', f'/aasx/files/{preview_name}', 'image/jpeg')

    doc_id_coll = find_sc(sm, 'DocumentId')
    if doc_id_coll is not None:
        set_prop(doc_id_coll, 'DocumentIdentifier', f'BOM_{article_nr}')
        set_prop(doc_id_coll, 'DocumentDomainId', 'CIM-Database')

# ── BackendSpecificMaterialInformation ────────────────────────────────────────
if 'BackendSpecificMaterialInformation' in submodels:
    sm = submodels['BackendSpecificMaterialInformation']
    msp = find_sc(sm, 'MaterialSystemProperties')
    if msp is not None:
        set_prop(msp, 'MaterialType', part_material)
        set_mlp(msp, 'ProductName', part_name, 'en')
        set_prop(msp, 'MaterialStatus', status)
        set_mlp(msp, 'BaseUnitOfMeasure', unit, 'en')
        set_prop(msp, 'MaterialNumber', part.get('materialObjectId',''))
        set_mlp(msp, 'Description', f'{part_name} - {category}', 'en')

# ── Submodel-IDs + Referenzen dynamisch anpassen ──────────────────────────────
# Alten Part-Namen aus der Shell-ID des Templates ermitteln (z.B. "Kugelschreiber"
# aus "localhost/demo/aas/Kugelschreiber"), BEVOR die Shell-ID unten überschrieben
# wird. Damit lässt sich das exakte Pfad-Segment in jeder Submodel-ID durch den
# aktuellen part_name ersetzen (kein blinder String-Replace).
old_part_name = None
_shell = root.find(f'.//{{{NS}}}assetAdministrationShell')
if _shell is not None:
    _shell_id = _shell.find(f'{{{NS}}}id')
    if _shell_id is not None and _shell_id.text:
        old_part_name = _shell_id.text.rstrip('/').split('/')[-1]

id_updates = {}  # alte Submodel-ID -> neue Submodel-ID
if old_part_name and old_part_name != part_name_id:
    for sm in submodels.values():
        id_elem = sm.find(f'{{{NS}}}id')
        if id_elem is not None and id_elem.text:
            old_id = id_elem.text
            segments = old_id.split('/')
            new_segments = [part_name_id if seg == old_part_name else seg for seg in segments]
            new_id = '/'.join(new_segments)
            if new_id != old_id:
                id_elem.text = new_id
                id_updates[old_id] = new_id

    # Alle Referenzen im Dokument (z.B. submodelRefs in der Shell, oder
    # Referenzen zwischen Submodellen) auf die neuen IDs nachziehen
    if id_updates:
        for key_elem in root.iter(f'{{{NS}}}key'):
            val_elem = key_elem.find(f'{{{NS}}}value')
            if val_elem is not None and val_elem.text in id_updates:
                val_elem.text = id_updates[val_elem.text]
        print(f"Submodel-IDs aktualisiert: '{old_part_name}' -> '{part_name_id}' ({len(id_updates)} IDs)")

# ── AAS Shell IDs anpassen ────────────────────────────────────────────────────
for aas in root.iter(f'{{{NS}}}assetAdministrationShell'):
    id_short = aas.find(f'{{{NS}}}idShort')
    id_elem  = aas.find(f'{{{NS}}}id')
    if id_short is not None: id_short.text = part_name_id
    if id_elem  is not None: id_elem.text  = f'localhost/demo/aas/{part_name_id}'
    ai = aas.find(f'{{{NS}}}assetInformation')
    if ai is not None:
        gai = ai.find(f'{{{NS}}}globalAssetId')
        if gai is not None: gai.text = f'localhost/demo/asset/{part_name_id}'

# ── XML schreiben ─────────────────────────────────────────────────────────────
indent_xml(root)
xml_str  = ET.tostring(root, encoding='unicode', xml_declaration=False)
xml_path = new_sub / f'{part_name_id}.aas.xml'
xml_path.write_text(f'<?xml version="1.0" encoding="utf-8"?>\n{xml_str}', encoding='utf-8')

# ── .rels Dateien ─────────────────────────────────────────────────────────────
rels_lines = [f'<Relationship Type="http://www.admin-shell.io/aasx/relationships/aas-spec" Target="{part_name_id}.aas.xml" Id="r1"/>']
rid = 2
for fp in sorted(files_dir.iterdir()):
    if fp.is_file():
        rels_lines.append(f'<Relationship Type="http://schemas.openxmlformats.org/package/2006/relationships/attachments" Target="../../files/{fp.name}" Id="r{rid}"/>')
        rid += 1
rels_header = '<?xml version="1.0" encoding="utf-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
(rels_sub/f'{part_name_id}.aas.xml.rels').write_text(
    rels_header + '\n  ' + '\n  '.join(rels_lines) + '\n</Relationships>', encoding='utf-8')

(aasx_rels_dir/'aasx-origin.rels').write_text(
    f'<?xml version="1.0" encoding="utf-8"?>'
    f'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    f'<Relationship Type="http://www.admin-shell.io/aasx/relationships/aas-spec" '
    f'Target="{part_name_id}/{part_name_id}.aas.xml" Id="r1"/></Relationships>', encoding='utf-8')

# ── AASX packen ───────────────────────────────────────────────────────────────
with zipfile.ZipFile(aasx_out, 'w', zipfile.ZIP_DEFLATED) as z:
    for fp in sorted(shell_dir.rglob('*')):
        if fp.is_file():
            z.write(fp, fp.relative_to(shell_dir))
print(f"\nFERTIG: {aasx_out.name} ({aasx_out.stat().st_size//1024} KB)")