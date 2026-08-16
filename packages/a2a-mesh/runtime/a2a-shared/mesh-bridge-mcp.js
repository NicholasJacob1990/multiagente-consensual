#!/usr/bin/env node

/**
 * A2A Mesh Bridge MCP
 *
 * Servidor MCP dedicado que expõe as tools de orquestração mesh:
 * a2a_call, a2a_broadcast, a2a_team
 *
 * Independente de qualquer agente. Chama os peers diretamente via HTTP.
 * Configurado nas CLIs elegíveis (Claude Code, Codex CLI e Cursor CLI).
 */

import { Server } from '@modelcontextprotocol/sdk/server/index.js';
import { StdioServerTransport } from '@modelcontextprotocol/sdk/server/stdio.js';
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from '@modelcontextprotocol/sdk/types.js';
import http from 'http';
import { loadPeerRegistry } from './peer-registry.js';
import { checkAgentHealth, ensureAgentOnline } from './agent-supervisor.js';
import { loadA2AAuthToken } from './auth-token.js';
import { AGENT_IDS } from './agent-catalog.js';
import {
  broadcastBridgeParams,
  callBridgeParams,
  consensusBridgeParams,
  debateBridgeParams,
  ensembleBridgeParams,
  planBridgeParams,
  teamBridgeParams,
} from './bridge-params.js';
import { createStableRequestIdFactory } from './request-id.js';
import { clampMcpWaitMs, MAX_MCP_WAIT_MS } from './mcp-policy.js';

// ============================================
// CONFIG
// ============================================

function getAllPeers() {
  return loadPeerRegistry({ includeSelf: true });
}

const INITIAL_PEERS = getAllPeers();
const A2A_AUTH_TOKEN = loadA2AAuthToken();

function bridgeContext() {
  const parsedDepth = Number.parseInt(process.env.A2A_MESH_BRIDGE_REMAINING_DEPTH || '7', 10);
  let meshChain = [];
  try {
    const parsed = JSON.parse(process.env.A2A_MESH_BRIDGE_CHAIN || '[]');
    if (Array.isArray(parsed)) meshChain = parsed.filter((item) => typeof item === 'string' && item);
  } catch {
    meshChain = [];
  }
  return {
    depth: Number.isFinite(parsedDepth) ? Math.max(0, parsedDepth) : 7,
    meshChain,
    calledBy: process.env.A2A_MESH_BRIDGE_CALLER || 'mcp-bridge',
  };
}

// ============================================
// HTTP CLIENT
// ============================================

function peerRequest(baseUrl, path, body, { method = 'POST', timeout = 30_000 } = {}) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl);
    const headers = { 'Content-Type': 'application/json' };
    if (A2A_AUTH_TOKEN) headers.Authorization = `Bearer ${A2A_AUTH_TOKEN}`;
    const req = http.request({
      hostname: url.hostname, port: url.port, path: url.pathname + url.search,
      method,
      headers,
      timeout,
    }, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString();
        let parsed;
        try { parsed = JSON.parse(raw); }
        catch { parsed = { raw }; }
        if (res.statusCode < 200 || res.statusCode >= 300) {
          const detail = parsed?.error?.message || parsed?.error || raw || res.statusMessage;
          reject(new Error(`A2A peer ${url.origin} returned HTTP ${res.statusCode}: ${String(detail).slice(0, 500)}`));
          return;
        }
        resolve(parsed);
      });
    });
    req.on('error', reject);
    req.on('timeout', () => { req.destroy(); reject(new Error('Timeout')); });
    if (body !== undefined) req.write(JSON.stringify(body));
    req.end();
  });
}

async function checkPeer(agentId, autoStart = false) {
  const ALL_PEERS = getAllPeers();
  const url = ALL_PEERS[agentId];
  try {
    const health = autoStart
      ? await ensureAgentOnline(agentId, url)
      : await checkAgentHealth(url);
    if (!health) return { agent: agentId, status: 'offline' };
    return { agent: agentId, status: 'online', model: health.model, mode: health.mode };
  } catch (error) {
    return { agent: agentId, status: 'offline', error: error.message };
  }
}

