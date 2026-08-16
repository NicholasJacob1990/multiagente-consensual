// ============================================
// Base A2A Server — Shared HTTP server factory
// ============================================

import http from 'http';
import https from 'https';
import fs from 'fs';
import { timingSafeEqual } from 'crypto';
import { createRPCAdapter } from './a2a-rpc-adapter.js';
import { A2A_PROTOCOL_VERSION, A2A_VERSION_HEADER, checkVersionHeader } from './protocol.js';
import { TERMINAL_STATES } from './task-states.js';
import { createSandboxManager } from './sandbox-manager.js';
import { mergeRequestTaskMetadata } from './provider-session.js';
import { DEFAULT_PORTS, publicAgentCatalog } from './agent-catalog.js';
import { recoverPartialArtifacts } from './partial-output.js';

// --- Shared helpers ---

export function extractPromptText(message) {
  return message.parts
    .filter(p => p.type === 'text')
    .map(p => p.text)
    .join('\n');
}

export function extractArtifacts(output) {
  const artifacts = [];
  const codeBlockRegex = /```(\w+)?\n([\s\S]*?)```/g;
  let match;
  while ((match = codeBlockRegex.exec(output)) !== null) {
    artifacts.push({
      name: match[1] ? `code.${match[1]}` : 'code-snippet',
      description: `Bloco de codigo ${match[1] || ''}`.trim(),
      parts: [{ type: 'text', text: match[2].trim() }],
    });
  }
  return artifacts;
}

// --- HTTP utilities ---

const MAX_BODY_SIZE = (() => {
  const raw = process.env.A2A_MAX_BODY_SIZE_MB;
  const mb = raw ? parseInt(raw, 10) : NaN;
  return Number.isFinite(mb) && mb > 0 ? mb * 1024 * 1024 : 100 * 1024 * 1024;
})(); // default 100 MB; override via A2A_MAX_BODY_SIZE_MB

function parseBody(req) {
  return new Promise((resolve, reject) => {
    const chunks = [];
    let totalLen = 0;
    req.on('data', (chunk) => {
      totalLen += chunk.length;
      if (totalLen > MAX_BODY_SIZE) {
        req.destroy();
        return reject(new Error('Request body too large'));
      }
      chunks.push(chunk);
    });
    req.on('end', () => {
      try {
        const body = Buffer.concat(chunks).toString();
        resolve(body ? JSON.parse(body) : {});
      } catch (e) {
        reject(new Error('Invalid JSON'));
      }
    });
    req.on('error', reject);
  });
}

