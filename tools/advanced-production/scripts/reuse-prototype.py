#!/usr/bin/env python3
"""Clone selected native prototype pages, with exact shape-text edits only.

Usage: reuse-prototype.py --job JOB.json --output NEW.pptx
Job paths are relative to JOB.json. This makes an independent excerpt; it does
not claim the source whole deck was preserved as a partial edit. No rendering or
semantic quality approval is inferred from this package operation.
"""
import argparse
import copy
import importlib.util
import io
import json
import posixpath
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import quoteattr

_spec = importlib.util.spec_from_file_location('pptx_scope_native', Path(__file__).with_name('pptx-scope.py'))
_scope = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scope)
Package, PackageError = _scope.Package, _scope.PackageError
P, A, R, PK, CT = _scope.P, _scope.A, _scope.R, _scope.PK, _scope.CT
sha256, xml, relpart = _scope.sha256, _scope.xml, _scope.relpart


MC = 'http://schemas.openxmlformats.org/markup-compatibility/2006'
XSI = 'http://www.w3.org/2001/XMLSchema-instance'


def _namespace_map(data):
    namespaces = {}
    if data is not None:
        for _, pair in ET.iterparse(io.BytesIO(data), events=('start-ns',)):
            prefix, uri = pair
            if prefix in namespaces and namespaces[prefix] != uri:
                # One root declaration cannot safely model shadowed QName-valued
                # compatibility prefixes. Refuse instead of guessing a binding.
                raise PackageError(f'Namespace prefix rebinding is unsupported: {prefix!r}')
            namespaces[prefix] = uri
    return namespaces


def _compatibility_prefixes(root):
    referenced = set()
    qname_lists = {'ProcessContent', 'PreserveElements', 'PreserveAttributes'}
    for node in root.iter():
        for key, value in node.attrib.items():
            local = key.rsplit('}', 1)[-1]
            is_mc = key.startswith('{' + MC + '}')
            if (is_mc and local in {'Ignorable', 'MustUnderstand'}) or (node.tag.startswith('{' + MC + '}') and local == 'Requires'):
                referenced.update(value.split())
            elif (is_mc and local in qname_lists) or key == '{' + XSI + '}type':
                referenced.update(token.split(':', 1)[0] for token in value.split() if ':' in token)
    return referenced


def _dump(root, source_xml=None, part_name=None):
    """Serialize changed parts without losing OPC defaults or MC QName aliases.

    ET tracks expanded element names, but not namespace prefixes occurring only
    inside Ignorable/Requires strings. Preserve original declarations explicitly;
    do not guess undefined/shadowed aliases. Unchanged slide/note parts never use
    this serializer and remain their original bytes.
    """
    namespaces = _namespace_map(source_xml)
    referenced = _compatibility_prefixes(root)
    missing = referenced - set(namespaces) - {'xml'}
    if missing:
        raise PackageError('Undefined compatibility namespace prefixes: ' + ', '.join(sorted(missing)))
    # Stable names cover new elements even when the original part did not use
    # their namespace. Source prefixes then take precedence.
    for prefix, uri in [('p', P), ('a', A), ('r', R), ('mc', MC)]:
        ET.register_namespace(prefix, uri)
    for prefix, uri in namespaces.items():
        if prefix == 'xml' or re.fullmatch(r'ns[0-9]+', prefix):
            continue  # ET reserves nsN; original aliases are restored below.
        ET.register_namespace(prefix, uri)
    root_namespace = root.tag[1:].split('}', 1)[0] if root.tag.startswith('{') else ''
    if root_namespace in {CT, PK}:
        # Office's OPC parsers require unprefixed Types/Relationships children
        # under the package default namespace, not ns0:Default etc.
        ET.register_namespace('', root_namespace)
    payload = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    emitted = _namespace_map(payload)
    declarations = []
    for prefix, uri in namespaces.items():
        if prefix == 'xml':
            continue
        if prefix in emitted:
            if emitted[prefix] != uri:
                raise PackageError(f'Namespace alias changed during serialization: {prefix!r}')
            continue
        if prefix == '' and root_namespace in {CT, PK}:
            continue  # The mandatory OPC default takes precedence.
        name = 'xmlns' + (':' + prefix if prefix else '')
        declarations.append(' ' + name + '=' + quoteattr(uri))
    if declarations:
        # Inject only missing declarations into the root start tag. Setting
        # xmlns attributes on the ET tree before serialization can duplicate
        # declarations that ET itself generates for used element namespaces.
        start = re.search(br'<(?![!?])[^\s/>]+', payload)
        if start is None:
            raise PackageError(f'Cannot serialize XML root for {part_name}')
        at = start.end()
        payload = payload[:at] + ''.join(declarations).encode('utf-8') + payload[at:]
    # Parse again to catch duplicate/invalid declarations before writing a ZIP.
    xml(payload, part_name or 'serialized XML')
    output_namespaces = _namespace_map(payload)
    if any(output_namespaces.get(prefix) != namespaces.get(prefix) for prefix in referenced if prefix != 'xml'):
        raise PackageError('Compatibility namespace binding verification failed')
    return payload


