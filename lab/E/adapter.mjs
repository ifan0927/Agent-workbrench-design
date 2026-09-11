import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { createInterface } from 'node:readline';
import { mkdirSync, readFileSync, writeFileSync, renameSync } from 'node:fs';
import { randomUUID } from 'node:crypto';
import { Trace } from './trace.mjs';

const stateDir = process.env.E_STATE ?? '/state';
mkdirSync(stateDir, { recursive: true, mode: 0o700 });
const generation = randomUUID();
const trace = new Trace(`${stateDir}/events.jsonl`, { generation, attempt: process.env.E_ATTEMPT ?? 'probe' });
let child;
let sequence = 0;
let threadId;
let turnId;
let closed = true;
let deadline;
const pending = new Map();
const persist = (name, value) => {
  const tmp = `${stateDir}/${name}.tmp`;
  writeFileSync(tmp, JSON.stringify(trace.clean(value), null, 2), { mode: 0o600, flush: true });
  renameSync(tmp, `${stateDir}/${name}`);
};
const send = payload => child.stdin.write(JSON.stringify(payload) + '\n');
function request(method, params = {}) {
  if (closed) return Promise.reject(new Error('transport_closed'));
  const id = ++sequence;
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => { pending.delete(id); reject(new Error('rpc_timeout')); }, 20000);
    pending.set(id, { resolve, reject, timer });
    send({ id, method, params });
  });
}
async function startServer() {
  if (!closed) throw new Error('server_already_running');
  child = spawn('codex', ['app-server', '--listen', 'stdio://', '-c', 'cli_auth_credentials_store="ephemeral"',
    '-c', 'model_provider="openai"', '-c', 'web_search="disabled"', '-c', 'analytics.enabled=false',
    '-c', 'check_for_update_on_startup=false'], { cwd: '/work', stdio: ['pipe', 'pipe', 'pipe'] });
  closed = false;
  trace.record('adapter', 'server/started', { pid: child.pid });
  child.stderr.on('data', b => trace.record('adapter', 'stderr/withheld', { bytes: b.length }));
  child.on('exit', (code, signal) => {
    closed = true;
    for (const p of pending.values()) { clearTimeout(p.timer); p.reject(new Error('transport_closed')); }
    pending.clear();
    trace.flush(null, true);
    trace.record('adapter', 'server/exited', { code, signal, pid: child.pid });
    persist('server.json', { closed, code, signal });
  });
  createInterface({ input: child.stdout }).on('line', line => {
    let message;
    try { message = JSON.parse(line); } catch {
      trace.record('adapter', 'gap', { cause: 'invalid_json', bytes: line.length });
      return;
    }
    if (message.method) {
      if (message.id !== undefined) {
        // Callbacks remain serviced while the LangGraph process is offline.
        trace.record('adapter', 'server/request', { method: message.method, id: message.id });
        send({ id: message.id, error: { code: -32001, message: 'host_action_required' } });
      } else {
        trace.event(message.method, message.params ?? {});
        if (message.method === 'turn/completed') {
          clearTimeout(deadline);
          const p = message.params;
          persist('result.json', { threadId: p.threadId, turn: { id: p.turn.id, status: p.turn.status, error: p.turn.error } });
        }
      }
    } else {
      const p = pending.get(message.id);
      if (p) {
        clearTimeout(p.timer);
        pending.delete(message.id);
        if (message.error) p.reject(new Error('rpc_error:' + JSON.stringify(trace.clean(message.error))));
        else p.resolve(message.result);
      }
    }
  });
  const initialized = await request('initialize', { clientInfo: { name: 'agent_workbench_lab_e', version: '0.1.0' }, capabilities: { experimentalApi: true } });
  send({ method: 'initialized', params: {} });
  return { pid: child.pid, initialized };
}
const api = createServer(async (req, res) => {
  try {
    let body = '';
    for await (const b of req) { body += b; if (body.length > 1048576) throw new Error('request_too_large'); }
    const input = JSON.parse(body);
    let result;
    if (input.action === 'start') result = await startServer();
    else if (input.action === 'status') result = { closed, pid: child?.pid, threadId, turnId, generation };
    else if (input.action === 'close-stdin') { child.stdin.end(); result = { requested: true, pid: child.pid }; }
    else if (input.action === 'stop-server') { child.kill('SIGTERM'); result = { requested: true, pid: child.pid }; }
    else if (input.action === 'rpc') {
      const { method, params = {} } = input;
      const allowed = ['config/read', 'skills/list', 'mcpServerStatus/list', 'model/list', 'thread/start', 'thread/resume', 'thread/read', 'turn/start', 'turn/interrupt', 'account/login/start', 'account/read'];
      if (!allowed.includes(method)) throw new Error('method_not_allowed');
      if (method === 'account/login/start') {
        if (params.type !== 'chatgptAuthTokens') throw new Error('external_auth_only');
        trace.secrets.push(params.accessToken, params.chatgptAccountId);
      } else if (method === 'turn/start') {
        // The host owns the batch ledger; this latch prohibits duplicate dispatch per adapter.
        let old;
        try { old = JSON.parse(readFileSync(`${stateDir}/dispatch.json`, 'utf8')); } catch (e) { if (e.code !== 'ENOENT') throw e; }
        if (old) throw new Error('dispatch_already_attempted');
        persist('dispatch.json', { phase: 'intent', at: new Date().toISOString(), threadId: params.threadId });
        deadline = setTimeout(async () => {
          trace.record('adapter', 'deadline', { threadId, turnId });
          setTimeout(() => {
            trace.record('adapter', 'deadline/fallback_exit', { threadId, turnId });
            process.exit(124);
          }, 30000);
          if (turnId) { try { await request('turn/interrupt', { threadId, turnId }); } catch {} }
        }, 300000);
      }
      result = await request(method, params);
      if (method === 'thread/start' || method === 'thread/resume') {
        threadId = result.thread.id;
        persist('thread.json', { ...Object.fromEntries(['model', 'modelProvider', 'reasoningEffort', 'cwd', 'instructionSources', 'sandbox', 'approvalPolicy'].map(k => [k, result[k]])),
          thread: { id: result.thread.id, ephemeral: result.thread.ephemeral, restoredTurns: result.thread.turns?.length } });
      }
      if (method === 'turn/start') {
        turnId = result.turn.id;
        persist('dispatch.json', { phase: 'acknowledged', threadId, turnId });
      }
      if (!method.startsWith('account/')) trace.record('adapter', 'rpc/completed', { method, threadId, turnId });
    } else throw new Error('unknown_action');
    res.writeHead(200, { 'content-type': 'application/json' });
    // This private control channel is separate from persisted trace output.
    res.end(JSON.stringify({ result }));
  } catch (e) {
    res.writeHead(400, { 'content-type': 'application/json' });
    res.end(JSON.stringify({ error: String(e) }));
  }
});
api.listen(4771, '127.0.0.1');
trace.record('adapter', 'ready', { generation });
