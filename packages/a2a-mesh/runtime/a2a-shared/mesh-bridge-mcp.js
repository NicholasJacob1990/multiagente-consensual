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
import { consensusBridgeParams, ensembleBridgeParams } from './bridge-params.js';

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

function peerRequest(baseUrl, path, body) {
  return new Promise((resolve, reject) => {
    const url = new URL(path, baseUrl);
    const headers = { 'Content-Type': 'application/json' };
    if (A2A_AUTH_TOKEN) headers.Authorization = `Bearer ${A2A_AUTH_TOKEN}`;
    const req = http.request({
      hostname: url.hostname, port: url.port, path: url.pathname,
      method: 'POST',
      headers,
      timeout: 2700000, // 45 min — debates e ensembles longos
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
    req.write(JSON.stringify(body));
    req.end();
  });
}

async function sendToAgent(agentId, prompt) {
  const context = bridgeContext();
  if (context.depth <= 0) return `Error: max mesh depth exceeded (chain: ${context.meshChain.join(' → ')})`;
  if (context.meshChain.includes(agentId)) {
    return `Error: mesh cycle refused (${[...context.meshChain, agentId].join(' → ')})`;
  }
  const ALL_PEERS = getAllPeers();
  const url = ALL_PEERS[agentId];
  if (!url) return `Unknown agent: ${agentId}. Available: ${Object.keys(ALL_PEERS).join(', ')}`;
  try {
    await ensureAgentOnline(agentId, url);
    const r = await peerRequest(url, '/tasks/send', {
      message: { role: 'user', parts: [{ type: 'text', text: prompt }] },
      metadata: {
        maxDepth: context.depth,
        meshChain: context.meshChain,
        calledBy: context.calledBy,
      },
    });
    const task = r.result || r;
    return task.status?.message?.parts?.map(p => p.text).join('\n') || 'No response';
  } catch (error) {
    return `Error (${agentId}): ${error.message}`;
  }
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

async function getCoordinator() {
  const peers = getAllPeers();
  const errors = [];
  for (const agentId of AGENT_IDS) {
    const url = peers[agentId];
    if (!url) continue;
    try {
      await ensureAgentOnline(agentId, url);
      return url;
    } catch (error) {
      errors.push(`${agentId}: ${error.message}`);
    }
  }
  throw new Error(`No A2A coordinator is available (${errors.join('; ')})`);
}

// ============================================
// MCP SERVER
// ============================================

const mcpServer = new Server(
  { name: 'a2a-mesh', version: '1.1.0' },
  { capabilities: { tools: {} } }
);

// ============================================
// TOOLS
// ============================================

const peerNames = Object.keys(INITIAL_PEERS).join(', ');

mcpServer.setRequestHandler(ListToolsRequestSchema, async () => ({
  tools: [
    {
      name: 'a2a_call',
      description: `Call one AI agent directly using its configured model. Available: ${peerNames}. Offline local agents are started automatically.`,
      inputSchema: {
        type: 'object',
        properties: {
          agent: { type: 'string', description: `Agent to call: ${peerNames}`, enum: Object.keys(INITIAL_PEERS) },
          prompt: { type: 'string', description: 'Task or question for the agent' },
        },
        required: ['agent', 'prompt'],
      },
    },
    {
      name: 'a2a_broadcast',
      description: `Send the same prompt to multiple agents in parallel. Default: all (${peerNames}). Returns all responses.`,
      inputSchema: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'Task or question for the agents' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs (default: all). Options: ${peerNames}` },
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_team',
      description: `Orchestrate a multi-step workflow. Steps run sequentially; agents within each step run in parallel or sequential mode. Use {{previous}} to reference prior step outputs.`,
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
        },
        required: ['steps'],
      },
    },
    {
      name: 'a2a_consensus',
      description: `Ask multiple agents the same question, then have a judge synthesize a consensus answer with confidence score. Available: ${peerNames}.`,
      inputSchema: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'Question or task to get consensus on' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs to consult (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Agent to act as judge/synthesizer (default: claude). Options: ${peerNames}` },
          quorum: { type: 'number', description: 'Minimum valid independent responses. Default: strict majority of participants.' },
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_debate',
      description: `Start an adversarial multi-agent debate. All agents (${peerNames}) argue and a judge synthesizes a verdict with scores. Great for exploring trade-offs.`,
      inputSchema: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Debate topic or question' },
          rounds: { type: 'number', description: 'Number of debate rounds (default: 4, recommended max: 18, exceptional max: 36)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Debaters (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Judge agent (default: claude). Options: ${peerNames}` },
        },
        required: ['topic'],
      },
    },
    {
      name: 'a2a_ensemble',
      description: `NxN code ensemble: all agents write code, cross-review each other, revise, then a judge synthesizes the best solution. Use for high-quality code generation.`,
      inputSchema: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'Coding task description' },
          language: { type: 'string', description: 'Programming language (default: python)' },
          rounds: { type: 'number', description: 'Review+revise cycles (default: 1, recommended max: 6, exceptional max: 12)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Exact participant set (default: all). Options: ${peerNames}` },
          judge: { type: 'string', description: `Judge agent (default: claude). Options: ${peerNames}` },
        },
        required: ['task'],
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
  const result = await sendToAgent(args.agent, args.prompt);
  return { content: [{ type: 'text', text: `**${args.agent}:**\n\n${result}` }] };
}

async function handleBroadcast(args) {
  const agents = args.agents || Object.keys(getAllPeers());
  const results = await Promise.allSettled(agents.map(id => sendToAgent(id, args.prompt)));
  const output = agents.map((id, i) => {
    const r = results[i];
    const text = r.status === 'fulfilled' ? r.value : `Error: ${r.reason?.message}`;
    return `### ${id}\n${text}`;
  }).join('\n\n---\n\n');
  return { content: [{ type: 'text', text: `**a2a_broadcast (${agents.length} agents):**\n\n${output}` }] };
}

async function handleTeam(args) {
  const steps = args.steps || [];
  const workflowName = args.name || 'workflow';
  const startTime = Date.now();
  const stepOutputs = [];
  let accumulated = args.context || '';

  for (let i = 0; i < steps.length; i++) {
    const step = steps[i];
    let prompt = step.prompt
      .replace(/\{\{previous\}\}/g, accumulated)
      .replace(/\{\{step_(\d+)\}\}/g, (_, n) => stepOutputs[parseInt(n)] || '');

    let stepResult;
    if (step.mode === 'parallel') {
      const results = await Promise.allSettled(step.agents.map(id => sendToAgent(id, prompt)));
      stepResult = step.agents.map((id, j) => {
        const r = results[j];
        return `**${id}**: ${r.status === 'fulfilled' ? r.value : `Error: ${r.reason?.message}`}`;
      }).join('\n\n');
    } else {
      const parts = [];
      for (const id of step.agents) {
        const agentPrompt = parts.length > 0
          ? `${prompt}\n\n[Prior responses in this step]\n${parts.join('\n\n')}`
          : prompt;
        const result = await sendToAgent(id, agentPrompt);
        parts.push(`**${id}**: ${result}`);
      }
      stepResult = parts.join('\n\n');
    }

    stepOutputs.push(stepResult);
    accumulated = stepOutputs.join('\n\n---\n\n');
  }

  const duration = Date.now() - startTime;
  const output = stepOutputs.map((s, i) => `## Step ${i + 1} (${steps[i].mode}: ${steps[i].agents.join(', ')})\n${s}`).join('\n\n---\n\n');
  return { content: [{ type: 'text', text: `**a2a_team "${workflowName}" (${steps.length} steps, ${duration}ms):**\n\n${output}` }] };
}

async function handleConsensus(args) {
  const context = bridgeContext();
  const serverUrl = await getCoordinator();
  const result = await peerRequest(serverUrl, '/mesh/consensus', consensusBridgeParams(args, context));

  // Format the result
  const r = result.result || result;
  const lines = [
    `**Consensus Result**`,
    `**Prompt**: ${r.prompt || args.prompt}`,
    `**Agents**: ${(r.agents || []).join(', ')}`,
    `**Judge**: ${r.judge || 'claude'}`,
    `**Confidence**: ${r.synthesis ? (r.synthesis.confidence * 100).toFixed(0) + '%' : 'N/A'}`,
    '',
  ];

  if (r.synthesis?.answer) {
    lines.push(`### Synthesized Answer`, r.synthesis.answer);
  }
  if (r.synthesis?.dissent) {
    lines.push('', `### Dissent`, r.synthesis.dissent);
  }
  if (r.synthesis?.agentAgreement && Object.keys(r.synthesis.agentAgreement).length > 0) {
    lines.push('', `### Agent Agreement`);
    for (const [agent, status] of Object.entries(r.synthesis.agentAgreement)) {
      lines.push(`- **${agent}**: ${status}`);
    }
  }
  if (r.timing) {
    lines.push('', `_Timing: ${r.timing.totalMs}ms_`);
  }

  return { content: [{ type: 'text', text: lines.join('\n') }] };
}

async function handleDebate(args) {
  const context = bridgeContext();
  const serverUrl = await getCoordinator();
  const result = await peerRequest(serverUrl, '/rpc', {
    jsonrpc: '2.0', id: `debate-${Date.now()}`,
    method: 'mesh/debate',
    params: {
      topic: args.topic,
      rounds: Math.min(args.rounds || 4, 36),
      agents: args.agents,
      judge: args.judge,
      depth: context.depth,
      meshChain: context.meshChain,
    },
  });

  if (result.error) {
    return { content: [{ type: 'text', text: `**Debate Error:** ${result.error.message || JSON.stringify(result.error)}` }], isError: true };
  }

  const r = result.result || result;
  const lines = [
    `**Debate: ${r.topic}**`,
    `**Agents**: ${(r.agents || []).join(' vs ')} | **Judge**: ${r.judge} | **Rounds**: ${r.rounds}`,
    r.timing ? `_Timing: ${(r.timing.totalMs / 1000).toFixed(1)}s_` : '',
    '',
  ];

  for (const h of (r.history || [])) {
    lines.push(`### Round ${h.round} — ${h.agent.toUpperCase()}`, h.argument, '');
  }

  if (r.synthesis) {
    lines.push(`---`, `### Verdict (${r.judge})`);
    if (r.synthesis.winner) lines.push(`**Winner:** ${r.synthesis.winner}`);
    if (r.synthesis.scores) {
      lines.push(`**Scores:** ${Object.entries(r.synthesis.scores).map(([a, s]) => `${a}: ${s}/10`).join(', ')}`);
    }
    if (r.synthesis.verdict) lines.push('', r.synthesis.verdict);
    if (r.synthesis.confidence) lines.push('', `_Confidence: ${(r.synthesis.confidence * 100).toFixed(0)}%_`);
  }

  return { content: [{ type: 'text', text: lines.join('\n') }] };
}

async function handleEnsemble(args) {
  const context = bridgeContext();
  const serverUrl = await getCoordinator();
  const result = await peerRequest(serverUrl, '/rpc', {
    jsonrpc: '2.0', id: `ensemble-${Date.now()}`,
    method: 'mesh/ensemble',
    params: ensembleBridgeParams(args, context),
  });

  if (result.error) {
    return { content: [{ type: 'text', text: `**Ensemble Error:** ${result.error.message || JSON.stringify(result.error)}` }], isError: true };
  }

  const r = result.result || result;
  const lines = [
    `**Code Ensemble**`,
    `**Task**: ${r.task}`,
    `**Agents**: ${(r.agents || []).join(', ')} | **Judge**: ${r.judge} | **Rounds**: ${r.rounds}`,
    r.timing ? `_Timing: ${(r.timing.totalMs / 1000).toFixed(1)}s_` : '',
    '',
    `### Final Code`,
    r.finalCode || '(no code produced)',
  ];

  return { content: [{ type: 'text', text: lines.join('\n') }] };
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
