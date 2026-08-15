import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  REQUIRED_GROK_MODEL,
  buildCursorArgs,
  createCursorExecutor,
  modelLabelsMatch,
  parseCursorStreamLine,
} from '../runtime/a2a-grok/cursor-cli-adapter.js';

test('fixa Grok 4.6 High e usa stream-json sem aprovar MCPs globalmente', () => {
  const args = buildCursorArgs({ workspace: '/tmp/projeto' });
  assert.deepEqual(args.slice(-2), ['--model', REQUIRED_GROK_MODEL]);
  assert.ok(args.includes('stream-json'));
  assert.ok(args.includes('--sandbox'));
  assert.ok(args.includes('disabled'));
  assert.ok(!args.includes('--approve-mcps'));
});

async function executeFixture(events) {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-grok-fixture-'));
  const binary = path.join(workspace, 'fake-cursor');
  const serialized = JSON.stringify(events);
  fs.writeFileSync(binary, `#!/usr/bin/env node\nprocess.stdin.resume(); process.stdin.on('end', () => { for (const event of ${serialized}) console.log(JSON.stringify(event)); });\n`, { mode: 0o700 });
  const taskManager = {
    taskEmitter: new EventEmitter(),
    updateTask(task, update) { Object.assign(task, update); },
    taskToJSON(task) { return task; },
  };
  const task = {
    id: 'fixture',
    history: [{ role: 'user', parts: [{ type: 'text', text: 'teste' }] }],
    status: { state: 'submitted' },
    metadata: { maxDepth: 0 },
  };
  const executor = createCursorExecutor({
    binary,
    workspace,
    taskManager,
    cliTimeoutMs: 5000,
    cliToolWrapper: { buildA2AToolPrefix: () => '', parseToolCall: () => null, removeToolCalls: (text) => text },
    dispatchTool: async () => '',
    normalizeToolOutput: String,
  });
  try {
    await executor.executeTask(task, () => {}, { signal: new AbortController().signal });
    return { task, healthState: executor.healthState };
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
}

test('falha fechado em mismatch de modelo', async () => {
  const { task, healthState } = await executeFixture([
    { type: 'system', subtype: 'init', model: 'Outro Modelo' },
    { type: 'result', subtype: 'success', result: 'não aceitar' },
  ]);
  assert.equal(task.status.state, 'failed');
  assert.match(task.status.message.parts[0].text, /model_mismatch/);
  assert.equal(healthState.modelVerified, false);
});

test('falha fechado sem result terminal e não promove parcial', async () => {
  const { task } = await executeFixture([
    { type: 'system', subtype: 'init', model: 'Cursor Grok 4.6 High' },
    { type: 'assistant', message: { text: 'parcial' } },
  ]);
  assert.equal(task.status.state, 'failed');
  assert.match(task.status.message.parts[0].text, /incomplete_stream/);
});

test('confirma o rótulo observado e exige evento terminal', () => {
  const init = parseCursorStreamLine(JSON.stringify({ type: 'system', subtype: 'init', model: 'Cursor Grok 4.6 High' }));
  const result = parseCursorStreamLine(JSON.stringify({ type: 'result', subtype: 'success', result: 'ok' }));
  assert.equal(modelLabelsMatch(REQUIRED_GROK_MODEL, init.model), true);
  assert.equal(result.terminal, true);
  assert.equal(result.result, 'ok');
  assert.equal(parseCursorStreamLine('texto parcial não JSON'), null);
});
