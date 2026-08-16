#!/usr/bin/env node

import { spawn, spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import http from "node:http";
import net from "node:net";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import { AGENT_CATALOG } from "../runtime/a2a-shared/agent-catalog.js";
import {
  inspectCursorMcp,
  removeCursorMcp,
  upsertCursorMcp,
} from "../runtime/a2a-shared/cursor-mcp-config.js";

export const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const RUNTIME_ROOT = path.join(PACKAGE_ROOT, "runtime");
export const AGENTS = Object.freeze(Object.fromEntries(
  Object.entries(AGENT_CATALOG).map(([id, definition]) => [id, {
    ...definition,
    entry: path.join(RUNTIME_ROOT, `a2a-${id}`, "server.js"),
  }]),
));

function usage() {
  return `A2A Mesh — servidores locais, MCP e painel multiagente

Uso:
  a2a-mesh install [--launchd] [--no-start]
  a2a-mesh start|stop|restart|status|doctor
  a2a-mesh open [--sandbox]
  a2a-mesh mcp [--replace-mcp]
  a2a-mesh uninstall [--purge]

Opções:
  --home <pasta>       usar outra HOME
  --targets <lista>    registrar MCP em codex,claude,cursor (padrão: todos)
  --launchd            instalar serviço de usuário no macOS
  --no-start           instalar sem iniciar os servidores
  --replace-mcp        substituir configuração MCP de mesmo nome
  --sandbox            abrir o painel de terminais
  --dry-run            mostrar ações sem alterar o sistema
  --json               emitir JSON
  --purge              remover também token, banco, logs e estado
`;
}

function nextValue(argv, index, flag) {
  if (index + 1 >= argv.length) throw new Error(`${flag} exige um valor`);
  return argv[index + 1];
}

export function parseArgs(argv) {
  const args = {
    command: argv[0] || "help",
    home: os.homedir(),
    targets: ["codex", "claude", "cursor"],
    launchd: false,
    start: true,
    replaceMcp: false,
    sandbox: false,
    dryRun: false,
    json: false,
    purge: false,
  };
  for (let index = 1; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--home") {
      args.home = path.resolve(nextValue(argv, index, value));
      index += 1;
    } else if (value === "--targets") {
      args.targets = nextValue(argv, index, value).split(",").map((item) => item.trim()).filter(Boolean);
      index += 1;
    } else if (value === "--launchd") args.launchd = true;
    else if (value === "--no-start") args.start = false;
    else if (value === "--replace-mcp") args.replaceMcp = true;
    else if (value === "--sandbox") args.sandbox = true;
    else if (value === "--dry-run") args.dryRun = true;
    else if (value === "--json") args.json = true;
    else if (value === "--purge") args.purge = true;
    else throw new Error(`opção desconhecida: ${value}`);
  }
  const invalid = args.targets.filter((target) => !["codex", "claude", "cursor"].includes(target));
  if (invalid.length) throw new Error(`alvos MCP não suportados: ${invalid.join(",")}`);
  return args;
}

export function pathsFor(home) {
  const stateRoot = path.join(home, ".local", "state", "a2a-mesh");
  return {
    tokenFile: path.join(home, ".a2a", "auth-token"),
    dbFile: path.join(home, ".a2a", "mesh.db"),
    stateRoot,
    pidFile: path.join(stateRoot, "pids.json"),
    logRoot: path.join(stateRoot, "logs"),
    dataRoot: path.join(stateRoot, "tasks"),
    installState: path.join(stateRoot, "install-state.json"),
    launchAgent: path.join(home, "Library", "LaunchAgents", "com.nicholasjacob.a2a-mesh.plist"),
    bridge: path.join(RUNTIME_ROOT, "a2a-shared", "mesh-bridge-mcp.js"),
  };
}

