import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { EventEmitter } from 'node:events';
import http from 'node:http';
import test from 'node:test';

import { createRPCAdapter } from '../runtime/a2a-shared/a2a-rpc-adapter.js';
import { MeshStore } from '../runtime/a2a-shared/mesh-store.js';
import { MeshEventBus } from '../runtime/a2a-shared/event-bus.js';
import { createTaskManager } from '../runtime/a2a-shared/task-manager.js';
import { recoverPartialArtifacts } from '../runtime/a2a-shared/partial-output.js';
import { callPeer } from '../runtime/a2a-shared/team-executor.js';
import { createMeshCaller } from '../runtime/a2a-shared/mesh-calls.js';
import { createStableRequestIdFactory } from '../runtime/a2a-shared/request-id.js';
import { clampMcpWaitMs, MAX_MCP_WAIT_MS } from '../runtime/a2a-shared/mcp-policy.js';
import { waitForRemotePoll } from '../runtime/a2a-shared/remote-task-control.js';

test('espera de polling remove o listener de abort ao resolver', async () => {
  let added = 0;
  let removed = 0;
  const signal = {
    aborted: false,
    addEventListener() { added += 1; },
    removeEventListener() { removed += 1; },
  };
  await waitForRemotePoll(1, signal);
  assert.equal(added, 1);
  assert.equal(removed, 1);
});

test('espera MCP nunca excede o teto total de 240 segundos', () => {
  assert.equal(MAX_MCP_WAIT_MS, 240_000);
  assert.equal(clampMcpWaitMs(999_999), 240_000);
  assert.equal(clampMcpWaitMs(12_345), 12_345);
  assert.equal(clampMcpWaitMs(-1), 0);
});

test('request_id automático é estável só na janela deslizante e na mesma sessão do bridge', () => {
  let clock = 1_000;
  let nonceValue = 0;
  const make = (scope) => createStableRequestIdFactory({
    scope,
    retryWindowMs: 5_000,
    now: () => clock,
    nonce: () => `nonce-${++nonceValue}`,
  });
  const firstBridge = make('bridge-a');
  const secondBridge = make('bridge-b');
  const params = { prompt: 'mesmo pedido', nested: { b: 2, a: 1 } };
  const first = firstBridge('mesh/call', params);
  assert.equal(firstBridge('mesh/call', { nested: { a: 1, b: 2 }, prompt: 'mesmo pedido' }), first);
  assert.notEqual(secondBridge('mesh/call', params), first);
  clock += 5_001;
  assert.notEqual(firstBridge('mesh/call', params), first);
});

function temporaryTaskManager() {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-durable-'));
  const tm = createTaskManager({ dataDir, selfId: 'codex', maxDepth: 7 });
  return {
    tm,
    cleanup() {
      tm.stopReaper();
      fs.rmSync(dataDir, { recursive: true, force: true });
    },
  };
}

function rpc(adapter, method, params) {
  return adapter.handle(JSON.stringify({ jsonrpc: '2.0', id: `${method}-${Date.now()}`, method, params }));
}

test('mesh async reutiliza request_id e mantém o mesmo taskId no executor', async () => {
  const fixture = temporaryTaskManager();
  let observedTaskId = null;
  try {
    const adapter = createRPCAdapter({
      tm: fixture.tm,
      executeTask() {},
      taskTimeoutMs: 1000,
      meshCaller: {
        async executeA2ACall(_params, context) {
          observedTaskId = context.taskId;
          return 'ok';
        },
      },
      maxDepth: 7,
      selfId: 'codex',
      peers: { claude: 'http://127.0.0.1:3142' },
      push: { set() {}, get() {}, delete() {} },
    });

    const first = await rpc(adapter, 'mesh/callAsync', {
      agent: 'claude', prompt: 'teste', request_id: 'same-request',
    });
    const second = await rpc(adapter, 'mesh/callAsync', {
      agent: 'claude', prompt: 'teste', request_id: 'same-request',
    });
    await new Promise(resolve => setImmediate(resolve));

    assert.equal(first.result.id, second.result.id);
    assert.equal(second.result.reused, true);
    assert.equal(observedTaskId, first.result.id);
    assert.equal(fixture.tm.tasks.get(first.result.id).status.state, 'completed');
  } finally {
    fixture.cleanup();
  }
});

