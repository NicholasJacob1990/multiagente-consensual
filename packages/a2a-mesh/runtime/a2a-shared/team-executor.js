// ============================================
// A2A Team Executor — Multi-step workflow orchestration
// ============================================
// Shared module: imported by every native A2A server.
// Each server injects its own context (selfId, peers, meshBus)

import { randomUUID } from 'crypto';
import { resolveSelfUrl } from './peer-registry.js';
import { persistContextSnapshot, resolveThreadId } from './mesh-context.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';
import { capTimeoutForAgent } from './agent-catalog.js';

function normalizePositiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeTimeoutMs(value, fallback, { min = 1000, max = 3600000 } = {}) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

const MAX_SELF_CALL_DEPTH = normalizePositiveInt(process.env.A2A_MAX_SELF_CALL_DEPTH, 3);
const TEAM_PROMPT_CHARS = normalizePositiveInt(process.env.A2A_TEAM_PROMPT_CHARS, 30000);
const TEAM_CONTEXT_CHARS = normalizePositiveInt(process.env.A2A_TEAM_CONTEXT_CHARS, 20000);
const TEAM_RESPONSE_CONTEXT_CHARS = normalizePositiveInt(process.env.A2A_TEAM_RESPONSE_CONTEXT_CHARS, 8000);

function truncateForPrompt(text, limit, label = 'content') {
  const value = String(text || '');
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n\n[TRUNCATED ${value.length - limit} chars from ${label}.]`;
}

function timeoutForAgent(agent, timeoutMs) {
  return capTimeoutForAgent(agent, 'team', timeoutMs);
}

/**
 * Execute a multi-step team workflow.
 *
 * @param {Object} input - The a2a_team tool input
 * @param {string} input.name - Workflow name (optional)
 * @param {Array}  input.steps - Array of { mode, agents, prompt }
 * @param {string} input.context - Initial shared context (optional)
 * @param {boolean} input.accumulate - Accumulate context between steps (default true)
 * @param {Object} context - Execution context injected by calling server
 * @param {number} context.depth - Current mesh depth
 * @param {Array}  context.meshChain - Chain of caller IDs
 * @param {string} context.taskId - Parent task ID
 * @param {string} context.selfId - This server's catalog ID
 * @param {Object} context.peers - { agentId: url } map (excludes self)
 * @param {Object} context.meshBus - MeshEventBus instance (optional)
 * @returns {string} Formatted markdown result
 */
export async function executeA2ATeam(input, context) {
  const { steps, name, context: initialContext, accumulate = true, includeSelf = false, timeout_ms } = input;
  const { depth, meshChain, taskId, selfId, peers, meshBus, meshStore, authToken = '', selfUrl = '', selfCallDepth = 0 } = context;
  const resolvedSelfUrl = selfUrl || resolveSelfUrl({ selfId, peers });
  const globalTimeoutMs = normalizeTimeoutMs(timeout_ms, null);

  if (!steps || !Array.isArray(steps) || steps.length === 0) {
    return 'Error: a2a_team requires at least one step.';
  }

  if ((depth ?? 7) <= 0) return `Error: max mesh depth exceeded (chain: ${(meshChain || []).join(' → ')})`;

  const teamId = randomUUID();
  const threadId = resolveThreadId(input, context, taskId || `team-${teamId}`);
  const startTime = Date.now();
  const stepResults = [];
  let accumulated = '';

  // Publish team start event
  if (meshBus) {
    meshBus.publish({
      taskId,
      type: 'a2a_team_start',
      payload: {
        teamId,
        name: name || 'unnamed',
        stepCount: steps.length,
        agents: [...new Set(steps.flatMap(s => s.agents || []))],
      },
    });
  }

  // Initial context
  if (initialContext) {
    accumulated = `[Context]\n${truncateForPrompt(initialContext, TEAM_CONTEXT_CHARS, 'initial team context')}\n\n`;
  }

  const childDepth = Math.max(0, (depth ?? 7) - 1);
  const childMetadata = {
    maxDepth: childDepth,
    calledBy: selfId,
    parentTaskId: taskId,
    meshChain: [...(meshChain || []), selfId],
    selfCallDepth,
    teamId,
  };

  for (let stepIdx = 0; stepIdx < steps.length; stepIdx++) {
    const step = steps[stepIdx];
    const chain = meshChain || [];
    const stepIncludeSelf = step.includeSelf ?? includeSelf;
    const agents = (step.agents || []).filter((agentId) => {
      if (agentId === selfId) return stepIncludeSelf && Boolean(resolvedSelfUrl) && !chain.includes(selfId);
      return peers[agentId] && !chain.includes(agentId);
    });

    if (agents.length === 0) {
      const availableAgents = resolvedSelfUrl ? [...Object.keys(peers), selfId] : Object.keys(peers);
      stepResults.push({
        stepIndex: stepIdx,
        mode: step.mode || 'parallel',
        agents: step.agents || [],
        results: [{ agent: 'none', error: `No valid agents. Available: ${availableAgents.join(', ')}` }],
      });
      continue;
    }

    // Resolve templates
    let prompt = step.prompt || '';
    if (accumulate && accumulated) {
      prompt = prompt.replace(/\{\{previous\}\}/g, accumulated.trim());
    } else {
      prompt = prompt.replace(/\{\{previous\}\}/g, '(no prior context)');
    }
    for (let i = 0; i < stepResults.length; i++) {
      const ref = formatStepOutput(stepResults[i], { forPrompt: true });
      prompt = prompt.replace(new RegExp(`\\{\\{step_${i}\\}\\}`, 'g'), ref);
    }
    const enriched = enrichPromptIfContinuation(prompt, { meshChain: meshChain || [], threadId }, meshStore);
    if (enriched.enriched) prompt = enriched.prompt;
    prompt = truncateForPrompt(prompt, TEAM_PROMPT_CHARS, `team step ${stepIdx + 1} prompt`);

    // Publish step event
    if (meshBus) {
      meshBus.publish({
        taskId,
        type: 'a2a_team_step',
        payload: {
          teamId,
          stepIndex: stepIdx,
          mode: step.mode,
          agents,
          promptPreview: prompt.slice(0, 200),
        },
      });
    }

    let stepResult;
    const stepTimeoutMs = normalizeTimeoutMs(step.timeout_ms, globalTimeoutMs);
    if (step.mode === 'parallel') {
      stepResult = await executeTeamParallel(agents, prompt, childMetadata, {
        peers,
        selfId,
        selfUrl: resolvedSelfUrl,
        authToken,
        timeoutMs: stepTimeoutMs,
        selfCallDepth,
      });
    } else {
      stepResult = await executeTeamSequential(agents, prompt, childMetadata, {
        peers,
        selfId,
        selfUrl: resolvedSelfUrl,
        authToken,
        timeoutMs: stepTimeoutMs,
        selfCallDepth,
      });
    }

    stepResult.stepIndex = stepIdx;
    stepResult.mode = step.mode || 'sequential';
    stepResults.push(stepResult);

    // Accumulate for next steps
    if (accumulate) {
      accumulated = truncateForPrompt(
        `${accumulated}${formatStepOutput(stepResult, { forPrompt: true })}\n\n`,
        TEAM_CONTEXT_CHARS,
        'accumulated team context',
      );
    }
  }

  // Publish team complete event
  const durationMs = Date.now() - startTime;
  if (meshBus) {
    meshBus.publish({
      taskId,
      type: 'a2a_team_complete',
      payload: { teamId, name: name || 'unnamed', steps: steps.length, durationMs },
    });
  }

  const output = formatTeamResult(stepResults, name, teamId, durationMs);
  persistContextSnapshot(meshStore, {
    threadId,
    taskId,
    mode: 'team',
    title: name || 'unnamed',
    summary: output,
    decisions: [`team completed ${steps.length} step(s) in ${durationMs}ms`],
    nextSteps: ['Use the team outputs as prior context for the next mesh mode.'],
    errors: stepResults.flatMap(step => step.results.filter(r => r.error).map(r => `${r.agent}: ${r.error}`)),
    artifacts: [{ kind: 'team_result', field: 'formatted_output' }],
    metadata: {
      teamId,
      name: name || 'unnamed',
      stepCount: steps.length,
      durationMs,
    },
  }, '[team-executor]');

  return output;
}

/**
 * Build peer request headers.
 */
function buildPeerHeaders(authToken = '') {
  return {
    'Content-Type': 'application/json',
    ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
  };
}

function extractPeerResponseText(data) {
  const msg = data?.result?.status?.message;
  return msg?.parts?.map(p => p.text).join('\n') || JSON.stringify(data?.result ?? data);
}

async function callPeer(peer, prompt, metadata, authToken = '', timeoutMs = 1500000) {
  const body = JSON.stringify({
    message: { role: 'user', parts: [{ type: 'text', text: prompt }] },
    metadata,
  });

  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(new Error('Request timeout')), timeoutMs);
  try {
    const response = await fetch(`${peer}/tasks/send`, {
      method: 'POST',
      headers: buildPeerHeaders(authToken),
      body,
      signal: controller.signal,
    });
    const raw = await response.text();
    const parsed = JSON.parse(raw);
    return extractPeerResponseText(parsed);
  } finally {
    clearTimeout(timeout);
  }
}

/**
 * Execute agents in parallel.
 */
async function executeTeamParallel(agents, prompt, metadata, {
  peers, selfId, selfUrl, authToken = '', timeoutMs = null, selfCallDepth = 0,
}) {
  const requestTimeoutMs = normalizeTimeoutMs(timeoutMs, 300000);
  const results = await Promise.all(agents.map(async (agent) => {
    const start = Date.now();
    try {
      const targetUrl = agent === selfId ? selfUrl : peers[agent];
      if (agent === selfId && selfCallDepth >= MAX_SELF_CALL_DEPTH) {
        return { agent, error: `max self-call depth exceeded (${MAX_SELF_CALL_DEPTH})`, durationMs: Date.now() - start };
      }
      const targetMetadata = agent === selfId
        ? { ...metadata, selfCallDepth: selfCallDepth + 1 }
        : metadata;
      const responseText = await callPeer(targetUrl, prompt, targetMetadata, authToken, timeoutForAgent(agent, requestTimeoutMs));
      return { agent, response: responseText, durationMs: Date.now() - start };
    } catch (err) {
      return { agent, error: err.message, durationMs: Date.now() - start };
    }
  }));
  return { agents, results };
}

/**
 * Execute agents sequentially (each sees prior agents' output within the step)
 */
async function executeTeamSequential(agents, prompt, metadata, {
  peers, selfId, selfUrl, authToken = '', timeoutMs = null, selfCallDepth = 0,
}) {
  const requestTimeoutMs = normalizeTimeoutMs(timeoutMs, 120000);
  const results = [];
  let withinStepContext = '';

  for (const agent of agents) {
    const targetUrl = agent === selfId ? selfUrl : peers[agent];
    if (!targetUrl) {
      results.push({ agent, error: `Unknown agent: ${agent}` });
      continue;
    }

    let agentPrompt = prompt;
    if (withinStepContext) {
      agentPrompt += `\n\n[Prior responses in this step]\n${withinStepContext}`;
    }
    agentPrompt = truncateForPrompt(agentPrompt, TEAM_PROMPT_CHARS, `team sequential prompt for ${agent}`);

    const start = Date.now();
    try {
      if (agent === selfId && selfCallDepth >= MAX_SELF_CALL_DEPTH) {
        results.push({ agent, error: `max self-call depth exceeded (${MAX_SELF_CALL_DEPTH})`, durationMs: Date.now() - start });
        withinStepContext += `**${agent}**: (error: max self-call depth exceeded (${MAX_SELF_CALL_DEPTH}))\n\n`;
        continue;
      }
      const targetMetadata = agent === selfId
        ? { ...metadata, selfCallDepth: selfCallDepth + 1 }
        : metadata;
      const responseText = await callPeer(targetUrl, agentPrompt, targetMetadata, authToken, timeoutForAgent(agent, requestTimeoutMs));

      results.push({ agent, response: responseText, durationMs: Date.now() - start });
      withinStepContext = truncateForPrompt(
        `${withinStepContext}**${agent}**: ${truncateForPrompt(responseText, TEAM_RESPONSE_CONTEXT_CHARS, `${agent} response`)}\n\n`,
        TEAM_CONTEXT_CHARS,
        'within-step team context',
      );
    } catch (err) {
      results.push({ agent, error: err.message, durationMs: Date.now() - start });
      withinStepContext += `**${agent}**: (error: ${err.message})\n\n`;
    }
  }

  return { agents, results };
}

/**
 * Format a single step's output for accumulation/reference
 */
function formatStepOutput(stepResult, { forPrompt = false } = {}) {
  return stepResult.results
    .map(r => {
      const text = r.response || `(error: ${r.error})`;
      return `**${r.agent}**: ${forPrompt ? truncateForPrompt(text, TEAM_RESPONSE_CONTEXT_CHARS, `${r.agent} response`) : text}`;
    })
    .join('\n\n');
}

/**
 * Format the final team result as Markdown
 */
function formatTeamResult(stepResults, name, teamId, durationMs) {
  let output = `# Team: ${name || 'unnamed'}\n`;
  output += `_ID: ${teamId.slice(0, 8)} | Duration: ${(durationMs / 1000).toFixed(1)}s_\n\n`;

  for (const step of stepResults) {
    output += `## Step ${step.stepIndex + 1} (${step.mode})\n\n`;
    for (const r of step.results) {
      output += `### ${r.agent}`;
      if (r.durationMs) output += ` (${(r.durationMs / 1000).toFixed(1)}s)`;
      output += '\n';
      output += r.response || `Error: ${r.error}`;
      output += '\n\n---\n\n';
    }
  }

  return output;
}