function sendJSON(res, data, status = 200, extraHeaders = {}) {
  res.writeHead(status, {
    'Content-Type': 'application/json',
    [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
    ...extraHeaders,
  });
  res.end(JSON.stringify(data));
}

function sendSSE(res, event, data) {
  res.write(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function sendError(res, code, message) {
  sendJSON(res, {
    jsonrpc: '2.0',
    error: { code, message },
  }, code >= 400 && code < 600 ? code : 500);
}

function isLoopbackRequest(req) {
  const ip = req.socket?.remoteAddress || '';
  return ip === '127.0.0.1' || ip === '::1' || ip === '::ffff:127.0.0.1';
}

function safeTokenEquals(provided, expected) {
  const a = Buffer.from(String(provided || ''));
  const b = Buffer.from(String(expected || ''));
  if (a.length !== b.length) return false;
  return timingSafeEqual(a, b);
}

function parseCookie(req, name) {
  const raw = String(req.headers.cookie || '');
  for (const part of raw.split(';')) {
    const [key, ...rest] = part.trim().split('=');
    if (key === name) return decodeURIComponent(rest.join('='));
  }
  return '';
}

function clampMeshDepth(value, maximum) {
  const parsed = Number.parseInt(String(value ?? maximum), 10);
  if (!Number.isFinite(parsed)) return maximum;
  return Math.max(0, Math.min(maximum, parsed));
}

function isAllowedLoopbackHost(req, port) {
  const raw = String(req.headers.host || '');
  if (!raw) return false;
  try {
    const parsed = new URL(`http://${raw}`);
    const local = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '[::1]' || parsed.hostname === '::1';
    const matchingPort = !parsed.port || Number(parsed.port) === Number(port);
    return local && matchingPort;
  } catch {
    return false;
  }
}

function isAllowedBrowserOrigin(req, port) {
  const raw = String(req.headers.origin || '');
  if (!raw) return true;
  try {
    const parsed = new URL(raw);
    const local = parsed.hostname === 'localhost' || parsed.hostname === '127.0.0.1' || parsed.hostname === '[::1]' || parsed.hostname === '::1';
    const allowedPorts = new Set([Number(port), ...Object.values(DEFAULT_PORTS)]);
    for (const agentId of Object.keys(DEFAULT_PORTS)) {
      const configured = Number.parseInt(process.env[`A2A_${agentId.toUpperCase()}_PORT`] || '', 10);
      if (Number.isFinite(configured)) allowedPorts.add(configured);
    }
    const allowedPort = Boolean(parsed.port) && allowedPorts.has(Number(parsed.port));
    return local && allowedPort;
  } catch {
    return false;
  }
}

function checkAuth(req, authToken, port) {
  const auth = req.headers['authorization'] || req.headers['a2a-token'] || '';
  const headerToken = auth.startsWith('Bearer ') ? auth.slice(7) : auth;
  const token = headerToken || parseCookie(req, 'A2A-Token');
  const allowLocalBypass = process.env.A2A_ALLOW_NO_TOKEN === 'true'
    && isLoopbackRequest(req)
    && isAllowedLoopbackHost(req, port)
    && isAllowedBrowserOrigin(req, port);

  // Explicit opt-in for local development/testing bypass.
  if (allowLocalBypass) return true;

  // Fail closed by default when token is not configured.
  if (!authToken) return false;

  return safeTokenEquals(token, authToken);
}

function ensureTaskAbortController(task) {
  if (task._abortController) return task._abortController;
  Object.defineProperty(task, '_abortController', {
    value: new AbortController(),
    writable: true,
    configurable: true,
    enumerable: false,
  });
  return task._abortController;
}

export function signalTaskProcess(task, signal) {
  const child = task?.process;
  if (!child || child.exitCode !== null) return false;
  let sent = false;
  if (child.pid && typeof process.kill === 'function') {
    try {
      process.kill(-child.pid, signal);
      sent = true;
    } catch { /* child is not a process-group leader */ }
  }
  try {
    sent = child.kill(signal) || sent;
  } catch { /* process already exited */ }
  return sent;
}

export function scheduleForcedTaskTermination(tasks, {
  graceMs = Number.parseInt(process.env.A2A_KILL_GRACE_MS || '5000', 10),
  exit = () => process.exit(0),
} = {}) {
  return setTimeout(() => {
    for (const task of tasks) signalTaskProcess(task, 'SIGKILL');
    exit();
  }, graceMs);
}

function abortTaskExecution(task, reason = 'Task cancelled') {
  if (task._abortController) {
    try {
      task._abortController.abort(new Error(reason));
    } catch (err) {
      if (process.env.A2A_DEBUG === 'true') {
        console.warn('[task-abort] Failed to abort controller', {
          taskId: task.id,
          error: err instanceof Error ? err.message : String(err),
        });
      }
    }
  }
  if (task.process) {
    const child = task.process;
    const pid = child.pid;
    // Try graceful shutdown first; some CLIs (notably gemini-cli) ignore
    // SIGTERM during inference, so we escalate to SIGKILL after a grace
    // period and target the process group when the child was spawned with
    // detached:true (negative pid signals the whole group on POSIX).
    const sendSignal = (sig) => {
      try {
        signalTaskProcess(task, sig);
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[task-abort] kill signal failed', {
            taskId: task.id, pid, sig, error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    };
    sendSignal('SIGTERM');
    const graceMs = parseInt(process.env.A2A_KILL_GRACE_MS || '5000', 10);
    setTimeout(() => sendSignal('SIGKILL'), graceMs).unref();
  }
}

// --- Agent Card builder ---

/**
 * Deep-merge two objects (target wins over source for primitives;
 * arrays in target fully replace source arrays).
 */
function deepMerge(source, target) {
  const out = { ...source };
  for (const key of Object.keys(target)) {
    const sv = source[key];
    const tv = target[key];
    if (
      tv && typeof tv === 'object' && !Array.isArray(tv) &&
      sv && typeof sv === 'object' && !Array.isArray(sv)
    ) {
      out[key] = deepMerge(sv, tv);
    } else {
      out[key] = tv;
    }
  }
  return out;
}

/**
 * Build a fully-populated Agent Card by merging user-provided overrides
 * on top of sensible defaults derived from the server config.
 *
 * @param {Object} config - The same config object passed to createA2AServer
 * @returns {Object} The merged agent card
 */
export function buildAgentCard(config) {
  const {
    selfId = '',
    authToken = '',
    agentCard: userCard = {},
  } = config;

  const hasAuth = Boolean(authToken);

  const defaults = {
    name: selfId || 'a2a-agent',
    description: '',
    url: '',
    version: '1.0.0',
    protocolVersion: A2A_PROTOCOL_VERSION,
    capabilities: {
      streaming: true,
      pushNotifications: true,
      stateTransitionHistory: true,
      inputRequiredState: true,
      authRequiredState: true,
      rejectedState: true,
    },
    skills: [],
    securitySchemes: {
      bearer: {
        type: 'http',
        scheme: 'bearer',
        description: 'Bearer token authentication',
      },
      a2aToken: {
        type: 'apiKey',
        in: 'header',
        name: 'A2A-Token',
        description: 'A2A mesh token',
      },
    },
    security: hasAuth ? [{ bearer: [] }, { a2aToken: [] }] : [],
    defaultInputModes: ['text'],
    defaultOutputModes: ['text'],
  };

  // Normalize user-provided skills: ensure each has inputModes/outputModes
  const merged = deepMerge(defaults, userCard);
  if (Array.isArray(merged.skills)) {
    merged.skills = merged.skills.map((skill) => ({
      id: skill.id || '',
      name: skill.name || '',
      description: skill.description || '',
      tags: skill.tags || [],
      inputModes: skill.inputModes || merged.defaultInputModes || ['text'],
      outputModes: skill.outputModes || merged.defaultOutputModes || ['text'],
      ...skill,
    }));
  }

  return merged;
}

// --- Route handlers ---

async function handleTaskSend(req, res, ctx) {
  const body = await parseBody(req);
  const message = body.message;
  if (!message || !message.parts || message.parts.length === 0) {
    return sendError(res, 400, 'message with parts is required');
  }

  const { tm } = ctx;
  if (tm.getActiveTasks().length >= tm.maxConcurrent) {
    return sendError(res, 429, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
  }
  tm.evictOldTasks();

  let task;
  if (body.id && tm.tasks.has(body.id)) {
    task = tm.tasks.get(body.id);
    task.history.push(message);
    tm.updateTask(task, { status: { state: 'submitted' } });
  } else {
    task = tm.createTask(message, mergeRequestTaskMetadata(body));
  }

  await new Promise((resolve) => {
    const controller = ensureTaskAbortController(task);
    let timeoutId;
    let settled = false;
    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timeoutId);
      resolve();
    };

    ctx.executeTask(task, (event) => {
      if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') finish();
    }, { signal: controller.signal });

    timeoutId = setTimeout(() => {
      if (task.status.state === 'working') {
        abortTaskExecution(task, `Task timed out after ${ctx.taskTimeoutMs}ms`);
        tm.updateTask(task, {
          status: {
            state: 'failed',
            message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: tarefa excedeu ${ctx.taskTimeoutMs / 60000} minutos` }] },
          },
        });
      }
      finish();
    }, ctx.taskTimeoutMs);
  });

  sendJSON(res, { jsonrpc: '2.0', result: tm.taskToJSON(task) });
}

async function handleTaskSendAsync(req, res, ctx) {
  const body = await parseBody(req);
  const message = body.message;
  if (!message || !message.parts || message.parts.length === 0) {
    return sendError(res, 400, 'message with parts is required');
  }

  const { tm } = ctx;
  if (tm.getActiveTasks().length >= tm.maxConcurrent) {
    return sendError(res, 429, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
  }
  tm.evictOldTasks();

  let task;
  if (body.id && tm.tasks.has(body.id)) {
    task = tm.tasks.get(body.id);
    task.history.push(message);
    tm.updateTask(task, { status: { state: 'submitted' } });
  } else {
    task = tm.createTask(message, mergeRequestTaskMetadata(body));
  }

  // Fire-and-forget: start execution without awaiting
  const controller = ensureTaskAbortController(task);
  let timeoutId;
  ctx.executeTask(task, (event) => {
    if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') {
      clearTimeout(timeoutId);
    }
  }, { signal: controller.signal });
  timeoutId = setTimeout(() => {
    if (task.status.state === 'working') {
      abortTaskExecution(task, `Task timed out after ${ctx.taskTimeoutMs}ms`);
      tm.updateTask(task, {
        status: {
          state: 'failed',
          message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: tarefa excedeu ${ctx.taskTimeoutMs / 60000} minutos` }] },
        },
      });
    }
  }, ctx.taskTimeoutMs);

  // Return 202 Accepted immediately
  sendJSON(res, { jsonrpc: '2.0', result: { id: task.id, status: task.status } }, 202);
}

async function handleTaskSendSubscribe(req, res, ctx) {
  const body = await parseBody(req);
  const message = body.message;
  if (!message || !message.parts || message.parts.length === 0) {
    return sendError(res, 400, 'message with parts is required');
  }

  const { tm } = ctx;
  if (tm.getActiveTasks().length >= tm.maxConcurrent) {
    return sendError(res, 429, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
  }
  tm.evictOldTasks();

  let task;
  if (body.id && tm.tasks.has(body.id)) {
    task = tm.tasks.get(body.id);
    task.history.push(message);
    tm.updateTask(task, { status: { state: 'submitted' } });
  } else {
    task = tm.createTask(message, mergeRequestTaskMetadata(body));
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream',
    'Cache-Control': 'no-cache',
    'Connection': 'keep-alive',
    [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
  });

  sendSSE(res, 'task-status', { id: task.id, status: task.status });

  const chunkHandler = (text) => {
    sendSSE(res, 'task-progress', { id: task.id, chunk: text });
  };
  tm.taskEmitter.on(`task:${task.id}:chunk`, chunkHandler);

  // Forward mesh dialogue events (ensemble, consensus real-time conversation)
  let dialogueHandler;
  const meshBusRef = ctx.meshBus;
  if (meshBusRef) {
    dialogueHandler = (event) => {
      const belongsToTask = event.taskId === task.id || event.payload?.parentTaskId === task.id;
      if (event.type === 'dialogue' && belongsToTask && !res.writableEnded) {
        sendSSE(res, 'task-dialogue', {
          id: task.id,
          taskId: event.taskId,
          operation: event.payload?.operation,
          phase: event.payload?.phase,
          agent: event.payload?.agent,
          role: event.payload?.role,
          text: event.payload?.text,
          extra: { ...event.payload, operation: undefined, phase: undefined, agent: undefined, role: undefined, text: undefined },
          timestamp: event.timestamp,
        });
      }
    };
    meshBusRef.on('event', dialogueHandler);
  }

  const heartbeat = setInterval(() => {
    if (!res.writableEnded) res.write(':heartbeat\n\n');
    else clearInterval(heartbeat);
  }, 30000);

  const cleanupStream = () => {
    clearInterval(heartbeat);
    tm.taskEmitter.off(`task:${task.id}:chunk`, chunkHandler);
    if (meshBusRef && dialogueHandler) meshBusRef.off('event', dialogueHandler);
  };

  const cleanupExecution = () => {
    clearTimeout(timeoutId);
    cleanupStream();
  };

  const controller = ensureTaskAbortController(task);
  let timeoutId;
  ctx.executeTask(task, (event) => {
    if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') {
      clearTimeout(timeoutId);
      if (!res.writableEnded && !res.destroyed) {
        sendSSE(res, 'task-status', { id: task.id, status: task.status });
        if (task.artifacts.length > 0) {
          sendSSE(res, 'task-artifacts', { id: task.id, artifacts: task.artifacts });
        }
        res.end();
      }
      cleanupExecution();
    }
  }, { signal: controller.signal });

  timeoutId = setTimeout(() => {
    if (!res.writableEnded) {
      abortTaskExecution(task, `Task timed out after ${ctx.taskTimeoutMs}ms`);
      tm.updateTask(task, {
        status: {
          state: 'failed',
          message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: tarefa excedeu ${ctx.taskTimeoutMs / 60000} minutos` }] },
        },
      });
      sendSSE(res, 'task-status', {
        id: task.id,
        status: { state: 'failed', message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: tarefa excedeu ${ctx.taskTimeoutMs / 60000} minutos` }] } },
      });
      cleanupExecution();
      res.end();
    }
  }, ctx.taskTimeoutMs);

  // A dropped SSE client must not cancel the model process or its timeout.
  // Detach only transport listeners; the durable task continues and can be
  // recovered through GET /tasks/:id or the dashboard timeline.
  res.on('close', cleanupStream);
}