test('cancelamento async aborta o sinal do modelo e não é sobrescrito por completion tardia', async () => {
  const fixture = temporaryTaskManager();
  let observedSignal = null;
  try {
    const adapter = createRPCAdapter({
      tm: fixture.tm,
      executeTask() {},
      taskTimeoutMs: 1000,
      meshCaller: {
        executeA2ACall(_params, context) {
          observedSignal = context.signal;
          return new Promise((_resolve, reject) => {
            context.signal.addEventListener('abort', () => reject(context.signal.reason), { once: true });
          });
        },
      },
      maxDepth: 7,
      selfId: 'codex',
      peers: { claude: 'http://127.0.0.1:3142' },
      push: { set() {}, get() {}, delete() {} },
    });

    const submitted = await rpc(adapter, 'mesh/callAsync', { agent: 'claude', prompt: 'longo' });
    await new Promise(resolve => setImmediate(resolve));
    const canceled = await rpc(adapter, 'tasks/cancel', { id: submitted.result.id });
    await new Promise(resolve => setImmediate(resolve));

    assert.equal(observedSignal.aborted, true);
    assert.equal(canceled.result.status.state, 'canceled');
    assert.equal(fixture.tm.tasks.get(submitted.result.id).status.state, 'canceled');
  } finally {
    fixture.cleanup();
  }
});

test('timeout completo aceita configuração de até cinco dias', async () => {
  const fixture = temporaryTaskManager();
  try {
    const adapter = createRPCAdapter({
      tm: fixture.tm,
      executeTask() {},
      taskTimeoutMs: 1000,
      meshCaller: { async executeA2ACall() { return 'ok'; } },
      maxDepth: 7,
      selfId: 'codex',
      peers: { claude: 'http://127.0.0.1:3142' },
      push: { set() {}, get() {}, delete() {} },
    });
    const response = await rpc(adapter, 'mesh/callAsync', {
      agent: 'claude', prompt: 'teste', operation_timeout_ms: 999_999_999,
    });
    assert.equal(response.result.operationTimeoutMs, 432_000_000);
    await new Promise(resolve => setImmediate(resolve));
  } finally {
    fixture.cleanup();
  }
});

