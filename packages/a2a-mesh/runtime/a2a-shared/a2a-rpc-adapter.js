// ============================================
// JSON-RPC 2.0 Adapter for A2A servers
// ============================================

import { TERMINAL_STATES } from './task-states.js';
import { mergeRequestTaskMetadata } from './provider-session.js';
import { recoverPartialArtifacts } from './partial-output.js';
import { randomUUID } from 'node:crypto';

/**
 * Create an RPC adapter that translates JSON-RPC 2.0 requests to internal handlers.
 *
 * @param {Object} ctx
 * @param {Object} ctx.tm - Task manager
 * @param {Function} ctx.executeTask - (task, onChunk) => void
 * @param {number} ctx.taskTimeoutMs - Task timeout in ms
 * @param {Object} ctx.meshCaller - Mesh caller instance
 * @param {Object} [ctx.meshStore] - MeshStore instance
 * @param {Object} [ctx.meshBus] - MeshEventBus instance
 * @param {Function} [ctx.teamExecutor] - Team executor function
 * @param {Function} [ctx.consensusExecutor] - Consensus executor (optional)
 * @param {number} ctx.maxDepth - Max mesh depth
 * @param {string} ctx.selfId - This server's ID
 * @param {Object} ctx.peers - Peer map
 * @param {Object} ctx.push - { set, get, delete } for push notifications
 */