function writeAtomic(file, value, mode = 0o600) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temporary = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.tmp`);
  fs.writeFileSync(temporary, value, { mode });
  fs.renameSync(temporary, file);
}

function writeJson(file, value, mode = 0o600) {
  writeAtomic(file, `${JSON.stringify(value, null, 2)}\n`, mode);
}

function readJson(file, fallback = null) {
  try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return fallback; }
}

function executable(binary, env = process.env) {
  for (const directory of String(env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    const candidate = path.join(directory, binary);
    try {
      fs.accessSync(candidate, fs.constants.X_OK);
      return candidate;
    } catch {
      // Continua procurando.
    }
  }
  return null;
}

export function agentCliAvailability(env = process.env) {
  return Object.fromEntries(Object.entries(AGENTS).map(([name, definition]) => [name, {
    available: Boolean(executable(definition.cliBinary, env)),
    binary: definition.cliBinary,
  }]));
}

export function cursorModelAvailability(env = process.env) {
  const definition = AGENTS.grok;
  const binary = executable(definition.cliBinary, env);
  if (!binary) return { available: false, binary: null, model: definition.model, reason: `CLI ausente: ${definition.cliBinary}` };
  const probe = command(binary, ["--list-models"], { env });
  const models = probe.status === 0
    ? probe.stdout.split(/\r?\n/).map((line) => line.trim().split(/\s+-\s+|\s+/)[0]).filter(Boolean)
    : [];
  const available = models.includes(definition.model);
  return {
    available,
    binary,
    model: definition.model,
    models,
    reason: available ? null : (probe.status === 0
      ? `modelo indisponível: ${definition.model}`
      : `falha ao consultar modelos do Cursor: ${probe.error || probe.stderr.trim() || `status ${probe.status}`}`),
  };
}

function command(binary, argv, options = {}) {
  if (options.dryRun) return { status: 0, stdout: "", stderr: "", simulated: true };
  const result = spawnSync(binary, argv, {
    encoding: "utf8",
    env: options.env || process.env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  return {
    status: result.status ?? 1,
    stdout: result.stdout || "",
    stderr: result.stderr || "",
    error: result.error?.message,
  };
}

function ensureToken(tokenFile, dryRun) {
  if (fs.existsSync(tokenFile)) return { created: false, file: tokenFile };
  if (!dryRun) writeAtomic(tokenFile, `${crypto.randomBytes(32).toString("base64url")}\n`, 0o600);
  return { created: true, file: tokenFile };
}

function serverEnvironment(home) {
  const paths = pathsFor(home);
  const agentEnvironment = {};
  for (const [id, definition] of Object.entries(AGENTS)) {
    const upper = id.toUpperCase();
    agentEnvironment[`A2A_${upper}_PORT`] = String(definition.port);
    agentEnvironment[`A2A_${upper}_DATA_DIR`] = path.join(paths.dataRoot, id);
  }
  return {
    ...process.env,
    PATH: [path.join(home, ".local", "bin"), process.env.PATH || ""].filter(Boolean).join(path.delimiter),
    HOME: home,
    A2A_BASE_DIR: RUNTIME_ROOT,
    A2A_AUTH_TOKEN_FILE: paths.tokenFile,
    A2A_BIND_HOST: "127.0.0.1",
    A2A_ALLOW_NO_TOKEN: process.env.A2A_ALLOW_NO_TOKEN || "false",
    A2A_AUTO_START: "true",
    A2A_ENABLE_SHELL_EXEC: process.env.A2A_ENABLE_SHELL_EXEC || "false",
    A2A_SHELL_FULL_ACCESS: process.env.A2A_SHELL_FULL_ACCESS || "false",
    A2A_TIMEOUT_CALL_MS: process.env.A2A_TIMEOUT_CALL_MS || "1800000",
    A2A_TIMEOUT_CONSENSUS_MS: process.env.A2A_TIMEOUT_CONSENSUS_MS || "1800000",
    A2A_TIMEOUT_DEBATE_MS: process.env.A2A_TIMEOUT_DEBATE_MS || "1800000",
    A2A_TIMEOUT_ENSEMBLE_MS: process.env.A2A_TIMEOUT_ENSEMBLE_MS || "1800000",
    A2A_MESH_OPERATION_TIMEOUT_MS: process.env.A2A_MESH_OPERATION_TIMEOUT_MS || "86400000",
    ...agentEnvironment,
    CODEX_CLI_MODEL: process.env.CODEX_CLI_MODEL || "gpt-5.6-sol",
    CODEX_MODEL: process.env.CODEX_MODEL || "gpt-5.6-sol",
    CODEX_REASONING_EFFORT: process.env.CODEX_REASONING_EFFORT || "xhigh",
    CLAUDE_CLI_MODEL: process.env.CLAUDE_CLI_MODEL || "claude-opus-5",
    A2A_GROK_MODEL: "cursor-grok-4.6-high",
    USE_CLI: process.env.USE_CLI || "force",
  };
}

export function health(port, timeoutMs = 1500) {
  return new Promise((resolve) => {
    const request = http.get(`http://127.0.0.1:${port}/health`, (response) => {
      const chunks = [];
      response.on("data", (chunk) => chunks.push(chunk));
      response.on("end", () => {
        try {
          const body = JSON.parse(Buffer.concat(chunks).toString("utf8"));
          resolve(response.statusCode === 200 && body.status === "ok" ? body : null);
        } catch { resolve(null); }
      });
    });
    request.setTimeout(timeoutMs, () => { request.destroy(); resolve(null); });
    request.on("error", () => resolve(null));
  });
}

