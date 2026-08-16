import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawn, spawnSync } from 'node:child_process';

import { bridgeEnvironmentForTask } from './bridge-context.js';

function abortError() {
  const error = new Error('Task aborted');
  error.name = 'AbortError';
  return error;
}

function delay(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(abortError());
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(timer);
      reject(abortError());
    }, { once: true });
  });
}

function createSemaphore(limit) {
  let active = 0;
  const queue = [];
  const drain = () => {
    while (active < limit && queue.length) {
      const next = queue.shift();
      if (next.signal?.aborted) { next.reject(abortError()); continue; }
      active += 1;
      next.resolve(() => { active = Math.max(0, active - 1); drain(); });
    }
  };
  return {
    acquire(signal) {
      return new Promise((resolve, reject) => {
        const entry = { signal, reject, resolve: null, onAbort: null };
        entry.onAbort = () => {
          const index = queue.indexOf(entry);
          if (index >= 0) queue.splice(index, 1);
          reject(abortError());
        };
        entry.resolve = (release) => {
          signal?.removeEventListener('abort', entry.onAbort);
          resolve(release);
        };
        signal?.addEventListener('abort', entry.onAbort, { once: true });
        queue.push(entry);
        drain();
      });
    },
    get active() { return active; },
    get queued() { return queue.length; },
  };
}

async function acquireFileLock(lockPath, signal, timeoutMs) {
  const deadline = Date.now() + timeoutMs;
  fs.mkdirSync(path.dirname(lockPath), { recursive: true });
  while (Date.now() < deadline) {
    if (signal?.aborted) throw abortError();
    try {
      const fd = fs.openSync(lockPath, 'wx', 0o600);
      fs.writeFileSync(fd, `${process.pid}\n`);
      return () => {
        try { fs.closeSync(fd); } catch { /* already closed */ }
        try { fs.unlinkSync(lockPath); } catch { /* already released */ }
      };
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
      try {
        const age = Date.now() - fs.statSync(lockPath).mtimeMs;
        if (age > Math.max(timeoutMs, 2_100_000)) fs.unlinkSync(lockPath);
      } catch { /* another process released it */ }
      await delay(150, signal);
    }
  }
  throw new Error(`Timeout waiting for shared CLI lock: ${lockPath}`);
}

function terminateProcessGroup(child) {
  if (!child || child.exitCode !== null) return;
  try { child.kill('SIGTERM'); } catch { /* already gone */ }
  if (child.pid) {
    try { process.kill(-child.pid, 'SIGTERM'); } catch { /* not a group leader */ }
  }
  setTimeout(() => {
    if (child.exitCode !== null) return;
    try { child.kill('SIGKILL'); } catch { /* already gone */ }
    if (child.pid) {
      try { process.kill(-child.pid, 'SIGKILL'); } catch { /* not a group leader */ }
    }
  }, 5000).unref();
}

function deepText(value) {
  if (typeof value === 'string') return value;
  if (Array.isArray(value)) return value.map(deepText).filter(Boolean).join('');
  if (!value || typeof value !== 'object') return '';
  for (const key of ['text', 'content', 'message', 'delta', 'response', 'result', 'output_text']) {
    const text = deepText(value[key]);
    if (text) return text;
  }
  return '';
}

export function parseOpenCodeStreamLine(line) {
  try {
    const event = JSON.parse(String(line || '').trim());
    if (!event || typeof event !== 'object') return null;
    const type = String(event.type || event.part?.type || '');
    return {
      raw: event,
      type,
      text: type === 'text' ? deepText(event.part?.text ?? event.text ?? event.part) : '',
      terminal: type === 'step_finish' || type === 'step-finish',
      isError: type === 'error' || event.error === true,
      error: deepText(event.error || event.message),
      sessionId: event.sessionID || event.sessionId || event.part?.sessionID || null,
      usage: event.part?.tokens || event.tokens || null,
      cost: event.part?.cost ?? event.cost ?? null,
    };
  } catch { return null; }
}

export function parseKimiStreamLine(line) {
  try {
    const event = JSON.parse(String(line || '').trim());
    if (!event || typeof event !== 'object') return null;
    const role = String(event.role || event.message?.role || '');
    const type = String(event.type || event.event || '');
    const assistant = role === 'assistant' || /assistant|message\.delta|content\.delta/i.test(type);
    const terminal = /result|turn\.end|message\.end|assistant\.final|system\.exit|finish/i.test(type);
    return {
      raw: event,
      type,
      text: assistant ? deepText(event.content ?? event.text ?? event.message ?? event.delta) : '',
      terminal,
      isError: role === 'error' || /error/i.test(type) || event.error === true,
      error: deepText(event.error || (role === 'error' ? event : '')),
      sessionId: event.session_id || event.sessionId || event.message?.session_id || null,
      usage: event.usage || event.stats || null,
      cost: event.cost ?? null,
    };
  } catch { return null; }
}