def _segments(shape):
    """Text slots with fixed paragraph/newline/cell boundaries; retain run styles."""
    groups, separators = [], []

    def paragraph(par):
        chunk = []
        for child in par:
            if child.tag == f'{{{A}}}br':
                groups.append(chunk)
                separators.append('\n')
                chunk = []
            else:
                chunk.extend(child.findall(f'.//{{{A}}}t'))
        groups.append(chunk)

    def body(body_node):
        paragraphs = body_node.findall(f'{{{A}}}p')
        for index, par in enumerate(paragraphs):
            if index:
                separators.append('\n')
            paragraph(par)

    if shape.tag == f'{{{P}}}sp':
        node = shape.find(f'{{{P}}}txBody')
        if node is None:
            raise PackageError('Selected shape has no native text body')
        body(node)
    elif shape.tag == f'{{{P}}}graphicFrame':
        table = shape.find(f'.//{{{A}}}tbl')
        if table is None:
            raise PackageError('Only native text shapes and tables support text replacement')
        for row_index, row in enumerate(table.findall(f'{{{A}}}tr')):
            if row_index:
                separators.append('\n')
            for cell_index, cell in enumerate(row.findall(f'{{{A}}}tc')):
                if cell_index:
                    separators.append('\t')
                body(cell.find(f'{{{A}}}txBody'))
    else:
        raise PackageError('Group/image IDs cannot be edited; select an individual text-shape ID')
    if len(separators) != max(0, len(groups) - 1):
        raise PackageError('Unsupported text topology')
    return groups, separators


def shape_text(shape):
    groups, separators = _segments(shape)
    result = ''
    for index, nodes in enumerate(groups):
        if index:
            result += separators[index - 1]
        result += ''.join(node.text or '' for node in nodes)
    return result


def _replace(root, edit):
    if not isinstance(edit, dict) or set(edit) != {'shape_id', 'before', 'after'}:
        raise PackageError('Each edit requires shape_id, before, after only')
    if any(not isinstance(edit[key], str) for key in edit):
        raise PackageError('shape_id, before and after must be strings')
    matches = []
    for node in root.iter():
        if node.tag not in {f'{{{P}}}sp', f'{{{P}}}graphicFrame', f'{{{P}}}pic', f'{{{P}}}grpSp'}:
            continue
        # Match this object's own cNvPr, never a nested group's first text ID.
        nv = next((child for child in node if child.tag.endswith(('}nvSpPr', '}nvGraphicFramePr', '}nvPicPr', '}nvGrpSpPr'))), None)
        props = nv.find(f'{{{P}}}cNvPr') if nv is not None else None
        if props is not None and props.get('id') == edit['shape_id']:
            matches.append(node)
    if len(matches) != 1:
        raise PackageError(f"Expected one shape ID {edit['shape_id']}; found {len(matches)}")
    shape = matches[0]
    current = shape_text(shape)
    if current != edit['before']:
        raise PackageError(f"Exact before mismatch for shape {edit['shape_id']}")
    groups, separators = _segments(shape)
    pieces = re.split(r'([\n\t])', edit['after'])
    if pieces[1::2] != separators:
        raise PackageError('Text edits cannot change paragraph/line-break/table-cell topology')
    for nodes, value in zip(groups, pieces[::2]):
        if not nodes and value:
            raise PackageError('Cannot add text into an empty native text slot')
        cursor = 0
        for index, node in enumerate(nodes):
            end = cursor + len(node.text or '') if index < len(nodes) - 1 else len(value)
            node.text = value[cursor:end]
            cursor = end
    if shape_text(shape) != edit['after']:
        raise PackageError('Text replacement verification failed')
    return {'shape_id': edit['shape_id'], 'before': current, 'after': edit['after']}


