import assert from "node:assert/strict";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  AGENTS,
  PACKAGE_ROOT,
  agentCliAvailability,
  cursorModelAvailability,
  openCodeModelAvailability,
  parseArgs,
  pathsFor,
} from "../npm/cli.mjs";

test("usa somente portas locais fixas e distintas", () => {
  assert.deepEqual(Object.values(AGENTS).map((agent) => agent.port), [3141, 3142, 3143, 3144, 3145, 3146, 3147, 3148]);
  assert.equal(new Set(Object.values(AGENTS).map((agent) => agent.port)).size, 8);
  assert.equal(AGENTS.grok.route, "cursor");
  assert.equal(AGENTS.grok.model, "cursor-grok-4.6-high");
  assert.equal(AGENTS.glm.model, "opencode-go/glm-5.3");
  assert.equal(AGENTS.deepseek.model, "opencode-go/deepseek-v4-pro");
  assert.equal(AGENTS.kimi.model, "kimi-code/k3");
  assert.equal(AGENTS.qwen.model, "opencode-go/qwen3.8-max");
});

test("reconhece GLM 5.3, DeepSeek V4 Pro e Qwen 3.8 Max no catálogo OpenCode Go", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-opencode-model-"));
  const opencode = path.join(root, "opencode");
  fs.writeFileSync(opencode, "#!/bin/sh\nprintf 'opencode-go/glm-5.3\\nopencode-go/deepseek-v4-pro\\nopencode-go/qwen3.8-max\\n'\n", { mode: 0o700 });
  try {
    assert.equal(openCodeModelAvailability("glm", { PATH: root }).available, true);
    assert.equal(openCodeModelAvailability("deepseek", { PATH: root }).available, true);
    assert.equal(openCodeModelAvailability("qwen", { PATH: root }).available, true);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("analisa instalação completa e opções MCP", () => {
  const args = parseArgs(["install", "--launchd", "--replace-mcp", "--targets", "codex,claude"]);
  assert.equal(args.command, "install");
  assert.equal(args.launchd, true);
  assert.equal(args.replaceMcp, true);
  assert.deepEqual(args.targets, ["codex", "claude"]);
});

test("registra Cursor como alvo MCP padrão", () => {
  assert.deepEqual(parseArgs(["install"]).targets, ["codex", "claude", "cursor"]);
});

test("rejeita alvo MCP não implementado", () => {
  assert.throws(() => parseArgs(["mcp", "--targets", "inexistente"]), /não suportados/);
});

test("mantém estado e dados fora do pacote", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-test-"));
  const paths = pathsFor(root);
  assert.match(paths.tokenFile, /\.a2a\/auth-token$/);
  assert.match(paths.dataRoot, /\.local\/state\/a2a-mesh\/tasks$/);
  fs.rmSync(root, { recursive: true, force: true });
});

test("ausência do Cursor degrada apenas o peer Grok", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-cli-availability-"));
  for (const binary of ["codex", "claude", "gemini", "opencode", "kimi"]) {
    const file = path.join(root, binary);
    fs.writeFileSync(file, "#!/bin/sh\nexit 0\n", { mode: 0o700 });
  }
  try {
    const availability = agentCliAvailability({ PATH: root });
    assert.equal(availability.codex.available, true);
    assert.equal(availability.claude.available, true);
    assert.equal(availability.gemini.available, true);
    assert.equal(availability.grok.available, false);
    assert.equal(availability.glm.available, true);
    assert.equal(availability.deepseek.available, true);
    assert.equal(availability.kimi.available, true);
    assert.equal(availability.qwen.available, true);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("Cursor sem o modelo exigido deixa somente o Grok indisponível", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-cursor-model-"));
  const cursor = path.join(root, "cursor-agent");
  fs.writeFileSync(cursor, "#!/bin/sh\nprintf 'cursor-outro-modelo - Outro modelo\\n'\n", { mode: 0o700 });
  try {
    const availability = cursorModelAvailability({ PATH: root });
    assert.equal(availability.available, false);
    assert.match(availability.reason, /modelo indisponível/);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("reconhece o Grok 4.6 High pela lista do Cursor", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-cursor-model-"));
  const cursor = path.join(root, "cursor-agent");
  fs.writeFileSync(cursor, "#!/bin/sh\nprintf 'cursor-grok-4.6-high - Grok 4.6 High\\n'\n", { mode: 0o700 });
  try {
    assert.equal(cursorModelAvailability({ PATH: root }).available, true);
  } finally {
    fs.rmSync(root, { recursive: true, force: true });
  }
});

test("entrypoint funciona por caminho simbólico ou alias de filesystem", () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-entry-"));
  const link = path.join(root, "a2a-mesh.mjs");
  fs.symlinkSync(path.join(PACKAGE_ROOT, "npm", "cli.mjs"), link);
  const result = spawnSync(process.execPath, [link, "--help"], { encoding: "utf8" });
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /A2A Mesh/);
  fs.rmSync(root, { recursive: true, force: true });
});
