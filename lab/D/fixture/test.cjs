const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { normalize } = require('./dist/index.cjs');
test('built output normalizes synthetic input', () => {
  assert.equal(normalize('  HeLLo '), 'hello');
});
test('private service DNS, network, persistence, and same-key isolation', async () => {
  const token = process.env.FIXTURE_VALUE;
  assert.ok(token);
  assert.equal(await (await fetch('http://service:8080/health')).text(), 'ready');
  await fetch('http://service:8080/value', { method: 'PUT', body: token });
  fs.writeFileSync('/work/test-written', token);
  // Both test workers must have written the same key before either reads it back.
  const deadline = Date.now() + 15000;
  while (!fs.existsSync('/barrier/release')) {
    if (Date.now() > deadline) throw new Error('barrier timeout');
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  assert.equal(await (await fetch('http://service:8080/value')).text(), token);
  fs.writeFileSync('/work/environment-result.json', JSON.stringify({ token, isolated: true }));
});
