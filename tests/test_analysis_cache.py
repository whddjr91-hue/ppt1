import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('analysis_cache', ROOT / 'scripts/analysis_cache.py')
C = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(C)


class CacheTests(unittest.TestCase):
    def test_reuse_only_exact_bytes_and_rules(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source, rules, payload = (root / x for x in ('source', 'rules', 'analysis'))
            source.write_text('원고', encoding='utf-8')
            rules.write_text('v1', encoding='utf-8')
            payload.write_text('actual analysis', encoding='utf-8')
            key = C.cache_key([source], [rules])
            entry = C.put(root / 'cache', key, payload)
            self.assertEqual(C.get(root / 'cache', key), b'actual analysis')
            source.write_text('변경', encoding='utf-8')
            self.assertIsNone(C.get(root / 'cache', C.cache_key([source], [rules])))
            source.write_text('원고', encoding='utf-8')
            rules.write_text('v2', encoding='utf-8')
            self.assertIsNone(C.get(root / 'cache', C.cache_key([source], [rules])))
            record = json.loads(entry.read_text())
            self.assertFalse(record['educational_quality_verified'])
            record['payload_hex'] = b'tampered'.hex()
            entry.write_text(json.dumps(record))
            self.assertIsNone(C.get(root / 'cache', key))


if __name__ == '__main__': unittest.main()
