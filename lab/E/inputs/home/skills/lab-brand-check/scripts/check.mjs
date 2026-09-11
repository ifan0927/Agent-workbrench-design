import { readFileSync } from 'node:fs';
import { spawn, spawnSync } from 'node:child_process';
const mode = process.argv[2];
if (mode === 'inspect') {
  console.log(JSON.stringify({ cwd: process.cwd(), node: process.version,
    package: JSON.parse(readFileSync('package.json', 'utf8')).name,
    fixtureHasLoopback: readFileSync('scripts/brand-api-fixture.mjs', 'utf8').includes("'127.0.0.1'"),
    sourceBytes: readFileSync('src/lib/content/news.ts').length }));
} else if (mode === 'test') {
  const env = { ...process.env };
  delete env.SITE_URL; delete env.BRAND_API_BASE_URL;
  const p = spawnSync('npm', ['test'], { stdio: 'inherit', env, timeout: 600000 });
  process.exitCode = p.status ?? 1;
} else if (mode === 'build') {
  const env = { ...process.env, SITE_URL: 'https://example.com', BRAND_API_BASE_URL: 'http://127.0.0.1:4177', PORT: '4177', ASTRO_TELEMETRY_DISABLED: '1' };
  delete env.TINA_BRANCH; delete env.TINA_CLIENT_ID; delete env.TINA_TOKEN;
  const fixture = spawn('node', ['scripts/brand-api-fixture.mjs'], { env, stdio: 'ignore' });
  try {
    let ready = false;
    for (let i = 0; i < 30; i++) {
      try { ready = (await fetch(env.BRAND_API_BASE_URL + '/api/v1/public/properties/availability')).ok; } catch {}
      if (ready) break;
      await new Promise(resolve => setTimeout(resolve, 1000));
    }
    if (!ready) throw new Error('fixture_not_ready');
    const p = spawnSync('npm', ['run', 'build'], { stdio: 'inherit', env, timeout: 600000 });
    process.exitCode = p.status ?? 1;
  } finally { fixture.kill('SIGTERM'); }
} else throw new Error('expected inspect, test, or build');
