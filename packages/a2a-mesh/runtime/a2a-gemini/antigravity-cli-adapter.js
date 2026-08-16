import { spawnSync } from 'node:child_process';

export const REQUIRED_ANTIGRAVITY_MODEL = 'gemini-3.7-flash-high';

function normalizeModelLabel(value) {
  return String(value || '').toLowerCase().replace(/[^a-z0-9]+/g, '');
}

export function antigravityModelLabelsMatch(configuredModel, observedModel) {
  const configured = normalizeModelLabel(configuredModel);
  const observed = normalizeModelLabel(observedModel);
  return Boolean(configured && observed && (configured === observed || observed.includes(configured) || configured.includes(observed)));
}

export function parseAntigravityModels(output) {
  return String(output || '')
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => /^[-a-z0-9.]+\s+/i.test(line))
    .map((line) => line.split(/\s+/)[0])
    .filter(Boolean);
}

export function verifyAntigravityModelAvailable(binary, model = REQUIRED_ANTIGRAVITY_MODEL, { timeoutMs = 30_000 } = {}) {
  const result = spawnSync(binary, ['models'], {
    encoding: 'utf8',
    timeout: timeoutMs,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  if (result.error) throw new Error(`Antigravity model probe failed: ${result.error.message}`);
  if (result.status !== 0) {
    throw new Error(`agy models failed (${result.status}): ${(result.stderr || result.stdout || '').trim()}`);
  }
  const models = parseAntigravityModels(result.stdout);
  if (!models.includes(model)) throw new Error(`required Antigravity model is unavailable: ${model}`);
  return { verified: true, model, availableModels: models };
}

export function parseAntigravityStreamLine(line) {
  let event;
  try { event = JSON.parse(String(line || '').trim()); } catch { return null; }
  if (event?.event === 'init') {
    return {
      event: 'init',
      model: event.init?.model || null,
      conversationId: event.conversation_id || null,
    };
  }
  if (event?.event === 'step_update') {
    return {
      event: 'step_update',
      text: typeof event.step_update?.text_delta === 'string' ? event.step_update.text_delta : '',
      state: event.step_update?.state || null,
      stepType: event.step_update?.step_type || null,
      usage: event.step_update?.usage || null,
    };
  }
  if (event?.event === 'result') {
    return {
      event: 'result',
      terminal: true,
      isError: event.result?.status !== 'SUCCESS',
      response: typeof event.result?.response === 'string' ? event.result.response : '',
      conversationId: event.result?.conversation_id || null,
      usage: event.result?.usage || null,
      status: event.result?.status || null,
    };
  }
  return { event: event?.event || 'unknown' };
}
