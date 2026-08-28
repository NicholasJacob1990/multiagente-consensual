import assert from 'node:assert/strict';
import test from 'node:test';

import { createDebateExecutor } from '../runtime/a2a-shared/mesh-debate.js';

test('debate explícito falha antes da primeira rodada quando um participante não tem heartbeat atual', async () => {
  const checked = [];
  let calls = 0;
  const executor = createDebateExecutor({
    meshCaller: {
      async executeA2ACall() {
        calls += 1;
        return 'argumento que não deveria ser solicitado';
      },
    },
    peers: {
      claude: 'http://127.0.0.1:3142',
      gemini: 'http://127.0.0.1:3143',
    },
    selfId: 'codex',
    selfUrl: 'http://127.0.0.1:3141',
    maxDepth: 7,
    peerDiscovery: {
      async checkHealth(agentId) {
        checked.push(agentId);
        return agentId === 'claude';
      },
      getPeer(agentId) {
        return {
          status: agentId === 'claude' ? 'online' : 'offline',
          lastSeen: null,
        };
      },
    },
  });

  await assert.rejects(
    executor.execute({
      topic: 'decisão arquitetural',
      agents: ['claude', 'gemini'],
      judge: 'codex',
      rounds: 1,
    }),
    /Debate preflight failed.*gemini.*last seen: never/i,
  );
  assert.deepEqual(checked, ['claude', 'gemini']);
  assert.equal(calls, 0);
});

test('debate rejeita participante explícito desconhecido em vez de substituí-lo pelo roster padrão', async () => {
  let calls = 0;
  const executor = createDebateExecutor({
    meshCaller: {
      async executeA2ACall() {
        calls += 1;
        return 'não deveria executar';
      },
    },
    peers: { claude: 'http://127.0.0.1:3142' },
    selfId: 'codex',
    selfUrl: 'http://127.0.0.1:3141',
    maxDepth: 7,
  });

  await assert.rejects(
    executor.execute({
      topic: 'decisão arquitetural',
      agents: ['claude', 'typo-gemini'],
      rounds: 1,
    }),
    /Unknown debate agents: typo-gemini/,
  );
  assert.equal(calls, 0);
});

test('debate explícito aborta se participante falha depois de passar no preflight', async () => {
  const executor = createDebateExecutor({
    meshCaller: {
      async executeA2ACall({ agent }) {
        if (agent === 'gemini') return 'Error from gemini: transport failed';
        return 'argumento válido';
      },
    },
    peers: {
      claude: 'http://127.0.0.1:3142',
      gemini: 'http://127.0.0.1:3143',
    },
    selfId: 'codex',
    selfUrl: 'http://127.0.0.1:3141',
    maxDepth: 7,
    peerDiscovery: {
      async checkHealth() { return true; },
      getPeer() { return { status: 'online', lastSeen: new Date() }; },
    },
  });

  await assert.rejects(
    executor.execute({
      topic: 'decisão arquitetural',
      agents: ['claude', 'gemini'],
      rounds: 1,
    }),
    /Debate participant gemini failed in round 1.*transport failed/i,
  );
});