function withDeadline(promise, deadline, label) {
  const remaining = Math.max(1, deadline - Date.now());
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => reject(new Error(`${label} deadline exhausted`)), remaining);
    timer.unref?.();
    Promise.resolve(promise).then(
      (value) => { clearTimeout(timer); resolve(value); },
      (error) => { clearTimeout(timer); reject(error); },
    );
  });
}

async function getCoordinatorInfo({ deadline = Date.now() + 60_000 } = {}) {
  const peers = getAllPeers();
  const errors = [];
  for (const agentId of AGENT_IDS) {
    const url = peers[agentId];
    if (!url) continue;
    if (Date.now() >= deadline) break;
    try {
      await withDeadline(ensureAgentOnline(agentId, url), deadline, 'Coordinator discovery');
      return { agentId, url };
    } catch (error) {
      errors.push(`${agentId}: ${error.message}`);
    }
  }
  throw new Error(`No A2A coordinator is available (${errors.join('; ')})`);
}

const taskCoordinators = new Map();
const TERMINAL_TASK_STATES = new Set(['completed', 'failed', 'canceled', 'rejected']);
const MAX_COORDINATOR_CACHE = 1000;
const parsedRetryWindow = Number.parseInt(process.env.A2A_MESH_REQUEST_RETRY_WINDOW_MS || '60000', 10);
const REQUEST_ID_RETRY_WINDOW_MS = Math.min(
  10 * 60 * 1000,
  Math.max(1_000, Number.isFinite(parsedRetryWindow) ? parsedRetryWindow : 60_000),
);
const defaultRequestId = createStableRequestIdFactory({
  scope: process.env.A2A_MESH_BRIDGE_SESSION_ID || undefined,
  retryWindowMs: REQUEST_ID_RETRY_WINDOW_MS,
});

function rememberCoordinator(taskId, coordinator) {
  if (!taskId || !coordinator?.agentId || !coordinator?.url) return;
  if (taskCoordinators.has(taskId)) taskCoordinators.delete(taskId);
  taskCoordinators.set(taskId, coordinator);
  while (taskCoordinators.size > MAX_COORDINATOR_CACHE) {
    taskCoordinators.delete(taskCoordinators.keys().next().value);
  }
}

function remainingTimeout(deadline, cap = 5_000) {
  return Math.max(1, Math.min(cap, deadline - Date.now()));
}

async function rpcRequest(baseUrl, method, params = {}, timeout = 30_000) {
  const response = await peerRequest(baseUrl, '/rpc', {
    jsonrpc: '2.0',
    id: `${method}-${Date.now()}-${Math.random().toString(16).slice(2)}`,
    method,
    params,
  }, { timeout });
  if (response?.error) throw new Error(response.error.message || JSON.stringify(response.error));
  return response?.result;
}

async function submitAsyncMeshTask(method, params, { deadline = Date.now() + MAX_MCP_WAIT_MS } = {}) {
  const coordinator = await getCoordinatorInfo({ deadline });
  const result = await rpcRequest(
    coordinator.url,
    `${method}Async`,
    params,
    remainingTimeout(deadline, 30_000),
  );
  if (!result?.id) throw new Error(`Coordinator did not return a task id for ${method}`);
  const effectiveAgent = result.coordinator || coordinator.agentId;
  const effective = {
    agentId: effectiveAgent,
    url: getAllPeers()[effectiveAgent] || coordinator.url,
  };
  rememberCoordinator(result.id, effective);
  return { ...result, coordinator: effectiveAgent, method };
}

async function taskFromCoordinator(taskId, coordinator, timeout = 5_000) {
  const task = await rpcRequest(coordinator.url, 'tasks/get', { id: taskId }, timeout);
  rememberCoordinator(taskId, coordinator);
  return { task, coordinator: coordinator.agentId };
}

