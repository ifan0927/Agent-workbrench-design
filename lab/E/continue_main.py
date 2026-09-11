"""Continue the mainline after a proven pre-dispatch setup failure."""
import json
from environment import ROOT, SOURCE, source_state, save
from runner import Runner
from validate import host, wait, OUT

runner = Runner(OUT)
report = json.loads((OUT / 'report.json').read_text())
report['preflight_failure'] = report.pop('error', None)
before = source_state(SOURCE)
try:
    runner.recover_undispatched_preflight('main:coding')
    state = host('recover', crash='running')
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
