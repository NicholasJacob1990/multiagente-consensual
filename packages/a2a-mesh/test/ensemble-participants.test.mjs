import assert from 'node:assert/strict';
import test from 'node:test';

import {
  canonicalizeCodeSubmission,
  clusterCodeSubmissions,
  createCodeEnsembleExecutor,
} from '../runtime/a2a-shared/mesh-code-ensemble.js';

test('normaliza formatação e agrupa candidatos equivalentes', () => {
  const compact = '```js\nfunction f(x){\nreturn x+1;\n}\n```';
  const spaced = 'function f(x){\n\n  return x+1;  \n}';
  assert.equal(canonicalizeCodeSubmission(compact), canonicalizeCodeSubmission(spaced));
  const clusters = clusterCodeSubmissions({ alpha: compact, beta: spaced, gamma: 'function f(x){return x+2;}' });
  assert.equal(clusters.length, 2);
  assert.deepEqual(clusters[0].agents, ['alpha', 'beta']);
});

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

test('ensemble aceita revisão que mantém código já correto', async () => {
  const events = [];
  const originalCode = 'function isEven(n) {\n  if (!Number.isInteger(n)) throw new TypeError("integer");\n  return n % 2 === 0;\n}';
  const meshCaller = {
    async executeA2ABroadcast() {
      return `**alpha**: ${originalCode}\n\n---\n\n**beta**: ${originalCode}`;
    },
    async executeA2ACall({ prompt }) {
      if (prompt.includes('expert code reviewer')) return 'Correct, concise, 10/10.';
      if (prompt.includes('Revise your code')) return originalCode;
      if (prompt.includes('Synthesize the best')) return originalCode;
      throw new Error(`unexpected prompt: ${prompt.slice(0, 40)}`);
    },
  };
  const executor = createCodeEnsembleExecutor({
    meshCaller,
    peers: { alpha: 'http://127.0.0.1:1', beta: 'http://127.0.0.1:2' },
    selfId: 'coordinator',
    maxDepth: 7,
    meshBus: { publish(event) { events.push(event); } },
  });

  const result = await executor.execute({
    task: 'Implement isEven',
    language: 'javascript',
    rounds: 1,
    judge: 'alpha',
    agents: ['alpha', 'beta'],
    deduplicate: false,
    early_exit: false,
  });

  assert.equal(result.finalCode, originalCode);
  const dialogue = events.filter(event => event.type === 'dialogue').map(event => event.payload);
  assert.equal(dialogue.filter(event => event.role === 'revised').length, 2);
  assert.equal(dialogue.some(event => /Revision rejected/.test(event.text)), false);
});

test('ensemble encerra NxN cedo quando todos os candidatos são equivalentes', async () => {
  const prompts = [];
  const code = 'function ok(){\n  return true;\n}';
  const executor = createCodeEnsembleExecutor({
    meshCaller: {
      async executeA2ABroadcast() {
        return `**alpha**: ${code}\n\n---\n\n**beta**: function ok(){\n\n    return true;\n}`;
      },
      async executeA2ACall({ prompt }) {
        prompts.push(prompt);
        return code;
      },
    },
    peers: { alpha: 'http://127.0.0.1:1', beta: 'http://127.0.0.1:2' },
    selfId: 'coordinator',
    maxDepth: 7,
  });

  const result = await executor.execute({
    task: 'Implement ok',
    language: 'javascript',
    profile: 'fast',
    judge: 'alpha',
    agents: ['alpha', 'beta'],
  });

  assert.equal(result.optimization.earlyExit, true);
  assert.equal(result.optimization.originalCandidates, 2);
  assert.equal(result.optimization.uniqueCandidates, 1);
  assert.deepEqual(result.phases.map(phase => phase.phase), ['write', 'equivalence-consensus', 'synthesize']);
  assert.equal(prompts.length, 1);
  assert.match(prompts[0], /Synthesize the best final solution/);
  assert.doesNotMatch(prompts[0], /expert code reviewer/);
});
