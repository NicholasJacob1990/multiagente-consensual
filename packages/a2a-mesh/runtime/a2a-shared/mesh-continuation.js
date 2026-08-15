// ============================================
// Mesh Continuation — inject prior history when user prompt is a continuation cue
// ============================================
//
// Why: each a2a_task_send is stateless. When the user types "continuem" / "continue"
// at the root of a /broadcast or /consensus, agents have no context. This helper
// detects continuation cues and prefixes a compact summary of recent completed
// tasks pulled from the shared meshStore (SQLite).
//
// Only triggers when:
//   1. prompt matches CONTINUATION_PATTERN (short, near-empty intent)
//   2. callContext.meshChain is empty (root user call, not a sub-call from another op)
//   3. meshStore is available

const CONTINUATION_PATTERN = /^\s*(continuem?|continua|continue|sigam?|prossigam?|prossiga|carry on|keep going|go on)[\s.!?]*$/i;

const DEFAULT_LIMIT = Number.parseInt(process.env.A2A_CONTINUATION_LIMIT ?? '', 10) || 5;
const DEFAULT_ENABLED = process.env.A2A_CONTINUATION_INJECT !== '0';
const MAX_OUTPUT_PREVIEW = 1500;

export function isContinuationPrompt(prompt) {
  if (typeof prompt !== 'string') return false;
  if (prompt.length > 80) return false;
  return CONTINUATION_PATTERN.test(prompt);
}

export function isRootCall(callContext) {
  if (!callContext) return true;
  const chain = callContext.meshChain;
  if (!Array.isArray(chain)) return true;
  return chain.length === 0;
}

function summarizeCompletedTask(task) {
  const when = task.completedAt || task.updatedAt || task.createdAt || '';
  const who = task.originServer || 'unknown';
  const input = (task.inputText || '').slice(0, 200).replace(/\s+/g, ' ').trim();
  const output = (task.outputText || '').slice(0, MAX_OUTPUT_PREVIEW).trim();
  return `### ${when} · ${who}\n**Pedido:** ${input}\n**Resposta:** ${output}`;
}

function formatContextSnapshot(snapshot) {
  if (!snapshot || !snapshot.summary) return null;
  const lines = [
    `### Thread ${snapshot.threadId || 'unknown'} · ${snapshot.mode || 'unknown'}`,
  ];
  if (snapshot.title) lines.push(`**Titulo:** ${snapshot.title}`);
  lines.push(`**Resumo canonico:** ${snapshot.summary}`);
  if (Array.isArray(snapshot.decisions) && snapshot.decisions.length > 0) {
    lines.push(`**Decisoes:**\n${snapshot.decisions.map(d => `- ${d}`).join('\n')}`);
  }
  if (Array.isArray(snapshot.nextSteps) && snapshot.nextSteps.length > 0) {
    lines.push(`**Proximos passos:**\n${snapshot.nextSteps.map(s => `- ${s}`).join('\n')}`);
  }
  if (Array.isArray(snapshot.errors) && snapshot.errors.length > 0) {
    lines.push(`**Erros pendentes:**\n${snapshot.errors.map(e => `- ${e}`).join('\n')}`);
  }
  if (Array.isArray(snapshot.artifacts) && snapshot.artifacts.length > 0) {
    const artifacts = snapshot.artifacts
      .map(a => (typeof a === 'string' ? a : a.path || a.id || JSON.stringify(a)))
      .filter(Boolean);
    if (artifacts.length > 0) lines.push(`**Artefatos:**\n${artifacts.map(a => `- ${a}`).join('\n')}`);
  }
  return lines.join('\n');
}

function fetchLatestSnapshotContext(meshStore, { threadId, mode } = {}) {
  if (!meshStore || typeof meshStore.getLatestContextSnapshot !== 'function') return null;
  try {
    return formatContextSnapshot(meshStore.getLatestContextSnapshot({ threadId, mode }));
  } catch {
    return null;
  }
}

export function fetchRecentContext(meshStore, { limit = DEFAULT_LIMIT, sessionId, originServer } = {}) {
  if (!meshStore || typeof meshStore.listTasks !== 'function') return null;
  const filter = { state: 'completed', limit };
  if (sessionId) filter.sessionId = sessionId;
  if (originServer) filter.originServer = originServer;
  let tasks;
  try {
    tasks = meshStore.listTasks(filter);
  } catch {
    return null;
  }
  if (!tasks || tasks.length === 0) return null;
  const useful = tasks.filter(t => t.outputText && t.outputText.length > 0).slice(0, limit);
  if (useful.length === 0) return null;
  return useful.map(summarizeCompletedTask).join('\n\n---\n\n');
}

export function enrichPromptIfContinuation(prompt, callContext, meshStore, { limit, sessionId, originServer } = {}) {
  if (!DEFAULT_ENABLED) return { prompt, enriched: false };
  if (!isContinuationPrompt(prompt)) return { prompt, enriched: false };
  if (!isRootCall(callContext)) return { prompt, enriched: false };
  const context = fetchLatestSnapshotContext(meshStore, {
    threadId: callContext?.threadId || callContext?.thread_id || sessionId,
  }) || fetchRecentContext(meshStore, { limit, sessionId, originServer });
  if (!context) return { prompt, enriched: false };

  const enrichedPrompt = [
    '<prior_context note="Histórico recente do mesh A2A — sessão atual stateless. Use isto para retomar com contexto.">',
    context,
    '</prior_context>',
    '',
    `Continuação solicitada pelo usuário ("${prompt.trim()}"). Retome o trabalho anterior com base no contexto acima.`,
  ].join('\n');

  return { prompt: enrichedPrompt, enriched: true };
}