test('timeline persistente recupera apenas eventos posteriores ao último SSE id', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-events-'));
  const dbPath = path.join(directory, 'mesh.db');
  const store = new MeshStore(dbPath);
  try {
    store.createTask({ id: 'task-1', originServer: 'codex', inputText: 'teste' });
    const first = store.createEvent('task-1', 'dialogue', 'codex', { text: 'um' });
    const second = store.createEvent('task-1', 'dialogue', 'codex', { text: 'dois' });
    const replay = store.getTimeline({ afterId: first, order: 'asc', limit: 10 });
    assert.deepEqual(replay.map(event => event.id), [second]);
    assert.equal(replay[0].payload.text, 'dois');
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('event bus entrega evento local a assinantes peer sem republicação em loop', () => {
  const bus = new MeshEventBus({
    selfId: 'codex',
    peers: {},
    store: {
      createEvent() { return 42; },
      getTimeline() { return []; },
    },
  });
  const response = new EventEmitter();
  response.body = '';
  response.writeHead = () => {};
  response.write = chunk => { response.body += chunk; };
  const request = { url: '/mesh/events?peer=true', headers: {} };

  bus.handleSSE(request, response);
  bus.publish({ taskId: 'task-1', type: 'dialogue', payload: { text: 'delta' } });

  assert.match(response.body, /id: 42/);
  assert.match(response.body, /event: mesh-event/);
  assert.match(response.body, /"text":"delta"/);
  response.emit('close');
  bus.disconnect();
});

test('replay SSE pagina o ledger e sinaliza lacuna somente no limite explícito', () => {
  const priorLimit = process.env.MESH_SSE_REPLAY_MAX;
  process.env.MESH_SSE_REPLAY_MAX = '100';
  const events = Array.from({ length: 120 }, (_, index) => ({
    id: index + 2,
    task_id: 'task-replay',
    event_type: 'dialogue',
    server: 'codex',
    created_at: '2026-08-15 12:00:00',
    payload: { text: `e${index + 2}` },
  }));
  const bus = new MeshEventBus({
    selfId: 'codex',
    peers: {},
    store: {
      getTimeline({ afterId, limit }) {
        return events.filter(item => item.id > afterId).slice(0, limit);
      },
    },
  });
  const response = new EventEmitter();
  response.body = '';
  response.writeHead = () => {};
  response.write = chunk => { response.body += chunk; };
  const request = { url: '/mesh/events?after=1', headers: {} };
  try {
    bus.handleSSE(request, response);
    assert.match(response.body, /id: 101/);
    assert.match(response.body, /event: mesh-gap/);
    assert.match(response.body, /"nextAfterId":101/);
  } finally {
    response.emit('close');
    bus.disconnect();
    if (priorLimit === undefined) delete process.env.MESH_SSE_REPLAY_MAX;
    else process.env.MESH_SSE_REPLAY_MAX = priorLimit;
  }
});

test('evento ao vivo já incluído no replay não é entregue duas vezes', () => {
  let bus;
  let emitted = false;
  const store = {
    createEvent() { return 2; },
    getTimeline({ afterId }) {
      if (!emitted && afterId === 1) {
        emitted = true;
        bus.publish({ taskId: 'task-race', type: 'dialogue', payload: { text: 'uma vez' } });
        return [{
          id: 2, task_id: 'task-race', event_type: 'dialogue', server: 'codex',
          created_at: '2026-08-15 12:00:00', payload: { text: 'uma vez' },
        }];
      }
      return [];
    },
  };
  bus = new MeshEventBus({ selfId: 'codex', peers: {}, store });
  const response = new EventEmitter();
  response.body = '';
  response.writeHead = () => {};
  response.write = chunk => { response.body += chunk; };
  try {
    bus.handleSSE({ url: '/mesh/events?after=1', headers: {} }, response);
    assert.equal((response.body.match(/^id: 2$/gm) || []).length, 1);
  } finally {
    response.emit('close');
    bus.disconnect();
  }
});

test('replay não confunde IDs iguais provenientes de servidores diferentes', () => {
  let response;
  const bus = new MeshEventBus({
    selfId: 'codex', peers: {},
    store: {
      getTimeline({ afterId }) {
        if (afterId !== 1) return [];
        response._pendingMeshEvents.push({
          payload: 'id: 2\nevent: peer-event\ndata: {"server":"claude","eventId":2}\n\n',
          dedupeKey: 'claude:2',
        });
        return [{
          id: 2, task_id: 'task-local', event_type: 'dialogue', server: 'codex',
          created_at: '2026-08-15 12:00:00', payload: { text: 'local' },
        }];
      },
    },
  });
  response = new EventEmitter();
  response.body = '';
  response.writeHead = () => {};
  response.write = chunk => { response.body += chunk; };
  try {
    bus.handleSSE({ url: '/mesh/events?after=1', headers: {} }, response);
    assert.match(response.body, /"text":"local"/);
    assert.match(response.body, /"server":"claude","eventId":2/);
  } finally {
    response.emit('close');
    bus.disconnect();
  }
});

test('peer-event não avança o cursor Last-Event-ID numérico do servidor local', async () => {
  const peer = http.createServer((_req, res) => {
    res.writeHead(200, { 'Content-Type': 'text/event-stream' });
    res.end(`data: ${JSON.stringify({
      taskId: 'peer-task', type: 'dialogue', payload: { text: 'peer' },
      server: 'claude', eventId: 999,
    })}\n\n`);
  });
  await new Promise(resolve => peer.listen(0, '127.0.0.1', resolve));
  const { port } = peer.address();
  const bus = new MeshEventBus({
    selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` },
    store: { getTimeline() { return []; } },
  });
  const response = new EventEmitter();
  response.body = '';
  response.writeHead = () => {};
  response.write = chunk => { response.body += chunk; };
  try {
    bus.handleSSE({ url: '/mesh/events', headers: {} }, response);
    bus.connectToPeers();
    for (let index = 0; index < 20 && !response.body.includes('peer-event'); index += 1) {
      await new Promise(resolve => setTimeout(resolve, 10));
    }
    assert.match(response.body, /event: peer-event/);
    assert.doesNotMatch(response.body, /^id: 999$/m);
  } finally {
    response.emit('close');
    bus.disconnect();
    await new Promise(resolve => peer.close(resolve));
  }
});

test('idempotência durável reutiliza a tarefa entre coordenadores distintos', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-idempotency-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  const tmA = createTaskManager({ dataDir: path.join(directory, 'a'), selfId: 'codex', meshStore: store });
  const tmB = createTaskManager({ dataDir: path.join(directory, 'b'), selfId: 'claude', meshStore: store });
  let executions = 0;
  const makeAdapter = (tm, selfId) => createRPCAdapter({
    tm,
    executeTask() {},
    taskTimeoutMs: 1000,
    meshStore: store,
    meshCaller: { async executeA2ACall() { executions += 1; return 'ok'; } },
    maxDepth: 7,
    selfId,
    peers: {},
    push: { set() {}, get() {}, delete() {} },
  });
  try {
    const [first, second] = await Promise.all([
      rpc(makeAdapter(tmA, 'codex'), 'mesh/callAsync', {
        agent: 'codex', prompt: 'teste', request_id: 'durable-cross-coordinator',
      }),
      rpc(makeAdapter(tmB, 'claude'), 'mesh/callAsync', {
        agent: 'claude', prompt: 'teste', request_id: 'durable-cross-coordinator',
      }),
    ]);
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(first.result.id, second.result.id);
    assert.equal(Number(first.result.reused === true) + Number(second.result.reused === true), 1);
    assert.equal(executions, 1);
    assert.equal(store.getIdempotentTask('mesh/call', 'durable-cross-coordinator').id, first.result.id);
  } finally {
    tmA.stopReaper();
    tmB.stopReaper();
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('reserva idempotente órfã é retomada após o TTL sem devolver tarefa fantasma', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-idempotency-orphan-'));
  const priorTtl = process.env.A2A_IDEMPOTENCY_RESERVATION_TTL_SECONDS;
  process.env.A2A_IDEMPOTENCY_RESERVATION_TTL_SECONDS = '10';
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  const tm = createTaskManager({ dataDir: path.join(directory, 'tasks'), selfId: 'codex', meshStore: store });
  let executions = 0;
  try {
    store.claimIdempotency('mesh/call', 'orphan-request', 'ghost-task');
    store.db.prepare(`
      UPDATE mesh_idempotency_keys SET created_at = datetime('now', '-1 hour')
      WHERE operation_type = 'mesh/call' AND request_id = 'orphan-request'
    `).run();
    const adapter = createRPCAdapter({
      tm,
      executeTask() {},
      taskTimeoutMs: 1000,
      meshStore: store,
      meshCaller: { async executeA2ACall() { executions += 1; return 'ok'; } },
      maxDepth: 7,
      selfId: 'codex',
      peers: {},
      push: { set() {}, get() {}, delete() {} },
    });
    const response = await rpc(adapter, 'mesh/callAsync', {
      agent: 'codex', prompt: 'retomar', request_id: 'orphan-request',
    });
    await new Promise(resolve => setImmediate(resolve));
    assert.notEqual(response.result.id, 'ghost-task');
    assert.equal(store.getIdempotentTask('mesh/call', 'orphan-request').id, response.result.id);
    assert.equal(executions, 1);
  } finally {
    tm.stopReaper();
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
    if (priorTtl === undefined) delete process.env.A2A_IDEMPOTENCY_RESERVATION_TTL_SECONDS;
    else process.env.A2A_IDEMPOTENCY_RESERVATION_TTL_SECONDS = priorTtl;
  }
});

test('reserva idempotente órfã ainda fresca não é devolvida como tarefa fantasma', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-idempotency-pending-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  const tm = createTaskManager({ dataDir: path.join(directory, 'tasks'), selfId: 'codex', meshStore: store });
  const adapter = createRPCAdapter({
    tm, executeTask() {}, taskTimeoutMs: 1000, meshStore: store,
    meshCaller: { async executeA2ACall() { return 'não deve executar'; } },
    maxDepth: 7, selfId: 'codex', peers: {}, push: { set() {}, get() {}, delete() {} },
  });
  try {
    store.claimIdempotency('mesh/call', 'pending-request', 'missing-task');
    const result = await rpc(adapter, 'mesh/callAsync', {
      agent: 'claude', prompt: 'teste', request_id: 'pending-request',
    });
    assert.equal(result.error.code, -32009);
    assert.match(result.error.message, /reservation.*pending/i);
  } finally {
    tm.stopReaper();
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('ledger poda chaves idempotentes de tarefas terminais antigas', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-idempotency-prune-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  try {
    store.createTask({ id: 'old-terminal', originServer: 'codex', inputText: 'x' });
    store.claimIdempotency('mesh/call', 'old-request', 'old-terminal');
    store.updateTask('old-terminal', { state: 'completed', outputText: 'ok' });
    store.db.prepare(`UPDATE tasks SET updated_at = datetime('now', '-31 days') WHERE id = ?`)
      .run('old-terminal');
    assert.equal(store.pruneIdempotency(30), 1);
    assert.equal(store.getIdempotentTask('mesh/call', 'old-request'), null);
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('estado terminal é compare-and-set e não aceita conclusão tardia', () => {
  const fixture = temporaryTaskManager();
  try {
    const task = fixture.tm.createTask({ role: 'user', parts: [{ type: 'text', text: 'x' }] });
    fixture.tm.updateTask(task, { status: { state: 'canceled' } });
    const changed = fixture.tm.updateTask(task, { status: { state: 'completed' } });
    const sameState = fixture.tm.updateTask(task, {
      status: { state: 'canceled', message: { role: 'agent', parts: [{ type: 'text', text: 'reescrito' }] } },
    });
    assert.equal(changed, false);
    assert.equal(sameState, false);
    assert.equal(task.status.state, 'canceled');
  } finally {
    fixture.cleanup();
  }
});

test('artefato parcial prefere snapshots exatos e preserva atribuição', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-partial-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  try {
    store.createTask({ id: 'partial-1', originServer: 'codex', inputText: 'x' });
    store.createEvent('partial-1', 'dialogue', 'codex', { agent: 'claude', role: 'response', text: 'não usar' });
    store.createEvent('partial-1', 'partial_output', 'codex', { agent: 'claude', text: 'texto exato' });
    store.createEvent('partial-1', 'dialogue', 'codex', { agent: 'grok', role: 'review', text: 'parecer grok' });
    store.createEvent('partial-1', 'dialogue', 'codex', { agent: 'kimi', role: 'response', text: '!' });
    store.createEvent('partial-1', 'dialogue', 'codex', { agent: 'kimi', role: 'response', text: '!' });
    const artifacts = recoverPartialArtifacts(store, 'partial-1');
    const text = artifacts[0].parts[0].text;
    assert.match(text, /## claude\n\ntexto exato/);
    assert.match(text, /## grok\n\nparecer grok/);
    assert.match(text, /## kimi\n\n!!/);
    assert.doesNotMatch(text, /não usar/);
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('snapshot substituível evita duplicar deltas e turno completo na recuperação', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-partial-snapshot-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  try {
    store.createTask({ id: 'partial-snapshot', originServer: 'codex', inputText: 'x' });
    store.createEvent('partial-snapshot', 'dialogue', 'codex', {
      agent: 'claude', role: 'response', text: 'A resposta completa.',
    });
    store.upsertPartialSnapshot('partial-snapshot', 'claude', 'A resposta completa.', {
      complete: true,
    });
    const text = recoverPartialArtifacts(store, 'partial-snapshot')[0].parts[0].text;
    assert.equal((text.match(/A resposta completa\./g) || []).length, 1);
    assert.equal(store.getPartialSnapshots('partial-snapshot').length, 1);
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('restart preserva saída parcial e não reescreve tarefa terminal no SQLite', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-stale-cas-'));
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  try {
    store.createTask({ id: 'zombie', originServer: 'codex', inputText: 'x' });
    store.updateTask('zombie', { state: 'working' });
    store.createEvent('zombie', 'dialogue', 'codex', {
      agent: 'claude', role: 'response', text: 'rascunho recuperável',
    });
    store.createTask({ id: 'done', originServer: 'codex', inputText: 'y' });
    store.updateTask('done', { state: 'completed', outputText: 'pronto' });
    const late = store.updateTask('done', { state: 'completed', outputText: 'reescrito' });

    assert.equal(store.failStaleActiveTasks({ originServer: 'codex' }), 1);
    assert.equal(store.getTask('zombie').state, 'failed');
    assert.match(store.getTask('zombie').artifacts[0].parts[0].text, /rascunho recuperável/);
    assert.equal(store.getTask('done').state, 'completed');
    assert.equal(store.getTask('done').outputText, 'pronto');
    assert.equal(late.updateAccepted, false);
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
  }
});

test('limite de eventos persiste mesh_gap e ainda aceita o estado terminal', () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-event-gap-'));
  const priorLimit = process.env.MESH_MAX_EVENTS_PER_TASK;
  process.env.MESH_MAX_EVENTS_PER_TASK = '1';
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  try {
    store.createTask({ id: 'limited', originServer: 'codex', inputText: 'x' });
    store.createEvent('limited', 'dialogue', 'codex', { text: 'excedente' });
    store.createEvent('limited', 'completed', 'codex', { text: 'fim' });
    const events = store.getEvents('limited');
    assert.deepEqual(events.map(event => event.event_type), ['created', 'mesh_gap', 'completed']);
    assert.equal(events[1].payload.reason, 'event_limit_reached');
  } finally {
    store.close();
    fs.rmSync(directory, { recursive: true, force: true });
    if (priorLimit === undefined) delete process.env.MESH_MAX_EVENTS_PER_TASK;
    else process.env.MESH_MAX_EVENTS_PER_TASK = priorLimit;
  }
});

test('team recupera tarefa após queda do SSE sem duplicar a chamada', async () => {
  let submissions = 0;
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      submissions += 1;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.end('event: task-status\ndata: {"id":"remote-recovery","status":{"state":"working"}}\n\n');
      return;
    }
    if (req.method === 'GET' && req.url === '/tasks/remote-recovery') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: {
        id: 'remote-recovery',
        status: { state: 'completed', message: { role: 'agent', parts: [{ type: 'text', text: 'recuperado' }] } },
      } }));
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const result = await callPeer(`http://127.0.0.1:${port}`, 'p', {}, '', 2000);
    assert.equal(result, 'recuperado');
    assert.equal(submissions, 1);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test('estado terminal encerra a espera mesmo se o peer mantiver o SSE aberto', async () => {
  let openResponse = null;
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      openResponse = res;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.write('event: task-status\ndata: {"id":"remote-keepalive","status":{"state":"completed","message":{"parts":[{"type":"text","text":"concluído"}]}}}\n\n');
      return; // Deliberately keep the transport open after terminal state.
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
    });
    const result = await Promise.race([
      caller.executeA2ACall(
        { agent: 'claude', prompt: 'teste terminal', timeout_ms: 2000 },
        { depth: 7, meshChain: [], taskId: 'parent-keepalive' },
      ),
      new Promise((_, reject) => setTimeout(() => reject(new Error('client waited for SSE close')), 750)),
    ]);
    assert.equal(result, 'concluído');
  } finally {
    openResponse?.end();
    server.closeAllConnections?.();
    await new Promise(resolve => server.close(resolve));
  }
});

test('team preserva deltas textuais repetidos exatamente na saída parcial', async () => {
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.write('event: task-status\ndata: {"id":"remote-deltas","status":{"state":"working"}}\n\n');
      for (const chunk of ['ab', 'b', '!', '!']) {
        res.write(`event: task-progress\ndata: ${JSON.stringify({ id: 'remote-deltas', chunk })}\n\n`);
      }
      res.end('event: task-status\ndata: {"id":"remote-deltas","status":{"state":"failed","message":{"parts":[{"type":"text","text":"falhou"}]}}}\n\n');
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const error = await callPeer(`http://127.0.0.1:${port}`, 'p', {}, '', 2000)
      .then(() => null, caught => caught);
    assert.equal(error.partial, 'abb!!');
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test('deltas ao vivo usam snapshot substituível e não esgotam o ledger de fases', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-transient-stream-'));
  const priorLimit = process.env.MESH_MAX_EVENTS_PER_TASK;
  process.env.MESH_MAX_EVENTS_PER_TASK = '5';
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  store.createTask({ id: 'parent-transient', originServer: 'codex', inputText: 'x' });
  const bus = new MeshEventBus({ selfId: 'codex', peers: {}, store });
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.write('event: task-status\ndata: {"id":"remote-transient","status":{"state":"working"}}\n\n');
      for (let index = 0; index < 30; index += 1) {
        res.write('event: task-progress\ndata: {"id":"remote-transient","chunk":"!"}\n\n');
      }
      res.end('event: task-status\ndata: {"id":"remote-transient","status":{"state":"completed","message":{"parts":[{"type":"text","text":"resposta final"}]}}}\n\n');
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
      meshBus: bus, meshStore: store,
    });
    const result = await caller.executeA2ACall(
      { agent: 'claude', prompt: 'stream', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-transient' },
    );
    assert.equal(result, 'resposta final');
    const persistedDialogue = store.getTimeline({
      taskId: 'parent-transient', eventType: 'dialogue', limit: 100,
    });
    assert.equal(persistedDialogue.filter(item => item.payload?.role === 'response').length, 0);
    assert.equal(store.getPartialSnapshots('parent-transient')[0].text, 'resposta final');
    const synthesisId = store.createEvent('parent-transient', 'dialogue', 'codex', {
      agent: 'judge', role: 'synthesis', text: 'síntese preservada',
    });
    assert.ok(synthesisId);
  } finally {
    bus.disconnect();
    store.close();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
    if (priorLimit === undefined) delete process.env.MESH_MAX_EVENTS_PER_TASK;
    else process.env.MESH_MAX_EVENTS_PER_TASK = priorLimit;
  }
});

test('task-dialogue transitório preserva streaming não durável em salto intermediário', async () => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-transient-hop-'));
  const priorLimit = process.env.MESH_MAX_EVENTS_PER_TASK;
  process.env.MESH_MAX_EVENTS_PER_TASK = '5';
  const store = new MeshStore(path.join(directory, 'mesh.db'));
  store.createTask({ id: 'parent-hop', originServer: 'codex', inputText: 'x' });
  const bus = new MeshEventBus({ selfId: 'codex', peers: {}, store });
  const liveDialogue = [];
  const chunks = Array.from({ length: 30 }, (_, index) => ['ab', 'b', '!', '!'][index % 4]);
  bus.on('event', event => {
    if (event.type === 'dialogue' && event.payload?.transient) liveDialogue.push(event);
  });
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.write('event: task-status\ndata: {"id":"remote-hop","status":{"state":"working"}}\n\n');
      for (const chunk of chunks) {
        const data = {
          id: 'remote-hop', operation: 'stream', phase: 'progress',
          agent: 'nested-agent', role: 'response', text: chunk,
          extra: { transient: true },
        };
        res.write(`event: task-dialogue\ndata: ${JSON.stringify(data)}\n\n`);
      }
      res.end('event: task-status\ndata: {"id":"remote-hop","status":{"state":"completed","message":{"parts":[{"type":"text","text":"resposta intermediária"}]}}}\n\n');
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
      meshBus: bus, meshStore: store,
    });
    const result = await caller.executeA2ACall(
      { agent: 'claude', prompt: 'stream encadeado', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-hop' },
    );
    assert.equal(result, 'resposta intermediária');
    assert.equal(liveDialogue.length, 30);
    assert.ok(liveDialogue.every(event => event.payload.transient === true));
    assert.equal(liveDialogue.map(event => event.payload.text).join(''), chunks.join(''));
    const persistedDialogue = store.getTimeline({
      taskId: 'parent-hop', eventType: 'dialogue', limit: 100,
    });
    assert.equal(persistedDialogue.filter(item => item.payload?.role === 'response').length, 0);
    const synthesisId = store.createEvent('parent-hop', 'dialogue', 'codex', {
      agent: 'judge', role: 'synthesis', text: 'síntese após salto preservada',
    });
    assert.ok(synthesisId);
  } finally {
    bus.disconnect();
    store.close();
    await new Promise(resolve => server.close(resolve));
    fs.rmSync(directory, { recursive: true, force: true });
    if (priorLimit === undefined) delete process.env.MESH_MAX_EVENTS_PER_TASK;
    else process.env.MESH_MAX_EVENTS_PER_TASK = priorLimit;
  }
});