def native_objects(data):
    root = xml(data)
    parents = {child: parent for parent in root.iter() for child in parent}
    tree = root.find(f'{{{P}}}cSld/{{{P}}}spTree')
    objects = []
    for shape in root.iter():
        if shape.tag not in {f'{{{P}}}sp', f'{{{P}}}graphicFrame', f'{{{P}}}pic', f'{{{P}}}grpSp'}:
            continue
        nv = next((child for child in shape if child.tag.endswith(('}nvSpPr', '}nvGraphicFramePr', '}nvPicPr', '}nvGrpSpPr'))), None)
        props = nv.find(f'{{{P}}}cNvPr') if nv is not None else None
        if props is None:
            continue
        try:
            value = shape_text(shape)
        except PackageError:
            value = None
        owner = shape
        while owner in parents and parents[owner] is not tree:
            owner = parents[owner]
        bounds = None
        for xpath in [f'{{{P}}}spPr/{{{A}}}xfrm', f'{{{P}}}grpSpPr/{{{A}}}xfrm', f'{{{P}}}xfrm']:
            transform = owner.find(xpath)
            if transform is not None:
                off, ext = transform.find(f'{{{A}}}off'), transform.find(f'{{{A}}}ext')
                if off is not None and ext is not None:
                    bounds = {**off.attrib, **ext.attrib}
                break
        objects.append({'shape_id': props.get('id'), 'name': props.get('name'),
                        'kind': shape.tag.rsplit('}', 1)[-1], 'text': value,
                        'top_level_bounds_emu': bounds,
                        'native_xml_sha256': sha256(ET.tostring(shape)),
                        'contains_chart': any(node.tag.endswith('}chart') for node in shape.iter()),
                        'contains_table': shape.find(f'.//{{{A}}}tbl') is not None})
    return objects


