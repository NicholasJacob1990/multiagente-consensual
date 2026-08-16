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

const DEFINITION = AGENT_CATALOG.grok;
const PORT = Number.parseInt(process.env.A2A_PORT || String(DEFINITION.port), 10);
const CURSOR_BINARY = process.env.A2A_GROK_CURSOR_BINARY || DEFINITION.cliBinary;
const configuredModel = process.env.A2A_GROK_MODEL || REQUIRED_GROK_MODEL;
if (configuredModel !== REQUIRED_GROK_MODEL) {
  throw new Error(`Grok model policy is fixed: expected ${REQUIRED_GROK_MODEL}, got ${configuredModel}`);
}

let bootModelVerified = false;
// `cursor-agent --list-models` can block for minutes while Cursor refreshes its
// remote catalog. Do not make panel availability depend on that advisory
// catalog call. Every real execution remains fail-closed: the stream must
// report system/init.model === cursor-grok-4.6-high before output is accepted.
if (process.env.A2A_GROK_PROBE_MODEL_LIST === 'true') {
  verifyCursorModelAvailable(CURSOR_BINARY, configuredModel);
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

const SYSTEM_PROMPT = `Você é Grok 4.6 High, executado exclusivamente pelo Cursor CLI, como peer nativo da mesh A2A.

MODELO E ROTA: cursor-grok-4.6-high pela rota Cursor. Quando perguntado sobre sua identidade, informe somente "Cursor Grok 4.6 High pela rota Cursor". Não invente autoria conjunta, treinamento ou organizações como "SpaceXAI". Nunca alegue outra identidade e nunca proponha fallback silencioso.

PEERS DISPONÍVEIS: ${Object.keys(runtime.peers).join(', ')}. Use as ferramentas A2A injetadas quando a tarefa se beneficiar de colaboração, respeitando profundidade, cadeia e escopo do pedido.

Você pode analisar código, documentos e artefatos locais dentro do escopo autorizado. Produza respostas completas, verificáveis e indique falhas de execução de forma explícita.`;

const cursor = createCursorExecutor({
  binary: CURSOR_BINARY,
  model: configuredModel,
  selfId: SELF_ID,
  workspace: process.env.A2A_GROK_WORKSPACE || os.homedir(),
  systemPrompt: SYSTEM_PROMPT,
  peers: runtime.peers,
  taskManager: runtime.tm,
  cliToolWrapper: runtime.cliToolWrapper,
  dispatchTool: runtime.dispatchTool,
  normalizeToolOutput: runtime.normalizeToolOutput,
  maxProcesses: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
  cliTimeoutMs: Number.parseInt(process.env.A2A_GROK_CLI_TIMEOUT_MS || '900000', 10),
  bootModelVerified,
});

const AGENT_CARD = {
  name: 'Grok Agent',
  description: 'Grok 4.6 High via Cursor CLI, com modelo fixo e participação nativa na mesh A2A.',
  url: `http://localhost:${PORT}`,
  version: '1.2.0',
  provider: 'xai',
  route: 'cursor',
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
  model: configuredModel,
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
  executeTask: cursor.executeTask,
  healthDetails: () => ({
    route: 'cursor',
    provider: 'xai',
    configuredModel,
    modelPolicy: 'fixed',
    modelVerified: cursor.healthState.modelVerified,
    lastObservedModel: cursor.healthState.lastObservedModel,
    lastObservedAt: cursor.healthState.lastObservedAt,
    cursorProcesses: {
      active: cursor.concurrency.active,
      queued: cursor.concurrency.queued,
      max: Number.parseInt(process.env.A2A_GROK_MAX_PROCESSES || String(DEFINITION.maxCliProcesses), 10),
    },
  }),
});