function portOpen(port, timeoutMs = 500) {
  return new Promise((resolve) => {
    const socket = net.createConnection({ host: "127.0.0.1", port });
    const done = (value) => { socket.destroy(); resolve(value); };
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => done(true));
    socket.once("timeout", () => done(false));
    socket.once("error", () => done(false));
  });
}

async function waitForHealth(port, timeoutMs = 20000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const value = await health(port, 1000);
    if (value) return value;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return null;
}

async function startServers(args, { foreground = false } = {}) {
  const paths = pathsFor(args.home);
  if (args.dryRun) return { started: Object.keys(AGENTS), existing: [], pids: {}, simulated: true };
  ensureToken(paths.tokenFile, false);
  fs.mkdirSync(paths.logRoot, { recursive: true });
  fs.mkdirSync(paths.dataRoot, { recursive: true });
  const existing = [];
  const started = [];
  const unavailable = [];
  const pids = {};
  const children = [];
  const runtimeEnvironment = serverEnvironment(args.home);
  const availability = agentCliAvailability(runtimeEnvironment);
  const grokAvailability = availability.grok.available ? cursorModelAvailability(runtimeEnvironment) : null;
  for (const [name, definition] of Object.entries(AGENTS)) {
    if (!availability[name].available) {
      unavailable.push({ name, reason: `CLI ausente: ${definition.cliBinary}` });
      continue;
    }
    if (name === "grok" && !grokAvailability?.available) {
      unavailable.push({ name, reason: grokAvailability?.reason || `modelo indisponível: ${definition.model}` });
      continue;
    }
    const current = await health(definition.port);
    if (current) {
      existing.push(name);
      continue;
    }
    if (await portOpen(definition.port)) {
      throw new Error(`porta ${definition.port} ocupada, mas /health não responde (${name})`);
    }
    const logFile = path.join(paths.logRoot, `${name}.log`);
    const log = fs.openSync(logFile, "a", 0o600);
    const child = spawn(process.execPath, [definition.entry], {
      cwd: path.dirname(definition.entry),
      detached: !foreground,
      env: { ...runtimeEnvironment, A2A_PORT: String(definition.port) },
      stdio: ["ignore", log, log],
    });
    fs.closeSync(log);
    if (!foreground) child.unref();
    children.push(child);
    pids[name] = child.pid;
    const ready = await waitForHealth(definition.port);
    if (!ready) throw new Error(`${name} não ficou saudável; consulte ${logFile}`);
    started.push(name);
  }
  if (!foreground) writeJson(paths.pidFile, { createdAt: new Date().toISOString(), pids });
  return { started, existing, unavailable, pids, children };
}

function processAlive(pid) {
  try { process.kill(pid, 0); return true; } catch { return false; }
}

async function stopServers(args) {
  const paths = pathsFor(args.home);
  const state = readJson(paths.pidFile, { pids: {} });
  const stopped = [];
  const preserved = [];
  for (const [name, pid] of Object.entries(state.pids || {})) {
    if (!Number.isInteger(pid) || !processAlive(pid)) continue;
    if (!args.dryRun) process.kill(pid, "SIGTERM");
    stopped.push({ name, pid });
  }
  for (const [name, definition] of Object.entries(AGENTS)) {
    if (await health(definition.port, 500) && !(state.pids || {})[name]) preserved.push(name);
  }
  if (!args.dryRun) fs.rmSync(paths.pidFile, { force: true });
  return { stopped, preserved };
}

