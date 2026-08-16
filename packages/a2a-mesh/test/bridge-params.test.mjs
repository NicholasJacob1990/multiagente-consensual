import assert from 'node:assert/strict';
import test from 'node:test';

import {
  callBridgeParams,
  consensusBridgeParams,
  ensembleBridgeParams,
  teamBridgeParams,
} from '../runtime/a2a-shared/bridge-params.js';

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

test('bridge preserva profundidade e cadeia em chamadas simples e equipes', () => {
  assert.deepEqual(
    callBridgeParams(
      { agent: 'claude', prompt: 'p' },
      { depth: 4, meshChain: ['codex'] },
    ),
    { agent: 'claude', prompt: 'p', depth: 4, meshChain: ['codex'] },
  );
  const team = teamBridgeParams(
    { name: 't', steps: [{ mode: 'parallel', agents: ['claude'], prompt: 'p' }] },
    { depth: 2, meshChain: ['codex'] },
  );
  assert.equal(team.depth, 2);
  assert.deepEqual(team.meshChain, ['codex']);
});

test('bridge recusa profundidade esgotada e ciclos antes de submeter trabalho', () => {
  assert.throws(
    () => callBridgeParams({ agent: 'claude', prompt: 'p' }, { depth: 0, meshChain: ['codex'] }),
    /max mesh depth exceeded/,
  );
  assert.throws(
    () => consensusBridgeParams(
      { prompt: 'p', agents: ['claude'], judge: 'codex' },
      { depth: 3, meshChain: ['claude'] },
    ),
    /mesh loop detected/,
  );
});
