"""Synthetic tests for E-specific answer binding and restart dispatch safety."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from flow import build
from environment import ROOT, COMMIT
from runner import Runner
from evidence import eligible


class FakeRunner:
    def __init__(self):
        self.registered = {}
        self.events = []
        self.launches = set()
        self.collections = set()
        self.stopped = True

    def register(self, attempt, spec): self.registered.setdefault(attempt, spec)
    def ensure(self, attempt):
        self.launches.add(attempt)
        return {'state': 'existing'}
    def observe(self, attempt): return {'state': 'result'}
    def event(self, kind, data): self.events.append((kind, data))
    def stop(self, attempt): return self.stopped
    def collect(self, attempt):
        self.collections.add(attempt)
        mode = self.registered[attempt]['mode']
        return {'response': {'status': 'waiting', 'question': '略過或阻擋 build？'} if mode == 'question' else {'status': 'completed'},
                'thread': {'thread': {'id': 'same-thread'}}, 'home': '/synthetic/home', 'work': '/synthetic/work'}


class FlowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.runner = FakeRunner()
        self.saver = SqliteSaver.from_conn_string(str(Path(self.tmp.name) / 'checkpoint.sqlite'))
        self.checkpointer = self.saver.__enter__()
        self.graph = build(self.runner, self.checkpointer)
        self.config = {'configurable': {'thread_id': 'test'}}
        self.graph.invoke({'job': 'test'}, self.config, durability='sync')

    def tearDown(self):
        self.saver.__exit__(None, None, None)
        self.tmp.cleanup()

    def waiting(self):
        baseline = json.loads((ROOT / 'results/e0/baseline.json').read_text())
        with patch('environment.source_state', return_value={'files': baseline['files']}):
            self.graph.invoke(Command(resume={'kind': 'poll', 'attempt': 'test:question'}), self.config, durability='sync')
        return self.graph.get_state(self.config).values

    def test_unbound_inputs_never_dispatch_coding(self):
        state = self.waiting()
        answer = {'kind': 'answer', 'question_id': state['question_id'], 'revision': 0, 'base': COMMIT, 'continue': True,
                  'value': json.loads((ROOT / 'inputs/controller.json').read_text())['answer']}
        for event in [{'kind': 'comment'}, {**answer, 'question_id': 'wrong'}, {**answer, 'base': 'wrong'},
                      {**answer, 'revision': 1}, {**answer, 'continue': False}, {**answer, 'value': 'other'}]:
            self.graph.invoke(Command(resume=event), self.config, durability='sync')
            self.assertEqual(self.runner.launches, {'test:question'})
        # Reconstruct the graph from durable state before accepting the bound answer.
        self.graph = build(self.runner, self.checkpointer)
        self.graph.invoke(Command(resume=answer), self.config, durability='sync')
        self.assertEqual(self.runner.launches, {'test:question', 'test:coding'})
        self.assertEqual(self.runner.registered['test:coding']['resume'], 'same-thread')
        self.assertEqual(self.runner.registered['test:coding']['task']['revision'], 1)
        self.assertNotIn('unresolved', self.runner.registered['test:coding']['task'])

    def test_stale_notification_cannot_collect(self):
        self.graph.invoke(Command(resume={'kind': 'poll', 'attempt': 'stale'}), self.config, durability='sync')
        self.assertFalse(self.runner.collections)

    def test_unknown_stop_does_not_resume_session(self):
        self.runner.stopped = False
        self.waiting()
        self.assertEqual(self.graph.get_state(self.config).values['status'], 'stop_unknown')
        self.assertEqual(self.runner.launches, {'test:question'})

    def test_unknown_container_never_relaunches(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as directory:
            runner = Runner(directory)
            runner.register('unknown', {'mode': 'question'})
            with runner.db() as db: db.execute("UPDATE attempts SET phase='dispatch_intent',cid='old'")
            class Missing:
                returncode = 1
            with patch('runner.run', return_value=Missing()) as command:
                self.assertEqual(runner.ensure('unknown')['state'], 'unknown')
                self.assertEqual(command.call_count, 1)
                self.assertEqual(command.call_args.args[:2], ('docker', 'inspect'))

    def test_repair_budget_survives_runner_restart(self):
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as directory:
            runner = Runner(directory)
            runner.register('repair-one', {'mode': 'repair'})
            Runner(directory).register('repair-one', {'mode': 'repair'})
            with self.assertRaisesRegex(RuntimeError, 'repair_limit'):
                Runner(directory).register('repair-two', {'mode': 'repair'})

    def test_new_commit_cannot_reuse_old_test_or_review(self):
        candidate = {'commit': 'new', 'tree': 'new-tree'}
        test = {'status': 'pass', 'candidate': candidate}
        review = {'approved': True, 'commit': 'new', 'requirement_sha256': 'r1'}
        self.assertTrue(eligible(candidate, test, review, 'r1'))
        self.assertFalse(eligible(candidate, {'status': 'pass', 'candidate': {'commit': 'old', 'tree': 'old-tree'}}, review, 'r1'))
        self.assertFalse(eligible(candidate, test, {**review, 'commit': 'old'}, 'r1'))
        self.assertFalse(eligible(candidate, test, review, 'r2'))


if __name__ == '__main__': unittest.main()
