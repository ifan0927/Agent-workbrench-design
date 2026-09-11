"""Offline audit of source hashes, actual artifacts, checkpoints, and D4 build evidence."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
from langgraph.checkpoint.sqlite import SqliteSaver
from flow import build
from runner import ROOT, save

EXPECTED = {
    'D1_restart_waiting_worker', 'D1_result_to_human_wait', 'D1_restart_waiting_human',
    'D1_comments_and_wrong_answers_do_not_dispatch', 'D1_explicit_answer_starts_next_attempt',
    'D1_continuation_completed', 'D2_old_result_rejected', 'D2_terminal_duplicate_ignored',
    'D2_journey_exactly_once', 'D2_after_intent', 'D2_concurrent_duplicate_dispatch',
    'D2_missing_container_not_relaunched', 'D3_parent_and_child_observed',
    'D3_cancel_saved_before_stop', 'D3_target_tree_stopped', 'D3_peer_continues',
    'D3_saved_artifact_survives', 'D3_late_result_cannot_advance_cancelled',
    'D3_restart_after_stop', 'D3_missing_stop_explicit_unknown', 'D4_environment',
    'cleanup_containers', 'cleanup_runtime',
} | {'D2_' + prefix + point for prefix in ('', 'identity_')
     for point in ('before_create', 'after_create', 'before_start', 'after_start')}


def audit(folder):
    folder = Path(folder).resolve()
    read = lambda path: json.loads((folder / path).read_text())
    report, manifest = read('report.json'), read('source-manifest.json')
    checks = {'full_required_runtime_checks': set(report['checks']) >= EXPECTED and report['passed']
              and all(report['checks'].values()),
              'sources_unchanged': all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h for p, h in manifest.items()),
              'no_model_or_credentials': report['model_calls'] == 0 and report['credentials_read'] is False}
    tests = json.loads((ROOT / 'results/tests.json').read_text())
    checks['negative_path_tests'] = tests['passed'] and tests['tests'] == 6 and tests['mode'] == 'simulated_docker_negative_paths'
    checks['artifact_hashes'] = all(hashlib.sha256((folder / 'artifacts' / row['name'] / name).read_bytes()).hexdigest() == digest
        for row in report['attempts'] for name, digest in report['artifacts'][row['id']].items())
    counts = {}
    for row in report['attempts']:
        path = folder / 'artifacts' / row['name'] / 'launches.jsonl'
        lines = [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []
        counts[row['id']] = len(lines)
        checks['launch_binding_' + row['id']] = all(line['attempt'] == row['id'] for line in lines)
    checks['actual_launch_counts'] = all(counts[job] == 1 for job in (
        'journey:1', 'journey:2', 'crash-before_create:1', 'crash-after_create:1',
        'crash-before_start:1', 'crash-after_start:1', 'duplicate:1', 'missing:1', 'cancel:1', 'peer:1'))
    checks['ambiguous_intent_zero_launch'] = counts['crash-after_intent:1'] == 0
    journey = report['cases']['journey']
    checks['answer_and_stale_result_binding'] = (journey['waiting']['values']['attempt'] == 'journey:1'
        and journey['resumed']['values']['attempt'] == journey['stale']['values']['attempt'] == 'journey:2'
        and journey['stale']['values']['status'] == 'waiting_worker'
        and journey['completed']['values']['status'] == 'completed')
    cancel = report['cases']['cancel']
    checks['cancel_and_peer_evidence'] = (cancel['cancelling']['values']['status'] == 'cancelling'
        and cancel['stopped']['values']['status'] == 'cancelled'
        and cancel['peer_heartbeat_after'] > cancel['peer_heartbeat_before'])
    with tempfile.TemporaryDirectory() as temp:
        database = Path(temp) / 'checkpoint.sqlite'
        shutil.copyfile(folder / 'checkpoints.sqlite', database)
        with SqliteSaver.from_conn_string(str(database)) as saver:
            graph = build(None, saver)
            for job, status in [('journey', 'completed'), ('cancel', 'cancelled'), ('peer', 'cancelled'),
                                ('cancel-missing', 'cancel_unknown'), ('crash-after_intent', 'interrupted')]:
                snapshot = graph.get_state({'configurable': {'thread_id': job}})
                checks['durable_checkpoint_' + job] = snapshot.values['status'] == status and not snapshot.next
        repo = Path(temp) / 'fixture'
        subprocess.run(['git', '-c', 'advice.detachedHead=false', 'clone', '-q',
                        str(folder / 'environment/fixture.bundle'), str(repo)], check=True)
        env = read('environment.json')
        checks['fixture_bundle_reconstructs_commit'] = subprocess.check_output(
            ['git', '-C', str(repo), 'rev-parse', 'HEAD'], text=True).strip() == env['commit']
        checks['fixture_matches_tested_source'] = all((repo / p).read_bytes() == (ROOT / p).read_bytes()
            for p in manifest if p.startswith('fixture/') or p == 'Dockerfile')
    env = read('environment.json')
    checks['environment_checks'] = env['passed'] and len(env['checks']) == 13 and all(env['checks'].values())
    for index, task in enumerate(env['tasks']):
        checks[f'environment_real_exit_{index}'] = task['state']['Status'] == 'exited' and task['state']['ExitCode'] == 0
        checks[f'environment_test_log_{index}'] = '# pass 2' in (folder / f'environment/test-{index}.txt').read_text()
        checks[f'environment_output_{index}'] = read(f'environment/environment-{index}.json') == {'token': f'dataset-{index}', 'isolated': True}
    checks['environment_overlap'] = max(t['state']['StartedAt'] for t in env['tasks']) < min(t['state']['FinishedAt'] for t in env['tasks'])
    return {'mode': 'offline_evidence_audit', 'passed': all(checks.values()), 'checks': checks}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    result = audit(args.folder)
    save(args.folder / 'audit.json', result)
    print(json.dumps(result, indent=2))
    raise SystemExit(0 if result['passed'] else 1)