test('cancelamento do pai é entregue à tarefa remota conhecida', async () => {
  let cancelRequests = 0;
  let streamResponse;
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      streamResponse = res;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.write('event: task-status\ndata: {"id":"remote-cancel","status":{"state":"working"}}\n\n');
      res.write('event: task-progress\ndata: {"id":"remote-cancel","chunk":"pronto"}\n\n');
      return;
    }
    if (req.method === 'POST' && req.url === '/tasks/remote-cancel/cancel') {
      cancelRequests += 1;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: 'remote-cancel', status: { state: 'canceled' } } }));
      streamResponse?.end();
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const controller = new AbortController();
  try {
    const { port } = server.address();
    let confirmRemoteKnown;
    const remoteKnown = new Promise(resolve => { confirmRemoteKnown = resolve; });
    const pending = callPeer(`http://127.0.0.1:${port}`, 'p', {}, '', 5000, {
      signal: controller.signal,
      onProgress(_text, remoteTaskId) {
        if (remoteTaskId === 'remote-cancel') confirmRemoteKnown();
      },
    });
    await remoteKnown;
    controller.abort(new Error('cancelar'));
    await assert.rejects(pending, /Task canceled by caller/);
    assert.equal(cancelRequests, 1);
  } finally {
    streamResponse?.end();
    await new Promise(resolve => server.close(resolve));
  }
});

