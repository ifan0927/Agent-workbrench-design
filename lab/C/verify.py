"""Audit saved evidence and reconstruct bundles independently of live workers."""

import argparse
import json
from pathlib import Path
import tempfile

from core import answer_transition, collect, digest, encoded, evidence_gate, git, restore
from fixtures import ORACLE, REQUIREMENT

ROOT = Path(__file__).resolve().parent


def audit(folder):
    def read(name):
        return json.loads((folder / name).read_text())

    report = read('report.json')
    tests = json.loads((ROOT / 'results/tests.json').read_text())
    checks = {'simulation_suite': tests['passed'] and tests['tests'] >= 10,
              'real_mode': report['mode'] == 'real_containers_and_model'}
    sources = read('source-manifest.json')
    checks['source_matches_execution'] = all(digest((ROOT.parent / p).read_bytes()) == h for p, h in sources.items())
    if report.get('reused_from'):
        source = folder.parent / report['reused_from']
        checks['inherited_artifacts_unchanged'] = all(digest((folder / p).read_bytes()) == h for p, h in report['inherited_artifacts'].items())
        checks['inherited_provenance'] = read('inherited-source-manifest.json') == json.loads((source / 'source-manifest.json').read_text())
        checks['inherited_turns_match_source'] = all((folder / p).read_bytes() == (source / p).read_bytes()
            for p in ('question-turn.json', 'implementation-turn.json', 'candidate.bundle', 'candidate.json'))
    checks['recorded_runtime_checks'] = report['passed'] and bool(report['checks']) and all(report['checks'].values())
    initial = read('initial/binding.json')
    binding = read('candidate.json')
    revised = read('revised.json')
    req = read('implementation-input/requirement.json')
    checks['fixed_requirement'] = (read('initial/requirement.json') == REQUIREMENT
        and req == {**REQUIREMENT, 'answer': {'question_id': 'empty-tags', 'value': 'discard'}}
        and digest(encoded(req)) == binding['requirement_sha256'] == revised['requirement_sha256'])
    checks['initial_bundle_unchanged'] = digest((folder / 'implementation-input/base.bundle').read_bytes()) == initial['bundle_sha256']
    question, development, review_turn = [read(n + '-turn.json') for n in ('question', 'implementation', 'review')]
    checks['three_real_completed_turns'] = all(t['status'] == 'completed' and t['usage']['totalTokens'] > 0 and t['commands']
        and t['model'] == report['model'] and t['reasoning_effort'] == 'low' for t in (question, development, review_turn))
    checks['independent_sessions'] = len({t['thread_id'] for t in (question, development, review_turn)}) == 3
    workers = report['workers']
    checks['separate_removed_containers'] = len({w['container'] for w in workers.values()}) == 3 and all(w['removed'] for w in workers.values())
    waiting, comment, ready = read('waiting.json'), read('after-comment.json'), read('implementation-input/handoff.json')
    checks['saved_question_and_partial_report'] = (waiting['question'] == question['output']['question']
        and read('partial-report.json') == question['output'] and question['output']['status'] == 'waiting')
    comment_state, comment_dispatch = answer_transition(waiting, comment['events'][-1])
    ready_state, answer_dispatch = answer_transition(comment, ready['answer'])
    checks['replayed_answer_transitions'] = comment_state == comment and not comment_dispatch and ready_state == ready and answer_dispatch
    checks['lost_session_fallback'] = report['checks']['lost_session_resume_rejected'] and waiting['session_id'] == question['thread_id'] != development['thread_id']
    test, review, new_test = read('test.json'), read('review.json'), read('revised-test.json')
    checks['review_only_allowed_inputs'] = {p.name for p in (folder / 'review-input').iterdir()} == {'requirement.json', 'candidate.json', 'test.json', 'verify.cjs'}
    checks['review_matches_saved_inputs'] = read('review-input/requirement.json') == req and read('review-input/candidate.json') == binding and read('review-input/test.json') == test
    checks['review_requirement_bytes_match_hash'] = digest((folder / 'review-input/requirement.json').read_bytes()) == binding['requirement_sha256']
    checks['independent_oracle_fixed'] = all((folder / name / 'verify.cjs').read_text() == ORACLE for name in ('implementation-input', 'review-input')) and test['execution']['oracle_sha256'] == digest(ORACLE.encode())
    checks['review_result_bound'] = (review['result'] == review_turn['output'] and review['thread_id'] == review_turn['thread_id']
        and review['result']['candidate'] == binding['commit'] and review['result']['requirement_sha256'] == binding['requirement_sha256']
        and review['result']['verdict'] == 'pass' and not any(f['blocking'] for f in review['result']['findings']))
    checks['original_evidence_passes'] = evidence_gate(binding, [test, review])['passed']
    stale = read('stale-evidence.json')
    checks['revised_evidence_rejected'] = (binding['commit'] != revised['commit'] and binding['tree'] != revised['tree']
        and stale['old_only'] == evidence_gate(revised, [test, review]) == {'passed': False, 'gaps': ['missing_current_test', 'missing_current_review']}
        and stale['new_test_old_review'] == evidence_gate(revised, [new_test, review]) == {'passed': False, 'gaps': ['missing_current_review']})
    with tempfile.TemporaryDirectory() as tmp:
        original, correction = Path(tmp) / 'original', Path(tmp) / 'correction'
        restore(folder / 'candidate.bundle', original, binding)
        restore(folder / 'revised.bundle', correction, revised)
        checks['bundle_rebuild_with_base_history'] = git(original, 'rev-parse', 'HEAD^') == initial['commit']
        checks['added_file_and_scope'] = (set(git(original, 'diff', '--name-only', initial['commit'], binding['commit']).splitlines()) == {'tags.cjs', 'usage.md'}
            and (original / 'usage.md').is_file() and git(original, 'show', '--format=', '--name-status', binding['commit']).splitlines() == ['M\ttags.cjs', 'A\tusage.md'])
        checks['collection_reproduced'] = collect(original, json.dumps(development['output']), workers['implementation']['process_exit_code'], ['tags.cjs', 'usage.md']) == read('collection.json')
        checks['revised_is_child'] = git(correction, 'rev-parse', 'HEAD^') == binding['commit']
    checks['separate_human_decisions'] = read('collection.json')['user_adoption'] == 'undecided' and read('collection.json')['next_authorization'] is None
    usage = {k: sum(t['usage'][k] for t in (question, development, review_turn)) for k in development['usage']}
    checks['usage_accounting'] = usage == report['usage_total']
    checks['new_usage_accounting'] = report['usage_this_run'] == (review_turn['usage'] if report.get('reused_from') else usage)
    return {'mode': 'offline_saved_evidence_audit', 'run': folder.name, 'passed': all(checks.values()), 'checks': checks, 'usage_total': usage}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', nargs='?', type=Path, default=ROOT / 'results/live-validated')
    args = parser.parse_args()
    result = audit(args.folder.resolve())
    (args.folder / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
