#!/usr/bin/env node

/**
 * A2A Codex Server (refactored)
 *
 * Uses shared modules from a2a-shared/ for HTTP server, task management,
 * local tools, and mesh communication. This file contains only
 * Codex-specific logic: OpenAI Responses API streaming, sandbox config,
 * tool format conversion, CLI fallback.
 */

import 'dotenv/config';
import https from 'https';
import fs from 'fs';
import os from 'os';
import path from 'node:path';
import { spawn } from 'child_process';

import { createA2AServer, extractPromptText, extractArtifacts } from '../a2a-shared/base-server.js';
import { BASE_TOOLS, getMeshToolDefs } from '../a2a-shared/local-tools.js';
import { createSharedRuntime } from '../a2a-shared/server-runtime.js';
import { loadA2AAuthToken } from '../a2a-shared/auth-token.js';
import { bridgeEnvironmentForTask } from '../a2a-shared/bridge-context.js';
import {
  buildDisabledSkillsOverride,
  prepareCodexRuntimeHome,
} from './codex-cli-isolation.js';

// ============================================
// CONFIG
// ============================================

const PORT = parseInt(process.env.A2A_PORT || '3141', 10);
const CODEX_API_MODEL = process.env.CODEX_API_MODEL || process.env.CODEX_MODEL || 'gpt-5.6-sol';
// Use the plain model id (not a '-codex' variant — those don't work with authenticated ChatGPT).
// 2026-07-25: bumped 5.5 -> 5.6-sol to match ~/.codex/config.toml.
const CODEX_CLI_MODEL = process.env.A2A_CODEX_CLI_MODEL || process.env.CODEX_CLI_MODEL || 'gpt-5.6-sol';
const CODEX_SANDBOX = process.env.CODEX_SANDBOX || 'danger-full-access';
// Esforço máximo solicitado para a rota Codex; continua configurável por ambiente.
const CODEX_REASONING_EFFORT = process.env.CODEX_REASONING_EFFORT || 'xhigh';
const OPENAI_API_KEY = process.env.OPENAI_API_KEY || '';
const USE_CLI = true; // Prefer CLI (gpt-5.6-sol) over API

const A2A_AUTH_TOKEN = loadA2AAuthToken();
const MAX_CONCURRENT_TASKS = parseInt(process.env.MAX_CONCURRENT_TASKS || '15', 10);
const MAX_TASKS = parseInt(process.env.MAX_TASKS || '200', 10);
const CODEX_CLI_TIMEOUT_MS = parseInt(process.env.CODEX_CLI_TIMEOUT_MS || '900000', 10);
const CODEX_RUNTIME_HOME = prepareCodexRuntimeHome();
const CODEX_SQLITE_HOME = process.env.A2A_CODEX_SQLITE_HOME || path.join(CODEX_RUNTIME_HOME, 'state');
const DISABLE_LOCAL_SKILLS = process.env.A2A_CODEX_DISABLE_LOCAL_SKILLS === 'true';
const DISABLED_SKILLS_OVERRIDE = DISABLE_LOCAL_SKILLS ? buildDisabledSkillsOverride() : '';
fs.mkdirSync(CODEX_SQLITE_HOME, { recursive: true });

// Mesh peers
const A2A_MESH_MAX_DEPTH = parseInt(process.env.A2A_MESH_MAX_DEPTH || '7', 10);
const SELF_ID = 'codex';
const {
  peers: A2A_PEERS,
  tm,
  meshCaller,
  meshStore,
  meshBus,
  teamExecutor,
  consensusExecutor,
  codeEnsembleExecutor,
  debateExecutor,
  planExecutor,
  dispatchTool,
  normalizeToolOutput,
  cliToolWrapper,
  peerDiscovery,
} = await createSharedRuntime({
  selfId: SELF_ID,
  authToken: A2A_AUTH_TOKEN,
  maxDepth: A2A_MESH_MAX_DEPTH,
  maxTasks: MAX_TASKS,
  maxConcurrent: MAX_CONCURRENT_TASKS,
  dataDir: process.env.A2A_CODEX_DATA_DIR,
});

