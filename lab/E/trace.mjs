import { appendFileSync, closeSync, fsyncSync, openSync, readFileSync } from 'node:fs';

// Delta payloads are withheld until the whole item can be redacted safely.
export class Trace {
  constructor(path, identity, secrets = []) {
    this.path = path;
    this.identity = identity;
    this.secrets = secrets;
    this.buffers = new Map();
    this.seq = 0;
    try {
      const lines = readFileSync(path, 'utf8').trim().split('\n');
      this.seq = JSON.parse(lines.at(-1)).seq;
    } catch (e) { if (e.code !== 'ENOENT') throw e; }
  }
  clean(value) {
    let text = JSON.stringify(value);
    for (const secret of this.secrets.filter(Boolean).sort((a, b) => b.length - a.length)) {
      const escaped = JSON.stringify(secret).slice(1, -1);
      text = text.split(escaped).join('[REDACTED]');
    }
    text = text.replace(/eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/g, '[REDACTED_JWT]');
    return JSON.parse(text);
  }
  record(origin, kind, data = {}) {
    const row = { seq: ++this.seq, time: new Date().toISOString(), ...this.identity, origin, kind, data: this.clean(data) };
    const fd = openSync(this.path, 'a', 0o600);
    try { appendFileSync(fd, JSON.stringify(row) + '\n'); fsyncSync(fd); } finally { closeSync(fd); }
    return row;
  }
  event(method, p) {
    const ids = Object.fromEntries(['threadId', 'turnId', 'itemId'].filter(k => p[k]).map(k => [k, p[k]]));
    if (method.includes('/reasoning/') && method !== 'item/reasoning/summaryTextDelta') {
      this.record('app-server', method, { ...ids, content: 'reasoning_payload_not_collected' });
      return;
    }
    if (method.endsWith('Delta') || method.endsWith('/delta')) {
      const key = JSON.stringify([p.threadId, p.turnId, p.itemId, method]);
      const b = this.buffers.get(key) ?? { ids, method, text: '', bytes: 0, truncated: false };
      const delta = p.delta ?? p.text ?? '';
      b.bytes += Buffer.byteLength(delta);
      if (b.bytes <= 262144) b.text += delta;
      else b.truncated = true;
      this.buffers.set(key, b);
      this.record('app-server', method, { ...ids, bytes: Buffer.byteLength(delta), payload: 'withheld_until_item_end' });
      return;
    }
    if (['item/started', 'item/completed'].includes(method)) {
      const item = p.item ?? {};
      // Never persist hidden reasoning, encrypted content, or arbitrary RPC fields.
      const keys = ['id', 'type', 'status', 'command', 'cwd', 'exitCode', 'aggregatedOutput', 'changes', 'text', 'plan', 'summary', 'tool', 'arguments', 'result'];
      const safe = Object.fromEntries(keys.filter(k => item[k] !== undefined).map(k => [k, item[k]]));
      if (item.type === 'reasoning') delete safe.text;
      for (const k of ['text', 'aggregatedOutput']) {
        if (typeof safe[k] === 'string' && safe[k].length > 262144) {
          // Redact before truncation so a prefix cannot expose a split secret.
          safe[k] = this.clean(safe[k]).slice(0, 262144);
          safe.truncated = true;
        }
      }
      this.record(item.type === 'agentMessage' || item.type === 'reasoning' ? 'agent' : 'app-server', method, { ...ids, item: safe });
      if (method === 'item/completed') this.flush(item.id, false);
    } else if (method === 'thread/tokenUsage/updated') {
      this.record('app-server', method, { ...ids, tokenUsage: p.tokenUsage });
    } else if (method.startsWith('turn/')) {
      const t = p.turn ?? {};
      this.record('app-server', method, { ...ids, turn: { id: t.id, status: t.status, error: t.error }, diff: p.diff });
      if (method === 'turn/completed') this.flush(null, true);
    } else {
      this.record('app-server', method, { ...ids, content: 'metadata_only' });
    }
  }
  flush(itemId, incomplete) {
    for (const [key, b] of this.buffers) {
      if (itemId && b.ids.itemId !== itemId) continue;
      // A truncated stream is entirely withheld: its boundary may split a secret.
      this.record('app-server', 'stream/collected', { ...b.ids, method: b.method, bytes: b.bytes, incomplete,
        truncated: b.truncated, text: b.truncated ? '[WITHHELD_TRUNCATED]' : b.text });
      this.buffers.delete(key);
    }
  }
}
