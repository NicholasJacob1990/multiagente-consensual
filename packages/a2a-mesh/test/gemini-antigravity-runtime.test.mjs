import assert from 'node:assert/strict';
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

import { RUNTIME_ROOT } from '../npm/cli.mjs';

async function freePort() {
  const server = net.createServer();
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const { port } = server.address();
  await new Promise((resolve, reject) => server.close((error) => error ? reject(error) : resolve()));
  return port;
}

async function waitForHealth(port, child, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Gemini peer exited with ${child.exitCode}`);
    try {
      const response = await fetch(`http://127.0.0.1:${port}/health`, { signal: AbortSignal.timeout(500) });
      if (response.ok) return response.json();
    } catch {
      // O peer ainda está iniciando.
    }
    await new Promise((resolve) => setTimeout(resolve, 100));
  }
  throw new Error('timeout esperando Gemini Antigravity');
}

test('Gemini usa Antigravity como rota efetiva quando o provider CLI é antigravity', { timeout: 30000 }, async () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-gemini-antigravity-'));
  const tokenFile = path.join(root, '.a2a', 'auth-token');
  const agy = path.join(root, 'agy');
  fs.mkdirSync(path.dirname(tokenFile), { recursive: true });
  fs.writeFileSync(tokenFile, 'test-token\n', { mode: 0o600 });
  fs.writeFileSync(agy, [
    '#!/bin/sh',
    'if [ "$1" = "models" ]; then',
    "  printf 'gemini-3.7-flash-high\\tGemini 3.7 Flash (High)\\n'",
    '  exit 0',
    'fi',
    'exit 23',
    '',
  ].join('\n'), { mode: 0o700 });

  const port = await freePort();
  const entry = path.join(RUNTIME_ROOT, 'a2a-gemini', 'server.js');
  const child = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env: {
      ...process.env,
      HOME: root,
      PATH: `${root}:${process.env.PATH || ''}`,
      A2A_PORT: String(port),
      A2A_GEMINI_PORT: String(port),
      A2A_GEMINI_DATA_DIR: path.join(root, 'tasks'),
      A2A_AUTH_TOKEN_FILE: tokenFile,
      A2A_ALLOW_NO_TOKEN: 'false',
      A2A_AUTO_START: 'false',
      A2A_SUPERVISOR_PID: String(process.pid),
      A2A_SUPERVISOR_MODE: 'foreground',
      GEMINI_CLI_PROVIDER: 'antigravity',
      ANTIGRAVITY_CLI: agy,
      ANTIGRAVITY_MODEL: 'gemini-3.7-flash-high',
      USE_CLI: '',
    },
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  let stderr = '';
  child.stderr.on('data', (chunk) => { stderr += chunk; });
  try {
    const health = await waitForHealth(port, child);
    assert.equal(health.mode, 'cli');
    assert.equal(health.route, 'antigravity');
    assert.equal(health.model, 'gemini-3.7-flash-high');
    assert.deepEqual(health.runtimeIdentity, {
      owner: '@nicholasjacob90/a2a-mesh',
      agentId: 'gemini',
    });
  } catch (error) {
    error.message += `\nGemini stderr: ${stderr.slice(-2000)}`;
    throw error;
  } finally {
    child.kill('SIGTERM');
    if (child.exitCode === null) await new Promise((resolve) => child.once('exit', resolve));
    fs.rmSync(root, { recursive: true, force: true });
  }
});