async function findTask(taskId, preferredAgent, { deadline = Date.now() + 30_000 } = {}) {
  const peers = getAllPeers();
  const candidates = [];
  const cached = taskCoordinators.get(taskId);
  if (cached) candidates.push(cached);
  if (preferredAgent && peers[preferredAgent]) candidates.push({ agentId: preferredAgent, url: peers[preferredAgent] });
  for (const agentId of AGENT_IDS) {
    if (peers[agentId]) candidates.push({ agentId, url: peers[agentId] });
  }

  const unique = [...new Map(candidates.map((item) => [item.agentId, item])).values()];
  const errors = [];
  if (Date.now() >= deadline) throw new Error(`Task ${taskId} lookup deadline exhausted`);
  try {
    return await Promise.any(unique.map((coordinator) =>
      taskFromCoordinator(taskId, coordinator, remainingTimeout(deadline))
        .catch((error) => {
          errors.push(`${coordinator.agentId}: ${error.message}`);
          throw error;
        }),
    ));
  } catch {
    // Fall through to the shared ledger when no coordinator owns the task.
  }

  // Every peer shares the SQLite ledger. If the original coordinator is
  // offline after a restart/crash, recover the last durable state from any
  // surviving peer instead of reporting a false "not found".
  const ledgerCandidates = AGENT_IDS.filter((agentId) => peers[agentId]);
  if (Date.now() < deadline) try {
    return await Promise.any(ledgerCandidates.map(async (agentId) => {
      const url = peers[agentId];
      try {
        const stored = await peerRequest(
        url,
        `/mesh/tasks/${encodeURIComponent(taskId)}`,
        undefined,
          { method: 'GET', timeout: remainingTimeout(deadline) },
        );
        const message = stored.outputText
          ? { role: 'agent', parts: [{ type: 'text', text: stored.outputText }] }
          : undefined;
        const origin = stored.originServer || agentId;
        const originUrl = peers[origin] || url;
        rememberCoordinator(taskId, { agentId: origin, url: originUrl });
        return {
          task: {
            ...stored,
            status: { state: stored.state, ...(message ? { message } : {}) },
          },
          coordinator: origin,
        };
      } catch (error) {
        errors.push(`${agentId}/ledger: ${error.message}`);
        throw error;
      }
    }));
  } catch {
    // A complete miss is reported below with all collected diagnostics.
  }
  throw new Error(`Task ${taskId} not found (${errors.join('; ')})`);
}

async function waitForTask(taskId, { waitMs = 60_000, coordinator } = {}) {
  const boundedWaitMs = clampMcpWaitMs(waitMs);
  const deadline = Date.now() + boundedWaitMs;
  let current = await findTask(taskId, coordinator, { deadline });
  while (!TERMINAL_TASK_STATES.has(current.task?.status?.state) && Date.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, Math.min(2_000, Math.max(0, deadline - Date.now()))));
    if (Date.now() >= deadline) break;
    current = await findTask(taskId, current.coordinator, { deadline });
  }
  return current;
}

function taskOutputText(task) {
  return task?.status?.message?.parts?.map((part) => part.text).filter(Boolean).join('\n') || '';
}

function taskReceiptText({ task, coordinator, method, reused = false }) {
  const state = task?.status?.state || 'submitted';
  const lines = [
    `**A2A task ${task.id}**`,
    `**Operation**: ${method || task.metadata?.type || 'mesh'}`,
    `**Coordinator**: ${coordinator || task.originServer || 'unknown'}`,
    `**Status**: ${state}${reused ? ' (idempotent reuse)' : ''}`,
  ];
  const output = taskOutputText(task);
  if (output) lines.push('', output);
  if (!TERMINAL_TASK_STATES.has(state)) {
    lines.push('', 'The run continues independently. Use `a2a_task_wait` or `a2a_task_status`; live dialogue is visible in the A2A panel.');
  }
  if (Array.isArray(task.artifacts) && task.artifacts.length > 0) {
    lines.push('', `**Artifacts**: ${task.artifacts.map((artifact) => artifact.name || 'artifact').join(', ')}`);
  }
  return lines.join('\n');
}