test('queda SSE com tarefa remota conhecida não reenvia prompt e cancela ao expirar', async () => {
  let submissions = 0;
  let cancelRequests = 0;
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      submissions += 1;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.end('event: task-status\ndata: {"id":"remote-stuck","status":{"state":"working"}}\n\n');
      return;
    }
    if (req.method === 'GET' && req.url === '/tasks/remote-stuck') {
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: 'remote-stuck', status: { state: 'working' } } }));
      return;
    }
    if (req.method === 'POST' && req.url === '/tasks/remote-stuck/cancel') {
      cancelRequests += 1;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: 'remote-stuck', status: { state: 'canceled' } } }));
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
    });
    const result = await caller.executeA2ACall(
      { agent: 'claude', prompt: 'não duplique', timeout_ms: 120 },
      { depth: 7, meshChain: [], taskId: 'parent-stuck' },
    );
    assert.match(result, /Timeout/);
    assert.equal(submissions, 1);
    assert.equal(cancelRequests, 1);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test('cancelamento durante recuperação SSE interrompe poll e cancela o remoto', async () => {
  let cancelRequests = 0;
  let confirmRecoveryStarted;
  const recoveryStarted = new Promise(resolve => { confirmRecoveryStarted = resolve; });
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.end('event: task-status\ndata: {"id":"remote-recover-cancel","status":{"state":"working"}}\n\n');
      return;
    }
    if (req.method === 'GET' && req.url === '/tasks/remote-recover-cancel') {
      confirmRecoveryStarted();
      setTimeout(() => {
        if (!res.writableEnded) {
          res.writeHead(200, { 'Content-Type': 'application/json' });
          res.end(JSON.stringify({ result: { id: 'remote-recover-cancel', status: { state: 'working' } } }));
        }
      }, 500);
      return;
    }
    if (req.method === 'POST' && req.url === '/tasks/remote-recover-cancel/cancel') {
      cancelRequests += 1;
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: 'remote-recover-cancel', status: { state: 'canceled' } } }));
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const controller = new AbortController();
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
    });
    const pending = caller.executeA2ACall(
      { agent: 'claude', prompt: 'cancelar recuperação', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-recover-cancel', signal: controller.signal },
    );
    await recoveryStarted;
    controller.abort(new Error('cancelar'));
    const result = await pending;
    assert.match(result, /Task canceled by caller/);
    assert.equal(cancelRequests, 1);
  } finally {
    await new Promise(resolve => server.close(resolve));
  }
});

