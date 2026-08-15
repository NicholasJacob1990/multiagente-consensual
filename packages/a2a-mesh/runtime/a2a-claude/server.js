#!/usr/bin/env node

/**
 * A2A Claude Server (refactored)
 *
 * Uses shared modules from a2a-shared/ for HTTP server, task management,
 * local tools, and mesh communication. This file contains only
 * Claude-specific logic: Anthropic Messages API streaming, rate limiting,
 * tool format conversion, CLI fallback.
 */

import 'dotenv/config';
import https from 'https';
import os from 'os';
import { spawn } from 'child_process';

import { createA2AServer, extractPromptText, extractArtifacts } from '../a2a-shared/base-server.js';
import { BASE_TOOLS, getMeshToolDefs } from '../a2a-shared/local-tools.js';
import { createSharedRuntime } from '../a2a-shared/server-runtime.js';
import { loadA2AAuthToken } from '../a2a-shared/auth-token.js';
import { bridgeEnvironmentForTask } from '../a2a-shared/bridge-context.js';

// ============================================
// CONFIG
// ============================================

const PORT = parseInt(process.env.A2A_PORT || '3142', 10);
const CLAUDE_API_MODEL = process.env.CLAUDE_API_MODEL || process.env.CLAUDE_MODEL || 'claude-opus-5';
const CLAUDE_CLI_MODEL = process.env.CLAUDE_CLI_MODEL || 'claude-opus-5';
const CLAUDE_PERMISSION_MODE = process.env.CLAUDE_PERMISSION_MODE || 'bypassPermissions';
const CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS = process.env.CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS !== 'false';
const ANTHROPIC_API_KEY = process.env.ANTHROPIC_API_KEY || '';
const USE_CLI = process.env.USE_CLI !== 'false' && process.env.USE_CLI !== '0'; // CLI primary (like Codex)
const USE_API = !USE_CLI && ANTHROPIC_API_KEY.length > 0;
const CLAUDE_MODEL = USE_API ? CLAUDE_API_MODEL : CLAUDE_CLI_MODEL;

const A2A_AUTH_TOKEN = loadA2AAuthToken();
const MAX_CONCURRENT_TASKS = parseInt(process.env.MAX_CONCURRENT_TASKS || '15', 10);
const MAX_TASKS = parseInt(process.env.MAX_TASKS || '200', 10);

// Mesh peers
const A2A_MESH_MAX_DEPTH = parseInt(process.env.A2A_MESH_MAX_DEPTH || '7', 10);
const SELF_ID = 'claude';
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
  dataDir: process.env.A2A_CLAUDE_DATA_DIR,
});

// ============================================
// CLAUDE-SPECIFIC: Tool format & dispatch
// ============================================

// Anthropic uses input_schema instead of parameters
function toAnthropicFormat(tool) {
  return { name: tool.name, description: tool.description, input_schema: tool.parameters };
}

function formatToolsForClaude(depth) {
  const localTools = BASE_TOOLS.map(toAnthropicFormat);
  const meshTools = depth > 0 ? getMeshToolDefs(Object.keys(A2A_PEERS)).map(toAnthropicFormat) : [];
  return [...localTools, ...meshTools];
}

// ============================================
// ANTHROPIC API: Streaming with content blocks
// ============================================

