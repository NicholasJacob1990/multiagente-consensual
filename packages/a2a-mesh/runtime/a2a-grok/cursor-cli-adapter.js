// ============================================
// Cursor/Grok CLI adapter — fixed model, stream-json and fail-closed execution
// ============================================

import { spawn, spawnSync } from 'node:child_process';
import os from 'node:os';
import { bridgeEnvironmentForTask } from '../a2a-shared/bridge-context.js';

export const REQUIRED_GROK_MODEL = 'cursor-grok-4.6-high';

export function normalizeModelLabel(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/[^a-z0-9.]+/g, ' ')
    .trim()
    .replace(/\s+/g, ' ');
}

export function modelLabelsMatch(configuredModel, observedLabel) {
  return normalizeModelLabel(configuredModel) === normalizeModelLabel(observedLabel);
}

export function extractCursorText(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) {
    return value.map((item) => extractCursorText(item)).filter(Boolean).join('');
  }
  if (!value || typeof value !== 'object') return '';
  if (typeof value.text === 'string') return value.text;
  if (typeof value.result === 'string') return value.result;
  return extractCursorText(value.content || value.message || value.delta || '');
}

export function parseCursorStreamLine(line) {
  try {
    const event = JSON.parse(String(line || '').trim());
    if (!event || typeof event !== 'object') return null;
    return {
      raw: event,
      type: event.type || '',
      subtype: event.subtype || '',
      model: event.type === 'system' && event.subtype === 'init' ? event.model || null : null,
      text: event.type === 'assistant' ? extractCursorText(event.message || event.content) : '',
      terminal: event.type === 'result',
      isError: event.type === 'result' ? Boolean(event.is_error || event.subtype === 'error') : false,
      result: event.type === 'result' ? extractCursorText(event.result || event.message || event.content) : '',
      sessionId: event.session_id || null,
    };
  } catch {
    return null;
  }
}

export function verifyCursorModelAvailable(binary, model = REQUIRED_GROK_MODEL, { timeoutMs = 90000 } = {}) {
  const result = spawnSync(binary, ['--list-models'], {
    encoding: 'utf8',
    timeout: timeoutMs,
    env: process.env,
  });
  if (result.error) throw new Error(`cursor-agent model probe failed: ${result.error.message}`);
  if (result.status !== 0) {
    throw new Error(`cursor-agent --list-models failed (${result.status}): ${(result.stderr || result.stdout || '').trim()}`);
  }
  const ids = String(result.stdout || '')
    .split(/\r?\n/)
    .map((line) => line.trim().split(/\s+-\s+|\s+/)[0])
    .filter(Boolean);
  if (!ids.includes(model)) {
    throw new Error(`required Cursor model is unavailable: ${model}`);
  }
  return { verified: true, model, availableModels: ids };
}

export function buildCursorArgs({ model = REQUIRED_GROK_MODEL, workspace = process.cwd() } = {}) {
  return [
    '--print',
    '--force',
    '--sandbox', 'disabled',
    '--trust',
    '--workspace', workspace,
    '--output-format', 'stream-json',
    '--stream-partial-output',
    '--model', model,
  ];
}

