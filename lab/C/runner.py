"""Bounded live C handoff: ask, destroy, rebuild context, code, destroy, review."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'A'))
from rpc import Rpc, RpcError, clean_env
from live import load_auth
from core import candidate, collect, digest, encoded, evidence_gate, git, restore, save, answer_transition
from fixtures import IMAGE, VERSION, REQUIREMENT, ORACLE, RESULT_SCHEMA, REVIEW_SCHEMA, seed


async def command(*args, required=True):
    proc = await asyncio.create_subprocess_exec(*args, stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.PIPE)
    try:
        out, err = await asyncio.wait_for(proc.communicate(), 30)
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    if required and proc.returncode:
        raise RuntimeError('local_command_failed:' + args[0])
    return proc.returncode, out.decode().rstrip('\n')


def checked(value, secrets):
    raw = encoded(value)
    if any(s.encode() in raw for s in secrets if s):
        raise RuntimeError('secret_in_output')
    return value


def docker_args(name, inputs, repo=None):
    args = ['docker', 'run', '--rm', '-i', '--name', name, '--init',
            '--label', 'agent-workbench.lab=C', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--memory=1g', '--cpus=1', '--pids-limit=128',
            '--read-only', '--tmpfs', '/tmp:rw,nosuid,size=256m',
            '--tmpfs', '/codex-home:rw,nosuid,uid=1000,gid=1000,mode=700,size=128m',
            '--mount', f'type=bind,src={inputs},dst=/input,readonly']
    if repo:
        args += ['--mount', f'type=bind,src={repo},dst=/work,readonly']
    else:
        args += ['--tmpfs', '/work:rw,nosuid,uid=1000,gid=1000,mode=700,size=64m']
    return args + [IMAGE, '-c', 'cli_auth_credentials_store="ephemeral"',
                   '-c', 'model_provider="openai"', '-c', 'web_search="disabled"',
                   '-c', 'analytics.enabled=false', '-c', 'check_for_update_on_startup=false',
                   '-c', 'features.multi_agent=false', '-c', 'features.apps=false']


@asynccontextmanager
async def server(inputs, external, secrets, lifecycle, repo=None):
    name = 'awb-c-' + uuid.uuid4().hex[:12]
    lifecycle.update(container=name, removed=False)
    rpc = Rpc(docker_args(name, inputs, repo), ROOT, clean_env(), secrets)
    rpc.container_name = name
    try:
        async with rpc:
            await rpc.initialize()
            login = await rpc.request('account/login/start', {'type': 'chatgptAuthTokens', **external})
            account = await rpc.request('account/read', {'refreshToken': False})
            lifecycle['external_auth'] = (login.get('type') == 'chatgptAuthTokens'
                                         and (account.get('account') or {}).get('type') == 'chatgpt')
            if not lifecycle['external_auth']:
                raise RuntimeError('external_auth_failed')
            if repo is None:
                await command('docker', 'exec', name, 'git', 'clone', '-q', '/input/base.bundle', '/work')
            yield rpc
            _, auth = await command('docker', 'exec', name, 'sh', '-c',
                                    'test ! -e /codex-home/auth.json && echo absent')
            lifecycle['auth_file_absent'] = auth == 'absent'
    finally:
        await command('docker', 'rm', '-f', name, required=False)
        # A daemon query must succeed; an arbitrary inspect error is not proof of absence.
        _, names = await command('docker', 'ps', '-a', '--filter', 'name=^/' + name + '$', '--format', '{{.Names}}')
        lifecycle.update(removed=not names, process_exit_code=rpc.process.returncode if hasattr(rpc, 'process') else None,
                         stderr_secret_found=rpc.stderr_secret_found, refresh_requests=rpc.refresh_requests)


async def start(rpc, model, role):
    result = await rpc.request('thread/start', {
        'model': model, 'modelProvider': 'openai', 'cwd': '/work', 'ephemeral': True,
        'approvalPolicy': 'never', 'sandbox': 'read-only', 'allowProviderModelFallback': False,
        'config': {'model_reasoning_effort': 'low'},
        'developerInstructions': 'This is a synthetic C lab. Work only with /input and /work. '
        'No delegation, network tools, credential access, publishing, or installs. '
        'Use local commands to inspect actual files. Write prose in Traditional Chinese. Role: ' + role})
    if result['model'] != model or result['modelProvider'] != 'openai' or result.get('reasoningEffort') != 'low':
        raise RuntimeError('effective_model_config_mismatch')
    return result


async def turn(rpc, thread, prompt, schema, seconds, secrets):
    tid = thread['thread']['id']
    result = {'thread_id': tid, 'status': 'failed', 'commands': [], 'usage': None,
              'model': thread['model'], 'reasoning_effort': thread['reasoningEffort']}
    turn_id, answer = None, None
    try:
        async with asyncio.timeout(seconds):
            response = await rpc.request('turn/start', {'threadId': tid,
                'sandboxPolicy': {'type': 'externalSandbox', 'networkAccess': 'enabled'},
                'input': [{'type': 'text', 'text': prompt}], 'outputSchema': schema})
            turn_id = response['turn']['id']
            result['turn_id'] = turn_id
            while True:
                event = await rpc.notifications.get()
                checked(event, secrets)
                method, p = event['method'], event['params']
                if method == 'lab/transportClosed':
                    raise RuntimeError('transport_closed')
                if p.get('threadId') != tid:
                    continue
                if method == 'thread/tokenUsage/updated' and p.get('turnId') == turn_id:
                    result['usage'] = p['tokenUsage']['total']
                if method == 'item/completed' and p.get('turnId') == turn_id:
                    item = p['item']
                    if item['type'] == 'agentMessage':
                        answer = item['text']
                    if item['type'] == 'commandExecution':
                        result['commands'].append({'sha256': digest(item.get('command', '').encode()),
                                                   'exit_code': item.get('exitCode')})
                if method == 'turn/completed' and p['turn']['id'] == turn_id:
                    result['status'] = p['turn']['status']
                    break
    except TimeoutError:
        result['status'] = 'timeout'
        if turn_id:
            try:
                await rpc.request('turn/interrupt', {'threadId': tid, 'turnId': turn_id}, timeout=5)
            except Exception:
                pass
    if answer:
        try:
            result['output'] = checked(json.loads(answer), secrets)
        except json.JSONDecodeError:
            result['output_format_error'] = True
    if result['status'] != 'completed' or 'output' not in result:
        raise RuntimeError('turn_not_delivered:' + result['status'])
    return result


async def dex(rpc, *args, required=True):
    return await command('docker', 'exec', rpc.container_name, *args, required=required)


async def export_file(rpc, source, target, secrets):
    # Some Docker backends cannot docker-cp files in tmpfs; read via the live process.
    proc = await asyncio.create_subprocess_exec('docker', 'exec', rpc.container_name, 'cat', source,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        data, _ = await asyncio.wait_for(proc.communicate(), 30)
    except BaseException:
        proc.kill()
        await proc.wait()
        raise
    if proc.returncode or any(s.encode() in data for s in secrets if s):
        raise RuntimeError('artifact_export_failed')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('xb') as f:
        f.write(data)


async def acceptance(repo, inputs):
    args = ['docker', 'run', '--rm', '--network=none', '--read-only', '--cap-drop=ALL',
            '--security-opt=no-new-privileges', '--memory=256m', '--cpus=1', '--pids-limit=64',
            '--label', 'agent-workbench.lab=C', '--mount', f'type=bind,src={repo},dst=/work,readonly',
            '--mount', f'type=bind,src={inputs},dst=/input,readonly', '--entrypoint', 'node', IMAGE, '/input/verify.cjs']
    code, output = await command(*args, required=False)
    return {'exit_code': code, 'oracle_marker_matches': output == 'C_ACCEPTANCE_OK',
            'oracle_sha256': digest((inputs / 'verify.cjs').read_bytes())}


async def finish(runtime, out, report, args, external, secrets, base_commit, question, development, lifecycle, inputs, answered, binding, chosen):
    # C2: only the durable bundle and report remain; original /work was tmpfs.
    reconstructed = runtime / 'reconstructed'
    restore(out / 'candidate.bundle', reconstructed, binding)
    report['checks']['new_file_restored'] = (reconstructed / 'usage.md').is_file()
    report['checks']['base_history_restored'] = git(reconstructed, 'rev-parse', 'HEAD^') == base_commit
    report['checks']['partial_report_survived'] = json.loads((out / 'partial-report.json').read_text()) == question['output']
    for p in reconstructed.iterdir():
        if p.is_file():
            checked(p.read_text(), secrets)
    collection = collect(reconstructed, json.dumps(development['output']),
                         lifecycle['process_exit_code'], ['tags.cjs', 'usage.md'])
    save(out / 'collection.json', collection)
    report['checks']['candidate_delivered'] = collection['delivery'] == 'complete'
    test_run = await acceptance(reconstructed, inputs)
    test = {'kind': 'test', 'binding': binding, 'passed': test_run['exit_code'] == 0 and test_run['oracle_marker_matches'],
            'execution': test_run}
    save(out / 'test.json', test)
    report['checks']['restored_acceptance'] = test['passed']
    # C3: review input has no development messages, session files, or handoff.
    review_input = out / 'review-input'
    review_input.mkdir()
    (review_input / 'requirement.json').write_bytes(encoded(answered))
    save(review_input / 'candidate.json', binding)
    save(review_input / 'test.json', test)
    (review_input / 'verify.cjs').write_text(ORACLE)
    lifecycle = report['workers']['review'] = {}
    async with server(review_input, external, secrets, lifecycle, reconstructed) as rpc:
        code, _ = await dex(rpc, 'touch', '/work/c-review-write-probe', required=False)
        report['checks']['review_workspace_readonly'] = code != 0
        thread = await start(rpc, chosen, '獨立 review；僅依固定候選、需求與驗證紀錄判斷，不修改檔案。')
        review_turn = await turn(rpc, thread, 'Review /work against /input/requirement.json. '
            'Read /input/candidate.json and /input/test.json, inspect the full relevant code and usage.md, '
            'and run node /input/verify.cjs. Return candidate commit, requirement_sha256, verdict, '
            'findings with locations/reasons/blocking flags, and limitations. A passing test is not a substitute '
            'for checking requirements. No development conversation is available.', REVIEW_SCHEMA, args.seconds, secrets)
        save(out / 'review-turn.json', review_turn)
    output = review_turn['output']
    review = {'kind': 'review', 'binding': binding,
              'passed': (output['candidate'] == binding['commit']
                         and output['requirement_sha256'] == binding['requirement_sha256']
                         and output['verdict'] == 'pass' and not any(f['blocking'] for f in output['findings'])),
              'result': output, 'thread_id': review_turn['thread_id']}
    save(out / 'review.json', review)
    report['checks']['fresh_thread'] = len({t['thread_id'] for t in (question, development, review_turn)}) == 3
    report['checks']['fixed_review_candidate'] = git(reconstructed, 'rev-parse', 'HEAD') == binding['commit'] and not git(reconstructed, 'status', '--porcelain')
    report['checks']['candidate_evidence_gate'] = evidence_gate(binding, [test, review])['passed']
    # C4: a real new commit requires its own evidence, even for a documentation correction.
    with (reconstructed / 'usage.md').open('a') as f:
        f.write('\n補充：非字串輸入會拋出 TypeError。\n')
    git(reconstructed, 'add', '--', 'usage.md')
    git(reconstructed, 'commit', '-q', '-m', 'Clarify invalid input behavior')
    new_binding = candidate(reconstructed, out / 'revised.bundle', answered)
    save(out / 'revised.json', new_binding)
    stale = evidence_gate(new_binding, [test, review])
    new_test_run = await acceptance(reconstructed, inputs)
    new_test = {'kind': 'test', 'binding': new_binding, 'passed': new_test_run['exit_code'] == 0 and new_test_run['oracle_marker_matches'], 'execution': new_test_run}
    save(out / 'revised-test.json', new_test)
    mixed = evidence_gate(new_binding, [new_test, review])
    save(out / 'stale-evidence.json', {'old_only': stale, 'new_test_old_review': mixed})
    report['checks']['old_evidence_rejected'] = stale == {'passed': False, 'gaps': ['missing_current_test', 'missing_current_review']}
    report['checks']['new_test_cannot_reuse_old_review'] = new_test['passed'] and mixed == {'passed': False, 'gaps': ['missing_current_review']}
    report['checks']['separate_human_decisions'] = collection['user_adoption'] == 'undecided' and collection['next_authorization'] is None
    report['usage_this_run'] = review_turn['usage'] if args.reuse else {key: sum(t['usage'][key] for t in (question, development, review_turn)) for key in development['usage']}
    report['usage_total'] = {key: sum(t['usage'][key] for t in (question, development, review_turn)) for key in development['usage']}


async def run(args):
    out = ROOT / 'results' / args.run
    out.mkdir(parents=True, exist_ok=False)
    report = {'mode': 'real_containers_and_model', 'codex_version': VERSION,
              'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'limits': {'max_model_turns': 1 if args.reuse else 3, 'seconds_per_turn': args.seconds,
                         'token_hard_cap': None, 'api_fallback': False, 'oauth_refresh': False},
              'workers': {}, 'checks': {}}
    external, before, secrets = load_auth(args.auth_file)
    ROOT.joinpath('.runtime').mkdir(exist_ok=True)
    try:
        _, version = await command('docker', 'run', '--rm', '--network=none', '--entrypoint', 'codex', IMAGE, '--version')
        if version != 'codex-cli ' + VERSION:
            raise RuntimeError('version_mismatch')
        _, report['image_id'] = await command('docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}')
        with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
            runtime = Path(tmp)
            if args.reuse:
                source = ROOT / 'results' / args.reuse
                previous = json.loads((source / 'report.json').read_text())
                needed = ['question_left_base_unchanged', 'comment_did_not_dispatch', 'explicit_answer_dispatched',
                          'lost_session_resume_rejected', 'worker_acceptance', 'candidate_delivered',
                          'restored_acceptance', 'auth_source_unchanged', 'workers_removed', 'worker_credentials']
                if not all(previous['checks'].get(k) for k in needed):
                    raise RuntimeError('reuse_prerequisites_failed')
                chosen = previous['model']
                if args.model and args.model != chosen:
                    raise RuntimeError('reuse_model_mismatch')
                for name in ('initial', 'implementation-input', 'partial-artifacts'):
                    shutil.copytree(source / name, out / name)
                for name in ('question-turn.json', 'implementation-turn.json', 'waiting.json', 'after-comment.json',
                             'partial-report.json', 'candidate.bundle', 'candidate.json'):
                    shutil.copyfile(source / name, out / name)
                save(out / 'inherited-source-manifest.json', json.loads((source / 'source-manifest.json').read_text()))
                report['reused_from'] = args.reuse
                report['inherited_artifacts'] = {str(p.relative_to(out)): digest(p.read_bytes())
                    for p in out.rglob('*') if p.is_file()}
                report['model'] = chosen
                report['resume_error_code'] = previous['resume_error_code']
                report['checks'].update({k: previous['checks'][k] for k in needed})
                for name in ('question', 'implementation'):
                    worker = previous['workers'][name]
                    _, live_names = await command('docker', 'ps', '-a', '--filter', 'name=^/' + worker['container'] + '$', '--format', '{{.Names}}')
                    if live_names:
                        raise RuntimeError('reuse_worker_still_exists')
                    report['workers'][name] = worker
                lifecycle = report['workers']['implementation']
                base_commit = json.loads((out / 'initial/binding.json').read_text())['commit']
                question = json.loads((out / 'question-turn.json').read_text())
                development = json.loads((out / 'implementation-turn.json').read_text())
                inputs = out / 'implementation-input'
                answered = json.loads((inputs / 'requirement.json').read_text())
                binding = json.loads((out / 'candidate.json').read_text())
                if digest(encoded(answered)) != binding['requirement_sha256']:
                    raise RuntimeError('reuse_requirement_mismatch')
            else:
                base = runtime / 'base'
                base_commit = seed(base)
                initial = out / 'initial'
                initial.mkdir()
                (initial / 'requirement.json').write_bytes(encoded(REQUIREMENT))
                base_binding = candidate(base, initial / 'base.bundle', REQUIREMENT)
                save(initial / 'binding.json', base_binding)
                # C5 phase 1: a real turn asks a necessary question, then loses its session.
                lifecycle = report['workers']['question'] = {}
                async with server(initial, external, secrets, lifecycle) as rpc:
                    models = await rpc.request('model/list', {'includeHidden': False})
                    chosen = args.model or next(m['model'] for m in models['data'] if m.get('isDefault'))
                    offered = next((m for m in models['data'] if m['model'] == chosen), None)
                    if not offered or 'low' not in [e['reasoningEffort'] for e in offered.get('supportedReasoningEfforts', [])]:
                        raise RuntimeError('model_or_effort_unavailable')
                    report['model'] = chosen
                    thread = await start(rpc, chosen, '需求釐清；尚未回答必要問題，勿修改檔案。')
                    question = await turn(rpc, thread, 'Read /input/requirement.json and /work/tags.cjs. '
                        'The empty-tag policy is deliberately undecided. Return status waiting, a specific '
                        'question matching pending_question id/options, a useful partial summary, and incomplete items. '
                        'Do not choose the policy or implement yet. artifacts and side_effects are empty arrays.',
                        RESULT_SCHEMA, args.seconds, secrets)
                    save(out / 'question-turn.json', question)
                    q = question['output']['question']
                    if question['output']['status'] != 'waiting' or not q or q['id'] != 'empty-tags' or set(q['options']) != {'discard', 'reject'}:
                        raise RuntimeError('question_contract_failed')
                    _, dirty = await dex(rpc, 'git', '-C', '/work', 'status', '--porcelain')
                    report['checks']['question_left_base_unchanged'] = not dirty
                save(out / 'partial-report.json', question['output'])
                state = {'phase': 'waiting', 'question': q, 'candidate': base_commit,
                         'requirement_sha256': base_binding['requirement_sha256'],
                         'summary': question['output']['summary'], 'session_id': question['thread_id'],
                         'user_adoption': 'undecided', 'next_authorization': None}
                save(out / 'waiting.json', state)
                # Reload durable state to simulate the next invocation, never rely on live memory.
                state = json.loads((out / 'waiting.json').read_text())
                state, dispatch = answer_transition(state, {'type': 'comment', 'text': 'discard', 'event_id': 'comment-1'})
                save(out / 'after-comment.json', state)
                report['checks']['comment_did_not_dispatch'] = not dispatch and state['phase'] == 'waiting'
                event = {'type': 'answer_and_continue', 'question_id': q['id'], 'event_id': 'answer-1',
                         'candidate': base_commit, 'requirement_sha256': state['requirement_sha256'], 'value': 'discard'}
                state, dispatch = answer_transition(json.loads((out / 'after-comment.json').read_text()), event)
                report['checks']['explicit_answer_dispatched'] = dispatch and state['phase'] == 'ready'
                if not dispatch:
                    raise RuntimeError('answer_not_dispatched')
                answered = {**REQUIREMENT, 'answer': {'question_id': 'empty-tags', 'value': 'discard'}}
                inputs = out / 'implementation-input'
                inputs.mkdir()
                shutil.copyfile(initial / 'base.bundle', inputs / 'base.bundle')
                (inputs / 'requirement.json').write_bytes(encoded(answered))
                save(inputs / 'handoff.json', state)
                (inputs / 'verify.cjs').write_text(ORACLE)
                lifecycle = report['workers']['implementation'] = {}
                async with server(inputs, external, secrets, lifecycle) as rpc:
                    try:
                        await rpc.request('thread/resume', {'threadId': state['session_id']})
                        report['checks']['lost_session_resume_rejected'] = False
                    except RpcError as exc:
                        report['checks']['lost_session_resume_rejected'] = True
                        report['resume_error_code'] = exc.error.get('code')
                    if not report['checks']['lost_session_resume_rejected']:
                        raise RuntimeError('unexpected_session_available')
                    thread = await start(rpc, chosen, '依保存交接與明確回答完成小型 coding 任務。')
                    development = await turn(rpc, thread, 'Read /input/handoff.json and /input/requirement.json. '
                        'The explicit answer authorizes continuation. Implement the requirement in tags.cjs and add usage.md. '
                        'Run node /input/verify.cjs. Do not commit; the collector will create a candidate after your turn. '
                        'Return the complete result with artifacts ["tags.cjs", "usage.md"], question null, '
                        'incomplete [], and side_effects [].', RESULT_SCHEMA, args.seconds, secrets)
                    save(out / 'implementation-turn.json', development)
                    code, marker = await dex(rpc, 'node', '/input/verify.cjs', required=False)
                    report['checks']['worker_acceptance'] = code == 0 and marker == 'C_ACCEPTANCE_OK'
                    for name in ('tags.cjs', 'usage.md'):
                        await export_file(rpc, '/work/' + name, out / 'partial-artifacts' / name, secrets)
                    # Commit in the disposable worker, then export all Git objects, including the new file.
                    _, changed = await dex(rpc, 'git', '-C', '/work', 'status', '--porcelain', '--untracked-files=all')
                    paths = {line[3:] for line in changed.splitlines()}
                    if paths != {'tags.cjs', 'usage.md'}:
                        raise RuntimeError('unexpected_changed_paths')
                    await dex(rpc, 'git', '-C', '/work', 'add', '--', 'tags.cjs', 'usage.md')
                    await dex(rpc, 'git', '-C', '/work', '-c', 'user.name=C Lab', '-c', 'user.email=lab@example.invalid',
                              '-c', 'core.hooksPath=/dev/null', 'commit', '-q', '-m', 'Implement answered tag normalization')
                    _, commit = await dex(rpc, 'git', '-C', '/work', 'rev-parse', 'HEAD')
                    _, tree = await dex(rpc, 'git', '-C', '/work', 'rev-parse', 'HEAD^{tree}')
                    await dex(rpc, 'git', '-C', '/work', 'bundle', 'create', '/tmp/candidate.bundle', '--all')
                    await export_file(rpc, '/tmp/candidate.bundle', out / 'candidate.bundle', secrets)
                    binding = {'commit': commit, 'tree': tree, 'bundle_sha256': digest((out / 'candidate.bundle').read_bytes()),
                               'requirement_sha256': digest(encoded(answered))}
                    save(out / 'candidate.json', binding)
            await finish(runtime, out, report, args, external, secrets, base_commit, question, development, lifecycle, inputs, answered, binding, chosen)
    except Exception as exc:
        report['error_type'] = type(exc).__name__
        if isinstance(exc, RuntimeError):
            report['error'] = checked(str(exc), secrets)
    finally:
        report['checks']['auth_source_unchanged'] = before == hashlib.sha256(args.auth_file.read_bytes()).digest()
        report['checks']['workers_removed'] = bool(report['workers']) and all(w.get('removed') for w in report['workers'].values())
        report['checks']['worker_credentials'] = all(w.get('auth_file_absent') and w.get('external_auth')
                                                   and not w.get('stderr_secret_found') and w.get('refresh_requests') == 0 for w in report['workers'].values())
        report['passed'] = 'error_type' not in report and all(report['checks'].values())
        save(out / 'report.json', checked(report, secrets))
        source_paths = sorted(ROOT.glob('*.py')) + [ROOT.parent / 'A' / n for n in ('rpc.py', 'live.py', 'auth.py', 'Dockerfile')]
        save(out / 'source-manifest.json', {str(p.relative_to(ROOT.parent)): digest(p.read_bytes()) for p in source_paths})
    print(json.dumps({'run': args.run, 'passed': report['passed'], 'checks': report['checks'], 'error': report.get('error')}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='C 組真實交接：最多三個模型 turn，合成 fixture 回答，不發布。')
    parser.add_argument('--auth-file', type=Path, required=True)
    parser.add_argument('--model', help='省略時固定使用本次 model/list 預設模型')
    parser.add_argument('--seconds', type=int, default=120, choices=range(1, 121), metavar='1..120')
    parser.add_argument('--run', default='live', help='results 下尚未存在的目錄名稱')
    parser.add_argument('--reuse', help='沿用已保存且通過 coding 驗收的 run，只重建與重新 review')
    args = parser.parse_args()
    if args.reuse and (Path(args.reuse).name != args.reuse or args.reuse in ('.', '..')):
        parser.error('--reuse 必須是 results 下單層目錄名稱')
    if Path(args.run).name != args.run or args.run in ('.', '..') or (ROOT / 'results' / args.run).exists():
        parser.error('--run 必須是新的單層目錄名稱')
    try:
        raise SystemExit(asyncio.run(run(args)))
    except Exception as exc:
        print(json.dumps({'passed': False, 'error_type': type(exc).__name__}))
        raise SystemExit(1)
