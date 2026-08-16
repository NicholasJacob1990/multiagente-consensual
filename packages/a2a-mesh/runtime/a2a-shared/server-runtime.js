// ============================================
// Shared Server Runtime — common mesh/task bootstrap for all agents
// ============================================

import { createTaskManager } from './task-manager.js';
import { createToolExecutor } from './local-tools.js';
import { createMeshCaller } from './mesh-calls.js';
import { loadPeerRegistry, resolveSelfUrl, PeerDiscovery } from './peer-registry.js';
import * as cliToolWrapper from './cli-tool-wrapper.js';
import { mergeArtifacts, preserveLocalFileArtifact } from './file-artifacts.js';

export function normalizeToolOutput(value) {
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function createDispatchTool({
  selfId,
  peers,
  meshBus,
  authToken,
  toolExecutor,
  meshCaller,
  meshStore,
  teamExecutor,
  consensusExecutor,
  codeEnsembleExecutor,
  debateExecutor,
  tm,
}) {
  return async function dispatchTool(name, input, context) {
    switch (name) {
      case 'a2a_call':
        return await meshCaller.executeA2ACall(input, context);
      case 'a2a_broadcast':
        return await meshCaller.executeA2ABroadcast(input, context);
      case 'a2a_team':
        if (teamExecutor) {
          return await teamExecutor(input, {
            ...context,
            depth: context.depth,
            meshChain: context.meshChain,
            taskId: context.taskId,
            selfCallDepth: context.selfCallDepth,
            selfId,
            peers,
            meshBus,
            meshStore,
            authToken,
          });
        }
        return 'Error: team executor not available (mesh modules not loaded).';
      case 'a2a_consensus':
        if (consensusExecutor) {
          return consensusExecutor.formatConsensusResult(await consensusExecutor.execute(input, context));
        }
        return 'Error: consensus executor not available.';
      case 'a2a_code_ensemble':
        if (codeEnsembleExecutor) {
          return codeEnsembleExecutor.formatEnsembleResult(await codeEnsembleExecutor.execute(input, context));
        }
        return 'Error: code ensemble executor not available (mesh modules not loaded).';
      case 'a2a_debate':
        if (debateExecutor) {
          return debateExecutor.formatDebateResult(await debateExecutor.execute(input, context));
        }
        return 'Error: debate executor not available (mesh modules not loaded).';
      default: {
        const result = await Promise.resolve(toolExecutor(name, input, context));
        if (name === 'write_file' && context?.taskId) {
          const task = tm?.tasks?.get(context.taskId);
          if (task) {
            try {
              const artifact = preserveLocalFileArtifact(input?.path, {
                taskId: task.id,
                agentId: selfId,
                source: 'write_file-tool',
                description: `Arquivo criado ou atualizado por ${selfId}`,
              });
              tm.updateTask(task, { artifacts: mergeArtifacts(task.artifacts || [], [artifact]) });
            } catch (error) {
              return `${normalizeToolOutput(result)}\nArtifact registration warning: ${error.message}`;
            }
          }
        }
        return result;
      }
    }
  };
}

/**
 * Build shared runtime objects used by all agent servers.
 */
export async function createSharedRuntime({
  selfId,
  authToken = '',
  maxDepth = 7,
  maxTasks = 200,
  maxConcurrent = 15,
  dataDir = null,
}) {
  const peers = loadPeerRegistry({ selfId });
  const selfUrl = resolveSelfUrl({ selfId, peers });

  let meshStore = null;
  let meshBus = null;
  let teamExecutor = null;
  let createConsensusExecutorFn = null;
  let createCodeEnsembleExecutorFn = null;
  let createDebateExecutorFn = null;
  let createPlanExecutorFn = null;
  let consensusExecutor = null;
  let codeEnsembleExecutor = null;
  let debateExecutor = null;
  let planExecutor = null;

  try {
    const { MeshStore } = await import('./mesh-store.js');
    const { MeshEventBus } = await import('./event-bus.js');
    const teamModule = await import('./team-executor.js');
    const { createConsensusExecutor } = await import('./mesh-consensus.js');
    const { createCodeEnsembleExecutor } = await import('./mesh-code-ensemble.js');
    const { createDebateExecutor } = await import('./mesh-debate.js');
    const { createPlanExecutor } = await import('./mesh-plan.js');

    meshStore = new MeshStore();
    meshBus = new MeshEventBus({ selfId, peers, store: meshStore, authToken });
    teamExecutor = teamModule.executeA2ATeam;
    createConsensusExecutorFn = createConsensusExecutor;
    createCodeEnsembleExecutorFn = createCodeEnsembleExecutor;
    createDebateExecutorFn = createDebateExecutor;
    createPlanExecutorFn = createPlanExecutor;

    console.log('[mesh] Shared runtime initialized (store + bus + team + consensus + code-ensemble + debate + plan)');
  } catch (err) {
    console.warn('[mesh] Shared runtime degraded (standalone mode):', err instanceof Error ? err.message : String(err));
  }

  const tm = createTaskManager({
    dataDir,
    selfId,
    maxDepth,
    maxTasks,
    maxConcurrent,
    meshStore,
    meshBus,
  });

  // Create PeerDiscovery for dynamic health-based peer status tracking
  const peerDiscovery = new PeerDiscovery(peers);

  const toolExecutor = createToolExecutor({ truncateOutput: false });
  const meshCaller = createMeshCaller({
    selfId,
    peers,
    maxDepth,
    meshBus,
    meshStore,
    authToken,
    selfUrl,
    peerDiscovery,
  });

  if (createConsensusExecutorFn) {
    consensusExecutor = createConsensusExecutorFn({
      meshCaller,
      peers,
      selfId,
      maxDepth,
      meshStore,
      meshBus,
      authToken,
      selfUrl,
      peerDiscovery,
    });
  }

  if (createCodeEnsembleExecutorFn) {
    codeEnsembleExecutor = createCodeEnsembleExecutorFn({
      meshCaller,
      peers,
      selfId,
      maxDepth,
      meshStore,
      meshBus,
      authToken,
      selfUrl,
      peerDiscovery,
    });
  }

  if (createDebateExecutorFn) {
    debateExecutor = createDebateExecutorFn({
      meshCaller,
      peers,
      selfId,
      maxDepth,
      meshStore,
      meshBus,
      authToken,
      selfUrl,
    });
  }

  if (createPlanExecutorFn) {
    planExecutor = createPlanExecutorFn({
      meshCaller,
      peers,
      selfId,
      maxDepth,
      meshStore,
      meshBus,
      authToken,
      selfUrl,
    });
  }

  const dispatchTool = createDispatchTool({
    selfId,
    peers,
    meshBus,
    authToken,
    toolExecutor,
    meshCaller,
    meshStore,
    teamExecutor,
    consensusExecutor,
    codeEnsembleExecutor,
    debateExecutor,
    tm,
  });

  return {
    peers,
    selfUrl,
    tm,
    toolExecutor,
    meshCaller,
    meshStore,
    meshBus,
    peerDiscovery,
    teamExecutor,
    consensusExecutor,
    codeEnsembleExecutor,
    debateExecutor,
    planExecutor,
    dispatchTool,
    normalizeToolOutput,
    cliToolWrapper,
  };
}
