import assert from 'node:assert/strict';
import test from 'node:test';

import { createCodeEnsembleExecutor } from '../runtime/a2a-shared/mesh-code-ensemble.js';

test('ensemble rejeita agente explícito desconhecido sem chamada externa', async () => {
  let calls = 0;
  const executor = createCodeEnsembleExecutor({
    meshCaller: {
      async executeA2ABroadcast() { calls += 1; return ''; },
      async executeA2ACall() { calls += 1; return ''; },
    },
    peers: { claude: 'http://127.0.0.1:1' },
    selfId: 'codex',
    maxDepth: 7,
  });

  await assert.rejects(
    executor.execute({ task: 'implemente', agents: ['claude', 'inexistente'] }),
    /Unknown ensemble agents: inexistente/,
  );
  assert.equal(calls, 0);
});
