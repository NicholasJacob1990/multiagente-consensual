#!/usr/bin/env node

/**
 * A2A Gemini Server (refactored)
 *
 * Uses shared modules from a2a-shared/ for HTTP server, task management,
 * local tools, and mesh communication. This file contains only
 * Gemini-specific logic: API streaming, Vertex AI, rate limiting, CLI fallback.
 */

import { config as dotenvConfig } from 'dotenv';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
dotenvConfig({ path: `${__dirname}/.env`, override: true });

import https from 'https';
import crypto from 'crypto';
import fs from 'fs';
import os from 'os';
import { spawn, execFile, execFileSync } from 'child_process';
import { promisify } from 'util';

import { createA2AServer, extractPromptText, extractArtifacts } from '../a2a-shared/base-server.js';
import { BASE_TOOLS, getMeshToolDefs } from '../a2a-shared/local-tools.js';
import { createSharedRuntime } from '../a2a-shared/server-runtime.js';
import { loadA2AAuthToken } from '../a2a-shared/auth-token.js';

const execFileAsync = promisify(execFile);

// ============================================
// LOGIN-SHELL ENV CAPTURE
// ============================================
// Captura env de uma sessão `zsh -l` (login shell) para que `gemini` rode com
// EXATAMENTE o mesmo ambiente do terminal do usuário: PATH, gcloud auth ADC,
// GOOGLE_* e qualquer config carregada via .zshrc/.zprofile. Sem isso, o mesh
// (spawn pelo launchd) tem env mínimo e `gemini` cai em Code Assist gratuito
// que satura. Captura síncrona uma única vez no startup.
function captureLoginShellEnv() {
  try {
    const raw = execFileSync('zsh', ['-l', '-c', 'env -0'], {
      encoding: 'buffer', timeout: 8000, maxBuffer: 4 * 1024 * 1024,
    });
    const env = {};
    for (const entry of raw.toString('utf8').split('\0')) {
      if (!entry) continue;
      const eq = entry.indexOf('=');
      if (eq > 0) env[entry.slice(0, eq)] = entry.slice(eq + 1);
    }
    return env;
  } catch (e) {
    console.warn(`[login-shell-env] capture falhou (${e.message?.slice(0,120)}); usando process.env`);
    return null;
  }
}
const LOGIN_SHELL_ENV = captureLoginShellEnv();

// ============================================
// CONFIG
// ============================================

const PORT = parseInt(process.env.A2A_PORT || '3143', 10);
const GEMINI_MODEL = process.env.GEMINI_MODEL || 'gemini-3.1-pro-preview';
const GEMINI_FALLBACK_MODEL = process.env.GEMINI_FALLBACK_MODEL || 'gemini-2.5-pro';
const GEMINI_CLI_MODEL = process.env.GEMINI_CLI_MODEL || GEMINI_FALLBACK_MODEL;
const GEMINI_APPROVAL_MODE = process.env.GEMINI_APPROVAL_MODE || 'yolo';
const GEMINI_YOLO = process.env.GEMINI_YOLO !== 'false';
const ANTIGRAVITY_CLI = process.env.ANTIGRAVITY_CLI || join(os.homedir(), '.local', 'bin', 'agy');
const USE_ANTIGRAVITY_CLI = process.env.GEMINI_CLI_PROVIDER !== 'gemini' && fs.existsSync(ANTIGRAVITY_CLI);
const ANTIGRAVITY_MODEL = process.env.ANTIGRAVITY_MODEL || 'Gemini 3.1 Pro (High)';
const ANTIGRAVITY_FALLBACK_MODEL = process.env.ANTIGRAVITY_FALLBACK_MODEL || 'Gemini 3.6 Flash (High)';
const GEMINI_VERTEX_FALLBACK_MODEL = process.env.GEMINI_VERTEX_FALLBACK_MODEL || GEMINI_CLI_MODEL || 'gemini-2.5-pro';
// Output token cap for direct API calls (PublicAPI/Vertex). CLI mode (`gemini -o json`)
// is governed by the CLI's own internal cap. 65536 was the historical default; raise
// via GEMINI_MAX_OUTPUT_TOKENS env when running long analyses (max for 3.1-pro is 65k;
// other models may differ — Gemini ignores values above what the model supports).
const GEMINI_MAX_OUTPUT_TOKENS = parseInt(process.env.GEMINI_MAX_OUTPUT_TOKENS || '65536', 10);

// Vertex AI config (used for fallback with gemini-2.5-pro)
const VERTEX_PROJECT = process.env.VERTEX_PROJECT || process.env.GOOGLE_CLOUD_PROJECT || '';
const VERTEX_LOCATION = process.env.VERTEX_LOCATION || 'us-central1';

// Auth: service account JWT preferred for both public API + Vertex
const FORCE_CLI = process.env.USE_CLI === 'force';
const USE_API = !FORCE_CLI;
const USE_CLI = !FORCE_CLI;

const A2A_AUTH_TOKEN = loadA2AAuthToken();
const MAX_CONCURRENT_TASKS = parseInt(process.env.MAX_CONCURRENT_TASKS || '15', 10);
const MAX_TASKS = parseInt(process.env.MAX_TASKS || '200', 10);

// Mesh peers
const A2A_MESH_MAX_DEPTH = parseInt(process.env.A2A_MESH_MAX_DEPTH || '7', 10);
const SELF_ID = 'gemini';
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
} = await createSharedRuntime({
  selfId: SELF_ID,
  authToken: A2A_AUTH_TOKEN,
  maxDepth: A2A_MESH_MAX_DEPTH,
  maxTasks: MAX_TASKS,
  maxConcurrent: MAX_CONCURRENT_TASKS,
  dataDir: process.env.A2A_GEMINI_DATA_DIR || './data/',
});

// ============================================
// GEMINI-SPECIFIC: Tool format & dispatch
// ============================================

// Gemini uses functionDeclarations — canonical format works directly
function formatToolsForGemini(depth) {
  const meshTools = depth > 0 ? getMeshToolDefs(Object.keys(A2A_PEERS)) : [];
  return [{ functionDeclarations: [...BASE_TOOLS, ...meshTools] }];
}

// ============================================
// VERTEX AI: Access token with caching
// ============================================

const GOOGLE_APPLICATION_CREDENTIALS = process.env.GOOGLE_APPLICATION_CREDENTIALS || '';

let _cachedToken = null;
let _tokenExpiry = 0;
let _tokenInFlight = null;

