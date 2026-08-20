import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { RUNTIME_ROOT } from "../npm/cli.mjs";

async function waitFor(url, timeoutMs = 15000) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    try {
      const response = await fetch(url, { signal: AbortSignal.timeout(800) });
      if (response.ok) return response;
    } catch {
      // O processo ainda está iniciando.
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  throw new Error(`timeout esperando ${url}`);
}

function requestWithHost(port, host) {
  return new Promise((resolve, reject) => {
    const request = http.get({ hostname: "127.0.0.1", port, path: "/health", headers: { Host: host } }, (response) => {
      response.resume();
      response.once("end", () => resolve(response));
    });
    request.once("error", reject);
  });
}

test("servidor empacotado expõe health, painel e sandbox somente em loopback", { timeout: 30000 }, async () => {
  const temporaryHome = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-runtime-"));
  const port = 43142;
  const token = "runtime-test-token-123456";
  const tokenFile = path.join(temporaryHome, ".a2a", "auth-token");
  fs.mkdirSync(path.dirname(tokenFile), { recursive: true });
  fs.writeFileSync(tokenFile, `${token}\n`, { mode: 0o600 });
  const entry = path.join(RUNTIME_ROOT, "a2a-claude", "server.js");
  const child = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env: {
      ...process.env,
      HOME: temporaryHome,
      A2A_PORT: String(port),
      A2A_BIND_HOST: "127.0.0.1",
      A2A_ALLOW_NO_TOKEN: "false",
      A2A_AUTH_TOKEN_FILE: tokenFile,
      A2A_CODEX_PORT: "43141",
      A2A_CLAUDE_PORT: String(port),
      A2A_GEMINI_PORT: "43143",
      A2A_GROK_PORT: "43144",
      A2A_CLAUDE_DATA_DIR: path.join(temporaryHome, "tasks", "claude"),
      A2A_AUTO_START: "false",
      A2A_SUPERVISOR_PID: String(process.pid),
      A2A_SUPERVISOR_MODE: "foreground",
    },
    stdio: "ignore",
  });
  try {
    const health = await (await waitFor(`http://127.0.0.1:${port}/health`)).json();
    assert.equal(health.status, "ok");
    assert.deepEqual(health.supervision, {
      pid: child.pid,
      supervisorPid: process.pid,
      mode: "foreground",
    });
    const crossPortHealth = await fetch(`http://127.0.0.1:${port}/health`, {
      headers: { Origin: "http://127.0.0.1:43141" },
    });
    assert.equal(crossPortHealth.status, 200);
    assert.equal(crossPortHealth.headers.get("access-control-allow-origin"), "http://127.0.0.1:43141");
    const forbiddenOrigin = await fetch(`http://127.0.0.1:${port}/health`, {
      headers: { Origin: "http://127.0.0.1:49999" },
    });
    assert.equal(forbiddenOrigin.status, 403);
    const forbiddenHost = await requestWithHost(port, "evil.example");
    assert.equal(forbiddenHost.statusCode, 403);
    const unauthenticatedUi = await fetch(`http://127.0.0.1:${port}/ui`, { redirect: "manual" });
    assert.equal(unauthenticatedUi.status, 401);
    assert.equal(unauthenticatedUi.headers.get("set-cookie"), null);
    const unauthenticatedSandbox = await fetch(`http://127.0.0.1:${port}/sandbox`, { redirect: "manual" });
    assert.equal(unauthenticatedSandbox.status, 401);
    assert.equal(unauthenticatedSandbox.headers.get("set-cookie"), null);
    const unauthenticatedCrossPortConfig = await fetch(`http://127.0.0.1:${port}/mesh/config`, {
      headers: { Origin: "http://127.0.0.1:43141" },
    });
    assert.equal(unauthenticatedCrossPortConfig.status, 401);
    assert.equal(unauthenticatedCrossPortConfig.headers.get("access-control-allow-origin"), "http://127.0.0.1:43141");
    assert.equal(unauthenticatedCrossPortConfig.headers.get("access-control-allow-credentials"), "true");

    const invalidBootstrap = await fetch(`http://127.0.0.1:${port}/ui?token=wrong`, { redirect: "manual" });
    assert.equal(invalidBootstrap.status, 401);
    assert.equal(invalidBootstrap.headers.get("set-cookie"), null);

    const bootstrap = await fetch(`http://127.0.0.1:${port}/ui?token=${encodeURIComponent(token)}`, { redirect: "manual" });
    assert.equal(bootstrap.status, 303);
    assert.equal(bootstrap.headers.get("location"), "/ui");
    const cookie = bootstrap.headers.get("set-cookie");
    assert.match(cookie, /^A2A-Token=/);
    assert.match(cookie, /HttpOnly/i);

    const ui = await fetch(`http://127.0.0.1:${port}/ui`, { headers: { Cookie: cookie } });
    assert.equal(ui.status, 200);
    assert.equal(ui.headers.get("x-frame-options"), "DENY");
    assert.match(await ui.text(), /A2A Mesh/);
    const sandbox = await fetch(`http://127.0.0.1:${port}/sandbox`, { headers: { Cookie: cookie } });
    assert.equal(sandbox.status, 200);
    assert.match(await sandbox.text(), /Agent CLI Sandbox/);
  } finally {
    child.kill("SIGTERM");
    await new Promise((resolve) => child.once("exit", resolve));
    fs.rmSync(temporaryHome, { recursive: true, force: true });
  }
});

