#!/usr/bin/env node

import 'dotenv/config';
import os from 'node:os';

import { createA2AServer } from '../a2a-shared/base-server.js';
import { createSharedRuntime } from '../a2a-shared/server-runtime.js';
import { loadA2AAuthToken } from '../a2a-shared/auth-token.js';
import { AGENT_CATALOG } from '../a2a-shared/agent-catalog.js';
import {
  REQUIRED_GROK_MODEL,
  createCursorExecutor,
  verifyCursorModelAvailable,
} from './cursor-cli-adapter.js';
import {
  OFFICIAL_GROK_MODEL,
  OFFICIAL_GROK_REASONING_EFFORT,
  createOfficialGrokExecutor,
  probeOfficialGrok,
} from './official-cli-adapter.js';

const DEFINITION = AGENT_CATALOG.grok;
const PORT = Number.parseInt(process.env.A2A_PORT || String(DEFINITION.port), 10);
const CURSOR_BINARY = process.env.A2A_GROK_CURSOR_BINARY || DEFINITION.cliBinary;
const OFFICIAL_BINARY = process.env.A2A_GROK_OFFICIAL_BINARY || 'grok';
const cursorModel = process.env.A2A_GROK_MODEL || REQUIRED_GROK_MODEL;
const officialModel = process.env.A2A_GROK_OFFICIAL_MODEL || OFFICIAL_GROK_MODEL;
const officialReasoningEffort = process.env.A2A_GROK_OFFICIAL_REASONING_EFFORT || OFFICIAL_GROK_REASONING_EFFORT;
if (officialModel !== OFFICIAL_GROK_MODEL) {
  throw new Error(`Official Grok model policy is fixed: expected ${OFFICIAL_GROK_MODEL}, got ${officialModel}`);
}
let activeRoute = process.env.A2A_GROK_ROUTE || 'cursor';
if (!['cursor', 'official'].includes(activeRoute)) activeRoute = 'cursor';

let bootModelVerified = false;
let cursorAvailableModels = [cursorModel];
let cursorCatalogLastAt = null;
let cursorCatalogError = null;
// `cursor-agent --list-models` can block for minutes while Cursor refreshes its
// remote catalog. Do not make panel availability depend on that advisory
// catalog call. Every real execution remains fail-closed: the stream must
// report system/init.model === cursor-grok-4.6-high before output is accepted.
if (process.env.A2A_GROK_PROBE_MODEL_LIST === 'true') {
  const probe = verifyCursorModelAvailable(CURSOR_BINARY, cursorModel);
  cursorAvailableModels = probe.availableModels;
  cursorCatalogLastAt = new Date().toISOString();
  bootModelVerified = true;
}

const A2A_AUTH_TOKEN = loadA2AAuthToken();
const MAX_CONCURRENT_TASKS = Number.parseInt(process.env.MAX_CONCURRENT_TASKS || '15', 10);
const MAX_TASKS = Number.parseInt(process.env.MAX_TASKS || '200', 10);
const A2A_MESH_MAX_DEPTH = Number.parseInt(process.env.A2A_MESH_MAX_DEPTH || '7', 10);
const SELF_ID = 'grok';

const runtime = await createSharedRuntime({
  selfId: SELF_ID,
  authToken: A2A_AUTH_TOKEN,
  maxDepth: A2A_MESH_MAX_DEPTH,
  maxTasks: MAX_TASKS,
  maxConcurrent: MAX_CONCURRENT_TASKS,
  dataDir: process.env.A2A_GROK_DATA_DIR,
});

const CURSOR_SYSTEM_PROMPT = (activeModel) => `Você é um agente executado pelo Cursor CLI como peer nativo da mesh A2A.

MODELO E ROTA: ${activeModel} pela rota Cursor. Quando perguntado sobre sua identidade, informe esse modelo e a rota Cursor exatamente como configurados. Não invente autoria conjunta, treinamento ou organizações. Nunca alegue outra identidade e nunca proponha fallback silencioso.

PEERS DISPONÍVEIS: ${Object.keys(runtime.peers).join(', ')}. Use as ferramentas A2A injetadas quando a tarefa se beneficiar de colaboração, respeitando profundidade, cadeia e escopo do pedido.

Você pode analisar código, documentos e artefatos locais dentro do escopo autorizado. Produza respostas completas, verificáveis e indique falhas de execução de forma explícita.`;

