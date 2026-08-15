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