def reuse(job_path, output_path):
    job_path, output = Path(job_path), Path(output_path)
    receipt_path = output.with_name(output.name + '.receipt.json')
    if output.exists() or receipt_path.exists():
        raise PackageError('Output or receipt already exists; overwrite refused')
    job = json.loads(job_path.read_text(encoding='utf-8'))
    if not isinstance(job, dict) or set(job) != {'reference', 'pages'}:
        raise PackageError('Job requires reference and pages only')
    reference, pages = job['reference'], job['pages']
    if not isinstance(reference, dict) or set(reference) != {'path', 'sha256'}:
        raise PackageError('reference requires path and sha256')
    if not isinstance(reference['path'], str) or not isinstance(reference['sha256'], str) or not re.fullmatch(r'[0-9a-fA-F]{64}', reference['sha256']):
        raise PackageError('Invalid reference path/SHA256')
    source = Path(reference['path'])
    if not source.is_absolute():
        source = job_path.parent / source
    source = source.resolve()
    if output.resolve() == source or receipt_path.resolve() == source:
        raise PackageError('Source overwrite refused')
    source_sha = sha256(source.read_bytes())
    if source_sha != reference['sha256'].lower():
        raise PackageError('Reference SHA256 mismatch')
    pkg = Package(source)
    if not isinstance(pages, list) or not pages:
        raise PackageError('pages must be a nonempty list')
    for page in pages:
        if not isinstance(page, dict) or set(page) - {'source_page', 'text_replacements'} or 'source_page' not in page:
            raise PackageError('Each page requires source_page and optional text_replacements')
        if type(page['source_page']) is not int or not 1 <= page['source_page'] <= len(pkg.slides):
            raise PackageError('source_page must be an existing 1-based logical page')
        if not isinstance(page.get('text_replacements', []), list):
            raise PackageError('text_replacements must be a list')
    files = dict(pkg.parts)
    selected = [pkg.slides[page['source_page'] - 1]['part'] for page in pages]
    clones = [f'ppt/nativeReuse/slides/slide{i}.xml' for i in range(1, len(pages) + 1)]
    if any(name in files for name in clones):
        raise PackageError('Reserved nativeReuse namespace already exists in reference')
    all_source_slides = {row['part'] for row in pkg.slides}
    types = copy.deepcopy(pkg.types)
    ledger, note_count = [], 0

    def add_type(part, old_part):
        ET.SubElement(types, f'{{{CT}}}Override', PartName='/' + part, ContentType=pkg.content_type(old_part))

    def remap_slide(target, current, clone):
        if target == current:
            return clone
        if target in all_source_slides:
            positions = [i for i, value in enumerate(selected) if value == target]
            if len(positions) != 1:
                raise PackageError('Cross-slide link targets an omitted or ambiguous repeated source page')
            return clones[positions[0]]
        return target

    for index, (page, old_part, clone) in enumerate(zip(pages, selected, clones), 1):
        data = pkg.parts[old_part]
        root = xml(data, old_part)
        edits = []
        edited_ids = set()
        for edit in page.get('text_replacements', []):
            if isinstance(edit, dict) and edit.get('shape_id') in edited_ids:
                raise PackageError('Duplicate shape edits in one output page')
            edits.append(_replace(root, edit))
            edited_ids.add(edit['shape_id'])
        files[clone] = _dump(root, data, clone) if edits else data
        add_type(clone, old_part)
        relationships = xml(pkg.parts[relpart(old_part)]) if relpart(old_part) in pkg.parts else ET.Element(f'{{{PK}}}Relationships')
        source_rows = {row['id']: row for row in pkg.relationships(old_part)}
        for entry in relationships:
            row = source_rows[entry.get('Id')]
            if row['external']:
                continue
            target = row['target']
            if row['type'].endswith('/notesSlide'):
                note_count += 1
                new_note = f'ppt/nativeReuse/notes/notes{index}-{note_count}.xml'
                if new_note in files:
                    raise PackageError('Native notes namespace collision')
                files[new_note] = pkg.parts[target]
                add_type(new_note, target)
                note_rels = xml(pkg.parts[relpart(target)]) if relpart(target) in pkg.parts else ET.Element(f'{{{PK}}}Relationships')
                by_id = {item['id']: item for item in pkg.relationships(target)}
                for relation in note_rels:
                    note_row = by_id[relation.get('Id')]
                    if note_row['external']:
                        continue
                    dest = note_row['target']
                    if note_row['type'].endswith('/slide') and dest != old_part:
                        raise PackageError('Unexpected notes slide back-reference')
                    relation.set('Target', '/' + remap_slide(dest, old_part, clone))
                files[relpart(new_note)] = _dump(note_rels, pkg.parts.get(relpart(target)), relpart(new_note))
                target = new_note
            else:
                target = remap_slide(target, old_part, clone)
            entry.set('Target', '/' + target)
        files[relpart(clone)] = _dump(relationships, pkg.parts.get(relpart(old_part)), relpart(clone))
        closure = pkg.closure(old_part)
        _, dependency_manifest = pkg.fingerprint(closure)
        ledger.append({'output_page': index, 'source_page': page['source_page'],
                       'source_part': old_part, 'output_part': clone,
                       'source_slide_sha256': sha256(data), 'output_slide_sha256': sha256(files[clone]),
                       'text_replacements': edits, 'source_native_objects': native_objects(data),
                       'output_native_objects': native_objects(files[clone]),
                       'source_dependency_manifest': dependency_manifest})
    presentation = copy.deepcopy(pkg.presentation)
    listing = presentation.find(f'{{{P}}}sldIdLst')
    for child in list(listing):
        listing.remove(child)
    rels = xml(files[relpart(pkg.main)])
    for row in list(rels):
        if row.get('Type', '').endswith('/slide'):
            rels.remove(row)
    used_ids = {row.get('Id') for row in rels}
    for i, clone in enumerate(clones, 1):
        rid = f'rIdNativeReuse{i}'
        if rid in used_ids:
            raise PackageError('Presentation relationship ID collision')
        ET.SubElement(rels, f'{{{PK}}}Relationship', Id=rid, Type=R + '/slide', Target='/' + clone)
        ET.SubElement(listing, f'{{{P}}}sldId', {'id': str(255 + i), f'{{{R}}}id': rid})
    # Deck-scoped navigation must not retain invalid links to omitted pages.
    removed_navigation = []
    for parent in list(presentation.iter()):
        for child in list(parent):
            if child.tag.rsplit('}', 1)[-1] in {'custShowLst', 'sectionLst'}:
                parent.remove(child)
                removed_navigation.append(child.tag.rsplit('}', 1)[-1])
    files[pkg.main] = _dump(presentation, pkg.parts[pkg.main], pkg.main)
    files[relpart(pkg.main)] = _dump(rels, pkg.parts[relpart(pkg.main)], relpart(pkg.main))
    # Source globals are retained byte-for-byte, except the app's truthful counts.
    for name in files:
        if name == 'docProps/app.xml':
            app = xml(files[name])
            for child in list(app):
                local = child.tag.rsplit('}', 1)[-1]
                if local == 'Slides':
                    child.text = str(len(pages))
                elif local == 'Notes':
                    child.text = str(note_count)
                elif local == 'HiddenSlides':
                    child.text = str(sum(xml(files[part]).get('show') == '0' for part in clones))
                elif local in {'HeadingPairs', 'TitlesOfParts'}:
                    app.remove(child)
            files[name] = _dump(app, pkg.parts[name], name)
    # Follow the live package graph, including chart workbooks and notes masters.
    seen, queue = set(), ['']
    while queue:
        part = queue.pop()
        if part:
            seen.add(part)
        rp = relpart(part)
        if rp not in files or rp in seen:
            continue
        seen.add(rp)
        for entry in xml(files[rp]):
            if entry.get('TargetMode') == 'External':
                continue
            target = _scope.resolve(part, entry.get('Target', ''))
            if target not in files:
                raise PackageError(f'Missing cloned relationship target: {target}')
            if target not in seen:
                queue.append(target)
    for part in seen:
        if part in all_source_slides:
            raise PackageError('Unsupported indirect cross-slide dependency would retain a source slide')
    files = {name: data for name, data in files.items() if name in seen}
    for entry in list(types):
        if entry.tag.endswith('Override') and entry.get('PartName', '').lstrip('/') not in files:
            types.remove(entry)
    files['[Content_Types].xml'] = _dump(types, pkg.parts['[Content_Types].xml'], '[Content_Types].xml')
    output.parent.mkdir(parents=True, exist_ok=True)
    created = False
    try:
        with output.open('xb') as handle:
            created = True
            with ZipFile(handle, 'w', ZIP_DEFLATED) as archive:
                for name, data in files.items():
                    archive.writestr(name, data)
        check = Package(output)
        if len(check.slides) != len(pages):
            raise PackageError('Output active slide count mismatch')
        for slide in check.slides:
            check.closure(slide['part'])
        if sha256(source.read_bytes()) != source_sha:
            raise PackageError('Reference changed during operation')
        receipt = {'operation': 'native_prototype_clone_exact_text', 'source_path': str(source),
                   'source_sha256': source_sha, 'source_preserved': True,
                   'output_path': str(output.resolve()), 'output_sha256': sha256(output.read_bytes()),
                   'active_slide_count': len(pages), 'slide_size_preserved': check.size == pkg.size,
                   'package_part_count': len(files), 'pages': ledger,
                   'removed_deck_navigation': removed_navigation,
                   'semantic_quality_pass': False, 'human_semantic_review_required': True,
                   'known_limits': ['Independent excerpt, not whole-deck partial-edit preservation.',
                                    'Native shared master/layout/media/chart/workbook resources remain shared.',
                                    'Exact edits preserve paragraph, cell and run formatting topology.',
                                    'Notes are cloned and slide back-references remapped.',
                                    'Indirect/omitted/ambiguous cross-slide links are rejected.',
                                    'No rendering, visual quality or PowerPoint GUI validation is claimed.']}
        with receipt_path.open('x', encoding='utf-8') as handle:
            json.dump(receipt, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
        return receipt
    except Exception:
        if created:
            output.unlink(missing_ok=True)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--job', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        result = reuse(args.job, args.output)
    except Exception as exc:
        print(json.dumps({'passed': False, 'error': str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({'passed': True, 'output': result['output_path'], 'sha256': result['output_sha256'],
                      'pages': result['active_slide_count'], 'receipt': args.output + '.receipt.json',
                      'human_semantic_review_required': True}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