function apiCallStream(messages, tools, modelOverride, onTextChunk, systemPrompt, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('Request aborted'));

    const body = JSON.stringify({
      model: modelOverride || CLAUDE_MODEL,
      max_tokens: 65536,
      system: systemPrompt || undefined,
      messages,
      tools: tools?.length ? tools : undefined,
      stream: true,
    });
    console.log(`[apiCallStream] Starting request, model=${modelOverride || CLAUDE_MODEL}, bodyLen=${body.length}`);

    const req = https.request({
      hostname: 'api.anthropic.com',
      port: 443,
      path: '/v1/messages',
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'x-api-key': ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      signal,
    }, (res) => {
      console.log(`[apiCallStream] Response status: ${res.statusCode}`);

      if (res.statusCode !== 200) {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          try {
            const parsed = JSON.parse(Buffer.concat(chunks).toString());
            if (parsed.error?.type === 'rate_limit_error') {
              const retryAfter = res.headers['retry-after'] ? parseInt(res.headers['retry-after']) * 1000 : null;
              parsed._retryAfterMs = retryAfter || 60000;
            }
            resolve(parsed);
          } catch (e) { reject(e); }
        });
        return;
      }

      let buffer = '';
      const content = [];
      let currentBlock = null;
      let stopReason = null;

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
            switch (evt.type) {
              case 'content_block_start':
                currentBlock = { ...evt.content_block };
                if (currentBlock.type === 'tool_use') currentBlock._inputJson = '';
                break;
              case 'content_block_delta':
                if (evt.delta?.type === 'text_delta' && evt.delta.text) {
                  if (currentBlock) currentBlock.text = (currentBlock.text || '') + evt.delta.text;
                  if (onTextChunk) onTextChunk(evt.delta.text);
                } else if (evt.delta?.type === 'input_json_delta' && evt.delta.partial_json) {
                  if (currentBlock) currentBlock._inputJson = (currentBlock._inputJson || '') + evt.delta.partial_json;
                }
                break;
              case 'content_block_stop':
                if (currentBlock) {
                  if (currentBlock.type === 'tool_use' && currentBlock._inputJson) {
                    try {
                      currentBlock.input = JSON.parse(currentBlock._inputJson);
                    } catch (err) {
                      console.warn('[apiCallStream] Failed to parse tool input JSON delta', {
                        error: err instanceof Error ? err.message : String(err),
                        preview: String(currentBlock._inputJson).slice(0, 200),
                      });
                      currentBlock.input = {};
                    }
                    delete currentBlock._inputJson;
                  }
                  content.push(currentBlock);
                  currentBlock = null;
                }
                break;
              case 'message_delta':
                if (evt.delta?.stop_reason) stopReason = evt.delta.stop_reason;
                break;
            }
          } catch (err) {
            console.warn('[apiCallStream] Failed to parse SSE event', {
              error: err instanceof Error ? err.message : String(err),
              preview: String(line).slice(0, 200),
            });
          }
        }
      });

      res.on('end', () => {
        console.log(`[apiCallStream] Stream ended. ${content.length} content blocks, stopReason=${stopReason}`);
        resolve({ content, stop_reason: stopReason });
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

function abortableSleep(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Error('Request aborted'));
    const timer = setTimeout(resolve, ms);
    if (signal) {
      signal.addEventListener('abort', () => {
        clearTimeout(timer);
        reject(new Error('Request aborted'));
      }, { once: true });
    }
  });
}

async function apiCall(messages, tools, modelOverride, onTextChunk, systemPrompt, signal) {
  const MAX_RETRIES = 5;
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    const result = await apiCallStream(messages, tools, modelOverride, onTextChunk, systemPrompt, signal);
    if (result.error && result.error.type === 'rate_limit_error') {
      const waitMs = result._retryAfterMs || (30000 * (attempt + 1));
      console.log(`[Rate limit] Tentativa ${attempt + 1}/${MAX_RETRIES}, aguardando ${waitMs / 1000}s...`);
      await abortableSleep(waitMs, signal);
      continue;
    }
    return result;
  }
  throw new Error('Rate limit exceeded after max retries');
}

// ============================================
// SYSTEM PROMPT
// ============================================

