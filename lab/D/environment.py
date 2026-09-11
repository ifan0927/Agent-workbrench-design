"""D4: a fixed local Git fixture, real build, two isolated services and test workers."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import urllib.request
from runner import ROOT, docker, save


def wait_for(predicate, seconds=25):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.15)
    raise TimeoutError('bounded observation expired')


def git(path, *args):
    env = {**os.environ, 'GIT_AUTHOR_DATE': '2026-09-10T00:00:00Z',
           'GIT_COMMITTER_DATE': '2026-09-10T00:00:00Z'}
    return subprocess.check_output(['git', '-c', 'advice.detachedHead=false', '-c', 'user.name=Lab D', '-c',
        'user.email=lab-d@example.invalid', '-C', str(path), *args], env=env, text=True).strip()


def run_environment(runtime, evidence):
    runtime, evidence = Path(runtime), Path(evidence)
    runtime.mkdir(parents=True)
    evidence.mkdir(parents=True)
    owner = 'd-env-' + hashlib.sha256(str(runtime).encode()).hexdigest()[:12]
    repo = runtime / 'repo'
    repo.mkdir()
    shutil.copytree(ROOT / 'fixture', repo / 'fixture')
    for name in ('Dockerfile', '.dockerignore'):
        shutil.copyfile(ROOT / name, repo / name)
    git(repo, 'init', '-q', '-b', 'main')
    git(repo, 'add', '.')
    git(repo, 'commit', '-q', '-m', 'Fixed D4 environment fixture')
    commit = git(repo, 'rev-parse', 'HEAD')
    git(repo, 'bundle', 'create', str(evidence / 'fixture.bundle'), 'HEAD')
    image = owner + ':fixture'
    checks, tasks, names, networks = {}, [], [], []
    try:
        build = docker('build', '--pull=false', '-t', image, str(repo), timeout=90)
        (evidence / 'build.txt').write_text(build.stdout + build.stderr)
        checks['image_build'] = build.returncode == 0
        image_id = json.loads(docker('image', 'inspect', image).stdout)[0]['Id']
        for index in range(2):
            base = runtime / str(index)
            base.mkdir()
            work, data, barrier = base / 'work', base / 'data', base / 'barrier'
            git(base, 'clone', '-q', str(evidence / 'fixture.bundle'), str(work))
            data.mkdir()
            barrier.mkdir()
            network = f'{owner}-{index}'
            docker('network', 'create', '--label', 'agent-workbench.lab=D',
                   '--label', 'lab.d.owner=' + owner, network)
            networks.append(network)
            service, worker = network + '-service', network + '-worker'
            common = ['--label', 'agent-workbench.lab=D', '--label', 'lab.d.owner=' + owner,
                      '--network', network, '--read-only', '--cap-drop', 'ALL',
                      '--security-opt', 'no-new-privileges', '--user', 'node',
                      '--pids-limit', '64', '--memory', '192m', '--cpus', '0.5']
            docker('create', '--name', service, *common, '--network-alias', 'service',
                   '-p', '127.0.0.1::8080', '--mount', f'type=bind,src={data},dst=/data', image_id)
            names.append(service)
            docker('start', service)
            info = json.loads(docker('inspect', service).stdout)[0]
            port = info['NetworkSettings']['Ports']['8080/tcp'][0]['HostPort']

            def healthy():
                try:
                    return urllib.request.urlopen(f'http://127.0.0.1:{port}/health', timeout=1).read() == b'ready'
                except OSError:
                    return False

            wait_for(healthy)
            token = f'dataset-{index}'
            docker('create', '--name', worker, *common, '--tmpfs', '/tmp:rw,nosuid,size=32m',
                   '-e', 'npm_config_cache=/tmp/npm', '-e', 'FIXTURE_VALUE=' + token,
                   '--mount', f'type=bind,src={work / "fixture"},dst=/work',
                   '--mount', f'type=bind,src={barrier},dst=/barrier,readonly',
                   '-w', '/work', image_id, 'sh', '-c', 'npm run build && npm test')
            names.append(worker)
            tasks.append({'worker': worker, 'service': service, 'port': port, 'work': str(work),
                          'data': str(data), 'barrier': str(barrier), 'token': token})
        with ThreadPoolExecutor(2) as pool:
            list(pool.map(lambda t: docker('start', t['worker']), tasks))
        wait_for(lambda: all((Path(t['work']) / 'fixture/test-written').exists() for t in tasks))
        checks['both_workers_running_at_barrier'] = all(
            json.loads(docker('inspect', t['worker']).stdout)[0]['State']['Running'] for t in tasks)
        for task in tasks:
            (Path(task['barrier']) / 'release').touch()
        for index, task in enumerate(tasks):
            result = docker('wait', task['worker'], timeout=30)
            logs = docker('logs', task['worker'])
            (evidence / f'test-{index}.txt').write_text(logs.stdout + logs.stderr)
            output = Path(task['work']) / 'fixture/environment-result.json'
            checks[f'test_{index}'] = (result.stdout.strip() == '0' and output.exists()
                and json.loads(output.read_text()) == {'token': task['token'], 'isolated': True})
            checks[f'data_{index}'] = (Path(task['data']) / 'value').read_text() == task['token']
            checks[f'fixed_commit_{index}'] = git(Path(task['work']), 'rev-parse', 'HEAD') == commit
            shutil.copyfile(output, evidence / f'environment-{index}.json')
            task['state'] = json.loads(docker('inspect', task['worker']).stdout)[0]['State']
        checks['unique_ports'] = len({t['port'] for t in tasks}) == 2
        checks['unique_work_and_data'] = len({t['work'] for t in tasks} | {t['data'] for t in tasks}) == 4
    finally:
        for name in names:
            docker('rm', '-f', name)
        for network in networks:
            docker('network', 'rm', network)
        if names:
            docker('image', 'rm', image)
    checks['container_cleanup'] = not docker('ps', '-aq', '--filter', 'label=lab.d.owner=' + owner).stdout.strip()
    checks['network_cleanup'] = not docker('network', 'ls', '-q', '--filter', 'label=lab.d.owner=' + owner).stdout.strip()
    shutil.rmtree(runtime)
    checks['directory_cleanup'] = not runtime.exists()
    return {'mode': 'real_docker_synthetic_git_repo', 'checks': checks, 'passed': all(checks.values()),
            'commit': commit, 'image_id': image_id, 'tasks': tasks}