async function statusReport(args) {
  const paths = pathsFor(args.home);
  const configured = readJson(paths.installState, null);
  const agents = {};
  for (const [name, definition] of Object.entries(AGENTS)) {
    const value = await health(definition.port);
    agents[name] = { online: Boolean(value), port: definition.port, health: value };
  }
  return {
    ok: true,
    command: "status",
    installed: Boolean(configured),
    packageVersion: JSON.parse(fs.readFileSync(path.join(PACKAGE_ROOT, "package.json"), "utf8")).version,
    panel: "http://127.0.0.1:3142/ui",
    sandbox: "http://127.0.0.1:3142/sandbox",
    agents,
  };
}

function mcpGet(target, env) {
  if (target === "cursor") {
    if (!executable("cursor-agent", env)) return { present: false, missingCli: true, output: "" };
    const state = inspectCursorMcp({ home: env.HOME, nodePath: process.execPath, bridge: pathsFor(env.HOME).bridge });
    return { present: state.present, missingCli: false, output: JSON.stringify(state.entry || {}), state };
  }
  if (!executable(target, env)) return { present: false, missingCli: true, output: "" };
  const argv = target === "codex" ? ["mcp", "get", "a2a-mesh", "--json"] : ["mcp", "get", "a2a-mesh"];
  const result = command(target, argv, { env });
  return { present: result.status === 0, missingCli: false, output: `${result.stdout}${result.stderr}`, result };
}

function registerMcp(args) {
  const bridge = pathsFor(args.home).bridge;
  const env = { ...process.env, HOME: args.home };
  const results = {};
  for (const target of args.targets) {
    if (target === "cursor") {
      if (!executable("cursor-agent", env)) {
        results[target] = { status: "missing-cli" };
        continue;
      }
      results[target] = upsertCursorMcp({
        home: args.home,
        nodePath: process.execPath,
        bridge,
        replace: args.replaceMcp,
        dryRun: args.dryRun,
      });
      continue;
    }
    const current = mcpGet(target, env);
    if (current.missingCli) {
      results[target] = { status: "missing-cli" };
      continue;
    }
    if (current.present && current.output.includes(bridge)) {
      results[target] = { status: "already-configured", bridge };
      continue;
    }
    if (current.present && !args.replaceMcp) {
      results[target] = { status: "preserved-existing", bridge: current.output.match(/\/[^\s]+mesh-bridge-mcp\.js/)?.[0] || null };
      continue;
    }
    if (current.present) {
      const removeArgs = target === "claude" ? ["mcp", "remove", "a2a-mesh", "--scope", "user"] : ["mcp", "remove", "a2a-mesh"];
      const removed = command(target, removeArgs, { env, dryRun: args.dryRun });
      if (removed.status !== 0) throw new Error(`não foi possível remover MCP anterior de ${target}: ${removed.stderr || removed.stdout}`);
    }
    const addArgs = target === "claude"
      ? ["mcp", "add", "--scope", "user", "a2a-mesh", "--", process.execPath, bridge]
      : ["mcp", "add", "a2a-mesh", "--", process.execPath, bridge];
    const added = command(target, addArgs, { env, dryRun: args.dryRun });
    if (added.status !== 0) throw new Error(`não foi possível registrar MCP em ${target}: ${added.stderr || added.stdout}`);
    results[target] = { status: current.present ? "replaced" : "configured", bridge };
  }
  return results;
}

function unregisterMcp(args) {
  const bridge = pathsFor(args.home).bridge;
  const env = { ...process.env, HOME: args.home };
  const results = {};
  for (const target of args.targets) {
    if (target === "cursor") {
      results[target] = removeCursorMcp({
        home: args.home,
        nodePath: process.execPath,
        bridge,
        dryRun: args.dryRun,
      });
      continue;
    }
    const current = mcpGet(target, env);
    if (current.missingCli || !current.present) {
      results[target] = { status: current.missingCli ? "missing-cli" : "absent" };
      continue;
    }
    if (!current.output.includes(bridge)) {
      results[target] = { status: "preserved-existing" };
      continue;
    }
    const removeArgs = target === "claude"
      ? ["mcp", "remove", "a2a-mesh", "--scope", "user"]
      : ["mcp", "remove", "a2a-mesh"];
    const removed = command(target, removeArgs, { env, dryRun: args.dryRun });
    if (removed.status !== 0) throw new Error(`não foi possível remover MCP de ${target}: ${removed.stderr || removed.stdout}`);
    results[target] = { status: args.dryRun ? "simulated" : "removed" };
  }
  return results;
}

