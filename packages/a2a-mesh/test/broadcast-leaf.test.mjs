import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';

import {
  BROADCAST_LEAF_POLICY,
  buildBroadcastPrompt,
  createMeshCaller,
} from '../runtime/a2a-shared/mesh-calls.js';

function startPeer(captured) {
  const server = http.createServer((req, res) => {
    if (req.method !== 'POST' || req.url !== '/tasks/sendSubscribe') {
      res.writeHead(404); res.end(); return;
    }
    const chunks = [];
    req.on('data', (chunk) => chunks.push(chunk));
    req.on('end', () => {
      captured.push(JSON.parse(Buffer.concat(chunks).toString('utf8')));
      res.writeHead(200, { 'Content-Type': 'text/event-stream' });
      res.end('event: task-status\ndata: {"id":"remote-broadcast","status":{"state":"completed","message":{"parts":[{"type":"text","text":"resposta direta"}]}}}\n\n');
    });
  });
  return new Promise((resolve) => server.listen(0, '127.0.0.1', () => resolve(server)));
}

test('broadcast comum transforma cada destinatário em folha sem recursão', async () => {
  const captured = [];
  const server = await startPeer(captured);
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'claude',
      peers: { codex: `http://127.0.0.1:${port}` },
      maxDepth: 7,
    });
    const result = await caller.executeA2ABroadcast(
      { prompt: 'Olá, responda em uma frase.', timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'broadcast-leaf' },
    );
    assert.match(result, /resposta direta/);
    assert.equal(captured.length, 1);
    assert.equal(captured[0].metadata.maxDepth, 0);
    assert.equal(captured[0].metadata.interactionMode, 'broadcast_leaf');
    assert.equal(captured[0].metadata.delegationAllowed, false);
    assert.match(captured[0].message.parts[0].text, /DIRECT BROADCAST RESPONSE/);
    assert.match(captured[0].message.parts[0].text, /Olá, responda em uma frase\./);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('broadcast recursivo só ocorre com opt-in explícito', async () => {
  const captured = [];
  const server = await startPeer(captured);
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'claude',
      peers: { codex: `http://127.0.0.1:${port}` },
      maxDepth: 7,
    });
    await caller.executeA2ABroadcast(
      { prompt: 'Investigue em subagentes.', recursive: true, timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'broadcast-recursive' },
    );
    assert.equal(captured[0].metadata.maxDepth, 6);
    assert.equal(captured[0].metadata.interactionMode, 'broadcast_recursive');
    assert.equal(captured[0].metadata.delegationAllowed, true);
    assert.equal(captured[0].message.parts[0].text, 'Investigue em subagentes.');
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});

test('prompt de folha é natural e não vaza a política na resposta esperada', () => {
  const wrapped = buildBroadcastPrompt('Pergunta', { allowDelegation: false });
  assert.ok(wrapped.startsWith(BROADCAST_LEAF_POLICY));
  assert.match(wrapped, /Answer the user's prompt directly and naturally/);
  assert.match(wrapped, /do not retry login, search for credentials/);
  assert.equal(buildBroadcastPrompt('Pergunta', { allowDelegation: true }), 'Pergunta');
});

test('papel interno atribuído desliga subdelegação e narração', async () => {
  const captured = [];
  const server = await startPeer(captured);
  try {
    const { port } = server.address();
    const caller = createMeshCaller({
      selfId: 'claude',
      peers: { grok: `http://127.0.0.1:${port}` },
      maxDepth: 7,
    });
    await caller.executeA2ACall(
      { agent: 'grok', prompt: 'Apresente o argumento final.', allowDelegation: false, timeout_ms: 2000 },
      { depth: 7, meshChain: [], taskId: 'assigned-role-leaf' },
    );
    assert.equal(captured[0].metadata.maxDepth, 0);
    assert.equal(captured[0].metadata.interactionMode, 'assigned_role_leaf');
    assert.equal(captured[0].metadata.delegationAllowed, false);
    assert.match(captured[0].message.parts[0].text, /Do not narrate your process/);
    assert.match(captured[0].message.parts[0].text, /not retry authentication/);
    assert.match(captured[0].message.parts[0].text, /Apresente o argumento final\./);
  } finally {
    await new Promise((resolve) => server.close(resolve));
  }
});