const SYSTEM_PROMPT = `Você é Claude, um agente técnico em uma mesh A2A (Agent-to-Agent) com outros agentes AI.

COMPORTAMENTO:
- Você recebe TAREFAS via A2A, não é uma sessão interativa de Claude Code
- Foco principal: resolver a task pedida com expressividade técnica e bom uso das capacidades disponíveis
- Use livremente ferramentas locais, MCPs configuradas e skills (~/.claude/skills/*) quando forem relevantes
- Evite "workflow de sessão" por hábito (ler CLAUDE.md, atualizar AI_LOG, /compact) — só faça isso se a task explicitamente envolver essa documentação
- Responda direto e técnico; cite arquivo:linha quando referenciar código

FERRAMENTAS LOCAIS: read_file, shell_exec, search_content, list_directory, directory_probe.

MCPs E SKILLS DISPONÍVEIS: você tem acesso ao mesmo conjunto que o Claude Code interativo (ver ~/.claude/mcp.json e ~/.claude/skills/). Use quando a task pedir ou quando claramente acelera a resposta. Exemplos: firecrawl pra extrair web, playwright pra automação browser, sei/tribunais pra dados jurídicos, perplexity pra pesquisa, qmd/mem0 pra memória persistente, iudex pra workflows do projeto.

AGENTES A2A DISPONÍVEIS:
- codex: OpenAI Codex (gpt-5.6-sol, esforço xhigh) — especialista em geração e análise de código, debugging e refactoring
- gemini: Google Gemini — forte em raciocínio, análise de dados, pesquisa e explicações detalhadas
- grok: xAI Grok 4.6 High, exclusivamente via Cursor CLI — forte em revisão adversarial e busca de pressupostos frágeis

QUANDO USAR CADA TOOL A2A:
- a2a_call: Consultar UM agente específico para tarefa direcionada (ex: "codex, refatore esta função")
- a2a_broadcast: Mesma pergunta para TODOS os agentes em paralelo, respostas lado a lado SEM síntese
- a2a_consensus: Mesma pergunta para todos + um juiz SINTETIZA o consenso. Use para decisões ("melhor abordagem?"), validação de ideias, ou quando precisa de resposta consolidada.
- a2a_team: Orquestrar workflow MULTI-STEP com pipeline (ex: step 1 paralelo codex+gemini analisam, step 2 sequential você sintetiza). Use {{previous}} no prompt para acumular contexto entre steps.
- a2a_code_ensemble: Gerar código de ALTA QUALIDADE via NxN cross-review — todos escrevem, revisam entre si, revisam com feedback, e um juiz sintetiza. Use para tarefas de código críticas onde qualidade importa mais que velocidade.

REGRA DE SELEÇÃO AUTOMÁTICA (siga esta ordem):
1. Tarefa trivial → resolva você mesmo, sem delegar
2. Tarefa para 1 especialista → a2a_call (codex para código, gemini para pesquisa)
3. Quer respostas lado a lado → a2a_broadcast
4. Quer decisão/consenso → a2a_consensus
5. Quer etapas ordenadas → a2a_team
6. Quer código de produção → a2a_code_ensemble

ACESSO A ARQUIVOS:
- Você tem acesso ao filesystem INTEIRO via read_file, search_content, list_directory, shell_exec
- SEMPRE use paths absolutos (ex: ~/Documents/Aplicativos/Transcritor/mlx_vomo.py)
- NUNCA diga "arquivo não encontrado" sem antes tentar read_file ou search_content
- Se não tiver o path, use shell_exec com find ou search_content para localizar
- Para métricas de diretório (total de entradas, item mais novo por mtime, contagem por tipo), use directory_probe primeiro
- Use list_directory apenas para listagem legível, não para contagem canônica
- Diretórios comuns: ~/Documents/Aplicativos/Transcritor/, ~/Documents/Aplicativos/Iudex/, ~/Documents/Aplicativos/

REGRAS:
- Delegue quando outro agente é mais adequado para a tarefa
- Para code review/debug: prefira codex
- Para análise/pesquisa/raciocínio: prefira gemini
- NÃO delegue tarefas triviais que você mesmo pode resolver

MESH DASHBOARD:
- Dashboard web: http://localhost:{PORT}/ui (portas: 3141 codex, 3142 claude, 3143 gemini, 3144 grok)
- Qualquer server serve o mesmo dashboard
- Features: status dos agents, chat interativo, traces, timeline, stats
- SSE real-time: eventos de tasks aparecem ao vivo no dashboard
- O usuário pode enviar tasks pelo dashboard ou pelo terminal`;

// ============================================
// TASK EXECUTION: API with tool_use loop
// ============================================

const MAX_TOOL_ROUNDS = 15;