function launchAgentXml(home) {
  const cli = fileURLToPath(import.meta.url);
  const escaped = (value) => value.replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  const servicePath = [...new Set([
    path.join(home, ".local", "bin"),
    "/opt/homebrew/bin",
    "/usr/local/bin",
    "/usr/bin",
    "/bin",
    "/usr/sbin",
    "/sbin",
    ...String(process.env.PATH || "").split(path.delimiter).filter(Boolean),
  ])].join(path.delimiter);
  return `<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.nicholasjacob.a2a-mesh</string>
  <key>ProgramArguments</key><array>
    <string>${escaped(process.execPath)}</string><string>${escaped(cli)}</string><string>serve</string>
    <string>--home</string><string>${escaped(home)}</string>
  </array>
  <key>EnvironmentVariables</key><dict>
    <key>PATH</key><string>${escaped(servicePath)}</string>
    <key>HOME</key><string>${escaped(home)}</string>
  </dict>
  <key>RunAtLoad</key><true/><key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>10</integer>
</dict></plist>
`;
}

function installLaunchAgent(args) {
  if (process.platform !== "darwin") return { status: "unsupported-platform" };
  const file = pathsFor(args.home).launchAgent;
  if (args.dryRun) return { status: "simulated", file };
  writeAtomic(file, launchAgentXml(args.home), 0o644);
  const domain = `gui/${process.getuid()}`;
  command("launchctl", ["bootout", domain, file], { env: process.env });
  const loaded = command("launchctl", ["bootstrap", domain, file], { env: process.env });
  if (loaded.status !== 0) throw new Error(`launchctl bootstrap falhou: ${loaded.stderr || loaded.stdout}`);
  return { status: "installed", file };
}

function removeLaunchAgent(args) {
  const file = pathsFor(args.home).launchAgent;
  if (!fs.existsSync(file)) return { status: "absent" };
  if (!args.dryRun && process.platform === "darwin") {
    command("launchctl", ["bootout", `gui/${process.getuid()}`, file], { env: process.env });
    fs.rmSync(file, { force: true });
  }
  return { status: args.dryRun ? "simulated" : "removed", file };
}

async function install(args) {
  const paths = pathsFor(args.home);
  const token = ensureToken(paths.tokenFile, args.dryRun);
  const mcp = registerMcp(args);
  const launchd = args.launchd ? installLaunchAgent(args) : { status: "not-requested" };
  const servers = args.start && !args.launchd ? await startServers(args) : { status: args.start ? "managed-by-launchd" : "not-started" };
  const state = {
    schema: "a2a_mesh_install_v1",
    installedAt: new Date().toISOString(),
    packageRoot: PACKAGE_ROOT,
    runtimeRoot: RUNTIME_ROOT,
    mcp,
    launchd,
  };
  if (!args.dryRun) writeJson(paths.installState, state);
  return { ok: true, command: "install", simulation: args.dryRun, token, mcp, launchd, servers, panel: "http://127.0.0.1:3142/ui" };
}

async function doctor(args) {
  const report = await statusReport(args);
  const checks = [];
  for (const file of [pathsFor(args.home).bridge, ...Object.values(AGENTS).map((agent) => agent.entry)]) {
    checks.push({ name: `file:${path.basename(path.dirname(file))}/${path.basename(file)}`, ok: fs.existsSync(file) });
  }
  checks.push({ name: "token", ok: fs.existsSync(pathsFor(args.home).tokenFile) });
  const env = serverEnvironment(args.home);
  for (const [name, definition] of Object.entries(AGENTS)) {
    const binary = executable(definition.cliBinary, env);
    checks.push({ name: `cli:${name}`, ok: Boolean(binary), detail: binary });
  }
  if (executable(AGENTS.grok.cliBinary, env)) {
    const model = cursorModelAvailability(env);
    checks.push({ name: "model:grok", ok: model.available, detail: model.reason || model.model });
  }
  for (const target of args.targets) {
    const value = mcpGet(target, { ...process.env, HOME: args.home });
    checks.push({ name: `mcp:${target}`, ok: value.present && value.output.includes(pathsFor(args.home).bridge), warning: value.present });
  }
  for (const [name, value] of Object.entries(report.agents)) checks.push({ name: `agent:${name}`, ok: value.online });
  return { ...report, command: "doctor", ok: checks.every((item) => item.ok || item.warning), checks };
}

