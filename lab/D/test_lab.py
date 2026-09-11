"""Negative-path tests; Docker responses are simulated and make no daemon calls."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from runner import Runner, save, ROOT


class FailureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.runner = Runner(self.temp.name)
        self.row = self.runner.register('job:1', 'complete')

    def exited(self):
        return {'Id': 'container-id', 'State': {'Running': False, 'Status': 'exited', 'ExitCode': 0}}

    def test_unavailable_docker_is_not_absence(self):
        unavailable = subprocess.CompletedProcess([], 1, '', 'Cannot connect to the Docker daemon')
        with patch('runner.docker', return_value=unavailable) as command:
            with self.assertRaisesRegex(RuntimeError, 'observation unavailable'):
                self.runner.ensure('job:1')
            self.assertEqual(command.call_count, 1)
        self.assertEqual(self.runner.record('job:1')['phase'], 'prepared')

    def test_foreign_container_is_not_adopted_or_stopped(self):
        info = {**self.exited(), 'Config': {'Labels': {'agent-workbench.lab': 'D', 'lab.d.owner': 'someone-else'}}}
        with patch('runner.docker', return_value=subprocess.CompletedProcess([], 0, json.dumps([info]), '')) as command:
            with self.assertRaisesRegex(RuntimeError, 'identity mismatch'):
                self.runner.ensure('job:1')
            self.assertEqual(self.runner.stop('job:1')['state'], 'unknown')
            self.assertTrue(all(call.args[0] == 'inspect' for call in command.call_args_list))

    def test_old_and_malformed_results_are_rejected(self):
        path = self.runner.output('job:1') / 'result.json'
        with patch.object(self.runner, 'inspect', return_value=self.exited()):
            for data in ('{', json.dumps({'attempt': 'old:1', 'status': 'complete', 'question': None, 'value': 42}),
                         json.dumps({'attempt': 'job:1', 'status': 'waiting', 'question': 'continue-work', 'value': 42})):
                path.write_text(data)
                self.assertEqual(self.runner.observe('job:1')['state'], 'invalid_result')

    def test_exited_without_result_never_restarts(self):
        with patch.object(self.runner, 'inspect', return_value=self.exited()), patch('runner.docker') as command:
            self.assertEqual(self.runner.ensure('job:1')['state'], 'exited')
            command.assert_not_called()

    def test_unknown_stop_remains_unknown_and_blocks_launch(self):
        with patch.object(self.runner, 'inspect', side_effect=RuntimeError('observation unavailable')):
            self.assertEqual(self.runner.stop('job:1')['state'], 'unknown')
        with patch('runner.docker') as command:
            self.assertEqual(self.runner.ensure('job:1')['state'], 'cancel_requested')
            command.assert_not_called()

    def test_attempt_input_is_immutable(self):
        with self.assertRaisesRegex(ValueError, 'input changed'):
            self.runner.register('job:1', 'question')


if __name__ == '__main__':
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(FailureTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    save(ROOT / 'results/tests.json', {'mode': 'simulated_docker_negative_paths',
         'tests': result.testsRun, 'passed': result.wasSuccessful(),
         'failures': len(result.failures), 'errors': len(result.errors)})
    raise SystemExit(0 if result.wasSuccessful() else 1)
