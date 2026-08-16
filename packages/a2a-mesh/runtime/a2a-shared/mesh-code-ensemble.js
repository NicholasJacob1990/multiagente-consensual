// ============================================
// Mesh Code Ensemble — NxN cross-review code generation
// ============================================

import { createHash, randomUUID } from 'crypto';
import { resolveSelfUrl } from './peer-registry.js';
import { persistContextSnapshot, resolveThreadId } from './mesh-context.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';
import { isMeshErrorText } from './mesh-calls.js';
import { classifySubmission } from './cli-tool-wrapper.js';
import { capTimeoutForAgent } from './agent-catalog.js';

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

const CODE_PREVIEW_CHARS = normalizePositiveInt(process.env.A2A_ENSEMBLE_CODE_PREVIEW_CHARS, 12000);
const REVIEW_PREVIEW_CHARS = normalizePositiveInt(process.env.A2A_ENSEMBLE_REVIEW_PREVIEW_CHARS, 6000);

export const ENSEMBLE_PROFILES = Object.freeze({
  fast: Object.freeze({ rounds: 1, deduplicate: true, earlyExit: true }),
  normal: Object.freeze({ rounds: 2, deduplicate: true, earlyExit: true }),
  deep: Object.freeze({ rounds: 5, deduplicate: false, earlyExit: false }),
});

function normalizeProfile(value) {
  const profile = String(value || '').trim().toLowerCase();
  return ENSEMBLE_PROFILES[profile] ? profile : 'custom';
}

function extractPrimaryCode(text) {
  const value = String(text || '').trim();
  const fenced = value.match(/```(?:[\w.+-]+)?\s*\n([\s\S]*?)```/);
  return (fenced?.[1] || value).trim();
}

export function canonicalizeCodeSubmission(text) {
  return extractPrimaryCode(text)
    .replace(/\r\n?/g, '\n')
    .split('\n')
    .map(line => line.trim())
    .filter(Boolean)
    .join('\n');
}

export function clusterCodeSubmissions(submissions) {
  const clusters = [];
  const byCanonical = new Map();
  for (const [agent, response] of Object.entries(submissions || {})) {
    const canonical = canonicalizeCodeSubmission(response);
    const hash = createHash('sha256').update(canonical).digest('hex');
    let cluster = byCanonical.get(hash);
    if (!cluster || cluster.canonical !== canonical) {
      cluster = { representative: agent, agents: [], hash, canonical };
      byCanonical.set(hash, cluster);
      clusters.push(cluster);
    }
    cluster.agents.push(agent);
  }
  return clusters;
}

function truncateForPrompt(text, limit, label = 'content') {
  const value = String(text || '');
  if (value.length <= limit) return value;
  const omitted = value.length - limit;
  return `${value.slice(0, limit)}\n\n[TRUNCATED ${omitted} chars from ${label}; preserve only actionable issues in this round.]`;
}

function timeoutForAgent(agent, timeoutMs) {
  return capTimeoutForAgent(agent, 'ensemble', timeoutMs);
}

function codeBlockForPrompt(agent, code) {
  return `<code author="${agent}" truncated="${String(code || '').length > CODE_PREVIEW_CHARS}">\n${truncateForPrompt(code, CODE_PREVIEW_CHARS, `${agent} code`)}\n</code>`;
}

