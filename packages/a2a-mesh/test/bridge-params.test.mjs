import assert from 'node:assert/strict';
import test from 'node:test';

import {
  callBridgeParams,
  consensusBridgeParams,
  debateBridgeParams,
  ensembleBridgeParams,
  planBridgeParams,
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
    { task: 't', language: 'typescript', rounds: 20, agents: ['codex', 'grok'], judge: 'claude', profile: 'deep', deduplicate: false, early_exit: false },
    { depth: 2, meshChain: [] },
  );
  assert.deepEqual(params.agents, ['codex', 'grok']);
  assert.equal(params.rounds, 12);
  assert.equal(params.judge, 'claude');
  assert.equal(params.profile, 'deep');
  assert.equal(params.deduplicate, false);
  assert.equal(params.early_exit, false);
});

test('bridge deixa o perfil definir as rodadas quando não há override explícito', () => {
  const params = ensembleBridgeParams(
    { task: 't', profile: 'normal', agents: ['codex'] },
    { depth: 2, meshChain: [] },
  );
  assert.equal(params.profile, 'normal');
  assert.equal(Object.hasOwn(params, 'rounds'), false);
});

test('perfis definem defaults de debate e plano, mas rodada explícita prevalece', () => {
  assert.equal(debateBridgeParams({ topic: 't', profile: 'fast' }, {}).rounds, 2);
  assert.equal(debateBridgeParams({ topic: 't', profile: 'deep', rounds: 11 }, {}).rounds, 11);
  assert.equal(planBridgeParams({ description: 'p', profile: 'deep' }, {}).rounds, 6);
  assert.equal(planBridgeParams({ description: 'p', profile: 'fast', rounds: 7 }, {}).rounds, 7);
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