async function submitTool(method, params, args = {}) {
  const deadline = Date.now() + MAX_MCP_WAIT_MS;
  const requestId = String(args.request_id || defaultRequestId(method, params));
  const submitted = await submitAsyncMeshTask(method, {
    ...params,
    request_id: requestId,
    timeout_ms: args.timeout_ms,
    operation_timeout_ms: args.operation_timeout_ms,
  }, { deadline });
  let located = {
    task: {
      id: submitted.id,
      status: submitted.status,
      metadata: { type: method },
      artifacts: [],
    },
    coordinator: submitted.coordinator,
  };
  if (args.wait_for_completion === true) {
    try {
      located = await waitForTask(submitted.id, {
        waitMs: Math.min(args.wait_ms || 60_000, Math.max(0, deadline - Date.now())),
        coordinator: submitted.coordinator,
      });
    } catch (error) {
      located.warning = `A espera falhou, mas a tarefa continua durável: ${error.message}`;
    }
  }
  const receipt = taskReceiptText({
    ...located,
    method,
    reused: submitted.reused === true,
  });
  return {
    content: [{
      type: 'text',
      text: located.warning ? `${receipt}\n\n**Aviso**: ${located.warning}` : receipt,
    }],
  };
}

// ============================================
// MCP SERVER
// ============================================

const mcpServer = new Server(
  { name: 'a2a-mesh', version: '1.2.0' },
  { capabilities: { tools: {} } }
);

// ============================================
// TOOLS
// ============================================

const peerNames = Object.keys(INITIAL_PEERS).join(', ');
const asyncControlProperties = {
  timeout_ms: {
    type: 'number',
    description: 'Maximum time for each individual model call in milliseconds (default and cap: 30 minutes unless explicitly configured).',
  },
  operation_timeout_ms: {
    type: 'number',
    description: 'Maximum time for the complete orchestration in milliseconds (default: 24 hours; maximum: 5 days).',
  },
  request_id: {
    type: 'string',
    description: 'Optional idempotency key. Reusing it returns the existing run instead of duplicating work.',
  },
  wait_for_completion: {
    type: 'boolean',
    description: 'Wait briefly for completion. Default false: returns a durable task receipt immediately.',
  },
  wait_ms: {
    type: 'number',
    description: 'Maximum time to wait in this MCP call (max 240000 ms). The task continues after this wait.',
  },
};

