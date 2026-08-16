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

test("painel aberto como arquivo local redireciona para o servidor Mesh", () => {
  assert.match(ui, /window\.location\.protocol === 'file:'/);
  assert.match(ui, /window\.location\.replace\('http:\/\/127\.0\.0\.1:3142\/ui'\)/);
});

test("modo showcase preserva o histórico e permite tema isolado para documentação", () => {
  assert.match(ui, /const SHOWCASE_MODE = new URLSearchParams\(window\.location\.search\)\.get\('showcase'\) === '1'/);
  assert.match(ui, /if \(!SHOWCASE_MODE\) \{/);
  assert.match(ui, /requestedTheme === 'light' \|\| requestedTheme === 'dark'/);
});

test("painel implementa todos os comandos anunciados no campo de entrada", () => {
  for (const command of [
    "call",
    "broadcast",
    "consensus",
    "ensemble",
    "debate",
    "plan",
    "team",
    "status",
  ]) {
    assert.match(ui, new RegExp(`case '/${command}'`));
  }
});

test("controles visuais usam listeners compatíveis com CSP", () => {
  assert.doesNotMatch(ui, /onclick=/);
  assert.doesNotMatch(ui, /cdn\.tailwindcss\.com/);
  for (const id of ["layout-toggle", "scroll-btn", "terminal-send", "autocomplete-box", "clear-chat-btn", "undo-clear"])
    assert.match(ui, new RegExp(`getElementById\\('${id}'\\)\\?\\.addEventListener`));
  assert.match(ui, /wireStaticControls\(\);/);
  assert.match(ui, /select\[data-config-key\]/);
  assert.match(ui, /id="clear-chat-btn" type="button"/);
  assert.match(ui, /function undoClear\(\)/);
  assert.match(ui, /clearRequested/);
  assert.match(ui, /\.app-header \{/);
  assert.match(ui, /z-index: 20/);
});

test("painel oferece perfis com override explícito por rodada", () => {
  assert.match(ui, /fast: Object\.freeze\(\{ ensemble: 1, debate: 2, plan: 1 \}\)/);
  assert.match(ui, /normal: Object\.freeze\(\{ ensemble: 2, debate: 4, plan: 3 \}\)/);
  assert.match(ui, /deep: Object\.freeze\(\{ ensemble: 5, debate: 8, plan: 6 \}\)/);
  assert.match(ui, /--profile=\(fast\|normal\|deep\)/);
  assert.match(ui, /--no-dedupe/);
  assert.match(ui, /--no-early-exit/);
  assert.match(ui, /roundsMatch/);
});

test("broadcast da UI é folha por padrão e recursivo apenas por flag", () => {
  assert.match(ui, /params: \{ prompt, agents: agentOption\.agents, includeSelf: true, recursive \}/);
  assert.match(ui, /--recursive/);
  assert.match(ui, /recursive: false/);
  assert.match(ui, /broadcast direto/);
});

test("painel aceita aliases portáveis e não transforma comando desconhecido em broadcast", () => {
  for (const alias of [
    "a2a-call", "a2a-broadcast", "a2a-consensus", "a2a-ensemble",
    "a2a-debate", "a2a-team", "a2a-status",
  ]) {
    assert.match(ui, new RegExp(`'/${alias}'`));
  }
  assert.match(ui, /Comando desconhecido:/);
  assert.doesNotMatch(ui, /Unknown command — treat as broadcast/);
});

test("painel mostra modelos efetivos e substitui streaming duplicado no resultado final", () => {
  for (const agent of ["claude", "codex", "gemini", "grok", "glm", "deepseek", "kimi", "qwen"]) {
    assert.match(ui, new RegExp(`id="label-${agent}"`));
  }
  assert.match(ui, /function effectiveHealthModel\(health\)/);
  assert.match(ui, /lastObservedModel \|\| health\?\.configuredModel/);
  assert.match(ui, /function removeLiveTaskOutput\(taskId\)/);
  assert.match(ui, /function removeTransientTaskOutput\(taskId\)/);
  assert.match(ui, /function removeLiveSynthesisOutput\(taskId\)/);
  assert.match(ui, /node\.dataset\.operation === 'stream'/);
  assert.match(ui, /\['synthesis', 'judge'\]\.includes\(node\.dataset\.role/);
  assert.match(ui, /\['broadcast', 'call', 'team', 'ensemble', 'plan'\]\.includes\(op\)/);
  assert.match(ui, /if \(parsed\.finalPlan\)/);
  assert.match(ui, /\*\*Autor\/Revisor:\*\*/);
  assert.match(ui, /raw\.startsWith\('# Team:'\)/);
  assert.match(ui, /finalStep\?\.\[1\]\?\.trim\(\)/);
  assert.match(ui, /task\.parentTaskId \|\| task\.parent_task_id \|\| task\.metadata\?\.parentTaskId/);
  assert.match(ui, /t\.parentTaskId \|\| t\.parent_task_id \|\| t\.metadata\?\.parentTaskId/);
  assert.match(ui, /const rootTasks = Array\.isArray\(tasks\)/);
  assert.match(ui, /mesh-live-output/);
  assert.match(ui, /Ver detalhes da auditoria/);
  assert.match(ui, /Baixar auditoria/);
  assert.match(ui, /outputTransformed:/);
  assert.match(ui, /storedOutput:/);
  assert.match(ui, /CHAT_MAX_RENDERED_NODES = 350/);
  assert.match(ui, /restoreOlderChatNodes/);
  assert.match(ui, /verificação pendente da primeira execução/);
  assert.match(ui, /data\.totalEvents \?\? eventCount/);
  assert.match(ui, /falha\(s\) histórica\(s\)/);
});

test("painel permite selecionar a equipe e aplicar override por comando", () => {
  assert.match(ui, /id="team-picker"/);
  assert.match(ui, /data-team-agent="qwen"/);
  assert.match(ui, /function setTeamSelection\(agents\)/);
  assert.match(ui, /function parseAgentsOption\(text/);
  assert.match(ui, /--agents=claude,codex,qwen/);
  assert.match(ui, /agents: agentOption\.agents/);
  assert.match(ui, /agents:   savedTeamAgents/);
});

test("team cria contribuição paralela e síntese pelo juiz", () => {
  assert.match(ui, /method: 'mesh\/team'/);
  assert.match(ui, /mode: 'parallel'/);
  assert.match(ui, /agents: \[judge\]/);
  assert.match(ui, /\{\{previous\}\}/);
  assert.match(ui, /Obedeça estritamente qualquer formato, extensão ou número máximo/);
  assert.match(ui, /Objetivo original:/);
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

test("plan aplica e verifica limite explícito de palavras", () => {
  const plan = fs.readFileSync(new URL('../runtime/a2a-shared/mesh-plan.js', import.meta.url), 'utf8');
  assert.match(plan, /explicitWordLimit/);
  assert.match(plan, /enforcePlanWordLimit/);
  assert.match(plan, /exceeded the requested/);
});

test("ensemble aceita revisão que preserva código já correto", () => {
  const ensemble = fs.readFileSync(new URL('../runtime/a2a-shared/mesh-code-ensemble.js', import.meta.url), 'utf8');
  assert.match(ensemble, /classifySubmission\(revisedStr, writePrompt\)/);
  assert.doesNotMatch(ensemble, /classifySubmission\(revisedStr, revisePrompt\)/);
});