test("peer Grok alterna explicitamente entre Cursor e CLI oficial sem fallback", { timeout: 30000 }, async () => {
  const temporaryHome = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-grok-route-"));
  const bin = path.join(temporaryHome, "bin");
  fs.mkdirSync(bin, { recursive: true });
  const cursor = path.join(bin, "cursor-agent");
  const grok = path.join(bin, "grok");
  fs.writeFileSync(cursor, "#!/bin/sh\nprintf 'cursor-grok-4.6-high - Grok 4.6 High\\ncursor-grok-4.6-xhigh - Grok 4.6 Extra High\\n'\n", { mode: 0o700 });
  fs.writeFileSync(grok, "#!/bin/sh\nprintf 'You are not authenticated.\\nDefault model: grok-4.6\\nAvailable models:\\n  * grok-4.6 (default)\\n'\n", { mode: 0o700 });
  const port = 43244;
  const token = "runtime-grok-token-123456";
  const tokenFile = path.join(temporaryHome, ".a2a", "auth-token");
  fs.mkdirSync(path.dirname(tokenFile), { recursive: true });
  fs.writeFileSync(tokenFile, `${token}\n`, { mode: 0o600 });
  const entry = path.join(RUNTIME_ROOT, "a2a-grok", "server.js");
  const child = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env: {
      ...process.env,
      HOME: temporaryHome,
      PATH: `${bin}:${process.env.PATH || ""}`,
      A2A_PORT: String(port),
      A2A_BIND_HOST: "127.0.0.1",
      A2A_ALLOW_NO_TOKEN: "false",
      A2A_AUTH_TOKEN_FILE: tokenFile,
      A2A_GROK_CURSOR_BINARY: cursor,
      A2A_GROK_OFFICIAL_BINARY: grok,
      A2A_GROK_PORT: String(port),
      A2A_GROK_DATA_DIR: path.join(temporaryHome, "tasks", "grok"),
      A2A_AUTO_START: "false",
    },
    stdio: "ignore",
  });
  try {
    await waitFor(`http://127.0.0.1:${port}/health`);
    const bootstrap = await fetch(`http://127.0.0.1:${port}/ui?token=${encodeURIComponent(token)}`, { redirect: "manual" });
    const cookie = bootstrap.headers.get("set-cookie");
    const officialResponse = await fetch(`http://127.0.0.1:${port}/mesh/config`, {
      method: "POST",
      headers: { Cookie: cookie, "Content-Type": "application/json" },
      body: JSON.stringify({ route: "official" }),
    });
    assert.equal(officialResponse.status, 200);
    const official = await officialResponse.json();
    assert.equal(official.route, "official");
    assert.equal(official.configuredModel, "grok-4.6");
    assert.equal(official.authenticated, false);
    assert.match(official.warning, /grok login/);

    const officialHealth = await (await fetch(`http://127.0.0.1:${port}/health`)).json();
    assert.equal(officialHealth.route, "official");
    assert.equal(officialHealth.cliBinary, "grok");
    assert.equal(officialHealth.model, "grok-4.6");

    const cursorResponse = await fetch(`http://127.0.0.1:${port}/mesh/config`, {
      method: "POST",
      headers: { Cookie: cookie, "Content-Type": "application/json" },
      body: JSON.stringify({ route: "cursor" }),
    });
    assert.equal(cursorResponse.status, 200);
    assert.equal((await cursorResponse.json()).route, "cursor");

    const cursorModelResponse = await fetch(`http://127.0.0.1:${port}/mesh/config`, {
      method: "POST",
      headers: { Cookie: cookie, "Content-Type": "application/json" },
      body: JSON.stringify({ route: "cursor", model: "cursor-grok-4.6-xhigh" }),
    });
    assert.equal(cursorModelResponse.status, 200);
    const cursorModel = await cursorModelResponse.json();
    assert.equal(cursorModel.configuredModel, "cursor-grok-4.6-xhigh");
    assert.ok(cursorModel.availableModels.includes("cursor-grok-4.6-xhigh"));
    const selectedHealth = await (await fetch(`http://127.0.0.1:${port}/health`)).json();
    assert.equal(selectedHealth.model, "cursor-grok-4.6-xhigh");
    assert.equal(selectedHealth.reasoningEffort, "xhigh");

    const failedTaskResponse = await fetch(`http://127.0.0.1:${port}/tasks/send`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
      body: JSON.stringify({
        message: { role: "user", parts: [{ type: "text", text: "teste de falha" }] },
      }),
    });
    assert.equal(failedTaskResponse.status, 200);
    assert.equal((await failedTaskResponse.json()).result.status.state, "failed");
    const degradedHealth = await (await fetch(`http://127.0.0.1:${port}/health`)).json();
    assert.equal(degradedHealth.status, "degraded");
    assert.equal(degradedHealth.executionAvailable, false);
    assert.match(degradedHealth.lastExecutionError, /model_unconfirmed/);
  } finally {
    child.kill("SIGTERM");
    await new Promise((resolve) => child.once("exit", resolve));
    fs.rmSync(temporaryHome, { recursive: true, force: true });
  }
});
