// ============================================
// Mesh Context — canonical thread snapshots
// ============================================

const SNAPSHOT_SUMMARY_CHARS = Number.parseInt(process.env.A2A_CONTEXT_SNAPSHOT_CHARS ?? '', 10) || 6000;

export function truncateContextText(text, limit = SNAPSHOT_SUMMARY_CHARS) {
  const value = String(text || '').trim();
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n\n[TRUNCATED ${value.length - limit} chars from canonical context snapshot.]`;
}

export function resolveThreadId(params = {}, callContext = {}, fallbackId = '') {
  return String(
    params.thread_id
    || params.threadId
    || callContext.thread_id
    || callContext.threadId
    || callContext.sessionId
    || fallbackId
  ).trim();
}

export function persistContextSnapshot(meshStore, snapshot, logPrefix = '[mesh-context]') {
  if (!meshStore || typeof meshStore.createContextSnapshot !== 'function') return null;
  try {
    return meshStore.createContextSnapshot({
      ...snapshot,
      title: truncateContextText(snapshot.title, 240),
      summary: truncateContextText(snapshot.summary),
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    console.warn(`${logPrefix} Failed to persist context snapshot`, { error: message });
    return null;
  }
}
