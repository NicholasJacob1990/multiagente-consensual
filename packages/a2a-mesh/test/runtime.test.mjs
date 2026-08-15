import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import fs from "node:fs";
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

test("servidor empacotado expõe health, painel e sandbox somente em loopback", { timeout: 30000 }, async () => {
  const temporaryHome = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mesh-runtime-"));
  const port = 43142;
  const entry = path.join(RUNTIME_ROOT, "a2a-claude", "server.js");
  const child = spawn(process.execPath, [entry], {
    cwd: path.dirname(entry),
    env: {
      ...process.env,
      HOME: temporaryHome,
      A2A_PORT: String(port),
      A2A_BIND_HOST: "127.0.0.1",
      A2A_ALLOW_NO_TOKEN: "true",
      A2A_AUTH_TOKEN_FILE: path.join(temporaryHome, ".a2a", "auth-token"),
      A2A_CODEX_PORT: "43141",
      A2A_CLAUDE_PORT: String(port),
      A2A_GEMINI_PORT: "43143",
      A2A_CLAUDE_DATA_DIR: path.join(temporaryHome, "tasks", "claude"),
      A2A_AUTO_START: "false",
    },
    stdio: "ignore",
  });
  try {
    const health = await (await waitFor(`http://127.0.0.1:${port}/health`)).json();
    assert.equal(health.status, "ok");
    assert.match(await (await waitFor(`http://127.0.0.1:${port}/ui`)).text(), /A2A Mesh/);
    assert.match(await (await waitFor(`http://127.0.0.1:${port}/sandbox`)).text(), /Agent CLI Sandbox/);
  } finally {
    child.kill("SIGTERM");
    await new Promise((resolve) => child.once("exit", resolve));
    fs.rmSync(temporaryHome, { recursive: true, force: true });
  }
});
