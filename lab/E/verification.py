"""Rebuild a candidate from its bundle and apply controller-owned acceptance."""
import json
import re
import shutil
import uuid
from pathlib import Path
from environment import ROOT, IMAGE, run, git, save, digest


def verify(runner, candidate, label, acceptance_only=False):
    directory = runner.runtime / ('verify-' + label)
    directory.mkdir()
    out = runner.root / ('verify-' + label)
    out.mkdir()
    work = directory / 'work'
    runner.clone(candidate['bundle'], work, candidate['commit'])
    assert git(work, 'rev-parse', 'HEAD^{tree}') == candidate['tree']
    name = 'awb-e-verify-' + uuid.uuid4().hex[:10]
    report = {'candidate': candidate, 'commands': [], 'acceptance_sha256': digest(ROOT / 'inputs/acceptance.test.ts'), 'status': 'running'}
    try:
        cid = run('docker', 'run', '-d', '--name', name, '--init', '--label', 'agent-workbench.lab=E', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--network=none', '--memory=6g', '--cpus=2', '--pids-limit=512',
            '--tmpfs', '/tmp:rw,nosuid,size=1g', '--mount', f'type=bind,src={work},dst=/work',
            '--mount', f'type=bind,src={ROOT / "inputs"},dst=/input,readonly',
            '-e', 'HOME=/tmp', '-e', 'NODE_OPTIONS=--max-old-space-size=4096', '-e', 'ASTRO_TELEMETRY_DISABLED=1',
            '--entrypoint', 'node', IMAGE, '-e', 'setInterval(()=>{},1000)').stdout.decode().strip()
        report['container_id'] = cid
        run('docker', 'exec', cid, 'node', '-e', "require('fs').cpSync('/opt/project/node_modules','/work/node_modules',{recursive:true,verbatimSymlinks:true})", timeout=90)
        def gate(label, args):
            p = run('docker', 'exec', cid, *args, timeout=620, check=False)
            text = (p.stdout + p.stderr).decode(errors='replace')
            (out / (label + '.log')).write_text(text)
            report['commands'].append({'label': label, 'command': args, 'exit_code': p.returncode})
            save(out / 'report.json', report)
            return p.returncode, text
        for label, args in ([] if acceptance_only else [('check', ['npm', 'run', 'check']), ('test', ['npm', 'test'])]):
            code, _ = gate(label, args)
            if code: raise RuntimeError(label + '_failed')
        shutil.copy2(ROOT / 'inputs/acceptance.test.ts', work / 'e-acceptance.test.ts')
        code, _ = gate('acceptance', ['npm', 'exec', '--', 'vitest', 'run', 'e-acceptance.test.ts'])
        assert digest(work / 'e-acceptance.test.ts') == report['acceptance_sha256']
        (work / 'e-acceptance.test.ts').unlink()
        if code: raise RuntimeError('fixed_acceptance_failed')
        if acceptance_only:
            report['status'] = 'pass'
            return report, str(out / 'report.json')
        code, _ = gate('build', ['node', '/input/home/skills/lab-brand-check/scripts/check.mjs', 'build'])
        if code: raise RuntimeError('valid_build_failed')
        assert not git(work, 'diff', '--name-only')
        # Only this throwaway validation checkout receives the negative article.
        fixture = work / 'content/news/e-invalid-date.mdx'
        template = next((work / 'content/news').glob('*.mdx')).read_text()
        injected, count = re.subn(r'^date:.*$', 'date: 2026-02-29', template, count=1, flags=re.M)
        assert count == 1
        injected = re.sub(r'^slug:.*$', 'slug: e-invalid-date', injected, count=1, flags=re.M)
        fixture.write_text(injected)
        report['negative_article'] = {'path': str(fixture.relative_to(work)), 'sha256': digest(fixture)}
        code, text = gate('negative-build', ['node', '/input/home/skills/lab-brand-check/scripts/check.mjs', 'build'])
        report['negative_diagnostic'] = code != 0 and 'e-invalid-date.mdx' in text and bool(re.search(r'date|日期', text, re.I))
        fixture.unlink()
        assert not git(work, 'diff', '--name-only')
        if not report['negative_diagnostic']: raise RuntimeError('negative_build_diagnostic_failed')
        report['status'] = 'pass'
    except Exception as e:
        report['status'], report['error'] = 'fail', str(e)
    finally:
        report['removed'] = run('docker', 'rm', '-f', name, check=False).returncode == 0
        save(out / 'report.json', report)
    return report, str(out / 'report.json')
