"""D1-D4 evidence suite: real host crashes and Docker; deterministic worker outputs."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from environment import run_environment, wait_for
from runner import ROOT, Runner, docker, save


def host(root, job, action, event=None, mode='question', fault=None):
    env = {k: v for k, v in os.environ.items() if not k.startswith(('LANGSMITH_', 'LANGCHAIN_', 'LAB_D_CRASH'))}
    if fault:
        env['LAB_D_CRASH'] = fault
    result = subprocess.run([sys.executable, str(ROOT / 'host.py'), '--root', str(root),
        '--job', job, action, '--event', json.dumps(event), '--mode', mode],
        env=env, capture_output=True, text=True, timeout=45)
    if fault:
        if result.returncode != 86:
            raise RuntimeError(f'fault did not terminate host: {fault}: {result.stderr}')
        return {'crash_exit_code': result.returncode}
    if result.returncode:
        raise RuntimeError(result.stderr)
    return json.loads(result.stdout)


def run(report_dir):
    report_dir = Path(report_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=False)
    runtime = ROOT / '.runtime' / report_dir.name
    runtime.mkdir(parents=True, exist_ok=False)
    runner = Runner(runtime / 'flow')
    checks, cases = {}, {}
    report = {'mode': 'real_langgraph_sqlite_docker_with_fixed_worker',
              'fault_injection': 'host os._exit(86); synthetic human events',
              'model_calls': 0, 'credentials_read': False,
              'versions': {'python': sys.version.split()[0],
                **{p: importlib.metadata.version(p) for p in ['langgraph', 'langgraph-checkpoint', 'langgraph-checkpoint-sqlite']},
                'docker': docker('version', '--format', '{{.Client.Version}} / {{.Server.Version}}').stdout.strip(),
                'worker_image': json.loads(docker('image', 'inspect', 'node:22.22.0-bookworm').stdout)[0]['Id']},
              'checks': checks, 'cases': cases}

    def snapshot(job, action='status', event=None, **kwargs):
        return host(runner.root, job, action, event, **kwargs)

    def release(attempt):
        wait_for(lambda: (runner.output(attempt) / 'launches.jsonl').exists())
        (runner.output(attempt) / 'release').touch()
        wait_for(lambda: runner.observe(attempt)['state'] == 'result')

    def launches(attempt):
        path = runner.output(attempt) / 'launches.jsonl'
        return len(path.read_text().splitlines()) if path.exists() else 0

    try:
        # D1: every call uses a fresh OS process and the same durable checkpoint.
        first = snapshot('journey', 'start')
        a1 = first['values']['attempt']
        wait_for(lambda: launches(a1) == 1)
        cid = runner.record(a1)['cid']
        recovered = snapshot('journey', 'recover')
        checks['D1_restart_waiting_worker'] = (first == recovered and runner.inspect(runner.record(a1))['State']['Running'])
        release(a1)
        waiting = snapshot('journey', 'resume', {'kind': 'poll', 'attempt': a1})
        checks['D1_result_to_human_wait'] = waiting['values']['status'] == 'waiting_human'
        checks['D1_restart_waiting_human'] = snapshot('journey', 'recover') == waiting
        comment = snapshot('journey', 'resume', {'kind': 'comment', 'attempt': a1, 'value': 'hello'})
        bad_answer = snapshot('journey', 'resume', {'kind': 'answer', 'attempt': a1, 'question': 'wrong',
                                                  'value': 'continue', 'continue': True})
        checks['D1_comments_and_wrong_answers_do_not_dispatch'] = (comment['values']['attempt'] == a1
            and bad_answer['values']['status'] == 'waiting_human' and runner.record('journey:2') is None)
        answer = {'kind': 'answer', 'attempt': a1, 'question': 'continue-work', 'value': 'continue', 'continue': True}
        resumed = snapshot('journey', 'resume', answer)
        a2 = resumed['values']['attempt']
        checks['D1_explicit_answer_starts_next_attempt'] = a2 == 'journey:2' and resumed['values']['answer'] == answer
        stale = snapshot('journey', 'resume', {'kind': 'poll', 'attempt': a1, 'result': {'status': 'complete'}})
        checks['D2_old_result_rejected'] = (stale['values']['attempt'] == a2
            and stale['values']['status'] == 'waiting_worker' and stale['values']['rejected'] == 3)
        release(a2)
        complete = snapshot('journey', 'resume', {'kind': 'poll', 'attempt': a2})
        checks['D1_continuation_completed'] = complete['values']['status'] == 'completed' and not complete['next']
        checks['D2_terminal_duplicate_ignored'] = snapshot('journey', 'resume', answer) == complete
        checks['D2_journey_exactly_once'] = launches(a1) == launches(a2) == 1 and runner.record(a1)['cid'] == cid
        cases['journey'] = {'initial': first, 'waiting': waiting, 'comment': comment, 'bad_answer': bad_answer,
                            'resumed': resumed, 'stale': stale, 'completed': complete}

        # D2: terminate the host around actual Docker boundaries, then reenter dispatch.
        for fault in ('before_create', 'after_intent', 'after_create', 'before_start', 'after_start'):
            job = 'crash-' + fault
            crashed = snapshot(job, 'start', mode='complete', fault=fault)
            before = snapshot(job)
            row_before = runner.record(job + ':1')
            restored = snapshot(job, 'recover')
            attempt = job + ':1'
            if fault == 'after_intent':
                checks['D2_' + fault] = restored['values']['status'] == 'interrupted' and launches(attempt) == 0
            else:
                wait_for(lambda: launches(attempt) == 1)
                row = runner.record(attempt)
                runner.ensure(attempt)
                release(attempt)
                runner.ensure(attempt)
                completed = snapshot(job, 'resume', {'kind': 'poll', 'attempt': attempt})
                checks['D2_' + fault] = launches(attempt) == 1 and completed['values']['status'] == 'completed'
                checks['D2_identity_' + fault] = runner.record(attempt)['cid'] == row['cid']
            cases[job] = {'crash': crashed, 'checkpoint_before_recovery': before,
                          'record_before_recovery': row_before, 'recovered': restored, 'launches': launches(attempt)}

        # Two host processes resend the same start request; only one graph dispatch exists.
        with ThreadPoolExecutor(2) as pool:
            duplicate = list(pool.map(lambda _: snapshot('duplicate', 'start', mode='complete'), range(2)))
        wait_for(lambda: launches('duplicate:1') == 1)
        checks['D2_concurrent_duplicate_dispatch'] = duplicate[0] == duplicate[1] and launches('duplicate:1') == 1
        release('duplicate:1')
        snapshot('duplicate', 'resume', {'kind': 'poll', 'attempt': 'duplicate:1'})

        # Missing resources must not be recreated after a confirmed prior launch.
        snapshot('missing', 'start', mode='complete')
        wait_for(lambda: launches('missing:1') == 1)
        missing_row = runner.record('missing:1')
        docker('rm', '-f', missing_row['cid'])
        observation = runner.ensure('missing:1')
        checks['D2_missing_container_not_relaunched'] = observation['state'] == 'unknown' and launches('missing:1') == 1
        cases['missing'] = observation

        # D3: TERM-ignoring parent and child, plus an independently running peer.
        target = snapshot('cancel', 'start', mode='tree')['values']['attempt']
        peer = snapshot('peer', 'start', mode='tree')['values']['attempt']
        wait_for(lambda: all((runner.output(a) / 'heartbeat').exists() for a in (target, peer)))
        top = docker('top', runner.record(target)['cid'], '-eo', 'pid,ppid,comm').stdout
        checks['D3_parent_and_child_observed'] = len(top.strip().splitlines()) >= 3
        cancellation = {'kind': 'cancel', 'attempt': target}
        snapshot('cancel', 'resume', cancellation, fault='before_stop')
        cancelling = snapshot('cancel')
        checks['D3_cancel_saved_before_stop'] = cancelling['values']['status'] == 'cancelling' and runner.inspect(runner.record(target))['State']['Running']
        stopped = snapshot('cancel', 'recover')
        target_count = (runner.output(target) / 'heartbeat').stat().st_size
        peer_count = (runner.output(peer) / 'heartbeat').stat().st_size
        time.sleep(.5)
        checks['D3_target_tree_stopped'] = (stopped['values']['status'] == 'cancelled'
            and not runner.inspect(runner.record(target))['State']['Running']
            and (runner.output(target) / 'heartbeat').stat().st_size == target_count)
        checks['D3_peer_continues'] = (runner.inspect(runner.record(peer))['State']['Running']
            and (runner.output(peer) / 'heartbeat').stat().st_size > peer_count)
        checks['D3_saved_artifact_survives'] = json.loads((runner.output(target) / 'partial.json').read_text())['attempt'] == target
        checks['D3_late_result_cannot_advance_cancelled'] = snapshot('cancel', 'resume', {'kind': 'poll', 'attempt': target}) == stopped
        cases['cancel'] = {'process_tree_before': top, 'cancelling': cancelling, 'stopped': stopped,
                           'target_heartbeat': target_count, 'peer_heartbeat_before': peer_count,
                           'peer_heartbeat_after': (runner.output(peer) / 'heartbeat').stat().st_size}
        snapshot('peer', 'resume', {'kind': 'cancel', 'attempt': peer}, fault='after_stop')
        checks['D3_restart_after_stop'] = snapshot('peer', 'recover')['values']['status'] == 'cancelled'

        snapshot('cancel-missing', 'start', mode='complete')
        docker('rm', '-f', runner.record('cancel-missing:1')['cid'])
        unknown = snapshot('cancel-missing', 'resume', {'kind': 'cancel', 'attempt': 'cancel-missing:1'})
        checks['D3_missing_stop_explicit_unknown'] = unknown['values']['status'] == 'cancel_unknown'
        cases['cancel_missing'] = unknown

        environment = run_environment(runtime / 'environment', report_dir / 'environment')
        save(report_dir / 'environment.json', environment)
        checks['D4_environment'] = environment['passed']
    except BaseException as error:
        report['error'] = {'type': type(error).__name__, 'message': str(error)}
        raise
    finally:
        with runner.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM attempts')]
        report['attempts'] = rows
        report['artifacts'] = {row['id']: runner.collect(row['id'], report_dir / 'artifacts' / row['name']) for row in rows}
        report['removed_containers'] = runner.cleanup()
        checks['cleanup_containers'] = not docker('ps', '-aq', '--filter', 'label=lab.d.owner=' + runner.owner).stdout.strip()
        # This database contains only synthetic workflow data and no authentication.
        for name in ('checkpoints.sqlite', 'attempts.sqlite'):
            if (runner.root / name).exists():
                shutil.copyfile(runner.root / name, report_dir / name)
        shutil.rmtree(runtime)
        checks['cleanup_runtime'] = not runtime.exists()
        report['passed'] = bool(checks) and all(checks.values()) and 'error' not in report
        save(report_dir / 'report.json', report)
        sources = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                   for p in sorted(ROOT.rglob('*')) if p.is_file()
                   and p.parts[len(ROOT.parts)] not in ('.venv', '.runtime', 'results', '__pycache__')
                   and p.suffix in ('.py', '.cjs', '.json', '.toml', '.lock')}
        sources['Dockerfile'] = hashlib.sha256((ROOT / 'Dockerfile').read_bytes()).hexdigest()
        sources['.dockerignore'] = hashlib.sha256((ROOT / '.dockerignore').read_bytes()).hexdigest()
        save(report_dir / 'source-manifest.json', sources)
        print(json.dumps({'report': str(report_dir), 'passed': report['passed'], 'checks': checks}, indent=2))
    return report['passed']


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(0 if run(args.report) else 1)
