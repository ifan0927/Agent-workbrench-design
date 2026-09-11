"""Real Codex app-server probes and bounded subscription-backed behavior checks."""

import argparse
import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent / 'A'))
from rpc import Rpc, RpcError, clean_env
from live import load_auth, command
from fixtures import IMAGE, VERSION, MODE, TASK, TOOL, sources, snapshot, file_map, preflight, settings_errors


class UnavailableSettings(Exception):
    def __init__(self, problems):
        self.problems = problems
        super().__init__('requested_settings_unavailable')


class LabRpc(Rpc):
    def __init__(self, *args, checkpoint=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.checkpoint = checkpoint
        self.calls = []

    async def handle(self, message):
        if message['method'] != 'item/tool/call':
            return await super().handle(message)
        p = message['params']
        ok = p.get('tool') == 'lab_checkpoint' and p.get('arguments') == {}
        self.calls.append({'tool': p.get('tool'), 'valid': ok, 'time': time.monotonic()})
        try:
            if ok and self.checkpoint:
                await self.checkpoint()
            result = {'success': ok, 'contentItems': [{'type': 'inputText', 'text': 'checkpoint complete' if ok else 'invalid tool'}]}
            await self.send({'id': message['id'], 'result': result})
        except Exception:
            await self.send({'id': message['id'], 'error': {'code': -32001, 'message': 'checkpoint_failed'}})

    async def initialize(self):
        result = await self.request('initialize', {'clientInfo': {'name': 'agent_workbench_lab_b', 'version': '0.1.0'},
                                                   'capabilities': {'experimentalApi': True}})
        await self.send({'method': 'initialized', 'params': {}})
        return result


def docker_args(name, snap, out, network):
    args = ['docker', 'run', '--rm', '-i', '--name', name, '--init', '--label', 'agent-workbench.lab=B',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=1g', '--cpus=1', '--pids-limit=128',
            '--read-only', '--tmpfs', '/tmp:rw,nosuid,size=256m',
            '--tmpfs', '/codex-home:rw,nosuid,uid=1000,gid=1000,mode=700,size=128m']
    mounts = [(snap / 'repo', '/work', True), (out, '/out', False),
              (snap / 'home/AGENTS.md', '/codex-home/AGENTS.md', True),
              (snap / 'home/config.toml', '/codex-home/config.toml', True),
              (snap / 'user-skills', '/home/node/.agents/skills', True)]
    mounts += [(p, '/codex-home/skills/' + p.name, True) for p in (snap / 'home/skills').iterdir()]
    for source, dest, readonly in mounts:
        args += ['--mount', f'type=bind,src={source},dst={dest}' + (',readonly' if readonly else '')]
    if not network:
        args += ['--network=none']
    return args + [IMAGE]


@asynccontextmanager
async def server(snap, out, external=None, secrets=(), checkpoint=None):
    out.mkdir()
    out.chmod(0o777)
    name = 'awb-b-' + uuid.uuid4().hex[:12]
    rpc = LabRpc(docker_args(name, snap, out, external is not None), ROOT, clean_env(), secrets, checkpoint=checkpoint)
    try:
        async with rpc:
            await rpc.initialize()
            if external:
                login = await rpc.request('account/login/start', {'type': 'chatgptAuthTokens', **external})
                account = await rpc.request('account/read', {'refreshToken': False})
                if login.get('type') != 'chatgptAuthTokens' or (account.get('account') or {}).get('type') != 'chatgpt':
                    raise RuntimeError('external_login_failed')
            rpc.container_name = name
            yield rpc
    finally:
        try:
            await command('docker', 'rm', '-f', name)
        except Exception:
            pass


async def inspect(rpc):
    config = await rpc.request('config/read', {'cwd': '/work', 'includeLayers': True})
    discovery = await rpc.request('skills/list', {'cwds': ['/work'], 'forceReload': True})
    entry = discovery['data'][0]
    mcp = await rpc.request('mcpServerStatus/list', {})
    models = await rpc.request('model/list', {'includeHidden': False})
    skills = [{k: s.get(k) for k in ('name', 'path', 'scope', 'enabled', 'dependencies', 'pluginId')} for s in entry['skills']]
    return {'effective_config': {k: config['config'].get(k) for k in ('model', 'model_provider', 'model_reasoning_effort', 'web_search')},
            'config_origins': {k: v for k, v in config['origins'].items() if k in ('model', 'model_reasoning_effort', 'web_search')},
            'skills': skills, 'skill_errors': entry['errors'],
            'mcp_servers': [m['name'] for m in mcp['data']],
            'model_catalog': [{'model': m['model'], 'supportedReasoningEfforts': m.get('supportedReasoningEfforts', [])} for m in models['data']],
            'preflight': preflight(skills, ['b-selected', 'b-twin', 'b-missing', 'b-unselected'], [m['name'] for m in mcp['data']])}


async def start(rpc, model, **overrides):
    params = {'model': model, 'modelProvider': 'openai', 'cwd': '/work', 'ephemeral': True,
              'approvalPolicy': 'never', 'sandbox': 'read-only', 'allowProviderModelFallback': False,
              'config': {'model_reasoning_effort': 'low'}, 'developerInstructions': MODE, 'dynamicTools': [TOOL]}
    params.update(overrides)
    return await rpc.request('thread/start', params)


def thread_summary(thread):
    return {k: thread.get(k) for k in ('model', 'modelProvider', 'reasoningEffort', 'cwd', 'instructionSources', 'sandbox', 'approvalPolicy')}


async def turn(rpc, thread, seconds, task=TASK):
    tid = thread['thread']['id']
    result = {'thread_id': tid, 'status': 'failed', 'commands': [], 'usage': None, 'secret_found': False}
    turn_id = None
    try:
        async with asyncio.timeout(seconds):
            response = await rpc.request('turn/start', {'threadId': tid,
                'sandboxPolicy': {'type': 'externalSandbox', 'networkAccess': 'enabled'},
                'input': [{'type': 'text', 'text': task}]})
            turn_id = response['turn']['id']
            result['turn_id'] = turn_id
            while True:
                e = await rpc.notifications.get()
                m, p = e['method'], e['params']
                raw = json.dumps(e).encode()
                result['secret_found'] |= any(s in raw for s in rpc.secrets)
                if m == 'lab/transportClosed':
                    raise RuntimeError('transport_closed')
                if p.get('threadId') != tid:
                    continue
                if m == 'turn/started' and p['turn']['id'] == turn_id:
                    result['started'] = time.monotonic()
                if m == 'thread/tokenUsage/updated' and p.get('turnId') == turn_id:
                    result['usage'] = p['tokenUsage']['total']
                if m == 'item/completed' and p.get('turnId') == turn_id:
                    item = p['item']
                    if item['type'] == 'commandExecution':
                        cmd = item.get('command', '')
                        # Commands only concern synthetic files; persist hashes and path matches, never arbitrary text.
                        result['commands'].append({'sha256': hashlib.sha256(cmd.encode()).hexdigest(),
                            'exit_code': item.get('exitCode'), 'status': item.get('status'),
                            'selected_skill_read': 'b-selected/SKILL.md' in cmd,
                            'proof_script': 'b-selected/scripts/proof.js' in cmd,
                            'repo_twin_read': '/work/.agents/skills/b-twin/' in cmd,
                            'unselected_read': 'b-unselected' in cmd,
                            'extra_read': 'b-repo-extra' in cmd or 'b-user-extra' in cmd})
                if m == 'turn/completed' and p['turn']['id'] == turn_id:
                    result['status'] = p['turn']['status']
                    result['ended'] = time.monotonic()
                    if p['turn'].get('error'):
                        err = p['turn']['error']
                        result['error'] = {'codexErrorInfo': err.get('codexErrorInfo'),
                                           'unknown_model_mentioned': 'b-model-does-not-exist' in err.get('message', '')}
                    break
    except TimeoutError:
        result['status'] = 'timeout'
        if turn_id:
            try:
                await rpc.request('turn/interrupt', {'threadId': tid, 'turnId': turn_id}, timeout=5)
            except Exception:
                pass
    return result


def check_receipt(out, version):
    expected = {'common': 'common', 'repo': 'repo', 'layered': 'task', 'version': version,
                'mode': 'mode', 'priority': 'mode', 'task': 'task', 'twin': 'repo-twin', 'proof': f'proof-{version}-74931'}
    try:
        actual = json.loads((out / 'receipt.json').read_text())
        return {'matches': actual == expected, 'sha256': hashlib.sha256((out / 'receipt.json').read_bytes()).hexdigest(),
                'verified_artifact': expected if actual == expected else None, 'fields': {k: actual.get(k) == v for k, v in expected.items()}}
    except (OSError, ValueError, AttributeError):
        return {'matches': False, 'fields': {}}


async def negative(rpc, model):
    result = {}
    for label, overrides in [('invalid_effort', {'config': {'model_reasoning_effort': 'b-not-an-effort'}}),
                             ('missing_permission_profile', {'sandbox': None, 'permissions': 'b-missing-profile'})]:
        try:
            response = await start(rpc, model, **overrides)
            result[label] = {'rejected': False, 'effective': thread_summary(response)}
        except RpcError as exc:
            result[label] = {'rejected': True, 'code': exc.error.get('code'),
                             'diagnostic_present': bool(exc.error.get('message'))}
    return result


async def run(args):
    version = await command('docker', 'run', '--rm', '--network=none', '--entrypoint', 'codex', IMAGE, '--version')
    if version != 'codex-cli ' + VERSION:
        raise RuntimeError('version_mismatch')
    external, before, secrets = (None, None, ())
    if args.live:
        external, before, secrets = load_auth(args.auth_file)
    ROOT.joinpath('.runtime').mkdir(exist_ok=True)
    report = {'mode': 'real_model' if args.live else 'real_app_server_no_model', 'codex_version': VERSION,
              'recorded_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
              'image_id': await command('docker', 'image', 'inspect', IMAGE, '--format', '{{.Id}}'),
              'limits': {'max_model_turns': 4 if args.live else 0, 'seconds_per_turn': args.seconds,
                         'token_hard_cap': None, 'api_fallback': False, 'oauth_refresh': False}}
    with tempfile.TemporaryDirectory(dir=ROOT / '.runtime') as tmp:
        runtime = Path(tmp)
        source, snap_a, snap_b = (runtime / p for p in ('sources', 'snapshot-a', 'snapshot-b'))
        sources(source, 'v1')
        manifest_a = snapshot(source, snap_a, args.model)
        report['snapshot_a'] = manifest_a
        updated = asyncio.Event()
        async def update():
            if not updated.is_set():
                sources(source, 'v2')
                report['source_updated_at'] = time.monotonic()
                report['snapshot_b'] = snapshot(source, snap_b, args.model)
                report['snapshot_a_unchanged_at_update'] = all(file_map(snap_a).get(k) == v for k, v in manifest_a['snapshot_files'].items())
                updated.set()
        async with server(snap_a, runtime / 'out-a', external, secrets, update) as a:
            report['discovery_a'] = await inspect(a)
            catalog = report['discovery_a']['model_catalog']
            report['settings_preflight'] = settings_errors(args.model, 'low', catalog, [TOOL], ['lab_checkpoint'])
            if report['settings_preflight']:
                raise UnavailableSettings(report['settings_preflight'])
            report['settings_negative'] = {
                'effort': settings_errors(args.model, 'b-not-an-effort', catalog, [TOOL], ['lab_checkpoint']),
                'model': settings_errors('b-model-does-not-exist', 'low', catalog, [TOOL], ['lab_checkpoint']),
                'tool': settings_errors(args.model, 'low', catalog, [], ['lab_checkpoint'])}
            report['negative_config'] = await negative(a, args.model)
            report['readonly_mount_enforced'] = await command('docker', 'exec', a.container_name, 'node', '-e',
                "try { require('fs').appendFileSync('/work/protected.txt','unexpected'); process.stdout.write('writable') } catch(e) { process.stdout.write(e.code) }") == 'EROFS'
            th_a = await start(a, args.model)
            report['thread_a'] = thread_summary(th_a)
            if args.live:
                report['turn_a'] = await turn(a, th_a, args.seconds)
                report['receipt_a'] = check_receipt(runtime / 'out-a', 'v1')
                report['checkpoint_a'] = a.calls
                if not updated.is_set():
                    report['failure'] = 'checkpoint_not_reached'
                else:
                    async with server(snap_b, runtime / 'out-b', external, secrets) as b:
                        report['discovery_b'] = await inspect(b)
                        th_b = await start(b, args.model)
                        report['thread_b'] = thread_summary(th_b)
                        report['turn_b'] = await turn(b, th_b, args.seconds)
                        report['receipt_b'] = check_receipt(runtime / 'out-b', 'v2')
                        report['checkpoint_b'] = b.calls
                        report['b_stderr_secret_found'] = b.stderr_secret_found
                    # Reuse A's running app-server and thread after source mutation to exercise reload/cache paths.
                    report['discovery_a_after'] = await inspect(a)
                    (runtime / 'out-a/receipt.json').unlink(missing_ok=True)
                    report['turn_a_after'] = await turn(a, th_a, args.seconds, TASK + '\nRepeat using the same frozen files, reread the skill reference and rerun its script.')
                    report['receipt_a_after'] = check_receipt(runtime / 'out-a', 'v1')
                bad = await start(a, 'b-model-does-not-exist')
                report['unknown_model_thread'] = thread_summary(bad)
                report['unknown_model_turn'] = await turn(a, bad, min(args.seconds, 45), 'Reply with OK. Do not use tools.')
                report['refresh_requests'] = a.refresh_requests
            else:
                await update()
                report['discovery_a_after'] = await inspect(a)
            report['a_stderr_secret_found'] = a.stderr_secret_found
            report['worker_auth_file_absent'] = await command('docker', 'exec', a.container_name, 'sh', '-c',
                'if test -e /codex-home/auth.json; then echo no; else echo yes; fi') == 'yes'
        report['snapshot_a_unchanged'] = all(file_map(snap_a).get(k) == v for k, v in manifest_a['snapshot_files'].items())
        # Preserve only the synthetic inputs, outside runtime and without credentials.
        evidence = ROOT / 'results' / (Path(args.report).stem + '-inputs')
        shutil.copytree(snap_a, evidence / 'snapshot-a')
        if snap_b.exists():
            shutil.copytree(snap_b, evidence / 'snapshot-b')
    if args.live:
        report['auth_source_unchanged'] = before == hashlib.sha256(args.auth_file.read_bytes()).digest()
    report['checks'] = assess(report)
    encoded = json.dumps(report, indent=2)
    if any(s in encoded for s in secrets if s):
        raise RuntimeError('report_secret_detected')
    with (ROOT / 'results' / args.report).open('x') as stream:
        stream.write(encoded + '\n')
    print(json.dumps({'report': args.report, 'checks': report['checks']}), flush=True)
    return 0 if all(report['checks'].values()) else 1


def assess(r):
    d = r['discovery_a']
    skills = d['skills']
    names = [s['name'] for s in skills]
    checks = {
        'selected_discovered': 'b-selected' in names,
        'unselected_library_absent': 'b-unselected' not in names,
        'repo_extra_discovered': 'b-repo-extra' in names,
        'user_extra_discovered': 'b-user-extra' in names,
        'same_name_distinct': names.count('b-twin') == 2,
        'missing_dependency_visible': any(p['reason'] == 'missing_dependency' for p in d['preflight']),
        'malformed_skill_reported': any('b-invalid' in e['path'] for e in d['skill_errors']),
        'config_rejected': r['negative_config']['missing_permission_profile']['rejected'],
        'host_missing_settings_rejected': all(r['settings_negative'].values()) and not r['settings_preflight'],
        'model_and_effort_effective': r['thread_a']['model'] == r['snapshot_a']['model_requested'] and r['thread_a']['reasoningEffort'] == 'low',
        'instruction_sources': r['thread_a']['instructionSources'] == ['/codex-home/AGENTS.md', '/work/AGENTS.md'],
        'readonly_mount_enforced': r['readonly_mount_enforced'],
        'snapshot_preserved': r['snapshot_a_unchanged'] and r.get('snapshot_a_unchanged_at_update', False),
    }
    if r['mode'] == 'real_model':
        for label in ('a', 'b', 'a_after'):
            t = r.get('turn_' + label, {})
            checks['behavior_' + label] = t.get('status') == 'completed' and r.get('receipt_' + label, {}).get('matches', False)
            commands = t.get('commands', [])
            checks['skill_script_' + label] = any(c['proof_script'] and c['exit_code'] == 0 for c in commands)
        t = r.get('turn_a', {})
        checks['update_during_turn'] = t.get('started', float('inf')) < r.get('source_updated_at', 0) < t.get('ended', 0)
        checks['dynamic_tool_executed'] = bool(r.get('checkpoint_a')) and bool(r.get('checkpoint_b'))
        checks['unknown_model_failed'] = r.get('unknown_model_turn', {}).get('status') == 'failed'
        checks['credentials_clean'] = r['auth_source_unchanged'] and r['worker_auth_file_absent'] and not any(
            r.get(k, True) for k in ('a_stderr_secret_found', 'b_stderr_secret_found')) and not any(
            r.get('turn_' + label, {}).get('secret_found', True) for label in ('a', 'b', 'a_after'))
    return checks


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='B1–B4：配置發現、快照與真實行為實驗')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--auth-file', type=Path, default=Path.home() / '.codex/auth.json')
    parser.add_argument('--model', default='gpt-6-astra')
    parser.add_argument('--seconds', type=int, default=120, choices=range(1, 181), metavar='1..180')
    parser.add_argument('--report', default='probe.json')
    args = parser.parse_args()
    if Path(args.report).name != args.report or not args.report.endswith('.json') or (ROOT / 'results' / args.report).exists() or (ROOT / 'results' / (Path(args.report).stem + '-inputs')).exists():
        parser.error('--report 必須是尚未存在的 .json 檔名')
    try:
        raise SystemExit(asyncio.run(run(args)))
    except Exception as exc:
        failure = {'status': 'failed', 'mode': 'setup_or_transport_failure', 'error_type': type(exc).__name__}
        if isinstance(exc, UnavailableSettings):
            failure['problems'] = exc.problems
        elif isinstance(exc, RuntimeError) and str(exc) in {
            'version_mismatch', 'chatgpt_auth_required', 'missing_external_token_fields',
            'access_token_expired_or_near_expiry', 'account_claim_mismatch', 'external_login_failed'}:
            failure['problem'] = str(exc)
        # Only persist known diagnostic fields, never arbitrary exception text.
        path = ROOT / 'results' / args.report
        if not path.exists():
            with path.open('x') as stream:
                stream.write(json.dumps(failure, indent=2) + '\n')
        print(json.dumps(failure), flush=True)
        raise SystemExit(1)
