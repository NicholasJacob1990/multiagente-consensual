import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

// Exercise the actual packaged bridge against the installed SDK, without
// contacting peers, starting agent CLIs, or reading the user's token.
test("SDK negocia stdio, lista ferramentas e preserva respostas de erro", { timeout: 15000 }, async () => {
  const temporaryHome = fs.mkdtempSync(path.join(os.tmpdir(), "a2a-mcp-sdk-"));
  const bridge = fileURLToPath(new URL("../runtime/a2a-shared/mesh-bridge-mcp.js", import.meta.url));
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [bridge],
    stderr: "pipe",
    env: {
      PATH: process.env.PATH || "",
      HOME: temporaryHome,
      A2A_AUTH_TOKEN_FILE: path.join(temporaryHome, "absent-token"),
      A2A_PEERS_FILE: path.join(temporaryHome, "absent-peers.json"),
      A2A_MESH_BRIDGE_REMAINING_DEPTH: "0",
      A2A_AUTO_START: "false",
    },
  });
  const client = new Client({ name: "sdk-compatibility-test", version: "1.0.0" });
  try {
    await client.connect(transport);
    assert.equal(client.getServerVersion().name, "a2a-mesh");
    const { tools } = await client.listTools();
    for (const name of ["a2a_call", "a2a_status", "a2a_task_wait"]) {
      assert.ok(tools.some(tool => tool.name === name && tool.inputSchema.type === "object"));
    }
    const result = await client.callTool({ name: "a2a_call", arguments: { agent: "codex", prompt: "test only" } });
    assert.equal(result.isError, true);
    assert.match(result.content[0].text, /max mesh depth exceeded/);
  } finally {
    await client.close();
    await transport.close();
    fs.rmSync(temporaryHome, { recursive: true, force: true });
  }
});
