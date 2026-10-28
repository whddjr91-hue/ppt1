"""Resolve bounded work and validate pilot evidence; never grade teaching quality."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bound(entry, base):
    p = Path(entry['path'])
    p = p if p.is_absolute() else base / p
    if digest(p) != entry['sha256']:
        raise ValueError('Evidence changed: ' + str(p))
    return p


def plan(job, base=ROOT):
    policy = json.loads((ROOT / 'prototype-policy.json').read_text())
    execution = policy['execution_policy']
    if policy['workflow_roles'] != execution['full']:
        raise ValueError('Legacy full workflow alias conflicts with execution policy')
    kind = job['kind']
    if kind not in ('simple', 'partial', 'full'):
        raise ValueError('Unknown task kind')
    if kind == 'full' and job.get('phase') not in ('pilot', 'bulk'):
        raise ValueError('Full creation requires explicit pilot or bulk phase')
    pages = job.get('pages', [])
    if kind != 'full' and (not pages or any(type(p) is not int or p < 1 for p in pages)):
        raise ValueError('Explicit target pages required')
    if kind == 'full' and job['phase'] == 'pilot' and (not 2 <= len(set(pages)) <= 5 or any(type(p) is not int or p < 1 for p in pages)):
        raise ValueError('Pilot must be bounded to 2-5 representative pages')
    # A semantic, source, or layout redesign is never a mechanical edit.
    if kind == 'simple' and job.get('change_type') not in ('typo', 'sync_number', 'coordinate'):
        raise ValueError('Use partial for meaning, design, or narration changes')
    if job.get('automatic_fix_attempts', 0) >= policy['max_automatic_fix_attempts'] and job.get('unresolved_defects'):
        raise ValueError('Two fixes exhausted: report cause before further execution')
    workflow = execution['partial_with_design' if kind == 'partial' and job.get('design_defects') else kind]
    if job.get('phase') == 'bulk':
        if kind != 'full':
            raise ValueError('Bulk must be a full lesson task')
        evidence = job.get('pilot')
        if not evidence:
            raise ValueError('Reviewed representative pages required before bulk')
        # Evidence is read, not a caller-supplied passed boolean.
        review = json.loads(bound(evidence, base).read_text())
        for key in ('prototype', 'manuscript', 'rules'):
            bound(job[key], base)
            if review.get(key + '_sha256') != job[key]['sha256']:
                raise ValueError('Pilot belongs to different ' + key)
        bound(review['artifact'], base)
        rows = review.get('pages', [])
        if len({r['page'] for r in rows}) < 2:
            raise ValueError('At least two representative pages required')
        required = {'intro', 'objectives_contents', 'diagram', 'case', 'closing_or_quiz'}
        # Multiple roles may share a representative page; absence must be justified.
        covered = {t for r in rows for t in r.get('types', [])}
        omitted = review.get('not_applicable', {})
        if any(t not in covered and len(omitted.get(t, '')) < 12 for t in required):
            raise ValueError('Pilot role coverage or justified absence missing')
        for r in rows:
            bound(r['render'], base)
            if r['render'].get('derived_from_sha256') != review['artifact']['sha256']:
                raise ValueError('Pilot render belongs to another artifact')
            for role in ('2', '5'):
                observation = r.get('reviews', {}).get(role, {})
                if observation.get('status') != 'passed' or len(observation.get('observation', '')) < 12:
                    raise ValueError('Independent semantic/design pilot review missing')
        if review.get('unresolved_defects') or review.get('user_rejected'):
            raise ValueError('Pilot has unresolved/rejected quality')
    high = bool(job.get('complex_instructional_judgment') or job.get('academic_risk') or job.get('final_quality_decision'))
    return {'kind': kind, 'pages': sorted(set(pages)), 'workflow_roles': workflow,
            'support_roles': [4] if job.get('new_assets') or job.get('unresolved_rights') else [],
            'model': 'gpt-6.1-sol', 'reasoning_effort': 'high' if high else 'medium',
            'model_application_verified': False,
            'role_routing': {
                '1': 'high' if job.get('final_quality_decision') or job.get('complex_instructional_judgment') else 'medium',
                '2': 'high' if job.get('academic_risk') or job.get('complex_instructional_judgment') else 'medium',
                '3': 'high' if job.get('complex_instructional_judgment') else 'medium',
                '4': 'high' if job.get('academic_risk') else 'medium',
                '5': 'high' if job.get('complex_visual_judgment') else 'medium'},
            'local_first': ['extract', 'sync', 'geometry', 'hash', 'render', 'package'],
            'review_scope': 'changed_and_dependency_affected_pages' if kind != 'full' else 'full_with_bound_prior_evidence',
            'educational_quality_verified': False, 'user_acceptance_verified': False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('job')
    a = p.parse_args()
    try:
        path = Path(a.job).resolve()
        print(json.dumps(plan(json.loads(path.read_text()), path.parent), ensure_ascii=False, indent=2))
    except (ValueError, KeyError, OSError, TypeError) as e:
        print(json.dumps({'execution_allowed': False, 'error': str(e)}, ensure_ascii=False))
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
