import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { createRPCAdapter } from '../runtime/a2a-shared/a2a-rpc-adapter.js';
import { createTaskManager } from '../runtime/a2a-shared/task-manager.js';

test('RPC limita profundidade recebida ao teto local', async () => {
  let observedContext = null;
  const adapter = createRPCAdapter({
    tm: {},
    executeTask() {},
    taskTimeoutMs: 1000,
    meshCaller: {
      async executeA2ACall(_params, context) {
        observedContext = context;
        return 'ok';
      },
    },
    maxDepth: 7,
    selfId: 'codex',
    peers: { claude: 'http://127.0.0.1:3142' },
    push: { set() {}, get() {}, delete() {} },
  });

  const response = await adapter.handle(JSON.stringify({
    jsonrpc: '2.0',
    id: 1,
    method: 'mesh/call',
    params: { agent: 'claude', prompt: 'teste', depth: 999 },
  }));

  assert.equal(response.result, 'ok');
  assert.equal(observedContext.depth, 7);
});

test('task manager limita metadata.maxDepth antes de qualquer provider', () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-depth-task-'));
  try {
    const tm = createTaskManager({ dataDir, selfId: 'codex', maxDepth: 7 });
    const task = tm.createTask(
      { role: 'user', parts: [{ type: 'text', text: 'teste' }] },
      { maxDepth: 999 },
    );
    assert.equal(task.metadata.maxDepth, 7);
  } finally {
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
