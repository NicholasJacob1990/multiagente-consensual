import os from 'node:os';

import { createA2AServer } from './base-server.js';
import { createSharedRuntime } from './server-runtime.js';
import { loadA2AAuthToken } from './auth-token.js';
import { AGENT_CATALOG } from './agent-catalog.js';
import { createExternalCliExecutor, verifyOpenCodeModelAvailable } from './external-cli-adapter.js';

export async function startExternalAgentServer(agentId) {
  const definition = AGENT_CATALOG[agentId];
  if (!definition) throw new Error(`Unknown external A2A agent: ${agentId}`);
  const upper = agentId.toUpperCase();
  const port = Number.parseInt(process.env.A2A_PORT || String(definition.port), 10);
  const binary = process.env[`A2A_${upper}_CLI_BINARY`] || definition.cliBinary;
  const configuredModel = process.env[`A2A_${upper}_MODEL`] || definition.model;
  if (configuredModel !== definition.model) {
    throw new Error(`${definition.displayName} model policy is fixed: expected ${definition.model}, got ${configuredModel}`);
  }

  let bootModelVerified = false;
  if (definition.route === 'opencode') {
    verifyOpenCodeModelAvailable(binary, configuredModel);
    bootModelVerified = true;
  }

  const authToken = loadA2AAuthToken();
  const maxDepth = Number.parseInt(process.env.A2A_MESH_MAX_DEPTH || '7', 10);
  const runtime = await createSharedRuntime({
    selfId: agentId,
    authToken,
    maxDepth,
    maxTasks: Number.parseInt(process.env.MAX_TASKS || '200', 10),
    maxConcurrent: Number.parseInt(process.env.MAX_CONCURRENT_TASKS || '15', 10),
    dataDir: process.env[`A2A_${upper}_DATA_DIR`],
  });

  const routeLabel = definition.route === 'opencode' ? 'OpenCode Go' : 'Kimi Code';
  const systemPrompt = `Você é ${definition.displayName}, executado exclusivamente pelo ${routeLabel}, como peer nativo da mesh A2A.

MODELO E ROTA: ${configuredModel} pela rota ${routeLabel}. O modelo é fixo e não admite fallback silencioso. Use esforço máximo disponível para análise, crítica e revisão.

PEERS DISPONÍVEIS: ${Object.keys(runtime.peers).join(', ')}. Use as ferramentas A2A injetadas quando a tarefa se beneficiar de colaboração, respeitando profundidade, cadeia e escopo.

Você pode analisar e, quando autorizado pela tarefa, criar ou alterar código, documentos e artefatos locais. Entregue respostas completas e explicite falhas de execução.`;

  const executor = createExternalCliExecutor({
    binary,
    model: configuredModel,
    route: definition.route,
    selfId: agentId,
    displayName: definition.displayName,
    workspace: process.env[`A2A_${upper}_WORKSPACE`] || os.homedir(),
    systemPrompt,
    peers: runtime.peers,
    taskManager: runtime.tm,
    cliToolWrapper: runtime.cliToolWrapper,
    dispatchTool: runtime.dispatchTool,
    normalizeToolOutput: runtime.normalizeToolOutput,
    maxProcesses: Number.parseInt(process.env[`A2A_${upper}_MAX_PROCESSES`] || String(definition.maxCliProcesses || 1), 10),
    cliTimeoutMs: Number.parseInt(process.env[`A2A_${upper}_CLI_TIMEOUT_MS`] || '1800000', 10),
    bootModelVerified,
  });

  const agentCard = {
    name: `${definition.displayName} Agent`,
    description: `${definition.displayName} via ${routeLabel}, com modelo fixo e participação nativa na mesh A2A.`,
    url: `http://localhost:${port}`,
    version: '1.3.0',
    provider: definition.provider,
    route: definition.route,
    capabilities: { streaming: true, pushNotifications: true, stateTransitionHistory: true },
    skills: [
      { id: 'analysis', name: 'Análise', description: 'Analisa problemas complexos e documentos.', tags: ['analysis'] },
      { id: 'review', name: 'Crítica e revisão', description: 'Avalia riscos, falhas e melhorias.', tags: ['review'] },
      { id: 'code', name: 'Código', description: 'Produz e revisa código e artefatos.', tags: ['code'] },
      { id: 'general', name: 'Tarefas gerais', description: 'Executa tarefas gerais autorizadas.', tags: ['general'] },
    ],
    defaultInputModes: ['text'],
    defaultOutputModes: ['text'],
  };

  return createA2AServer({
    port,
    selfId: agentId,
    model: configuredModel,
    useApi: false,
    authToken,
    taskTimeoutMs: 2_700_000,
    agentCard,
    peers: runtime.peers,
    maxDepth,
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
    executeTask: executor.executeTask,
    healthDetails: () => ({
      route: definition.route,
      provider: definition.provider,
      configuredModel,
      modelPolicy: 'fixed',
      modelVerified: executor.healthState.modelVerified,
      lastObservedModel: executor.healthState.lastObservedModel,
      lastObservedAt: executor.healthState.lastObservedAt,
      lastUsage: executor.healthState.lastUsage,
      lastCost: executor.healthState.lastCost,
      cliProcesses: { active: executor.concurrency.active, queued: executor.concurrency.queued, max: definition.maxCliProcesses || 1 },
    }),
  });
}
