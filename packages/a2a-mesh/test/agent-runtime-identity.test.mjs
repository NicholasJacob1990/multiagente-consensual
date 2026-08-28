import assert from 'node:assert/strict';
import http from 'node:http';
import test from 'node:test';

import { health as cliHealth } from '../npm/cli.mjs';
import { checkAgentHealth } from '../runtime/a2a-shared/agent-supervisor.js';
import { PeerDiscovery } from '../runtime/a2a-shared/peer-registry.js';

async function serveHealth(payload) {
  const server = http.createServer((request, response) => {
    if (request.url === '/health') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify(payload));
      return;
    }
    if (request.url === '/.well-known/agent.json') {
      response.writeHead(200, { 'content-type': 'application/json' });
      response.end(JSON.stringify({ name: 'Gemini Agent' }));
      return;
    }
    response.writeHead(404).end();
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  return {
    baseUrl: `http://127.0.0.1:${port}`,
    port,
    close: () => new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve())),
  };
}

test('supervisores rejeitam health legado que não pertence ao peer empacotado', async () => {
  const fixture = await serveHealth({
    status: 'ok',
    model: 'gemini-3.1-pro-preview',
    mode: 'api',
    protocolVersion: '1.0',
  });
  try {
    assert.equal(await checkAgentHealth(fixture.baseUrl, 1000, 'gemini'), null);
    assert.equal(await cliHealth(fixture.port, 1000, 'gemini'), null);

    const discovery = new PeerDiscovery({ gemini: fixture.baseUrl });
    assert.equal(await discovery.checkHealth('gemini'), false);
    assert.equal(discovery.getPeer('gemini').status, 'offline');
  } finally {
    await fixture.close();
  }
});

test('supervisores aceitam somente a identidade gerenciada do peer esperado', async () => {
  const managed = {
    status: 'ok',
    model: 'gemini-3.7-flash-high',
    mode: 'cli',
    protocolVersion: '1.0',
    runtimeIdentity: {
      owner: '@nicholasjacob90/a2a-mesh',
      agentId: 'gemini',
    },
  };
  const fixture = await serveHealth(managed);
  try {
    assert.deepEqual(await checkAgentHealth(fixture.baseUrl, 1000, 'gemini'), managed);
    assert.deepEqual(await cliHealth(fixture.port, 1000, 'gemini'), managed);

    const discovery = new PeerDiscovery({ gemini: fixture.baseUrl });
    assert.equal(await discovery.checkHealth('gemini'), true);
    assert.equal(discovery.getPeer('gemini').status, 'online');
  } finally {
    await fixture.close();
  }
});
