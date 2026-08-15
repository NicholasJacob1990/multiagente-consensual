// ============================================
// Mesh Debate — Multi-agent adversarial debate
// ============================================

import { randomUUID } from 'crypto';
import { resolveSelfUrl } from './peer-registry.js';
import { persistContextSnapshot, resolveThreadId } from './mesh-context.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';
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

const DEBATE_HISTORY_ENTRY_CHARS = normalizePositiveInt(process.env.A2A_DEBATE_HISTORY_ENTRY_CHARS, 4000);
const DEBATE_JUDGE_ENTRY_CHARS = normalizePositiveInt(process.env.A2A_DEBATE_JUDGE_ENTRY_CHARS, 6000);
const DEBATE_JUDGE_MAX_ENTRIES = normalizePositiveInt(process.env.A2A_DEBATE_JUDGE_MAX_ENTRIES, 24);
const GEMINI_DEBATE_TIMEOUT_MS = normalizePositiveInt(process.env.A2A_GEMINI_DEBATE_TIMEOUT_MS, 900000);

function truncateForPrompt(text, limit, label = 'content') {
  const value = String(text || '');
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n\n[TRUNCATED ${value.length - limit} chars from ${label}.]`;
}

function timeoutForAgent(agent, timeoutMs) {
  return agent === 'gemini' ? Math.min(timeoutMs, GEMINI_DEBATE_TIMEOUT_MS) : timeoutMs;
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
 * Create a debate executor.
 *
 * @param {Object} config
 * @param {Object} config.meshCaller - createMeshCaller instance
 * @param {Object} config.peers - { agentId: url }
 * @param {string} config.selfId - This server's ID
 * @param {number} config.maxDepth - Max mesh depth
 * @param {Object} [config.meshStore] - MeshStore (optional)
 * @param {Object} [config.meshBus] - MeshEventBus (optional)
 */
export function createDebateExecutor({ meshCaller, peers, selfId, maxDepth, meshStore, meshBus, authToken = '', selfUrl = '' }) {
  const resolvedSelfUrl = selfUrl || resolveSelfUrl({ selfId, peers });
  const DEFAULT_DEBATE_TIMEOUT_MS = normalizePositiveInt(process.env.A2A_TIMEOUT_DEBATE_MS, 2400000); // 40 min

  /**
   * Execute a multi-agent debate.
   *
   * @param {Object} params
   * @param {string} params.topic - The debate topic
   * @param {number} [params.rounds=4] - Number of debate rounds
   * @param {string[]} [params.agents] - Agents to participate (default: all peers + self)
   * @param {string} [params.judge] - Judge agent (default: 'claude')
   * @param {string} [params.order] - Agent order strategy: 'rotate' or 'fixed'
   */
  async function execute(params, callContext = {}) {
    const { topic, rounds: rawRounds = 4, judge = 'claude', order = 'rotate', timeout_ms } = params;
    const rounds = Math.max(1, Math.min(36, parseInt(rawRounds, 10) || 4));
    const debateId = randomUUID();
    const threadId = resolveThreadId(params, callContext, `debate-${debateId}`);
    const timeoutMs = normalizeTimeoutMs(timeout_ms, DEFAULT_DEBATE_TIMEOUT_MS);
    const parentDepth = normalizePositiveInt(callContext.depth, maxDepth);
    const parentChain = normalizeMeshChain(callContext.meshChain);
    const parentSelfCallDepth = normalizePositiveInt(callContext.selfCallDepth, 0);
    const { prompt: topicForPrompt } = enrichPromptIfContinuation(topic, { meshChain: parentChain, threadId }, meshStore);

    // Determine participants: requested agents, or all available (peers + self)
    const allAvailable = [...Object.keys(peers), selfId];
    const requestedAgents = params.agents?.filter(a => allAvailable.includes(a));
    const agents = (requestedAgents?.length ? requestedAgents : allAvailable)
      .filter(agent => agent === selfId || !parentChain.includes(agent));

    if (agents.length < 2) throw new Error('Debate requires at least 2 agents');

    const context = {
      depth: parentDepth - 1,
      meshChain: [...parentChain],
      taskId: `debate-${debateId}`,
      timeoutMs,
      selfCallDepth: parentSelfCallDepth,
    };

    const emitDialogue = (phase, agent, role, text, extra = {}) => {
      if (!meshBus) return;
      meshBus.publish({
        taskId: context.taskId,
        type: 'dialogue',
        payload: { operation: 'debate', phase, agent, role, text: String(text).slice(0, 100000), ...extra },
      });
    };

    // Setup
    emitDialogue('setup', '*', 'system', `Debate iniciado: "${topic}" | ${rounds} rounds | Debatedores: ${agents.join(', ')} | Juiz: ${judge}`);
    const startTime = Date.now();
    const history = [];

    // Debate rounds
    for (let round = 1; round <= rounds; round++) {
      // Rotate order each round to avoid first-mover advantage
      const agentOrder = order === 'rotate'
        ? [...agents.slice((round - 1) % agents.length), ...agents.slice(0, (round - 1) % agents.length)]
        : agents;

      emitDialogue(`round-${round}`, '*', 'system', `Rodada ${round}/${rounds} — Ordem: ${agentOrder.join(' → ')}`);

      for (const agent of agentOrder) {
        const prompt = buildDebaterPrompt(topicForPrompt, history, agent, round, rounds, agents);
        let response;

        emitDialogue(`round-${round}`, '*', 'system', `${agent} elaborando argumento…`);

        try {
          if (agent === selfId) {
            // Generate self response by calling own URL
            response = await meshCaller.executeA2ACall(
              { agent: selfId, prompt, timeout_ms: timeoutForAgent(selfId, timeoutMs) },
              {
                depth: context.depth - 1,
                meshChain: [...context.meshChain],
                taskId: context.taskId,
                selfCallDepth: context.selfCallDepth,
              },
            );
          } else if (peers[agent]) {
            response = await meshCaller.executeA2ACall(
              { agent, prompt, timeout_ms: timeoutForAgent(agent, timeoutMs) },
              {
                depth: context.depth - 1,
                meshChain: [...context.meshChain],
                taskId: context.taskId,
                selfCallDepth: context.selfCallDepth,
              },
            );
          } else {
            response = `[${agent} indisponível]`;
          }
        } catch (err) {
          response = `[Erro de ${agent}: ${formatError(err)}]`;
          emitDialogue(`round-${round}`, agent, 'error', formatError(err));
        }

        // executeA2ACall returns string errors instead of throwing; convert
        // them to the same '[Erro de X: ...]' shape so the debate history
        // doesn't treat error text as a real argument.
        if (isMeshErrorText(response)) {
          const errText = String(response).trim();
          emitDialogue(`round-${round}`, agent, 'error', errText);
          response = `[Erro de ${agent}: ${errText}]`;
        }

        const entry = { round, agent, argument: String(response) };
        history.push(entry);
        emitDialogue(`round-${round}`, agent, 'argument', entry.argument, { round });
      }
    }

    const debateDurationMs = Date.now() - startTime;
    emitDialogue('debate-end', '*', 'system', `Debate concluído em ${debateDurationMs}ms. Enviando para juiz: ${judge}`);

    // Judge phase
    const judgeStartTime = Date.now();

    const judgeCandidates = [
      judge,
      ...agents,
    ].filter((agentId, index, arr) => arr.indexOf(agentId) === index);
    const actualJudge = judgeCandidates.find((agentId) =>
      agentId
      && agentId !== selfId
      && peers[agentId]
      && !context.meshChain.includes(agentId),
    ) || selfId;

    emitDialogue('judge', actualJudge, 'system', `Juiz ${actualJudge} analisando o debate...`);

    const judgePrompt = buildJudgePrompt(topicForPrompt, history, agents, rounds);
    let synthesis;

    try {
      let judgeResponse;
      if (actualJudge === selfId) {
        judgeResponse = await meshCaller.executeA2ACall(
          { agent: selfId, prompt: judgePrompt, timeout_ms: timeoutForAgent(selfId, timeoutMs) },
          {
            depth: context.depth - 1,
            meshChain: [...context.meshChain],
            taskId: context.taskId,
            selfCallDepth: context.selfCallDepth,
          },
        );
      } else if (peers[actualJudge]) {
        judgeResponse = await meshCaller.executeA2ACall(
          { agent: actualJudge, prompt: judgePrompt, timeout_ms: timeoutForAgent(actualJudge, timeoutMs) },
          {
            depth: context.depth - 1,
            meshChain: [...context.meshChain],
            taskId: context.taskId,
            selfCallDepth: context.selfCallDepth,
          },
        );
      } else {
        judgeResponse = buildFallbackSynthesis(history, agents);
      }
      synthesis = parseJudgeResponse(judgeResponse, history, agents);
    } catch (err) {
      synthesis = buildFallbackSynthesis(history, agents);
      emitDialogue('judge', actualJudge, 'error', formatError(err));
    }

    const judgeDurationMs = Date.now() - judgeStartTime;
    emitDialogue('judge', actualJudge, 'synthesis', synthesis.verdict || synthesis.summary, {
      winner: synthesis.winner,
      scores: synthesis.scores,
      confidence: synthesis.confidence,
    });

    const result = {
      debateId,
      topic,
      agents,
      judge: actualJudge,
      rounds,
      history,
      synthesis,
      timing: {
        debateDurationMs,
        judgeDurationMs,
        totalMs: Date.now() - startTime,
      },
    };

    // Persist event
    if (meshBus) {
      meshBus.publish({
        taskId: context.taskId,
        type: 'debate',
        payload: {
          debateId,
          topic: topic.slice(0, 5000),
          agents,
          judge: actualJudge,
          rounds,
          winner: synthesis.winner,
          scores: synthesis.scores,
        },
      });
    }

    if (meshStore) {
      try {
        meshStore.createEvent(context.taskId, 'debate', selfId, {
          debateId, agents, judge: actualJudge, rounds,
          winner: synthesis.winner,
          scores: synthesis.scores,
          topic: topic.slice(0, 5000),
        });
      } catch (err) {
        console.warn('[debate] Failed to persist event:', formatError(err));
      }
    }

    persistContextSnapshot(meshStore, {
      threadId,
      taskId: context.taskId,
      mode: 'debate',
      title: topic,
      summary: synthesis.verdict || synthesis.summary || 'Debate completed without verdict text.',
      decisions: [`winner=${synthesis.winner || 'indeterminado'}; confidence=${synthesis.confidence ?? 0}`],
      nextSteps: ['Use the verdict and strongest objections as context for the next mesh mode.'],
      artifacts: [{ kind: 'debate_history', field: 'history' }],
      metadata: {
        debateId,
        agents,
        judge: actualJudge,
        rounds,
        winner: synthesis.winner,
        scores: synthesis.scores,
        confidence: synthesis.confidence,
      },
    }, '[mesh-debate]');

    return result;
  }

  function buildDebaterPrompt(topic, history, agent, round, totalRounds, allAgents) {
    const others = allAgents.filter(a => a !== agent).join(', ');
    let prompt = `Você está em um debate técnico adversarial. Seu papel é defender sua posição com argumentos fortes e contestar os oponentes.

TÓPICO: ${topic}
VOCÊ É: ${agent}
SEUS OPONENTES: ${others}
RODADA: ${round}/${totalRounds}

REGRAS:
- Argumento conciso (máx 20 linhas)
- Responda DIRETAMENTE aos pontos dos oponentes
- Use evidências técnicas concretas
- Aponte falhas nos argumentos alheios
- Defenda sua posição com convicção`;

    if (history.length > 0) {
      prompt += '\n\nHISTÓRICO DO DEBATE:\n';
      // Show recent history (last N entries to avoid context overflow)
      const recentHistory = history.slice(-15);
      for (const h of recentHistory) {
        const marker = h.agent === agent ? '[VOCÊ]' : `[${h.agent.toUpperCase()}]`;
        // Truncate individual arguments to keep context manageable
        const arg = truncateForPrompt(h.argument, DEBATE_HISTORY_ENTRY_CHARS, `${h.agent} debate argument`);
        prompt += `\nRodada ${h.round} — ${marker}:\n${arg}\n`;
      }
      prompt += '\n\nAgora apresente seu argumento para esta rodada:';
    } else {
      prompt += '\n\nApresente seu argumento inicial:';
    }

    return prompt;
  }

  function buildJudgePrompt(topic, history, agents, rounds) {
    let prompt = `Você é o juiz de um debate técnico entre ${agents.join(', ')}.

TÓPICO: ${topic}
RODADAS: ${rounds}

DEBATE COMPLETO:\n`;

    const judgeHistory = history.slice(-DEBATE_JUDGE_MAX_ENTRIES);
    if (history.length > judgeHistory.length) {
      prompt += `\n[TRUNCATED ${history.length - judgeHistory.length} older debate entries before judge phase.]\n`;
    }
    for (const h of judgeHistory) {
      prompt += `\n--- Rodada ${h.round} — ${h.agent.toUpperCase()} ---\n${truncateForPrompt(h.argument, DEBATE_JUDGE_ENTRY_CHARS, `${h.agent} judge argument`)}\n`;
    }

    prompt += `\n\nAnalise o debate e responda OBRIGATORIAMENTE em JSON:
\`\`\`json
{
  "winner": "nome_do_agente ou empate",
  "summary": "resumo em 3-5 frases do debate",
  "bestArguments": {"${agents[0]}": "melhor ponto de ${agents[0]}", "${agents[1]}": "melhor ponto de ${agents[1]}"${agents[2] ? `, "${agents[2]}": "melhor ponto de ${agents[2]}"` : ''}},
  "weaknesses": {"${agents[0]}": "ponto fraco", "${agents[1]}": "ponto fraco"${agents[2] ? `, "${agents[2]}": "ponto fraco"` : ''}},
  "verdict": "seu veredito detalhado com justificativa (5-10 linhas)",
  "scores": {"${agents[0]}": 7, "${agents[1]}": 8${agents[2] ? `, "${agents[2]}": 7` : ''}},
  "confidence": 0.85
}
\`\`\``;

    return prompt;
  }

  function parseJudgeResponse(response, history, agents) {
    const text = String(response);
    if (isMeshErrorText(text)) {
      return {
        winner: 'indeterminado',
        summary: `Judge failed: ${text.slice(0, 500)}`,
        bestArguments: {},
        weaknesses: {},
        verdict: `Judge failed: ${text}`,
        scores: Object.fromEntries(agents.map(a => [a, 0])),
        confidence: 0,
      };
    }
    // Try to extract JSON from response
    const jsonMatch = text.match(/```json\s*([\s\S]*?)```/) || text.match(/\{[\s\S]*"winner"[\s\S]*\}/);
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[1] || jsonMatch[0]);
        return {
          winner: parsed.winner || 'empate',
          summary: parsed.summary || text.slice(0, 500),
          bestArguments: parsed.bestArguments || {},
          weaknesses: parsed.weaknesses || {},
          verdict: parsed.verdict || text,
          scores: parsed.scores || {},
          confidence: parsed.confidence || 0.7,
        };
      } catch { /* fall through */ }
    }
    // Fallback: use raw text as verdict
    return {
      winner: 'indeterminado',
      summary: text.slice(0, 500),
      bestArguments: {},
      weaknesses: {},
      verdict: text,
      scores: Object.fromEntries(agents.map(a => [a, 5])),
      confidence: 0.5,
    };
  }

  function buildFallbackSynthesis(history, agents) {
    const argCounts = {};
    for (const h of history) {
      argCounts[h.agent] = (argCounts[h.agent] || 0) + 1;
    }
    return {
      winner: 'indeterminado (juiz indisponível)',
      summary: `Debate com ${history.length} argumentos de ${Object.keys(argCounts).length} agentes. Juiz não disponível.`,
      bestArguments: {},
      weaknesses: {},
      verdict: 'Juiz não conseguiu analisar o debate. Veja os argumentos individuais.',
      scores: Object.fromEntries(agents.map(a => [a, 5])),
      confidence: 0.2,
    };
  }

  function formatDebateResult(result) {
    const lines = [];
    lines.push(`# Debate: ${result.topic}`);
    lines.push(`Debatedores: ${result.agents.join(', ')} | Juiz: ${result.judge} | Rounds: ${result.rounds}`);
    lines.push(`Tempo total: ${(result.timing.totalMs / 1000).toFixed(1)}s\n`);

    for (const h of result.history) {
      lines.push(`## Rodada ${h.round} — ${h.agent.toUpperCase()}`);
      lines.push(h.argument);
      lines.push('');
    }

    lines.push(`## Veredito (${result.judge})`);
    if (result.synthesis.winner) lines.push(`**Vencedor:** ${result.synthesis.winner}`);
    if (result.synthesis.scores) {
      const scoreStr = Object.entries(result.synthesis.scores).map(([a, s]) => `${a}: ${s}/10`).join(', ');
      lines.push(`**Scores:** ${scoreStr}`);
    }
    if (result.synthesis.verdict) lines.push(`\n${result.synthesis.verdict}`);
    if (result.synthesis.confidence) lines.push(`\n*Confiança: ${(result.synthesis.confidence * 100).toFixed(0)}%*`);

    return lines.join('\n');
  }

  return { execute, formatDebateResult };
}
