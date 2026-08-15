// ============================================
// Local Tools — Shared tool executor for A2A servers
// ============================================

import fs from 'fs';
import os from 'os';
import path from 'path';
import { execFile } from 'child_process';
import { promisify } from 'util';

const execFileAsync = promisify(execFile);

/**
 * Create a tool executor with configurable output truncation.
 *
 * @param {Object} config
 * @param {boolean} config.truncateOutput - Truncate shell_exec/read_file output (Claude=true)
 * @param {number}  config.maxOutputChars - Max chars before truncation (default 50000)
 * @returns {function} executeTool(name, input, context)
 */
export function createToolExecutor({ truncateOutput = false, maxOutputChars = 50000 } = {}) {
  const SHELL_ENABLED = process.env.A2A_ENABLE_SHELL_EXEC !== 'false'; // enabled by default
  const SHELL_TIMEOUT_MS = parseInt(process.env.A2A_SHELL_TIMEOUT_MS || '120000', 10); // 2 min
  const SHELL_CWD_ROOT = (process.env.A2A_SHELL_CWD || '/').replace(/^~/, os.homedir());
  const SHELL_FULL_ACCESS = process.env.A2A_SHELL_FULL_ACCESS === 'true';
  const SHELL_ALLOWLIST = SHELL_FULL_ACCESS ? null : new Set(
    (process.env.A2A_SHELL_ALLOWLIST || 'ls,cat,rg,find,head,tail,pwd,echo,wc,tree,du,file,stat,grep,sort,uniq,diff,dirname,basename,realpath,which')
      .split(',')
      .map(s => s.trim())
      .filter(Boolean),
  );
  const SHELL_BLOCKED_PATTERN = SHELL_FULL_ACCESS ? null : /&&|;|\$\(|`/; // allow pipe (|) for chaining

  function maybeTruncate(text, label) {
    if (!truncateOutput || !text || text.length <= maxOutputChars) return text;
    return text.slice(0, maxOutputChars) + `\n[TRUNCATED: ${text.length} chars total${label ? `, ${label}` : ''}]`;
  }

  function resolveSafeShellCwd(inputCwd) {
    const requested = (inputCwd || SHELL_CWD_ROOT).replace(/^~/, os.homedir());
    if (SHELL_FULL_ACCESS) return path.resolve(requested);
    const root = path.resolve(SHELL_CWD_ROOT);
    const resolved = path.resolve(requested);
    const rel = path.relative(root, resolved);
    if (rel.startsWith('..') || path.isAbsolute(rel)) {
      throw new Error(`cwd outside allowed root (${root})`);
    }
    return resolved;
  }

  /**
   * Execute a local tool by name.
   * Does NOT handle a2a_call, a2a_broadcast, a2a_team — those are handled by the caller.
   */
  return async function executeTool(name, input = {}) {
    try {
      switch (name) {
        case 'shell_exec': {
          if (!SHELL_ENABLED) {
            return 'Error: shell_exec disabled by policy (set A2A_ENABLE_SHELL_EXEC=false to disable).';
          }

          const raw = String(input.command || '').trim();
          if (!raw) return 'Error: command is required';
          if (SHELL_BLOCKED_PATTERN && SHELL_BLOCKED_PATTERN.test(raw)) {
            return 'Error: command blocked by policy (operators &&, ;, $(), ` not allowed).';
          }

          // Validate all binaries in pipe chain
          const pipeSegments = raw.split(/\s*\|\s*/);
          if (SHELL_ALLOWLIST) {
            for (const seg of pipeSegments) {
              const bin = seg.split(/\s+/)[0];
              if (!SHELL_ALLOWLIST.has(bin)) {
                return `Error: command '${bin}' is not allowlisted. Allowed: ${[...SHELL_ALLOWLIST].join(', ')}`;
              }
            }
          }

          const cwd = resolveSafeShellCwd(input.cwd);

          if (pipeSegments.length > 1) {
            // Use shell for pipe commands (all binaries already validated)
            const { execFile: execFileCb } = await import('child_process');
            const { stdout } = await new Promise((resolve, reject) => {
              execFileCb('/bin/sh', ['-c', raw], {
                cwd,
                timeout: SHELL_TIMEOUT_MS,
                maxBuffer: 1024 * 1024 * 20,
                encoding: 'utf8',
                env: { ...process.env, NO_COLOR: '1' },
              }, (err, stdout, stderr) => {
                if (err) reject(err);
                else resolve({ stdout });
              });
            });
            return maybeTruncate(stdout, undefined) || '(no output)';
          }

          const parts = raw.split(/\s+/);
          const bin = parts[0];
          const args = parts.slice(1);

          const { stdout } = await execFileAsync(bin, args, {
            shell: false,
            cwd,
            timeout: SHELL_TIMEOUT_MS,
            maxBuffer: 1024 * 1024 * 20,
            encoding: 'utf8',
            env: { ...process.env, NO_COLOR: '1' },
          });
          return maybeTruncate(stdout, undefined) || '(no output)';
        }
        case 'read_file': {
          const resolved = input.path.replace(/^~/, os.homedir());
          const content = await fs.promises.readFile(resolved, 'utf8');
          return maybeTruncate(content, 'use search_content for specific patterns');
        }
        case 'write_file': {
          const resolved = input.path.replace(/^~/, os.homedir());
          const dir = path.dirname(resolved);
          await fs.promises.mkdir(dir, { recursive: true });
          await fs.promises.writeFile(resolved, input.content, 'utf8');
          return `Written ${input.content.length} chars to ${resolved}`;
        }
        case 'list_directory': {
          const resolved = input.path.replace(/^~/, os.homedir());
          const { stdout: lsOut } = await execFileAsync('ls', ['-la', '--', resolved], { encoding: 'utf8', timeout: 30000 });
          return lsOut.split('\n').slice(0, 2000).join('\n');
        }
        case 'directory_probe': {
          const resolved = (input.path || '').replace(/^~/, os.homedir());
          if (!resolved) return 'Error: path is required';

          const includeHidden = input.includeHidden !== false;
          const dirents = await fs.promises.readdir(resolved, { withFileTypes: true });
          const entries = includeHidden
            ? dirents
            : dirents.filter(d => !d.name.startsWith('.'));

          entries.sort((a, b) => a.name.localeCompare(b.name));

          const typeCounts = { files: 0, directories: 0, symlinks: 0, other: 0 };
          let newest = null;
          let skippedEntries = 0;

          for (const e of entries) {
            if (e.isSymbolicLink()) typeCounts.symlinks += 1;
            else if (e.isDirectory()) typeCounts.directories += 1;
            else if (e.isFile()) typeCounts.files += 1;
            else typeCounts.other += 1;

            const fullPath = path.join(resolved, e.name);
            try {
              const st = await fs.promises.lstat(fullPath);
              if (!newest || st.mtimeMs > newest.mtimeMs) {
                newest = { name: e.name, path: fullPath, mtimeMs: st.mtimeMs };
              }
            } catch {
              skippedEntries += 1;
            }
          }

          return {
            path: resolved,
            includeHidden,
            totalEntries: entries.length,
            newestByMtimeName: newest?.name || null,
            newestEntry: newest,
            typeCounts,
            skippedEntries,
            sample: entries.slice(0, 20).map(e => e.name),
          };
        }
        case 'search_content': {
          const resolved = (input.path || '.').replace(/^~/, os.homedir());
          const grepArgs = ['-rn'];
          if (input.glob) grepArgs.push(`--include=${input.glob}`);
          grepArgs.push('--', input.pattern, resolved);
          try {
            const { stdout: grepOut } = await execFileAsync('grep', grepArgs, { encoding: 'utf8', timeout: 60000 });
            return grepOut.split('\n').slice(0, 2000).join('\n') || 'No matches found.';
          } catch (e) {
            const stdout = typeof e?.stdout === 'string' ? e.stdout : e?.stdout?.toString?.() || '';
            return stdout || 'No matches found.';
          }
        }
        case 'web_search': {
          const searchUrl = `https://lite.duckduckgo.com/lite/?q=${encodeURIComponent(input.query)}`;
          const { stdout: html } = await execFileAsync('curl', ['-sL', searchUrl, '-H', 'User-Agent: Mozilla/5.0'], { encoding: 'utf8', timeout: 15000 });
          return html.replace(/<[^>]*>/g, '').split('\n').filter(l => l.trim()).slice(0, 200).join('\n');
        }
        case 'web_fetch': {
          const fetchUrl = input.url;
          if (/^file:/i.test(fetchUrl) || /^(https?:\/\/)?(127\.|10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.|169\.254\.|0\.0\.0\.0|localhost)/i.test(fetchUrl)) {
            return 'Error: blocked URL (internal/local addresses not allowed)';
          }
          const { stdout: rawHtml } = await execFileAsync('curl', ['-sL', '--', fetchUrl, '-H', 'User-Agent: Mozilla/5.0'], { encoding: 'utf8', timeout: 15000 });
          return rawHtml
            .replace(/<script[^>]*>[\s\S]*?<\/script>/gi, '')
            .replace(/<style[^>]*>[\s\S]*?<\/style>/gi, '')
            .replace(/<[^>]*>/g, '')
            .split('\n').filter(l => l.trim()).slice(0, 500).join('\n');
        }
        default:
          return `Unknown tool: ${name}`;
      }
    } catch (err) {
      const stdout = typeof err?.stdout === 'string' ? err.stdout : err?.stdout?.toString?.() || '';
      return `Error: ${err.message}\n${stdout}`;
    }
  };
}

