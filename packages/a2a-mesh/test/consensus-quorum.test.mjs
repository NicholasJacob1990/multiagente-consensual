import assert from 'node:assert/strict';
import test from 'node:test';

import { createConsensusExecutor } from '../runtime/a2a-shared/mesh-consensus.js';

test('consenso para antes do juiz quando não atinge quórum', async () => {
  let judgeCalls = 0;
  const meshCaller = {
    async executeA2ABroadcast() {
      return '**claude**: resposta válida\n\n---\n\n**grok**: Error: timeout';
    },
    async executeA2ACall() {
      judgeCalls += 1;
      return 'não deveria executar';
    },
  };
  const executor = createConsensusExecutor({
    meshCaller,
    peers: { claude: 'http://127.0.0.1:1', grok: 'http://127.0.0.1:2' },
    selfId: 'codex',
    maxDepth: 7,
  });
  const result = await executor.execute({
    prompt: 'decida',
    agents: ['claude', 'grok'],
    quorum: 2,
  });
  assert.equal(result.approved, false);
  assert.deepEqual(result.quorum, { required: 2, valid: 1, met: false });
  assert.equal(result.synthesis.confidence, 0);
  assert.equal(judgeCalls, 0);
});

test('consenso rejeita agente explícito desconhecido sem chamada externa', async () => {
  let calls = 0;
  const executor = createConsensusExecutor({
    meshCaller: {
      async executeA2ABroadcast() { calls += 1; return ''; },
      async executeA2ACall() { calls += 1; return ''; },
    },
    peers: { claude: 'http://127.0.0.1:1' },
    selfId: 'codex',
    maxDepth: 7,
  });
  await assert.rejects(
    executor.execute({ prompt: 'decida', agents: ['claude', 'inexistente'] }),
    /Unknown consensus agents: inexistente/,
  );
  assert.equal(calls, 0);
});

test('participantes padrão do consenso incluem apenas peers online', async () => {
  const requestedBroadcasts = [];
  const executor = createConsensusExecutor({
    meshCaller: {
      async executeA2ABroadcast(params) {
        requestedBroadcasts.push(params.agents);
        return '**claude**: resposta válida';
      },
      async executeA2ACall() { return 'síntese'; },
    },
    peers: {
      claude: 'http://127.0.0.1:1',
      gemini: 'http://127.0.0.1:2',
      grok: 'http://127.0.0.1:3',
    },
    selfId: 'codex',
    maxDepth: 7,
    selfUrl: 'http://127.0.0.1:9',
    peerDiscovery: {
      async checkAllHealth() {},
      getOnlinePeers() { return { claude: { status: 'online' } }; },
    },
    async selfResponder() {
      return { agent: 'codex', response: null, error: 'self intentionally unavailable in unit test', durationMs: 0 };
    },
  });
  const result = await executor.execute({ prompt: 'decida' });
  assert.deepEqual(requestedBroadcasts, [['claude']]);
  assert.deepEqual(result.agents, ['claude', 'codex']);
  assert.equal(result.quorum.required, 2);
});