mcpServer.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'a2a_call',
      description: `Submit a durable call to one AI agent. Returns a task receipt immediately by default; use a2a_task_wait/status for long runs. Available: ${peerNames}.`,
      inputSchema: {
        type: 'object',
        properties: {
          agent: { type: 'string', description: `Agent to call: ${peerNames}`, enum: Object.keys(INITIAL_PEERS) },
          prompt: { type: 'string', description: 'Task or question for the agent' },
          ...asyncControlProperties,
        },
        required: ['agent', 'prompt'],
      },
    },
    {
      name: 'a2a_broadcast',
      description: `Submit a durable parallel broadcast. Default: all (${peerNames}). Progress streams to the A2A panel.`,
      inputSchema: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'Task or question for the agents' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs (default: all). Options: ${peerNames}` },
          ...asyncControlProperties,
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_team',
      description: `Submit a durable multi-step workflow. Steps run sequentially; agents within each step can run in parallel or sequence. Use {{previous}} to reference prior outputs.`,
      inputSchema: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Workflow name (for tracing)' },
          steps: {
            type: 'array',
            description: 'Pipeline steps',
            items: {
              type: 'object',
              properties: {
                mode: { type: 'string', enum: ['parallel', 'sequential'], description: 'How agents execute within this step' },
                agents: { type: 'array', items: { type: 'string' }, description: `Agents for this step: ${peerNames}` },
                prompt: { type: 'string', description: 'Prompt. Use {{previous}} for accumulated context from prior steps, {{step_N}} for a specific step.' },
              },
              required: ['mode', 'agents', 'prompt'],
            },
          },
          context: { type: 'string', description: 'Initial shared context (optional)' },
          ...asyncControlProperties,
        },
        required: ['steps'],
      },
    },
    {
      name: 'a2a_consensus',
      description: `Submit durable multi-agent consensus with an independent judge. Returns a task receipt; live responses stream to the panel. Available: ${peerNames}.`,
      inputSchema: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'Question or task to get consensus on' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs to consult (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Agent to act as judge/synthesizer (default: claude). Options: ${peerNames}` },
          quorum: { type: 'number', description: 'Minimum valid independent responses. Default: strict majority of participants.' },
          ...asyncControlProperties,
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_debate',
      description: `Submit a durable adversarial debate. Agents argue and a judge synthesizes a verdict. Returns immediately with a task id so long debates survive MCP host timeouts.`,
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Debate topic or question' },
          rounds: { type: 'number', description: 'Number of debate rounds (default: 4, recommended max: 18, exceptional max: 36)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Debaters (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Judge agent (default: claude). Options: ${peerNames}` },
          ...asyncControlProperties,
        },
        required: ['topic'],
      },
    },
    {
      name: 'a2a_ensemble',
      description: `Submit a durable NxN code ensemble: write, cross-review, revise and synthesize. Progress and model output stream to the panel.`,
      inputSchema: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'Coding task description' },
          language: { type: 'string', description: 'Programming language (default: python)' },
          rounds: { type: 'number', description: 'Review+revise cycles (default: 1, recommended max: 6, exceptional max: 12)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Exact participant set (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Judge agent (default: claude). Options: ${peerNames}` },
          ...asyncControlProperties,
        },
        required: ['task'],
      },
    },
    {
      name: 'a2a_plan',
      description: 'Submit a durable author-review planning loop with persisted versions and live review streaming.',
      inputSchema: {
        type: 'object',
        properties: {
          description: { type: 'string', description: 'Plan objective or specification.' },
          author: { type: 'string', description: `Author agent (default: claude). Options: ${peerNames}` },
          reviewer: { type: 'string', description: `Reviewer agent (default: codex). Options: ${peerNames}` },
          rounds: { type: 'number', description: 'Maximum author-review rounds (default: 3; max: 36).' },
          lenses: { type: 'array', items: { type: 'string' }, description: 'Optional review lenses such as engineer, security, ops, product or performance.' },
          ...asyncControlProperties,
        },
        required: ['description'],
      },
    },
    {
      name: 'a2a_task_status',
      description: 'Get the durable status, full final output and preserved partial artifacts of an A2A task.',
      inputSchema: {
        type: 'object',
        properties: {
          task_id: { type: 'string', description: 'Task id returned by any A2A orchestration tool.' },
          coordinator: { type: 'string', enum: Object.keys(INITIAL_PEERS), description: 'Optional coordinator hint.' },
        },
        required: ['task_id'],
      },
    },
    {
      name: 'a2a_task_wait',
      description: 'Wait up to 240 seconds for an A2A task, then return its current or terminal state. Safe to call repeatedly.',
      inputSchema: {
        type: 'object',
        properties: {
          task_id: { type: 'string', description: 'Task id returned by any A2A orchestration tool.' },
          wait_ms: { type: 'number', description: 'This wait only, maximum 240000 ms (default 60000).' },
          coordinator: { type: 'string', enum: Object.keys(INITIAL_PEERS), description: 'Optional coordinator hint.' },
        },
        required: ['task_id'],
      },
    },
    {
      name: 'a2a_task_cancel',
      description: 'Cancel an active A2A task and its current model call. Preserved partial output remains auditable.',
      inputSchema: {
        type: 'object',
        properties: {
          task_id: { type: 'string', description: 'Task id returned by any A2A orchestration tool.' },
          coordinator: { type: 'string', enum: Object.keys(INITIAL_PEERS), description: 'Optional coordinator hint.' },
        },
        required: ['task_id'],
      },
    },
    {
      name: 'a2a_status',
      description: 'Check which A2A agents are online and their models. Local agents are started automatically by default.',
      inputSchema: {
        type: 'object',
        properties: {
          auto_start: { type: 'boolean', description: 'Start offline local agents before checking (default: true)' },
        },
      },
    },
  ],
}));