/**
 * Canonical tool definitions (JSON Schema format).
 * Each provider converts these to their own format via formatTools().
 */
export const BASE_TOOLS = [
  {
    name: 'shell_exec',
    description: 'Execute a shell command and return output. Supports pipes (|). Allowed commands: ls, cat, rg, find, head, tail, pwd, echo, wc, tree, du, file, stat, grep, sort, uniq, diff, dirname, basename, realpath, which. Use to explore codebases, analyze directory structures, count files, etc.',
    parameters: {
      type: 'object',
      properties: {
        command: { type: 'string', description: 'Command string. Supports pipes (e.g. "find . -name *.py | wc -l"). No &&, ;, $() or backticks.' },
        cwd: { type: 'string', description: 'Working directory (absolute path or ~/...)' },
      },
      required: ['command'],
    },
  },
  {
    name: 'read_file',
    description: 'Read the full contents of a file. Use for source code analysis, config files, etc.',
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Absolute or ~/ path to the file' },
      },
      required: ['path'],
    },
  },
  {
    name: 'write_file',
    description: 'Write content to a file',
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Absolute or ~/ path to the file' },
        content: { type: 'string', description: 'Content to write' },
      },
      required: ['path', 'content'],
    },
  },
  {
    name: 'list_directory',
    description: 'List files and directories in a path (ls -la). Use to explore project structures and discover files.',
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Directory path' },
      },
      required: ['path'],
    },
  },
  {
    name: 'directory_probe',
    description: 'Inspect a directory with canonical metrics (entry count, newest item by mtime, type counts). Prefer this over ad-hoc ls pipelines when precision matters.',
    parameters: {
      type: 'object',
      properties: {
        path: { type: 'string', description: 'Directory path (absolute or ~/...)' },
        includeHidden: { type: 'boolean', description: 'Include hidden entries (default: true)' },
      },
      required: ['path'],
    },
  },
  {
    name: 'search_content',
    description: 'Search file contents for a regex pattern (grep -rn). Use to find functions, classes, imports, patterns across a codebase.',
    parameters: {
      type: 'object',
      properties: {
        pattern: { type: 'string', description: 'Regex pattern' },
        path: { type: 'string', description: 'File or directory to search' },
        glob: { type: 'string', description: 'File glob filter (e.g. "*.py")' },
      },
      required: ['pattern'],
    },
  },
  {
    name: 'web_search',
    description: 'Search the web using DuckDuckGo',
    parameters: {
      type: 'object',
      properties: {
        query: { type: 'string', description: 'Search query' },
      },
      required: ['query'],
    },
  },
  {
    name: 'web_fetch',
    description: 'Fetch a URL and return its content as text',
    parameters: {
      type: 'object',
      properties: {
        url: { type: 'string', description: 'URL to fetch' },
      },
      required: ['url'],
    },
  },
];

