// ============================================
// A2A Agent Catalog — single operational source of truth
// ============================================

const entries = {
  codex: {
    id: 'codex',
    port: 3141,
    displayName: 'Codex',
    cliBinary: 'codex',
    route: 'codex',
    provider: 'openai',
    model: 'gpt-5.6-sol',
    modelPolicy: 'fixed',
    reasoningEffort: 'xhigh',
    timeoutCapMs: 1_800_000,
    color: '#fbbf24',
    dotColor: 'amber',
  },
  claude: {
    id: 'claude',
    port: 3142,
    displayName: 'Claude',
    cliBinary: 'claude',
    route: 'claude',
    provider: 'anthropic',
    model: 'claude-opus-5',
    modelPolicy: 'fixed',
    timeoutCapMs: 1_800_000,
    color: '#a78bfa',
    dotColor: 'purple',
  },
  gemini: {
    id: 'gemini',
    port: 3143,
    displayName: 'Gemini',
    cliBinary: 'agy',
    route: 'antigravity',
    provider: 'google',
    model: 'gemini-3.7-flash-high',
    modelPolicy: 'selectable-catalog',
    timeoutCapMs: 1_800_000,
    color: '#60a5fa',
    dotColor: 'blue',
  },
  grok: {
    id: 'grok',
    port: 3144,
    displayName: 'Grok',
    cliBinary: 'cursor-agent',
    route: 'cursor',
    provider: 'xai',
    model: 'cursor-grok-4.6-high',
    modelPolicy: 'selectable-catalog',
    timeoutCapMs: 1_800_000,
    maxCliProcesses: 2,
    routes: Object.freeze({
      cursor: Object.freeze({
        id: 'cursor',
        displayName: 'Cursor CLI',
        cliBinary: 'cursor-agent',
        provider: 'xai',
        model: 'cursor-grok-4.6-high',
        reasoningEffort: 'high',
      }),
      official: Object.freeze({
        id: 'official',
        displayName: 'xAI Grok CLI oficial',
        cliBinary: 'grok',
        provider: 'xai',
        model: 'grok-4.6',
        reasoningEffort: 'xhigh',
      }),
    }),
    color: '#34d399',
    dotColor: 'green',
  },
  glm: {
    id: 'glm',
    port: 3145,
    displayName: 'GLM 5.3',
    cliBinary: 'opencode',
    route: 'opencode',
    provider: 'zai',
    modelVendor: 'zai',
    credentialProvider: 'opencode-go',
    model: 'opencode-go/glm-5.3',
    modelPolicy: 'selectable-catalog',
    reasoningEffort: 'max',
    timeoutCapMs: 1_800_000,
    maxCliProcesses: 1,
    color: '#fb7185',
    dotColor: 'rose',
  },
  deepseek: {
    id: 'deepseek',
    port: 3146,
    displayName: 'DeepSeek V4 Pro',
    cliBinary: 'opencode',
    route: 'opencode',
    provider: 'deepseek',
    modelVendor: 'deepseek',
    credentialProvider: 'opencode-go',
    model: 'opencode-go/deepseek-v4-pro',
    modelPolicy: 'selectable-catalog',
    reasoningEffort: 'max',
    timeoutCapMs: 1_800_000,
    maxCliProcesses: 1,
    color: '#22d3ee',
    dotColor: 'cyan',
  },
  kimi: {
    id: 'kimi',
    port: 3147,
    displayName: 'Kimi K3',
    cliBinary: 'kimi-secure',
    route: 'kimi-code',
    provider: 'opencode-go',
    modelVendor: 'moonshot',
    credentialProvider: 'opencode-go',
    model: 'kimi-code/k3',
    modelPolicy: 'fixed',
    reasoningEffort: 'max',
    timeoutCapMs: 1_800_000,
    maxCliProcesses: 1,
    color: '#c084fc',
    dotColor: 'violet',
  },
  qwen: {
    id: 'qwen',
    port: 3148,
    displayName: 'Qwen 3.8 Max',
    cliBinary: 'opencode',
    route: 'opencode',
    provider: 'alibaba',
    modelVendor: 'alibaba',
    credentialProvider: 'opencode-go',
    model: 'opencode-go/qwen3.8-max',
    modelPolicy: 'selectable-catalog',
    reasoningEffort: 'max',
    timeoutCapMs: 1_800_000,
    maxCliProcesses: 1,
    color: '#f97316',
    dotColor: 'orange',
  },
};

export const AGENT_CATALOG = Object.freeze(Object.fromEntries(
  Object.entries(entries).map(([id, definition]) => [id, Object.freeze({ ...definition })]),
));

export const AGENT_IDS = Object.freeze(Object.keys(AGENT_CATALOG));

export const DEFAULT_PORTS = Object.freeze(Object.fromEntries(
  Object.entries(AGENT_CATALOG).map(([id, definition]) => [id, definition.port]),
));

export function getAgentDefinition(agentId) {
  return AGENT_CATALOG[String(agentId || '').toLowerCase()] || null;
}

export function capTimeoutForAgent(agentId, operation, requestedMs) {
  const definition = getAgentDefinition(agentId);
  if (!definition) return requestedMs;
  const envName = `A2A_${definition.id.toUpperCase()}_${String(operation || 'CALL').toUpperCase()}_TIMEOUT_MS`;
  const configured = Number.parseInt(process.env[envName] || '', 10);
  const cap = Number.isFinite(configured) && configured > 0
    ? configured
    : definition.timeoutCapMs;
  return cap ? Math.min(requestedMs, cap) : requestedMs;
}

export function publicAgentCatalog() {
  return Object.fromEntries(Object.entries(AGENT_CATALOG).map(([id, definition]) => [id, {
    id,
    port: definition.port,
    displayName: definition.displayName,
    cliBinary: definition.cliBinary,
    route: definition.route,
    provider: definition.provider,
    modelVendor: definition.modelVendor,
    credentialProvider: definition.credentialProvider,
    model: definition.model,
    modelPolicy: definition.modelPolicy,
    reasoningEffort: definition.reasoningEffort,
    color: definition.color,
    dotColor: definition.dotColor,
    routes: definition.routes ? Object.values(definition.routes).map((route) => ({ ...route })) : undefined,
  }]));
}
