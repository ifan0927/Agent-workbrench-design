"""Behavioral tests of snapshot isolation and fail-closed capability checks."""

import json
import shutil
from pathlib import Path
import tempfile
import unittest

from fixtures import sources, snapshot, file_map, preflight, settings_errors


class ConfigurationTests(unittest.TestCase):
    def test_updates_do_not_change_running_snapshot_or_copy_unselected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, a, b = (root / name for name in ('source', 'a', 'b'))
            sources(src, 'v1')
            manifest = snapshot(src, a, 'synthetic-model')
            before = file_map(a)
            sources(src, 'v2')
            snapshot(src, b, 'synthetic-model')
            self.assertEqual(file_map(a), before)
            self.assertNotEqual((a / 'home/AGENTS.md').read_text(), (b / 'home/AGENTS.md').read_text())
            self.assertEqual(json.loads((a / 'home/skills/b-selected/references/value.json').read_text())['proof'], 'proof-v1-74931')
            self.assertFalse((a / 'home/skills/b-unselected').exists())
            self.assertEqual(manifest['snapshot_files']['repo/AGENTS.md'], manifest['source_files']['repo/AGENTS.md'])
            with self.assertRaisesRegex(ValueError, 'snapshot_exists'):
                snapshot(src, a, 'synthetic-model')

    def test_catalog_and_required_tools_gate_before_model_work(self):
        catalog = [{'model': 'model', 'supportedReasoningEfforts': [{'reasoningEffort': 'low'}]}]
        tools = [{'name': 'checkpoint'}]
        self.assertEqual(settings_errors('model', 'low', catalog, tools, ['checkpoint']), [])
        self.assertEqual(settings_errors('missing', 'low', catalog, tools, []), ['model_unavailable'])
        self.assertEqual(settings_errors('model', 'arbitrary', catalog, tools, []), ['reasoning_effort_unavailable'])
        self.assertEqual(settings_errors('model', 'low', catalog, [], ['checkpoint']), ['required_tool_missing'])

    def test_audit_rejects_unrelated_model_failure_and_snapshot_tampering(self):
        from verify import audit, ROOT
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            report = json.loads((ROOT / 'results/live.json').read_text())
            shutil.copytree(ROOT / 'results/live-inputs', folder / 'live-inputs')
            path = folder / 'live.json'
            path.write_text(json.dumps(report))
            self.assertTrue(audit(path)['passed'])
            report['unknown_model_turn']['error']['unknown_model_mentioned'] = False
            path.write_text(json.dumps(report))
            self.assertFalse(audit(path)['passed'])
            report['unknown_model_turn']['error']['unknown_model_mentioned'] = True
            path.write_text(json.dumps(report))
            (folder / 'live-inputs/snapshot-a/home/skills/b-selected/references/value.json').write_text('{"proof":"changed"}')
            self.assertFalse(audit(path)['passed'])

    def test_reject_symlink_to_mutable_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sources(root / 'src', 'v1')
            (root / 'src/library/link').symlink_to(root / 'src/library/b-selected', target_is_directory=True)
            with self.assertRaisesRegex(ValueError, 'source_symlink'):
                snapshot(root / 'src', root / 'out', 'synthetic-model')

    def test_missing_ambiguous_disabled_and_dependency_are_not_ready(self):
        skills = [{'name': 'twin', 'path': '/one', 'enabled': True},
                  {'name': 'twin', 'path': '/two', 'enabled': True},
                  {'name': 'disabled', 'path': '/disabled', 'enabled': False},
                  {'name': 'needs-mcp', 'path': '/needs', 'enabled': True,
                   'dependencies': {'tools': [{'type': 'mcp', 'value': 'absent'}]}}]
        issues = preflight(skills, ['twin', 'disabled', 'missing', 'needs-mcp'])
        self.assertEqual([p['reason'] for p in issues], ['ambiguous', 'missing', 'missing', 'missing_dependency'])
        self.assertEqual(preflight(skills, ['needs-mcp'], ['absent']), [])


if __name__ == '__main__':
    unittest.main()