// ============================================
// CODEX-SPECIFIC: Tool format & dispatch
// ============================================

// OpenAI Responses API format: { type: 'function', name, description, parameters }
function toResponsesFormat(tool) {
  return { type: 'function', name: tool.name, description: tool.description, parameters: tool.parameters };
}

function formatToolsForCodex(depth) {
  const localTools = BASE_TOOLS.map(toResponsesFormat);
  const meshTools = depth > 0 ? getMeshToolDefs(Object.keys(A2A_PEERS)).map(toResponsesFormat) : [];
  return [...localTools, ...meshTools];
}

// ============================================
// OPENAI RESPONSES API: Streaming
// ============================================

function openaiResponsesApiCall(input, tools, previousResponseId, onTextChunk, instructions, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('Request aborted'));

    const body = JSON.stringify({
      model: CODEX_API_MODEL,
      max_output_tokens: 100000,
      instructions: instructions || undefined,
      input,
      tools: tools && tools.length > 0 ? tools : undefined,
      previous_response_id: previousResponseId || undefined,
      stream: true,
    });

    const req = https.request({
      hostname: 'api.openai.com',
      port: 443,
      path: '/v1/responses',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${OPENAI_API_KEY}`,
      },
      signal,
    }, (res) => {
      if (res.statusCode !== 200) {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          try { resolve(JSON.parse(Buffer.concat(chunks).toString())); }
          catch (e) { reject(e); }
        });
        return;
      }

      let buffer = '';
      let textContent = '';
      const functionCalls = new Map();
      let responseId = null;

      res.on('data', (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw || raw === '[DONE]') continue;

          try {
            const evt = JSON.parse(raw);

            if (evt.type === 'response.created' && evt.response?.id) {
              responseId = evt.response.id;
            }

            if (evt.type === 'response.output_text.delta' && evt.delta) {
              textContent += evt.delta;
              if (onTextChunk) onTextChunk(evt.delta);
            }

            if (evt.type === 'response.output_item.added' && evt.item?.type === 'function_call') {
              functionCalls.set(evt.item.id, {
                call_id: evt.item.call_id,
                name: evt.item.name,
                arguments: '',
              });
            }

            if (evt.type === 'response.function_call_arguments.delta' && evt.item_id) {
              const fc = functionCalls.get(evt.item_id);
              if (fc) fc.arguments += evt.delta;
            }

            if (evt.type === 'response.function_call_arguments.done' && evt.item_id) {
              const fc = functionCalls.get(evt.item_id);
              if (fc) fc.arguments = evt.arguments;
            }

            if (evt.type === 'response.completed' && evt.response) {
              responseId = evt.response.id;
              for (const item of (evt.response.output || [])) {
                if (item.type === 'message') {
                  for (const c of (item.content || [])) {
                    if (c.type === 'output_text' && c.text && !textContent) {
                      textContent = c.text;
                    }
                  }
                }
                if (item.type === 'function_call' && !functionCalls.has(item.id)) {
                  functionCalls.set(item.id, {
                    call_id: item.call_id,
                    name: item.name,
                    arguments: item.arguments,
                  });
                }
              }
            }
          } catch (err) {
            console.warn('[openaiResponsesApiCall] Failed to parse streaming event', {
              error: err instanceof Error ? err.message : String(err),
              preview: String(line).slice(0, 200),
            });
          }
        }
      });

      res.on('end', () => {
        resolve({
          responseId,
          textContent,
          functionCalls: [...functionCalls.values()],
        });
      });
    });

    if (signal) {
      signal.addEventListener('abort', () => {
        req.destroy(new Error('Request aborted'));
      }, { once: true });
    }

    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

// ============================================
// SYSTEM PROMPT
// ============================================

const SYSTEM_PROMPT = `You are Codex running ${CODEX_CLI_MODEL} with ${CODEX_REASONING_EFFORT} reasoning through the Codex CLI, as a technical agent in an A2A (Agent-to-Agent) mesh. Never claim a different model or reasoning effort.

LOCAL TOOLS: shell_exec, read_file, search_content, list_directory, directory_probe.

MCPs AND SKILLS: you have access to the same MCPs configured in ~/.codex/config.toml (applescript, browsermcp, gdrive, macos-control, multiagent-debate, playwright, sei, tribunais, etc) and skills in ~/.codex/skills/. Use them freely when relevant — e.g. playwright for browser automation, gdrive for Drive files, sei/tribunais for legal data. Avoid session-workflow distractions (reading AGENTS.md, exploring repo by habit) unless the task explicitly asks for it.

A2A AGENTS AVAILABLE:
- claude: Anthropic Claude (Opus) — strong at synthesis, analysis, complex reasoning, writing
- gemini: Google Gemini — strong at reasoning, data analysis, research, detailed explanations
- grok: xAI Grok 4.6 High, exclusively through Cursor CLI — strong at adversarial review and exposing fragile assumptions

WHEN TO USE EACH A2A TOOL:
- a2a_call: Query ONE specific agent for a directed task (e.g. "claude, synthesize these findings")
- a2a_broadcast: Ask the SAME question to ALL agents in parallel, side-by-side WITHOUT synthesis
- a2a_consensus: Same question to all agents + a judge SYNTHESIZES consensus. Use for decisions ("best approach?"), idea validation, or when a consolidated answer is needed.
- a2a_team: Orchestrate a MULTI-STEP workflow pipeline (e.g. step 1 parallel analysis, step 2 synthesis). Use {{previous}} in prompts to accumulate context between steps.
- a2a_code_ensemble: HIGH-QUALITY code generation via NxN cross-review — all agents write code, review each other's submissions, revise with feedback, then a judge synthesizes the best solution. Use for critical code tasks where quality matters more than speed.

AUTO-SELECTION RULE (follow this order):
1. Trivial task → solve it yourself, don't delegate
2. Task for 1 specialist → a2a_call (claude for writing, gemini for research)
3. Want side-by-side answers → a2a_broadcast
4. Want decision/consensus → a2a_consensus
5. Want ordered steps → a2a_team
6. Want production code → a2a_code_ensemble

FILE ACCESS RULES:
- You have access to the ENTIRE filesystem via read_file, search_content, list_directory, shell_exec
- ALWAYS use absolute paths (e.g. ~/Documents/Aplicativos/Transcritor/mlx_vomo.py)
- When asked about files, NEVER say "file not found" without trying read_file or search_content first
- If a path is not given, use shell_exec with find or search_content to locate the file
- For directory metrics (entry count, newest item by mtime, type counts), use directory_probe first
- Use list_directory for readable listings, not canonical counting
- Common project dirs: ~/Documents/Aplicativos/Transcritor/, ~/Documents/Aplicativos/Iudex/, ~/Documents/Aplicativos/

RULES:
- Delegate when another agent is better suited for the task
- For synthesis/writing/complex reasoning: prefer claude
- For research/data analysis: prefer gemini
- Do NOT delegate trivial tasks you can solve yourself

MESH DASHBOARD:
- Web dashboard: http://localhost:{PORT}/ui (ports: 3141 codex, 3142 claude, 3143 gemini, 3144 grok)
- Any server serves the same dashboard
- Features: agent status, interactive chat, traces, timeline, stats
- Real-time SSE: task events appear live on the dashboard
- Users can send tasks from the dashboard or terminal`;

// ============================================
// TASK EXECUTION: API with tool loop
// ============================================

const MAX_TOOL_ROUNDS = 15;

async function executeCodexAPIWithTools(task, onChunk, runContext = {}) {
  tm.updateTask(task, { status: { state: 'working' } });
  const signal = runContext?.signal;

  const currentDepth = task.metadata?.maxDepth ?? A2A_MESH_MAX_DEPTH;
  const toolContext = {
    depth: currentDepth,
    meshChain: task.metadata?.meshChain || [],
    taskId: task.id,
    selfCallDepth: task.metadata?.selfCallDepth || 0,
  };
  const tools = formatToolsForCodex(currentDepth);

  const input = task.history.map(m => ({
    role: m.role === 'agent' ? 'assistant' : 'user',
    content: extractPromptText(m),
  }));

  const instructions = task.metadata?.system || SYSTEM_PROMPT;

  let allText = '';
  let previousResponseId = null;

  const onTextDelta = (text) => {
    if (onChunk) onChunk({ type: 'progress', text });
    tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
  };

  try {
    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      const data = await openaiResponsesApiCall(input, tools, previousResponseId, onTextDelta, instructions, signal);

      if (data.error) {
        throw new Error(data.error.message);
      }

      previousResponseId = data.responseId;

      if (data.textContent) {
        allText += data.textContent;
      }

      if (!data.functionCalls || data.functionCalls.length === 0) {
        break;
      }

      const toolOutputs = [];
      for (const fc of data.functionCalls) {
        let parsedInput;
        try {
          parsedInput = JSON.parse(fc.arguments);
        } catch {
          parsedInput = { raw: fc.arguments };
        }

        const result = await dispatchTool(fc.name, parsedInput, toolContext);
        if (onChunk) onChunk({ type: 'progress', text: `[tool: ${fc.name}] ` });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, `[tool: ${fc.name}]\n`);

        toolOutputs.push({
          type: 'function_call_output',
          call_id: fc.call_id,
          output: normalizeToolOutput(result).slice(0, 100000),
        });
      }

      // Next round: send tool outputs with previous_response_id
      input.length = 0;
      input.push(...toolOutputs);
    }

    const agentMessage = { role: 'agent', parts: [{ type: 'text', text: allText }] };
    const artifacts = extractArtifacts(allText);

    tm.updateTask(task, {
      status: { state: 'completed', message: agentMessage },
      history: [...task.history, agentMessage],
      artifacts: [...task.artifacts, ...artifacts],
    });

    if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
  } catch (e) {
    const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro API: ${e.message}` }] };
    tm.updateTask(task, {
      status: { state: 'failed', message: errorMessage },
      history: [...task.history, errorMessage],
    });
    if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
  }
}