function reviewBlockForPrompt(reviewer, review) {
  return `<review from="${reviewer}" truncated="${String(review || '').length > REVIEW_PREVIEW_CHARS}">\n${truncateForPrompt(review, REVIEW_PREVIEW_CHARS, `${reviewer} review`)}\n</review>`;
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

/**
 * Create a code ensemble executor.
 *
 * Implements a 4-phase pipeline:
 *   1. WRITE   — All agents generate code in parallel
 *   2. REVIEW  — Each agent reviews all OTHER agents' code (NxN)
 *   3. REVISE  — Each agent revises their code using received reviews
 *   4. SYNTH   — A judge synthesizes the best final solution
 *
 * Multiple rounds repeat phases 2+3 before synthesis.
 *
 * @param {Object} config
 * @param {Object} config.meshCaller - createMeshCaller instance
 * @param {Object} config.peers - { agentId: url }
 * @param {string} config.selfId - This server's ID
 * @param {number} config.maxDepth - Max mesh depth
 * @param {Object} [config.meshStore] - MeshStore (optional)
 * @param {Object} [config.meshBus] - MeshEventBus (optional)
 */
export function createCodeEnsembleExecutor({ meshCaller, peers, selfId, maxDepth, meshStore, meshBus, authToken = '', selfUrl = '', peerDiscovery = null }) {
  const resolvedSelfUrl = selfUrl || resolveSelfUrl({ selfId, peers });
  const DEFAULT_ENSEMBLE_TIMEOUT_MS = normalizePositiveInt(process.env.A2A_TIMEOUT_ENSEMBLE_MS, 1800000); // 30 min per model call
  const MAX_SELF_CALL_DEPTH = normalizePositiveInt(process.env.A2A_MAX_SELF_CALL_DEPTH, 3);

  /**
   * Execute the code ensemble pipeline.
   *
   * @param {Object} params
   * @param {string} params.task - Coding task description
   * @param {string} [params.language='python'] - Programming language
   * @param {number} [params.rounds=1] - Review+revise cycles (1-12)
   * @param {string} [params.judge='claude'] - Judge agent ID
   * @returns {Object} Ensemble result with final_code
   */
  async function execute(params, callContext = {}) {
    const {
      task,
      language = 'python',
      rounds: requestedRounds,
      judge = 'claude',
      timeout_ms,
      agents: requestedAgents,
      profile: requestedProfile,
    } = params;
    if (!task) throw new Error('task is required');
    const timeoutMs = normalizeTimeoutMs(timeout_ms, DEFAULT_ENSEMBLE_TIMEOUT_MS);
    const parentDepth = normalizePositiveInt(callContext.depth, maxDepth);
    const parentChain = normalizeMeshChain(callContext.meshChain);
    const parentSelfCallDepth = normalizePositiveInt(callContext.selfCallDepth, 0);

    const profile = normalizeProfile(requestedProfile);
    const profileConfig = ENSEMBLE_PROFILES[profile] || null;
    const rawRounds = requestedRounds ?? profileConfig?.rounds ?? 1;
    const rounds = Math.max(1, Math.min(12, rawRounds));
    const deduplicate = params.deduplicate ?? profileConfig?.deduplicate ?? true;
    const earlyExit = params.early_exit ?? params.earlyExit ?? profileConfig?.earlyExit ?? true;
    const ensembleId = randomUUID();
    const threadId = resolveThreadId(params, callContext, `ensemble-${ensembleId}`);
    const { prompt: taskForPrompt } = enrichPromptIfContinuation(task, { meshChain: parentChain, threadId }, meshStore);
    const hasExplicitAgents = Array.isArray(requestedAgents) && requestedAgents.length > 0;
    const invalidAgents = hasExplicitAgents
      ? [...new Set(requestedAgents)].filter((agent) => agent !== selfId && !peers[agent])
      : [];
    if (invalidAgents.length > 0) throw new Error(`Unknown ensemble agents: ${invalidAgents.join(', ')}`);
    let defaultPeerIds = Object.keys(peers);
    if (!hasExplicitAgents && peerDiscovery) {
      await peerDiscovery.checkAllHealth();
      defaultPeerIds = Object.keys(peerDiscovery.getOnlinePeers());
      if (defaultPeerIds.length === 0) throw new Error('No online peer agents available for ensemble');
    }
    const requested = hasExplicitAgents ? requestedAgents : [...defaultPeerIds, selfId];
    const allParticipants = [...new Set(requested)]
      .filter((agent) => agent === selfId || Boolean(peers[agent]));
    if (allParticipants.length === 0) throw new Error('No valid agents available in mesh');
    const agents = allParticipants.filter((agent) => agent !== selfId);
    const includeSelf = allParticipants.includes(selfId);

    const context = {
      depth: parentDepth - 1,
      meshChain: [...parentChain],
      taskId: callContext.taskId || `ensemble-${ensembleId}`,
      selfCallDepth: parentSelfCallDepth,
      timeoutMs,
      signal: callContext.signal,
    };

    const startTime = Date.now();
    const phases = [];

    const persistResultContext = (result) => {
      persistContextSnapshot(meshStore, {
        threadId,
        taskId: context.taskId,
        mode: 'ensemble',
        title: task,
        summary: result.finalCode || 'No final code produced.',
        decisions: [`judge=${result.judge}; rounds=${result.rounds}; profile=${result.profile}; activeAgents=${result.agents.join(', ')}`],
        nextSteps: ['Review finalCode and apply it to the target workspace if accepted.'],
        errors: result.phases.flatMap(p => Array.isArray(p.results) ? p.results.filter(r => r.error).map(r => `${r.agent}: ${r.error}`) : []),
        artifacts: [{ kind: 'final_code', language, field: 'finalCode' }],
        metadata: {
          ensembleId,
          language,
          rounds: result.rounds,
          judge: result.judge,
          agents: result.agents,
          profile: result.profile,
          optimization: result.optimization,
        },
      }, '[mesh-ensemble]');
      return result;
    };

    const emitDialogue = (phase, agent, role, text, extra = {}) => {
      if (!meshBus) return;
      meshBus.publish({
        taskId: context.taskId,
        type: 'dialogue',
        payload: { operation: 'ensemble', phase, agent, role, text: String(text).slice(0, 50000), ...extra },
      });
    };

    // ---- Phase 1: WRITE ----
    emitDialogue('write', '*', 'system', `Fase WRITE iniciada — ${allParticipants.length} agentes gerando código ${language}`, { agents: allParticipants });

    const writePrompt = `You are an expert programmer. Write clean, correct ${language} code for this task.\n\n## Task\n${taskForPrompt}\n\nRespond ONLY with the code (inside a single code block).`;

    const writeStart = Date.now();
    // Run peer broadcast + self response in parallel
    const [peerWriteResults, selfWriteResult] = await Promise.all([
      callAllAgents(agents, writePrompt, context, timeoutMs),
      includeSelf ? generateSelfResponse(writePrompt, context, timeoutMs) : Promise.resolve(null),
    ]);
    const writeResults = [...peerWriteResults, ...(selfWriteResult ? [selfWriteResult] : [])];
    phases.push({ phase: 'write', durationMs: Date.now() - writeStart, results: writeResults });

    // Emit each agent's write result
    for (const r of writeResults) {
      if (!r.error && r.response) {
        emitDialogue('write', r.agent, 'author', r.response);
      } else if (r.error) {
        emitDialogue('write', r.agent, 'error', r.error);
      }
    }
    emitDialogue('write', '*', 'system', `Fase WRITE concluída (${Date.now() - writeStart}ms)`, { durationMs: Date.now() - writeStart });

    // Build submissions map (agent -> code), filtering out toxic outputs.
    // Anti-loop short-circuit: if WRITE returned only bootstrap, prompt-echo,
    // or a mesh error string, we MUST NOT pass it to REVIEW/REVISE — those
    // phases would review noise and "fix" hallucinations on top of garbage.
    const submissions = {};
    const rejectedAgents = [];
    for (const r of writeResults) {
      if (r.error || !r.response) continue;
      const verdict = classifySubmission(r.response, writePrompt);
      if (verdict !== 'ok') {
        rejectedAgents.push({ agent: r.agent, reason: verdict });
        emitDialogue('write', r.agent, 'rejected', `Submission rejected (${verdict}) — excluded from REVIEW/REVISE`, { reason: verdict });
        continue;
      }
      submissions[r.agent] = r.response;
    }
    if (rejectedAgents.length > 0) {
      const summary = rejectedAgents.map(r => `${r.agent}=${r.reason}`).join(', ');
      console.warn(`[mesh-ensemble] WRITE phase rejected ${rejectedAgents.length}/${writeResults.length} submissions: ${summary}`);
    }
    const activeAgents = Object.keys(submissions);
    if (activeAgents.length === 0) {
      // All agents produced bootstrap/echo/error — fail fast with a clear
      // signal so the caller knows the ensemble couldn't even start, not that
      // REVIEW had nothing to do.
      const reasons = rejectedAgents.map(r => `${r.agent}: ${r.reason}`).join('; ');
      emitDialogue('write', '*', 'error', `Ensemble aborted — no agent produced usable code in WRITE (${reasons || 'all errored'})`, { reasons: rejectedAgents });
      return persistResultContext(buildResult(ensembleId, task, allParticipants, '', phases, rounds, judge, startTime));
    }

    const candidateClusters = clusterCodeSubmissions(submissions);
    const workingAgents = deduplicate
      ? candidateClusters.map(cluster => cluster.representative)
      : activeAgents;
    const equivalentCandidates = activeAgents.length - workingAgents.length;
    const unanimousEquivalent = Boolean(
      earlyExit
      && activeAgents.length > 1
      && candidateClusters.length === 1,
    );
    if (equivalentCandidates > 0) {
      emitDialogue('deduplicate', '*', 'system',
        `${equivalentCandidates} candidato(s) equivalente(s) agrupado(s); ${workingAgents.length} versão(ões) materialmente distinta(s) seguirá(ão).`,
        { candidateClusters: candidateClusters.map(({ representative, agents, hash }) => ({ representative, agents, hash })) });
    }
    if (unanimousEquivalent) {
      phases.push({ phase: 'equivalence-consensus', durationMs: 0 });
      emitDialogue('deduplicate', '*', 'system',
        'Consenso por equivalência detectado — REVIEW/REVISE omitidos; o juiz ainda validará o candidato final.',
        { earlyExit: true });
    }

    // ---- Phases 2+3: REVIEW + REVISE (repeated for rounds) ----
    let allReviews = {};  // reviewer -> review text (persists across rounds for synthesize phase)
    for (let round = 1; round <= rounds && !unanimousEquivalent; round++) {
      context.signal?.throwIfAborted();
      // Phase 2: CROSS-REVIEW (each reviews all OTHERS)
      emitDialogue(`review-${round}`, '*', 'system', `Fase REVIEW round ${round} — cross-review NxN`, { round, agents: activeAgents });
      const reviewStart = Date.now();
      allReviews = {};
      const reviewsByAuthor = {}; // author -> [review texts]
      for (const a of workingAgents) reviewsByAuthor[a] = [];

      for (const reviewer of workingAgents) {
        context.signal?.throwIfAborted();
        const otherBlocks = workingAgents
          .filter(a => a !== reviewer)
          .map(a => codeBlockForPrompt(a, submissions[a]))
          .join('\n\n');

        if (!otherBlocks) continue;

        const reviewing = workingAgents.filter(a => a !== reviewer);
        emitDialogue(`review-${round}`, reviewer, 'reviewer', `Revisando código de: ${reviewing.join(', ')}...`, { reviewing });

        const reviewPrompt = `You are an expert code reviewer. Review the following ${language} solutions for this task.\n\n## Task\n${taskForPrompt}\n\n## Code submissions\n${otherBlocks}\n\nFor each submission: correctness issues, performance, style, 1-10 score.`;

        let reviewResponse;
        if (reviewer === selfId) {
          const selfResult = await generateSelfResponse(reviewPrompt, context);
          reviewResponse = selfResult.response || selfResult.error || '';
        } else {
          reviewResponse = await meshCaller.executeA2ACall(
            { agent: reviewer, prompt: reviewPrompt, timeout_ms: timeoutForAgent(reviewer, timeoutMs), allowDelegation: false },
            {
              depth: context.depth,
              meshChain: [...context.meshChain],
              taskId: context.taskId,
              selfCallDepth: context.selfCallDepth,
              signal: context.signal,
            },
          );
        }
        const reviewText = String(reviewResponse || '');
        allReviews[reviewer] = reviewText;

        emitDialogue(`review-${round}`, reviewer, 'review', reviewText, { reviewing });

        // Distribute review to all OTHER authors
        for (const author of workingAgents) {
          if (author !== reviewer && reviewText) {
            reviewsByAuthor[author].push(reviewBlockForPrompt(reviewer, reviewText));
          }
        }
      }
      phases.push({ phase: `cross-review-${round}`, durationMs: Date.now() - reviewStart });
      emitDialogue(`review-${round}`, '*', 'system', `Fase REVIEW round ${round} concluída (${Date.now() - reviewStart}ms)`, { durationMs: Date.now() - reviewStart });

      // Phase 3: REVISE (each agent revises with received reviews)
      emitDialogue(`revise-${round}`, '*', 'system', `Fase REVISE round ${round} — incorporando feedback`, { round, agents: activeAgents });
      const reviseStart = Date.now();
      for (const agent of workingAgents) {
        context.signal?.throwIfAborted();
        const reviews = reviewsByAuthor[agent].join('\n\n');
        if (!reviews) continue;

        emitDialogue(`revise-${round}`, agent, 'revising', `Revisando código com base no feedback...`);

        const revisePrompt = `You are an expert programmer. Revise your code based on peer reviews.\n\n## Original task\n${taskForPrompt}\n\n## Your original code\n${truncateForPrompt(submissions[agent], CODE_PREVIEW_CHARS, `${agent} original code`)}\n\n## Peer reviews\n${reviews}\n\nIncorporate valid feedback. Fix bugs, improve performance. Respond ONLY with the revised code.`;

        let revised;
        if (agent === selfId) {
          const selfResult = await generateSelfResponse(revisePrompt, context);
          revised = selfResult.response || selfResult.error || '';
        } else {
          revised = await meshCaller.executeA2ACall(
            { agent, prompt: revisePrompt, timeout_ms: timeoutForAgent(agent, timeoutMs), allowDelegation: false },
            {
              depth: context.depth,
              meshChain: [...context.meshChain],
              taskId: context.taskId,
              selfCallDepth: context.selfCallDepth,
              signal: context.signal,
            },
          );
        }
        // Same anti-loop guard as WRITE: only adopt the revision if it's
        // substantive. Bootstrap/echo/error revisions would replace the prior
        // round's good code with noise, then propagate forward.
        const revisedStr = String(revised || '');
        // Classify against the task prompt, not the revision prompt. The latter
        // embeds the author's prior code, so a legitimate decision to keep an
        // already-correct implementation looked like a prompt echo.
        const verdict = revisedStr ? classifySubmission(revisedStr, writePrompt) : 'empty';
        if (verdict === 'ok') {
          submissions[agent] = revisedStr;
          emitDialogue(`revise-${round}`, agent, 'revised', revisedStr);
        } else {
          emitDialogue(`revise-${round}`, agent, 'error', `Revision rejected (${verdict}); keeping prior round code. Raw: ${revisedStr.slice(0, 200)}`);
        }
      }
      phases.push({ phase: `revise-${round}`, durationMs: Date.now() - reviseStart });
      emitDialogue(`revise-${round}`, '*', 'system', `Fase REVISE round ${round} concluída (${Date.now() - reviseStart}ms)`, { durationMs: Date.now() - reviseStart });
    }

    // ---- Phase 4: SYNTHESIZE ----
    context.signal?.throwIfAborted();
    const judgeCandidates = [
      judge,
      ...activeAgents,
    ].filter((agentId, index, arr) => arr.indexOf(agentId) === index);
    const judgeAgent = judgeCandidates.find((agentId) =>
      agentId
      && agentId !== selfId
      && peers[agentId]
      && activeAgents.includes(agentId)
      && !context.meshChain.includes(agentId),
    ) || null;
    const synthJudge = judgeAgent || selfId;
    emitDialogue('synthesize', synthJudge, 'system', `Fase SYNTHESIZE — ${synthJudge} sintetizando solução final`, { judge: synthJudge });

    const synthStart = Date.now();
    const allCode = workingAgents
      .map((a) => {
        const cluster = candidateClusters.find(item => item.representative === a);
        const authors = cluster?.agents?.length > 1 ? ` equivalentAuthors="${cluster.agents.join(',')}"` : '';
        return `<code author="${a}"${authors} truncated="${String(submissions[a] || '').length > CODE_PREVIEW_CHARS}">\n${truncateForPrompt(submissions[a], CODE_PREVIEW_CHARS, `${a} code`)}\n</code>`;
      })
      .join('\n\n');

    const allReviewText = Object.entries(allReviews)
      .map(([reviewer, text]) => reviewBlockForPrompt(reviewer, text))
      .join('\n\n');

    const synthPrompt = `You are a senior engineering lead. Synthesize the best final solution.\n\n## Task\n${taskForPrompt}\n\n## All implementations\n${allCode}\n\n## Reviews\n${allReviewText}\n\nProduce the single best ${language} implementation. Respond ONLY with the final code.`;

    let finalCode;
    if (judgeAgent && judgeAgent !== selfId) {
      finalCode = String(await meshCaller.executeA2ACall(
        { agent: judgeAgent, prompt: synthPrompt, timeout_ms: timeoutForAgent(judgeAgent, timeoutMs), allowDelegation: false },
        {
          depth: context.depth - 1,
          meshChain: [...context.meshChain],
          taskId: context.taskId,
          selfCallDepth: context.selfCallDepth,
          signal: context.signal,
        },
      ) || '');
    } else {
      // Self-judge: actually synthesize using self response
      const selfSynthResult = await generateSelfResponse(synthPrompt, context, timeoutMs);
      finalCode = selfSynthResult.response || submissions[activeAgents[0]] || '';
    }
    phases.push({ phase: 'synthesize', durationMs: Date.now() - synthStart });
    emitDialogue('synthesize', judgeAgent || '*', 'synthesis', finalCode, { durationMs: Date.now() - synthStart });

    // Persist event
    if (meshBus) {
      meshBus.publish({
        taskId: context.taskId,
        type: 'code-ensemble',
        payload: { ensembleId, agents: activeAgents, judge: synthJudge, rounds, language },
      });
    }
    if (meshStore) {
      try {
        meshStore.createEvent(context.taskId, 'code-ensemble', selfId, {
          ensembleId, agents: activeAgents, judge: synthJudge, rounds, language,
          phases: phases.map(p => p.phase),
        });
      } catch (err) {
        console.warn('[mesh-ensemble] Failed to persist code-ensemble event', {
          taskId: context.taskId,
          ensembleId,
          server: selfId,
          error: formatError(err),
        });
      }
    }

    return persistResultContext(buildResult(
      ensembleId,
      task,
      activeAgents,
      finalCode,
      phases,
      rounds,
      synthJudge,
      startTime,
      {
        profile,
        optimization: {
          deduplicate: Boolean(deduplicate),
          earlyExit: unanimousEquivalent,
          originalCandidates: activeAgents.length,
          uniqueCandidates: workingAgents.length,
        },
        candidateClusters: candidateClusters.map(({ representative, agents, hash }) => ({ representative, agents, hash })),
      },
    ));
  }

  /**
   * Generate self response — the orchestrating server also participates.
   */
  async function generateSelfResponse(prompt, context, timeoutMs = DEFAULT_ENSEMBLE_TIMEOUT_MS) {
    const start = Date.now();
    try {
      if (!resolvedSelfUrl) {
        return { agent: selfId, response: null, durationMs: Date.now() - start, error: 'Self URL is not configured' };
      }
      if (context.selfCallDepth >= MAX_SELF_CALL_DEPTH) {
        return { agent: selfId, response: null, durationMs: Date.now() - start, error: `max self-call depth exceeded (${MAX_SELF_CALL_DEPTH})` };
      }
      const response = await meshCaller.executeA2ACall(
        { agent: selfId, prompt, timeout_ms: timeoutMs, allowDelegation: false },
        {
          depth: 1,
          meshChain: [...context.meshChain],
          taskId: context.taskId,
          selfCallDepth: context.selfCallDepth,
          signal: context.signal,
        },
      );
      if (isMeshErrorText(response)) {
        return { agent: selfId, response: null, durationMs: Date.now() - start, error: String(response) };
      }
      return { agent: selfId, response: String(response), durationMs: Date.now() - start, error: null };
    } catch (err) {
      return { agent: selfId, response: null, durationMs: Date.now() - start, error: err.message };
    }
  }

  /**
   * Call all agents in parallel via broadcast, returns structured results.
   */
  async function callAllAgents(agents, prompt, context, timeoutMs = DEFAULT_ENSEMBLE_TIMEOUT_MS) {
    const start = Date.now();
    try {
      const raw = await meshCaller.executeA2ABroadcast(
        { agents, prompt, timeout_ms: timeoutMs },
        {
          depth: context.depth,
          meshChain: [...context.meshChain],
          taskId: context.taskId,
          selfCallDepth: context.selfCallDepth,
          signal: context.signal,
        },
      );
      // If the entire broadcast failed at the mesh layer, raw is a bare error
      // string with no per-agent sections. Surface it as one error per agent so
      // downstream phases don't treat the error message as content.
      if (isMeshErrorText(raw)) {
        return agents.map(a => ({ agent: a, response: null, durationMs: Date.now() - start, error: String(raw).trim() }));
      }
      const sections = String(raw).split('\n\n---\n\n');
      return sections.map(section => {
        const match = section.match(/^\*\*(\w+)\*\*:\s*([\s\S]*)$/);
        if (match) {
          const isError = isMeshErrorText(match[2]);
          return { agent: match[1], response: isError ? null : match[2], durationMs: Date.now() - start, error: isError ? match[2].trim() : null };
        }
        return { agent: 'unknown', response: section, durationMs: Date.now() - start, error: null };
      });
    } catch (err) {
      return agents.map(a => ({ agent: a, response: null, durationMs: Date.now() - start, error: err.message }));
    }
  }

  function buildResult(ensembleId, task, agents, finalCode, phases, rounds, judge, startTime, extra = {}) {
    return {
      ensembleId,
      task: task.slice(0, 5000),
      agents,
      judge,
      rounds,
      finalCode: finalCode || '',
      phases,
      timing: { totalMs: Date.now() - startTime },
      profile: extra.profile || 'custom',
      optimization: extra.optimization || {
        deduplicate: false,
        earlyExit: false,
        originalCandidates: agents.length,
        uniqueCandidates: agents.length,
      },
      ...extra,
    };
  }

  /**
   * Format ensemble result for tool output.
   */
  function formatEnsembleResult(result) {
    const lines = [
      `## Code Ensemble Result`,
      `**Task**: ${result.task}`,
      `**Agents**: ${result.agents.join(', ')}`,
      `**Judge**: ${result.judge}`,
      `**Rounds**: ${result.rounds}`,
      `**Phases**: ${result.phases.map(p => p.phase).join(' → ')}`,
      '',
      '### Final Code',
      result.finalCode || '(no code produced)',
    ];

    const phaseTimings = result.phases.map(p => `${p.phase}: ${p.durationMs}ms`).join(', ');
    lines.push('', `_Timing: ${phaseTimings}, total ${result.timing.totalMs}ms_`);

    return lines.join('\n');
  }

  return { execute, formatEnsembleResult };
}
