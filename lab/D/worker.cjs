// Deterministic model substitute. The launch log is an independent execution oracle.
const fs = require('node:fs');
const { spawn } = require('node:child_process');
const [attempt, mode] = process.argv.slice(2);
const save = (name, value) => {
  fs.writeFileSync(`/out/${name}.tmp`, JSON.stringify(value));
  fs.renameSync(`/out/${name}.tmp`, `/out/${name}`);
};
fs.appendFileSync('/out/launches.jsonl', JSON.stringify({ attempt, pid: process.pid }) + '\n');
save('partial.json', { attempt, artifact: 'saved before completion' });
if (mode === 'tree') {
  // Ignore TERM so cancellation must cover the child as well as its parent.
  process.on('SIGTERM', () => {});
  const child = spawn(process.execPath, ['-e', `
    const fs = require('node:fs');
    process.on('SIGTERM', () => {});
    setInterval(() => fs.appendFileSync('/out/heartbeat', 'x'), 100);
  `], { stdio: 'ignore' });
  save('tree.json', { parent: process.pid, child: child.pid });
  setInterval(() => {}, 1000);
} else {
  // A host-controlled latch makes dispatch/restart timing deterministic.
  const timer = setInterval(() => {
    if (!fs.existsSync('/out/release')) return;
    clearInterval(timer);
    save('result.json', { attempt, status: mode === 'question' ? 'waiting' : 'complete',
      question: mode === 'question' ? 'continue-work' : null, value: 42 });
  }, 100);
}
