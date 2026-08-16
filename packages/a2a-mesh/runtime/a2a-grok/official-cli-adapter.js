// ============================================
// Official xAI Grok CLI adapter — explicit route, streaming-json, no fallback
// ============================================

import { spawn, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

import { bridgeEnvironmentForTask } from '../a2a-shared/bridge-context.js';
import { extractResponseArtifacts, mergeArtifacts, stripArtifactDeclarations } from '../a2a-shared/file-artifacts.js';

export const OFFICIAL_GROK_MODEL = 'grok-4.6';
export const OFFICIAL_GROK_REASONING_EFFORT = 'xhigh';

export function parseOfficialGrokModels(output) {
  const text = String(output || '');
  const models = [];
  for (const line of text.split(/\r?\n/)) {
    const item = line.match(/^\s*\*\s+([^\s(]+)(?:\s+\(default\))?\s*$/i)?.[1];
    if (item) models.push(item);
    const defaultModel = line.match(/^\s*Default model:\s*(\S+)\s*$/i)?.[1];
    if (defaultModel) models.push(defaultModel);
  }
  return [...new Set(models)];
}

export function probeOfficialGrok(binary = 'grok', model = OFFICIAL_GROK_MODEL, { timeoutMs = 15_000, env = process.env } = {}) {
  const result = spawnSync(binary, ['models'], {
    encoding: 'utf8',
    timeout: timeoutMs,
    env,
  });
  const output = `${result.stdout || ''}\n${result.stderr || ''}`.trim();
  const models = parseOfficialGrokModels(output);
  const authenticated = result.status === 0 && !/not authenticated|authentication required|please log in/i.test(output);
  const modelAvailable = models.includes(model);
  return {
    available: !result.error && result.status === 0 && modelAvailable,
    authenticated,
    modelAvailable,
    model,
    models,
    error: result.error?.message || (result.status !== 0 ? output || `status ${result.status}` : null),
  };
}

export function parseOfficialGrokStreamLine(line) {
  try {
    const event = JSON.parse(String(line || '').trim());
    if (!event || typeof event !== 'object') return null;
    const type = String(event.type || '');
    return {
      raw: event,
      type,
      text: type === 'text' ? String(event.data ?? event.text ?? '') : '',
      terminal: type === 'end',
      isError: type === 'error' || Boolean(event.error),
      error: event.error ? String(event.error?.message || event.error) : '',
      sessionId: event.session_id || event.sessionId || null,
      model: event.model || event.message?.model || null,
    };
  } catch {
    return null;
  }
}

export function buildOfficialGrokArgs({
  model = OFFICIAL_GROK_MODEL,
  workspace = process.cwd(),
  reasoningEffort = OFFICIAL_GROK_REASONING_EFFORT,
  promptFile,
} = {}) {
  if (!promptFile) throw new Error('promptFile is required for the official Grok CLI');
  return [
    '--prompt-file', promptFile,
    '--model', model,
    '--cwd', workspace,
    '--output-format', 'streaming-json',
    '--reasoning-effort', reasoningEffort,
    '--always-approve',
    '--permission-mode', 'bypassPermissions',
    '--sandbox', 'off',
    '--no-memory',
  ];
}

function createSemaphore(limit) {
  let active = 0;
  const queue = [];
  const drain = () => {
    while (active < limit && queue.length > 0) {
      const next = queue.shift();
      if (next.signal?.aborted) {
        next.reject(new Error('Task aborted before official Grok execution'));
        continue;
      }
      active += 1;
      next.resolve(() => {
        active = Math.max(0, active - 1);
        drain();
      });
    }
  };
  return {
    acquire(signal) {
      return new Promise((resolve, reject) => {
        const entry = { resolve, reject, signal, onAbort: null };
        entry.onAbort = () => {
          const index = queue.indexOf(entry);
          if (index >= 0) queue.splice(index, 1);
          reject(new Error('Task aborted while waiting for official Grok capacity'));
        };
        signal?.addEventListener('abort', entry.onAbort, { once: true });
        entry.resolve = (release) => {
          signal?.removeEventListener('abort', entry.onAbort);
          resolve(release);
        };
        queue.push(entry);
        drain();
      });
    },
    get active() { return active; },
    get queued() { return queue.length; },
  };
}

function terminateProcessGroup(child) {
  if (!child || child.exitCode !== null) return;
  try { child.kill('SIGTERM'); } catch { /* already gone */ }
  if (child.pid) {
    try { process.kill(-child.pid, 'SIGTERM'); } catch { /* not a process-group leader */ }
  }
  setTimeout(() => {
    if (child.exitCode !== null) return;
    try { child.kill('SIGKILL'); } catch { /* already gone */ }
    if (child.pid) {
      try { process.kill(-child.pid, 'SIGKILL'); } catch { /* not a process-group leader */ }
    }
  }, 5000).unref();
}

function cleanOfficialEnvironment(task, selfId) {
  const env = bridgeEnvironmentForTask(task, selfId, { ...process.env, NO_COLOR: '1' });
  for (const key of [
    'ANTHROPIC_API_KEY',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY',
    'GOOGLE_API_KEY',
    'GOOGLE_APPLICATION_CREDENTIALS',
  ]) delete env[key];
  return env;
}

export function createOfficialGrokExecutor({
  binary = 'grok',
  model = OFFICIAL_GROK_MODEL,
  reasoningEffort = OFFICIAL_GROK_REASONING_EFFORT,
  selfId = 'grok',
  workspace = process.cwd(),
  systemPrompt = '',
  peers = {},
  taskManager,
  cliToolWrapper,
  dispatchTool,
  normalizeToolOutput,
  maxToolRounds = 15,
  maxProcesses = 2,
  cliTimeoutMs = 900_000,
  initialProbe = null,
} = {}) {
  const semaphore = createSemaphore(Math.max(1, maxProcesses));
  const healthState = {
    configuredModel: model,
    modelPolicy: 'fixed',
    reasoningEffort,
    modelVerified: Boolean(initialProbe?.authenticated && initialProbe?.modelAvailable),
    authenticated: Boolean(initialProbe?.authenticated),
    modelAvailable: Boolean(initialProbe?.modelAvailable),
    lastObservedModel: null,
    lastObservedAt: null,
    lastProbeAt: initialProbe ? new Date().toISOString() : null,
    lastProbeError: initialProbe?.error || null,
  };

  function refreshProbe() {
    const probe = probeOfficialGrok(binary, model);
    healthState.authenticated = probe.authenticated;
    healthState.modelAvailable = probe.modelAvailable;
    healthState.modelVerified = probe.authenticated && probe.modelAvailable;
    healthState.lastProbeAt = new Date().toISOString();
    healthState.lastProbeError = probe.error;
    return probe;
  }

  async function runRound(task, prompt, round, onChunk, signal, allTextRef) {
    if (signal?.aborted || task.status?.state === 'canceled') throw new Error('Task aborted');
    const probe = refreshProbe();
    if (!probe.authenticated) {
      throw new Error('official_grok_not_authenticated: execute `grok login` no terminal e tente novamente');
    }
    if (!probe.modelAvailable) {
      throw new Error(`official_grok_model_unavailable: ${model}`);
    }

    const toolPrefix = cliToolWrapper?.buildA2AToolPrefix(peers, task.metadata?.maxDepth ?? 7) || '';
    const governedPrompt = `${systemPrompt}\n\n${toolPrefix}${prompt}`.trim();
    const promptDirectory = fs.mkdtempSync(path.join(os.tmpdir(), 'a2a-grok-official-'));
    const promptFile = path.join(promptDirectory, 'prompt.md');
    fs.writeFileSync(promptFile, governedPrompt, { encoding: 'utf8', mode: 0o600 });
    const args = buildOfficialGrokArgs({ model, workspace, reasoningEffort, promptFile });

    try {
      const outcome = await new Promise((resolve, reject) => {
        const child = spawn(binary, args, {
          cwd: workspace,
          stdio: ['ignore', 'pipe', 'pipe'],
          env: cleanOfficialEnvironment(task, selfId),
          detached: true,
        });
        task.process = child;
        let buffer = '';
        let stderr = '';
        let terminal = false;
        let streamedText = '';
        let sessionId = null;
        let observedModel = null;
        const progressFilter = cliToolWrapper?.createToolCallStreamFilter?.();

        const onAbort = () => terminateProcessGroup(child);
        signal?.addEventListener('abort', onAbort, { once: true });
        const timer = setTimeout(() => terminateProcessGroup(child), cliTimeoutMs);
        let spawnError = null;
        const cleanupProcess = () => {
          clearTimeout(timer);
          signal?.removeEventListener('abort', onAbort);
          task.process = null;
        };

        const consumeLine = (line) => {
          const parsed = parseOfficialGrokStreamLine(line);
          if (!parsed) return;
          if (parsed.model) observedModel = parsed.model;
          if (parsed.sessionId) sessionId = parsed.sessionId;
          if (parsed.isError) stderr += `${parsed.error || 'official Grok returned an error'}\n`;
          if (parsed.text) {
            streamedText += parsed.text;
            const visibleDelta = progressFilter ? progressFilter.push(parsed.text) : parsed.text;
            if (visibleDelta) {
              onChunk?.({ type: 'progress', text: visibleDelta });
              taskManager.taskEmitter.emit(`task:${task.id}:chunk`, visibleDelta);
            }
          }
          if (parsed.terminal) terminal = true;
        };

        child.stdout.on('data', (chunk) => {
          buffer += chunk.toString();
          const lines = buffer.split(/\r?\n/);
          buffer = lines.pop() || '';
          for (const line of lines) consumeLine(line);
        });
        child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });
        child.on('error', (error) => {
          spawnError = error;
          cleanupProcess();
          reject(error);
        });
        child.on('close', (code, closeSignal) => {
          cleanupProcess();
          if (spawnError) return;
          if (buffer.trim()) consumeLine(buffer);
          const visibleTail = progressFilter?.flush?.() || '';
          if (visibleTail) {
            onChunk?.({ type: 'progress', text: visibleTail });
            taskManager.taskEmitter.emit(`task:${task.id}:chunk`, visibleTail);
          }
          if (signal?.aborted || task.status?.state === 'canceled') return reject(new Error('Task aborted'));
          if (code !== 0) return reject(new Error(`official Grok CLI exited with code ${code}${closeSignal ? ` (${closeSignal})` : ''}: ${stderr.trim() || 'no diagnostic'}`));
          if (!terminal) return reject(new Error('incomplete_stream: official Grok CLI exited without an end event'));
          if (!streamedText.trim()) return reject(new Error('official Grok CLI returned an empty result'));
          const effectiveModel = observedModel || model;
          healthState.lastObservedModel = effectiveModel;
          healthState.lastObservedAt = new Date().toISOString();
          healthState.modelVerified = effectiveModel === model;
          resolve({ text: streamedText, observedModel: effectiveModel, sessionId });
        });
      });

      const toolCall = cliToolWrapper?.parseToolCall(outcome.text);
      if (toolCall && round < maxToolRounds) {
        if (signal?.aborted || task.status?.state === 'canceled') throw new Error('Task aborted');
        let result;
        try {
          result = await dispatchTool(toolCall.name, toolCall.input, {
            depth: task.metadata?.maxDepth ?? 7,
            meshChain: task.metadata?.meshChain || [],
            taskId: task.id,
            selfCallDepth: task.metadata?.selfCallDepth || 0,
          });
        } catch (error) {
          result = `Tool error: ${error.message}`;
        }
        if (toolCall.beforeCall) allTextRef.value += `${toolCall.beforeCall}\n`;
        const followUp = cliToolWrapper.buildFollowUpPrompt(
          prompt,
          outcome.text,
          toolCall.name,
          normalizeToolOutput(result),
        );
        return runRound(task, followUp, round + 1, onChunk, signal, allTextRef);
      }

      allTextRef.value += cliToolWrapper ? cliToolWrapper.removeToolCalls(outcome.text) : outcome.text;
      return outcome;
    } finally {
      fs.rmSync(promptDirectory, { recursive: true, force: true });
    }
  }

  async function executeTask(task, onChunk, runContext = {}) {
    const signal = runContext.signal;
    taskManager.updateTask(task, { status: { state: 'working' } });
    let release;
    try {
      release = await semaphore.acquire(signal);
      const prompt = task.history[0]?.parts?.filter((part) => part.type === 'text').map((part) => part.text).join('\n') || '';
      const allText = { value: '' };
      const outcome = await runRound(task, prompt, 0, onChunk, signal, allText);
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const text = allText.value.trim();
      const artifacts = extractResponseArtifacts(text, { taskId: task.id, agentId: selfId });
      const agentMessage = { role: 'agent', parts: [{ type: 'text', text: stripArtifactDeclarations(text) }] };
      taskManager.updateTask(task, {
        status: { state: 'completed', message: agentMessage },
        history: [...task.history, agentMessage],
        artifacts: mergeArtifacts(task.artifacts || [], artifacts),
        metadata: {
          ...task.metadata,
          observedModel: outcome.observedModel,
          providerSessionId: outcome.sessionId || task.metadata?.providerSessionId,
          providerRuntime: 'grok-official',
          providerRoute: 'official',
        },
      });
      onChunk?.({ type: 'completed', task: taskManager.taskToJSON(task) });
    } catch (error) {
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const message = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar Grok pela CLI oficial: ${error.message}` }] };
      taskManager.updateTask(task, {
        status: { state: 'failed', message },
        history: [...task.history, message],
      });
      onChunk?.({ type: 'failed', task: taskManager.taskToJSON(task) });
    } finally {
      release?.();
    }
  }

  return {
    executeTask,
    healthState,
    concurrency: semaphore,
    refreshProbe,
  };
}