// ============================================
// CLI FALLBACK
// ============================================

function executeCodexCLI(task, onChunk, runContext = {}) {
  const signal = runContext.signal;
  const currentDepth = task.metadata?.maxDepth ?? A2A_MESH_MAX_DEPTH;
  const toolContext = {
    depth: currentDepth,
    meshChain: task.metadata?.meshChain || [],
    taskId: task.id,
    selfCallDepth: task.metadata?.selfCallDepth || 0,
  };

  const prompt = extractPromptText(task.history[0]);
  const contextMessages = task.history.slice(1).map(m => {
    const role = m.role === 'user' ? 'User' : 'Codex';
    return `${role}: ${extractPromptText(m)}`;
  });

  let basePrompt = contextMessages.length > 0
    ? `${contextMessages.join('\n\n')}\n\nUser: ${prompt}`
    : prompt;

  const toolPrefix = cliToolWrapper?.buildA2AToolPrefix(A2A_PEERS, currentDepth) || '';

  tm.updateTask(task, { status: { state: 'working' } });

  const MAX_CLI_TOOL_ROUNDS = 15;
  let allText = '';
  const cliIdentityPrefix = `[A2A RUNTIME IDENTITY]\nYou are Codex running ${CODEX_CLI_MODEL} with ${CODEX_REASONING_EFFORT} reasoning through the Codex CLI. Never claim another model or effort.\n[END A2A RUNTIME IDENTITY]\n\n`;

  function runCLIRound(currentPrompt, round) {
    if (signal?.aborted || task.status?.state === 'canceled') return;
    const outputFile = `/tmp/a2a-codex-${task.id}-r${round}.txt`;

    const cliArgs = [
      'exec', '--ephemeral', '--skip-git-repo-check', '--color', 'never',
      '--dangerously-bypass-approvals-and-sandbox',
      '-m', CODEX_CLI_MODEL,
      '-c', `model_reasoning_effort="${CODEX_REASONING_EFFORT}"`,
      '-c', `sqlite_home=${JSON.stringify(CODEX_SQLITE_HOME)}`,
      '-o', outputFile,
      cliIdentityPrefix + toolPrefix + currentPrompt,
    ];
    if (DISABLED_SKILLS_OVERRIDE) {
      cliArgs.splice(cliArgs.length - 1, 0, '-c', DISABLED_SKILLS_OVERRIDE);
    }

    const child = spawn('codex', cliArgs, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: bridgeEnvironmentForTask(task, SELF_ID, { ...process.env, NO_COLOR: '1', CODEX_HOME: CODEX_RUNTIME_HOME }),
      // detached so the whole process tree can be reaped via process.kill(-pid).
      detached: true,
    });

    // Close stdin immediately so codex exec doesn't wait for additional input
    child.stdin.end();

    task.process = child;
    let stdout = '';
    let stderr = '';
    let timedOut = false;
    const progressFilter = cliToolWrapper?.createToolCallStreamFilter?.();

    const timeout = setTimeout(() => {
      timedOut = true;
      child.kill('SIGTERM');
      setTimeout(() => {
        if (task.process === child) child.kill('SIGKILL');
      }, 5000).unref();
    }, CODEX_CLI_TIMEOUT_MS);

    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      const safeText = progressFilter ? progressFilter.push(text) : text;
      if (safeText) {
        if (onChunk) onChunk({ type: 'progress', text: safeText });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, safeText);
      }
    });

    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

    child.on('close', async (code) => {
      task.process = null;
      clearTimeout(timeout);
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const safeTail = progressFilter?.flush?.() || '';
      if (safeTail) {
        if (onChunk) onChunk({ type: 'progress', text: safeTail });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, safeTail);
      }

      let output = '';
      let outputFromFile = false;
      try {
        if (fs.existsSync(outputFile)) {
          output = fs.readFileSync(outputFile, 'utf8').trim();
          outputFromFile = output.length > 0;
          fs.unlinkSync(outputFile);
        }
      } catch (err) {
        console.warn('[runCLI] Failed to read/remove CLI output file', {
          file: outputFile,
          error: err instanceof Error ? err.message : String(err),
        });
      }
      // Fall back to stdout/stderr only when the structured outputFile is empty.
      // Sanitize bootstrap noise (rmcp transport errors, codex header block,
      // prompt echo) so we don't mistake the CLI's own banner for the answer.
      if (!output) {
        const fallback = stdout.trim() || stderr.trim();
        const cleaned = cliToolWrapper?.sanitizeCliBootstrap?.(fallback) ?? fallback;
        if (cleaned.length >= 20) output = cleaned;
      }

      if (timedOut && !output) {
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro: Codex CLI timed out after ${CODEX_CLI_TIMEOUT_MS}ms` }] };
        tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
        if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
        return;
      }

      if (!output || (code !== 0 && !outputFromFile)) {
        // Treat empty answer or non-zero exit without a file artifact as failure.
        // Surface the actual rmcp/transport error from stderr so the dashboard
        // shows root cause instead of a bootstrap echo masquerading as code.
        const errSummary = (stderr.trim() || 'Unknown error').split('\n').slice(0, 5).join(' | ');
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro (code ${code}): ${errSummary}` }] };
        tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
        if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
        return;
      }

      const wrapper = cliToolWrapper;
      const toolCall = wrapper?.parseToolCall(output);

      if (toolCall && round < MAX_CLI_TOOL_ROUNDS) {
        let result;
        try {
          result = await dispatchTool(toolCall.name, toolCall.input, toolContext);
        } catch (toolErr) {
          result = `Tool error: ${toolErr.message}`;
        }
        allText += (toolCall.beforeCall ? toolCall.beforeCall + '\n' : '');

        const followUp = wrapper.buildFollowUpPrompt(basePrompt, output, toolCall.name, normalizeToolOutput(result));
        if (!signal?.aborted && task.status?.state !== 'canceled') runCLIRound(followUp, round + 1);
        return;
      }

      allText += (wrapper ? wrapper.removeToolCalls(output) : output);

      const agentMessage = { role: 'agent', parts: [{ type: 'text', text: allText }] };
      const artifacts = extractArtifacts(allText);
      tm.updateTask(task, {
        status: { state: 'completed', message: agentMessage },
        history: [...task.history, agentMessage],
        artifacts: [...task.artifacts, ...artifacts],
        metadata: {
          ...task.metadata,
          configuredModel: CODEX_CLI_MODEL,
          reasoningEffort: CODEX_REASONING_EFFORT,
          providerRuntime: 'codex-cli',
        },
      });
      if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
    });

    child.on('error', (err) => {
      task.process = null;
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar Codex: ${err.message}` }] };
      tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
      if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
    });
  }

  runCLIRound(basePrompt, 0);
}

// ============================================
// MAIN TASK EXECUTOR
// ============================================

function executeCodexTask(task, onChunk, runContext = {}) {
  const forceApi = task.metadata?.useAPI === true;
  if (!USE_CLI || forceApi) {
    executeCodexAPIWithTools(task, onChunk, runContext).catch(err => {
      console.error('executeCodexAPIWithTools error, falling back to CLI:', err.message);
      tm.updateTask(task, { status: { state: 'working' } });
      console.log(`[CLI fallback] Task ${task.id} retrying via Codex CLI`);
      if (!runContext.signal?.aborted) executeCodexCLI(task, onChunk, runContext);
    });
    return;
  }
  return executeCodexCLI(task, onChunk, runContext);
}

// ============================================
// AGENT CARD
// ============================================

const AGENT_CARD = {
  name: 'Codex Agent',
  description: `Codex ${CODEX_CLI_MODEL} com esforço ${CODEX_REASONING_EFFORT}, executado pela Codex CLI e exposto via protocolo A2A.`,
  url: `http://localhost:${PORT}`,
  version: '1.0.0',
  capabilities: {
    streaming: true,
    pushNotifications: false,
    stateTransitionHistory: true,
  },
  skills: [
    { id: 'code-generation', name: 'Geração de Código', description: 'Gera código em qualquer linguagem a partir de descrição natural', tags: ['coding', 'generation'] },
    { id: 'code-review', name: 'Code Review', description: 'Analisa código buscando bugs, segurança e melhorias', tags: ['review', 'quality'] },
    { id: 'debugging', name: 'Debug', description: 'Analisa erros e sugere correções', tags: ['debug', 'troubleshooting'] },
    { id: 'explanation', name: 'Explicação de Código', description: 'Explica código complexo de forma clara', tags: ['explain', 'documentation'] },
    { id: 'architecture', name: 'Arquitetura', description: 'Sugere arquiteturas e padrões de design', tags: ['architecture', 'design'] },
    { id: 'general', name: 'Conversa Geral', description: 'Responde perguntas gerais de programação', tags: ['chat', 'general'] },
  ],
  defaultInputModes: ['text'],
  defaultOutputModes: ['text'],
};

// ============================================
// START SERVER
// ============================================

createA2AServer({
  port: PORT,
  selfId: SELF_ID,
  model: USE_CLI ? CODEX_CLI_MODEL : CODEX_API_MODEL,
  useApi: !USE_CLI,
  authToken: A2A_AUTH_TOKEN,
  taskTimeoutMs: 2700000, // 45 min
  agentCard: AGENT_CARD,
  peers: A2A_PEERS,
  maxDepth: A2A_MESH_MAX_DEPTH,
  taskManager: tm,
  meshCaller,
  meshStore,
  meshBus,
  peerDiscovery,
  teamExecutor,
  consensusExecutor,
  ensembleExecutor: codeEnsembleExecutor,
  debateExecutor,
  planExecutor,
  healthDetails: () => ({
    route: 'codex',
    provider: 'openai',
    configuredModel: USE_CLI ? CODEX_CLI_MODEL : CODEX_API_MODEL,
    reasoningEffort: CODEX_REASONING_EFFORT,
    modelPolicy: 'fixed',
    modelVerification: USE_CLI ? 'cli-argument' : 'api-response',
    providerRuntime: USE_CLI ? 'codex-cli' : 'openai-api',
  }),
  executeTask: executeCodexTask,
});
