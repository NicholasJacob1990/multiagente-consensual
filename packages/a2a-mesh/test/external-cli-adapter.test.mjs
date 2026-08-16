import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  buildExternalCliArgs,
  createExternalCliExecutor,
  parseKimiStreamLine,
  parseOpenCodeStreamLine,
  verifyKimiSecureCredential,
  verifyOpenCodeModelAvailable,
} from '../runtime/a2a-shared/external-cli-adapter.js';

test('parser OpenCode preserva texto, sessão, custo e uso do modelo', () => {
  const text = parseOpenCodeStreamLine(JSON.stringify({
    type: 'text', sessionID: 'ses-1', part: { type: 'text', text: 'resposta GLM' },
  }));
  assert.equal(text.text, 'resposta GLM');
  assert.equal(text.sessionId, 'ses-1');

  const finish = parseOpenCodeStreamLine(JSON.stringify({
    type: 'step_finish', part: { type: 'step-finish', tokens: { input: 10, output: 4 }, cost: 0.01 },
  }));
  assert.equal(finish.terminal, true);
  assert.deepEqual(finish.usage, { input: 10, output: 4 });
  assert.equal(finish.cost, 0.01);
});

test('parser Kimi ignora metadados e aceita conteúdo de assistente', () => {
  assert.equal(parseKimiStreamLine('{"role":"meta","type":"system.version","version":"0.36.0"}').text, '');
  const response = parseKimiStreamLine('{"role":"assistant","type":"message.delta","content":"resposta Kimi"}');
  assert.equal(response.text, 'resposta Kimi');
});

test('rotas externas preservam o modelo selecionado e esforço máximo do OpenCode', () => {
  const glm = buildExternalCliArgs({ route: 'opencode', model: 'opencode-go/glm-5.3', prompt: 'tarefa' });
  assert.deepEqual(glm.slice(0, 8), ['run', '--model', 'opencode-go/glm-5.3', '--variant', 'max', '--format', 'json', '--auto']);
  const qwen = buildExternalCliArgs({ route: 'opencode', model: 'opencode-go/qwen3.8-max', prompt: 'tarefa' });
  assert.deepEqual(qwen.slice(0, 8), ['run', '--model', 'opencode-go/qwen3.8-max', '--variant', 'max', '--format', 'json', '--auto']);
  const kimi = buildExternalCliArgs({ route: 'kimi-code', model: 'kimi-code/k3', prompt: 'tarefa' });
  assert.deepEqual(kimi, ['--prompt', 'tarefa', '--output-format', 'stream-json']);
  assert.equal(kimi.includes('kimi-code/k3'), false);
});

test('Kimi usa wrapper seguro e não inclui modelo nem credencial nos argumentos', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-kimi-secure-'));
  const binary = path.join(root, 'kimi-secure');
  fs.writeFileSync(binary, '#!/bin/sh\nprintf "__kimi_env__  type=openai  models=1  source=inline\\n"\n', { mode: 0o700 });
  try {
    const probe = verifyKimiSecureCredential(binary);
    assert.equal(probe.verified, true);
    assert.equal(probe.credentialProvider, 'opencode-go');
    assert.equal(probe.credentialSource, 'macos-keychain');
    const args = buildExternalCliArgs({ route: 'kimi-code', model: 'kimi-code/k3', prompt: 'teste' });
    assert.equal(args.includes('--model'), false);
    assert.equal(args.join(' ').includes('kimi-code/k3'), false);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('sonda Kimi falha fechada quando o wrapper não ativa o provider efêmero', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-kimi-secure-invalid-'));
  const binary = path.join(root, 'kimi-secure');
  fs.writeFileSync(binary, '#!/bin/sh\nprintf "opencode-go  type=openai  models=1  source=inline\\n"\n', { mode: 0o700 });
  try {
    assert.throws(() => verifyKimiSecureCredential(binary), /did not activate/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test('executor OpenCode troca modelo somente fora de uma execução', () => {
  const executor = createExternalCliExecutor({
    binary: 'opencode',
    model: 'opencode-go/glm-5.3',
    route: 'opencode',
    selfId: 'glm',
    displayName: 'GLM',
    taskManager: { taskEmitter: { emit() {} } },
  });
  executor.updateModel('opencode-go/kimi-k3', { verified: true });
  assert.equal(executor.configuredModel, 'opencode-go/kimi-k3');
  assert.equal(executor.healthState.configuredModel, 'opencode-go/kimi-k3');
  assert.equal(executor.healthState.modelVerified, true);
});

test('sonda OpenCode falha fechada quando o modelo fixo não existe', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-external-model-'));
  const binary = path.join(root, 'opencode');
  fs.writeFileSync(binary, '#!/bin/sh\nprintf "opencode-go/glm-5.3\\n"\n', { mode: 0o700 });
  try {
    assert.equal(verifyOpenCodeModelAvailable(binary, 'opencode-go/glm-5.3').verified, true);
    assert.throws(() => verifyOpenCodeModelAvailable(binary, 'opencode-go/deepseek-v4-pro'), /unavailable/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});
