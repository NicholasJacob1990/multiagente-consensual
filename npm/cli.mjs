#!/usr/bin/env node

import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

export const PACKAGE_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
export const MARKETPLACE_NAME = "multiagente-npm";
export const PLUGIN_NAME = "multiagente-consensual";
export const A2A_PACKAGE = "@nicholasjacob90/a2a-mesh@1.4.0";
export const ALL_TARGETS = Object.freeze([
  "codex",
  "claude",
  "cursor",
  "opencode",
  "kimi",
  "antigravity",
]);

const PAYLOAD_ROOTS = [
  ".claude-plugin",
  ".codex-plugin",
  "assets",
  "bin",
  "commands",
  "references",
  "scripts",
  "skills",
];
const PAYLOAD_FILES = ["README.md"];
const CORE_COMMANDS = [
  "consenso",
  "loop-debate-agentes",
  "redacao-juridica-consensual",
  "workflow-agentes",
];
const COMMAND_DIRS = {
  codex: [".codex", "prompts"],
  claude: [".claude", "commands"],
  cursor: [".cursor", "commands"],
  opencode: [".config", "opencode", "commands"],
  antigravity: [".gemini", "commands"],
};
const SKILL_DIRS = {
  claude: [".claude", "skills"],
  cursor: [".cursor", "skills"],
  opencode: [".config", "opencode", "skills"],
  kimi: [".agents", "skills"],
  antigravity: [".agents", "skills"],
};
const ROUTE_BINARIES = {
  codex: "codex",
  claude: "claude",
  cursor: "cursor-agent",
  opencode: "opencode",
  kimi: "kimi-secure",
  antigravity: "agy",
};

function usage() {
  return `Multiagente Consensual — instalador NPM/NPX

Uso:
  multiagente-consensual install --all
  multiagente-consensual install --all --with-a2a
  multiagente-consensual install <codex|claude|cursor|opencode|kimi|antigravity>
  multiagente-consensual update --all
  multiagente-consensual upgrade --all --with-a2a
  multiagente-consensual status [--all|alvo]
  multiagente-consensual doctor [--all|alvo]
  multiagente-consensual uninstall --all [--purge]

Opções:
  --all                 selecionar todas as seis CLIs
  --dry-run             mostrar ações sem alterar o sistema
  --json                emitir resultado estruturado
  --launchd             iniciar o bridge automaticamente no login do macOS
  --home <pasta>        usar outra HOME (útil para instalação isolada)
  --install-root <dir>  alterar a raiz estável do marketplace
  --skip-registries     não registrar plugins no Codex/Claude Code
  --skip-bridge         não instalar o wrapper multiagent-bridge
  --with-a2a            instalar servidores A2A, MCP e painel local
  --replace-a2a-mcp     substituir uma configuração a2a-mesh já existente
  --purge               remover também payload estável e estado no uninstall
`;
}

function nextValue(argv, index, flag) {
  if (index + 1 >= argv.length) throw new Error(`${flag} exige um valor`);
  return argv[index + 1];
}

export function parseArgs(argv) {
  const args = {
    command: argv[0] || "help",
    target: null,
    all: false,
    dryRun: false,
    json: false,
    launchd: false,
    home: os.homedir(),
    installRoot: null,
    skipRegistries: false,
    skipBridge: false,
    withA2a: false,
    replaceA2aMcp: false,
    purge: false,
  };
  for (let index = 1; index < argv.length; index += 1) {
    const value = argv[index];
    if (value === "--all") args.all = true;
    else if (value === "--dry-run") args.dryRun = true;
    else if (value === "--json") args.json = true;
    else if (value === "--launchd") args.launchd = true;
    else if (value === "--skip-registries") args.skipRegistries = true;
    else if (value === "--skip-bridge") args.skipBridge = true;
    else if (value === "--with-a2a") args.withA2a = true;
    else if (value === "--replace-a2a-mcp") args.replaceA2aMcp = true;
    else if (value === "--purge") args.purge = true;
    else if (value === "--home") {
      args.home = path.resolve(nextValue(argv, index, value));
      index += 1;
    } else if (value === "--install-root") {
      args.installRoot = path.resolve(nextValue(argv, index, value));
      index += 1;
    } else if (value.startsWith("-")) throw new Error(`opção desconhecida: ${value}`);
    else if (args.target === null) args.target = value;
    else throw new Error(`argumento inesperado: ${value}`);
  }
  if (args.installRoot === null) {
    args.installRoot = path.join(args.home, ".local", "share", PLUGIN_NAME, "marketplace");
  }
  return args;
}

