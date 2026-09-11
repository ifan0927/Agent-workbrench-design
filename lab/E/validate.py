"""Inject bounded experimental events into the real LangGraph/Codex mainline."""
import json
import os
from pathlib import Path
import subprocess
import time
from environment import ROOT, COMMIT, save, source_state, SOURCE
from runner import Runner

PYTHON = str(ROOT.parent / 'D/.venv/bin/python')
OUT = ROOT / 'results/live'


def host(action, event=None, crash=None, timeout=1350, job='main', seed=None):
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR') if k in os.environ}
    if crash: env['E_CRASH'] = crash
    p = subprocess.run([PYTHON, str(ROOT / 'host.py'), '--root', str(OUT), '--job', job, action, '--event', json.dumps(event), '--seed', json.dumps(seed)], env=env, capture_output=True, timeout=timeout)
    if p.returncode in (86, 87): return {'crashed': p.returncode}
    if p.returncode:
        (OUT / 'host-error.log').write_bytes(p.stderr)
        raise RuntimeError('host_failed:' + str(p.returncode))
    return json.loads(p.stdout)


def wait(runner, attempt):
    end = time.time() + 310
    while time.time() < end:
        if runner.observe(attempt)['state'] != 'running': return
        time.sleep(1)
    runner.stop(attempt)
    raise RuntimeError('turn_deadline')


def main():
    OUT.mkdir()
    runner = Runner(OUT)
    before = source_state(SOURCE)
    report = {'E1': 'not-run', 'E2': 'not-run', 'E3': 'not-run', 'E4': 'not-run', 'E5': 'not-run', 'E6': 'not-run'}
    save(OUT / 'report.json', report)
    try:
        assert json.loads((ROOT / 'results/e0-corrected/report.json').read_text())['status'] == 'pass'
        state = host('start')
        wait(runner, 'main:question')
        state = host('resume', {'kind': 'poll', 'attempt': 'main:question'})
        assert state['values']['status'] == 'waiting_answer'
        q = state['values']['question_id']
        state = host('resume', {'kind': 'comment', 'value': '請繼續'})
        assert state['values']['status'] == 'waiting_answer'
        answer = {'actor': 'experiment-fixture', 'kind': 'answer', 'question_id': q, 'revision': 0, 'base': COMMIT, 'continue': True, 'value': json.loads((ROOT / 'inputs/controller.json').read_text())['answer']}
        state = host('resume', {**answer, 'question_id': 'wrong-binding'})
        assert state['values']['status'] == 'waiting_answer'
        with runner.db() as db: assert db.execute('SELECT count(*) FROM dispatches').fetchone()[0] == 1
        report['answer_rejections'] = 2
        state = host('resume', answer, crash='running')
        assert state.get('crashed') == 86
        state = host('recover')
        assert state['values']['attempt'] == 'main:coding'
        wait(runner, 'main:coding')
        state = host('resume', {'kind': 'poll', 'attempt': 'main:coding'}, crash='saved')
        assert state.get('crashed') == 87
        state = host('resume', {'kind': 'poll', 'attempt': 'main:coding'})
        if state['values']['status'] == 'verification_failed':
            report['E1'] = 'fail'
            report['verification'] = state['values']['verification_path']
            raise RuntimeError('candidate_verification_failed')
        assert state['values']['attempt'] == 'main:review'
        state = host('resume', {'kind': 'poll', 'attempt': 'main:coding'})
        assert state['values']['attempt'] == 'main:review'
        wait(runner, 'main:review')
        state = host('resume', {'kind': 'poll', 'attempt': 'main:review'})
        report['E1'] = 'pass' if state['values']['status'] == 'completed' else 'fail'
        question = json.loads((runner.paths('main:question') / 'state/thread.json').read_text())
        coding = json.loads((runner.paths('main:coding') / 'state/thread.json').read_text())
        report['E2'] = 'pass' if question['thread']['id'] == coding['thread']['id'] and coding['thread'].get('restoredTurns', 0) >= 1 else 'fail'
        with runner.db() as db:
            counts = {r['attempt']: r['n'] for r in db.execute('SELECT attempt,count(*) n FROM dispatches GROUP BY attempt')}
            collections = [json.loads(r['data']) for r in db.execute("SELECT data FROM events WHERE kind='result_collected'")]
        report['E3'] = 'pass' if counts.get('main:coding') == 1 and sum(r['attempt'] == 'main:coding' for r in collections) == 1 else 'fail'
        report['state'] = state['values']
        report['dispatch_counts'] = counts
    except Exception as e:
        report['error'] = str(e)
    finally:
        runner.cleanup()
        report['source_unchanged'] = before == source_state(SOURCE)
        with runner.db() as db: report['turn_starts'] = db.execute('SELECT count(*) FROM dispatches').fetchone()[0]
        save(OUT / 'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k != 'state'}, ensure_ascii=False))


if __name__ == '__main__': main()
