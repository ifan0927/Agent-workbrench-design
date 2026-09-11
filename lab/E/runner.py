"""E-only container adapter. The graph owns workflow and retry decisions."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time

from environment import ROOT, COMMIT, IMAGE, git, run, save, digest, source_state
from probe import call
sys.path.insert(0, str(ROOT.parent / 'A'))
from live import load_auth

MODE = '你正在固定版本的 E 組隔離實驗。只處理提供的任務，不委派、不呼叫網路工具、不更改配置或驗收。使用相關 lab-brand-check skill。不要執行 git commit，host 將保存實際改動。'


class Runner:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.runtime = ROOT / '.runtime' / self.root.name
        self.runtime.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.runtime.chmod(0o700)
        self.root.mkdir(parents=True, exist_ok=True)
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, spec TEXT, name TEXT, cid TEXT, phase TEXT, collected INTEGER DEFAULT 0)')
            db.execute('CREATE TABLE IF NOT EXISTS dispatches (attempt TEXT PRIMARY KEY, at TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS events (seq INTEGER PRIMARY KEY, at TEXT, kind TEXT, data TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS repair (slot INTEGER PRIMARY KEY CHECK(slot=1), attempt TEXT UNIQUE)')

    def db(self):
        db = sqlite3.connect(self.root / 'attempts.sqlite')
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA synchronous=FULL')
        return db

    def event(self, kind, data):
        with self.db() as db:
            db.execute("INSERT INTO events(at,kind,data) VALUES(datetime('now'),?,?)", (kind, json.dumps(data)))

    def row(self, attempt):
        with self.db() as db:
            return dict(db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone())

    def paths(self, attempt):
        return self.runtime / hashlib.sha256(attempt.encode()).hexdigest()[:16]

    def register(self, attempt, spec):
        name = 'awb-e-' + hashlib.sha256((str(self.root) + attempt).encode()).hexdigest()[:16]
        with self.db() as db:
            if spec['mode'] == 'repair':
                old = db.execute('SELECT attempt FROM repair WHERE slot=1').fetchone()
                if old and old['attempt'] != attempt: raise RuntimeError('repair_limit')
                db.execute('INSERT OR IGNORE INTO repair VALUES(1,?)', (attempt,))
            db.execute('INSERT OR IGNORE INTO attempts(id,spec,name,phase) VALUES(?,?,?,?)', (attempt, json.dumps(spec), name, 'prepared'))

    def clone(self, source, work, commit):
        run('git', 'clone', '--no-local', '--no-hardlinks', str(source), str(work))
        git(work, 'remote', 'remove', 'origin')
        git(work, 'checkout', '--detach', commit)
        git(work, 'config', 'user.name', 'E Lab')
        git(work, 'config', 'user.email', 'e-lab@example.invalid')

    def ensure(self, attempt):
        row = self.row(attempt)
        if row['phase'] != 'prepared':
            info = run('docker', 'inspect', row['name'], check=False)
            if info.returncode:
                return {'state': 'unknown'}
            data = json.loads(info.stdout)[0]
            if data['Id'] != row['cid'] or data['Config']['Labels'].get('lab.e.attempt') != attempt:
                return {'state': 'unknown'}
            return {'state': 'existing', 'container': row['cid']}
        spec = json.loads(row['spec'])
        directory = self.paths(attempt)
        directory.mkdir()
        work, state, scripts, inputs = [directory / n for n in ('work', 'state', 'adapter', 'input')]
        for p in (state, scripts, inputs):
            p.mkdir(mode=0o777)
            p.chmod(0o777)
        for n in ('adapter.mjs', 'client.mjs', 'trace.mjs'):
            shutil.copy2(ROOT / n, scripts / n)
        source = Path(spec.get('source', ROOT / 'baseline'))
        self.clone(source, work, spec.get('base', COMMIT))
        home = Path(spec.get('home', directory / 'home'))
        if not home.exists():
            shutil.copytree(ROOT / 'inputs/home', home)
        for p in [home, *(home / 'skills').rglob('*')]:
            if p.is_dir(): p.chmod(0o777)
        save(inputs / 'task.json', spec['task'])
        if spec['mode'] == 'parallel': shutil.copy2(ROOT / 'inputs/barrier.mjs', inputs / 'barrier.mjs')
        if spec.get('test_report'):
            shutil.copy2(spec['test_report'], inputs / 'verification.json')
        readonly = spec['mode'] in ('question', 'review')
        args = ['docker', 'create', '--name', row['name'], '--init', '--label', 'agent-workbench.lab=E', '--label', 'lab.e.attempt=' + attempt,
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=6g', '--cpus=2', '--pids-limit=512',
                '--tmpfs', '/tmp:rw,nosuid,size=1g', '--mount', f'type=bind,src={work},dst=/work' + (',readonly' if readonly else ''),
                '--mount', f'type=bind,src={home},dst=/codex-home', '--mount', f'type=bind,src={state},dst=/state',
                '--mount', f'type=bind,src={scripts},dst=/lab,readonly', '--mount', f'type=bind,src={inputs},dst=/input,readonly',
                '-e', 'E_ATTEMPT=' + attempt, '-e', 'HOME=/tmp', '-e', 'NODE_OPTIONS=--max-old-space-size=4096',
                '-e', 'ASTRO_TELEMETRY_DISABLED=1', '--entrypoint', 'node', IMAGE, '/lab/adapter.mjs']
        with self.db() as db:
            db.execute('UPDATE attempts SET phase=? WHERE id=?', ('create_intent', attempt))
        cid = run(*args).stdout.decode().strip()
        with self.db() as db:
            db.execute('UPDATE attempts SET cid=?,phase=? WHERE id=?', (cid, 'created', attempt))
        run('docker', 'start', cid)
        for _ in range(100):
            if (state / 'events.jsonl').exists(): break
            time.sleep(.1)
        if not readonly and spec['mode'] != 'parallel':
            run('docker', 'exec', cid, 'node', '-e', "require('fs').cpSync('/opt/project/node_modules','/work/node_modules',{recursive:true,verbatimSymlinks:true})", timeout=90)
        started = call(row['name'], {'action': 'start'})
        external, _, _ = load_auth(Path.home() / '.codex/auth.json')
        call(row['name'], {'action': 'rpc', 'method': 'account/login/start', 'params': {'type': 'chatgptAuthTokens', **external}})
        account = call(row['name'], {'action': 'rpc', 'method': 'account/read', 'params': {'refreshToken': False}})
        assert account['account']['type'] == 'chatgpt'
        models = call(row['name'], {'action': 'rpc', 'method': 'model/list', 'params': {'includeHidden': False}})
        model = next(m for m in models['data'] if m['model'] == 'gpt-6-astra')
        assert any(e['reasoningEffort'] == 'low' for e in model['supportedReasoningEfforts'])
        config = call(row['name'], {'action': 'rpc', 'method': 'config/read', 'params': {'cwd': '/work', 'includeLayers': True}})
        assert config['config']['model'] == 'gpt-6-astra'
        assert config['config']['model_reasoning_effort'] == 'low'
        skills = call(row['name'], {'action': 'rpc', 'method': 'skills/list', 'params': {'cwds': ['/work'], 'forceReload': True}})
        selected = [s for d in skills['data'] for s in d['skills'] if s['name'] == 'lab-brand-check' and s['enabled']]
        assert selected
        params = {'model': 'gpt-6-astra', 'modelProvider': 'openai', 'cwd': '/work', 'approvalPolicy': 'never',
                  'sandbox': 'read-only', 'allowProviderModelFallback': False, 'config': {'model_reasoning_effort': 'low'}, 'developerInstructions': MODE}
        if spec.get('resume'):
            params['threadId'] = spec['resume']
            thread = call(row['name'], {'action': 'rpc', 'method': 'thread/resume', 'params': params})
            assert thread['thread']['id'] == spec['resume']
        else:
            params['ephemeral'] = False
            thread = call(row['name'], {'action': 'rpc', 'method': 'thread/start', 'params': params})
        assert thread['model'] == 'gpt-6-astra'
        evidence = {'container_id': cid, 'mode': spec['mode'], 'base': spec.get('base', COMMIT), 'start': started,
                    'thread': json.loads((state / 'thread.json').read_text()), 'skill': selected,
                    'configuration': {k: config['config'].get(k) for k in ('model', 'model_provider', 'model_reasoning_effort', 'web_search')},
                    'config_origins': config.get('origins'), 'input_hash': digest(inputs / 'task.json'),
                    'config_files': {str(p.relative_to(home)): digest(p) for p in [home / 'AGENTS.md', home / 'config.toml', *(home / 'skills').rglob('*')] if p.is_file()}}
        save(self.root / (directory.name + '-preflight.json'), evidence)
        if spec['mode'] == 'review':
            schema = {'type': 'object', 'properties': {'approved': {'type': 'boolean'}, 'findings': {'type': 'array', 'items': {'type': 'string'}}}, 'required': ['approved', 'findings'], 'additionalProperties': False}
            prompt = '這是獨立 fresh review。讀 /input/task.json 與 /input/verification.json，檢查 /work 完整候選及相關指引。不要修改任何檔案。判斷需求正確性、測試是否被弱化、有無範圍外變更。回傳 approved 與 findings JSON。'
        else:
            schema = {'type': 'object', 'properties': {'status': {'type': 'string', 'enum': ['waiting', 'completed']}, 'question': {'type': ['string', 'null']}, 'summary': {'type': 'string'}}, 'required': ['status', 'question', 'summary'], 'additionalProperties': False}
            prompt = '請讀 /input/task.json，依目前 phase 自主完成這一回合。只用本地程式與工具，不要額外委派。最後回傳要求的 JSON。'
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT count(*) FROM dispatches').fetchone()[0] >= 10:
                raise RuntimeError('batch_turn_limit')
            db.execute("INSERT INTO dispatches VALUES(?,datetime('now'))", (attempt,))
            db.execute('UPDATE attempts SET phase=? WHERE id=?', ('dispatch_intent', attempt))
        response = call(row['name'], {'action': 'rpc', 'method': 'turn/start', 'params': {
            'threadId': thread['thread']['id'], 'sandboxPolicy': {'type': 'externalSandbox', 'networkAccess': 'enabled'},
            'input': [{'type': 'text', 'text': prompt}], 'outputSchema': schema}})
        with self.db() as db:
            db.execute('UPDATE attempts SET phase=? WHERE id=?', ('running', attempt))
        self.event('dispatch_acknowledged', {'attempt': attempt, 'container_id': cid, 'thread_id': thread['thread']['id'], 'turn_id': response['turn']['id']})
        return {'state': 'started', 'container': cid}

    def observe(self, attempt):
        row = self.row(attempt)
        path = self.paths(attempt) / 'state/result.json'
        if path.exists():
            result = json.loads(path.read_text())
            return {'state': 'result', 'result': result}
        info = run('docker', 'inspect', row['name'], check=False)
        if info.returncode or not json.loads(info.stdout)[0]['State']['Running']:
            return {'state': 'unknown'}
        return {'state': 'running'}

    def events(self, attempt):
        return [json.loads(line) for line in (self.paths(attempt) / 'state/events.jsonl').read_text().splitlines()]

    def collect(self, attempt):
        rows = self.events(attempt)
        messages = [r['data']['item']['text'] for r in rows if r['kind'] == 'item/completed' and r['data']['item']['type'] == 'agentMessage']
        response = json.loads(messages[-1]) if messages else None
        result = self.observe(attempt)['result']
        if result['turn']['status'] != 'completed':
            raise RuntimeError('model_turn_' + result['turn']['status'])
        assert response is not None
        directory = self.paths(attempt)
        output = self.root / directory.name
        output.mkdir(exist_ok=True)
        for name in ('events.jsonl', 'thread.json', 'dispatch.json', 'result.json'):
            shutil.copy2(directory / 'state' / name, output / name)
        save(output / 'response.json', response)
        usages = [r['data']['tokenUsage'] for r in rows if r['kind'] == 'thread/tokenUsage/updated']
        save(output / 'usage.json', {'scope': 'thread_total', 'completeness': 'reported' if usages else 'unknown', 'value': usages[-1] if usages else None})
        with self.db() as db:
            changed = db.execute('UPDATE attempts SET collected=1 WHERE id=? AND collected=0', (attempt,)).rowcount
        if changed: self.event('result_collected', {'attempt': attempt})
        spec = json.loads(self.row(attempt)['spec'])
        binding = {'commit': spec.get('base', COMMIT), 'requirement_sha256': digest(directory / 'input/task.json'),
                   'attempt': attempt, 'approved': response.get('approved')}
        save(output / 'binding.json', binding)
        return {'response': response, 'binding': binding, 'thread': json.loads((directory / 'state/thread.json').read_text()),
                'home': str(directory / 'home'), 'work': str(directory / 'work'), 'evidence': str(output)}

    def stop(self, attempt):
        row = self.row(attempt)
        self.event('stop_requested', {'attempt': attempt, 'container_id': row['cid']})
        run('docker', 'stop', '-t', '5', row['name'], timeout=15, check=False)
        info = run('docker', 'inspect', row['name'], check=False)
        stopped = info.returncode == 0 and not json.loads(info.stdout)[0]['State']['Running']
        self.event('container_stopped', {'attempt': attempt, 'confirmed': stopped})
        return stopped

    def cancel(self, attempt):
        row = self.row(attempt)
        dispatch = json.loads((self.paths(attempt) / 'state/dispatch.json').read_text())
        self.event('cancel_requested', {'attempt': attempt, 'actor': 'experiment-fixture', 'thread_id': dispatch['threadId'], 'turn_id': dispatch['turnId']})
        native = {'acknowledged': False, 'terminal': None}
        try:
            response = call(row['name'], {'action': 'rpc', 'method': 'turn/interrupt', 'params': {'threadId': dispatch['threadId'], 'turnId': dispatch['turnId']}})
            native['acknowledged'] = response == {}
            end = time.time() + 10
            while time.time() < end:
                observed = self.observe(attempt)
                if observed['state'] == 'result':
                    native['terminal'] = observed['result']['turn']['status']
                    break
                time.sleep(.2)
        except Exception as e: native['error'] = str(e)
        stopped = self.stop(attempt)
        result = {'native': native, 'container_stopped': stopped}
        save(self.root / (self.paths(attempt).name + '-cancel.json'), result)
        return result

    def candidate(self, attempt):
        work = self.paths(attempt) / 'work'
        allowed = {'src/lib/content/news.ts'}
        changed = git(work, 'diff', '--name-only').splitlines()
        assert set(changed) <= allowed, 'existing_files_changed_outside_scope'
        new = git(work, 'ls-files', '--others', '--exclude-standard').splitlines()
        assert all(p.startswith('src/lib/content/') and (p.endswith('.test.ts') or p.endswith('.test.mjs')) for p in new), 'unexpected_untracked_files'
        assert changed, 'no_candidate_change'
        git(work, 'add', '--', *changed, *new)
        git(work, 'commit', '-m', 'E lab: validate news dates and source diagnostics')
        commit = git(work, 'rev-parse', 'HEAD')
        out = self.root / self.paths(attempt).name
        git(work, 'bundle', 'create', str(out / 'candidate.bundle'), 'HEAD')
        diff = run('git', '-C', str(work), 'diff', COMMIT, 'HEAD', '--binary').stdout
        (out / 'candidate.diff').write_bytes(diff)
        result = {'commit': commit, 'tree': git(work, 'rev-parse', 'HEAD^{tree}'), 'bundle': str(out / 'candidate.bundle'), 'bundle_sha256': digest(out / 'candidate.bundle'), 'changed': changed + new}
        save(out / 'candidate.json', result)
        return result

    def cleanup(self):
        with self.db() as db: rows = list(db.execute('SELECT * FROM attempts'))
        for row in rows:
            if row['cid']:
                self.stop(row['id'])
                directory = self.paths(row['id'])
                out = self.root / directory.name
                out.mkdir(exist_ok=True)
                for name in ('events.jsonl', 'thread.json', 'dispatch.json', 'result.json'):
                    if (directory / 'state' / name).exists(): shutil.copy2(directory / 'state' / name, out / name)
                run('docker', 'rm', '-f', row['cid'], check=False)

    def recover_undispatched_preflight(self, attempt):
        row = self.row(attempt)
        assert row['phase'] == 'created'
        with self.db() as db:
            assert db.execute('SELECT count(*) FROM dispatches WHERE attempt=?', (attempt,)).fetchone()[0] == 0
        directory = self.paths(attempt)
        assert not (directory / 'state/dispatch.json').exists()
        assert not any(r['kind'] in ('turn/started', 'turn/completed') for r in self.events(attempt))
        assert run('docker', 'inspect', row['cid'], check=False).returncode != 0
        archive = directory.with_name(directory.name + '-undispatched')
        directory.rename(archive)
        with self.db() as db:
            db.execute('UPDATE attempts SET phase=?,cid=NULL,name=? WHERE id=?', ('prepared', row['name'] + '-p2', attempt))
        self.event('preflight_reprepared', {'attempt': attempt, 'old_container': row['cid'], 'archive': str(archive), 'proof': 'no_host_dispatch_intent_no_adapter_dispatch_no_turn_events'})
