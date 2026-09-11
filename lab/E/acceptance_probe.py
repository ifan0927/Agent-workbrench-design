"""Confirm fixed date acceptance exposes the untouched baseline defect; no model."""
import argparse
import json
import shutil
from environment import ROOT, IMAGE, COMMIT, run, git, save, digest

parser = argparse.ArgumentParser()
parser.add_argument('--report', default='acceptance-probe')
args = parser.parse_args()
assert args.report.replace('-', '').isalnum()
out = ROOT / 'results' / args.report
out.mkdir()
out.chmod(0o777)
runtime = ROOT / '.runtime' / args.report
runtime.mkdir()
work = runtime / 'work'
run('git', 'clone', '--no-local', '--no-hardlinks', str(ROOT / 'baseline'), str(work))
git(work, 'remote', 'remove', 'origin')
shutil.copy2(ROOT / 'inputs/acceptance.test.ts', work / 'e-acceptance.test.ts')
name = 'awb-e-acceptance-probe'
report = {'kind': 'real_container_fixed_acceptance_no_model', 'model_turns': 0, 'baseline': COMMIT,
          'acceptance_sha256': digest(ROOT / 'inputs/acceptance.test.ts')}
try:
    p = run('docker', 'run', '--name', name, '--init', '--label', 'agent-workbench.lab=E', '--read-only',
            '--cap-drop=ALL', '--security-opt=no-new-privileges', '--network=none', '--memory=2g', '--pids-limit=128',
            '--tmpfs', '/tmp:rw,nosuid,size=256m', '--mount', f'type=bind,src={work},dst=/work',
            '--mount', f'type=bind,src={out},dst=/out', '-e', 'HOME=/tmp', '--entrypoint', 'node', IMAGE,
            '-e', "require('fs').cpSync('/opt/project/node_modules','/work/node_modules',{recursive:true,verbatimSymlinks:true});process.exitCode=require('child_process').spawnSync('npm',['exec','--','vitest','run','e-acceptance.test.ts','--reporter=json','--outputFile=/out/vitest.json'],{stdio:'inherit'}).status??1", check=False)
    (out / 'command.log').write_bytes(p.stdout + p.stderr)
    tests = json.loads((out / 'vitest.json').read_text())
    report.update(exit_code=p.returncode, total=tests['numTotalTests'], passed=tests['numPassedTests'], failed=tests['numFailedTests'])
    report['status'] = 'pass' if p.returncode != 0 and tests['numFailedTests'] > 0 and tests['numPassedTests'] >= 12 and tests['numTotalTests'] == 45 else 'fail'
    report['meaning'] = '驗收能抓出原始基準的日期缺陷；不是修正候選已通過。'
finally:
    report['removed'] = run('docker', 'rm', '-f', name, check=False).returncode == 0
    save(out / 'report.json', report)
print(json.dumps(report, ensure_ascii=False))
