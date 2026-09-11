"""E4 and E5 experiment injections; all model dispatch remains in LangGraph."""
import json
from pathlib import Path
import shutil
import time
from environment import ROOT, COMMIT, run, git, save, digest
from runner import Runner
from validate import OUT, host, wait
from verification import verify
from evidence import eligible


def repair(runner, main_state):
    candidate = main_state['candidate']
    source = runner.runtime / 'injected'
    runner.clone(candidate['bundle'], source, candidate['commit'])
    path = source / 'src/lib/content/news.ts'
    text = path.read_text()
    target = "  const match = date.match("
    assert text.count(target) == 1
    text = text.replace(target, "  // E4 experimental regression, deliberately injected by the host.\n  if (date === '2024-02-29') throw new Error('E4 injected leap-day regression');\n" + target)
    path.write_text(text)
    git(source, 'add', 'src/lib/content/news.ts')
    git(source, 'commit', '-m', 'E4 experiment: deliberately reject a valid leap day')
    commit = git(source, 'rev-parse', 'HEAD')
    bundle = OUT / 'e4-injected.bundle'
    git(source, 'bundle', 'create', str(bundle), 'HEAD')
    injected = {'commit': commit, 'tree': git(source, 'rev-parse', 'HEAD^{tree}'), 'bundle': str(bundle), 'bundle_sha256': digest(bundle)}
    old_review_attempt = 'main:review'
    old_spec = json.loads(runner.row(old_review_attempt)['spec'])
    old_review = {'commit': old_spec['base'], 'requirement_sha256': digest(runner.paths(old_review_attempt) / 'input/task.json'), 'approved': main_state['collected']['response']['approved']}
    old_rejected = not eligible(injected, main_state['verification'], old_review, old_review['requirement_sha256'])
    assert old_rejected
    save(OUT / 'e4-injection.json', {'origin': 'experiment-fixture', 'parent': candidate['commit'], 'candidate': injected,
        'old_evidence_rejected': old_rejected, 'old_review_binding': old_review})
    failed, _ = verify(runner, injected, 'injected', acceptance_only=True)
    assert failed['status'] == 'fail' and failed.get('error') == 'fixed_acceptance_failed'
    task = dict(main_state['task'])
    task['phase'] = '這是 E4 明確標示的實驗錯誤 commit，不是前一模型自然失誤。固定驗收顯示合法 2024-02-29 被拒絕。僅允許一次外層修正，恢復原需求並用相關 lab skill test 驗證，不改既有測試。'
    state = host('start', job='repair', seed={'phase': 'repair', 'task': task, 'base': commit, 'source': str(bundle)})
    wait(runner, 'repair:repair')
    state = host('resume', {'kind': 'poll', 'attempt': 'repair:repair'}, job='repair')
    if state['values']['status'] == 'verification_failed': return {'status': 'fail', 'state': state['values']}
    assert state['values']['attempt'] == 'repair:review'
    wait(runner, 'repair:review')
    state = host('resume', {'kind': 'poll', 'attempt': 'repair:review'}, job='repair')
    result = {'status': 'pass' if state['values']['status'] == 'completed' else 'fail', 'state': state['values']}
    save(OUT / 'e4.json', result)
    return result


def parallel(runner):
    for lane in ('a', 'b'):
        task = {'lane': lane, 'phase': '這是小型真實並行驗證。執行 node /input/barrier.mjs；它會讀本地 API fixture 並等待 controller 放行。必須等待腳本完成後讀 e5-result.json，再回報 status=completed、question=null 與 lane 結果摘要。不要自行建立 /state/release、修改腳本或停止 fixture。不做其他實作或 build。'}
        host('start', job='parallel-' + lane, seed={'phase': 'parallel', 'task': task})
    a, b = 'parallel-a:parallel', 'parallel-b:parallel'
    end = time.time() + 120
    while time.time() < end:
        if all((runner.paths(x) / 'work/e5-partial.json').exists() for x in (a, b)): break
        if any(runner.observe(x)['state'] != 'running' for x in (a, b)): raise RuntimeError('parallel_ended_before_barrier')
        time.sleep(.5)
    assert all((runner.paths(x) / 'work/e5-partial.json').exists() for x in (a, b))
    assert all(runner.observe(x)['state'] == 'running' for x in (a, b))
    overlap = {x: json.loads((runner.paths(x) / 'state/dispatch.json').read_text()) for x in (a, b)}
    before = json.loads((runner.paths(b) / 'work/e5-progress.json').read_text())
    state_a = host('resume', {'kind': 'cancel', 'attempt': a}, job='parallel-a')
    assert state_a['values']['status'] == 'cancelled'
    cancelled_at = time.time()
    # The other worker must produce progress after target cancellation, before release.
    end = time.time() + 10
    while time.time() < end:
        after = json.loads((runner.paths(b) / 'work/e5-progress.json').read_text())
        if after['tick'] > before['tick'] and (runner.paths(b) / 'work/e5-progress.json').stat().st_mtime > cancelled_at: break
        time.sleep(.3)
    assert after['tick'] > before['tick']
    (runner.paths(b) / 'state/release').write_text('release by experiment controller\n')
    wait(runner, b)
    state_b = host('resume', {'kind': 'poll', 'attempt': b}, job='parallel-b')
    assert state_b['values']['status'] == 'completed'
    # A fresh host ignores a late notification for the cancelled attempt.
    late = host('resume', {'kind': 'poll', 'attempt': a}, job='parallel-a')
    assert late['values']['status'] == 'cancelled'
    partial_a = json.loads((runner.paths(a) / 'work/e5-partial.json').read_text())
    final_b = json.loads((runner.paths(b) / 'work/e5-result.json').read_text())
    assert partial_a['lane'] == 'a' and final_b['lane'] == 'b'
    assert not (runner.paths(a) / 'work/e5-result.json').exists()
    result = {'status': 'pass' if state_a['values']['cancellation']['native'] == {'acknowledged': True, 'terminal': 'interrupted'} else 'fail',
              'overlap': overlap, 'target': state_a['values'], 'survivor': state_b['values'], 'before_cancel': before,
              'after_cancel': after, 'cancelled_at_epoch': cancelled_at, 'partial_a': partial_a, 'final_b': final_b, 'late_notification_ignored': True}
    for attempt in (a, b):
        out = OUT / runner.paths(attempt).name
        out.mkdir(exist_ok=True)
        for p in (runner.paths(attempt) / 'work').glob('e5-*.json'): shutil.copy2(p, out / p.name)
    save(OUT / 'e5.json', result)
    return result


def main():
    runner = Runner(OUT)
    report = json.loads((OUT / 'report.json').read_text())
    assert report['E1'] == 'pass'
    try:
        report['E4'] = repair(runner, report['state'])['status']
        save(OUT / 'report.json', report)
        report['E5'] = parallel(runner)['status']
    except Exception as e:
        report['followup_error'] = str(e)
    finally:
        runner.cleanup()
        with runner.db() as db: report['turn_starts'] = db.execute('SELECT count(*) FROM dispatches').fetchone()[0]
        save(OUT / 'report.json', report)
    print(json.dumps({k: v for k, v in report.items() if k not in ('state',)}, ensure_ascii=False))


if __name__ == '__main__': main()