/**
 * A2A mesh tool definitions (canonical format).
 * @param {string[]} peerNames - Available peer IDs
 */
export function getMeshToolDefs(peerNames) {
  const peersStr = peerNames.join(', ');
  return [
    {
      name: 'a2a_call',
      description: `Call another AI agent to collaborate on a task. Available: ${peersStr}.`,
      parameters: {
        type: 'object',
        properties: {
          agent: { type: 'string', description: `Agent ID (${peersStr})` },
          prompt: { type: 'string', description: 'Task or question to send' },
          timeout_ms: { type: 'integer', description: 'Optional per-call timeout in milliseconds' },
        },
        required: ['agent', 'prompt'],
      },
    },
    {
      name: 'a2a_broadcast',
      description: `Call multiple AI agents IN PARALLEL. Available: ${peersStr}.`,
      parameters: {
        type: 'object',
        properties: {
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs (default: all)` },
          includeSelf: { type: 'boolean', description: 'Include orchestrator itself as participant (default: false)' },
          prompt: { type: 'string', description: 'Task or question to send' },
          timeout_ms: { type: 'integer', description: 'Optional per-call timeout in milliseconds' },
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_team',
      description: `Orchestrate a multi-agent workflow with sequential and parallel steps. Available: ${peersStr}.`,
      parameters: {
        type: 'object',
        properties: {
          name: { type: 'string', description: 'Workflow name' },
          steps: {
            type: 'array',
            items: {
              type: 'object',
              properties: {
                mode: { type: 'string', enum: ['parallel', 'sequential'] },
                agents: { type: 'array', items: { type: 'string' } },
                prompt: { type: 'string', description: 'Use {{previous}} for accumulated context' },
                includeSelf: { type: 'boolean', description: 'Override global includeSelf for this step' },
                timeout_ms: { type: 'integer', description: 'Optional timeout for this step in milliseconds' },
              },
              required: ['mode', 'agents', 'prompt'],
            },
          },
          context: { type: 'string', description: 'Initial shared context' },
          accumulate: { type: 'boolean', description: 'Accumulate outputs between steps (default true)' },
          includeSelf: { type: 'boolean', description: 'Include orchestrator in steps where listed in agents (default: false)' },
          timeout_ms: { type: 'integer', description: 'Optional default timeout for all team steps in milliseconds' },
        },
        required: ['steps'],
      },
    },
    {
      name: 'a2a_consensus',
      description: `Ask multiple agents the same question and synthesize a consensus answer with a judge. Available agents: ${peersStr}.`,
      parameters: {
        type: 'object',
        properties: {
          prompt: { type: 'string', description: 'Question or task to get consensus on' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs to consult (default: all)` },
          judge: { type: 'string', description: `Agent ID to act as judge (default: claude)` },
          quorum: { type: 'integer', description: 'Minimum valid independent responses (default: strict majority)' },
          timeout_ms: { type: 'integer', description: 'Optional timeout for internal calls in milliseconds' },
        },
        required: ['prompt'],
      },
    },
    {
      name: 'a2a_code_ensemble',
      description: `NxN cross-review code ensemble: all agents (${peersStr}) write code, review each other's submissions, revise based on feedback, then a judge synthesizes the best solution. Use for high-quality code generation.`,
      parameters: {
        type: 'object',
        properties: {
          task: { type: 'string', description: 'Coding task description' },
          language: { type: 'string', description: 'Programming language (default: python)' },
          rounds: { type: 'integer', description: 'Number of review+revise cycles (default: 1, recommended max: 6, exceptional max: 12)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Exact participant set (default: all)` },
          judge: { type: 'string', description: `Agent ID for final synthesis (default: round-robin)` },
          timeout_ms: { type: 'integer', description: 'Optional timeout for internal calls in milliseconds' },
        },
        required: ['task'],
      },
    },
    {
      name: 'a2a_debate',
      description: `Adversarial debate: agents (${peersStr}) argue different positions on a topic across multiple rounds, then a judge evaluates and picks a winner. Use for exploring trade-offs, evaluating architectures, or stress-testing ideas.`,
      parameters: {
        type: 'object',
        properties: {
          topic: { type: 'string', description: 'Debate topic or question' },
          rounds: { type: 'integer', description: 'Number of debate rounds (default: 4, recommended max: 18, exceptional max: 36)' },
          agents: { type: 'array', items: { type: 'string' }, description: `Agent IDs to debate (default: all)` },
          judge: { type: 'string', description: `Agent ID to judge the debate (default: claude)` },
          order: { type: 'string', enum: ['rotate', 'fixed'], description: 'Agent order strategy (default: rotate)' },
          timeout_ms: { type: 'integer', description: 'Optional timeout for internal calls in milliseconds' },
        },
        required: ['topic'],
      },
    },
  ];
}
