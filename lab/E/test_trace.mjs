import assert from 'node:assert/strict';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { Trace } from './trace.mjs';

const root = mkdtempSync(join(tmpdir(), 'awb-e-trace-'));
try {
  const path = join(root, 'events.jsonl');
  const secret = 'canary-secret-cross-delta-1937';
  const trace = new Trace(path, { generation: 'one', attempt: 'synthetic' }, [secret]);
  const ids = { threadId: 't', turnId: 'u', itemId: 'i' };
  for (const delta of ['before ', secret.slice(0, 12), secret.slice(12), ' after', ' after']) {
    trace.event('item/commandExecution/outputDelta', { ...ids, delta });
  }
  assert(!readFileSync(path, 'utf8').includes(secret.slice(0, 12)));
  trace.event('item/completed', { ...ids, item: { id: 'i', type: 'commandExecution', command: 'printf canary', aggregatedOutput: 'before ' + secret + ' after after', exitCode: 0 } });
  const resumed = new Trace(path, { generation: 'two', attempt: 'synthetic' }, [secret]);
  resumed.record('host', 'reconnected');
  const rows = readFileSync(path, 'utf8').trim().split('\n').map(JSON.parse);
  assert(!JSON.stringify(rows).includes(secret));
  assert.deepEqual(rows.map(r => r.seq), rows.map((_, i) => i + 1));
  assert.equal(rows.filter(r => r.kind.endsWith('outputDelta')).length, 5);
  assert.equal(rows.find(r => r.kind === 'stream/collected').data.text, 'before [REDACTED] after after');
  assert.equal(rows.at(-1).generation, 'two');
  resumed.event('item/reasoning/textDelta', { ...ids, delta: 'hidden-reasoning-must-not-persist' });
  resumed.event('item/completed', { ...ids, item: { id: 'reasoning', type: 'reasoning', text: 'hidden-reasoning-must-not-persist', summary: ['visible summary'] } });
  assert(!readFileSync(path, 'utf8').includes('hidden-reasoning-must-not-persist'));
  console.log(JSON.stringify({ status: 'pass', kind: 'synthetic', checks: ['split_secret_withheld', 'assembled_redaction', 'identical_deltas_preserved', 'durable_sequence_across_generation'] }));
} finally { rmSync(root, { recursive: true, force: true }); }
