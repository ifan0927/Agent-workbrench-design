"""Docker facts only: register, ensure, observe, stop, and collect. No workflow policy."""

from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parent
IMAGE = 'node:22.22.0-bookworm'


def docker(*args, check=True, timeout=30):
    return subprocess.run(['docker', *args], text=True, capture_output=True,
                          check=check, timeout=timeout)


def save(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as stream:
        json.dump(data, stream, indent=2, sort_keys=True)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


@contextmanager
def lock(path):
    with Path(path).open('a') as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def crash(point):
    if os.environ.get('LAB_D_CRASH') == point:
        os._exit(86)


class Runner:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.owner = 'd-' + hashlib.sha256(str(self.root).encode()).hexdigest()[:16]
        self.db = self.root / 'attempts.sqlite'
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS attempts (
                id TEXT PRIMARY KEY, mode TEXT NOT NULL, name TEXT NOT NULL UNIQUE,
                phase TEXT NOT NULL, cid TEXT, stopped INTEGER NOT NULL DEFAULT 0)''')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=30)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def record(self, attempt):
        with self.connect() as db:
            row = db.execute('SELECT * FROM attempts WHERE id=?', (attempt,)).fetchone()
            return dict(row) if row else None

    def register(self, attempt, mode):
        if mode not in ('question', 'complete', 'tree'):
            raise ValueError('unsupported mode')
        name = self.owner + '-' + hashlib.sha256(attempt.encode()).hexdigest()[:16]
        with self.connect() as db:
            db.execute('INSERT OR IGNORE INTO attempts(id,mode,name,phase) VALUES(?,?,?,?)',
                       (attempt, mode, name, 'prepared'))
        row = self.record(attempt)
        if row['mode'] != mode:
            raise ValueError('attempt input changed')
        self.output(attempt).mkdir(exist_ok=True)
        return row

    def output(self, attempt):
        # Paths use a digest, never caller-supplied path components.
        return self.root / hashlib.sha256(attempt.encode()).hexdigest()[:24]

    def inspect(self, row):
        result = docker('inspect', row['name'], check=False)
        if result.returncode:
            if 'No such object:' in result.stderr:
                return None
            raise RuntimeError('docker observation unavailable')
        info = json.loads(result.stdout)[0]
        labels = info['Config'].get('Labels') or {}
        if (labels.get('agent-workbench.lab') != 'D'
                or labels.get('lab.d.owner') != self.owner
                or labels.get('lab.d.attempt') != row['id']
                or (row['cid'] and row['cid'] != info['Id'])):
            raise RuntimeError('container identity mismatch')
        return info

    def ensure(self, attempt):
        with lock(self.root / ('attempt-' + hashlib.sha256(attempt.encode()).hexdigest() + '.lock')):
            row = self.record(attempt)
            if row is None:
                raise ValueError('attempt must be persisted before dispatch')
            if row['stopped']:
                return {'state': 'cancel_requested'}
            info = self.inspect(row)
            if info is None:
                if row['phase'] != 'prepared':
                    return {'state': 'unknown', 'reason': 'container_missing_after_intent'}
                crash('before_create')
                # Once intent is durable, absence cannot prove that launch never happened.
                with self.connect() as db:
                    db.execute("UPDATE attempts SET phase='intent' WHERE id=?", (attempt,))
                crash('after_intent')
                docker('create', '--name', row['name'], '--label', 'agent-workbench.lab=D',
                       '--label', 'lab.d.owner=' + self.owner, '--label', 'lab.d.attempt=' + attempt,
                       '--restart', 'no', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                       '--security-opt', 'no-new-privileges', '--user', 'node',
                       '--pids-limit', '64', '--memory', '128m', '--cpus', '0.5',
                       '--mount', f'type=bind,src={ROOT / "worker.cjs"},dst=/worker.cjs,readonly',
                       '--mount', f'type=bind,src={self.output(attempt)},dst=/out',
                       IMAGE, 'node', '/worker.cjs', attempt, row['mode'])
                crash('after_create')
                info = self.inspect(row)
            with self.connect() as db:
                db.execute("UPDATE attempts SET phase='bound',cid=? WHERE id=?", (info['Id'], attempt))
            if info['State']['Status'] == 'created':
                crash('before_start')
                docker('start', info['Id'])
                crash('after_start')
            # Never restart an exited container, including one without a result.
            return self.observe(attempt)

    def observe(self, attempt):
        row = self.record(attempt)
        info = self.inspect(row)
        if info is None:
            return {'state': 'unknown', 'reason': 'container_missing'}
        state = info['State']
        if state['Running']:
            return {'state': 'running', 'cid': info['Id']}
        path = self.output(attempt) / 'result.json'
        if row['stopped']:
            return {'state': 'stopped', 'cid': info['Id']}
        if state['Status'] == 'exited' and state['ExitCode'] == 0 and path.exists():
            try:
                result = json.loads(path.read_text())
                expected = 'waiting' if row['mode'] == 'question' else 'complete'
                if (result['attempt'] != attempt or result['status'] != expected
                        or result['value'] != 42
                        or result['question'] != ('continue-work' if expected == 'waiting' else None)):
                    raise ValueError('wrong result binding')
            except (ValueError, KeyError, TypeError):
                return {'state': 'invalid_result'}
            return {'state': 'result', 'result': result,
                    'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'cid': info['Id']}
        return {'state': state['Status'], 'exit_code': state['ExitCode'], 'cid': info['Id']}

    def stop(self, attempt):
        with lock(self.root / ('attempt-' + hashlib.sha256(attempt.encode()).hexdigest() + '.lock')):
            with self.connect() as db:
                db.execute('UPDATE attempts SET stopped=1 WHERE id=?', (attempt,))
            crash('before_stop')
            try:
                row = self.record(attempt)
                info = self.inspect(row)
                if info is None:
                    return {'state': 'unknown', 'reason': 'cannot_confirm_stop'}
                if info['State']['Running']:
                    docker('stop', '--time', '1', info['Id'], timeout=10)
                crash('after_stop')
                observed = self.inspect(row)
                return {'state': 'stopped' if observed and not observed['State']['Running'] else 'unknown',
                        'cid': info['Id']}
            except (RuntimeError, subprocess.SubprocessError):
                return {'state': 'unknown', 'reason': 'stop_observation_unavailable'}

    def collect(self, attempt, destination):
        # Retain only known artifacts, never a directory-wide host copy.
        artifacts = {}
        for name in ('launches.jsonl', 'partial.json', 'tree.json', 'heartbeat', 'result.json'):
            source = self.output(attempt) / name
            if source.is_file():
                data = source.read_bytes()
                target = Path(destination) / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                artifacts[name] = hashlib.sha256(data).hexdigest()
        return artifacts

    def cleanup(self):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute('SELECT * FROM attempts')]
        removed = []
        for row in rows:
            info = self.inspect(row)
            if info:
                docker('rm', '-f', info['Id'])
                removed.append(info['Id'])
        return removed
