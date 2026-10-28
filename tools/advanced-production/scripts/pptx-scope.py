#!/usr/bin/env python3
"""Fail-closed, part-byte scope audit for an existing PPTX (stdlib only).

This is a structural guard, never an educational/semantic quality approval.
An excerpt/reordered deck is not a partial edit of its source whole deck.
"""
import argparse
import hashlib
import json
import posixpath
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile, BadZipFile

P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
PK = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
A = 'http://schemas.openxmlformats.org/drawingml/2006/main'


class PackageError(ValueError):
    pass


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def xml(data, name='XML'):
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise PackageError(f'Invalid {name}: {exc}') from exc


def relpart(part):
    return posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels') if part else '_rels/.rels'


def resolve(part, target):
    uri = urllib.parse.urlsplit(target)
    if uri.scheme or uri.netloc or uri.query:
        raise PackageError(f'Unsupported internal relationship URI: {target}')
    path = urllib.parse.unquote(uri.path)
    result = posixpath.normpath(path.lstrip('/') if path.startswith('/') else posixpath.join(posixpath.dirname(part), path))
    if result == '..' or result.startswith('../') or '\\' in result:
        raise PackageError(f'Relationship escapes package: {target}')
    return result


def structure(node):
    """Stable parsed representation; preserve meaningful text and XML whitespace."""
    return (node.tag, tuple(sorted(node.attrib.items())), node.text or '',
            tuple(structure(child) for child in node), node.tail or '')


class Package:
    def __init__(self, path):
        self.path = Path(path)
        with ZipFile(self.path) as archive:
            items = [info for info in archive.infolist() if not info.is_dir()]
            names = [info.filename for info in items]
            if len(names) != len(set(names)):
                raise PackageError('Duplicate ZIP part names')
            if any(name.startswith('/') or '\\' in name or posixpath.normpath(name) != name or name.startswith('../') for name in names):
                raise PackageError('Non-canonical ZIP part name')
            self.parts = {info.filename: archive.read(info) for info in items}
        if '[Content_Types].xml' not in self.parts:
            raise PackageError('Missing [Content_Types].xml')
        self.types = xml(self.parts['[Content_Types].xml'], 'content types')
        self.defaults, self.overrides = {}, {}
        for entry in self.types:
            if entry.tag == f'{{{CT}}}Default':
                key = entry.get('Extension', '').lower()
                if key in self.defaults:
                    raise PackageError('Duplicate content-type default')
                self.defaults[key] = entry.get('ContentType')
            elif entry.tag == f'{{{CT}}}Override':
                key = urllib.parse.unquote(entry.get('PartName', '').lstrip('/'))
                if key in self.overrides:
                    raise PackageError('Duplicate content-type override')
                self.overrides[key] = entry.get('ContentType')
            else:
                raise PackageError('Unknown content-type declaration')
        roots = [row for row in self.relationships('') if row['type'].endswith('/officeDocument') and not row['external']]
        if len(roots) != 1:
            raise PackageError('Expected one root officeDocument relationship')
        self.main = roots[0]['target']
        self.presentation = xml(self.parts[self.main], self.main)
        self.presentation_rels = self.relationships(self.main)
        by_id = {row['id']: row for row in self.presentation_rels}
        self.slides = []
        listing = self.presentation.find(f'{{{P}}}sldIdLst')
        if listing is not None:
            for item in listing:
                rid = item.get(f'{{{R}}}id')
                row = by_id.get(rid)
                if row is None or row['external'] or not row['type'].endswith('/slide'):
                    raise PackageError(f'Invalid logical slide relationship: {rid}')
                self.slides.append({'part': row['target'], 'rid': rid, 'id': item.get('id')})
        if not self.slides or len({row['part'] for row in self.slides}) != len(self.slides):
            raise PackageError('Expected nonempty, unique active slide parts')
        size = self.presentation.find(f'{{{P}}}sldSz')
        self.size = tuple(sorted(size.attrib.items())) if size is not None else None

    def content_type(self, part):
        value = self.overrides.get(part, self.defaults.get(posixpath.splitext(part)[1].lstrip('.').lower()))
        if not value:
            raise PackageError(f'Missing effective content type: {part}')
        return value

    def relationships(self, part):
        name = relpart(part)
        if name not in self.parts:
            return []
        root = xml(self.parts[name], name)
        if root.tag != f'{{{PK}}}Relationships':
            raise PackageError(f'Invalid relationship root: {name}')
        rows, ids = [], set()
        for item in root:
            rid, target, kind = item.get('Id'), item.get('Target'), item.get('Type')
            if not rid or not target or not kind or rid in ids:
                raise PackageError(f'Invalid/duplicate relationship: {name}')
            ids.add(rid)
            external = item.get('TargetMode') == 'External'
            resolved = target if external else resolve(part, target)
            if not external and resolved not in self.parts:
                raise PackageError(f'Missing target {resolved} from {name}')
            rows.append({'id': rid, 'type': kind, 'target': resolved, 'raw_target': target,
                         'external': external})
        return rows

    def closure(self, start):
        seen, queue = set(), [start]
        while queue:
            part = queue.pop()
            if part in seen:
                continue
            if part not in self.parts:
                raise PackageError(f'Missing dependency: {part}')
            seen.add(part)
            rp = relpart(part)
            if rp in self.parts:
                seen.add(rp)
            for row in self.relationships(part):
                if not row['external'] and row['target'] not in seen:
                    queue.append(row['target'])
        return seen

    def fingerprint(self, parts):
        manifest = {part: {'sha256': sha256(self.parts[part]), 'content_type': self.content_type(part)}
                    for part in sorted(parts)}
        return sha256(json.dumps(manifest, sort_keys=True).encode()), manifest