const OFFICIAL_SYSTEM_PROMPT = `Você é Grok 4.6, executado pela CLI oficial da xAI, como peer nativo da mesh A2A.

MODELO E ROTA: grok-4.6 pela CLI oficial da xAI, com esforço ${officialReasoningEffort}. Quando perguntado sobre sua identidade, informe somente "Grok 4.6 pela CLI oficial da xAI". Nunca alegue a rota Cursor e nunca proponha fallback silencioso.

PEERS DISPONÍVEIS: ${Object.keys(runtime.peers).join(', ')}. Use as ferramentas A2A injetadas quando a tarefa se beneficiar de colaboração, respeitando profundidade, cadeia e escopo do pedido.

Você pode analisar código, documentos e artefatos locais dentro do escopo autorizado. Produza respostas completas, verificáveis e indique falhas de execução de forma explícita.`;

const cursor = createCursorExecutor({
  binary: CURSOR_BINARY,
  model: cursorModel,
  selfId: SELF_ID,
  workspace: process.env.A2A_GROK_WORKSPACE || os.homedir(),
  systemPrompt: CURSOR_SYSTEM_PROMPT,
  peers: runtime.peers,
  taskManager: runtime.tm,
  cliToolWrapper: runtime.cliToolWrapper,
  dispatchTool: runtime.dispatchTool,
  normalizeToolOutput: runtime.normalizeToolOutput,
  maxProcesses: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
  cliTimeoutMs: Number.parseInt(process.env.A2A_GROK_CLI_TIMEOUT_MS || '900000', 10),
  bootModelVerified,
});

const officialProbe = probeOfficialGrok(OFFICIAL_BINARY, officialModel);
const official = createOfficialGrokExecutor({
  binary: OFFICIAL_BINARY,
  model: officialModel,
  reasoningEffort: officialReasoningEffort,
  selfId: SELF_ID,
  workspace: process.env.A2A_GROK_WORKSPACE || os.homedir(),
  systemPrompt: OFFICIAL_SYSTEM_PROMPT,
  peers: runtime.peers,
  taskManager: runtime.tm,
  cliToolWrapper: runtime.cliToolWrapper,
  dispatchTool: runtime.dispatchTool,
  normalizeToolOutput: runtime.normalizeToolOutput,
  maxProcesses: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
  cliTimeoutMs: Number.parseInt(process.env.A2A_GROK_CLI_TIMEOUT_MS || '900000', 10),
  initialProbe: officialProbe,
});

function activeExecutor() {
  return activeRoute === 'official' ? official : cursor;
}

function refreshCursorCatalog() {
  try {
    const probe = verifyCursorModelAvailable(CURSOR_BINARY, cursor.configuredModel, { timeoutMs: 30_000 });
    cursorAvailableModels = probe.availableModels;
    cursorCatalogLastAt = new Date().toISOString();
    cursorCatalogError = null;
    return probe;
  } catch (error) {
    cursorCatalogError = error.message;
    throw error;
  }
}

function cursorReasoningEffort(model = cursor.configuredModel) {
  return String(model).match(/-(none|low|medium|high|xhigh|max)(?:-fast)?$/i)?.[1]?.toLowerCase()
    || DEFINITION.routes.cursor.reasoningEffort;
}

function cursorModelProvider(model = cursor.configuredModel) {
  const value = String(model).toLowerCase();
  if (value.startsWith('claude-')) return 'anthropic';
  if (value.startsWith('gpt-')) return 'openai';
  if (value.startsWith('gemini-')) return 'google';
  if (value.startsWith('kimi-')) return 'moonshot';
  if (value.startsWith('glm-')) return 'zai';
  return 'xai';
}

function routeConfiguration({ refreshCatalog = false } = {}) {
  if (
    refreshCatalog
    && activeRoute === 'cursor'
    && cursor.concurrency.active === 0
    && cursor.concurrency.queued === 0
  ) refreshCursorCatalog();
  const executor = activeExecutor();
  const route = DEFINITION.routes[activeRoute];
  const configuredModel = activeRoute === 'cursor' ? cursor.configuredModel : officialModel;
  return {
    route: activeRoute,
    cliBinary: route.cliBinary,
    configuredModel,
    reasoningEffort: activeRoute === 'cursor' ? cursorReasoningEffort(configuredModel) : route.reasoningEffort,
    provider: activeRoute === 'cursor' ? cursorModelProvider(configuredModel) : route.provider,
    supportedRoutes: Object.values(DEFINITION.routes).map((item) => ({
      ...item,
      model: item.id === 'cursor' ? cursor.configuredModel : item.model,
    })),
    availableModels: activeRoute === 'cursor' ? cursorAvailableModels : [officialModel],
    configurableModels: activeRoute === 'cursor',
    authenticated: activeRoute === 'official' ? executor.healthState.authenticated : true,
    modelAvailable: activeRoute === 'official' ? executor.healthState.modelAvailable : true,
    catalogLastAt: activeRoute === 'cursor' ? cursorCatalogLastAt : executor.healthState.lastProbeAt,
    catalogError: activeRoute === 'cursor' ? cursorCatalogError : executor.healthState.lastProbeError,
  };
}

