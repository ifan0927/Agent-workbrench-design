"""Offline E6 timeline, evidence binding, reconstruction, and token accounting."""
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from environment import ROOT, SOURCE, COMMIT, run, git, save, digest, source_state
from runner import Runner
from validate import OUT


def main():
    runner = Runner(OUT)
    audit = {'status': 'pass', 'attempts': [], 'gaps': [], 'token_scope': 'one dispatched turn per app-server generation; resume counter reset checked against per-request last values', 'usage': {}, 'rebuilt': []}
    timeline = []
    totals = {'inputTokens': 0, 'cachedInputTokens': 0, 'outputTokens': 0, 'totalTokens': 0}
    unknown_usage = []
    with runner.db() as db:
        attempts = list(db.execute('SELECT * FROM attempts ORDER BY rowid'))
        host_events = list(db.execute('SELECT * FROM events ORDER BY seq'))
        dispatch_count = db.execute('SELECT count(*) FROM dispatches').fetchone()[0]
    audit['turn_starts'] = dispatch_count
    assert dispatch_count <= 10
    for row in attempts:
        directory = runner.paths(row['id'])
        out = OUT / directory.name
        file = out / 'events.jsonl'
        if not file.exists():
            audit['gaps'].append({'attempt': row['id'], 'cause': 'trace_missing'})
            continue
        events = [json.loads(x) for x in file.read_text().splitlines()]
        previous = json.loads((out / 'audit.json').read_text()) if (out / 'audit.json').exists() else {}
        task_path = directory / 'input/task.json' if (directory / 'input/task.json').exists() else out / 'task.json'
        seqs = [e['seq'] for e in events]
        contiguous = seqs == list(range(1, len(events) + 1))
        explicit_gaps = [e for e in events if e['kind'] == 'gap']
        started = {e['data']['item']['id']: e['data']['item'] for e in events if e['kind'] == 'item/started'}
        completed = {e['data']['item']['id']: e['data']['item'] for e in events if e['kind'] == 'item/completed'}
        commands = [i for i in completed.values() if i['type'] == 'commandExecution']
        open_items = [{'id': k, 'type': v['type']} for k, v in started.items() if k not in completed]
        dispatch = json.loads((out / 'dispatch.json').read_text()) if (out / 'dispatch.json').exists() else None
        result = json.loads((out / 'result.json').read_text()) if (out / 'result.json').exists() else None
        spec = json.loads(row['spec'])
        active_starts = [e for e in events if e['kind'] == 'turn/started']
        native_complete = [e for e in events if e['kind'] == 'turn/completed']
        usage_events = [e['data']['tokenUsage'] for e in events if e['kind'] == 'thread/tokenUsage/updated' and dispatch and e['data'].get('turnId') == dispatch.get('turnId')]
        usage = None
        accounting = 'unknown'
        if usage_events:
            distinct = []
            for u in usage_events:
                if not distinct or u['total'] != distinct[-1]['total']: distinct.append(u)
            final = distinct[-1]['total']
            matches_requests = all(sum(u['last'].get(k, 0) for u in distinct) == final.get(k, 0) for k in totals)
            if matches_requests:
                accounting = 'generation_total_matches_sum_of_request_last'
                usage = {k: final.get(k) for k in totals}
                assert usage['inputTokens'] + usage['outputTokens'] == usage['totalTokens']
                for k in totals: totals[k] += usage[k]
            else:
                accounting = 'partial_or_unresolved_cumulative_scope'
                usage = {'reported_total': final}
                unknown_usage.append(row['id'])
        else: unknown_usage.append(row['id'])
        completeness = 'reported_completed_turn' if result and result['turn']['status'] == 'completed' and usage is not None and accounting == 'generation_total_matches_sum_of_request_last' else 'partial_or_unknown'
        if completeness != 'reported_completed_turn' and row['id'] not in unknown_usage: unknown_usage.append(row['id'])
        snapshot = {'attempt': row['id'], 'mode': spec['mode'], 'container_id': row['cid'], 'thread_id': dispatch.get('threadId') if dispatch else None,
                    'turn_id': dispatch.get('turnId') if dispatch else None, 'status': result['turn']['status'] if result else 'unknown',
                    'events': len(events), 'sequence_contiguous': contiguous, 'turn_starts': len(active_starts),
                    'turn_completions': len(native_complete), 'commands_completed': len(commands), 'open_items': open_items,
                    'usage': usage, 'usage_accounting': accounting, 'usage_completeness': completeness, 'collected': row['collected'],
                    'adapter_files': {p.name: digest(p) for p in (directory / 'adapter').glob('*.mjs')} if (directory / 'adapter').exists() else previous.get('adapter_files'),
                    'input_sha256': digest(task_path)}
        snapshot['container_removed'] = run('docker', 'inspect', row['cid'], check=False).returncode != 0
        assert snapshot['container_removed'], 'remove workers before offline audit'
        save(out / 'audit.json', snapshot)
        if task_path != out / 'task.json': shutil.copy2(task_path, out / 'task.json')
        audit['attempts'].append(snapshot)
        if not contiguous or explicit_gaps or not dispatch or not result or len(active_starts) != 1 or len(native_complete) != 1:
            audit['gaps'].append({'attempt': row['id'], 'cause': 'missing_or_discontinuous_lifecycle'})
        if open_items:
            audit['gaps'].append({'attempt': row['id'], 'cause': 'unfinished_items', 'items': open_items})
        for e in events:
            if e['kind'] in ('item/started', 'item/completed', 'turn/started', 'turn/completed', 'server/started', 'server/exited', 'rpc/completed'):
                item = e['data'].get('item', {})
                timeline.append({'time': e['time'], 'attempt': row['id'], 'collector': e['generation'], 'seq': e['seq'], 'origin': e['origin'],
                                 'kind': e['kind'], 'item_type': item.get('type'), 'command': item.get('command'), 'cwd': item.get('cwd'),
                                 'exit_code': item.get('exitCode'), 'evidence': str(file.relative_to(OUT))})
    audit['usage'] = {'known_total': totals, 'unknown_or_partial_attempts': unknown_usage, 'cached_input_included_in_input': True,
                      'complete_batch_total': not unknown_usage}
    for row in host_events:
        timeline.append({'time': row['at'].replace(' ', 'T') + 'Z', 'origin': 'host', 'seq': row['seq'], 'kind': row['kind'], 'data': json.loads(row['data'])})
    timeline.sort(key=lambda e: (e['time'], e.get('attempt', ''), e['seq']))
    save(OUT / 'timeline.json', timeline)
    lines = ['# E 組離線時間線', '', '同一收集者依 seq 排序；跨程序依 UTC 時間與身分核對，不將相同文字 delta 去重。', '']
    for e in timeline:
        if e['kind'] == 'item/started' and e.get('item_type') not in ('commandExecution', 'fileChange'): continue
        summary = e.get('command') or e.get('item_type') or e.get('data') or ''
        lines.append(f"- {e['time']} · {e.get('attempt', 'host')} · {e['origin']} · {e['kind']} · {str(summary).replace(chr(10), ' ')[:500]}")
    (OUT / 'timeline.md').write_text('\n'.join(lines) + '\n')
    # Reconstruct from self-contained bundles only after all model workers are removed.
    for candidate_file in OUT.glob('*/candidate.json'):
        candidate = json.loads(candidate_file.read_text())
        assert digest(Path(candidate['bundle'])) == candidate['bundle_sha256']
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as temp:
            work = Path(temp) / 'reconstructed'
            runner.clone(candidate['bundle'], work, candidate['commit'])
            assert git(work, 'rev-parse', 'HEAD^{tree}') == candidate['tree']
            changed = git(work, 'diff', '--name-only', COMMIT, 'HEAD').splitlines()
            assert all(p == 'src/lib/content/news.ts' or (p.startswith('src/lib/content/') and p.endswith('.test.ts') and not (ROOT / 'baseline' / p).exists()) for p in changed)
            audit['rebuilt'].append({'commit': candidate['commit'], 'tree': candidate['tree'], 'files': source_state(work)['files'], 'changed': changed})
    baseline_before = json.loads((ROOT / 'results/e0/source-before.json').read_text())
    audit['source_unchanged'] = source_state(SOURCE) == baseline_before
    audit['current_implementation'] = {str(p.relative_to(ROOT)): digest(p) for p in [*ROOT.glob('*.py'), *ROOT.glob('*.mjs'), *ROOT.glob('inputs/**/*.json'), *ROOT.glob('inputs/**/*.mjs'), *ROOT.glob('inputs/**/*.ts'), *ROOT.glob('inputs/**/*.md'), *ROOT.glob('inputs/**/*.toml')]}
    if audit['gaps'] or not audit['source_unchanged']: audit['status'] = 'inconclusive'
    save(OUT / 'audit.json', audit)
    report = json.loads((OUT / 'report.json').read_text())
    report['E6'] = audit['status']
    report['usage'] = audit['usage']
    save(OUT / 'report.json', report)
    print(json.dumps({'E6': audit['status'], 'gaps': audit['gaps'], 'usage': audit['usage']}, ensure_ascii=False))


if __name__ == '__main__': main()
