#!/usr/bin/env python3
"""Reuse explicitly supplied analysis only for identical inputs and rules.

This is a byte cache, not an analysis, quality review, or incremental parser.
Inputs and cache contents may be confidential; use a private cache directory.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import tempfile

SCHEMA = 1


def paragraph_delta(before, after):
    """Compare approved structured extraction, including memo/speaker metadata.

    This does not extract HWP, decide deletions, or approve narration. Every
    manuscript paragraph must have a stable ID and an explicit page map.
    """
    def rows(manifest):
        result = {}
        for row in manifest['paragraphs']:
            key = row['id']
            if not isinstance(key, str) or not key or key in result:
                raise ValueError('Missing or duplicate paragraph ID')
            if key not in manifest['page_map']:
                raise ValueError('Missing paragraph page mapping')
            result[key] = row
        return result
    old, new = rows(before), rows(after)
    same_rules = before['rules_sha256'] == after['rules_sha256']
    changed = sorted(k for k in old.keys() | new.keys() if not same_rules or old.get(k) != new.get(k) or before['page_map'].get(k) != after['page_map'].get(k))
    pages = {p for m in (before, after) for k in changed for p in m['page_map'].get(k, [])}
    return {'changed_paragraph_ids': changed, 'affected_pages': sorted(pages),
            'reusable_paragraph_ids': sorted(old.keys() & new.keys() - set(changed)),
            'source_hash_changed': before['source_sha256'] != after['source_sha256'],
            'educational_quality_verified': False}


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def cache_key(inputs, rules):
    # Order and labels matter; hash the bytes of every dependency including rules.
    return {'schema': SCHEMA, 'inputs': [digest(p) for p in inputs],
            'rules': [digest(p) for p in rules]}


def key_id(key):
    return hashlib.sha256(json.dumps(key, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def put(cache_dir, key, payload):
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    data = Path(payload).read_bytes()
    record = {'key': key, 'payload_sha256': hashlib.sha256(data).hexdigest(),
              'payload_hex': data.hex(), 'educational_quality_verified': False}
    target = directory / (key_id(key) + '.json')
    fd, tmp = tempfile.mkstemp(prefix='.cache-', dir=directory)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(record, f, ensure_ascii=False)
        os.replace(tmp, target)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    return target


def get(cache_dir, key):
    path = Path(cache_dir) / (key_id(key) + '.json')
    if not path.is_file(): return None
    try:
        record = json.loads(path.read_text(encoding='utf-8'))
        data = bytes.fromhex(record['payload_hex'])
        if record['key'] != key or hashlib.sha256(data).hexdigest() != record['payload_sha256']:
            return None
        return data
    except (ValueError, KeyError, TypeError, OSError):
        return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('put', 'get'))
    parser.add_argument('--cache-dir', required=True)
    parser.add_argument('--input', action='append', required=True, help='Repeat for every relevant source/artifact')
    parser.add_argument('--rule', action='append', required=True, help='Repeat for every relevant rule/tool version')
    parser.add_argument('--payload', help='Analysis to store; required for put')
    parser.add_argument('--output', help='Output path for get; existing files are not overwritten')
    args = parser.parse_args()
    key = cache_key(args.input, args.rule)
    if args.action == 'put':
        if not args.payload: parser.error('--payload is required for put')
        print(put(args.cache_dir, key, args.payload))
    else:
        if not args.output: parser.error('--output is required for get')
        data = get(args.cache_dir, key)
        if data is None:
            print('CACHE_MISS')
            return 1
        with open(args.output, 'xb') as f: f.write(data)
        print('CACHE_HIT: bytes restored; semantic quality is not verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
