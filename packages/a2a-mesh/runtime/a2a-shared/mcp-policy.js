export const MAX_MCP_WAIT_MS = 240_000;

export function clampMcpWaitMs(value) {
  const parsed = Number.parseInt(String(value), 10);
  return Math.min(MAX_MCP_WAIT_MS, Math.max(0, Number.isFinite(parsed) ? parsed : 0));
}
