// ============================================
// Mesh Consensus — Multi-agent consensus with judge
// ============================================

import { randomUUID } from 'crypto';
import { resolveSelfUrl } from './peer-registry.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';
import { persistContextSnapshot, resolveThreadId } from './mesh-context.js';
import { isMeshErrorText } from './mesh-calls.js';

function formatError(err) {
  return err instanceof Error ? err.message : String(err);
}

function normalizePositiveInt(value, fallback) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
}

function normalizeTimeoutMs(value, fallback, { min = 1000, max = 3600000 } = {}) {
  const parsed = Number.parseInt(String(value ?? ''), 10);
  if (!Number.isFinite(parsed)) return fallback;
  return Math.min(max, Math.max(min, parsed));
}

function normalizeMeshChain(meshChain) {
  if (!Array.isArray(meshChain)) return [];
  const normalized = [];
  for (const entry of meshChain) {
    if (typeof entry !== 'string' || !entry) continue;
    if (normalized[normalized.length - 1] !== entry) {
      normalized.push(entry);
    }
  }
  return normalized;
}

function appendSelfToMeshChain(meshChain, selfId) {
  const normalized = normalizeMeshChain(meshChain);
  if (normalized[normalized.length - 1] !== selfId) {
    normalized.push(selfId);
  }
  return normalized;
}

/**
 * Create a consensus executor.
 *
 * @param {Object} config
 * @param {Object} config.meshCaller - createMeshCaller instance
 * @param {Object} config.peers - { agentId: url }
 * @param {string} config.selfId - This server's ID
 * @param {number} config.maxDepth - Max mesh depth
 * @param {Object} [config.meshStore] - MeshStore (optional)
 * @param {Object} [config.meshBus] - MeshEventBus (optional)
 */