test('cancelamentos do usuário não abrem o circuit breaker do peer', async () => {
  let submissions = 0;
  let notifySubmission = null;
  const streams = new Map();
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      submissions += 1;
      const id = `cancel-circuit-${submissions}`;
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      if (submissions <= 6) {
        streams.set(id, res);
        res.write(`event: task-status\ndata: ${JSON.stringify({ id, status: { state: 'working' } })}\n\n`);
      } else {
        res.end(`event: task-status\ndata: ${JSON.stringify({
          id, status: { state: 'completed', message: { parts: [{ type: 'text', text: 'peer disponível' }] } },
        })}\n\n`);
      }
      notifySubmission?.();
      notifySubmission = null;
      return;
    }
    const match = /^\/tasks\/(cancel-circuit-\d+)\/cancel$/.exec(req.url || '');
    if (req.method === 'POST' && match) {
      streams.get(match[1])?.end();
      streams.delete(match[1]);
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: match[1], status: { state: 'canceled' } } }));
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
    });
    for (let index = 0; index < 6; index += 1) {
      const controller = new AbortController();
      const submitted = new Promise(resolve => { notifySubmission = resolve; });
      const pending = caller.executeA2ACall(
        { agent: 'claude', prompt: `cancelar ${index}`, timeout_ms: 2000 },
        { depth: 7, meshChain: [], taskId: `parent-circuit-${index}`, signal: controller.signal },
      );
      await submitted;
      controller.abort(new Error('cancelar'));
      assert.match(await pending, /Task canceled by caller/);
    }
    const recovered = await caller.executeA2ACall(
      { agent: 'claude', prompt: 'ainda disponível', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-circuit-final' },
    );
    assert.equal(recovered, 'peer disponível');
    assert.equal(submissions, 7);
  } finally {
    for (const stream of streams.values()) stream.end();
    await new Promise(resolve => server.close(resolve));
  }
});

