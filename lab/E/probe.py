"""No-model probe: adapter ownership survives disconnected host clients."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import uuid
from environment import ROOT, BASE_IMAGE, run, save, digest


def call(name, data):
    p = subprocess.run(['docker', 'exec', '-i', name, 'node', '/lab/client.mjs'], input=json.dumps(data).encode(), capture_output=True, timeout=30)
    reply = json.loads(p.stdout)
    if p.returncode:
        raise RuntimeError(reply.get('error', 'client_failed'))
    return reply['result']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='probe')
    args = parser.parse_args()
    assert args.report.replace('-', '').isalnum()
    out = ROOT / 'results' / args.report
    out.mkdir(parents=True)
    state = ROOT / '.runtime' / (args.report + '-state')
    state.mkdir(parents=True, mode=0o700)
    state.chmod(0o777)
    name = 'awb-e-probe-' + uuid.uuid4().hex[:10]
    report = {'kind': 'real_container_no_model', 'model_turns': 0, 'status': 'running'}
    try:
        cid = run('docker', 'run', '-d', '--name', name, '--init', '--label', 'agent-workbench.lab=E',
            '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--network=none', '--memory=1g', '--pids-limit=128',
            '--tmpfs', '/tmp:rw,nosuid,size=256m', '--tmpfs', '/codex-home:rw,nosuid,uid=1000,gid=1000,mode=700,size=128m',
            '--mount', f'type=bind,src={ROOT / "inputs/home/AGENTS.md"},dst=/codex-home/AGENTS.md,readonly',
            '--mount', f'type=bind,src={ROOT / "inputs/home/config.toml"},dst=/codex-home/config.toml,readonly',
            '--mount', f'type=bind,src={ROOT / "inputs/home/skills"},dst=/codex-home/skills,readonly',
            '--mount', f'type=bind,src={ROOT / "baseline"},dst=/work,readonly',
            '--mount', f'type=bind,src={ROOT},dst=/lab,readonly', '--mount', f'type=bind,src={state},dst=/state',
            '--entrypoint', 'node', BASE_IMAGE, '/lab/adapter.mjs').stdout.decode().strip()
        report['container_id'] = cid
        for _ in range(30):
            if (state / 'events.jsonl').exists(): break
            time.sleep(.1)
        report['start'] = call(name, {'action': 'start'})
        # Each call is a separate docker exec/client process; no host RPC process stays alive.
        report['second_host_status'] = call(name, {'action': 'status'})
        assert report['second_host_status']['pid'] == report['start']['pid']
        assert not report['second_host_status']['closed']
        report['config'] = call(name, {'action': 'rpc', 'method': 'config/read', 'params': {'cwd': '/work', 'includeLayers': True}})
        report['skills'] = call(name, {'action': 'rpc', 'method': 'skills/list', 'params': {'cwds': ['/work'], 'forceReload': True}})
        assert any(s['name'] == 'lab-brand-check' and s['enabled'] for d in report['skills']['data'] for s in d['skills'])
        report['models'] = call(name, {'action': 'rpc', 'method': 'model/list', 'params': {'includeHidden': False}})
        selected = next(m for m in report['models']['data'] if m['model'] == 'gpt-6-astra')
        assert any(e['reasoningEffort'] == 'low' for e in selected['supportedReasoningEfforts'])
        thread = call(name, {'action': 'rpc', 'method': 'thread/start', 'params': {'model': 'gpt-6-astra',
            'modelProvider': 'openai', 'cwd': '/work', 'approvalPolicy': 'never', 'sandbox': 'read-only',
            'ephemeral': False, 'allowProviderModelFallback': False, 'config': {'model_reasoning_effort': 'low'}}})
        report['thread_settings'] = {k: thread.get(k) for k in ('model', 'reasoningEffort', 'instructionSources', 'cwd')}
        assert thread['model'] == 'gpt-6-astra'
        report['skill_inspect'] = json.loads(run('docker', 'exec', name, 'node', '/codex-home/skills/lab-brand-check/scripts/check.mjs', 'inspect').stdout)
        report['stdin_close'] = call(name, {'action': 'close-stdin'})
        time.sleep(1)
        report['after_stdin_close'] = call(name, {'action': 'status'})
        if not report['after_stdin_close']['closed']:
            call(name, {'action': 'stop-server'})
            time.sleep(1)
        report['after_stop'] = call(name, {'action': 'status'})
        assert report['after_stop']['closed']
        report['restart'] = call(name, {'action': 'start'})
        assert report['restart']['pid'] != report['start']['pid']
        call(name, {'action': 'stop-server'})
        time.sleep(.5)
        report['status'] = 'pass'
    except Exception as e:
        report['status'], report['error'] = 'fail', str(e)
    finally:
        report['removed'] = run('docker', 'rm', '-f', name, check=False).returncode == 0
        if (state / 'events.jsonl').exists():
            (out / 'events.jsonl').write_bytes((state / 'events.jsonl').read_bytes())
        report['implementation'] = {p.name: digest(p) for p in [ROOT / n for n in ('adapter.mjs', 'client.mjs', 'trace.mjs', 'probe.py')]}
        save(out / 'report.json', report)
    print(json.dumps({'status': report['status'], 'error': report.get('error')}))


if __name__ == '__main__': main()