// --- Batch handler ---

async function handleTaskBatch(req, res, ctx) {
  const body = await parseBody(req);
  const items = body.tasks;
  if (!Array.isArray(items) || items.length === 0) {
    return sendError(res, 400, 'tasks array is required');
  }
  if (items.length > 10) {
    return sendError(res, 400, 'batch max 10 tasks');
  }

  const { tm } = ctx;
  const active = tm.getActiveTasks().length;
  if (active + items.length > tm.maxConcurrent) {
    return sendError(res, 429, `Too many concurrent tasks (active ${active}, batch ${items.length}, max ${tm.maxConcurrent})`);
  }
  tm.evictOldTasks();

  const results = await Promise.all(items.map(item => {
    return new Promise((resolve) => {
      const message = item.message;
      if (!message || !message.parts || message.parts.length === 0) {
        return resolve({ error: 'message with parts is required' });
      }

      const task = tm.createTask(message, mergeRequestTaskMetadata(item));
      const controller = ensureTaskAbortController(task);
      let timeoutId;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutId);
        resolve(tm.taskToJSON(task));
      };

      ctx.executeTask(task, (event) => {
        if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') {
          finish();
        }
      }, { signal: controller.signal });

      timeoutId = setTimeout(() => {
        if (task.status.state === 'working') {
          abortTaskExecution(task, `Task timed out after ${ctx.taskTimeoutMs}ms`);
          tm.updateTask(task, {
            status: {
              state: 'failed',
              message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: tarefa excedeu ${ctx.taskTimeoutMs / 60000} minutos` }] },
            },
          });
        }
        finish();
      }, ctx.taskTimeoutMs);
    });
  }));

  sendJSON(res, { jsonrpc: '2.0', result: results });
}

// --- Push notifications (webhooks) ---

const pushSubscriptions = new Map(); // taskId -> { url, headers }

function setPushNotification(taskId, url, headers = {}) {
  pushSubscriptions.set(taskId, { url, headers });
}

function getPushNotification(taskId) {
  return pushSubscriptions.get(taskId) || null;
}

function deletePushNotification(taskId) {
  return pushSubscriptions.delete(taskId);
}

function firePushNotification(taskId, taskJSON) {
  const sub = pushSubscriptions.get(taskId);
  if (!sub) return;
  const state = taskJSON.status?.state;
  // Fire push for all terminal states + auth_required (caller needs to know)
  if (!TERMINAL_STATES.has(state) && state !== 'auth_required') return;

  const payload = JSON.stringify({ jsonrpc: '2.0', method: 'tasks/pushNotification', params: { taskId, task: taskJSON } });
  const target = new URL(sub.url);

  const mod = target.protocol === 'https:' ? https : http;
  const req = mod.request({
    hostname: target.hostname,
    port: target.port,
    path: target.pathname + target.search,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...sub.headers },
  }, () => {});
  req.on('error', (err) => console.error(`[push] Failed to notify ${sub.url}: ${err.message}`));
  req.write(payload);
  req.end();

  pushSubscriptions.delete(taskId); // one-shot
}

export { setPushNotification, getPushNotification, deletePushNotification };

// ============================================
// Factory
// ============================================

/**
 * Create and start an A2A HTTP server.
 *
 * @param {Object} config
 * @param {number} config.port
 * @param {string} [config.host] - Bind address (defaults to loopback)
 * @param {string} config.selfId
 * @param {string} config.model - Model name for /health
 * @param {boolean} config.useApi - API mode flag for /health
 * @param {string} [config.authToken] - A2A_AUTH_TOKEN (empty = no auth)
 * @param {number} [config.taskTimeoutMs] - Task timeout in ms
 * @param {Object} config.agentCard - Agent Card JSON
 * @param {Object} config.peers - { agentId: url }
 * @param {number} config.maxDepth - A2A_MESH_MAX_DEPTH
 * @param {Object} config.taskManager - from createTaskManager()
 * @param {Object} config.meshCaller - from createMeshCaller()
 * @param {Object} [config.meshStore] - MeshStore (nullable)
 * @param {Object} [config.meshBus] - MeshEventBus (nullable)
 * @param {Function} [config.teamExecutor] - executeA2ATeam (nullable)
 * @param {Object} [config.consensusExecutor] - consensus executor (nullable)
 * @param {Object} [config.ensembleExecutor] - code ensemble executor (nullable)
 * @param {Object} [config.debateExecutor] - debate executor (nullable)
 * @param {Object} [config.planExecutor] - plan executor (nullable)
 * @param {Function} config.executeTask - (task, onChunk) => void
 */
export function createA2AServer(config) {
  const {
    port, selfId, model, useApi,
    host = process.env.A2A_BIND_HOST || '127.0.0.1',
    authToken = '',
    taskTimeoutMs = 2700000, // 45 min — suporta debates e ensembles longos
    agentCard: _rawAgentCard,
    peers, maxDepth,
    taskManager: tm,
    meshCaller,
    meshStore = null,
    meshBus = null,
    peerDiscovery = null,
    teamExecutor = null,
    consensusExecutor = null,
    ensembleExecutor = null,
    debateExecutor = null,
    planExecutor = null,
    healthDetails = null,
    executeTask,
  } = config;

  // Build enriched agent card from user-provided config + defaults
  const agentCard = buildAgentCard(config);

  const ctx = { tm, executeTask, taskTimeoutMs, meshBus, authToken };
  const sandboxManager = createSandboxManager();

  // JSON-RPC 2.0 adapter
  const rpcAdapter = createRPCAdapter({
    tm, executeTask, taskTimeoutMs,
    meshCaller, meshStore, meshBus,
    teamExecutor, consensusExecutor, ensembleExecutor, debateExecutor, planExecutor,
    maxDepth, selfId, peers, authToken,
    push: { set: setPushNotification, get: getPushNotification, delete: deletePushNotification },
  });

  // Hook push notifications on task state changes
  const origUpdateTask = tm.updateTask.bind(tm);
  tm.updateTask = function(task, updates) {
    origUpdateTask(task, updates);
    const state = task.status?.state;
    if (TERMINAL_STATES.has(state) || state === 'auth_required') {
      firePushNotification(task.id, tm.taskToJSON(task));
    }
  };

  const server = http.createServer(async (req, res) => {
    const url = new URL(req.url, `http://localhost:${port}`);
    const method = req.method;

    if (!isLoopbackRequest(req) || !isAllowedLoopbackHost(req, port)) {
      return sendError(res, 403, 'Forbidden: A2A mesh accepts only loopback hosts');
    }

    if (method === 'OPTIONS') {
      if (!isAllowedBrowserOrigin(req, port)) {
        return sendError(res, 403, 'Forbidden origin');
      }
      const origin = String(req.headers.origin || '');
      res.writeHead(204, {
        ...(origin ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {}),
        'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type, Authorization, A2A-Token, A2A-Protocol-Version',
        [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
      });
      return res.end();
    }

    // Soft-check protocol version on incoming requests (warn only, never reject)
    checkVersionHeader(req);

    try {
      // Public endpoints
      if (url.pathname === '/.well-known/agent.json' && method === 'GET') {
        return sendJSON(res, agentCard);
      }
      if (url.pathname === '/health' && method === 'GET') {
        if (!isAllowedBrowserOrigin(req, port)) return sendError(res, 403, 'Forbidden origin');
        const origin = String(req.headers.origin || '');
        const details = typeof healthDetails === 'function' ? healthDetails() : (healthDetails || {});
        return sendJSON(res, {
          status: 'ok', model, mode: useApi ? 'api' : 'cli',
          protocolVersion: A2A_PROTOCOL_VERSION,
          tasks: tm.tasks.size,
          // Reaper telemetry: if totalReaped grows, something upstream is
          // failing to emit terminal states. lastReaped > 0 = active leak.
          reaper: typeof tm.getReaperStats === 'function' ? tm.getReaperStats() : null,
          mesh: meshBus ? meshBus.getStatus() : null,
          ...details,
        }, 200, origin ? { 'Access-Control-Allow-Origin': origin, Vary: 'Origin' } : {});
      }

      // Browser session bootstrap: the CLI opens a one-use URL containing the
      // already-known token. Only a matching token may create the HttpOnly
      // cookie; the redirect immediately removes it from the address bar.
      if ((url.pathname === '/ui' || url.pathname === '/sandbox') && method === 'GET' && url.searchParams.has('token')) {
        const presentedToken = url.searchParams.get('token') || '';
        if (!authToken || !safeTokenEquals(presentedToken, authToken)) {
          return sendError(res, 401, 'Unauthorized: invalid UI bootstrap token');
        }
        res.writeHead(303, {
          Location: url.pathname,
          'Set-Cookie': `A2A-Token=${encodeURIComponent(authToken)}; HttpOnly; SameSite=Strict; Path=/`,
          'Cache-Control': 'no-store, must-revalidate',
          'X-Frame-Options': 'DENY',
          'Content-Security-Policy': "frame-ancestors 'none'; base-uri 'none'",
          [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
        });
        return res.end();
      }

      // Auth guard
      if (!isAllowedBrowserOrigin(req, port)) {
        return sendError(res, 403, 'Forbidden origin');
      }
      if (!checkAuth(req, authToken, port)) {
        return sendError(res, 401, 'Unauthorized: invalid or missing token');
      }

      // JSON-RPC 2.0 endpoint
      if (url.pathname === '/rpc' && method === 'POST') {
        const chunks = [];
        let totalLen = 0;
        for await (const chunk of req) {
          totalLen += chunk.length;
          if (totalLen > MAX_BODY_SIZE) {
            return sendJSON(res, { jsonrpc: '2.0', error: { code: -32600, message: 'Request body too large' }, id: null });
          }
          chunks.push(chunk);
        }
        const rawBody = Buffer.concat(chunks).toString();
        const rpcResult = await rpcAdapter.handle(rawBody);
        if (rpcResult === null) {
          // All requests were notifications — no response per JSON-RPC 2.0 spec
          res.writeHead(204, { [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION });
          return res.end();
        }
        return sendJSON(res, rpcResult);
      }

      // Task endpoints
      if (url.pathname === '/tasks/batch' && method === 'POST') {
        return await handleTaskBatch(req, res, ctx);
      }
      if (url.pathname === '/tasks/send' && method === 'POST') {
        return await handleTaskSend(req, res, ctx);
      }
      if (url.pathname === '/tasks/sendAsync' && method === 'POST') {
        return await handleTaskSendAsync(req, res, ctx);
      }
      if (url.pathname === '/tasks/sendSubscribe' && method === 'POST') {
        return await handleTaskSendSubscribe(req, res, ctx);
      }

      const taskIdMatch = url.pathname.match(/^\/tasks\/([a-zA-Z0-9_-]+)$/);
      if (taskIdMatch && method === 'GET') {
        const task = tm.tasks.get(taskIdMatch[1]);
        if (!task) return sendError(res, 404, `Task ${taskIdMatch[1]} not found`);
        return sendJSON(res, { jsonrpc: '2.0', result: tm.taskToJSON(task) });
      }

      const cancelMatch = url.pathname.match(/^\/tasks\/([a-zA-Z0-9_-]+)\/cancel$/);
      if (cancelMatch && method === 'POST') {
        const task = tm.tasks.get(cancelMatch[1]);
        if (!task) return sendError(res, 404, `Task ${cancelMatch[1]} not found`);
        if (TERMINAL_STATES.has(task.status.state)) {
          return sendError(res, 400, `Cannot cancel task in '${task.status.state}' state`);
        }
        const partial = recoverPartialArtifacts(meshStore, task.id);
        abortTaskExecution(task, 'Task cancelled by user');
        tm.updateTask(task, {
          status: {
            state: 'canceled',
            message: { role: 'agent', parts: [{
              type: 'text',
              text: `Task canceled by user.${partial.length ? ' Saída parcial preservada em partial-output.md.' : ''}`,
            }] },
          },
          artifacts: [...task.artifacts, ...partial],
        });
        return sendJSON(res, { jsonrpc: '2.0', result: tm.taskToJSON(task) });
      }

      if (url.pathname === '/tasks' && method === 'GET') {
        return sendJSON(res, { jsonrpc: '2.0', result: [...tm.tasks.values()].map(tm.taskToJSON) });
      }

      // Push notification endpoints
      if (url.pathname === '/tasks/pushNotification/set' && method === 'POST') {
        const body = await parseBody(req);
        if (!body.taskId || !body.url) return sendError(res, 400, 'taskId and url are required');
        if (!tm.tasks.has(body.taskId)) return sendError(res, 404, `Task ${body.taskId} not found`);
        setPushNotification(body.taskId, body.url, body.headers || {});
        return sendJSON(res, { jsonrpc: '2.0', result: { taskId: body.taskId, url: body.url } });
      }
      if (url.pathname === '/tasks/pushNotification/get' && method === 'POST') {
        const body = await parseBody(req);
        if (!body.taskId) return sendError(res, 400, 'taskId is required');
        const sub = getPushNotification(body.taskId);
        return sendJSON(res, { jsonrpc: '2.0', result: sub || { taskId: body.taskId, subscribed: false } });
      }
      if (url.pathname === '/tasks/pushNotification/delete' && method === 'POST') {
        const body = await parseBody(req);
        if (!body.taskId) return sendError(res, 400, 'taskId is required');
        deletePushNotification(body.taskId);
        return sendJSON(res, { jsonrpc: '2.0', result: { taskId: body.taskId, deleted: true } });
      }

      // Mesh observability endpoints
      if (url.pathname === '/mesh/events' && method === 'GET') {
        if (!meshBus) return sendError(res, 503, 'Mesh not available');
        return meshBus.handleSSE(req, res);
      }

      // Accept prefixed task ids too (call-*, consensus-*, debate-*, ensemble-*, direct-*)
      const traceMatch = url.pathname.match(/^\/mesh\/trace\/([a-zA-Z0-9_-]+)$/);
      if (traceMatch && method === 'GET') {
        if (!meshStore) return sendError(res, 503, 'Mesh not available');
        const trace = meshStore.getTrace(traceMatch[1]);
        if (!trace) return sendError(res, 404, 'Task not found in mesh');
        return sendJSON(res, trace);
      }

      if (url.pathname === '/mesh/timeline' && method === 'GET') {
        if (!meshStore) return sendError(res, 503, 'Mesh not available');
        const limit = parseInt(url.searchParams.get('limit') || '100');
        const since = url.searchParams.get('since');
        const svr = url.searchParams.get('server');
        const taskId = url.searchParams.get('taskId');
        const eventType = url.searchParams.get('eventType');
        const afterId = url.searchParams.get('afterId');
        const order = url.searchParams.get('order') === 'asc' ? 'asc' : undefined;
        return sendJSON(res, meshStore.getTimeline({
          limit: Math.min(2000, Math.max(1, limit || 100)),
          since, server: svr, taskId, eventType, afterId, order,
        }));
      }

      if (url.pathname === '/mesh/stats' && method === 'GET') {
        if (!meshStore) return sendError(res, 503, 'Mesh not available');
        return sendJSON(res, meshStore.getStats());
      }

      if (url.pathname === '/mesh/tasks' && method === 'GET') {
        if (!meshStore) return sendError(res, 503, 'Mesh not available');
        const state = url.searchParams.get('state');
        const origin = url.searchParams.get('origin');
        const limit = parseInt(url.searchParams.get('limit') || '50');
        return sendJSON(res, meshStore.listTasks({ state, originServer: origin, limit }));
      }

      const meshTaskMatch = url.pathname.match(/^\/mesh\/tasks\/([a-zA-Z0-9_-]+)$/);
      if (meshTaskMatch && method === 'GET') {
        if (!meshStore) return sendError(res, 503, 'Mesh not available');
        const task = meshStore.getTask(meshTaskMatch[1]);
        if (!task) return sendError(res, 404, `Task ${meshTaskMatch[1]} not found in mesh`);
        return sendJSON(res, task);
      }

      if (url.pathname === '/mesh/peers' && method === 'GET') {
        if (!peerDiscovery) return sendJSON(res, { peers: {} });
        return sendJSON(res, { peers: peerDiscovery.getAllPeers() });
      }

      if (url.pathname === '/mesh/catalog' && method === 'GET') {
        return sendJSON(res, { agents: publicAgentCatalog() });
      }

      if (url.pathname === '/mesh/call' && method === 'POST') {
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await meshCaller.executeA2ACall({
          agent: body.agent,
          prompt: body.prompt,
          timeout_ms: body.timeout_ms,
        }, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/broadcast' && method === 'POST') {
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await meshCaller.executeA2ABroadcast({
          prompt: body.prompt,
          agents: body.agents,
          includeSelf: body.includeSelf,
          timeout_ms: body.timeout_ms,
        }, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/consensus' && method === 'POST') {
        if (!consensusExecutor) return sendError(res, 503, 'Consensus executor not available');
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await consensusExecutor.execute(body, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/debate' && method === 'POST') {
        if (!debateExecutor) return sendError(res, 503, 'Debate executor not available');
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await debateExecutor.execute(body, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/ensemble' && method === 'POST') {
        if (!ensembleExecutor) return sendError(res, 503, 'Code ensemble executor not available');
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await ensembleExecutor.execute(body, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/team' && method === 'POST') {
        if (!teamExecutor) return sendError(res, 503, 'Team executor not available');
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth), meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
          selfId, peers, meshBus, meshStore, authToken,
        };
        const result = await teamExecutor({
          name: body.name,
          steps: body.steps,
          context: body.context,
          accumulate: body.accumulate,
          includeSelf: body.includeSelf,
          timeout_ms: body.timeout_ms,
          thread_id: body.thread_id,
          threadId: body.threadId,
        }, mctx);
        return sendJSON(res, { result });
      }

      if (url.pathname === '/mesh/plan' && method === 'POST') {
        if (!planExecutor) return sendError(res, 503, 'Plan executor not available');
        const body = await parseBody(req);
        const mctx = {
          depth: clampMeshDepth(body.depth, maxDepth),
          meshChain: body.meshChain || [],
          taskId: body.taskId || `direct-${Date.now()}`,
          selfCallDepth: body.selfCallDepth || 0,
        };
        const result = await planExecutor.execute(body, mctx);
        return sendJSON(res, { result });
      }

      // --- Agent CLI Sandbox ---
      if (url.pathname === '/sandbox' && method === 'GET') {
        const sandboxPath = new URL('./mesh-sandbox.html', import.meta.url).pathname;
        try {
          const html = fs.readFileSync(sandboxPath, 'utf8');
          res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store, must-revalidate', 'Pragma': 'no-cache', 'Expires': '0', 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:* http://localhost:*; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'", [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION });
          return res.end(html);
        } catch (e) {
          return sendError(res, 500, `Sandbox UI not found: ${e.message}`);
        }
      }

      if (url.pathname === '/sandbox/sessions' && method === 'GET') {
        return sendJSON(res, { sessions: sandboxManager.listSessions() });
      }

      if (url.pathname === '/sandbox/sessions' && method === 'POST') {
        const body = await parseBody(req);
        const session = await sandboxManager.startSession({
          agent: body.agent,
          cols: body.cols,
          rows: body.rows,
          sessionCwd: body.cwd,
          restart: body.restart,
        });
        return sendJSON(res, { session }, 201);
      }

      const sandboxMatch = url.pathname.match(/^\/sandbox\/sessions\/([^/]+)(?:\/([^/]+))?$/);
      if (sandboxMatch) {
        const sessionId = decodeURIComponent(sandboxMatch[1]);
        const action = sandboxMatch[2] || '';

        if (!action && method === 'DELETE') {
          sandboxManager.kill(sessionId);
          return sendJSON(res, { ok: true });
        }

        if (action === 'events' && method === 'GET') {
          res.writeHead(200, {
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Cache-Control': 'no-cache, no-transform',
            'Connection': 'keep-alive',
            [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION,
          });
          res.write(': connected\n\n');
          const unsubscribe = sandboxManager.subscribe(sessionId, (event) => sendSSE(res, event.type, event));
          req.on('close', unsubscribe);
          return;
        }

        if (action === 'input' && method === 'POST') {
          const body = await parseBody(req);
          sandboxManager.write(sessionId, body.data || '');
          return sendJSON(res, { ok: true });
        }

        if (action === 'resize' && method === 'POST') {
          const body = await parseBody(req);
          sandboxManager.resize(sessionId, { cols: body.cols, rows: body.rows });
          return sendJSON(res, { ok: true });
        }
      }

      // --- Mesh Dashboard UI ---
      if (url.pathname === '/ui' && method === 'GET') {
        const uiPath = new URL('./mesh-ui.html', import.meta.url).pathname;
        try {
          const html = fs.readFileSync(uiPath, 'utf8');
          res.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store, must-revalidate', 'Pragma': 'no-cache', 'Expires': '0', 'X-Frame-Options': 'DENY', 'Content-Security-Policy': "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self' http://127.0.0.1:* http://localhost:*; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'", [A2A_VERSION_HEADER]: A2A_PROTOCOL_VERSION });
          return res.end(html);
        } catch (e) {
          return sendError(res, 500, `UI not found: ${e.message}`);
        }
      }

      sendError(res, 404, 'Not found');
    } catch (err) {
      console.error('Request error:', err);
      sendError(res, 500, err.message);
    }
  });

  // Crash protection is process-global. Install it once in production only;
  // test runners intercept process.exit and would otherwise recurse forever.
  const crashProtectionKey = Symbol.for('a2a.crashProtectionInstalled');
  const isTestRuntime = process.env.NODE_ENV === 'test' || Boolean(process.env.VITEST);
  if (!isTestRuntime && !process[crashProtectionKey]) {
    process[crashProtectionKey] = true;
    process.on('uncaughtException', (err) => {
      console.error('[CRASH PROTECTION] uncaughtException:', err.message);
      console.error(err.stack);
      setImmediate(() => process.exit(1));
    });
    process.on('unhandledRejection', (reason) => {
      console.error('[CRASH PROTECTION] unhandledRejection:', reason);
      setImmediate(() => process.exit(1));
    });
  }

  // Graceful shutdown
  let _shuttingDown = false;
  const shutdown = () => {
    if (_shuttingDown) return;
    _shuttingDown = true;
    console.log('Encerrando servidor...');
    try {
      for (const task of tm.tasks.values()) {
        if (task.process) {
          try {
            abortTaskExecution(task, 'Server shutting down');
          } catch (err) {
            if (process.env.A2A_DEBUG === 'true') {
              console.warn('[shutdown] Failed to kill task process', {
                taskId: task.id,
                pid: task.process?.pid,
                error: err instanceof Error ? err.message : String(err),
              });
            }
          }
        }
      }
      if (peerDiscovery) {
        try {
          peerDiscovery.stop();
        } catch (err) {
          if (process.env.A2A_DEBUG === 'true') {
            console.warn('[shutdown] Failed to stop peer discovery', {
              error: err instanceof Error ? err.message : String(err),
            });
          }
        }
      }
      if (meshBus) {
        try {
          meshBus.disconnect();
        } catch (err) {
          if (process.env.A2A_DEBUG === 'true') {
            console.warn('[shutdown] Failed to disconnect mesh bus', {
              error: err instanceof Error ? err.message : String(err),
            });
          }
        }
      }
      if (meshStore) {
        try {
          meshStore.close();
        } catch (err) {
          if (process.env.A2A_DEBUG === 'true') {
            console.warn('[shutdown] Failed to close mesh store', {
              error: err instanceof Error ? err.message : String(err),
            });
          }
        }
      }
      try {
        sandboxManager.closeAll();
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[shutdown] Failed to close sandbox sessions', {
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
      server.close();
      // Keep the parent alive for the grace window. The forced timer is
      // intentionally referenced; otherwise process.exit would strand
      // detached CLI descendants that ignored SIGTERM.
      scheduleForcedTaskTermination(tm.tasks.values());
    } catch (e) {
      console.error('Error during shutdown:', e.message);
      process.exit(1);
    }
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);

  // Start
  server.listen(port, host, () => {
    console.log(`A2A ${selfId.charAt(0).toUpperCase() + selfId.slice(1)} Server rodando em http://${host}:${port}`);
    console.log(`Agent Card: http://localhost:${port}/.well-known/agent.json`);
    const modeLabel = useApi ? (config.cliModel ? `api (fallback: cli/${config.cliModel})` : 'api') : 'cli';
    console.log(`Modelo: ${model} | Modo: ${modeLabel}`);

    if (meshBus) {
      setTimeout(() => {
        meshBus.connectToPeers();
        console.log('[mesh] Connecting to peers:', Object.keys(peers).join(', '));
      }, 2000);
    }

    if (peerDiscovery) {
      peerDiscovery.start().then(() => {
        const online = Object.keys(peerDiscovery.getOnlinePeers());
        console.log('[discovery] Initial health check complete. Online:', online.length ? online.join(', ') : 'none');
      }).catch(() => {});
    }
  });

  return server;
}