async function uninstall(args) {
  const stopped = await stopServers(args);
  const launchd = removeLaunchAgent(args);
  const mcp = unregisterMcp(args);
  const paths = pathsFor(args.home);
  if (args.purge && !args.dryRun) {
    fs.rmSync(paths.stateRoot, { recursive: true, force: true });
    fs.rmSync(path.dirname(paths.tokenFile), { recursive: true, force: true });
  } else if (!args.dryRun) {
    fs.rmSync(paths.installState, { force: true });
  }
  return { ok: true, command: "uninstall", simulation: args.dryRun, stopped, launchd, mcp, purged: args.purge };
}

async function serve(args) {
  const started = await startServers(args, { foreground: true });
  const children = started.children || [];
  const shutdown = () => {
    for (const child of children) if (child.pid && processAlive(child.pid)) child.kill("SIGTERM");
    process.exit(0);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
  await new Promise((resolve) => {
    if (!children.length) return resolve();
    let remaining = children.length;
    for (const child of children) child.once("exit", () => { remaining -= 1; if (remaining === 0) resolve(); });
  });
  return { ok: true, command: "serve" };
}

function openPanel(args) {
  const url = `http://127.0.0.1:3142/${args.sandbox ? "sandbox" : "ui"}`;
  const tokenFile = pathsFor(args.home).tokenFile;
  if (!fs.existsSync(tokenFile)) throw new Error(`token da mesh não encontrado: ${tokenFile}`);
  const token = fs.readFileSync(tokenFile, "utf8").trim();
  if (!token) throw new Error(`token da mesh vazio: ${tokenFile}`);
  const bootstrapUrl = `${url}?token=${encodeURIComponent(token)}`;
  if (!args.dryRun) {
    const opener = process.platform === "darwin" ? "open" : "xdg-open";
    const result = command(opener, [bootstrapUrl]);
    if (result.status !== 0) throw new Error(`não foi possível abrir ${url}`);
  }
  return { ok: true, command: "open", simulation: args.dryRun, url };
}

function print(result, json) {
  if (json) return process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
  if (result.command === "status" || result.command === "doctor") {
    for (const [name, value] of Object.entries(result.agents)) console.log(`${name}=${value.online ? "online" : "offline"} port=${value.port}`);
    console.log(`painel=${result.panel}`);
    console.log(`sandbox=${result.sandbox}`);
    if (result.checks) for (const check of result.checks) console.log(`${check.name}=${check.ok ? "ok" : check.warning ? "aviso" : "falha"}`);
    return;
  }
  console.log(`${result.command}: ${result.simulation ? "simulação concluída" : "concluído"}`);
  if (result.panel) console.log(`painel=${result.panel}`);
  if (result.url) console.log(`url=${result.url}`);
}

export async function main(argv = process.argv.slice(2)) {
  let args;
  try {
    args = parseArgs(argv);
    if (["help", "--help", "-h"].includes(args.command)) {
      process.stdout.write(usage());
      return 0;
    }
    let result;
    if (args.command === "install") result = await install(args);
    else if (args.command === "start") result = { ok: true, command: "start", ...(await startServers(args)) };
    else if (args.command === "stop") result = { ok: true, command: "stop", ...(await stopServers(args)) };
    else if (args.command === "restart") {
      await stopServers(args);
      result = { ok: true, command: "restart", ...(await startServers(args)) };
    } else if (args.command === "status") result = await statusReport(args);
    else if (args.command === "doctor") result = await doctor(args);
    else if (args.command === "mcp") result = { ok: true, command: "mcp", simulation: args.dryRun, mcp: registerMcp(args) };
    else if (args.command === "open") result = openPanel(args);
    else if (args.command === "uninstall") result = await uninstall(args);
    else if (args.command === "serve") result = await serve(args);
    else throw new Error(`comando desconhecido: ${args.command}`);
    print(result, args.json);
    return result.ok ? 0 : 1;
  } catch (error) {
    const failure = { ok: false, error: error.message };
    if (args?.json) process.stderr.write(`${JSON.stringify(failure)}\n`);
    else process.stderr.write(`erro: ${error.message}\n`);
    return 1;
  }
}

if (
  process.argv[1]
  && fs.realpathSync(path.resolve(process.argv[1])) === fs.realpathSync(fileURLToPath(import.meta.url))
) {
  process.exitCode = await main();
}
