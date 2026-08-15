// ============================================
// Task Manager — Task CRUD, persistence, mesh sync
// ============================================

import fs from 'fs';
import os from 'node:os';
import path from 'path';
import { fileURLToPath } from 'node:url';
import { randomUUID } from 'crypto';
import { EventEmitter } from 'events';
import { ACTIVE_STATES, TERMINAL_STATES, WAITING_STATES } from './task-states.js';
import { extractProviderSession, mergeProviderSessionMetadata } from './provider-session.js';

/**
 * Create a task manager with CRUD, JSON persistence, and mesh store sync.
 *
 * @param {Object} config
 * @param {string} config.dataDir - Directory for tasks.json (e.g. './data/')
 * @param {string} config.selfId - This server's ID
 * @param {number} config.maxDepth - A2A_MESH_MAX_DEPTH
 * @param {number} config.maxTasks - Max tasks before eviction (default 200)
 * @param {number} config.maxConcurrent - Max concurrent active tasks (default 5)
 * @param {Object} [config.meshStore] - MeshStore instance (optional)
 * @param {Object} [config.meshBus] - MeshEventBus instance (optional)
 */
export function createTaskManager({
  dataDir,
  selfId,
  maxDepth = 7,
  maxTasks = 200,
  maxConcurrent = 5,
  meshStore = null,
  meshBus = null,
} = {}) {

  const moduleDir = path.dirname(fileURLToPath(import.meta.url));
  const resolvedDir = dataDir
    ? (path.isAbsolute(dataDir) ? dataDir : path.resolve(moduleDir, dataDir))
    : path.join(os.homedir(), '.local', 'state', 'a2a-mesh', 'tasks', selfId || 'unknown');
  const tasksFile = path.join(resolvedDir, 'tasks.json');
  const taskEmitter = new EventEmitter();

  function ensureDir() {
    if (!fs.existsSync(resolvedDir)) fs.mkdirSync(resolvedDir, { recursive: true });
  }

  function writeTasksFile(serializable) {
    ensureDir();
    const temporary = path.join(resolvedDir, `.tasks.${process.pid}.${Date.now()}.tmp`);
    fs.writeFileSync(temporary, JSON.stringify(serializable, null, 2), { mode: 0o600 });
    fs.renameSync(temporary, tasksFile);
  }

  function loadTasks() {
    try {
      ensureDir();
      if (fs.existsSync(tasksFile)) {
        const data = JSON.parse(fs.readFileSync(tasksFile, 'utf8'));
        let zombieCount = 0;
        const recoveredTasks = [];
        const tasks = new Map(data.map(t => {
          // Tasks stuck in working/submitted from a previous process are
          // irrecoverable — no running process, no timeout timer, no abort
          // controller. Mark them as failed to prevent blocking new tasks.
          // Waiting states (input_required, auth_required) are NOT zombies —
          // they're paused and can be resumed with new input.
          if (ACTIVE_STATES.has(t.status?.state)) {
            zombieCount++;
            recoveredTasks.push(t.id);
            t.status = {
              state: 'failed',
              message: {
                role: 'agent',
                parts: [{ type: 'text', text: 'Task failed: server restarted while task was in progress' }],
              },
            };
            t.updatedAt = new Date().toISOString();
          }
          return [t.id, t];
        }));
        if (zombieCount > 0) {
          console.warn(`[task-manager] Recovered ${zombieCount} zombie task(s) from previous run (marked as failed)`);
          // Persist corrected states immediately so they don't reappear as zombies
          try {
            const serializable = [...tasks.values()].map(({ process: _p, ...rest }) => rest);
            writeTasksFile(serializable);
          } catch (e) {
            console.warn('[task-manager] Failed to persist zombie recovery:', e.message);
          }
          if (meshStore) {
            for (const id of recoveredTasks) {
              try {
                const reason = 'Task failed: server restarted while task was in progress';
                meshStore.updateTask(id, {
                  state: 'failed',
                  outputText: reason,
                  error: reason,
                });
                if (typeof meshStore.createEvent === 'function') {
                  meshStore.createEvent(id, 'failed', selfId, { outputPreview: reason });
                }
              } catch (e) {
                console.warn('[task-manager] Failed to sync zombie recovery to meshStore:', e.message);
              }
            }
          }
        }
        return tasks;
      }
    } catch (e) {
      console.error('Erro ao carregar tarefas:', e.message);
    }
    return new Map();
  }

  const tasks = loadTasks();
  if (meshStore && typeof meshStore.failStaleActiveTasks === 'function') {
    try {
      const recovered = meshStore.failStaleActiveTasks({
        originServer: selfId,
        reason: 'Task failed: server restarted while task was in progress',
      });
      if (recovered > 0) {
        console.warn(`[task-manager] Recovered ${recovered} meshStore zombie task(s) for ${selfId}`);
      }
    } catch (e) {
      console.warn('[task-manager] Failed to recover meshStore zombie tasks:', e.message);
    }
  }

  function saveTasks() {
    try {
      ensureDir();
      const serializable = [...tasks.values()].map(({ process: _p, ...rest }) => rest);
      writeTasksFile(serializable);
    } catch (e) {
      console.error('Erro ao salvar tarefas:', e.message);
    }
  }

  function getActiveTasks() {
    return [...tasks.values()].filter(t => ACTIVE_STATES.has(t.status.state));
  }

  function evictOldTasks() {
    if (tasks.size <= maxTasks) return;
    const sorted = [...tasks.entries()].sort((a, b) => (a[1].createdAt || '').localeCompare(b[1].createdAt || ''));
    while (tasks.size > maxTasks && sorted.length > 0) {
      const [id, task] = sorted.shift();
      const state = task.status.state;
      // Don't evict active or waiting tasks — only terminal states can be evicted
      if (ACTIVE_STATES.has(state) || WAITING_STATES.has(state)) continue;
      tasks.delete(id);
    }
    saveTasks();
  }

  function createTask(message, metadata = {}) {
    const id = randomUUID();
    const sessionId = metadata.sessionId || randomUUID();
    const taskMetadata = mergeProviderSessionMetadata(metadata, { sessionId, agentId: selfId });
    const parsedDepth = Number.parseInt(String(taskMetadata.maxDepth ?? maxDepth), 10);
    taskMetadata.maxDepth = Math.max(0, Math.min(maxDepth, Number.isFinite(parsedDepth) ? parsedDepth : maxDepth));
    const providerSession = extractProviderSession(taskMetadata);

    const task = {
      id,
      sessionId,
      ...providerSession,
      status: { state: 'submitted' },
      history: [message],
      artifacts: [],
      metadata: taskMetadata,
      process: null,
      createdAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
    };

    tasks.set(id, task);
    saveTasks();

    if (meshStore) {
      try {
        meshStore.createTask({
          id, sessionId, originServer: selfId,
          parentTaskId: metadata.parentTaskId,
          calledBy: metadata.calledBy,
          meshChain: metadata.meshChain,
          depth: taskMetadata.maxDepth,
          inputText: message.parts?.map(p => p.text).join('\n'),
          metadata: taskMetadata,
          ...providerSession,
        });
      } catch (e) { console.warn('[mesh] createTask error:', e.message); }
    }

    return task;
  }

  function updateTask(task, updates) {
    Object.assign(task, updates, { updatedAt: new Date().toISOString() });
    taskEmitter.emit(`task:${task.id}`, task);
    saveTasks();

    if (meshStore) {
      try {
        const state = updates.status?.state;
        const outputText = updates.status?.message?.parts?.map(p => p.text).join('\n');
        meshStore.updateTask(task.id, {
          state, outputText,
          error: state === 'failed' ? outputText : undefined,
          artifacts: updates.artifacts,
          history: updates.history,
        });
      } catch (e) { console.warn('[mesh] updateTask error:', e.message); }
    }
    if (meshBus && updates.status?.state) {
      meshBus.publish({
        taskId: task.id, type: updates.status.state,
        payload: { outputPreview: updates.status?.message?.parts?.[0]?.text?.slice(0, 200) },
      });
    }
  }

  function taskToJSON(task) {
    const { process: _proc, ...rest } = task;
    return rest;
  }

  /**
   * Force-fail tasks stuck in active states past `staleThresholdMs`.
   *
   * Recovery on `loadTasks()` only handles the "server crashed and restarted"
   * case. If executeTask throws synchronously, the per-call setTimeout in
   * base-server is cleared, or a child process exits without emitting a
   * terminal state, the task stays in `working` forever and consumes a
   * `maxConcurrent` slot. This reaper is the in-process safety net.
   *
   * Waiting states (input_required, auth_required) are intentionally NOT
   * reaped — they're paused on user input by design.
   *
   * Returns the number of reaped tasks (useful for tests/metrics).
   */
  // Cumulative counters for /health observability. The reaper firing is the
  // safety net — if reaperLastReaped > 0 frequently, something upstream is
  // failing to emit terminal states.
  const reaperStats = { totalReaped: 0, totalRuns: 0, lastReaped: 0, lastRunAt: null };

  function reapStuckTasks({ staleThresholdMs, now = Date.now() } = {}) {
    const cutoff = now - staleThresholdMs;
    let reaped = 0;
    for (const task of tasks.values()) {
      if (!ACTIVE_STATES.has(task.status?.state)) continue;
      const updatedAt = Date.parse(task.updatedAt || task.createdAt || '');
      if (!Number.isFinite(updatedAt) || updatedAt > cutoff) continue;
      const ageMs = now - updatedAt;
      const reason = `Task failed: stuck in '${task.status.state}' for ${Math.round(ageMs / 60000)}min (reaper)`;
      // Best-effort: kill any lingering child process before flipping state.
      if (task.process) {
        try {
          if (task.process.pid) {
            try { process.kill(-task.process.pid, 'SIGKILL'); } catch { /* not a group leader */ }
          }
          task.process.kill('SIGKILL');
        } catch { /* already gone */ }
      }
      updateTask(task, {
        status: {
          state: 'failed',
          message: { role: 'agent', parts: [{ type: 'text', text: reason }] },
        },
      });
      reaped++;
    }
    reaperStats.totalRuns++;
    reaperStats.lastReaped = reaped;
    reaperStats.lastRunAt = new Date(now).toISOString();
    reaperStats.totalReaped += reaped;
    if (reaped > 0) {
      console.warn(`[task-manager] Reaper force-failed ${reaped} stuck task(s) for ${selfId} (cumulative: ${reaperStats.totalReaped})`);
    }
    return reaped;
  }

  function getReaperStats() {
    return { ...reaperStats };
  }

  // Periodic reaper. Default threshold is 1.5x the longest expected task
  // (consensus/ensemble run up to 45 min, so 60 min default is safe).
  const REAPER_INTERVAL_MS = Number.parseInt(process.env.A2A_TASK_REAPER_INTERVAL_MS || '60000', 10);
  const STALE_THRESHOLD_MS = Number.parseInt(process.env.A2A_TASK_STALE_THRESHOLD_MS || '3600000', 10);
  const reaperEnabled = REAPER_INTERVAL_MS > 0 && STALE_THRESHOLD_MS > 0;
  const reaperHandle = reaperEnabled
    ? setInterval(() => {
        try { reapStuckTasks({ staleThresholdMs: STALE_THRESHOLD_MS }); }
        catch (e) { console.warn('[task-manager] Reaper error:', e.message); }
      }, REAPER_INTERVAL_MS)
    : null;
  if (reaperHandle?.unref) reaperHandle.unref();

  function stopReaper() {
    if (reaperHandle) clearInterval(reaperHandle);
  }

  return {
    tasks,
    taskEmitter,
    createTask,
    updateTask,
    taskToJSON,
    getActiveTasks,
    evictOldTasks,
    reapStuckTasks,
    getReaperStats,
    stopReaper,
    saveTasks,
    maxConcurrent,
  };
}