// ============================================
// TOOL HANDLERS
// ============================================

mcpServer.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case 'a2a_call':
        return await handleCall(args);
      case 'a2a_broadcast':
        return await handleBroadcast(args);
      case 'a2a_team':
        return await handleTeam(args);
      case 'a2a_consensus':
        return await handleConsensus(args);
      case 'a2a_debate':
        return await handleDebate(args);
      case 'a2a_ensemble':
        return await handleEnsemble(args);
      case 'a2a_plan':
        return await handlePlan(args);
      case 'a2a_task_status':
        return await handleTaskStatus(args);
      case 'a2a_task_wait':
        return await handleTaskWait(args);
      case 'a2a_task_cancel':
        return await handleTaskCancel(args);
      case 'a2a_status':
        return await handleStatus(args);
      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    return {
      content: [{ type: 'text', text: `Error [${name}]: ${error.message}` }],
      isError: true,
    };
  }
});

async function handleCall(args) {
  return submitTool('mesh/call', callBridgeParams(args, bridgeContext()), args);
}

async function handleBroadcast(args) {
  return submitTool('mesh/broadcast', broadcastBridgeParams(args, bridgeContext()), args);
}

async function handleTeam(args) {
  return submitTool('mesh/team', teamBridgeParams(args, bridgeContext()), args);
}

async function handleConsensus(args) {
  const context = bridgeContext();
  return submitTool('mesh/consensus', consensusBridgeParams(args, context), args);
}

async function handleDebate(args) {
  return submitTool('mesh/debate', debateBridgeParams(args, bridgeContext()), args);
}

async function handleEnsemble(args) {
  const context = bridgeContext();
  return submitTool('mesh/ensemble', ensembleBridgeParams(args, context), args);
}

async function handlePlan(args) {
  return submitTool('mesh/plan', planBridgeParams(args, bridgeContext()), args);
}

async function handleTaskStatus(args) {
  const located = await findTask(args.task_id, args.coordinator);
  return { content: [{ type: 'text', text: taskReceiptText({ ...located }) }] };
}

async function handleTaskWait(args) {
  const located = await waitForTask(args.task_id, {
    waitMs: args.wait_ms || 60_000,
    coordinator: args.coordinator,
  });
  return { content: [{ type: 'text', text: taskReceiptText({ ...located }) }] };
}

async function handleTaskCancel(args) {
  const located = await findTask(args.task_id, args.coordinator);
  const coordinator = taskCoordinators.get(args.task_id) || {
    agentId: located.coordinator,
    url: getAllPeers()[located.coordinator],
  };
  if (!coordinator.url) {
    throw new Error(`Task ${args.task_id} is durable, but coordinator ${coordinator.agentId || 'unknown'} is offline; cancellation could not be delivered.`);
  }
  const task = await rpcRequest(coordinator.url, 'tasks/cancel', { id: args.task_id }, 30_000);
  return { content: [{ type: 'text', text: taskReceiptText({ task, coordinator: coordinator.agentId }) }] };
}

async function handleStatus(args = {}) {
  const ALL_PEERS = getAllPeers();
  const autoStart = args.auto_start !== false;
  const results = await Promise.all(Object.keys(ALL_PEERS).map(id => checkPeer(id, autoStart)));
  const lines = results.map(r =>
    `- **${r.agent}**: ${r.status}${r.model ? ` (${r.model}${r.mode ? ', ' + r.mode : ''})` : ''}${r.error ? ` — ${r.error}` : ''}`
  );
  return { content: [{ type: 'text', text: `**A2A Mesh Status:**\n\n${lines.join('\n')}` }] };
}

// ============================================
// MAIN
// ============================================

async function main() {
  const transport = new StdioServerTransport();
  await mcpServer.connect(transport);
  console.error(`A2A Mesh Bridge MCP started — peers: ${peerNames}`);
}

main().catch((error) => {
  console.error('Fatal error:', error);
  process.exit(1);
});