async function executeClaudeAPIWithTools(task, onChunk, runContext = {}) {
  tm.updateTask(task, { status: { state: 'working' } });
  const signal = runContext?.signal;

  const requestModel = task.metadata?.model || null;
  const currentDepth = task.metadata?.maxDepth ?? A2A_MESH_MAX_DEPTH;
  const toolContext = {
    depth: currentDepth,
    meshChain: task.metadata?.meshChain || [],
    taskId: task.id,
    selfCallDepth: task.metadata?.selfCallDepth || 0,
  };
  const tools = formatToolsForClaude(currentDepth);

  const systemPrompt = task.metadata?.system || SYSTEM_PROMPT;

  const messages = task.history.map(m => ({
    role: m.role === 'agent' ? 'assistant' : 'user',
    content: extractPromptText(m),
  }));

  let allText = '';
  const onTextDelta = (text) => {
    if (onChunk) onChunk({ type: 'progress', text });
    tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
  };

  try {
    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      console.log(`[API] Round ${round + 1}/${MAX_TOOL_ROUNDS}, messages=${messages.length}, tools=${tools.length}`);
      const data = await apiCall(messages, tools, requestModel, onTextDelta, systemPrompt, signal);

      if (data.error) {
        console.error(`[API] Error:`, data.error.message);
        throw new Error(data.error.message);
      }

      const textParts = data.content?.filter(c => c.type === 'text').map(c => c.text) || [];
      allText += textParts.join('\n');

      const toolUses = data.content?.filter(c => c.type === 'tool_use') || [];
      console.log(`[API] Round ${round + 1}: textLen=${textParts.join('').length}, toolUses=${toolUses.length}, stopReason=${data.stop_reason}`);

      if (toolUses.length === 0) {
        console.log(`[API] Done: no tool use, stopReason=${data.stop_reason}`);
        break;
      }

      messages.push({ role: 'assistant', content: data.content });

      const toolResults = [];
      for (const tu of toolUses) {
        const result = await dispatchTool(tu.name, tu.input, toolContext);
        if (onChunk) onChunk({ type: 'progress', text: `[tool: ${tu.name}] ` });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, `[tool: ${tu.name}]\n`);
        toolResults.push({
          type: 'tool_result',
          tool_use_id: tu.id,
          content: normalizeToolOutput(result).slice(0, 100000),
        });
      }

      messages.push({ role: 'user', content: toolResults });
    }

    // Force a final text-only call if response is too short
    if (allText.length < 500) {
      console.log(`[API] Forcing final text-only call (allText=${allText.length} chars)`);
      messages.push({
        role: 'user',
        content: 'Você atingiu o limite de tool rounds. Agora escreva sua resposta final completa com base em tudo que verificou. Não use tools.',
      });
      const finalData = await apiCall(messages, [], requestModel, onTextDelta, undefined, signal);
      if (!finalData.error) {
        const finalText = finalData.content?.filter(c => c.type === 'text').map(c => c.text).join('\n') || '';
        allText += finalText;
        console.log(`[API] Final text-only response: ${finalText.length} chars`);
      }
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
    // Re-throw credit/auth errors so executeClaudeTask can fallback to CLI
    const msg = e.message || '';
    if (msg.includes('credit balance') || msg.includes('authentication') || msg.includes('401') || msg.includes('403') || msg.includes('overloaded')) {
      throw e;
    }
    const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro API: ${msg}` }] };
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

function executeClaudeCLI(task, onChunk, runContext = {}) {
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
    const role = m.role === 'user' ? 'User' : 'Claude';
    return `${role}: ${extractPromptText(m)}`;
  });

  let basePrompt = contextMessages.length > 0
    ? `${contextMessages.join('\n\n')}\n\nUser: ${prompt}`
    : prompt;

  const toolPrefix = cliToolWrapper?.buildA2AToolPrefix(A2A_PEERS, currentDepth) || '';

  tm.updateTask(task, { status: { state: 'working' } });

  const MAX_CLI_TOOL_ROUNDS = 15;
  let allText = '';

  function runCLIRound(currentPrompt, round) {
    if (signal?.aborted || task.status?.state === 'canceled') return;
    const cleanEnv = bridgeEnvironmentForTask(task, SELF_ID, { ...process.env, NO_COLOR: '1' });
    delete cleanEnv.CLAUDECODE;
    delete cleanEnv.CLAUDE_CODE_ENTRYPOINT;
    // Always remove API key so CLI uses Max subscription auth instead of API credits
    // This ensures both direct CLI mode AND API→CLI fallback work correctly
    delete cleanEnv.ANTHROPIC_API_KEY;

    const cliModel = task.metadata?.model || CLAUDE_CLI_MODEL;
    const systemPrompt = task.metadata?.system || SYSTEM_PROMPT;
    const cliArgs = [
      '-p', toolPrefix + currentPrompt,
      '--system-prompt', systemPrompt,
      '--output-format', 'text',
      '--no-session-persistence',
      ...(CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS
        ? ['--dangerously-skip-permissions']
        : ['--permission-mode', CLAUDE_PERMISSION_MODE]),
      '--tools', 'default',
      '--add-dir', os.homedir(),
    ];
    // Only pass --model if not 'default' (let CLI use plan default)
    if (cliModel && cliModel !== 'default') {
      cliArgs.push('--model', cliModel);
    }

    const child = spawn('claude', cliArgs, {
      stdio: ['ignore', 'pipe', 'pipe'],
      env: cleanEnv,
      // detached so the whole process tree can be reaped via process.kill(-pid).
      detached: true,
    });

    task.process = child;
    let stdout = '';
    let stderr = '';

    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      if (onChunk) onChunk({ type: 'progress', text });
      tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
    });

    child.stderr.on('data', (chunk) => { stderr += chunk.toString(); });

    child.on('close', async (code) => {
      task.process = null;
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const rawOutput = stdout.trim() || stderr.trim();
      // Strip CLI bootstrap noise (transport errors, skill conflicts, prompt echo)
      // before treating stdout as the model's answer.
      const output = cliToolWrapper?.sanitizeCliBootstrap?.(rawOutput) ?? rawOutput;

      if (code !== 0 && !output) {
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro (code ${code}): ${stderr.trim() || 'Unknown error'}` }] };
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
        if (onChunk) onChunk({ type: 'progress', text: `\n[tool: ${toolCall.name}]\n` });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, `\n[tool: ${toolCall.name}]\n`);

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
      });
      if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
    });

    child.on('error', (err) => {
      task.process = null;
      if (signal?.aborted || task.status?.state === 'canceled') return;
      const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar Claude: ${err.message}` }] };
      tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
      if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
    });
  }

  runCLIRound(basePrompt, 0);
}

// ============================================
// MAIN TASK EXECUTOR
// ============================================

function executeClaudeTask(task, onChunk, runContext = {}) {
  const forceCLI = task.metadata?.useCLI === true;

  if (USE_API && !forceCLI) {
    executeClaudeAPIWithTools(task, onChunk, runContext).catch(err => {
      console.error('executeClaudeAPIWithTools error, falling back to CLI:', err.message);
      tm.updateTask(task, { status: { state: 'working' } });
      console.log(`[CLI fallback] Task ${task.id} retrying via Claude CLI`);
      if (!runContext.signal?.aborted) executeClaudeCLI(task, onChunk, runContext);
    });
    return;
  }
  console.log(`[CLI mode] Task ${task.id} using Claude CLI${forceCLI ? ' (forced)' : ''}`);
  return executeClaudeCLI(task, onChunk, runContext);
}

// ============================================
// AGENT CARD
// ============================================

const AGENT_CARD = {
  name: 'Claude Agent',
  description: 'Agente Claude CLI exposto via protocolo A2A. Executa tarefas de programacao, review, debug e geracao de codigo usando Anthropic Claude.',
  url: `http://localhost:${PORT}`,
  version: '1.0.0',
  capabilities: {
    streaming: true,
    pushNotifications: false,
    stateTransitionHistory: true,
  },
  skills: [
    { id: 'code-generation', name: 'Geracao de Codigo', description: 'Gera codigo em qualquer linguagem a partir de descricao natural', tags: ['coding', 'generation'] },
    { id: 'code-review', name: 'Code Review', description: 'Analisa codigo buscando bugs, seguranca e melhorias', tags: ['review', 'quality'] },
    { id: 'debugging', name: 'Debug', description: 'Analisa erros e sugere correcoes', tags: ['debug', 'troubleshooting'] },
    { id: 'explanation', name: 'Explicacao de Codigo', description: 'Explica codigo complexo de forma clara', tags: ['explain', 'documentation'] },
    { id: 'architecture', name: 'Arquitetura', description: 'Sugere arquiteturas e padroes de design', tags: ['architecture', 'design'] },
    { id: 'reasoning', name: 'Raciocinio Complexo', description: 'Analise profunda e raciocinio sobre problemas complexos', tags: ['reasoning', 'analysis'] },
    { id: 'general', name: 'Conversa Geral', description: 'Responde perguntas gerais de programacao', tags: ['chat', 'general'] },
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
  model: CLAUDE_MODEL,
  useApi: USE_API,
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
  executeTask: executeClaudeTask,
});