test('cancelamento de sonda HALF_OPEN libera a próxima tentativa', async () => {
  const previous = {
    threshold: process.env.A2A_PEER_CB_FAILURE_THRESHOLD,
    open: process.env.A2A_PEER_CB_OPEN_MS,
    base: process.env.A2A_PEER_RETRY_BASE_DELAY_MS,
    max: process.env.A2A_PEER_RETRY_MAX_DELAY_MS,
    jitter: process.env.A2A_PEER_RETRY_JITTER_MS,
  };
  process.env.A2A_PEER_CB_FAILURE_THRESHOLD = '1';
  process.env.A2A_PEER_CB_OPEN_MS = '1';
  process.env.A2A_PEER_RETRY_BASE_DELAY_MS = '1';
  process.env.A2A_PEER_RETRY_MAX_DELAY_MS = '1';
  process.env.A2A_PEER_RETRY_JITTER_MS = '0';
  let submissions = 0;
  let probeStream;
  let confirmProbeKnown;
  const probeKnown = new Promise(resolve => { confirmProbeKnown = resolve; });
  const meshBus = {
    publish(event) {
      if (event.payload?.agent === 'claude'
        && event.payload?.phase === 'status'
        && event.payload?.text === 'claude processing...') {
        confirmProbeKnown();
      }
    },
  };
  const server = http.createServer((req, res) => {
    if (req.method === 'POST' && req.url === '/tasks/sendSubscribe') {
      submissions += 1;
      if (submissions <= 2) {
        res.writeHead(500); res.end('falha transitória');
      } else if (submissions === 3) {
        probeStream = res;
        res.writeHead(200, { 'Content-Type': 'text/event-stream' });
        res.write('event: task-status\ndata: {"id":"half-open-probe","status":{"state":"working"}}\n\n');
      } else {
        res.writeHead(200, { 'Content-Type': 'text/event-stream' });
        res.end('event: task-status\ndata: {"id":"half-open-success","status":{"state":"completed","message":{"parts":[{"type":"text","text":"recuperado"}]}}}\n\n');
      }
      return;
    }
    if (req.method === 'POST' && req.url === '/tasks/half-open-probe/cancel') {
      probeStream?.end();
      res.writeHead(200, { 'Content-Type': 'application/json' });
      res.end(JSON.stringify({ result: { id: 'half-open-probe', status: { state: 'canceled' } } }));
      return;
    }
    res.writeHead(404); res.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'codex', peers: { claude: `http://127.0.0.1:${port}` }, maxDepth: 7,
      meshBus,
    });
    assert.match(await caller.executeA2ACall(
      { agent: 'claude', prompt: 'abrir circuito', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-open' },
    ), /HTTP 500/);
    await new Promise(resolve => setTimeout(resolve, 5));
    const controller = new AbortController();
    const probe = caller.executeA2ACall(
      { agent: 'claude', prompt: 'sonda', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-probe', signal: controller.signal },
    );
    await probeKnown;
    controller.abort(new Error('cancelar sonda'));
    assert.match(await probe, /Task canceled by caller/);
    const recovered = await caller.executeA2ACall(
      { agent: 'claude', prompt: 'nova sonda', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'parent-after-probe' },
    );
    assert.equal(recovered, 'recuperado');
    assert.equal(submissions, 4);
  } finally {
    probeStream?.end();
    await new Promise(resolve => server.close(resolve));
    const restore = (name, value) => {
      if (value === undefined) delete process.env[name];
      else process.env[name] = value;
    };
    restore('A2A_PEER_CB_FAILURE_THRESHOLD', previous.threshold);
    restore('A2A_PEER_CB_OPEN_MS', previous.open);
    restore('A2A_PEER_RETRY_BASE_DELAY_MS', previous.base);
    restore('A2A_PEER_RETRY_MAX_DELAY_MS', previous.max);
    restore('A2A_PEER_RETRY_JITTER_MS', previous.jitter);
  }
});