export function createConsensusExecutor({ meshCaller, peers, selfId, maxDepth, meshStore, meshBus, authToken = '', selfUrl = '' }) {
  const resolvedSelfUrl = selfUrl || resolveSelfUrl({ selfId, peers });
  const DEFAULT_CONSENSUS_TIMEOUT_MS = normalizePositiveInt(process.env.A2A_TIMEOUT_CONSENSUS_MS, 2400000); // 40 min
  const MAX_SELF_CALL_DEPTH = normalizePositiveInt(process.env.A2A_MAX_SELF_CALL_DEPTH, 3);

  /**
   * Execute a consensus round.
   *
   * @param {Object} params
   * @param {string} params.prompt - The question to ask
   * @param {string[]} [params.agents] - Agents to consult (default: all peers)
   * @param {string} [params.judge] - Judge agent ID (default: 'claude')
   * @returns {Object} Consensus result
   */
  async function execute(params, callContext = {}) {
    const { prompt: rawPrompt, agents: requestedAgents, judge = 'claude', timeout_ms } = params;
    if (!rawPrompt) throw new Error('prompt is required');
    const timeoutMs = normalizeTimeoutMs(timeout_ms, DEFAULT_CONSENSUS_TIMEOUT_MS);
    const parentChain = normalizeMeshChain(callContext.meshChain);
    const parentSelfCallDepth = normalizePositiveInt(callContext.selfCallDepth, 0);

    const consensusId = randomUUID();
    const threadId = resolveThreadId(params, callContext, `consensus-${consensusId}`);
    const { prompt } = enrichPromptIfContinuation(rawPrompt, { meshChain: parentChain, threadId }, meshStore);

    const agents = (requestedAgents || Object.keys(peers)).filter(a => peers[a]);
    if (agents.length === 0) throw new Error('No valid agents specified');

    const context = {
      // Consensus should be single-hop: participants/judge answer directly,
      // without recursively delegating to other mesh agents.
      depth: 1,
      // Keep parent chain as-is; mesh caller appends selfId per hop.
      meshChain: [...parentChain],
      taskId: `consensus-${consensusId}`,
      selfCallDepth: parentSelfCallDepth,
      timeoutMs,
    };

    const emitDialogue = (phase, agent, role, text, extra = {}) => {
      if (!meshBus) return;
      meshBus.publish({
        taskId: context.taskId,
        type: 'dialogue',
        payload: { operation: 'consensus', phase, agent, role, text: String(text).slice(0, 50000), ...extra },
      });
    };

    // Phase 1: Broadcast to all peers AND generate self response in parallel
    const allParticipants = [...agents, selfId];
    emitDialogue('collect', '*', 'system', `Fase COLLECT — consultando ${allParticipants.length} agentes (${allParticipants.join(', ')})`, { agents: allParticipants });
    const startTime = Date.now();

    // Run peer broadcast + self response in parallel
    const [peerResults, selfResponse] = await Promise.all([
      collectResponses(agents, prompt, context, timeoutMs),
      generateSelfResponse(prompt, context, timeoutMs),
    ]);

    // Combine: peers + self
    const rawResults = [...peerResults, selfResponse];
    const collectDurationMs = Date.now() - startTime;

    // Emit each agent's response
    for (const r of rawResults) {
      if (!r.error && r.response) {
        emitDialogue('collect', r.agent, 'response', r.response);
      } else if (r.error) {
        emitDialogue('collect', r.agent, 'error', r.error);
      }
    }
    emitDialogue('collect', '*', 'system', `Fase COLLECT concluída (${collectDurationMs}ms)`, { durationMs: collectDurationMs });

    // Phase 2: Send to a PEER judge for real synthesis (not self-judge)
    // Pick a peer as judge to avoid self-judging bias
    const judgeCandidates = [
      judge,
      ...agents,
    ].filter((agentId, index, arr) => arr.indexOf(agentId) === index);
    const actualJudge = judgeCandidates.find((agentId) =>
      agentId
      && agentId !== selfId
      && peers[agentId]
      && !context.meshChain.includes(agentId),
    ) || null;
    const judgeLabel = actualJudge || selfId;
    emitDialogue('judge', judgeLabel, 'system', `Fase JUDGE — ${judgeLabel} sintetizando consenso`, { judge: judgeLabel });
    const judgeStartTime = Date.now();
    const judgePrompt = buildJudgePrompt(prompt, rawResults);
    let synthesis;

    if (actualJudge && peers[actualJudge]) {
      // Judge is single-hop synthesis (does not recurse into mesh), so it needs
      // depth: 1 — using context.depth - 1 caused every JUDGE phase to fail with
      // "max mesh depth exceeded" because COLLECT already consumes the budget.
      const judgeResponse = await meshCaller.executeA2ACall(
        { agent: actualJudge, prompt: judgePrompt, timeout_ms: timeoutMs },
        {
          depth: 1,
          meshChain: [...context.meshChain],
          taskId: context.taskId,
          selfCallDepth: context.selfCallDepth,
        },
      );
      synthesis = parseJudgeResponse(judgeResponse, rawResults);
      emitDialogue('judge', actualJudge, 'synthesis', synthesis.answer, { confidence: synthesis.confidence, dissent: synthesis.dissent });
    } else {
      // Last resort fallback if no peers available
      synthesis = buildFallbackSynthesis(rawResults);
      emitDialogue('judge', selfId, 'synthesis', synthesis.answer, { confidence: synthesis.confidence, selfJudge: true });
    }
    const judgeDurationMs = Date.now() - judgeStartTime;
    emitDialogue('judge', actualJudge || selfId, 'system', `Fase JUDGE concluída (${judgeDurationMs}ms)`, { durationMs: judgeDurationMs });

    const result = {
      consensusId,
      prompt,
      agents: allParticipants,
      judge: actualJudge || selfId,
      responses: rawResults,
      synthesis,
      timing: { collectDurationMs, judgeDurationMs, totalMs: Date.now() - startTime },
    };

    // Persist event
    if (meshBus) {
      meshBus.publish({
        taskId: context.taskId,
        type: 'consensus',
        payload: {
          consensusId,
          agents,
          judge: actualJudge || selfId,
          confidence: synthesis.confidence,
          prompt: prompt.slice(0, 10000),
        },
      });
    }

    if (meshStore) {
      try {
        meshStore.createEvent(context.taskId, 'consensus', selfId, {
          consensusId, agents, judge: actualJudge || selfId,
          confidence: synthesis.confidence,
          synthesis: synthesis.answer,
        });
      } catch (err) {
        console.warn('[mesh-consensus] Failed to persist consensus event', {
          taskId: context.taskId,
          consensusId,
          server: selfId,
          error: formatError(err),
        });
      }
    }

    persistContextSnapshot(meshStore, {
      threadId,
      taskId: context.taskId,
      mode: 'consensus',
      title: rawPrompt,
      summary: synthesis.answer,
      decisions: [`judge=${actualJudge || selfId}; confidence=${synthesis.confidence}`],
      nextSteps: synthesis.dissent ? [`Review dissent: ${synthesis.dissent}`] : [],
      errors: rawResults.filter(r => r.error).map(r => `${r.agent}: ${r.error}`),
      metadata: {
        consensusId,
        agents: allParticipants,
        judge: actualJudge || selfId,
        confidence: synthesis.confidence,
        dissent: synthesis.dissent,
      },
    }, '[mesh-consensus]');

    return result;
  }

  /**
   * Generate self response — the orchestrating server also participates.
   * Calls localhost /tasks/send to generate a response using its own model.
   */
  async function generateSelfResponse(prompt, context, timeoutMs = DEFAULT_CONSENSUS_TIMEOUT_MS) {
    const start = Date.now();
    try {
      if (!resolvedSelfUrl) {
        return { agent: selfId, response: null, durationMs: Date.now() - start, error: 'Self URL is not configured' };
      }
      if (context.selfCallDepth >= MAX_SELF_CALL_DEPTH) {
        return { agent: selfId, response: null, durationMs: Date.now() - start, error: `max self-call depth exceeded (${MAX_SELF_CALL_DEPTH})` };
      }

      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), timeoutMs);
      const resp = await fetch(`${resolvedSelfUrl}/tasks/send`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(authToken ? { Authorization: `Bearer ${authToken}` } : {}),
        },
        body: JSON.stringify({
          message: { role: 'user', parts: [{ type: 'text', text: prompt }] },
          metadata: {
            maxDepth: 0,
            calledBy: selfId,
            meshChain: appendSelfToMeshChain(context.meshChain, selfId),
            skipSelfCall: true,
            selfCallDepth: context.selfCallDepth + 1,
          },
        }),
        signal: controller.signal,
      });
      // NOTE: do NOT clearTimeout before resp.json() — the body read can also hang.
      // The AbortController must cover the entire operation (fetch + body read).
      const data = await resp.json();
      clearTimeout(timeout);
      const msg = data.result?.status?.message;
      const text = msg?.parts?.map(p => p.text).join('\n');
      if (text) return { agent: selfId, response: text, durationMs: Date.now() - start, error: null };
      return { agent: selfId, response: JSON.stringify(data.result ?? data), durationMs: Date.now() - start, error: null };
    } catch (err) {
      return { agent: selfId, response: null, durationMs: Date.now() - start, error: err.message };
    }
  }

  /**
   * Collect responses from agents in parallel.
   * Uses executeA2ABroadcast (spawns parallel fetch via Node script) instead of
   * sequential executeA2ACall (which uses execFileSync).
   */
  async function collectResponses(agents, prompt, context, timeoutMs = DEFAULT_CONSENSUS_TIMEOUT_MS) {
    const start = Date.now();
    try {
      // executeA2ABroadcast runs all agents in parallel via async fetch
      const rawMarkdown = await meshCaller.executeA2ABroadcast(
        { agents, prompt, timeout_ms: timeoutMs },
        {
          depth: context.depth,
          meshChain: [...context.meshChain],
          taskId: context.taskId,
          selfCallDepth: context.selfCallDepth,
        },
      );

      // Parse the markdown response back into structured results
      // Format: **agent**: response\n\n---\n\n**agent2**: response2
      const sections = String(rawMarkdown).split('\n\n---\n\n');
      return sections.map(section => {
        const match = section.match(/^\*\*(\w+)\*\*:\s*([\s\S]*)$/);
        if (match) {
          const isError = match[2].startsWith('Error');
          return {
            agent: match[1],
            response: isError ? null : match[2],
            durationMs: Date.now() - start,
            error: isError ? match[2] : null,
          };
        }
        return { agent: 'unknown', response: section, durationMs: Date.now() - start, error: null };
      });
    } catch (err) {
      // Fallback: return error for all agents
      return agents.map(agent => ({
        agent, response: null, durationMs: Date.now() - start, error: err.message,
      }));
    }
  }

  /**
   * Build the judge prompt with all agent responses.
   */
  function buildJudgePrompt(originalPrompt, responses) {
    const agentResponses = responses
      .map(r => `### ${r.agent}\n${r.error ? `[ERROR: ${r.error}]` : r.response}`)
      .join('\n\n---\n\n');

    return `You are a judge synthesizing responses from multiple AI agents.

## Original Question
${originalPrompt}

## Agent Responses
${agentResponses}

## Your Task
Analyze all agent responses and provide a synthesized answer. Respond with a JSON block:

\`\`\`json
{
  "answer": "Your synthesized answer combining the best insights from all agents",
  "confidence": 0.85,
  "dissent": "Any significant disagreements between agents (or null if they agree)",
  "agentAgreement": {
    "agentName": "agree|partial|disagree"
  }
}
\`\`\`

Be thorough but concise. The confidence score (0.0-1.0) should reflect how much the agents agreed.`;
  }

  /**
   * Parse the judge's response, extracting JSON if possible.
   */
  function parseJudgeResponse(response, rawResults) {
    const responseStr = String(response);
    // Try to extract JSON block
    const jsonMatch = responseStr.match(/```json\s*([\s\S]*?)```/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[1]);
        return {
          answer: parsed.answer || responseStr,
          confidence: typeof parsed.confidence === 'number' ? Math.min(1, Math.max(0, parsed.confidence)) : 0.5,
          dissent: parsed.dissent || null,
          agentAgreement: parsed.agentAgreement || {},
        };
      } catch (err) {
        console.warn('[mesh-consensus] Failed to parse judge JSON response, using fallback synthesis', {
          error: formatError(err),
          responsePreview: responseStr.slice(0, 200),
        });
      }
    }

    if (isMeshErrorText(responseStr)) {
      return {
        answer: `Judge failed: ${responseStr}`,
        confidence: 0,
        dissent: 'Judge returned a mesh/tooling error instead of a synthesis.',
        agentAgreement: Object.fromEntries(rawResults.map(r => [r.agent, r.error ? 'error' : 'unknown'])),
      };
    }

    // Fallback: use raw response as synthesis
    return {
      answer: responseStr,
      confidence: 0.5,
      dissent: null,
      agentAgreement: {},
    };
  }

  /**
   * Build a fallback synthesis when self-judging.
   */
  function buildFallbackSynthesis(responses) {
    const validResponses = responses.filter(r => !r.error);
    if (validResponses.length === 0) {
      return { answer: 'No valid responses received from agents.', confidence: 0, dissent: null, agentAgreement: {} };
    }

    const combined = validResponses.map(r => `**${r.agent}**: ${r.response}`).join('\n\n');
    return {
      answer: combined,
      confidence: validResponses.length / responses.length,
      dissent: null,
      agentAgreement: Object.fromEntries(validResponses.map(r => [r.agent, 'agree'])),
    };
  }

  /**
   * Format consensus result for tool output.
   */
  function formatConsensusResult(result) {
    const lines = [
      `## Consensus Result`,
      `**Prompt**: ${result.prompt}`,
      `**Agents**: ${result.agents.join(', ')}`,
      `**Judge**: ${result.judge}`,
      `**Confidence**: ${(result.synthesis.confidence * 100).toFixed(0)}%`,
      '',
      `### Synthesized Answer`,
      result.synthesis.answer,
    ];

    if (result.synthesis.dissent) {
      lines.push('', `### Dissent`, result.synthesis.dissent);
    }

    if (Object.keys(result.synthesis.agentAgreement).length > 0) {
      lines.push('', `### Agent Agreement`);
      for (const [agent, status] of Object.entries(result.synthesis.agentAgreement)) {
        lines.push(`- **${agent}**: ${status}`);
      }
    }

    lines.push('', `_Timing: collect ${result.timing.collectDurationMs}ms, judge ${result.timing.judgeDurationMs}ms, total ${result.timing.totalMs}ms_`);

    return lines.join('\n');
  }

  return { execute, formatConsensusResult };
}
