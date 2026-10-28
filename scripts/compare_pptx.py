#!/usr/bin/env python3
"""Conservatively identify PPTX slide changes; not a visual or semantic review."""
import argparse
import hashlib
import json
import re
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
    return {'changed_slide_part_numbers': sorted(slides),
            'shared_or_other_changed_parts': shared,
            'requires_global_dependency_review': bool(shared),
            'limitations': 'Part numbers are not presentation order; inspect slide ordering and relationships. Shared/other changes require impact review. No rendering, unchanged-page guarantee, or semantic approval is provided.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('before'); p.add_argument('after')
    args = p.parse_args()
    print(json.dumps(compare(args.before, args.after), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