export function resolveTargets(args) {
  if (args.all && args.target) throw new Error("--all não pode ser combinado com um alvo");
  if (args.all || !args.target) return [...ALL_TARGETS];
  if (!ALL_TARGETS.includes(args.target)) throw new Error(`alvo desconhecido: ${args.target}`);
  return [args.target];
}

function nowToken() {
  return `${new Date().toISOString().replace(/\D/g, "").slice(0, 17)}-${process.pid}`;
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function writeJsonAtomic(file, value, mode = 0o600) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  const temp = path.join(path.dirname(file), `.${path.basename(file)}.${process.pid}.tmp`);
  fs.writeFileSync(temp, `${JSON.stringify(value, null, 2)}\n`, { mode });
  fs.renameSync(temp, file);
}

function canonicalPath(value) {
  const resolved = path.resolve(value);
  return fs.existsSync(resolved) ? fs.realpathSync.native(resolved) : resolved;
}

function hashFile(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

function executableOnPath(binary, env = process.env) {
  const extensions = process.platform === "win32" ? [".exe", ".cmd", ".bat", ""] : [""];
  for (const directory of String(env.PATH || "").split(path.delimiter)) {
    if (!directory) continue;
    for (const extension of extensions) {
      const candidate = path.join(directory, `${binary}${extension}`);
      try {
        fs.accessSync(candidate, fs.constants.X_OK);
        return candidate;
      } catch {
        // Continue procurando.
      }
    }
  }
  return null;
}

function pythonBinary(env) {
  return executableOnPath("python3", env) || executableOnPath("python", env);
}

function environmentForHome(home) {
  const env = {
    ...process.env,
    HOME: home,
    PATH: [path.join(home, ".local", "bin"), process.env.PATH || ""].join(path.delimiter),
  };
  if (path.resolve(home) !== path.resolve(os.homedir())) {
    delete env.CODEX_HOME;
    delete env.CLAUDE_CONFIG_DIR;
    delete env.XDG_CONFIG_HOME;
    delete env.XDG_DATA_HOME;
    delete env.XDG_STATE_HOME;
  }
  return env;
}

function run(binary, argv, context, options = {}) {
  const action = { binary, argv, cwd: options.cwd || context.pluginRoot };
  context.actions.push(action);
  if (context.dryRun) return { status: 0, stdout: "", stderr: "", simulated: true };
  const completed = spawnSync(binary, argv, {
    cwd: action.cwd,
    env: context.env,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });
  if (completed.error) throw completed.error;
  const result = {
    status: completed.status ?? 1,
    stdout: completed.stdout || "",
    stderr: completed.stderr || "",
  };
  if (result.status !== 0 && !options.allowFailure) {
    throw new Error(
      `${binary} ${argv.join(" ")} falhou (${result.status}): ${(result.stderr || result.stdout).trim()}`,
    );
  }
  return result;
}

function copyEntry(source, destination) {
  if (!fs.existsSync(source)) return;
  fs.cpSync(source, destination, { recursive: true, force: true, preserveTimestamps: true });
}

function copyPayloadEntry(source, destination) {
  if (!fs.existsSync(source)) return;
  fs.cpSync(source, destination, {
    recursive: true,
    force: true,
    preserveTimestamps: true,
    filter: (candidate) => {
      const name = path.basename(candidate);
      return !["__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".DS_Store"].includes(name)
        && !name.endsWith(".pyc");
    },
  });
}

function commandNames(pluginRoot) {
  const names = fs
    .readdirSync(path.join(pluginRoot, "commands"), { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith(".md"))
    .map((entry) => entry.name.slice(0, -3));
  return [...new Set([...names, ...CORE_COMMANDS])].sort();
}

function skillNames(pluginRoot) {
  return fs
    .readdirSync(path.join(pluginRoot, "skills"), { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(pluginRoot, "skills", entry.name, "SKILL.md")))
    .map((entry) => entry.name)
    .sort();
}

function managedPaths(home, targets, pluginRoot, includeCommon = true) {
  const paths = [];
  const commands = commandNames(pluginRoot);
  const skills = skillNames(pluginRoot);
  for (const target of targets) {
    if (COMMAND_DIRS[target]) {
      const directory = path.join(home, ...COMMAND_DIRS[target]);
      for (const name of commands) paths.push(path.join(directory, `${name}.md`));
    }
    if (SKILL_DIRS[target]) {
      const directory = path.join(home, ...SKILL_DIRS[target]);
      for (const name of skills) paths.push(path.join(directory, name));
    }
  }
  if (includeCommon) {
    for (const name of skills) paths.push(path.join(home, ".codex", "skills", name));
    paths.push(path.join(home, ".agents", "multiagent-manifest.json"));
    paths.push(path.join(home, ".agents", "model-routing.yaml"));
    paths.push(path.join(home, ".codex", "assets", "multiagent-manifest.json"));
    paths.push(path.join(home, ".codex", "scripts", "provenance.py"));
  }
  return [...new Set(paths)];
}

function hashTree(root) {
  const digest = crypto.createHash("sha256");
  function visit(current, relative) {
    const info = fs.lstatSync(current);
    if (info.isSymbolicLink()) {
      digest.update(`L\0${relative}\0${fs.readlinkSync(current)}\0`);
      return;
    }
    if (info.isFile()) {
      digest.update(`F\0${relative}\0${hashFile(current)}\0`);
      return;
    }
    if (!info.isDirectory()) return;
    digest.update(`D\0${relative}\0`);
    for (const name of fs.readdirSync(current).sort()) {
      visit(path.join(current, name), path.join(relative, name));
    }
  }
  visit(root, ".");
  return digest.digest("hex");
}

function backupManaged(home, targets, pluginRoot, stateRoot, dryRun) {
  const existing = managedPaths(home, targets, pluginRoot).filter((item) => fs.existsSync(item));
  if (existing.length === 0 || dryRun) return { path: null, entries: existing.length };
  const root = path.join(stateRoot, nowToken());
  const entries = [];
  existing.forEach((source, index) => {
    const relative = path.join("files", String(index).padStart(4, "0"));
    const destination = path.join(root, relative);
    copyEntry(source, destination);
    entries.push({ source, backup: relative });
  });
  writeJsonAtomic(path.join(root, "manifest.json"), { createdAt: new Date().toISOString(), entries });
  return { path: root, entries: existing.length };
}

function installStablePayload(context) {
  const pluginDestination = path.join(context.installRoot, "plugins", PLUGIN_NAME);
  const staging = path.join(context.installRoot, "plugins", `.${PLUGIN_NAME}.${process.pid}.staging`);
  if (context.dryRun) return pluginDestination;
  fs.mkdirSync(path.dirname(staging), { recursive: true });
  fs.rmSync(staging, { recursive: true, force: true });
  fs.mkdirSync(staging, { recursive: true });
  for (const name of PAYLOAD_ROOTS) copyPayloadEntry(path.join(PACKAGE_ROOT, name), path.join(staging, name));
  for (const name of PAYLOAD_FILES) copyPayloadEntry(path.join(PACKAGE_ROOT, name), path.join(staging, name));
  if (fs.existsSync(pluginDestination)) {
    const backup = path.join(context.backupRoot, nowToken(), "plugin-source");
    fs.mkdirSync(path.dirname(backup), { recursive: true });
    fs.renameSync(pluginDestination, backup);
  }
  fs.renameSync(staging, pluginDestination);
  return pluginDestination;
}

export function marketplaceDocuments(pluginVersion) {
  return {
    claude: {
      name: MARKETPLACE_NAME,
      owner: { name: "Nicholas Jacob" },
      metadata: {
        description: "Distribuição NPM do Multiagente Consensual",
        version: pluginVersion,
      },
      plugins: [
        {
          name: PLUGIN_NAME,
          description: "Debate, consenso, loops, ensemble e workflows multiagente.",
          source: `./plugins/${PLUGIN_NAME}`,
          version: pluginVersion,
          author: { name: "Nicholas Jacob" },
          license: "UNLICENSED",
          keywords: ["multi-agent", "consensus", "debate"],
        },
      ],
    },
    codex: {
      name: MARKETPLACE_NAME,
      interface: { displayName: "Multiagente NPM" },
      plugins: [
        {
          name: PLUGIN_NAME,
          source: { source: "local", path: `./plugins/${PLUGIN_NAME}` },
          policy: { installation: "AVAILABLE", authentication: "ON_USE" },
          category: "Productivity",
        },
      ],
    },
  };
}

function createMarketplaces(context) {
  const pluginVersion = readJson(path.join(context.pluginRoot, ".codex-plugin", "plugin.json")).version;
  const documents = marketplaceDocuments(pluginVersion);
  if (!context.dryRun) {
    writeJsonAtomic(path.join(context.installRoot, ".claude-plugin", "marketplace.json"), documents.claude, 0o644);
    writeJsonAtomic(path.join(context.installRoot, ".agents", "plugins", "marketplace.json"), documents.codex, 0o644);
  }
  return pluginVersion;
}

function parseJsonOutput(result, label) {
  try {
    return JSON.parse(result.stdout);
  } catch (error) {
    throw new Error(`${label} devolveu JSON inválido: ${error.message}`);
  }
}

function registerCodex(context) {
  if (!executableOnPath("codex", context.env)) return { status: "missing" };
  const listed = run("codex", ["plugin", "marketplace", "list", "--json"], context);
  if (!context.dryRun) {
    const data = parseJsonOutput(listed, "codex plugin marketplace list");
    const current = (data.marketplaces || []).find((entry) => entry.name === MARKETPLACE_NAME);
    if (current && canonicalPath(current.root) !== canonicalPath(context.installRoot)) {
      throw new Error(`marketplace ${MARKETPLACE_NAME} já aponta para ${current.root}`);
    }
    if (!current) run("codex", ["plugin", "marketplace", "add", context.installRoot, "--json"], context);
  } else {
    run("codex", ["plugin", "marketplace", "add", context.installRoot, "--json"], context);
  }
  run("codex", ["plugin", "add", `${PLUGIN_NAME}@${MARKETPLACE_NAME}`, "--json"], context);
  return { status: "installed" };
}

function registerClaude(context) {
  if (!executableOnPath("claude", context.env)) return { status: "missing" };
  const listed = run("claude", ["plugin", "marketplace", "list", "--json"], context);
  if (!context.dryRun) {
    const data = parseJsonOutput(listed, "claude plugin marketplace list");
    const current = data.find((entry) => entry.name === MARKETPLACE_NAME);
    if (current && canonicalPath(current.path || current.installLocation) !== canonicalPath(context.installRoot)) {
      throw new Error(`marketplace ${MARKETPLACE_NAME} já aponta para ${current.path || current.installLocation}`);
    }
    if (!current) run("claude", ["plugin", "marketplace", "add", context.installRoot, "--scope", "user"], context);
  } else {
    run("claude", ["plugin", "marketplace", "add", context.installRoot, "--scope", "user"], context);
  }
  const installed = run("claude", ["plugin", "list", "--json"], context);
  let present = false;
  if (!context.dryRun) {
    const data = parseJsonOutput(installed, "claude plugin list");
    present = data.some((entry) => entry.id === `${PLUGIN_NAME}@${MARKETPLACE_NAME}`);
  }
  if (present) run("claude", ["plugin", "update", `${PLUGIN_NAME}@${MARKETPLACE_NAME}`], context);
  else run("claude", ["plugin", "install", `${PLUGIN_NAME}@${MARKETPLACE_NAME}`, "--scope", "user"], context);
  return { status: "installed" };
}

function synchronizeSurfaces(context, targets) {
  const python = pythonBinary(context.env);
  if (!python) throw new Error("Python 3 não foi encontrado no PATH");
  return run(
    python,
    [path.join(context.pluginRoot, "scripts", "sync_cli_surface.py"), "--targets", targets.join(",")],
    context,
  );
}

function installBridge(context, targets, launchd) {
  if (context.skipBridge) return { status: "skipped" };
  const python = pythonBinary(context.env);
  if (!python) throw new Error("Python 3 não foi encontrado no PATH");
  const args = [
    path.join(context.pluginRoot, "scripts", "install_host.py"),
    "--bin-dir",
    path.join(context.home, ".local", "bin"),
    "--bridge-dir",
    path.join(context.home, ".agents", "cowork-bridge"),
    "--config",
    path.join(context.home, ".agents", "cowork-bridge-config.json"),
    "--private-state",
    path.join(context.home, ".agents", "cowork-bridge-state"),
  ];
  if (launchd && process.platform === "darwin" && path.resolve(context.home) === path.resolve(os.homedir())) {
    args.push("--launchd");
  }
  const result = run(python, args, context);
  if (targets.includes("kimi") && process.platform === "darwin") {
    const wrapper = path.join(context.home, ".local", "bin", "kimi-secure");
    const kimiConfig = path.join(context.home, ".kimi", "config.toml");
    if (!context.dryRun && !fs.existsSync(wrapper) && fs.existsSync(kimiConfig)) {
      run(python, [path.join(context.pluginRoot, "scripts", "install_kimi_keychain.py"), "--no-shell-alias"], context);
    }
  }
  return { status: "installed", result };
}

function a2aInstallRoot(home) {
  return path.join(home, ".local", "share", PLUGIN_NAME, "a2a");
}

function a2aCliPath(home) {
  return path.join(
    a2aInstallRoot(home),
    "node_modules",
    "@nicholasjacob90",
    "a2a-mesh",
    "npm",
    "cli.mjs",
  );
}

function installA2a(context, args, targets) {
  if (!args.withA2a) return { status: "not-requested" };
  const npm = executableOnPath("npm", context.env);
  if (!npm) throw new Error("npm não foi encontrado para instalar o runtime A2A");
  const root = a2aInstallRoot(args.home);
  run(
    npm,
    ["install", "--prefix", root, "--no-audit", "--no-fund", "--save-exact", A2A_PACKAGE],
    context,
  );
  const cli = a2aCliPath(args.home);
  if (!context.dryRun && !fs.existsSync(cli)) throw new Error(`CLI A2A não foi instalada em ${cli}`);
  const mcpTargets = targets.filter((target) => ["codex", "claude", "cursor"].includes(target));
  const argv = [cli, "install", "--home", args.home, "--json"];
  if (mcpTargets.length) argv.push("--targets", mcpTargets.join(","));
  else argv.push("--targets", "");
  if (args.launchd) argv.push("--launchd");
  if (args.replaceA2aMcp) argv.push("--replace-mcp");
  const configured = run(process.execPath, argv, context);
  return {
    status: "installed",
    package: A2A_PACKAGE,
    root,
    cli,
    panel: "http://127.0.0.1:3142/ui",
    sandbox: "http://127.0.0.1:3142/sandbox",
    output: configured.stdout.trim(),
  };
}

function buildCoworkArtifact(context) {
  const python = pythonBinary(context.env);
  if (!python) throw new Error("Python 3 não foi encontrado no PATH");
  const output = path.join(context.installRoot, "cowork", `${PLUGIN_NAME}.plugin`);
  run(
    python,
    [path.join(context.pluginRoot, "scripts", "package_plugin.py"), "--output", output],
    context,
  );
  return output;
}

function snapshotManagedFiles(context, targets) {
  const hashes = {};
  const trees = {};
  if (context.dryRun) return { files: hashes, trees };
  for (const item of managedPaths(context.home, targets, context.pluginRoot)) {
    if (!fs.existsSync(item)) continue;
    const info = fs.lstatSync(item);
    if (info.isFile()) hashes[item] = hashFile(item);
    else if (info.isDirectory() || info.isSymbolicLink()) trees[item] = hashTree(item);
  }
  return { files: hashes, trees };
}

function installOrUpdate(args, targets) {
  const stateRoot = path.join(args.home, ".local", "state", PLUGIN_NAME);
  const backupRoot = path.join(args.home, ".local", "state", `${PLUGIN_NAME}-backups`);
  const context = {
    actions: [],
    dryRun: args.dryRun,
    env: environmentForHome(args.home),
    home: args.home,
    installRoot: args.installRoot,
    pluginRoot: PACKAGE_ROOT,
    skipBridge: args.skipBridge,
    stateRoot,
    backupRoot,
  };
  const backup = backupManaged(args.home, targets, PACKAGE_ROOT, backupRoot, args.dryRun);
  const stablePlugin = installStablePayload(context);
  context.pluginRoot = args.dryRun ? PACKAGE_ROOT : stablePlugin;
  const pluginVersion = createMarketplaces(context);
  synchronizeSurfaces(context, targets);
  const registrations = {};
  if (!args.skipRegistries && targets.includes("codex")) registrations.codex = registerCodex(context);
  if (!args.skipRegistries && targets.includes("claude")) registrations.claude = registerClaude(context);
  const bridge = installBridge(context, targets, args.launchd);
  const a2a = installA2a(context, args, targets);
  const coworkArtifact = buildCoworkArtifact(context);
  const managed = snapshotManagedFiles(context, targets);
  const state = {
    schema: "multiagente_npm_install_v1",
    npmVersion: readJson(path.join(PACKAGE_ROOT, "package.json")).version,
    pluginVersion,
    installedAt: new Date().toISOString(),
    home: args.home,
    installRoot: args.installRoot,
    targets,
    backup,
    registrations,
    bridge: bridge.status,
    a2a,
    coworkArtifact,
    managedFiles: managed.files,
    managedTrees: managed.trees,
  };
  if (!args.dryRun) writeJsonAtomic(path.join(stateRoot, "install-state.json"), state);
  return { ok: true, command: args.command, simulation: args.dryRun, ...state, actions: context.actions };
}

function status(args, targets) {
  const stateFile = path.join(args.home, ".local", "state", PLUGIN_NAME, "install-state.json");
  const state = fs.existsSync(stateFile) ? readJson(stateFile) : null;
  const routes = Object.fromEntries(
    targets.map((target) => {
      const expected = ROUTE_BINARIES[target];
      const env = environmentForHome(args.home);
      const resolved = executableOnPath(expected, env);
      const fallback = target === "kimi" ? executableOnPath("kimi", process.env) : null;
      return [target, { expected, resolved, fallback, available: Boolean(resolved) }];
    }),
  );
  return {
    ok: true,
    command: "status",
    installed: Boolean(state),
    state,
    routes,
    a2a: state?.a2a || { status: "not-installed" },
    coworkArtifact: path.join(args.installRoot, "cowork", `${PLUGIN_NAME}.plugin`),
  };
}

function doctor(args, targets) {
  const report = status(args, targets);
  const pluginRoot = path.join(args.installRoot, "plugins", PLUGIN_NAME);
  const actions = [];
  const context = {
    actions,
    dryRun: args.dryRun,
    env: environmentForHome(args.home),
    home: args.home,
    installRoot: args.installRoot,
    pluginRoot,
    stateRoot: path.join(args.home, ".local", "state", PLUGIN_NAME),
  };
  const checks = [];
  if (!fs.existsSync(pluginRoot)) checks.push({ name: "payload", ok: false, message: "payload estável ausente" });
  else {
    const python = pythonBinary(context.env);
    if (!python) checks.push({ name: "python", ok: false, message: "Python 3 ausente" });
    else {
      const lint = run(
        python,
        [path.join(pluginRoot, "scripts", "manifest_lint.py"), "--manifest", path.join(pluginRoot, "assets", "multiagent-manifest.json"), "validate"],
        context,
        { allowFailure: true },
      );
      checks.push({ name: "manifest", ok: lint.status === 0, output: (lint.stdout || lint.stderr).trim() });
    }
  }
  const installedA2aCli = a2aCliPath(args.home);
  if (args.withA2a || report.a2a?.status === "installed") {
    if (!fs.existsSync(installedA2aCli)) {
      checks.push({ name: "a2a-runtime", ok: false, message: "runtime A2A ausente" });
    } else {
      const a2aDoctor = run(
        process.execPath,
        [installedA2aCli, "doctor", "--home", args.home, "--json"],
        context,
        { allowFailure: true },
      );
      checks.push({
        name: "a2a-runtime",
        ok: a2aDoctor.status === 0,
        output: (a2aDoctor.stdout || a2aDoctor.stderr).trim(),
      });
    }
  }
  for (const [target, route] of Object.entries(report.routes)) {
    checks.push({
      name: `route:${target}`,
      ok: route.available,
      message: route.available ? route.resolved : `${route.expected} não encontrado`,
      severity: "warning",
    });
  }
  return { ...report, command: "doctor", ok: checks.every((item) => item.ok || item.severity === "warning"), checks, actions };
}

function removeMatchingFiles(state, targets, args, result) {
  if (!state) return;
  const includeCommon = targets.length === ALL_TARGETS.length;
  const permitted = new Set(managedPaths(args.home, targets, PACKAGE_ROOT, includeCommon));
  if (!(targets.includes("kimi") && targets.includes("antigravity"))) {
    for (const item of [...permitted]) {
      if (item.startsWith(path.join(args.home, ".agents", "skills") + path.sep)) permitted.delete(item);
    }
  }
  for (const [file, expectedHash] of Object.entries(state.managedFiles || {})) {
    if (!permitted.has(file) || !fs.existsSync(file) || !fs.statSync(file).isFile()) continue;
    if (hashFile(file) !== expectedHash) {
      result.preserved.push({ file, reason: "modificado após a instalação" });
      continue;
    }
    if (!args.dryRun) fs.rmSync(file);
    result.removed.push(file);
  }
  for (const [tree, expectedHash] of Object.entries(state.managedTrees || {})) {
    if (!permitted.has(tree) || !fs.existsSync(tree)) continue;
    if (hashTree(tree) !== expectedHash) {
      result.preserved.push({ file: tree, reason: "árvore modificada após a instalação" });
      continue;
    }
    if (!args.dryRun) fs.rmSync(tree, { recursive: true, force: true });
    result.removed.push(tree);
  }
}

function uninstall(args, targets) {
  const stateRoot = path.join(args.home, ".local", "state", PLUGIN_NAME);
  const stateFile = path.join(stateRoot, "install-state.json");
  const state = fs.existsSync(stateFile) ? readJson(stateFile) : null;
  const context = {
    actions: [],
    dryRun: args.dryRun,
    env: environmentForHome(args.home),
    home: args.home,
    installRoot: args.installRoot,
    pluginRoot: PACKAGE_ROOT,
    stateRoot,
  };
  const result = { ok: true, command: "uninstall", simulation: args.dryRun, targets, removed: [], preserved: [], actions: context.actions };
  const installedA2aCli = a2aCliPath(args.home);
  if (targets.length === ALL_TARGETS.length && (state?.a2a?.status === "installed" || fs.existsSync(installedA2aCli))) {
    const a2aArgs = [installedA2aCli, "uninstall", "--home", args.home, "--json"];
    if (args.purge) a2aArgs.push("--purge");
    if (args.dryRun) a2aArgs.push("--dry-run");
    run(process.execPath, a2aArgs, context, { allowFailure: true });
    if (args.purge && !args.dryRun) fs.rmSync(a2aInstallRoot(args.home), { recursive: true, force: true });
    result.removed.push("a2a-mesh");
  }
  if (targets.includes("codex") && executableOnPath("codex", context.env)) {
    run("codex", ["plugin", "remove", `${PLUGIN_NAME}@${MARKETPLACE_NAME}`], context, { allowFailure: true });
  }
  if (targets.includes("claude") && executableOnPath("claude", context.env)) {
    run("claude", ["plugin", "uninstall", `${PLUGIN_NAME}@${MARKETPLACE_NAME}`], context, { allowFailure: true });
  }
  removeMatchingFiles(state, targets, args, result);
  if (args.purge) {
    if (executableOnPath("codex", context.env)) {
      run("codex", ["plugin", "marketplace", "remove", MARKETPLACE_NAME], context, { allowFailure: true });
    }
    if (executableOnPath("claude", context.env)) {
      run("claude", ["plugin", "marketplace", "remove", MARKETPLACE_NAME], context, { allowFailure: true });
    }
    if (!args.dryRun) {
      fs.rmSync(args.installRoot, { recursive: true, force: true });
      fs.rmSync(stateRoot, { recursive: true, force: true });
    }
    result.removed.push(args.installRoot, stateRoot);
  }
  return result;
}

function printResult(result, json) {
  if (json) {
    process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
    return;
  }
  if (result.command === "status" || result.command === "doctor") {
    console.log(`instalado=${result.installed}`);
    for (const [target, route] of Object.entries(result.routes)) {
      console.log(`${target}=${route.available ? route.resolved : "indisponível"}`);
    }
    if (result.checks) for (const check of result.checks) console.log(`${check.name}=${check.ok ? "ok" : check.message}`);
    return;
  }
  console.log(`${result.command}: ${result.simulation ? "simulação concluída" : "concluído"}`);
  if (result.pluginVersion) console.log(`plugin=${result.pluginVersion}`);
  if (result.targets) console.log(`targets=${result.targets.join(",")}`);
  if (result.coworkArtifact) console.log(`cowork=${result.coworkArtifact}`);
  if (result.a2a?.status === "installed") console.log(`a2a=${result.a2a.panel}`);
  if (result.backup?.path) console.log(`backup=${result.backup.path}`);
  if (result.preserved?.length) console.log(`preservados=${result.preserved.length}`);
}

export function main(argv = process.argv.slice(2)) {
  let args;
  try {
    args = parseArgs(argv);
    if (["help", "--help", "-h"].includes(args.command)) {
      process.stdout.write(usage());
      return 0;
    }
    if (!["install", "update", "upgrade", "status", "doctor", "uninstall"].includes(args.command)) {
      throw new Error(`comando desconhecido: ${args.command}`);
    }
    const targets = resolveTargets(args);
    if (args.purge && targets.length !== ALL_TARGETS.length) {
      throw new Error("--purge exige uninstall --all para não quebrar superfícies compartilhadas");
    }
    let result;
    if (["install", "update", "upgrade"].includes(args.command)) result = installOrUpdate(args, targets);
    else if (args.command === "status") result = status(args, targets);
    else if (args.command === "doctor") result = doctor(args, targets);
    else result = uninstall(args, targets);
    printResult(result, args.json);
    return result.ok ? 0 : 1;
  } catch (error) {
    const result = { ok: false, error: error.message };
    if (args?.json) process.stderr.write(`${JSON.stringify(result, null, 2)}\n`);
    else process.stderr.write(`erro: ${error.message}\n`);
    return 1;
  }
}

if (
  process.argv[1]
  && fs.realpathSync(path.resolve(process.argv[1])) === fs.realpathSync(fileURLToPath(import.meta.url))
) {
  process.exitCode = main();
}
