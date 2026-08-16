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
  parseCursorModels,
  parseCursorStreamLine,
} from '../runtime/a2a-grok/cursor-cli-adapter.js';
import {
  OFFICIAL_GROK_MODEL,
  buildOfficialGrokArgs,
  createOfficialGrokExecutor,
  parseOfficialGrokModels,
  parseOfficialGrokStreamLine,
  probeOfficialGrok,
} from '../runtime/a2a-grok/official-cli-adapter.js';

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

test('catálogo Cursor ignora cabeçalho e dica de uso', () => {
  assert.deepEqual(
    parseCursorModels('Available models\n\nauto - Auto (default)\ncursor-grok-4.6-high - Grok 4.6\nTip: use --model'),
    ['auto', 'cursor-grok-4.6-high'],
  );
});

test('executor Cursor aceita troca explícita para modelo do catálogo', () => {
  const executor = createCursorExecutor({
    binary: 'cursor-agent',
    taskManager: { taskEmitter: new EventEmitter() },
  });
  executor.updateModel('cursor-grok-4.6-xhigh', { verified: true });
  assert.equal(executor.configuredModel, 'cursor-grok-4.6-xhigh');
  assert.equal(executor.healthState.configuredModel, 'cursor-grok-4.6-xhigh');
  assert.equal(executor.healthState.modelVerified, true);
});

test('publica a resposta terminal do Grok uma única vez', async () => {
  const { task } = await executeFixture([
    { type: 'system', subtype: 'init', model: 'Cursor Grok 4.6 High' },
    { type: 'assistant', message: { text: 'resposta natural' } },
    { type: 'result', subtype: 'success', result: 'resposta natural' },
  ]);
  assert.equal(task.status.state, 'completed');
  assert.equal(task.status.message.parts[0].text, 'resposta natural');
});

test('configura a CLI oficial com rota explícita, esforço xhigh e sandbox desligado', () => {
  const args = buildOfficialGrokArgs({ workspace: '/tmp/projeto', promptFile: '/tmp/prompt.md' });
  assert.ok(args.includes('streaming-json'));
  assert.ok(args.includes('bypassPermissions'));
  assert.ok(args.includes('off'));
  assert.deepEqual(args.slice(0, 2), ['--prompt-file', '/tmp/prompt.md']);
  assert.equal(args[args.indexOf('--model') + 1], OFFICIAL_GROK_MODEL);
  assert.equal(args[args.indexOf('--reasoning-effort') + 1], 'xhigh');
});

test('interpreta catálogo e streaming da CLI oficial', () => {
  assert.deepEqual(parseOfficialGrokModels('Default model: grok-4.6\nAvailable models:\n  * grok-4.6 (default)'), ['grok-4.6']);
  assert.deepEqual(parseOfficialGrokStreamLine('{"type":"text","data":"olá"}').text, 'olá');
  assert.equal(parseOfficialGrokStreamLine('{"type":"end"}').terminal, true);
  assert.equal(parseOfficialGrokStreamLine('não json'), null);
});

test('distingue CLI oficial instalada de sessão autenticada', () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-grok-official-probe-'));
  const binary = path.join(workspace, 'grok');
  fs.writeFileSync(binary, '#!/bin/sh\nprintf "You are not authenticated.\\nDefault model: grok-4.6\\nAvailable models:\\n  * grok-4.6 (default)\\n"\n', { mode: 0o700 });
  try {
    const probe = probeOfficialGrok(binary);
    assert.equal(probe.available, true);
    assert.equal(probe.modelAvailable, true);
    assert.equal(probe.authenticated, false);
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
});

test('executa resposta da CLI oficial sem fallback para Cursor', async () => {
  const workspace = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-grok-official-fixture-'));
  const binary = path.join(workspace, 'grok');
  fs.writeFileSync(binary, `#!/usr/bin/env node
if (process.argv[2] === 'models') {
  console.log('Default model: grok-4.6');
  console.log('Available models:');
  console.log('  * grok-4.6 (default)');
} else {
  console.log(JSON.stringify({ type: 'text', data: 'resposta oficial' }));
  console.log(JSON.stringify({ type: 'end', model: 'grok-4.6', session_id: 'sessao-oficial' }));
}
`, { mode: 0o700 });
  const taskManager = {
    taskEmitter: new EventEmitter(),
    updateTask(task, update) { Object.assign(task, update); },
    taskToJSON(task) { return task; },
  };
  const task = {
    id: 'official-fixture',
    history: [{ role: 'user', parts: [{ type: 'text', text: 'teste' }] }],
    status: { state: 'submitted' },
    metadata: { maxDepth: 0 },
  };
  const executor = createOfficialGrokExecutor({
    binary,
    workspace,
    taskManager,
    cliTimeoutMs: 5000,
    initialProbe: { authenticated: true, modelAvailable: true },
    cliToolWrapper: { buildA2AToolPrefix: () => '', parseToolCall: () => null, removeToolCalls: (text) => text },
    dispatchTool: async () => '',
    normalizeToolOutput: String,
  });
  try {
    await executor.executeTask(task, () => {}, { signal: new AbortController().signal });
    assert.equal(task.status.state, 'completed');
    assert.equal(task.status.message.parts[0].text, 'resposta oficial');
    assert.equal(task.metadata.providerRuntime, 'grok-official');
    assert.equal(task.metadata.providerRoute, 'official');
    assert.equal(task.metadata.observedModel, 'grok-4.6');
  } finally {
    fs.rmSync(workspace, { recursive: true, force: true });
  }
});
