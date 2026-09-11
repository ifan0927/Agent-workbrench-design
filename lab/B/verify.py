"""Offline completion audit against saved runtime evidence and materialized inputs."""

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def audit(report_path):
    r = json.loads(report_path.read_text())
    if r['mode'] != 'real_model':
        raise ValueError('real_model_evidence_required')
    inputs = report_path.parent / (report_path.stem + '-inputs')
    checks = {}
    for label, version in [('a', 'v1'), ('b', 'v2')]:
        folder = inputs / ('snapshot-' + label)
        manifest = json.loads((folder / 'manifest.json').read_text())
        checks['manifest_' + label] = manifest == r['snapshot_' + label] and all(
            (folder / p).is_file() and hashlib.sha256((folder / p).read_bytes()).hexdigest() == digest
            for p, digest in manifest['snapshot_files'].items())
        checks['source_repo_unchanged_' + label] = all(
            digest == manifest['source_files'].get(p) for p, digest in manifest['snapshot_files'].items() if p.startswith('repo/'))
        checks['reference_' + label] = json.loads((folder / 'home/skills/b-selected/references/value.json').read_text()) == {'proof': f'proof-{version}-74931'}
        checks['loaded_sources_' + label] = r['thread_' + label]['instructionSources'] == ['/codex-home/AGENTS.md', '/work/AGENTS.md']
        checks['runtime_config_' + label] = (r['thread_' + label]['model'] == manifest['model_requested']
            and r['thread_' + label]['modelProvider'] == 'openai' and r['thread_' + label]['reasoningEffort'] == 'low'
            and r['discovery_' + label]['effective_config']['web_search'] == 'disabled')
        checks['checkpoint_' + label] = bool(r['checkpoint_' + label]) and all(c['valid'] and c['tool'] == 'lab_checkpoint' for c in r['checkpoint_' + label])
    for label, version in [('a', 'v1'), ('b', 'v2'), ('a_after', 'v1')]:
        t = r['turn_' + label]
        artifact = r['receipt_' + label]['verified_artifact']
        checks['artifact_' + label] = t['status'] == 'completed' and artifact == {
            'common': 'common', 'repo': 'repo', 'layered': 'task', 'version': version,
            'mode': 'mode', 'priority': 'mode', 'task': 'task', 'twin': 'repo-twin', 'proof': f'proof-{version}-74931'}
        checks['execution_' + label] = any(c['proof_script'] and c['status'] == 'completed' and c['exit_code'] == 0 for c in t['commands'])
        checks['no_extra_path_observed_' + label] = not any(c['unselected_read'] or c['extra_read'] for c in t['commands'])
    checks['selected_read'] = all(any(c['selected_skill_read'] and c['exit_code'] == 0 for c in r['turn_' + label]['commands']) for label in ('a', 'b'))
    a, b, again = (r['turn_' + label] for label in ('a', 'b', 'a_after'))
    checks['snapshot_timeline'] = a['started'] < r['source_updated_at'] < a['ended'] < b['started'] < again['started']
    checks['same_running_a_thread'] = a['thread_id'] == again['thread_id'] != b['thread_id']
    checks['a_rescan_stable'] = r['discovery_a']['skills'] == r['discovery_a_after']['skills']
    checks['snapshot_readonly'] = r['readonly_mount_enforced'] and r['snapshot_a_unchanged'] and r['snapshot_a_unchanged_at_update']
    skills = r['discovery_a']['skills']
    checks['capability_sources'] = {s['path'] for s in skills if s['name'] == 'b-twin'} == {
        '/work/.agents/skills/b-twin/SKILL.md', '/codex-home/skills/b-twin/SKILL.md'}
    checks['selection_vs_discovery'] = set(r['snapshot_a']['selected_skills']) < {s['name'] for s in skills} and not any(s['name'] == 'b-unselected' for s in skills)
    checks['missing_dependency'] = 'b_absent' not in r['discovery_a']['mcp_servers'] and any(p['reason'] == 'missing_dependency' and p['dependency'] == 'b_absent' for p in r['discovery_a']['preflight'])
    checks['malformed_warning'] = any(e['path'].endswith('/b-invalid/SKILL.md') and e['message'] for e in r['discovery_a']['skill_errors'])
    checks['settings_gate'] = r['settings_preflight'] == [] and r['settings_negative'] == {
        'effort': ['reasoning_effort_unavailable'], 'model': ['model_unavailable'], 'tool': ['required_tool_missing']}
    checks['native_profile_error'] = r['negative_config']['missing_permission_profile']['rejected']
    checks['native_model_error'] = r['unknown_model_turn']['status'] == 'failed' and r['unknown_model_turn']['error']['unknown_model_mentioned'] and r['unknown_model_thread']['model'] == 'b-model-does-not-exist'
    checks['credentials'] = r['auth_source_unchanged'] and r['worker_auth_file_absent'] and not r['a_stderr_secret_found'] and not r['b_stderr_secret_found'] and not any(r['turn_' + label]['secret_found'] for label in ('a', 'b', 'a_after'))
    # tokenUsage.total is cumulative per thread; do not count A's first turn twice.
    usage = {key: again['usage'][key] + b['usage'][key] for key in again['usage']}
    return {'report': report_path.name, 'checks': checks, 'passed': all(checks.values()),
            'usage_known_thread_totals': usage, 'unknown_model_usage': r['unknown_model_turn']['usage']}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('report', nargs='?', type=Path, default=ROOT / 'results/live.json')
    args = parser.parse_args()
    result = audit(args.report)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
