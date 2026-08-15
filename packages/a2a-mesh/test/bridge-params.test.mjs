import assert from 'node:assert/strict';
import test from 'node:test';

import { consensusBridgeParams, ensembleBridgeParams } from '../runtime/a2a-shared/bridge-params.js';

test('bridge encaminha quórum configurável ao consenso', () => {
  assert.deepEqual(
    consensusBridgeParams(
      { prompt: 'p', agents: ['claude', 'grok'], judge: 'codex', quorum: 2 },
      { depth: 3, meshChain: ['gemini'] },
    ),
    { prompt: 'p', agents: ['claude', 'grok'], judge: 'codex', quorum: 2, depth: 3, meshChain: ['gemini'] },
  );
});

test('bridge encaminha o conjunto exato de agentes ao ensemble', () => {
  const params = ensembleBridgeParams(
    { task: 't', language: 'typescript', rounds: 20, agents: ['codex', 'grok'], judge: 'claude' },
    { depth: 2, meshChain: [] },
  );
  assert.deepEqual(params.agents, ['codex', 'grok']);
  assert.equal(params.rounds, 12);
  assert.equal(params.judge, 'claude');
});
