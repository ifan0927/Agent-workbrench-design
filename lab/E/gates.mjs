import { cpSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';

mkdirSync('/tmp/home', { recursive: true });
cpSync('/opt/project', '/work', { recursive: true, verbatimSymlinks: true });
const report = { commands: [], environment: { node: process.version, site: process.env.SITE_URL, api: process.env.BRAND_API_BASE_URL, tinaCloudConfigured: ['TINA_BRANCH', 'TINA_CLIENT_ID', 'TINA_TOKEN'].some(k => Boolean(process.env[k])) } };
const save = () => writeFileSync('/work/e0-gates.json', JSON.stringify(report, null, 2));
let fixture;
let failed = false;
try {
  for (const [label, args] of [['check', ['run', 'check']], ['test', ['test']], ['build', ['run', 'build']]]) {
    if (label === 'build') {
      fixture = spawn('node', ['scripts/brand-api-fixture.mjs'], { cwd: '/work', stdio: 'ignore' });
      let ready = false;
      for (let attempt = 0; attempt < 30; attempt++) {
        try { ready = (await fetch('http://127.0.0.1:4177/api/v1/public/properties/availability')).ok; } catch {}
        if (ready) break;
        await new Promise(resolve => setTimeout(resolve, 1000));
      }
      if (!ready) throw new Error('fixture_not_ready');
    }
    const started = Date.now();
    const env = { ...process.env };
    if (label !== 'build') {
      delete env.SITE_URL;
      delete env.BRAND_API_BASE_URL;
      delete env.PORT;
    }
    const p = spawnSync('npm', args, { cwd: '/work', env, encoding: 'utf8', timeout: 600000, maxBuffer: 16 * 1024 * 1024 });
    writeFileSync(`/work/e0-${label}.log`, (p.stdout ?? '') + (p.stderr ?? ''));
    report.commands.push({ command: ['npm', ...args], exit_code: p.status, signal: p.signal, error: p.error?.code, seconds: (Date.now() - started) / 1000 });
    save();
    if (p.status !== 0) { failed = true; break; }
  }
} catch (e) {
  report.error = String(e);
  failed = true;
} finally {
  fixture?.kill('SIGTERM');
  try { report.memory_peak_bytes = Number(readFileSync('/sys/fs/cgroup/memory.peak', 'utf8')); } catch { report.memory_peak_bytes = null; }
  report.disk_kib = spawnSync('du', ['-sk', '/work'], { encoding: 'utf8' }).stdout?.trim();
  save();
}
process.exitCode = failed ? 1 : 0;
