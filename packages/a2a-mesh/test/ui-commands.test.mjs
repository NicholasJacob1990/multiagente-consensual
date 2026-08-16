import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ui = fs.readFileSync(
  path.join(root, "runtime", "a2a-shared", "mesh-ui.html"),
  "utf8",
);

test("painel implementa todos os comandos anunciados no campo de entrada", () => {
  for (const command of [
    "call",
    "broadcast",
    "consensus",
    "ensemble",
    "debate",
    "plan",
    "team",
  ]) {
    assert.match(ui, new RegExp(`case '/${command}'`));
  }
});

test("team cria contribuição paralela e síntese pelo juiz", () => {
  assert.match(ui, /method: 'mesh\/team'/);
  assert.match(ui, /mode: 'parallel'/);
  assert.match(ui, /agents: \[judge\]/);
  assert.match(ui, /\{\{previous\}\}/);
});

test("painel submete operações longas de forma assíncrona e recupera o resultado", () => {
  assert.match(ui, /`\$\{parsed\.method\}Async`/);
  assert.match(ui, /AbortSignal\.timeout\(30000\)/);
  assert.match(ui, /loadCompletedTaskResult\(data\.taskId, type\)/);
  assert.match(ui, /\/mesh\/tasks\/\$\{encodeURIComponent\(taskId\)\}/);
  assert.match(ui, /meshLastEventId/);
  assert.match(ui, /partial-output\.md/);
  assert.match(ui, /function isDuplicateMeshEvent\(data\)/);
  assert.match(ui, /MAX_RENDERED_MESH_EVENT_KEYS = 10000/);
  assert.match(ui, /case 'mesh_gap'/);
});
