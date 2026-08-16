import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import {
  buildExternalCliArgs,
  parseKimiStreamLine,
  parseOpenCodeStreamLine,
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

test('rotas externas fixam modelos e esforço máximo do OpenCode', () => {
  const glm = buildExternalCliArgs({ route: 'opencode', model: 'opencode-go/glm-5.3', prompt: 'tarefa' });
  assert.deepEqual(glm.slice(0, 8), ['run', '--model', 'opencode-go/glm-5.3', '--variant', 'max', '--format', 'json', '--auto']);
  const qwen = buildExternalCliArgs({ route: 'opencode', model: 'opencode-go/qwen3.8-max', prompt: 'tarefa' });
  assert.deepEqual(qwen.slice(0, 8), ['run', '--model', 'opencode-go/qwen3.8-max', '--variant', 'max', '--format', 'json', '--auto']);
  const kimi = buildExternalCliArgs({ route: 'kimi-code', model: 'kimi-code/k3', prompt: 'tarefa' });
  assert.deepEqual(kimi, ['--model', 'kimi-code/k3', '--prompt', 'tarefa', '--output-format', 'stream-json']);
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