/** Generate JWT-signed access token from service account JSON */
async function getServiceAccountToken(keyFilePath) {
  const keyData = JSON.parse(fs.readFileSync(keyFilePath, 'utf8'));
  const now = Math.floor(Date.now() / 1000);

  const header = Buffer.from(JSON.stringify({ alg: 'RS256', typ: 'JWT' })).toString('base64url');
  const payload = Buffer.from(JSON.stringify({
    iss: keyData.client_email,
    scope: 'https://www.googleapis.com/auth/generative-language https://www.googleapis.com/auth/cloud-platform',
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
  })).toString('base64url');

  const signature = crypto.sign('RSA-SHA256', Buffer.from(`${header}.${payload}`), keyData.private_key);
  const jwt = `${header}.${payload}.${signature.toString('base64url')}`;

  // Exchange JWT for access token
  return new Promise((resolve, reject) => {
    const body = `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`;
    const req = https.request({
      hostname: 'oauth2.googleapis.com',
      port: 443,
      path: '/token',
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    }, (res) => {
      const chunks = [];
      res.on('data', c => chunks.push(c));
      res.on('end', () => {
        try {
          const data = JSON.parse(Buffer.concat(chunks).toString());
          if (data.access_token) resolve(data.access_token);
          else reject(new Error(`Token exchange failed: ${JSON.stringify(data)}`));
        } catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

async function getAccessToken() {
  const now = Date.now();
  if (_cachedToken && now < _tokenExpiry) return _cachedToken;
  if (_tokenInFlight) return _tokenInFlight;

  _tokenInFlight = (async () => {
    // Prefer service account JWT (has both generative-language + cloud-platform scopes)
    const keyFile = GOOGLE_APPLICATION_CREDENTIALS;
    if (keyFile && fs.existsSync(keyFile)) {
      const token = await getServiceAccountToken(keyFile);
      _cachedToken = token;
      _tokenExpiry = Date.now() + 55 * 60 * 1000;
      console.log('[auth] Authenticated via service account JWT (dual scope)');
      return _cachedToken;
    }

    // Fallback: gcloud (only has cloud-platform scope — works for Vertex, not public API)
    try {
      const { stdout } = await execFileAsync('gcloud', ['auth', 'print-access-token'], {
        encoding: 'utf8',
        timeout: 10000,
      });
      const token = String(stdout || '').trim();
      if (token) {
        _cachedToken = token;
        _tokenExpiry = Date.now() + 55 * 60 * 1000;
        return _cachedToken;
      }
    } catch (e) {
      console.log(`[auth] gcloud auth failed: ${e.message?.slice(0, 60)}`);
    }

    throw new Error('No credentials available (no service account, gcloud failed)');
  })().finally(() => {
    _tokenInFlight = null;
  });

  return _tokenInFlight;
}

// ============================================
// GEMINI API: Streaming call with SSE
// ============================================

/** Low-level HTTPS streaming request to Gemini API */
function geminiStreamRequest(reqOptions, body, onTextChunk) {
  return new Promise((resolve, reject) => {
    const req = https.request(reqOptions, (res) => {
      if (res.statusCode !== 200) {
        const chunks = [];
        res.on('data', (c) => chunks.push(c));
        res.on('end', () => {
          try {
            const errorBody = Buffer.concat(chunks).toString();
            try { resolve(JSON.parse(errorBody)); }
            catch { reject(new Error(`HTTP ${res.statusCode}: ${errorBody.slice(0, 300)}`)); }
          } catch (e) { reject(e); }
        });
        return;
      }

      let buffer = '';
      const allParts = [];

      res.on('data', (chunk) => {
        buffer += chunk.toString();
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const raw = line.slice(6).trim();
          if (!raw) continue;

          try {
            const evt = JSON.parse(raw);
            const parts = evt.candidates?.[0]?.content?.parts || [];
            for (const part of parts) {
              if (part.text) {
                allParts.push(part);
                if (onTextChunk) onTextChunk(part.text);
              } else if (part.functionCall) {
                allParts.push(part);
              }
            }
          } catch (err) {
            console.warn('[geminiApiCall] Failed to parse SSE chunk', {
              error: err instanceof Error ? err.message : String(err),
              preview: String(raw).slice(0, 200),
            });
          }
        }
      });

      res.on('end', () => {
        resolve({
          candidates: [{ content: { parts: allParts, role: 'model' } }],
        });
      });
    });

    if (reqOptions.signal) {
      reqOptions.signal.addEventListener('abort', () => {
        req.destroy(new Error('Request aborted'));
      }, { once: true });
    }

    req.on('error', reject);
    req.write(body);
    req.end();
  });
}

/** Low-level HTTPS JSON request (non-streaming) */
function geminiJsonRequest(reqOptions, body) {
  return new Promise((resolve, reject) => {
    const req = https.request(reqOptions, (res) => {
      const chunks = [];
      res.on('data', (chunk) => chunks.push(chunk));
      res.on('end', () => {
        const raw = Buffer.concat(chunks).toString();
        try {
          const data = raw ? JSON.parse(raw) : {};
          resolve(data);
        } catch (err) {
          const status = res.statusCode || 'unknown';
          reject(new Error(`HTTP ${status}: invalid JSON response (${String(err).slice(0, 120)})`));
        }
      });
    });

    if (reqOptions.signal) {
      reqOptions.signal.addEventListener('abort', () => {
        req.destroy(new Error('Request aborted'));
      }, { once: true });
    }

    req.on('error', reject);
    if (body) req.write(body);
    req.end();
  });
}

function ensureVertexTextParts(result, onTextChunk) {
  const parts = result?.candidates?.[0]?.content?.parts || [];
  for (const part of parts) {
    if (part.text && onTextChunk) onTextChunk(part.text);
  }
  return result;
}

async function geminiVertexCall(model, body, onTextChunk, signal) {
  if (!VERTEX_PROJECT) {
    return { error: { message: 'VERTEX_PROJECT/GOOGLE_CLOUD_PROJECT não definido para fallback Vertex' } };
  }

  const token = await getAccessToken();
  const host = `${VERTEX_LOCATION}-aiplatform.googleapis.com`;
  const path = `/v1/projects/${VERTEX_PROJECT}/locations/${VERTEX_LOCATION}/publishers/google/models/${model}:generateContent`;

  const result = await geminiJsonRequest({
    hostname: host,
    port: 443,
    path,
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
    signal,
  }, body);

  return ensureVertexTextParts(result, onTextChunk);
}

let _publicApiDisabled = false; // Disabled after persistent scope/auth errors

/** High-level Gemini API call: Public API (OAuth) → Vertex (fallback) → throw */
async function geminiApiCall(contents, tools, onTextChunk, systemInstruction, signal) {
  if (signal?.aborted) throw new Error('Request aborted');

  function makeBody() {
    return JSON.stringify({
      contents,
      tools: tools && tools.length > 0 ? tools : undefined,
      systemInstruction: systemInstruction ? { parts: [{ text: systemInstruction }] } : undefined,
      generationConfig: { maxOutputTokens: GEMINI_MAX_OUTPUT_TOKENS },
    });
  }

  // 1. Public Google AI API with OAuth Bearer token → gemini-3.1-pro-preview
  //    Uses service account JWT from iudex-vertex (billing enabled)
  if (!_publicApiDisabled) {
    try {
      const token = await getAccessToken();
      const model = GEMINI_MODEL; // gemini-3.1-pro-preview
      const result = await geminiStreamRequest({
        hostname: 'generativelanguage.googleapis.com',
        port: 443,
        path: `/v1beta/models/${model}:streamGenerateContent?alt=sse`,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        signal,
      }, makeBody(), onTextChunk);

      const errMsg = result?.error?.message || '';
      if (errMsg && (errMsg.includes('scope') || errMsg.includes('PERMISSION_DENIED'))) {
        console.log(`[PublicAPI] Auth scope issue: ${errMsg.slice(0, 100)}, trying Vertex...`);
        _publicApiDisabled = true;
      } else if (errMsg && (errMsg.includes('Quota') || errMsg.includes('429'))) {
        console.log(`[PublicAPI] Quota hit for ${model}, trying Vertex...`);
      } else if (errMsg && (errMsg.includes('not found') || errMsg.includes('404'))) {
        console.log(`[PublicAPI] Model ${model} not found, trying Vertex with fallback...`);
      } else if (errMsg) {
        console.log(`[PublicAPI] Error: ${errMsg.slice(0, 100)}, trying Vertex...`);
      } else {
        return result; // Success!
      }
    } catch (pubErr) {
      console.log(`[PublicAPI→Vertex] ${pubErr.message?.slice(0, 100)}`);
    }
  }

  // 2. Public API fallback with GEMINI_FALLBACK_MODEL (e.g. gemini-3-flash-preview)
  if (GEMINI_FALLBACK_MODEL && GEMINI_FALLBACK_MODEL !== GEMINI_MODEL) {
    try {
      const token = await getAccessToken();
      const model = GEMINI_FALLBACK_MODEL;
      console.log(`[PublicAPI] Fallback to ${model}`);
      const result = await geminiStreamRequest({
        hostname: 'generativelanguage.googleapis.com',
        port: 443,
        path: `/v1beta/models/${model}:streamGenerateContent?alt=sse`,
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Authorization': `Bearer ${token}` },
        signal,
      }, makeBody(), onTextChunk);

      const errMsg = result?.error?.message || '';
      if (errMsg) {
        console.log(`[PublicAPI fallback] Error: ${errMsg.slice(0, 100)}`);
      } else {
        return result; // Success with fallback model
      }
    } catch (fallbackErr) {
      console.log(`[PublicAPI fallback] ${fallbackErr.message?.slice(0, 100)}`);
    }
  }

  // 3. Vertex fallback with project credentials (works with gcloud user token)
  const vertexCandidates = Array.from(new Set([
    GEMINI_MODEL,
    GEMINI_FALLBACK_MODEL,
    GEMINI_VERTEX_FALLBACK_MODEL,
    GEMINI_CLI_MODEL,
    'gemini-2.5-pro',
    'gemini-2.5-flash',
  ].filter(Boolean)));

  const body = makeBody();
  for (const model of vertexCandidates) {
    try {
      const result = await geminiVertexCall(model, body, onTextChunk, signal);
      const errMsg = result?.error?.message || '';
      if (!errMsg) {
        if (model !== GEMINI_MODEL) {
          console.log(`[Vertex] Using fallback model ${model}`);
        }
        return result;
      }

      const shortErr = errMsg.slice(0, 120);
      console.log(`[Vertex:${model}] ${shortErr}`);
      continue;
    } catch (vertexErr) {
      console.log(`[Vertex:${model}] ${vertexErr.message?.slice(0, 120)}`);
    }
  }

  throw new Error(`No API path succeeded for ${GEMINI_MODEL}`);
}

// ============================================
// SYSTEM PROMPT
// ============================================

const SYSTEM_INSTRUCTION = `You are a helpful AI assistant with access to tools for file operations and shell commands.

IMPORTANT PATH REFERENCE — Common project locations:
- Iudex: ~/Documents/Aplicativos/Iudex/
  - Backend API: ~/Documents/Aplicativos/Iudex/apps/api/app/
  - Root scripts: ~/Documents/Aplicativos/Iudex/mlx_vomo.py
- Transcritor: ~/Documents/Aplicativos/Transcritor/
  - Key files: mlx_vomo.py, quality_engine.py, _prompts.py, audit_module.py, format_transcription_gemini.py
- All projects: ~/Documents/Aplicativos/

FILE ACCESS RULES:
- ALWAYS use absolute paths (~/... or /Users/nicholasjacob/...)
- NEVER say "file not found" without trying read_file or search_content first
- If path unknown, use shell_exec with find or search_content to locate
- For directory metrics (entry count, newest item by mtime, type counts), use directory_probe first
- Use list_directory for readable listings, not canonical counting
- Use list_directory to explore before assuming paths

Respond in Portuguese (pt-BR) when the user writes in Portuguese.`;

const MESH_SYSTEM_SUFFIX = `

---

Você é Gemini, um agente técnico em uma mesh A2A (Agent-to-Agent) com outros agentes AI.

FERRAMENTAS LOCAIS: shell_exec, read_file, search_content, list_directory, directory_probe.

MCPs E SKILLS: você tem acesso a MCPs e skills configuradas no seu ambiente (gemini-a2a, mem0, drive, file-store etc.). Use livremente quando relevante para a task — pesquisa profunda, sync com Drive, busca de documentos. Evite "workflow de sessão" automático (ler AI_LOG, explorar repo) sem que a task peça explicitamente.

AGENTES A2A DISPONÍVEIS:
- claude: Anthropic Claude (Opus) — forte em síntese, análise complexa, escrita, raciocínio avançado
- codex: OpenAI Codex (gpt-5.2-codex) — especialista em geração e análise de código, debugging, refactoring

QUANDO USAR CADA TOOL A2A:
- a2a_call: Consultar UM agente específico para tarefa direcionada (ex: "codex, refatore esta função")
- a2a_broadcast: Mesma pergunta para TODOS os agentes em paralelo, respostas lado a lado SEM síntese
- a2a_consensus: Mesma pergunta para todos + um juiz SINTETIZA o consenso. Use para decisões ("melhor abordagem?"), validação de ideias, ou quando precisa de resposta consolidada.
- a2a_team: Orquestrar workflow MULTI-STEP com pipeline (ex: step 1 paralelo codex+claude analisam, step 2 você sintetiza). Use {{previous}} no prompt para acumular contexto.
- a2a_code_ensemble: Gerar código de ALTA QUALIDADE via NxN cross-review — todos escrevem, revisam entre si, revisam com feedback, e um juiz sintetiza. Use para tarefas de código críticas onde qualidade importa mais que velocidade.

REGRA DE SELEÇÃO AUTOMÁTICA (siga esta ordem):
1. Tarefa trivial → resolva você mesmo, sem delegar
2. Tarefa para 1 especialista → a2a_call (codex para código, claude para escrita)
3. Quer respostas lado a lado → a2a_broadcast
4. Quer decisão/consenso → a2a_consensus
5. Quer etapas ordenadas → a2a_team
6. Quer código de produção → a2a_code_ensemble

REGRAS:
- Delegue quando outro agente é mais adequado
- Para código/debug: prefira codex
- Para síntese/escrita/raciocínio complexo: prefira claude
- NÃO delegue tarefas triviais

MESH DASHBOARD:
- Dashboard web: http://localhost:{PORT}/ui (onde PORT = 3141 codex, 3142 claude, 3143 gemini)
- Qualquer server serve o mesmo dashboard
- Features: status dos agents, chat interativo, traces, timeline, stats
- SSE real-time: eventos de tasks aparecem ao vivo no dashboard
- O usuário pode enviar tasks pelo dashboard ou pelo terminal`;

// ============================================
// TASK EXECUTION: API with tools loop
// ============================================

const API_CALL_DELAY_MS = parseInt(process.env.API_CALL_DELAY_MS || '3000', 10);
const MAX_RETRIES = 3;
const MAX_TOOL_ROUNDS = 15;

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

async function apiCallWithRetry(contents, tools, onTextDelta, systemInstruction, signal) {
  for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {
    const data = await geminiApiCall(contents, tools, onTextDelta, systemInstruction, signal);
    if (data.error?.message?.includes('Quota exceeded')) {
      const wait = (attempt + 1) * 5000; // 5s, 10s, 15s
      console.log(`[rate-limit] Quota hit, waiting ${wait}ms (attempt ${attempt + 1}/${MAX_RETRIES})`);
      await abortableSleep(wait, signal);
      continue;
    }
    return data;
  }
  return geminiApiCall(contents, tools, onTextDelta, systemInstruction, signal);
}

async function executeGeminiAPIWithTools(task, onChunk, runContext = {}) {
  tm.updateTask(task, { status: { state: 'working' } });
  const signal = runContext?.signal;

  const currentDepth = task.metadata?.maxDepth ?? A2A_MESH_MAX_DEPTH;
  const toolContext = {
    depth: currentDepth,
    meshChain: task.metadata?.meshChain || [],
    taskId: task.id,
    selfCallDepth: task.metadata?.selfCallDepth || 0,
  };
  const geminiTools = formatToolsForGemini(currentDepth);

  const contents = task.history.map(m => ({
    role: m.role === 'agent' ? 'model' : 'user',
    parts: [{ text: extractPromptText(m) }],
  }));

  const systemInstruction = task.metadata?.system || SYSTEM_INSTRUCTION + MESH_SYSTEM_SUFFIX;

  let allText = '';
  const onTextDelta = (text) => {
    if (onChunk) onChunk({ type: 'progress', text });
    tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
  };

  try {
    for (let round = 0; round < MAX_TOOL_ROUNDS; round++) {
      if (round > 0) await abortableSleep(API_CALL_DELAY_MS, signal);

      const data = await apiCallWithRetry(contents, geminiTools, onTextDelta, systemInstruction, signal);
      if (data.error) throw new Error(data.error.message);

      const candidate = data.candidates?.[0];
      if (!candidate) throw new Error('No response from Gemini API');

      const parts = candidate.content?.parts || [];
      for (const part of parts) {
        if (part.text) allText += part.text;
      }

      const functionCalls = parts.filter(p => p.functionCall);
      if (functionCalls.length === 0) break;

      contents.push(candidate.content);

      const responseParts = [];
      for (const fc of functionCalls) {
        let result;
        try {
          result = await dispatchTool(fc.functionCall.name, fc.functionCall.args || {}, toolContext);
        } catch (toolErr) {
          result = `Tool error: ${toolErr.message}`;
        }
        if (onChunk) onChunk({ type: 'progress', text: `[tool: ${fc.functionCall.name}] ` });
        tm.taskEmitter.emit(`task:${task.id}:chunk`, `[tool: ${fc.functionCall.name}]\n`);

        responseParts.push({
          functionResponse: {
            name: fc.functionCall.name,
            response: { name: fc.functionCall.name, content: normalizeToolOutput(result).slice(0, 100000) },
          },
        });
      }

      contents.push({ role: 'user', parts: responseParts });
    }

    if (!allText.trim()) {
      // Guard against empty API completions: force one final text-only pass.
      contents.push({
        role: 'user',
        parts: [{ text: 'Forneça agora a resposta final completa em texto. Não use tools.' }],
      });
      const finalData = await apiCallWithRetry(contents, [], onTextDelta, systemInstruction, signal);
      if (finalData.error) throw new Error(finalData.error.message);
      const finalCandidate = finalData.candidates?.[0];
      if (!finalCandidate) throw new Error('EMPTY_RESPONSE_FROM_API');
      const finalParts = finalCandidate.content?.parts || [];
      for (const part of finalParts) {
        if (part.text) allText += part.text;
      }
    }

    if (!allText.trim()) {
      throw new Error('EMPTY_RESPONSE_FROM_API');
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
    // Re-throw retryable errors so executeGeminiTask can fallback to CLI.
    if (e.message && (
      e.message.includes('quota') ||
      e.message.includes('429') ||
      e.message.includes('rate') ||
      e.message.includes('RESOURCE_EXHAUSTED') ||
      e.message.includes('No response from Gemini API') ||
      e.message.includes('No API path succeeded') ||
      e.message.includes('EMPTY_RESPONSE_FROM_API')
    )) {
      throw e;
    }
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

function executeGeminiCLI(task, onChunk, modelOverride) {
  const useModel = modelOverride || GEMINI_MODEL;
  const currentDepth = task.metadata?.maxDepth ?? A2A_MESH_MAX_DEPTH;
  const toolContext = {
    depth: currentDepth,
    meshChain: task.metadata?.meshChain || [],
    taskId: task.id,
    selfCallDepth: task.metadata?.selfCallDepth || 0,
  };

  const prompt = extractPromptText(task.history[0]);
  const contextMessages = task.history.slice(1).map(m => {
    const role = m.role === 'user' ? 'User' : 'Gemini';
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
    const effectiveCliModel = USE_ANTIGRAVITY_CLI
      ? (useModel === GEMINI_FALLBACK_MODEL ? ANTIGRAVITY_FALLBACK_MODEL : ANTIGRAVITY_MODEL)
      : useModel;
    console.log(`[CLI] Task ${task.id} using ${USE_ANTIGRAVITY_CLI ? 'agy' : 'gemini'} model ${effectiveCliModel} (round ${round})`);
    // A2A_SUPPRESS_HOOKS=1: hooks (mem0 SessionStart, vault digest) fazem exit silent.
    // stdin='ignore' fecha stdin, gemini não fica esperando input.
    // Use argv array instead of bash -c so long prompts with quotes/newlines are not re-parsed by the shell.
    const includeDirs = '/tmp,/Users/nicholasjacob/Documents,/Users/nicholasjacob';
    // Use o env do login shell (zsh -l) — mesmo que o user tem ao rodar
    // `gemini` direto no terminal. Isso traz PATH, gcloud auth, GOOGLE_* e
    // qualquer var de .zshrc/.zprofile. Fallback: process.env do mesh.
    // Preserve login-shell tools while retaining .env and launchd overrides.
    // Using LOGIN_SHELL_ENV alone discarded the configured Vertex project.
    const baseEnv = LOGIN_SHELL_ENV
      ? { ...LOGIN_SHELL_ENV, ...process.env }
      : process.env;
    const cliEnv = { ...baseEnv, A2A_SUPPRESS_HOOKS: '1' };
    const geminiPermissionArgs = GEMINI_YOLO
      ? ['--yolo']
      : ['--approval-mode', GEMINI_APPROVAL_MODE];
    const antigravityMode = 'accept-edits';
    const cliArgs = USE_ANTIGRAVITY_CLI
      ? [
          '--print', toolPrefix + currentPrompt,
          '--output-format', 'json',
          '--mode', antigravityMode,
          '--dangerously-skip-permissions',
          '--model', effectiveCliModel,
          '--add-dir', '/tmp',
          '--add-dir', os.homedir(),
        ]
      : [
          '--prompt', toolPrefix + currentPrompt,
          '--model', effectiveCliModel,
          ...geminiPermissionArgs,
          '--allowed-mcp-server-names', '__none__',
          '--include-directories', includeDirs,
          '-o', 'json',
        ];
    const child = spawn(USE_ANTIGRAVITY_CLI ? ANTIGRAVITY_CLI : 'gemini', cliArgs, {
      stdio: ['ignore', 'pipe', 'pipe'],
      cwd: os.homedir(),
      env: cliEnv,
      // detached:true creates a new process group so abortTaskExecution
      // can signal the whole tree via process.kill(-pid). The gemini CLI
      // ignores SIGTERM during inference; group-targeted SIGKILL is the
      // only reliable way to reap it.
      detached: true,
    });

    task.process = child;
    let stdout = '';
    let stderr = '';
    let antigravityEnvelopeSeen = false;

    // Fail-fast capacity detection: gemini-cli runs its own internal
    // retry-with-backoff (Attempt 1, Attempt 2, ...) on 429/CAPACITY_EXHAUSTED
    // before ever returning. That can burn ~15min before our `close` handler
    // sees the error and triggers fallback. Watch the streams as they arrive
    // and kill the child early so the close handler can switch models fast.
    let capacityErrorDetected = false;
    function scanForCapacityError(text) {
      if (capacityErrorDetected) return;
      if (!cliToolWrapper?.hasCapacityError?.(text)) return;
      // Only short-circuit if we have a fallback to try.
      if (useModel === GEMINI_FALLBACK_MODEL) return;
      capacityErrorDetected = true;
      console.log(`[CLI fallback] Capacity error detected on ${useModel} — killing child early to fail fast`);
      try {
        child.kill('SIGTERM');
        if (child.pid) { try { process.kill(-child.pid, 'SIGTERM'); } catch { /* not group leader */ } }
        setTimeout(() => {
          try {
            if (child.killed || child.exitCode !== null) return;
            child.kill('SIGKILL');
            if (child.pid) { try { process.kill(-child.pid, 'SIGKILL'); } catch { /* not group leader */ } }
          } catch { /* already gone */ }
        }, 2000).unref();
      } catch (e) {
        console.warn('[CLI fallback] Failed to kill capacity-exhausted child:', e.message);
      }
    }

    child.stdout.on('data', (chunk) => {
      const text = chunk.toString();
      stdout += text;
      if (onChunk) onChunk({ type: 'progress', text });
      tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
      scanForCapacityError(text);

      // agy can keep its process alive after emitting the complete print-mode
      // envelope. Once a terminal envelope is safely parsed, stop that idle
      // process so the synchronous A2A request returns without extra latency.
      if (USE_ANTIGRAVITY_CLI && !antigravityEnvelopeSeen) {
        try {
          const envelope = JSON.parse(stdout.trim());
          if (envelope?.status === 'SUCCESS' || envelope?.status === 'ERROR') {
            antigravityEnvelopeSeen = true;
            child.kill('SIGTERM');
          }
        } catch { /* wait for the rest of the JSON envelope */ }
      }
    });

    child.stderr.on('data', (chunk) => {
      const text = chunk.toString();
      stderr += text;
      scanForCapacityError(text);
    });

    child.on('close', async (code) => {
      task.process = null;
      // Gemini CLI -o json wraps response in { session_id, response, stats }.
      // Hooks/skills/warnings polluem stdout antes do JSON; extraímos só o objeto JSON e seu response.
      let output = stdout.trim();
      const jsonStart = output.lastIndexOf('{\n  "session_id"');
      const jsonMatch = jsonStart >= 0
        ? [output.slice(jsonStart)]
        : output.match(/\{[\s\S]*"response"[\s\S]*\}\s*$/);
      let extractedFromJson = false;
      let parsedEnvelope = null;
      if (jsonMatch) {
        try {
          const parsed = JSON.parse(jsonMatch[0]);
          parsedEnvelope = parsed;
          if (typeof parsed.response === 'string') {
            output = parsed.response;
            extractedFromJson = true;
          }
        } catch { /* fallback to raw output */ }
      }
      // Truncation diagnostics: log model + chars + everything we can extract
      // about why the response ended. If a response ever comes back exactly at
      // the maxOutputTokens cap, finishReason should reveal it.
      try {
        const stats = parsedEnvelope?.stats;
        const tokens = stats?.models?.[useModel]?.tokens
                    || (stats?.models && Object.values(stats.models)[0]?.tokens)
                    || null;
        const finishReason = parsedEnvelope?.candidates?.[0]?.finishReason
                          || parsedEnvelope?.finish_reason
                          || stats?.finish_reason
                          || parsedEnvelope?.stop_reason
                          || null;
        const truncated = finishReason === 'MAX_TOKENS' || finishReason === 'max_tokens';
        const stdoutBytes = Buffer.byteLength(stdout, 'utf8');
        console.log(`[CLI done] task=${task.id?.slice(0,8) || '?'} model=${useModel} chars=${output.length} stdoutBytes=${stdoutBytes} tokens=${tokens?.candidates ?? '?'}/${tokens?.total ?? '?'} finish=${finishReason || 'n/a'}${truncated ? ' ⚠️ TRUNCATED-AT-CAP' : ''}`);
        // First time we see `tokens=?/?` for a given model, dump envelope keys
        // so we know where stats actually live in this CLI version.
        if (!tokens && parsedEnvelope) {
          const keys = Object.keys(parsedEnvelope).join(',');
          const statsKeys = stats ? Object.keys(stats).join(',') : 'no-stats';
          console.log(`[CLI envelope-shape] task=${task.id?.slice(0,8)} top-keys=[${keys}] stats-keys=[${statsKeys}] sample=${JSON.stringify(parsedEnvelope).slice(0, 400)}`);
        }
      } catch (e) { /* logging is best-effort */ }
      // When JSON extraction fails, gemini-cli stdout still contains skill-conflict
      // warnings, /private/tmp EACCES warnings, and the prompt echo. Strip them so
      // we don't ship that as the agent's answer.
      if (!extractedFromJson) {
        const cleaned = cliToolWrapper?.sanitizeCliBootstrap?.(output) ?? output;
        if (cleaned) output = cleaned;
      }
      const errOutput = stderr.trim();

      // Detect capacity/quota/model errors in stderr — try fallback model
      const combinedErr = errOutput + '\n' + output;
      const isQuotaError = combinedErr && (
        combinedErr.includes('RESOURCE_EXHAUSTED') ||
        combinedErr.includes('MODEL_CAPACITY_EXHAUSTED') ||
        combinedErr.includes('quota') ||
        combinedErr.includes('429') ||
        combinedErr.includes('No capacity available')
      );
      const isModelNotFound = combinedErr && (
        combinedErr.includes('ModelNotFoundError') ||
        combinedErr.includes('entity was not found') ||
        (combinedErr.includes('code: 404') && combinedErr.includes('Error'))
      );

      if ((isQuotaError || isModelNotFound) && useModel !== GEMINI_FALLBACK_MODEL) {
        const trigger = capacityErrorDetected ? 'early-kill' : 'post-close';
        console.log(`[CLI fallback] Model ${useModel} ${isModelNotFound ? 'not found' : 'exhausted'} (${trigger}), retrying with ${GEMINI_FALLBACK_MODEL}`);
        executeGeminiCLI(task, onChunk, GEMINI_FALLBACK_MODEL);
        return;
      }

      // Non-zero exit code = failure
      if (code !== 0 && !output) {
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro (code ${code}): ${errOutput || 'Unknown error'}` }] };
        tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
        if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
        return;
      }

      // Non-zero exit with output that looks like an error (not real content)
      if (code !== 0 && output) {
        const looksLikeError = output.includes('critical error') || output.includes('RetryableQuotaError') || output.includes('RESOURCE_EXHAUSTED') || output.includes('ModelNotFoundError');
        if (looksLikeError && useModel !== GEMINI_FALLBACK_MODEL) {
          console.log(`[CLI fallback] Output looks like error, retrying with ${GEMINI_FALLBACK_MODEL}`);
          executeGeminiCLI(task, onChunk, GEMINI_FALLBACK_MODEL);
          return;
        }
        if (looksLikeError) {
          const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro Gemini CLI (${useModel}): modelo indisponível` }] };
          tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
          if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
          return;
        }
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
        runCLIRound(followUp, round + 1);
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
      const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro ao executar Gemini: ${err.message}` }] };
      tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
      if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
    });
  }

  runCLIRound(basePrompt, 0);
}

// ============================================
// DEEP RESEARCH: Interactions API
// ============================================

const DR_POLL_INTERVAL_MS = parseInt(process.env.DR_POLL_INTERVAL_MS || '10000', 10);
const DR_MAX_POLLS = 360; // 60 minutes max

async function createInteraction(input, model, signal, extraTools = [], agentConfigOverrides = {}, builtinTools = {}) {
  // Auth: prefere GEMINI_API_KEY (padrão documentado) com fallback para OAuth Bearer (SA JWT).
  const apiKey = process.env.GEMINI_API_KEY || '';
  const useApiKey = !!apiKey;
  const token = useApiKey ? null : await getAccessToken();

  // Built-in tools ativáveis explicitamente. Defaults: todos true (google_search, url_context,
  // code_execution estão ativos no Deep Research por default, mas podem ser desabilitados
  // omitindo-os do array `tools`).
  const allTools = [...extraTools];
  if (builtinTools.google_search !== false) allTools.push({ type: 'google_search' });
  if (builtinTools.url_context !== false) allTools.push({ type: 'url_context' });
  if (builtinTools.code_execution !== false) allTools.push({ type: 'code_execution' });

  const tools = allTools.length > 0 ? allTools : undefined;

  const agent_config = {
    type: 'deep-research',
    thinking_summaries: 'auto',
    ...agentConfigOverrides,
  };

  const body = JSON.stringify({
    input,
    agent: model,
    background: true,
    store: true, // explícito por boas práticas — default quando background=true
    agent_config,
    ...(tools ? { tools } : {}),
  });

  const headers = { 'Content-Type': 'application/json' };
  if (useApiKey) {
    headers['x-goog-api-key'] = apiKey;
  } else {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return geminiJsonRequest({
    hostname: 'generativelanguage.googleapis.com',
    port: 443,
    path: '/v1beta/interactions',
    method: 'POST',
    headers,
    signal,
  }, body);
}

/** Resolve Deep Research model from mode string */
function resolveDeepResearchModel(mode) {
  switch (String(mode || '').toLowerCase()) {
    case 'max': return 'deep-research-max-preview-04-2026';
    case 'pro': return 'deep-research-pro-preview-12-2025';
    case 'standard':
    default: return 'deep-research-preview-04-2026';
  }
}

/**
 * Follow-up leve: continuação usando modelo standard (não Deep Research agent).
 * Muito mais rápido e barato — pra perguntas pós-relatório sem re-rodar Deep Research.
 * Doc oficial: https://ai.google.dev/gemini-api/docs/deep-research#followup
 */
async function createInteractionFollowup(input, previousInteractionId, model, signal) {
  const apiKey = process.env.GEMINI_API_KEY || '';
  const useApiKey = !!apiKey;
  const token = useApiKey ? null : await getAccessToken();

  const body = JSON.stringify({
    input,
    model: model || 'gemini-3.1-pro-preview',
    previous_interaction_id: previousInteractionId,
  });

  const headers = { 'Content-Type': 'application/json' };
  if (useApiKey) {
    headers['x-goog-api-key'] = apiKey;
  } else {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return geminiJsonRequest({
    hostname: 'generativelanguage.googleapis.com',
    port: 443,
    path: '/v1beta/interactions',
    method: 'POST',
    headers,
    signal,
  }, body);
}

/**
 * Streaming SSE do Deep Research (alternativa ao polling).
 * Stream events: interaction.start, content.delta, interaction.complete, error.
 * Retorna payload equivalente ao GET /interactions/<id> quando complete.
 * Doc: https://ai.google.dev/gemini-api/docs/deep-research#streaming
 */
function createInteractionStream(input, model, signal, extraTools, agentConfigOverrides, builtinTools, onDelta) {
  return new Promise(async (resolve, reject) => {
    try {
      const apiKey = process.env.GEMINI_API_KEY || '';
      const useApiKey = !!apiKey;
      const token = useApiKey ? null : await getAccessToken();

      const allTools = [...(extraTools || [])];
      if (builtinTools?.google_search !== false) allTools.push({ type: 'google_search' });
      if (builtinTools?.url_context !== false) allTools.push({ type: 'url_context' });
      if (builtinTools?.code_execution !== false) allTools.push({ type: 'code_execution' });

      const body = JSON.stringify({
        input,
        agent: model,
        background: true,
        store: true,
        stream: true,
        agent_config: { type: 'deep-research', thinking_summaries: 'auto', ...(agentConfigOverrides || {}) },
        ...(allTools.length > 0 ? { tools: allTools } : {}),
      });

      const headers = { 'Content-Type': 'application/json', 'Accept': 'text/event-stream' };
      if (useApiKey) headers['x-goog-api-key'] = apiKey;
      else headers['Authorization'] = `Bearer ${token}`;

      const accumulated = { outputs: [], id: null, status: 'in_progress' };
      let buffer = '';
      let lastEventId = null;

      const req = https.request({
        hostname: 'generativelanguage.googleapis.com',
        port: 443,
        path: '/v1beta/interactions',
        method: 'POST',
        headers,
        signal,
      }, (res) => {
        if (res.statusCode !== 200) {
          const chunks = [];
          res.on('data', c => chunks.push(c));
          res.on('end', () => reject(new Error(`SSE HTTP ${res.statusCode}: ${Buffer.concat(chunks).toString().slice(0, 400)}`)));
          return;
        }

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
              if (evt.event_id) lastEventId = evt.event_id;
              // Extrai ID da interaction assim que chegar
              if (evt.interaction?.id && !accumulated.id) accumulated.id = evt.interaction.id;
              // Delta de conteúdo → emite chunk pra caller
              if (evt.event_type === 'content.delta' && evt.delta) {
                if (onDelta) onDelta(evt.delta);
              }
              // Complete → injeta no accumulated
              if (evt.event_type === 'interaction.complete') {
                accumulated.status = 'completed';
                if (evt.interaction?.outputs) accumulated.outputs = evt.interaction.outputs;
              }
              if (evt.event_type === 'error') {
                accumulated.status = 'failed';
                accumulated.error = evt.error || evt;
              }
            } catch (parseErr) {
              // Ignora chunks malformados
            }
          }
        });

        res.on('end', () => {
          accumulated.lastEventId = lastEventId;
          resolve(accumulated);
        });
      });

      if (signal) {
        signal.addEventListener('abort', () => req.destroy(new Error('Stream aborted')), { once: true });
      }
      req.on('error', reject);
      req.write(body);
      req.end();
    } catch (err) {
      reject(err);
    }
  });
}

async function pollInteraction(id, signal) {
  const apiKey = process.env.GEMINI_API_KEY || '';
  const useApiKey = !!apiKey;
  const token = useApiKey ? null : await getAccessToken();

  const headers = {};
  if (useApiKey) {
    headers['x-goog-api-key'] = apiKey;
  } else {
    headers['Authorization'] = `Bearer ${token}`;
  }

  return geminiJsonRequest({
    hostname: 'generativelanguage.googleapis.com',
    port: 443,
    path: `/v1beta/interactions/${encodeURIComponent(id)}`,
    method: 'GET',
    headers,
    signal,
  }, null);
}

async function executeDeepResearch(task, onChunk, runContext = {}) {
  const signal = runContext?.signal;
  tm.updateTask(task, { status: { state: 'working' } });

  const prompt = extractPromptText(task.history[0] || {});

  // Mode resolution: "pro" | "max" | "standard". Backward-compat: deepResearchMax=true → "max"
  const mode = task.metadata?.deepResearchMode
    || (task.metadata?.deepResearchMax === true ? 'max' : 'standard');
  const model = resolveDeepResearchModel(mode);

  const progressUpdate = (text) => {
    if (onChunk) onChunk({ type: 'progress', text });
    tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
  };

  try {
    // Build extra tools from metadata: mcp_servers and/or file_search_store_names
    const extraTools = [];
    for (const mcp of (task.metadata?.mcpServers || [])) {
      extraTools.push({ type: 'mcp_server', ...mcp });
    }
    const storeNames = task.metadata?.fileSearchStoreNames || [];
    if (storeNames.length > 0) {
      extraTools.push({ type: 'file_search', file_search_store_names: storeNames });
    }

    // Build multimodal input: text + documents (PDFs via uri+mime_type) + images (via uri).
    // Spec oficial: https://ai.google.dev/gemini-api/docs/deep-research#multimodal-input
    const documents = task.metadata?.documents || [];
    const imageInputs = task.metadata?.images || [];
    const hasMultimodal = documents.length > 0 || imageInputs.length > 0;
    const input = hasMultimodal
      ? [
          { type: 'text', text: prompt },
          ...documents.map(d => ({
            type: 'document',
            uri: d.uri,
            mime_type: d.mime_type || d.mimeType || 'application/pdf',
          })),
          ...imageInputs.map(img => ({
            type: 'image',
            uri: typeof img === 'string' ? img : img.uri,
          })),
        ]
      : prompt;

    // Agent config overrides from metadata
    const agentConfigOverrides = {};
    if (task.metadata?.collaborativePlanning === true) agentConfigOverrides.collaborative_planning = true;
    if (task.metadata?.visualization !== undefined) {
      agentConfigOverrides.visualization = task.metadata.visualization ? 'auto' : 'off';
    }

    // Built-in tools: google_search, url_context, code_execution — default true cada,
    // podem ser desativadas via metadata.builtinTools = { google_search: false, ... }
    const builtinTools = task.metadata?.builtinTools || {};

    const toolsDesc = extraTools.length > 0
      ? ` + ${extraTools.map(t => t.type === 'mcp_server' ? `MCP:${t.name || t.url}` : `FileSearch(${storeNames.length})`).join(', ')}`
      : '';
    const disabledTools = Object.entries(builtinTools).filter(([, v]) => v === false).map(([k]) => `-${k}`);
    const builtinDesc = disabledTools.length > 0 ? ` | disabled: ${disabledTools.join(',')}` : '';
    const docsDesc = documents.length > 0 ? ` + ${documents.length} docs` : '';
    const configDesc = Object.keys(agentConfigOverrides).length > 0
      ? ` | ${Object.keys(agentConfigOverrides).join(',')}`
      : '';
    const useStream = task.metadata?.stream === true;
    progressUpdate(`🔬 Iniciando Deep Research (${model})${useStream ? ' [SSE streaming]' : ''}${toolsDesc}${docsDesc}${configDesc}${builtinDesc}...\n`);

    // Caminho SSE: stream direto, sem polling
    if (useStream) {
      const streamResult = await createInteractionStream(
        input, model, signal, extraTools, agentConfigOverrides, builtinTools,
        (delta) => {
          // Emite cada delta como chunk progress pro caller
          if (delta.type === 'text' && delta.text) progressUpdate(delta.text);
          else if (delta.type === 'thought_summary' && delta.text) progressUpdate(`💭 ${delta.text}\n`);
          else if (delta.type === 'image') progressUpdate(`🖼️  [imagem gerada]\n`);
        }
      );

      if (streamResult.status !== 'completed') {
        throw new Error(`Stream falhou: ${JSON.stringify(streamResult.error || streamResult).slice(0, 300)}`);
      }
      // Reutiliza o mesmo pipeline de processamento abaixo
      const result = streamResult;
      const outputs = result.outputs || [];
      const textOutput = outputs.filter(o => o.type === 'text').map(o => o.text).join('\n\n');
      if (!textOutput.trim()) throw new Error('Stream retornou output vazio');

      // Imagens (mesmo tratamento do polling path — factorizado inline aqui porque SSE
      // já sai do polling loop antes)
      const images = outputs.filter(o => o.type === 'image');
      const savedImages = [];
      if (images.length > 0) {
        const imgDir = `/tmp/dr-images/${task.id}`;
        try {
          fs.mkdirSync(imgDir, { recursive: true });
          images.forEach((img, i) => {
            const ext = (img.mime_type || 'image/png').split('/')[1] || 'png';
            const filepath = `${imgDir}/chart-${String(i + 1).padStart(2, '0')}.${ext}`;
            const buf = Buffer.from(img.data || '', 'base64');
            fs.writeFileSync(filepath, buf);
            savedImages.push({ path: filepath, mime: img.mime_type, bytes: buf.length });
          });
          progressUpdate(`\n🖼️  Salvou ${images.length} imagem(ns) em ${imgDir}/\n`);
        } catch (_) {}
      }
      const imgRefs = savedImages.length > 0
        ? '\n\n---\n\n### Visualizações Geradas\n\n' +
          savedImages.map((im, i) => `- ![Chart ${i+1}](${im.path}) — ${im.mime}, ${im.bytes} bytes`).join('\n')
        : '';
      const finalText = textOutput + imgRefs;

      const agentMessage = { role: 'agent', parts: [{ type: 'text', text: finalText }] };
      const artifacts = [
        ...extractArtifacts(finalText),
        ...savedImages.map((im, i) => ({
          name: `chart-${i+1}`,
          description: `Visualização gerada (${im.mime})`,
          parts: [{ type: 'text', text: im.path }],
        })),
      ];

      tm.updateTask(task, {
        status: { state: 'completed', message: agentMessage },
        history: [...task.history, agentMessage],
        artifacts: [...task.artifacts, ...artifacts],
      });
      if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
      return;
    }

    const interaction = await createInteraction(input, model, signal, extraTools, agentConfigOverrides, builtinTools);
    if (interaction.error) {
      throw new Error(interaction.error.message || JSON.stringify(interaction.error));
    }

    const interactionId = interaction.id;
    if (!interactionId) throw new Error('Nenhum interaction ID retornado pela API');

    progressUpdate(`📋 Interaction ID: ${interactionId}\n⏳ Pesquisando...\n`);

    let polls = 0;
    let result;
    while (polls < DR_MAX_POLLS) {
      if (signal?.aborted) throw new Error('Request aborted');
      await abortableSleep(DR_POLL_INTERVAL_MS, signal);
      polls++;

      result = await pollInteraction(interactionId, signal);
      if (result.error) throw new Error(result.error.message || JSON.stringify(result.error));

      if (polls % 6 === 0) {
        const elapsed = Math.round((polls * DR_POLL_INTERVAL_MS) / 1000);
        progressUpdate(`⏳ Pesquisando... (${elapsed}s decorridos)\n`);
      }

      if (result.status === 'completed') break;
      if (result.status === 'failed') {
        throw new Error(`Deep Research falhou: ${result.error?.message || 'Erro desconhecido'}`);
      }
    }

    if (result?.status !== 'completed') {
      throw new Error(`Deep Research timeout após ${Math.round((polls * DR_POLL_INTERVAL_MS) / 1000)}s`);
    }

    const outputs = result.outputs || [];
    const textOutput = outputs.filter(o => o.type === 'text').map(o => o.text).join('\n\n');
    if (!textOutput.trim()) throw new Error('Deep Research retornou output vazio');

    // Processa outputs do tipo 'image' (geradas via visualization=auto) → salva como PNG
    const images = outputs.filter(o => o.type === 'image');
    const savedImages = [];
    if (images.length > 0) {
      const imgDir = `/tmp/dr-images/${task.id}`;
      try {
        fs.mkdirSync(imgDir, { recursive: true });
        images.forEach((img, i) => {
          const ext = (img.mime_type || 'image/png').split('/')[1] || 'png';
          const filepath = `${imgDir}/chart-${String(i + 1).padStart(2, '0')}.${ext}`;
          const buf = Buffer.from(img.data || '', 'base64');
          fs.writeFileSync(filepath, buf);
          savedImages.push({ path: filepath, mime: img.mime_type, bytes: buf.length });
        });
        progressUpdate(`🖼️  Salvou ${images.length} imagem(ns) em ${imgDir}/\n`);
      } catch (imgErr) {
        progressUpdate(`⚠️  Falha ao salvar imagens: ${imgErr.message}\n`);
      }
    }

    // Concatena referências às imagens no final do texto pra ficar auditável
    const imgRefs = savedImages.length > 0
      ? '\n\n---\n\n### Visualizações Geradas\n\n' +
        savedImages.map((im, i) => `- ![Chart ${i+1}](${im.path}) — ${im.mime}, ${im.bytes} bytes`).join('\n')
      : '';
    const finalText = textOutput + imgRefs;

    const agentMessage = { role: 'agent', parts: [{ type: 'text', text: finalText }] };
    const artifacts = [
      ...extractArtifacts(finalText),
      ...savedImages.map((im, i) => ({
        name: `chart-${i+1}`,
        description: `Visualização gerada pelo Deep Research (${im.mime})`,
        parts: [{ type: 'text', text: im.path }],
      })),
    ];

    tm.updateTask(task, {
      status: { state: 'completed', message: agentMessage },
      history: [...task.history, agentMessage],
      artifacts: [...task.artifacts, ...artifacts],
    });
    if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
  } catch (e) {
    const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro Deep Research: ${e.message}` }] };
    tm.updateTask(task, {
      status: { state: 'failed', message: errorMessage },
      history: [...task.history, errorMessage],
    });
    if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
  }
}

// ============================================
// FOLLOW-UP (modelo standard, síncrono)
// ============================================

async function executeInteractionFollowup(task, onChunk, runContext = {}) {
  const signal = runContext?.signal;
  tm.updateTask(task, { status: { state: 'working' } });

  const prompt = extractPromptText(task.history[0] || {});
  const previousId = task.metadata?.previousInteractionId;
  const model = task.metadata?.followupModel || 'gemini-3.1-pro-preview';

  const progressUpdate = (text) => {
    if (onChunk) onChunk({ type: 'progress', text });
    tm.taskEmitter.emit(`task:${task.id}:chunk`, text);
  };

  if (!previousId) {
    const msg = { role: 'agent', parts: [{ type: 'text', text: 'Erro: previousInteractionId ausente na metadata' }] };
    tm.updateTask(task, { status: { state: 'failed', message: msg }, history: [...task.history, msg] });
    if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
    return;
  }

  try {
    progressUpdate(`💬 Follow-up leve (${model}) continuando interaction ${previousId.slice(0, 24)}...\n`);
    const resp = await createInteractionFollowup(prompt, previousId, model, signal);
    if (resp.error) throw new Error(resp.error.message || JSON.stringify(resp.error));

    const outputs = resp.outputs || [];
    const textOutput = outputs.filter(o => o.type === 'text').map(o => o.text).join('\n\n');
    if (!textOutput.trim()) throw new Error('Follow-up retornou output vazio');

    const agentMessage = { role: 'agent', parts: [{ type: 'text', text: textOutput }] };
    const artifacts = extractArtifacts(textOutput);

    tm.updateTask(task, {
      status: { state: 'completed', message: agentMessage },
      history: [...task.history, agentMessage],
      artifacts: [...task.artifacts, ...artifacts],
    });
    if (onChunk) onChunk({ type: 'completed', task: tm.taskToJSON(task) });
  } catch (e) {
    const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro Follow-up: ${e.message}` }] };
    tm.updateTask(task, {
      status: { state: 'failed', message: errorMessage },
      history: [...task.history, errorMessage],
    });
    if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
  }
}

// ============================================
// MAIN TASK EXECUTOR
// ============================================

function executeGeminiTask(task, onChunk, runContext = {}) {
  // Follow-up leve: metadata.interactionFollowup + previousInteractionId
  if (task.metadata?.interactionFollowup === true && task.metadata?.previousInteractionId) {
    return executeInteractionFollowup(task, onChunk, runContext);
  }
  // Deep Research: triggered by metadata.deepResearch or prompt prefix [deep-research]
  const firstPrompt = extractPromptText(task.history[0] || {});
  if (task.metadata?.deepResearch === true || /^\[?deep[-\s]?research[:\]]?\s*/i.test(firstPrompt.trim())) {
    return executeDeepResearch(task, onChunk, runContext);
  }

  console.log(`[executeGeminiTask] task=${task.id?.slice(0,8)} branch=${USE_API ? 'API' : 'CLI'} (USE_API=${USE_API} USE_CLI=${USE_CLI} FORCE_CLI=${FORCE_CLI})`);
  if (USE_API) {
    // API-first: use gemini-3.1-pro-preview via API, fallback to CLI with gemini-2.5-pro
    executeGeminiAPIWithTools(task, onChunk, runContext).catch(err => {
      console.error(`[API→CLI fallback] task=${task.id?.slice(0,8)} API error: ${err.message?.slice(0, 200)}`);
      if (USE_CLI) {
        tm.updateTask(task, { status: { state: 'working' } });
        console.log(`[CLI fallback] Task ${task.id} retrying via Gemini CLI (model: ${GEMINI_CLI_MODEL})`);
        executeGeminiCLI(task, onChunk, GEMINI_CLI_MODEL);
      } else {
        const errorMessage = { role: 'agent', parts: [{ type: 'text', text: `Erro API Gemini: ${err.message}` }] };
        tm.updateTask(task, { status: { state: 'failed', message: errorMessage }, history: [...task.history, errorMessage] });
        if (onChunk) onChunk({ type: 'failed', task: tm.taskToJSON(task) });
      }
    });
    return;
  }
  // CLI-only mode (USE_CLI=force)
  return executeGeminiCLI(task, onChunk, GEMINI_CLI_MODEL);
}

// ============================================
// AGENT CARD
// ============================================

const AGENT_CARD = {
  name: 'Gemini Agent',
  description: 'Agente Gemini CLI exposto via protocolo A2A. Executa tarefas de programacao, review, debug e geracao de codigo usando Google Gemini.',
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
    { id: 'multimodal', name: 'Multimodal', description: 'Analise de imagens, audio e video', tags: ['multimodal', 'vision'] },
    { id: 'search', name: 'Busca e Pesquisa', description: 'Pesquisa na web e analise de informacoes atualizadas', tags: ['search', 'web'] },
    { id: 'deep-research', name: 'Deep Research', description: 'Pesquisa profunda autonoma via Interactions API. Ativa com metadata.deepResearch=true ou prefixo [deep-research]. Modo max com metadata.deepResearchMax=true.', tags: ['research', 'deep-research', 'interactions-api'] },
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
  model: FORCE_CLI && USE_ANTIGRAVITY_CLI ? ANTIGRAVITY_MODEL : GEMINI_MODEL,
  cliModel: USE_API && USE_CLI ? GEMINI_CLI_MODEL : undefined,
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
  teamExecutor,
  consensusExecutor,
  ensembleExecutor: codeEnsembleExecutor,
  debateExecutor,
  planExecutor,
  executeTask: executeGeminiTask,
});
