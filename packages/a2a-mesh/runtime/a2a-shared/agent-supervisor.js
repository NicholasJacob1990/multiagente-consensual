// ============================================
// Local A2A agent supervisor
// ============================================

import fs from 'node:fs';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { AGENT_IDS as CATALOG_AGENT_IDS } from './agent-catalog.js';
import { isManagedAgentHealth } from './runtime-identity.js';

const LOCAL_HOSTS = new Set(['localhost', '127.0.0.1', '::1']);
const AGENT_IDS = new Set(CATALOG_AGENT_IDS);
const inFlightStarts = new Map();

function getAgentDirectory(agentId) {
  const packagedRuntimeRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
  const baseDir = process.env.A2A_BASE_DIR || packagedRuntimeRoot;
  return path.join(baseDir, `a2a-${agentId}`);
}

function assertLocalAgent(agentId, baseUrl) {
  if (!AGENT_IDS.has(agentId)) {
    throw new Error(`Unknown A2A agent: ${agentId}`);
  }

  const url = new URL(baseUrl);
  if (url.protocol !== 'http:' || !LOCAL_HOSTS.has(url.hostname)) {
    throw new Error(`Auto-start is only supported for local HTTP peers: ${baseUrl}`);
  }
  if (!url.port) {
    throw new Error(`A2A peer URL must include a port: ${baseUrl}`);
  }
  return url;
}

export function checkAgentHealth(baseUrl, timeoutMs = 3000, expectedAgentId = null) {
  return new Promise((resolve) => {
    const request = http.get(new URL('/health', baseUrl), (response) => {
      const chunks = [];
      response.on('data', (chunk) => chunks.push(chunk));
      response.on('end', () => {
        if (response.statusCode < 200 || response.statusCode >= 300) {
          resolve(null);
          return;
        }
        try {
          const health = JSON.parse(Buffer.concat(chunks).toString());
          resolve(isManagedAgentHealth(health, expectedAgentId) ? health : null);
        } catch {
          resolve(null);
        }
      });
    });
    request.on('error', () => resolve(null));
    request.setTimeout(timeoutMs, () => {
      request.destroy();
      resolve(null);
    });
  });
}

async function startLocalAgent(agentId, baseUrl, timeoutMs) {
  if (!AGENT_IDS.has(agentId)) {
    throw new Error(`Unknown A2A agent: ${agentId}`);
  }
  const currentHealth = await checkAgentHealth(baseUrl, 3000, agentId);
  if (currentHealth) return currentHealth;

  const foreignHealth = await checkAgentHealth(baseUrl);
  if (foreignHealth) {
    throw new Error(`A2A agent ${agentId} port is owned by an incompatible or legacy runtime at ${baseUrl}`);
  }

  if (process.env.A2A_AUTO_START === 'false') {
    throw new Error(`A2A agent ${agentId} is offline at ${baseUrl} and auto-start is disabled`);
  }

  const url = assertLocalAgent(agentId, baseUrl);
  const agentDirectory = getAgentDirectory(agentId);
  const serverPath = path.join(agentDirectory, 'server.js');
  if (!fs.existsSync(serverPath)) {
    throw new Error(`A2A server entrypoint not found: ${serverPath}`);
  }

  let spawnError = null;
  const child = spawn(process.execPath, [serverPath], {
    cwd: agentDirectory,
    stdio: 'ignore',
    detached: true,
    env: {
      ...process.env,
      A2A_PORT: url.port,
      [`A2A_${agentId.toUpperCase()}_PORT`]: url.port,
      [`A2A_${agentId.toUpperCase()}_DATA_DIR`]: process.env[`A2A_${agentId.toUpperCase()}_DATA_DIR`]
        || path.join(os.homedir(), '.local', 'state', 'a2a-mesh', 'tasks', agentId),
    },
  });
  child.once('error', (error) => { spawnError = error; });
  child.unref();

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (spawnError) {
      throw new Error(`Failed to start A2A agent ${agentId}: ${spawnError.message}`);
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
    const health = await checkAgentHealth(baseUrl, 1000, agentId);
    if (health) return health;
  }

  throw new Error(`Timed out waiting for A2A agent ${agentId} at ${baseUrl}`);
}

/**
 * Ensure a local A2A peer is online. Concurrent callers share one start attempt.
 */
export function ensureAgentOnline(agentId, baseUrl, options = {}) {
  const timeoutMs = options.timeoutMs ?? (agentId === 'gemini'
    ? Number.parseInt(process.env.A2A_GEMINI_STARTUP_TIMEOUT_MS || '120000', 10)
    : 20000);
  const key = `${agentId}:${baseUrl}`;
  if (inFlightStarts.has(key)) return inFlightStarts.get(key);

  const start = startLocalAgent(agentId, baseUrl, timeoutMs)
    .finally(() => inFlightStarts.delete(key));
  inFlightStarts.set(key, start);
  return start;
}
