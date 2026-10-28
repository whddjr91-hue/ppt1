#!/usr/bin/env python3
"""Conservatively identify PPTX slide changes; not a visual or semantic review."""
import argparse
import hashlib
import json
import re
import posixpath
import xml.etree.ElementTree as ET
from zipfile import ZipFile

SLIDE = re.compile(r'^ppt/slides/slide(\d+)\.xml$')
RELS = re.compile(r'^ppt/slides/_rels/slide(\d+)\.xml\.rels$')


def index(path):
    with ZipFile(path) as z:
        if z.testzip() is not None: raise ValueError('invalid ZIP CRC')
        return {n: hashlib.sha256(z.read(n)).hexdigest() for n in z.namelist() if not n.endswith('/')}


def compare(before, after):
    a, b = index(before), index(after)
    changed = sorted(n for n in set(a) | set(b) if a.get(n) != b.get(n))
    slides, shared = set(), []
    for name in changed:
        m = SLIDE.match(name) or RELS.match(name)
        if m: slides.add(int(m.group(1)))
        else: shared.append(name)
    old, new = page_dependencies(before), page_dependencies(after)
    affected = sorted(p for p in set(old) | set(new) if old.get(p) != new.get(p))
    return {'changed_slide_part_numbers': sorted(slides),
            'affected_pages': affected,
            'unchanged_pages': sorted(p for p in set(old) & set(new) if p not in affected),
            'shared_or_other_changed_parts': shared,
            'requires_global_dependency_review': bool(shared),
            'limitations': 'Affected pages use presentation order and transitive internal dependencies. External URLs, renderer/font environment and semantic influence require separate checks. Exact package preservation is not visual approval.'}


def page_dependencies(path):
    """Include notes, media, charts, layouts, themes and embedded fonts conservatively."""
    with ZipFile(path) as z:
        names = set(z.namelist())
        if '_rels/.rels' in names:
            targets = [r.get('Target', '').lstrip('/') for r in ET.fromstring(z.read('_rels/.rels'))
                       if r.get('Type', '').endswith('/officeDocument')]
            if targets != ['ppt/presentation.xml']:
                raise ValueError('Unsupported root presentation relationship: full package inspection required')
        if 'ppt/presentation.xml' not in names:
            # Legacy diagnostic fixtures do not constitute actual page-order proof.
            return {int(SLIDE.match(n).group(1)): {n: hashlib.sha256(z.read(n)).hexdigest()}
                    for n in names if SLIDE.match(n)}
        def relationships(part):
            rp = posixpath.join(posixpath.dirname(part), '_rels', posixpath.basename(part) + '.rels')
            if rp not in names:
                return rp, {}
            rels = {}
            for r in ET.fromstring(z.read(rp)):
                if r.get('TargetMode') == 'External':
                    continue
                target = r.attrib['Target']
                target = target.lstrip('/') if target.startswith('/') else posixpath.normpath(posixpath.join(posixpath.dirname(part), target))
                if target not in names:
                    raise ValueError('Unresolved relationship: ' + target)
                rels[r.attrib['Id']] = target
            return rp, rels
        _, presentation_rels = relationships('ppt/presentation.xml')
        p = ET.fromstring(z.read('ppt/presentation.xml'))
        ns = {'p': 'http://schemas.openxmlformats.org/presentationml/2006/main'}
        order = [presentation_rels[e.attrib['{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id']]
                 for e in p.findall('p:sldIdLst/p:sldId', ns)]
        # Global presentation data/font changes invalidate every page; do not traverse
        # presentation relationships to every slide from each individual slide.
        globals_ = {n for n in names if n.startswith('ppt/fonts/')}
        globals_ |= {n for n in ('_rels/.rels', '[Content_Types].xml', 'ppt/presentation.xml', 'ppt/presProps.xml', 'ppt/viewProps.xml', 'ppt/tableStyles.xml') if n in names}
        globals_ |= {n for n in presentation_rels.values() if n not in order}
        pages = {}
        for page, slide in enumerate(order, 1):
            pending, seen = [slide, *globals_], set()
            while pending:
                part = pending.pop()
                if part in seen:
                    continue
                seen.add(part)
                rp, rels = relationships(part)
                if rp in names:
                    seen.add(rp)
                if part != 'ppt/presentation.xml':
                    pending.extend(v for v in rels.values() if v not in seen)
            pages[page] = {n: hashlib.sha256(z.read(n)).hexdigest() for n in seen}
        return pages


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before'); p.add_argument('after')
    args = p.parse_args()
    print(json.dumps(compare(args.before, args.after), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
