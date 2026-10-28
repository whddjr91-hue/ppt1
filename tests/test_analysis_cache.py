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
    def test_paragraph_memo_and_rule_changes_invalidate_affected_pages(self):
        import copy
        old = {'source_sha256': 'a', 'rules_sha256': 'r',
               'paragraphs': [{'id': 'P1', 'text': '본문', 'speaker': '강사', 'memo': ''}, {'id': 'P2', 'text': '사례'}],
               'page_map': {'P1': [17], 'P2': [18, 19]}}
        new = copy.deepcopy(old); new['source_sha256'] = 'b'
        new['paragraphs'][0]['memo'] = '승인된 감수 변경'
        delta = C.paragraph_delta(old, new)
        self.assertEqual(delta['affected_pages'], [17])
        self.assertEqual(delta['reusable_paragraph_ids'], ['P2'])
        new['rules_sha256'] = 'new rules'
        self.assertEqual(C.paragraph_delta(old, new)['affected_pages'], [17, 18, 19])

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
