import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('production_plan', ROOT / 'scripts/production_plan.py')
P = importlib.util.module_from_spec(spec); spec.loader.exec_module(P)


class PlanTests(unittest.TestCase):
    def test_roles_are_conditional_and_high_is_retained_for_judgment(self):
        job = {'kind': 'partial', 'pages': [17]}
        self.assertEqual(P.plan(job)['workflow_roles'], [3, 2, 1])
        self.assertEqual(P.plan(job)['support_roles'], [])
        job.update(design_defects=['관계가 불명확한 비교 도식의 위계 수정'], new_assets=True, academic_risk=True)
        result = P.plan(job)
        self.assertEqual(result['workflow_roles'], [3, 2, 5, 3, 2, 1])
        self.assertEqual(result['support_roles'], [4])
        self.assertEqual(result['reasoning_effort'], 'high')
        self.assertFalse(result['model_application_verified'])

    def test_mechanical_scope_cannot_hide_semantic_edit(self):
        with self.assertRaises(ValueError):
            P.plan({'kind': 'simple', 'pages': [17], 'change_type': 'narration'})
        self.assertEqual(P.plan({'kind': 'simple', 'pages': [17], 'change_type': 'coordinate'})['workflow_roles'], [3, 1])

    def test_two_failed_fixes_stop_and_bulk_without_pilot_blocks(self):
        with self.assertRaises(ValueError):
            P.plan({'kind': 'partial', 'pages': [17], 'automatic_fix_attempts': 2, 'unresolved_defects': ['overlap']})
        with self.assertRaises(ValueError):
            P.plan({'kind': 'full', 'phase': 'bulk'})

    def test_missing_or_mistyped_full_phase_cannot_bypass_pilot(self):
        for phase in (None, 'bulkk', 'final'):
            with self.assertRaises(ValueError):
                P.plan({'kind': 'full', 'phase': phase})
        with self.assertRaises(ValueError):
            P.plan({'kind': 'full', 'phase': 'pilot', 'pages': list(range(1, 59))})

    def test_pilot_has_to_bind_sources_renders_and_independent_reviews(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            def entry(name):
                p = base / name; p.write_text(name)
                return {'path': name, 'sha256': P.digest(p)}
            job = {'kind': 'full', 'phase': 'bulk', **{k: entry(k) for k in ('prototype', 'manuscript', 'rules')}}
            review = {k + '_sha256': job[k]['sha256'] for k in ('prototype', 'manuscript', 'rules')}
            review['artifact'] = entry('artifact')
            review['pages'] = []
            for page, types in [(1, ['intro', 'case']), (2, ['objectives_contents', 'diagram', 'closing_or_quiz'])]:
                render = entry('render' + str(page)); render['derived_from_sha256'] = review['artifact']['sha256']
                review['pages'].append({'page': page, 'types': types, 'render': render,
                    'reviews': {str(r): {'status': 'passed', 'observation': 'Fixture observation only, not actual educational approval.'} for r in (2, 5)}})
            rp = base / 'review.json'
            def save():
                rp.write_text(json.dumps(review)); job['pilot'] = {'path': rp.name, 'sha256': P.digest(rp)}
            save()
            self.assertEqual(P.plan(job, base)['workflow_roles'], [3, 2, 5, 3, 2, 1])
            review['pages'][0]['reviews'].pop('5'); save()
            with self.assertRaises(ValueError): P.plan(job, base)
            review['pages'][0]['reviews']['5'] = {'status': 'passed', 'observation': 'An actual observation belongs here.'}
            review['prototype_sha256'] = '0' * 64; save()
            with self.assertRaises(ValueError): P.plan(job, base)


if __name__ == '__main__': unittest.main()