export function verifyOpenCodeModelAvailable(binary, model, { timeoutMs = 90_000 } = {}) {
  const result = spawnSync(binary, ['models'], { encoding: 'utf8', timeout: timeoutMs, env: process.env });
  if (result.error) throw new Error(`OpenCode model probe failed: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`OpenCode model probe failed (${result.status}): ${(result.stderr || '').trim()}`);
  const models = String(result.stdout || '').split(/\r?\n/).map(value => value.trim()).filter(Boolean);
  if (!models.includes(model)) throw new Error(`required OpenCode model is unavailable: ${model}`);
  return { verified: true, model, availableModels: models };
}

export function buildExternalCliArgs({ route, model, prompt }) {
  if (route === 'opencode') {
    return ['run', '--model', model, '--variant', 'max', '--format', 'json', '--auto', prompt];
  }
  if (route === 'kimi-code') {
    return ['--model', model, '--prompt', prompt, '--output-format', 'stream-json'];
  }
  throw new Error(`Unsupported external CLI route: ${route}`);
}

export function createExternalCliExecutor({
  binary,
  model,
  route,
  selfId,
  displayName,
  workspace = os.homedir(),
  systemPrompt = '',
  peers = {},
  taskManager,
  cliToolWrapper,
  dispatchTool,
  normalizeToolOutput,
  maxToolRounds = 15,
  maxProcesses = 1,
  cliTimeoutMs = 1_800_000,
  bootModelVerified = false,
  sharedLockPath = route === 'opencode' ? path.join(os.tmpdir(), 'a2a-opencode-go.lock') : '',
} = {}) {
  const semaphore = createSemaphore(Math.max(1, maxProcesses));
  const parser = route === 'opencode' ? parseOpenCodeStreamLine : parseKimiStreamLine;
  const healthState = {
    configuredModel: model,
    modelPolicy: 'fixed',
    modelVerified: Boolean(bootModelVerified),
    lastObservedModel: null,
    lastObservedAt: null,
    lastUsage: null,
    lastCost: null,
  };

  async function runRound(task, prompt, round, onChunk, signal, allTextRef) {
    if (signal?.aborted || task.status?.state === 'canceled') throw abortError();
    const toolPrefix = cliToolWrapper?.buildA2AToolPrefix(peers, task.metadata?.maxDepth ?? 7) || '';
    const governedPrompt = `${systemPrompt}\n\n${toolPrefix}${prompt}`.trim();
    let releaseLock = null;
    if (sharedLockPath) releaseLock = await acquireFileLock(sharedLockPath, signal, cliTimeoutMs);
    try {
      const outcome = await new Promise((resolve, reject) => {
        const child = spawn(binary, buildExternalCliArgs({ route, model, prompt: governedPrompt }), {
          cwd: workspace,
          stdio: ['ignore', 'pipe', 'pipe'],
          env: bridgeEnvironmentForTask(task, selfId, { ...process.env, NO_COLOR: '1' }),
          detached: true,
        });
        task.process = child;
        let buffer = '';
        let stderr = '';
        let text = '';
        let streamed = '';
        let sessionId = null;
        let terminalSeen = false;
        let usage = null;
        let cost = null;
        let eventError = null;
        const progressFilter = cliToolWrapper?.createToolCallStreamFilter?.();
        const onAbort = () => terminateProcessGroup(child);
        signal?.addEventListener('abort', onAbort, { once: true });
        const timer = setTimeout(() => terminateProcessGroup(child), cliTimeoutMs);
        const cleanup = () => {
          clearTimeout(timer);
          signal?.removeEventListener('abort', onAbort);
          task.process = null;
        };
        const emitText = (candidate) => {
          if (!candidate) return;
          let delta = candidate;
          if (candidate.startsWith(streamed)) delta = candidate.slice(streamed.length);
          if (!delta) return;
          streamed += delta;
          text += delta;
          const visible = progressFilter ? progressFilter.push(delta) : delta;
          if (visible) {
            onChunk?.({ type: 'progress', text: visible });
            taskManager.taskEmitter.emit(`task:${task.id}:chunk`, visible);
          }
        };
        const consume = (line) => {
          const parsed = parser(line);
          if (!parsed) return;
          emitText(parsed.text);
          if (parsed.terminal) terminalSeen = true;
          if (parsed.isError) eventError = parsed.error || `${displayName} returned an error event`;
          sessionId = parsed.sessionId || sessionId;
          usage = parsed.usage || usage;
          cost = parsed.cost ?? cost;
        };
        child.stdout.on('data', chunk => {
          buffer += chunk.toString();
          const lines = buffer.split(/\r?\n/);
          buffer = lines.pop() || '';
          for (const line of lines) consume(line);
        });
        child.stderr.on('data', chunk => { stderr += chunk.toString(); });
        child.once('error', error => { cleanup(); reject(error); });
        child.once('close', (code, closeSignal) => {
          cleanup();
          if (buffer.trim()) consume(buffer);
          const tail = progressFilter?.flush?.() || '';
          if (tail) {
            onChunk?.({ type: 'progress', text: tail });
            taskManager.taskEmitter.emit(`task:${task.id}:chunk`, tail);
          }
          if (signal?.aborted || task.status?.state === 'canceled') return reject(abortError());
          if (code !== 0) return reject(new Error(`${displayName} CLI exited with code ${code}${closeSignal ? ` (${closeSignal})` : ''}: ${stderr.trim() || eventError || 'no diagnostic'}`));
          if (eventError) return reject(new Error(eventError));
          if (!text.trim()) return reject(new Error(`${displayName} CLI returned empty output${terminalSeen ? '' : ' without a terminal event'}`));
          resolve({ text: text.trim(), sessionId, usage, cost, terminalSeen });
        });
      });

      // The shared OpenCode database lock covers only the provider process.
      // Release it before a possible recursive A2A tool round reacquires it.
      releaseLock?.();
      releaseLock = null;

      healthState.modelVerified = true;
      healthState.lastObservedModel = model;
      healthState.lastObservedAt = new Date().toISOString();
      healthState.lastUsage = outcome.usage;
      healthState.lastCost = outcome.cost;
      const toolCall = cliToolWrapper?.parseToolCall(outcome.text);
      if (toolCall && round < maxToolRounds) {
        let result;
        try {
          result = await dispatchTool(toolCall.name, toolCall.input, {
            depth: task.metadata?.maxDepth ?? 7,
            meshChain: task.metadata?.meshChain || [],
            taskId: task.id,
            selfCallDepth: task.metadata?.selfCallDepth || 0,
          });
        } catch (error) { result = `Tool error: ${error.message}`; }
        if (toolCall.beforeCall) allTextRef.value += `${toolCall.beforeCall}\n`;
        return runRound(task, cliToolWrapper.buildFollowUpPrompt(prompt, outcome.text, toolCall.name, normalizeToolOutput(result)), round + 1, onChunk, signal, allTextRef);
      }
      allTextRef.value += cliToolWrapper ? cliToolWrapper.removeToolCalls(outcome.text) : outcome.text;
      return outcome;
    } finally {
      releaseLock?.();
    }
  }

  async function executeTask(task, onChunk, runContext = {}) {
    const signal = runContext.signal;
    taskManager.updateTask(task, { status: { state: 'working' } });
    let release;
    try {
      release = await semaphore.acquire(signal);
      const prompt = task.history[0]?.parts?.filter(part => part.type === 'text').map(part => part.text).join('\n') || '';
      const allText = { value: '' };
      const outcome = await runRound(task, prompt, 0, onChunk, signal, allText);
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const message = { role: 'agent', parts: [{ type: 'text', text: allText.value.trim() }] };
      taskManager.updateTask(task, {
        status: { state: 'completed', message },
        history: [...task.history, message],
        metadata: {
          ...task.metadata,
          observedModel: model,
          providerSessionId: outcome.sessionId || task.metadata?.providerSessionId,
          providerRuntime: route,
          usage: outcome.usage || task.metadata?.usage,
          cost: outcome.cost ?? task.metadata?.cost,
        },
      });
      onChunk?.({ type: 'completed', task: taskManager.taskToJSON(task) });
    } catch (error) {
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const message = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar ${displayName}: ${error.message}` }] };
      taskManager.updateTask(task, { status: { state: 'failed', message }, history: [...task.history, message] });
      onChunk?.({ type: 'failed', task: taskManager.taskToJSON(task) });
    } finally { release?.(); }
  }

  return { executeTask, healthState, concurrency: semaphore };
}
