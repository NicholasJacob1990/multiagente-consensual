const RECOVERABLE_ROLES = new Set([
  'response', 'argument', 'review', 'revised', 'synthesis', 'judge',
]);

function cleanText(value) {
  return typeof value === 'string' ? value : String(value || '');
}

function newestExactPartials(meshStore, taskId) {
  const byAgent = new Map();
  if (typeof meshStore.getPartialSnapshots === 'function') {
    const snapshots = meshStore.getPartialSnapshots(taskId);
    for (const item of snapshots) {
      const text = cleanText(item.text);
      if (!text) continue;
      byAgent.set(cleanText(item.agent) || 'agente-desconhecido', {
        text,
        complete: item.metadata?.complete === true,
      });
    }
  }
  const events = meshStore.getTimeline({
    taskId,
    eventType: 'partial_output',
    limit: 2000,
  });
  for (const event of events) {
    const text = cleanText(event.payload?.text);
    if (!text) continue;
    const agent = cleanText(event.payload?.agent) || 'agente-desconhecido';
    if (!byAgent.has(agent)) byAgent.set(agent, { text, complete: false });
  }
  return byAgent;
}

function reconstructDialogue(meshStore, taskId) {
  const events = [];
  let cursor = 0;
  const maximum = 20_000;
  while (events.length < maximum) {
    const page = meshStore.getTimeline({
      taskId,
      eventType: 'dialogue',
      afterId: cursor,
      order: 'asc',
      limit: Math.min(1000, maximum - events.length),
    });
    if (!Array.isArray(page) || page.length === 0) break;
    events.push(...page);
    cursor = page[page.length - 1].id;
    if (page.length < 1000) break;
  }
  const byAgent = new Map();
  const lastByAgent = new Map();
  for (const event of events) {
    const role = event.payload?.role;
    if (!RECOVERABLE_ROLES.has(role)) continue;
    const text = cleanText(event.payload?.text);
    if (!text) continue;
    const agent = cleanText(event.payload?.agent) || 'agente-desconhecido';
    if (role !== 'response' && lastByAgent.get(agent) === text) continue;
    lastByAgent.set(agent, text);
    const previous = byAgent.get(agent) || '';
    // Streaming response events are deltas and must be concatenated exactly.
    // Deliberative events are complete turns, so retain a visible boundary.
    byAgent.set(agent, role === 'response' ? previous + text : `${previous}${previous ? '\n\n' : ''}${text}`);
  }
  return byAgent;
}

export function recoverPartialArtifacts(meshStore, taskId, {
  description = 'Saída parcial recuperável preservada após falha, cancelamento ou timeout.',
  maxChars = 200_000,
} = {}) {
  if (!meshStore || !taskId) return [];
  try {
    const parts = reconstructDialogue(meshStore, taskId);
    const exact = newestExactPartials(meshStore, taskId);
    for (const [agent, snapshot] of exact) {
      const existing = parts.get(agent) || '';
      if (snapshot.complete && existing) {
        if (!existing.endsWith(snapshot.text)) {
          parts.set(agent, `${existing}\n\n${snapshot.text}`);
        }
      } else {
        parts.set(agent, snapshot.text);
      }
    }
    if (parts.size === 0) return [];
    const entries = [...parts.entries()];
    const separators = Math.max(0, entries.length - 1) * '\n\n---\n\n'.length;
    const headingChars = entries.reduce((sum, [agent]) => sum + `## ${agent}\n\n`.length, 0);
    const available = Math.max(entries.length, maxChars - separators - headingChars);
    const perAgent = Math.max(1, Math.floor(available / entries.length));
    const text = entries
      .map(([agent, content]) => {
        const body = content.length > perAgent ? `…[trecho anterior truncado]\n${content.slice(-perAgent)}` : content;
        return `## ${agent}\n\n${body}`;
      })
      .join('\n\n---\n\n')
      .slice(0, maxChars);
    return [{
      name: 'partial-output.md',
      description,
      parts: [{ type: 'text', text }],
    }];
  } catch {
    return [];
  }
}
