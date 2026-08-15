// ============================================
// Agent CLI Sandbox — PTY sessions for original CLIs
// ============================================

import os from 'os';
import path from 'path';
import { randomUUID } from 'crypto';
import { execFile, spawn as spawnChild } from 'child_process';

const DEFAULT_COLS = 120;
const DEFAULT_ROWS = 32;
const MAX_TRANSCRIPT_CHARS = 2_000_000;

const AGENT_COMMANDS = Object.freeze({
  claude: {
    command: process.env.A2A_SANDBOX_CLAUDE_CMD || 'claude',
    args: (process.env.A2A_SANDBOX_CLAUDE_ARGS || '').split(/\s+/).filter(Boolean),
    env: (env) => {
      const clean = { ...env, NO_COLOR: env.A2A_SANDBOX_COLOR === '1' ? undefined : '1' };
      delete clean.ANTHROPIC_API_KEY;
      delete clean.CLAUDECODE;
      delete clean.CLAUDE_CODE_ENTRYPOINT;
      return clean;
    },
  },
  codex: {
    command: process.env.A2A_SANDBOX_CODEX_CMD || 'codex',
    args: (process.env.A2A_SANDBOX_CODEX_ARGS || '').split(/\s+/).filter(Boolean),
    env: (env) => ({ ...env, NO_COLOR: env.A2A_SANDBOX_COLOR === '1' ? undefined : '1' }),
  },
  gemini: {
    command: process.env.A2A_SANDBOX_GEMINI_CMD || 'gemini',
    args: (process.env.A2A_SANDBOX_GEMINI_ARGS || '').split(/\s+/).filter(Boolean),
    env: (env) => ({ ...env, A2A_SUPPRESS_HOOKS: env.A2A_SUPPRESS_HOOKS || '1' }),
  },
  grok: {
    command: process.env.A2A_SANDBOX_GROK_CMD || 'cursor-agent',
    args: (process.env.A2A_SANDBOX_GROK_ARGS || '--force --sandbox disabled --trust --model cursor-grok-4.6-high').split(/\s+/).filter(Boolean),
    env: (env) => {
      const clean = { ...env, NO_COLOR: env.A2A_SANDBOX_COLOR === '1' ? undefined : '1' };
      for (const key of ['ANTHROPIC_API_KEY', 'OPENAI_API_KEY', 'GEMINI_API_KEY', 'GOOGLE_API_KEY', 'GOOGLE_APPLICATION_CREDENTIALS', 'XAI_API_KEY']) delete clean[key];
      return clean;
    },
  },
});

function normalizeAgent(agent) {
  return String(agent || '').trim().toLowerCase();
}

function normalizeSize(value, fallback) {
  const n = Number(value);
  if (!Number.isFinite(n) || n <= 0) return fallback;
  return Math.max(10, Math.min(500, Math.floor(n)));
}

async function loadNodePty() {
  try {
    return await import('node-pty');
  } catch (err) {
    throw new Error(`node-pty is required for /sandbox. Run npm install first. (${err.message})`);
  }
}

function execFileQuiet(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    execFile(command, args, options, (error, stdout, stderr) => {
      if (error) {
        error.stdout = stdout;
        error.stderr = stderr;
        reject(error);
        return;
      }
      resolve({ stdout, stderr });
    });
  });
}