export function createRPCAdapter(ctx) {
  const {
    tm, executeTask, taskTimeoutMs,
    meshCaller, meshStore, meshBus,
    teamExecutor, consensusExecutor, ensembleExecutor, debateExecutor, planExecutor,
    maxDepth, selfId, peers, push, authToken = '',
  } = ctx;

  const DEFAULT_ASYNC_OPERATION_TIMEOUT_MS = 86_400_000; // 24 h
  const MAX_ASYNC_OPERATION_TIMEOUT_MS = 432_000_000; // 5 days

  function asyncOperationTimeout(params = {}) {
    const configuredDefault = Number.parseInt(
      process.env.A2A_MESH_OPERATION_TIMEOUT_MS || String(DEFAULT_ASYNC_OPERATION_TIMEOUT_MS),
      10,
    );
    const fallback = Number.isFinite(configuredDefault) && configuredDefault > 0
      ? configuredDefault
      : DEFAULT_ASYNC_OPERATION_TIMEOUT_MS;
    const requested = Number.parseInt(String(params.operation_timeout_ms ?? fallback), 10);
    return Math.min(
      MAX_ASYNC_OPERATION_TIMEOUT_MS,
      Math.max(60_000, Number.isFinite(requested) ? requested : fallback),
    );
  }

  function taskInputPreview(methodName, params = {}) {
    const value = params.prompt || params.topic || params.task || params.description
      || params.name || methodName;
    return String(value).slice(0, 20_000);
  }

  function clampDepth(value) {
    const parsed = Number.parseInt(String(value ?? maxDepth), 10);
    if (!Number.isFinite(parsed)) return maxDepth;
    return Math.max(0, Math.min(maxDepth, parsed));
  }

  function ensureTaskAbortController(task) {
    if (task._abortController) return task._abortController;
    Object.defineProperty(task, '_abortController', {
      value: new AbortController(),
      writable: true,
      configurable: true,
      enumerable: false,
    });
    return task._abortController;
  }

  function abortTaskExecution(task, reason = 'Task cancelled') {
    if (task._abortController) {
      try {
        task._abortController.abort(new Error(reason));
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[rpc] Failed to abort task controller', {
            taskId: task.id,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
    if (task.process) {
      try {
        task.process.kill('SIGTERM');
      } catch (err) {
        if (process.env.A2A_DEBUG === 'true') {
          console.warn('[rpc] Failed to kill task process', {
            taskId: task.id,
            pid: task.process?.pid,
            error: err instanceof Error ? err.message : String(err),
          });
        }
      }
    }
  }

  // --- Method handlers ---

  async function handleTasksSend(params) {
    const message = params.message;
    if (!message?.parts?.length) throw rpcError(-32602, 'message with parts is required');

    if (tm.getActiveTasks().length >= tm.maxConcurrent) {
      throw rpcError(-32000, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
    }
    tm.evictOldTasks();

    let task;
    if (params.id && tm.tasks.has(params.id)) {
      task = tm.tasks.get(params.id);
      task.history.push(message);
      tm.updateTask(task, { status: { state: 'submitted' } });
    } else {
      task = tm.createTask(message, mergeRequestTaskMetadata(params));
    }

    await new Promise((resolve) => {
      const controller = ensureTaskAbortController(task);
      let timeoutId;
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        clearTimeout(timeoutId);
        resolve();
      };
      executeTask(task, (event) => {
        if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') finish();
      }, { signal: controller.signal });
      timeoutId = setTimeout(() => {
        if (task.status.state === 'working') {
          abortTaskExecution(task, `Task timed out after ${taskTimeoutMs}ms`);
          tm.updateTask(task, {
            status: { state: 'failed', message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: ${taskTimeoutMs / 60000} min` }] } },
          });
        }
        finish();
      }, taskTimeoutMs);
    });

    return tm.taskToJSON(task);
  }

  async function handleTasksSendAsync(params) {
    const message = params.message;
    if (!message?.parts?.length) throw rpcError(-32602, 'message with parts is required');

    if (tm.getActiveTasks().length >= tm.maxConcurrent) {
      throw rpcError(-32000, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
    }
    tm.evictOldTasks();

    let task;
    if (params.id && tm.tasks.has(params.id)) {
      task = tm.tasks.get(params.id);
      task.history.push(message);
      tm.updateTask(task, { status: { state: 'submitted' } });
    } else {
      task = tm.createTask(message, mergeRequestTaskMetadata(params));
    }

    // Fire-and-forget: start execution without awaiting completion
    const controller = ensureTaskAbortController(task);
    let timeoutId;
    executeTask(task, (event) => {
      if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') {
        clearTimeout(timeoutId);
      }
    }, { signal: controller.signal });
    timeoutId = setTimeout(() => {
      if (task.status.state === 'working') {
        abortTaskExecution(task, `Task timed out after ${taskTimeoutMs}ms`);
        tm.updateTask(task, {
          status: { state: 'failed', message: { role: 'agent', parts: [{ type: 'text', text: `Timeout: ${taskTimeoutMs / 60000} min` }] } },
        });
      }
    }, taskTimeoutMs);

    // Return immediately with task ID and current status
    return { id: task.id, status: task.status };
  }

  function handleTasksGet(params) {
    if (!params.id) throw rpcError(-32602, 'id is required');
    const task = tm.tasks.get(params.id);
    if (!task) throw rpcError(-32602, `Task ${params.id} not found`);
    return tm.taskToJSON(task);
  }

  function handleTasksCancel(params) {
    if (!params.id) throw rpcError(-32602, 'id is required');
    const task = tm.tasks.get(params.id);
    if (!task) throw rpcError(-32602, `Task ${params.id} not found`);
    // Can't cancel a task that's already in a terminal state
    if (TERMINAL_STATES.has(task.status.state)) {
      throw rpcError(-32000, `Cannot cancel task in '${task.status.state}' state`);
    }
    const partial = recoverPartialArtifacts(meshStore, task.id);
    abortTaskExecution(task, 'Task cancelled by user');
    tm.updateTask(task, {
      status: {
        state: 'canceled',
        message: { role: 'agent', parts: [{
          type: 'text',
          text: `Task canceled by user.${partial.length ? ' Saída parcial preservada em partial-output.md.' : ''}`,
        }] },
      },
      artifacts: [...task.artifacts, ...partial],
    });
    return tm.taskToJSON(task);
  }

  function handleTasksList() {
    return [...tm.tasks.values()].map(tm.taskToJSON);
  }

  async function handleTasksBatch(params) {
    const items = params.tasks;
    if (!Array.isArray(items) || items.length === 0) throw rpcError(-32602, 'tasks array is required');
    if (items.length > 10) throw rpcError(-32602, 'batch max 10 tasks');

    const active = tm.getActiveTasks().length;
    if (active + items.length > tm.maxConcurrent) {
      throw rpcError(-32000, `Too many concurrent tasks (active ${active}, batch ${items.length}, max ${tm.maxConcurrent})`);
    }
    tm.evictOldTasks();

    return Promise.all(items.map(item => {
      return new Promise((resolve) => {
        const message = item.message;
        if (!message?.parts?.length) return resolve({ error: 'message with parts is required' });
        const task = tm.createTask(message, mergeRequestTaskMetadata(item));
        const controller = ensureTaskAbortController(task);
        let timeoutId;
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          clearTimeout(timeoutId);
          resolve(tm.taskToJSON(task));
        };
        executeTask(task, (event) => {
          if (TERMINAL_STATES.has(event.type) || event.type === 'input_required' || event.type === 'auth_required') finish();
        }, { signal: controller.signal });
        timeoutId = setTimeout(() => {
          if (task.status.state === 'working') {
            abortTaskExecution(task, `Task timed out after ${taskTimeoutMs}ms`);
            tm.updateTask(task, {
              status: { state: 'failed', message: { role: 'agent', parts: [{ type: 'text', text: `Timeout` }] } },
            });
          }
          finish();
        }, taskTimeoutMs);
      });
    }));
  }

  // Push notification handlers
  function handlePushSet(params) {
    if (!params.taskId || !params.url) throw rpcError(-32602, 'taskId and url are required');
    if (!tm.tasks.has(params.taskId)) throw rpcError(-32602, `Task ${params.taskId} not found`);
    push.set(params.taskId, params.url, params.headers || {});
    return { taskId: params.taskId, url: params.url };
  }

  function handlePushGet(params) {
    if (!params.taskId) throw rpcError(-32602, 'taskId is required');
    return push.get(params.taskId) || { taskId: params.taskId, subscribed: false };
  }

  function handlePushDelete(params) {
    if (!params.taskId) throw rpcError(-32602, 'taskId is required');
    push.delete(params.taskId);
    return { taskId: params.taskId, deleted: true };
  }

  // Mesh handlers
  async function handleMeshCall(params, execution = {}) {
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    return meshCaller.executeA2ACall({ agent: params.agent, prompt: params.prompt, timeout_ms: params.timeout_ms }, mctx);
  }

  async function handleMeshBroadcast(params, execution = {}) {
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    const includeSelf = params.includeSelf === true;
    return meshCaller.executeA2ABroadcast({ prompt: params.prompt, agents: params.agents, includeSelf, timeout_ms: params.timeout_ms }, mctx);
  }

  async function handleMeshTeam(params, execution = {}) {
    if (!teamExecutor) throw rpcError(-32601, 'Team executor not available');
    const mctx = {
      depth: clampDepth(params.depth), meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      selfId, peers, meshBus, authToken,
      signal: execution.signal,
    };
    return teamExecutor({
      name: params.name,
      steps: params.steps,
      context: params.context,
      accumulate: params.accumulate,
      includeSelf: params.includeSelf,
      timeout_ms: params.timeout_ms,
      profile: params.profile,
    }, mctx);
  }

  async function handleMeshConsensus(params, execution = {}) {
    if (!consensusExecutor) throw rpcError(-32601, 'Consensus executor not available');
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    return consensusExecutor.execute(params, mctx);
  }

  async function handleMeshEnsemble(params, execution = {}) {
    if (!ensembleExecutor) throw rpcError(-32601, 'Code ensemble executor not available');
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    return ensembleExecutor.execute(params, mctx);
  }

  async function handleMeshDebate(params, execution = {}) {
    if (!debateExecutor) throw rpcError(-32601, 'Debate executor not available');
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    return debateExecutor.execute(params, mctx);
  }

  async function handleMeshPlan(params, execution = {}) {
    if (!planExecutor) throw rpcError(-32601, 'Plan executor not available');
    const mctx = {
      depth: clampDepth(params.depth),
      meshChain: params.meshChain || [],
      taskId: params.taskId || `rpc-${Date.now()}`,
      selfCallDepth: params.selfCallDepth || 0,
      signal: execution.signal,
    };
    return planExecutor.execute(params, mctx);
  }

  function formatAsyncResultText(result) {
    if (typeof result === 'string') return result;
    try {
      return JSON.stringify(result, null, 2);
    } catch {
      return String(result);
    }
  }

  function createAsyncMeshTask(methodName, params, runner) {
    const requestId = String(params?.request_id || '').trim();
    if (requestId) {
      const existing = [...tm.tasks.values()].find((candidate) =>
        candidate.metadata?.requestId === requestId
        && candidate.metadata?.type === methodName,
      );
      if (existing) {
        return { id: existing.id, status: existing.status, reused: true, requestId, coordinator: selfId };
      }
    }

    if (tm.getActiveTasks().length >= tm.maxConcurrent) {
      throw rpcError(-32000, `Too many concurrent tasks (max ${tm.maxConcurrent})`);
    }
    tm.evictOldTasks();

    const operationTimeoutMs = asyncOperationTimeout(params);

    const message = {
      role: 'user',
      parts: [{ type: 'text', text: `[${methodName}] ${taskInputPreview(methodName, params)}` }],
    };
    const reservedTaskId = randomUUID();
    let claimed = false;
    if (requestId && meshStore?.claimIdempotency) {
      const claim = meshStore.claimIdempotency(methodName, requestId, reservedTaskId);
      if (!claim.claimed) {
        const existing = meshStore.getIdempotentTask(methodName, requestId);
        if (existing?.reservationOnly) {
          throw rpcError(
            -32009,
            `Idempotency reservation ${requestId} is pending without a task; retry after the reservation TTL`,
          );
        }
        return {
          id: claim.taskId,
          status: { state: existing?.state || 'submitted' },
          reused: true,
          requestId,
          coordinator: existing?.originServer || selfId,
        };
      }
      claimed = true;
    }
    let task;
    try {
      task = tm.createTask(message, mergeRequestTaskMetadata(params, {
        type: methodName,
        requestId: requestId || undefined,
        operationTimeoutMs,
      }), reservedTaskId);
    } catch (error) {
      if (claimed) meshStore.releaseIdempotency(methodName, requestId, reservedTaskId);
      throw error;
    }
    const controller = ensureTaskAbortController(task);

    let timeoutId;
    Promise.resolve()
      .then(async () => {
        tm.updateTask(task, { status: { state: 'working' } });
        const result = await runner(task);
        if (TERMINAL_STATES.has(task.status.state)) return;
        const text = formatAsyncResultText(result);
        const agentMessage = { role: 'agent', parts: [{ type: 'text', text }] };
        tm.updateTask(task, {
          status: { state: 'completed', message: agentMessage },
          history: [...task.history, agentMessage],
        });
      })
      .catch((err) => {
        if (TERMINAL_STATES.has(task.status.state)) return;
        const msg = err instanceof Error ? err.message : String(err);
        const partial = recoverPartialArtifacts(meshStore, task.id);
        const retained = partial.length > 0 ? ' Saída parcial preservada em partial-output.md.' : '';
        const suffix = /[.!?]$/.test(msg) ? '' : '.';
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro: ${msg}${suffix}${retained}` }] };
        tm.updateTask(task, {
          status: { state: 'failed', message: errorMessage },
          history: [...task.history, errorMessage],
          artifacts: [...task.artifacts, ...partial],
        });
      })
      .finally(() => {
        clearTimeout(timeoutId);
      });

    timeoutId = setTimeout(() => {
      if (task.status.state === 'working' || task.status.state === 'submitted') {
        const partial = recoverPartialArtifacts(meshStore, task.id);
        abortTaskExecution(task, `Task timed out after ${operationTimeoutMs}ms`);
        tm.updateTask(task, {
          status: {
            state: 'failed',
            message: { role: 'agent', parts: [{
              type: 'text',
              text: `Timeout da operação: ${Math.round(operationTimeoutMs / 60000)} min.${partial.length ? ' Saída parcial preservada em partial-output.md.' : ''}`,
            }] },
          },
          artifacts: [...task.artifacts, ...partial],
        });
      }
    }, operationTimeoutMs);

    return {
      id: task.id,
      status: task.status,
      requestId: requestId || null,
      operationTimeoutMs,
      coordinator: selfId,
    };
  }

  function handleMeshCallAsync(params) {
    return createAsyncMeshTask('mesh/call', params, (task) =>
      handleMeshCall({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshBroadcastAsync(params) {
    return createAsyncMeshTask('mesh/broadcast', params, (task) =>
      handleMeshBroadcast({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshTeamAsync(params) {
    return createAsyncMeshTask('mesh/team', params, (task) =>
      handleMeshTeam({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshConsensusAsync(params) {
    return createAsyncMeshTask('mesh/consensus', params, (task) =>
      handleMeshConsensus({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshEnsembleAsync(params) {
    return createAsyncMeshTask('mesh/ensemble', params, (task) =>
      handleMeshEnsemble({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshDebateAsync(params) {
    return createAsyncMeshTask('mesh/debate', params, (task) =>
      handleMeshDebate({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshPlanAsync(params) {
    return createAsyncMeshTask('mesh/plan', params, (task) =>
      handleMeshPlan({ ...params, taskId: task.id }, { signal: task._abortController?.signal }),
    );
  }

  function handleMeshTrace(params) {
    if (!meshStore) throw rpcError(-32601, 'Mesh not available');
    if (!params.taskId) throw rpcError(-32602, 'taskId is required');
    const trace = meshStore.getTrace(params.taskId);
    if (!trace) throw rpcError(-32602, 'Task not found in mesh');
    return trace;
  }

  function handleMeshTimeline(params) {
    if (!meshStore) throw rpcError(-32601, 'Mesh not available');
    return meshStore.getTimeline({ limit: params.limit || 100, since: params.since, server: params.server });
  }

  function handleMeshStats() {
    if (!meshStore) throw rpcError(-32601, 'Mesh not available');
    return meshStore.getStats();
  }

  function handleMeshTasks(params) {
    if (!meshStore) throw rpcError(-32601, 'Mesh not available');
    return meshStore.listTasks({ state: params.state, originServer: params.origin, limit: params.limit || 50 });
  }

  // --- Method dispatch table ---

  const methods = {
    'tasks/send': handleTasksSend,
    'tasks/sendAsync': handleTasksSendAsync,
    'tasks/get': handleTasksGet,
    'tasks/cancel': handleTasksCancel,
    'tasks/list': handleTasksList,
    'tasks/batch': handleTasksBatch,
    'tasks/sendSubscribe': () => { throw rpcError(-32001, 'Use REST POST /tasks/sendSubscribe for SSE streaming'); },
    'tasks/pushNotification/set': handlePushSet,
    'tasks/pushNotification/get': handlePushGet,
    'tasks/pushNotification/delete': handlePushDelete,
    'mesh/call': handleMeshCall,
    'mesh/callAsync': handleMeshCallAsync,
    'mesh/broadcast': handleMeshBroadcast,
    'mesh/broadcastAsync': handleMeshBroadcastAsync,
    'mesh/team': handleMeshTeam,
    'mesh/teamAsync': handleMeshTeamAsync,
    'mesh/consensus': handleMeshConsensus,
    'mesh/consensusAsync': handleMeshConsensusAsync,
    'mesh/ensemble': handleMeshEnsemble,
    'mesh/ensembleAsync': handleMeshEnsembleAsync,
    'mesh/debate': handleMeshDebate,
    'mesh/debateAsync': handleMeshDebateAsync,
    'mesh/plan': handleMeshPlan,
    'mesh/planAsync': handleMeshPlanAsync,
    'mesh/trace': handleMeshTrace,
    'mesh/timeline': handleMeshTimeline,
    'mesh/stats': handleMeshStats,
    'mesh/tasks': handleMeshTasks,
  };

  // --- Core JSON-RPC 2.0 processor ---

  async function processOne(req) {
    if (!req || typeof req !== 'object') {
      return { jsonrpc: '2.0', error: { code: -32600, message: 'Invalid Request' }, id: null };
    }
    if (req.jsonrpc !== '2.0') {
      return { jsonrpc: '2.0', error: { code: -32600, message: 'Invalid Request: jsonrpc must be "2.0"' }, id: req.id ?? null };
    }
    if (!req.method || typeof req.method !== 'string') {
      return { jsonrpc: '2.0', error: { code: -32600, message: 'Invalid Request: method is required' }, id: req.id ?? null };
    }

    const handler = methods[req.method];
    if (!handler) {
      return { jsonrpc: '2.0', error: { code: -32601, message: `Method not found: ${req.method}` }, id: req.id ?? null };
    }

    // JSON-RPC 2.0: requests without "id" are notifications — no response
    const isNotification = !('id' in req);

    try {
      const result = await handler(req.params || {});
      return isNotification ? null : { jsonrpc: '2.0', result, id: req.id };
    } catch (err) {
      if (isNotification) return null; // notifications never get error responses
      if (err._rpc) {
        return { jsonrpc: '2.0', error: { code: err.code, message: err.message }, id: req.id };
      }
      return { jsonrpc: '2.0', error: { code: -32000, message: err.message }, id: req.id };
    }
  }

  /**
   * Handle a raw JSON-RPC request (single or batch).
   * @param {string} rawBody - Raw JSON string from request body
   * @returns {Promise<Object|Array>} JSON-RPC response(s)
   */
  async function handle(rawBody) {
    let parsed;
    try {
      parsed = JSON.parse(rawBody);
    } catch {
      return { jsonrpc: '2.0', error: { code: -32700, message: 'Parse error' }, id: null };
    }

    if (Array.isArray(parsed)) {
      if (parsed.length === 0) {
        return { jsonrpc: '2.0', error: { code: -32600, message: 'Invalid Request: empty batch' }, id: null };
      }
      const results = await Promise.all(parsed.map(processOne));
      // Filter out notifications (no id) per JSON-RPC 2.0 spec
      const filtered = results.filter(r => r !== null);
      return filtered.length > 0 ? filtered : null;
    }

    return processOne(parsed);
  }

  return { handle, methods };
}

// Helper to create typed RPC errors
function rpcError(code, message) {
  const err = new Error(message);
  err.code = code;
  err._rpc = true;
  return err;
}
