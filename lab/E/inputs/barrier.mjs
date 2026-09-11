import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { spawn } from 'node:child_process';
const task = JSON.parse(readFileSync('/input/task.json', 'utf8'));
const fixture = spawn('node', ['scripts/brand-api-fixture.mjs'], { cwd: '/work', env: { ...process.env, PORT: '4177' }, stdio: 'ignore' });
const save = (name, data) => writeFileSync(`/work/${name}.json`, JSON.stringify(data));
try {
  let api;
  for (let i = 0; i < 30; i++) {
    try { api = await (await fetch('http://127.0.0.1:4177/api/v1/public/properties/availability')).json(); break; } catch {}
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!api?.items?.length) throw new Error('fixture_failed');
  save('e5-partial', { lane: task.lane, fixturePid: fixture.pid, items: api.items.length });
  console.log('E5_BARRIER_READY ' + task.lane);
  let tick = 0;
  while (!existsSync('/state/release')) {
    save('e5-progress', { lane: task.lane, tick: ++tick, time: new Date().toISOString() });
    if (tick > 220) throw new Error('barrier_deadline');
    await new Promise(resolve => setTimeout(resolve, 1000));
  }
  save('e5-result', { lane: task.lane, tick: ++tick, time: new Date().toISOString(), complete: true });
  console.log('E5_BARRIER_COMPLETE ' + task.lane);
} finally { fixture.kill('SIGTERM'); }