def _normalize_main(pkg, allowed):
    root = xml(pkg.parts[pkg.main])
    listing = root.find(f'{{{P}}}sldIdLst')
    if listing is not None:
        for page, child in enumerate(listing, 1):
            if page in allowed:
                child.attrib.clear()
                child.set('allowed-page', str(page))
    return structure(root)


def _normalize_main_rels(pkg, allowed):
    root = xml(pkg.parts[relpart(pkg.main)])
    rids = {row['rid'] for i, row in enumerate(pkg.slides, 1) if i in allowed}
    for row in list(root):
        if row.get('Type', '').endswith('/slide') and row.get('Id') in rids:
            root.remove(row)
    return structure(root)


def _normalize_types(pkg, allowed_parts, all_parts):
    root = xml(pkg.parts['[Content_Types].xml'])
    for entry in list(root):
        if entry.tag.endswith('Override'):
            if urllib.parse.unquote(entry.get('PartName', '').lstrip('/')) in allowed_parts:
                root.remove(entry)
        elif entry.tag.endswith('Default'):
            ext = entry.get('Extension', '').lower()
            users = {name for name in all_parts if posixpath.splitext(name)[1].lstrip('.').lower() == ext}
            if users and users <= allowed_parts:
                root.remove(entry)
    return structure(root)


def compare(before, after, allowed_pages):
    """Compare equal-length whole decks, authorizing only declared logical pages.

    Page ownership includes every reachable dependency and its effective type.
    Reordering existing slide identities, size/count changes and unknown global
    changes are blocked, even if every page was declared. New part identities at
    a declared position may replace that page; they cannot move old pages.
    """
    result = {'passed': False, 'changed_pages': [], 'unexpected_pages': [],
              'semantic_quality_pass': False, 'human_semantic_review_required': True,
              'scope_kind': 'whole_deck_partial_edit', 'errors': []}
    try:
        old, new = Package(before), Package(after)
        allowed = set(allowed_pages)
        if any(type(page) is not int or page < 1 or page > len(old.slides) for page in allowed):
            raise PackageError('allowed_pages must contain existing 1-based logical page integers')
        result.update({'allowed_pages': sorted(allowed), 'before_slide_count': len(old.slides),
                       'after_slide_count': len(new.slides), 'slide_count_changed': len(old.slides) != len(new.slides),
                       'slide_size_changed': old.size != new.size})
        old_parts = [row['part'] for row in old.slides]
        new_parts = [row['part'] for row in new.slides]
        old_ids = [row['id'] for row in old.slides]
        new_ids = [row['id'] for row in new.slides]
        # Old identities that survive must stay at their original logical index.
        moved = any(part in new_parts and new_parts.index(part) != i for i, part in enumerate(old_parts))
        moved_ids = any(sid in new_ids and new_ids.index(sid) != i for i, sid in enumerate(old_ids))
        result['slide_order_changed'] = moved or moved_ids
        old_closures = [old.closure(part) for part in old_parts]
        new_closures = [new.closure(part) for part in new_parts]
        changes = []
        for i in range(max(len(old_closures), len(new_closures))):
            a = old.fingerprint(old_closures[i])[0] if i < len(old_closures) else None
            b = new.fingerprint(new_closures[i])[0] if i < len(new_closures) else None
            if a != b:
                changes.append(i + 1)
        result['changed_pages'] = changes
        result['unexpected_pages'] = [page for page in changes if page not in allowed]
        all_names = set(old.parts) | set(new.parts)
        changed_parts = sorted(name for name in all_names if old.parts.get(name) != new.parts.get(name))
        result['changed_parts'] = changed_parts
        known = set().union(*old_closures, *new_closures)
        allowed_parts = set().union(*(old_closures[i - 1] for i in allowed),
                                    *(new_closures[i - 1] for i in allowed if i <= len(new_closures)))
        special = {'[Content_Types].xml', old.main, new.main, relpart(old.main), relpart(new.main)}
        unknown = [name for name in changed_parts if name not in known and name not in special]
        global_changes = []
        if old.main != new.main or _normalize_main(old, allowed) != _normalize_main(new, allowed):
            global_changes.append('presentation_structure')
        if _normalize_main_rels(old, allowed) != _normalize_main_rels(new, allowed):
            global_changes.append('presentation_relationships')
        if _normalize_types(old, allowed_parts, all_names) != _normalize_types(new, allowed_parts, all_names):
            global_changes.append('content_types')
        result['unknown_global_changes'] = unknown + global_changes
        result['passed'] = not (result['unexpected_pages'] or result['slide_count_changed'] or
                                result['slide_order_changed'] or result['slide_size_changed'] or
                                result['unknown_global_changes'])
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, BadZipFile) as exc:
        result['errors'].append(str(exc))
    return result


analyze_scope = compare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--before', '--baseline', required=True)
    parser.add_argument('--after', '--candidate', required=True)
    parser.add_argument('--pages', '--allow-pages', default='')
    parser.add_argument('--report')
    args = parser.parse_args()
    try:
        pages = [int(page) for page in args.pages.split(',') if page.strip()]
    except ValueError:
        parser.error('--pages expects comma-separated 1-based integers')
    result = compare(args.before, args.after, pages)
    payload = json.dumps(result, ensure_ascii=False, indent=2) + '\n'
    if args.report:
        with Path(args.report).open('x', encoding='utf-8') as handle:
            handle.write(payload)
    print(payload, end='')
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
