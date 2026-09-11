"""Prepare an independent fixed repository and run the unmodified E0 gates."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import uuid

ROOT = Path(__file__).resolve().parent
# Set this explicitly to a compatible local source; private repository data is not published.
SOURCE = Path(os.environ.get('LAB_E_SOURCE', str(Path.home() / 'Developer/active/brand-frontend'))).expanduser()
COMMIT = '506158ab49b672dc8e86604d8f1f4dca28a9b340'
BASE_IMAGE = 'agent-workbench-lab-a:0.153.4'
IMAGE = 'agent-workbench-lab-e:0.153.4'


def run(*args, cwd=None, timeout=60, check=True):
    env = {k: os.environ[k] for k in ('PATH', 'HOME', 'TMPDIR') if k in os.environ}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null', GIT_OPTIONAL_LOCKS='0')
    p = subprocess.run(args, cwd=cwd, env=env, capture_output=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'command_failed:{args[0]}:{p.returncode}: {p.stderr.decode()[-2000:]}')
    return p


def git(repo, *args):
    return run('git', '-C', str(repo), *args).stdout.decode().strip()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    with temp.open('w') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())
    temp.replace(path)


def source_state(repo):
    names = run('git', '-C', str(repo), 'ls-files', '-z').stdout.decode().split('\0')
    files = {}
    for name in filter(None, names):
        path = repo / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError('unsupported_tracked_file:' + name)
        files[name] = digest(path)
    return {'head': git(repo, 'rev-parse', 'HEAD'),
            'status': git(repo, 'status', '--porcelain=v1', '--untracked-files=all'),
            'files': files}


def prepare(out):
    before = source_state(SOURCE)
    save(out / 'source-before.json', before)
    assert git(SOURCE, 'rev-parse', '--is-shallow-repository') == 'false'
    assert not run('git', '-C', str(SOURCE), 'config', '--get', 'extensions.partialClone', check=False).stdout
    assert not (SOURCE / '.git/objects/info/alternates').exists()
    assert not list((SOURCE / '.git/objects/pack').glob('*.promisor'))
    git(SOURCE, 'cat-file', '-e', COMMIT + '^{commit}')
    modes = git(SOURCE, 'ls-tree', '-r', COMMIT)
    assert all(line.startswith(('100644 ', '100755 ')) for line in modes.splitlines())
    baseline = ROOT / 'baseline'
    baseline.mkdir()
    run('git', 'clone', '--mirror', '--no-local', '--no-hardlinks', str(SOURCE), str(baseline / '.git'))
    (baseline / '.git/config').write_text('[core]\nrepositoryformatversion = 0\nbare = false\nfilemode = true\nlogallrefupdates = true\n')
    shutil.rmtree(baseline / '.git/hooks', ignore_errors=True)
    git(baseline, 'checkout', '--detach', '--force', COMMIT)
    git(baseline, 'fsck', '--full')
    objects = lambda p: sorted(git(p, 'rev-list', '--objects', '--all').splitlines())
    assert objects(SOURCE) == objects(baseline)
    assert git(baseline, 'rev-parse', 'HEAD^{tree}') == git(SOURCE, 'rev-parse', COMMIT + '^{tree}')
    assert not git(baseline, 'remote')
    assert not (baseline / '.git/objects/info/alternates').exists()
    for p in baseline.rglob('*'):
        assert not p.is_symlink()
        if p.is_file():
            assert p.stat().st_nlink == 1
    expected = {}
    for name in source_state(baseline)['files']:
        expected[name] = hashlib.sha256(run('git', '-C', str(SOURCE), 'show', f'{COMMIT}:{name}').stdout).hexdigest()
    assert source_state(baseline)['files'] == expected
    manifest = {'commit': COMMIT, 'tree': git(baseline, 'rev-parse', 'HEAD^{tree}'),
                'files': expected, 'reachable_objects_sha256': hashlib.sha256('\n'.join(objects(baseline)).encode()).hexdigest(),
                'reachable_object_count': len(objects(baseline)), 'commits': int(git(baseline, 'rev-list', '--all', '--count')),
                'independent_objects': True, 'remote_absent': True, 'baseline': str(baseline)}
    save(out / 'baseline.json', manifest)
    for p in baseline.rglob('*'):
        p.chmod(p.stat().st_mode & ~0o222)
    baseline.chmod(0o555)
    assert before == source_state(SOURCE)
    return baseline


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='e0')
    parser.add_argument('--reuse-baseline', action='store_true')
    args = parser.parse_args()
    assert args.report.replace('-', '').isalnum()
    out = ROOT / 'results' / args.report
    out.mkdir(parents=True)
    report = {'status': 'running', 'model_turns': 0, 'commands': [], 'limits': {'setup_seconds': 900, 'gate_seconds': 600, 'memory_bytes': 6 * 1024**3, 'node_heap_mib': 4096, 'cpus': 2, 'pids': 512}}
    save(out / 'report.json', report)
    name = 'awb-e-e0-' + uuid.uuid4().hex[:10]
    try:
        if args.reuse_baseline:
            baseline = ROOT / 'baseline'
            save(out / 'source-before.json', source_state(SOURCE))
            original = json.loads((ROOT / 'results/e0/baseline.json').read_text())
            assert source_state(baseline)['files'] == original['files']
            assert git(baseline, 'rev-parse', 'HEAD') == COMMIT
            git(baseline, 'fsck', '--full')
            save(out / 'baseline.json', original)
        else:
            baseline = prepare(out)
        report['implementation'] = {p.name: digest(p) for p in (ROOT / 'environment.py', ROOT / 'gates.mjs')}
        runtime = ROOT / '.runtime' / args.report
        context = runtime / 'context'
        context.mkdir(parents=True)
        archive = runtime / 'source.tar'
        run('git', '-C', str(baseline), 'archive', '--format=tar', '-o', str(archive), COMMIT)
        with tarfile.open(archive) as tar:
            tar.extractall(context / 'project', filter='data')
        shutil.copy2(ROOT / 'gates.mjs', context / 'gates.mjs')
        base = json.loads(run('docker', 'image', 'inspect', BASE_IMAGE).stdout)[0]
        report['base_image_id'] = base['Id']
        (context / 'Dockerfile').write_text('FROM ' + BASE_IMAGE + '\nUSER root\nCOPY --chown=node:node project/ /opt/project/\nCOPY gates.mjs /opt/lab/gates.mjs\nUSER node\nWORKDIR /opt/project\nRUN npm ci --no-audit --no-fund && npm cache clean --force\nWORKDIR /work\nENTRYPOINT ["node", "/opt/lab/gates.mjs"]\n')
        started = time.time()
        p = run('docker', 'build', '--pull=false', '--progress=plain', '-t', IMAGE, str(context), timeout=900, check=False)
        (out / 'image-build.log').write_bytes(p.stdout + p.stderr)
        report['commands'].append({'command': 'docker build (npm ci from unchanged lockfile)', 'exit_code': p.returncode, 'seconds': time.time() - started})
        save(out / 'report.json', report)
        if p.returncode:
            raise RuntimeError('dependency_image_failed')
        inspect = json.loads(run('docker', 'image', 'inspect', IMAGE).stdout)[0]
        report['image'] = {k: inspect.get(k) for k in ('Id', 'RepoDigests', 'Size', 'Architecture', 'Os')}
        work = runtime / 'work'
        work.mkdir(mode=0o777)
        work.chmod(0o777)
        args = ['docker', 'create', '--name', name, '--init', '--label', 'agent-workbench.lab=E', '--label', 'lab.e.slice=E0',
                '--read-only', '--cap-drop=ALL', '--security-opt=no-new-privileges', '--memory=6g', '--cpus=2', '--pids-limit=512',
                '--network=none', '--tmpfs', '/tmp:rw,nosuid,size=1g', '--mount', f'type=bind,src={work},dst=/work',
                '-e', 'HOME=/tmp/home', '-e', 'SITE_URL=https://example.com', '-e', 'BRAND_API_BASE_URL=http://127.0.0.1:4177',
                '-e', 'PORT=4177', '-e', 'ASTRO_TELEMETRY_DISABLED=1', '-e', 'NODE_OPTIONS=--max-old-space-size=4096', IMAGE]
        cid = run(*args).stdout.decode().strip()
        report['container_id'] = cid
        report['container_command'] = args
        save(out / 'report.json', report)
        p = run('docker', 'start', '-a', cid, timeout=1850, check=False)
        (out / 'container.log').write_bytes(p.stdout + p.stderr)
        info = json.loads(run('docker', 'inspect', cid).stdout)[0]
        report['container_state'] = info['State']
        report['mounts'] = info['Mounts']
        report['gates'] = json.loads((work / 'e0-gates.json').read_text())
        shutil.copy2(work / 'e0-gates.json', out / 'gates.json')
        for log in work.glob('e0-*.log'):
            shutil.copy2(log, out / log.name)
        report['tracked_files_unchanged'] = all(digest(work / path) == h for path, h in json.loads((out / 'baseline.json').read_text())['files'].items())
        report['status'] = 'pass' if info['State']['ExitCode'] == 0 and report['tracked_files_unchanged'] and all(g['exit_code'] == 0 for g in report['gates']['commands']) else 'fail'
    except Exception as e:
        report['status'] = 'fail'
        report['error'] = str(e)
    finally:
        after = source_state(SOURCE)
        save(out / 'source-after.json', after)
        report['source_unchanged'] = after == json.loads((out / 'source-before.json').read_text())
        if not report['source_unchanged']:
            report['status'] = 'fail'
        cleanup = run('docker', 'rm', '-f', name, check=False)
        report['container_removed'] = cleanup.returncode == 0
        save(out / 'report.json', report)
    print(json.dumps({'status': report['status'], 'error': report.get('error'), 'report': str(out / 'report.json')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