function shellQuote(value) {
  return `'${String(value).replace(/'/g, `'\\''`)}'`;
}

function buildShellCommand(command, args) {
  return [command, ...args].map(shellQuote).join(' ');
}

function sendLiteralToTmux(target, data) {
  const parts = String(data ?? '').split('\n');
  parts.forEach((part, index) => {
    if (part) spawnChild('tmux', ['send-keys', '-t', target, '-l', part], { stdio: 'ignore' });
    if (index < parts.length - 1) spawnChild('tmux', ['send-keys', '-t', target, 'Enter'], { stdio: 'ignore' });
  });
}

function createTmuxPtyModule() {
  return {
    spawn(command, args, options = {}) {
      const sessionName = `a2a-sandbox-${randomUUID().slice(0, 12)}`;
      const target = `${sessionName}:0.0`;
      const emitter = new EventTarget();
      let killed = false;
      let lastCapture = '';

      const shellCommand = buildShellCommand(command, args);
      const tmuxArgs = [
        'new-session',
        '-d',
        '-s', sessionName,
        '-x', String(options.cols || DEFAULT_COLS),
        '-y', String(options.rows || DEFAULT_ROWS),
        '-c', options.cwd || process.cwd(),
        '--',
        '/bin/zsh',
        '-lc',
        shellCommand,
      ];
      const result = spawnChild('tmux', tmuxArgs, {
        stdio: 'ignore',
        env: options.env || process.env,
      });

      const poll = setInterval(async () => {
        try {
          await execFileQuiet('tmux', ['has-session', '-t', sessionName]);
        } catch {
          if (!killed) {
            killed = true;
            clearInterval(poll);
            emitter.dispatchEvent(new CustomEvent('exit', { detail: { exitCode: 0, signal: null } }));
          }
          return;
        }

        try {
          const { stdout } = await execFileQuiet('tmux', ['capture-pane', '-pt', target, '-S', '-2000']);
          if (stdout !== lastCapture) {
            const data = stdout.startsWith(lastCapture) ? stdout.slice(lastCapture.length) : stdout;
            lastCapture = stdout;
            if (data) emitter.dispatchEvent(new CustomEvent('data', { detail: data }));
          }
        } catch {
          // Session may have exited between has-session and capture-pane.
        }
      }, 400);
      poll.unref?.();

      result.on('error', (error) => {
        if (!killed) {
          killed = true;
          clearInterval(poll);
          emitter.dispatchEvent(new CustomEvent('data', { detail: `Failed to start tmux sandbox: ${error.message}\n` }));
          emitter.dispatchEvent(new CustomEvent('exit', { detail: { exitCode: 1, signal: null } }));
        }
      });

      return {
        pid: result.pid,
        write(data) { sendLiteralToTmux(target, data); },
        resize(cols, rows) {
          spawnChild('tmux', ['resize-window', '-t', sessionName, '-x', String(cols), '-y', String(rows)], { stdio: 'ignore' });
        },
        kill() {
          spawnChild('tmux', ['kill-session', '-t', sessionName], { stdio: 'ignore' });
        },
        onData(handler) {
          const listener = (event) => handler(event.detail);
          emitter.addEventListener('data', listener);
          return { dispose: () => emitter.removeEventListener('data', listener) };
        },
        onExit(handler) {
          const listener = (event) => handler(event.detail);
          emitter.addEventListener('exit', listener);
          return { dispose: () => emitter.removeEventListener('exit', listener) };
        },
      };
    },
  };
}

async function loadRuntimePtyModule() {
  const backend = String(process.env.A2A_SANDBOX_BACKEND || 'tmux').toLowerCase();
  if (backend === 'node-pty') return await loadNodePty();
  return createTmuxPtyModule();
}

export function createSandboxManager({
  ptyModule = null,
  cwd = process.env.A2A_SANDBOX_CWD || path.join(os.homedir(), 'Documents', 'Aplicativos'),
  env = process.env,
} = {}) {
  const sessions = new Map();

  async function getPty() {
    return ptyModule || await loadRuntimePtyModule();
  }

  function publicSession(session) {
    return {
      id: session.id,
      agent: session.agent,
      command: session.command,
      args: session.args,
      cwd: session.cwd,
      pid: session.pid,
      state: session.state,
      createdAt: session.createdAt,
      exitedAt: session.exitedAt,
      exitCode: session.exitCode,
      signal: session.signal,
    };
  }

  function appendTranscript(session, data) {
    session.transcript += data;
    if (session.transcript.length > MAX_TRANSCRIPT_CHARS) {
      session.transcript = session.transcript.slice(-MAX_TRANSCRIPT_CHARS);
    }
  }

  function publish(session, event) {
    for (const subscriber of session.subscribers) {
      try { subscriber(event); } catch { /* stale UI subscriber */ }
    }
  }

  async function startSession({ agent, cols = DEFAULT_COLS, rows = DEFAULT_ROWS, sessionCwd, restart = false } = {}) {
    const normalizedAgent = normalizeAgent(agent);
    const spec = AGENT_COMMANDS[normalizedAgent];
    if (!spec) {
      throw new Error(`Unknown sandbox agent: ${agent}. Available: ${Object.keys(AGENT_COMMANDS).join(', ')}`);
    }

    if (restart) {
      for (const existing of sessions.values()) {
        if (existing.agent === normalizedAgent && existing.state === 'running') {
          kill(existing.id);
        }
      }
    }

    const pty = await getPty();
    const id = `${normalizedAgent}-${randomUUID()}`;
    const resolvedCwd = sessionCwd || cwd;
    const args = [...spec.args];
    const ptyProcess = pty.spawn(spec.command, args, {
      name: 'xterm-256color',
      cols: normalizeSize(cols, DEFAULT_COLS),
      rows: normalizeSize(rows, DEFAULT_ROWS),
      cwd: resolvedCwd,
      env: spec.env(env),
    });

    const session = {
      id,
      agent: normalizedAgent,
      command: spec.command,
      args,
      cwd: resolvedCwd,
      pid: ptyProcess.pid,
      ptyProcess,
      state: 'running',
      createdAt: new Date().toISOString(),
      exitedAt: null,
      exitCode: null,
      signal: null,
      transcript: '',
      subscribers: new Set(),
    };
    sessions.set(id, session);

    ptyProcess.onData((data) => {
      appendTranscript(session, data);
      publish(session, { type: 'data', data });
    });
    ptyProcess.onExit(({ exitCode, signal } = {}) => {
      session.state = 'exited';
      session.exitedAt = new Date().toISOString();
      session.exitCode = exitCode ?? null;
      session.signal = signal ?? null;
      publish(session, { type: 'exit', exitCode: session.exitCode, signal: session.signal });
    });

    return publicSession(session);
  }

  function getSession(id) {
    return sessions.get(id) || null;
  }

  function listSessions() {
    return [...sessions.values()].map(publicSession);
  }

  function write(id, data) {
    const session = getSession(id);
    if (!session) throw new Error(`Sandbox session not found: ${id}`);
    if (session.state !== 'running') throw new Error(`Sandbox session is not running: ${id}`);
    session.ptyProcess.write(String(data ?? ''));
  }

  function resize(id, { cols, rows } = {}) {
    const session = getSession(id);
    if (!session) throw new Error(`Sandbox session not found: ${id}`);
    if (session.state !== 'running') return;
    session.ptyProcess.resize(normalizeSize(cols, DEFAULT_COLS), normalizeSize(rows, DEFAULT_ROWS));
  }

  function kill(id) {
    const session = getSession(id);
    if (!session) throw new Error(`Sandbox session not found: ${id}`);
    if (session.state !== 'running') return;
    session.ptyProcess.kill();
  }

  function subscribe(id, subscriber) {
    const session = getSession(id);
    if (!session) throw new Error(`Sandbox session not found: ${id}`);
    session.subscribers.add(subscriber);
    if (session.transcript) subscriber({ type: 'data', data: session.transcript });
    if (session.state !== 'running') {
      subscriber({ type: 'exit', exitCode: session.exitCode, signal: session.signal });
    }
    return () => session.subscribers.delete(subscriber);
  }

  function getTranscript(id) {
    const session = getSession(id);
    if (!session) throw new Error(`Sandbox session not found: ${id}`);
    return session.transcript;
  }

  function closeAll() {
    for (const session of sessions.values()) {
      if (session.state === 'running') {
        try { session.ptyProcess.kill(); } catch { /* already gone */ }
      }
    }
  }

  return {
    startSession,
    listSessions,
    write,
    resize,
    kill,
    subscribe,
    getTranscript,
    closeAll,
  };
}