function updateRouteConfiguration(update = {}) {
  const current = activeExecutor();
  if (current.concurrency.active > 0 || current.concurrency.queued > 0) {
    throw new Error('Aguarde as tarefas do Grok terminarem antes de trocar rota ou modelo.');
  }
  const route = String(update.route || activeRoute).toLowerCase();
  if (!DEFINITION.routes[route]) {
    throw new Error(`Rota Grok inválida: ${route || '(vazia)'}. Use cursor ou official.`);
  }
  activeRoute = route;
  if (activeRoute === 'official') {
    if (update.model && update.model !== officialModel) {
      throw new Error(`A rota oficial está fixada em ${officialModel}.`);
    }
    official.refreshProbe();
  } else if (update.model) {
    const requestedModel = String(update.model).trim();
    const probe = verifyCursorModelAvailable(CURSOR_BINARY, requestedModel, { timeoutMs: 30_000 });
    cursorAvailableModels = probe.availableModels;
    cursorCatalogLastAt = new Date().toISOString();
    cursorCatalogError = null;
    cursor.updateModel(requestedModel, { verified: probe.verified });
  } else if (update.refreshCatalog === true) {
    refreshCursorCatalog();
  }
  const configuration = routeConfiguration();
  return {
    ...configuration,
    warning: activeRoute === 'official' && !configuration.authenticated
      ? 'CLI oficial não autenticada. Execute `grok login` antes de enviar tarefas.'
      : null,
  };
}

const AGENT_CARD = {
  name: 'Grok Agent',
  description: 'Grok via Cursor CLI ou CLI oficial da xAI, com rota explícita e participação nativa na mesh A2A.',
  url: `http://localhost:${PORT}`,
  version: '1.4.0',
  provider: 'xai',
  route: activeRoute,
  supportedRoutes: Object.values(DEFINITION.routes).map((item) => ({ ...item })),
  capabilities: {
    streaming: true,
    pushNotifications: true,
    stateTransitionHistory: true,
  },
  skills: [
    { id: 'adversarial-review', name: 'Revisão adversarial', description: 'Procura falhas, riscos e pressupostos frágeis.', tags: ['review', 'adversarial'] },
    { id: 'code-analysis', name: 'Análise de código', description: 'Analisa, depura e propõe mudanças em código.', tags: ['code', 'debug'] },
    { id: 'reasoning', name: 'Raciocínio', description: 'Avalia problemas complexos e trade-offs.', tags: ['reasoning', 'analysis'] },
    { id: 'general', name: 'Tarefas gerais', description: 'Executa tarefas gerais dentro do escopo autorizado.', tags: ['general'] },
  ],
  defaultInputModes: ['text'],
  defaultOutputModes: ['text'],
};

createA2AServer({
  port: PORT,
  selfId: SELF_ID,
  model: cursorModel,
  useApi: false,
  authToken: A2A_AUTH_TOKEN,
  taskTimeoutMs: 2700000,
  agentCard: AGENT_CARD,
  peers: runtime.peers,
  maxDepth: A2A_MESH_MAX_DEPTH,
  taskManager: runtime.tm,
  meshCaller: runtime.meshCaller,
  meshStore: runtime.meshStore,
  meshBus: runtime.meshBus,
  peerDiscovery: runtime.peerDiscovery,
  teamExecutor: runtime.teamExecutor,
  consensusExecutor: runtime.consensusExecutor,
  ensembleExecutor: runtime.codeEnsembleExecutor,
  debateExecutor: runtime.debateExecutor,
  planExecutor: runtime.planExecutor,
  executeTask: (task, onChunk, runContext) => activeExecutor().executeTask(task, onChunk, runContext),
  runtimeConfigDetails: () => routeConfiguration({ refreshCatalog: true }),
  updateRuntimeConfig: updateRouteConfiguration,
  healthDetails: () => {
    const executor = activeExecutor();
    const configuration = routeConfiguration();
    return {
      ...configuration,
      model: configuration.configuredModel,
      modelPolicy: activeRoute === 'cursor' ? 'selectable-catalog' : 'fixed-per-route',
      modelVerified: executor.healthState.modelVerified,
      lastObservedModel: executor.healthState.lastObservedModel,
      lastObservedAt: executor.healthState.lastObservedAt,
      lastProbeAt: executor.healthState.lastProbeAt || null,
      lastProbeError: executor.healthState.lastProbeError || null,
      cliProcesses: {
        active: executor.concurrency.active,
        queued: executor.concurrency.queued,
        max: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
      },
      cursorProcesses: {
        active: cursor.concurrency.active,
        queued: cursor.concurrency.queued,
        max: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
      },
      officialProcesses: {
        active: official.concurrency.active,
        queued: official.concurrency.queued,
        max: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
      },
    };
  },
});