function createSemaphore(limit) {
  let active = 0;
  const queue = [];
  const drain = () => {
    while (active < limit && queue.length > 0) {
      const next = queue.shift();
      if (next.signal?.aborted) {
        next.reject(new Error('Task aborted before Cursor execution'));
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
          reject(new Error('Task aborted while waiting for Cursor capacity'));
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

function cleanCursorEnvironment(task, selfId) {
  const env = bridgeEnvironmentForTask(task, selfId, { ...process.env, NO_COLOR: '1' });
  for (const key of [
    'ANTHROPIC_API_KEY',
    'OPENAI_API_KEY',
    'GEMINI_API_KEY',
    'GOOGLE_API_KEY',
    'GOOGLE_APPLICATION_CREDENTIALS',
    'XAI_API_KEY',
  ]) delete env[key];
  return env;
}

export function createCursorExecutor({
  binary = 'cursor-agent',
  model = REQUIRED_GROK_MODEL,
  selfId = 'grok',
  workspace = process.env.A2A_GROK_WORKSPACE || process.cwd(),
  systemPrompt = '',
  peers = {},
  taskManager,
  cliToolWrapper,
  dispatchTool,
  normalizeToolOutput,
  maxToolRounds = 15,
  maxProcesses = 2,
  cliTimeoutMs = 900000,
  bootModelVerified = false,
} = {}) {
  const semaphore = createSemaphore(Math.max(1, maxProcesses));
  const healthState = {
    configuredModel: model,
    modelPolicy: 'fixed',
    modelVerified: Boolean(bootModelVerified),
    lastObservedModel: null,
    lastObservedAt: null,
  };

  async function runRound(task, prompt, round, onChunk, signal, allTextRef) {
    if (signal?.aborted || task.status?.state === 'canceled') throw new Error('Task aborted');
    const toolPrefix = cliToolWrapper?.buildA2AToolPrefix(peers, task.metadata?.maxDepth ?? 7) || '';
    const governedPrompt = `${systemPrompt}\n\n${toolPrefix}${prompt}`.trim();
    const args = buildCursorArgs({ model, workspace });

    const outcome = await new Promise((resolve, reject) => {
      const child = spawn(binary, args, {
        cwd: workspace,
        stdio: ['pipe', 'pipe', 'pipe'],
        env: cleanCursorEnvironment(task, selfId),
        detached: true,
      });
      task.process = child;
      let buffer = '';
      let stderr = '';
      let observedModel = null;
      let terminal = null;
      let streamedText = '';
      let modelError = null;
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
        const parsed = parseCursorStreamLine(line);
        if (!parsed) return;
        if (parsed.model) {
          observedModel = parsed.model;
          healthState.lastObservedModel = parsed.model;
          healthState.lastObservedAt = new Date().toISOString();
          if (!modelLabelsMatch(model, parsed.model)) {
            healthState.modelVerified = false;
            modelError = new Error(`model_mismatch: configured=${model} observed=${parsed.model}`);
            terminateProcessGroup(child);
          } else {
            healthState.modelVerified = true;
          }
        }
        if (parsed.text) {
          let delta = parsed.text;
          if (parsed.text.startsWith(streamedText)) delta = parsed.text.slice(streamedText.length);
          if (delta) {
            streamedText += delta;
            const visibleDelta = progressFilter ? progressFilter.push(delta) : delta;
            if (visibleDelta) {
              onChunk?.({ type: 'progress', text: visibleDelta });
              taskManager.taskEmitter.emit(`task:${task.id}:chunk`, visibleDelta);
            }
          }
        }
        if (parsed.terminal) terminal = parsed;
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
        if (modelError) return reject(modelError);
        if (signal?.aborted || task.status?.state === 'canceled') return reject(new Error('Task aborted'));
        if (code !== 0) return reject(new Error(`Cursor exited with code ${code}${closeSignal ? ` (${closeSignal})` : ''}: ${stderr.trim() || 'no diagnostic'}`));
        if (!observedModel) return reject(new Error('model_unconfirmed: Cursor stream omitted system/init.model'));
        if (!terminal) return reject(new Error('incomplete_stream: Cursor exited without a result event'));
        if (terminal.isError) return reject(new Error(terminal.result || stderr.trim() || 'Cursor returned an error result'));
        const resultText = terminal.result;
        if (!resultText.trim()) return reject(new Error('Cursor returned an empty terminal result'));
        resolve({ text: resultText, observedModel, sessionId: terminal.sessionId });
      });
      child.stdin.end(`${governedPrompt}\n`);
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
      const agentMessage = { role: 'agent', parts: [{ type: 'text', text }] };
      taskManager.updateTask(task, {
        status: { state: 'completed', message: agentMessage },
        history: [...task.history, agentMessage],
        metadata: {
          ...task.metadata,
          observedModel: outcome.observedModel,
          providerSessionId: outcome.sessionId || task.metadata?.providerSessionId,
          providerRuntime: 'cursor',
        },
      });
      onChunk?.({ type: 'completed', task: taskManager.taskToJSON(task) });
    } catch (error) {
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const message = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar Grok pelo Cursor: ${error.message}` }] };
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
  };
}
