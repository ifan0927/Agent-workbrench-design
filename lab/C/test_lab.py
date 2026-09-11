"""Behavioral failures and durable handoff tests; no model or Docker required."""

import copy
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from core import answer_transition, candidate, collect, digest, encoded, evidence_gate, git, restore, save
from fixtures import REQUIREMENT, seed

ROOT = Path(__file__).resolve().parent


class LabTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def result(self, **kwargs):
        return {'status': 'complete', 'summary': '已完成', 'artifacts': ['report.md'],
                'question': None, 'incomplete': [], 'side_effects': [], **kwargs}

    def test_c1_success_exit_missing_output(self):
        p = subprocess.run([sys.executable, '-c', 'pass'], capture_output=True)
        r = collect(self.root, json.dumps(self.result()), p.returncode, ['report.md'])
        self.assertEqual(r['execution'], 'completed')
        self.assertEqual(r['delivery'], 'incomplete')
        self.assertIn('missing_required:report.md', r['gaps'])

    def test_c1_invalid_format_keeps_partial_artifact(self):
        (self.root / 'report.md').write_text('可保留的部分研究成果')
        for raw in ('not json', '[]', '{}', '{"status": "complete"}'):
            with self.subTest(raw=raw):
                p = subprocess.run([sys.executable, '-c', 'import sys; print(sys.argv[1])', raw], capture_output=True)
                r = collect(self.root, p.stdout, p.returncode, ['report.md'])
                self.assertEqual(r['delivery'], 'incomplete')
                self.assertIn('invalid_result_format', r['gaps'])
                self.assertEqual(r['artifacts']['report.md'], digest((self.root / 'report.md').read_bytes()))

    def test_c1_partial_and_failed_process_do_not_deliver(self):
        (self.root / 'report.md').write_text('部分成果')
        r = collect(self.root, json.dumps(self.result(status='partial', incomplete=['缺少來源'])), 0, ['report.md', 'source.json'])
        self.assertEqual(r['delivery'], 'incomplete')
        self.assertIn('缺少來源', r['gaps'])
        self.assertIn('missing_required:source.json', r['gaps'])
        self.assertIn('report.md', r['artifacts'])
        r = collect(self.root, json.dumps(self.result()), 1, ['report.md'])
        self.assertEqual(r['delivery'], 'incomplete')

    def test_c1_delivery_is_not_adoption_or_authorization(self):
        (self.root / 'report.md').write_text('成果')
        r = collect(self.root, json.dumps(self.result()), 0, ['report.md'])
        self.assertEqual(r['delivery'], 'complete')
        self.assertEqual(r['user_adoption'], 'undecided')
        self.assertIsNone(r['next_authorization'])

    def test_c1_complete_claim_with_pending_question_is_incomplete(self):
        (self.root / 'report.md').write_text('仍有必要問題')
        r = collect(self.root, json.dumps(self.result(question={'id': 'pending'})), 0, ['report.md'])
        self.assertEqual(r['delivery'], 'incomplete')
        self.assertIn('unanswered_question', r['gaps'])

    def test_c1_symlink_and_traversal_are_not_collected(self):
        (self.root / 'report.md').symlink_to('/etc/hosts')
        r = collect(self.root, json.dumps(self.result(artifacts=['../secret', 'report.md'])), 0, ['report.md'])
        self.assertFalse(r['artifacts'])
        self.assertEqual(r['delivery'], 'incomplete')

    def test_c2_bundle_rebuilds_new_file_and_history_after_deletion(self):
        repo = self.root / 'worker'
        base = seed(repo)
        (repo / 'new.txt').write_text('新增檔案\n')
        with self.assertRaisesRegex(ValueError, 'uncommitted_candidate'):
            candidate(repo, self.root / 'bad.bundle', REQUIREMENT)
        git(repo, 'add', '--', 'new.txt')
        git(repo, 'commit', '-qm', 'Add delivered file')
        bundle = self.root / 'saved.bundle'
        binding = candidate(repo, bundle, REQUIREMENT)
        shutil.rmtree(repo)
        rebuilt = self.root / 'rebuilt'
        restore(bundle, rebuilt, binding)
        self.assertEqual((rebuilt / 'new.txt').read_text(), '新增檔案\n')
        self.assertEqual(git(rebuilt, 'rev-parse', 'HEAD^'), base)
        bundle.write_bytes(bundle.read_bytes() + b'tampered')
        with self.assertRaisesRegex(ValueError, 'bundle_hash_mismatch'):
            restore(bundle, self.root / 'tampered', binding)

    def test_c4_old_tests_and_review_cannot_support_revised_candidate(self):
        old = {'commit': 'a', 'tree': 't', 'bundle_sha256': 'b', 'requirement_sha256': 'r'}
        evidence = [{'kind': kind, 'binding': old, 'passed': True} for kind in ('test', 'review')]
        self.assertTrue(evidence_gate(old, evidence)['passed'])
        for field in old:
            new = {**old, field: 'new'}
            self.assertFalse(evidence_gate(new, evidence)['passed'])
            self.assertEqual(evidence_gate(new, evidence + [{'kind': 'test', 'binding': new, 'passed': True}])['gaps'], ['missing_current_review'])
        evidence[1]['passed'] = False
        self.assertFalse(evidence_gate(old, evidence)['passed'])

    def waiting(self):
        return {'phase': 'waiting', 'question': {'id': 'empty-tags', 'options': ['discard', 'reject']},
                'requirement_sha256': digest(encoded(REQUIREMENT)), 'candidate': 'base', 'events': []}

    def answer(self):
        return {'type': 'answer_and_continue', 'question_id': 'empty-tags', 'candidate': 'base',
                'requirement_sha256': digest(encoded(REQUIREMENT)), 'value': 'discard', 'event_id': 'answer-1'}

    def test_c5_comment_is_saved_but_never_starts_work(self):
        state, dispatch = answer_transition(self.waiting(), {'type': 'comment', 'text': 'discard'})
        self.assertFalse(dispatch)
        self.assertEqual(state['phase'], 'waiting')
        self.assertEqual(len(state['events']), 1)

    def test_c5_answer_survives_new_process_and_duplicate_does_not_restart(self):
        state_path = self.root / 'waiting.json'
        save(state_path, self.waiting())
        p = subprocess.run([sys.executable, '-c',
            'import json,sys; from core import answer_transition; '
            'print(json.dumps(answer_transition(json.load(open(sys.argv[1])), json.loads(sys.argv[2]))))',
            str(state_path), json.dumps(self.answer())], cwd=ROOT, capture_output=True, check=True)
        state, dispatch = json.loads(p.stdout)
        self.assertTrue(dispatch)
        self.assertEqual(state['next_authorization']['event_id'], 'answer-1')
        self.assertFalse(answer_transition(state, self.answer())[1])

    def test_c5_wrong_question_requirement_candidate_or_value_cannot_continue(self):
        for field in ('question_id', 'requirement_sha256', 'candidate', 'value', 'type', 'event_id'):
            event = {**self.answer(), field: ''}
            self.assertFalse(answer_transition(self.waiting(), event)[1], field)


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(LabTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {'mode': 'simulation_real_processes_and_git_no_model', 'tests': result.testsRun,
              'failures': len(result.failures), 'errors': len(result.errors), 'passed': result.wasSuccessful()}
    (ROOT / 'results' / 'tests.json').write_text(json.dumps(report, indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
