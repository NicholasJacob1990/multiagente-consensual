import assert from 'node:assert/strict';
import fs from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { chromium } from 'playwright';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const uiHtml = fs.readFileSync(path.join(root, 'runtime', 'a2a-shared', 'mesh-ui.html'), 'utf8');

function chromeExecutable() {
  const candidates = [
    chromium.executablePath(),
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome',
    '/usr/bin/chromium',
    '/usr/bin/chromium-browser',
  ];
  return candidates.find(candidate => candidate && fs.existsSync(candidate)) || null;
}

function sendJson(response, value) {
  response.writeHead(200, { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' });
  response.end(JSON.stringify(value));
}

function fixtureTask(id, operation) {
  if (operation === 'team') {
    return {
      id,
      metadata: { type: 'mesh/team' },
      createdAt: '2026-08-16T00:00:00.000Z',
      updatedAt: '2026-08-16T00:00:03.200Z',
      firstTokenAt: '2026-08-16T00:00:00.420Z',
      usage: { total: 880, input: 700, output: 180 },
      cost: 0.014,
      status: {
        state: 'completed',
        message: {
          role: 'agent',
          parts: [{
            type: 'text',
            text: '# Team: fixture\n\n## Step 1 (parallel)\n\n### codex\nCONTRIBUIÇÃO-INDIVIDUAL\n\n---\n\n## Step 2 (sequential)\n\n### claude\n- SÍNTESE-FINAL\n\n---\n',
          }],
        },
      },
      artifacts: [],
    };
  }
  return {
    id,
    metadata: { type: 'mesh/ensemble' },
    createdAt: '2026-08-16T00:00:00.000Z',
    updatedAt: '2026-08-16T00:00:05.400Z',
    firstTokenAt: '2026-08-16T00:00:00.350Z',
    usage: { total: 1234, input: 1000, output: 234 },
    cost: 0.042,
    status: {
      state: 'completed',
      message: {
        role: 'agent',
        parts: [{
          type: 'text',
          text: JSON.stringify({
            finalCode: '```javascript\nfunction approved() { return true; }\n```',
            profile: 'fast',
            phases: [
              { phase: 'write', durationMs: 900 },
              { phase: 'cross-review-1', durationMs: 1200 },
              { phase: 'revise-1', durationMs: 800 },
              { phase: 'synthesize', durationMs: 600 },
            ],
            timing: { totalMs: 5400 },
            optimization: { deduplicate: true, earlyExit: true, originalCandidates: 4, uniqueCandidates: 1 },
          }),
        }],
      },
    },
    artifacts: [{
      name: 'approved.js',
      description: 'Código consolidado pelo ensemble',
      parts: [{ type: 'text', text: 'function approved() { return true; }\n' }],
    }],
  };
}

test('painel executa comandos, detalhes, clear e virtualização em navegador real', { timeout: 60_000 }, async (t) => {
  const executablePath = chromeExecutable();
  if (!executablePath) return t.skip('Chrome/Chromium não disponível para E2E');

  const requests = [];
  const canceledRequests = [];
  const tasks = new Map();
  const sseResponses = new Set();
  const server = http.createServer(async (request, response) => {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname === '/ui') {
      response.writeHead(200, { 'Content-Type': 'text/html; charset=utf-8', 'Cache-Control': 'no-store' });
      response.end(uiHtml);
      return;
    }
    if (url.pathname === '/rpc' && request.method === 'POST') {
      let body = '';
      for await (const chunk of request) body += chunk;
      const payload = JSON.parse(body);
      requests.push(payload);
      const operation = payload.method.includes('team') ? 'team' : 'ensemble';
      const id = `e2e-${operation}-${requests.length}`;
      tasks.set(id, fixtureTask(id, operation));
      sendJson(response, { jsonrpc: '2.0', id: payload.id, result: { id, status: { state: 'completed' } } });
      return;
    }
    const cancelMatch = url.pathname.match(/^\/tasks\/(.+)\/cancel$/);
    if (cancelMatch && request.method === 'POST') {
      canceledRequests.push(decodeURIComponent(cancelMatch[1]));
      sendJson(response, { id: cancelMatch[1], status: { state: 'canceled' } });
      return;
    }
    const taskMatch = url.pathname.match(/^\/tasks\/(.+)$/);
    if (taskMatch) {
      sendJson(response, tasks.get(decodeURIComponent(taskMatch[1])) || { status: { state: 'failed' } });
      return;
    }
    if (url.pathname === '/mesh/tasks') {
      sendJson(response, [
        { id: 'active-run', state: 'working', method: 'mesh/debate', originServer: 'grok', inputText: 'Debate em andamento' },
        { id: 'recent-ok', state: 'completed', method: 'mesh/call', originServer: 'codex', inputText: 'Produza um arquivo de exemplo', artifacts: [{ name: 'recente.md', description: 'Artefato recente', parts: [{ type: 'text', text: '# Recente' }, { type: 'file', file: { uri: 'a2a-artifact://recent-ok/hash/recente.md', mimeType: 'text/markdown;charset=utf-8' } }], metadata: { kind: 'local-file', size: 10, mimeType: 'text/markdown;charset=utf-8', sha256: 'abcdef0123456789' } }] },
        { id: 'historic-fail', state: 'failed', method: 'mesh/plan' },
      ]);
      return;
    }
    if (url.pathname === '/mesh/artifacts/recent-ok/0') {
      const content = Buffer.from('# Recente\n');
      response.writeHead(200, {
        'Content-Type': 'text/markdown;charset=utf-8',
        'Content-Length': content.length,
        'Content-Disposition': 'attachment; filename="recente.md"',
      });
      response.end(content);
      return;
    }
    if (url.pathname === '/mesh/stats') {
      sendJson(response, { totalTasks: 2, connectedPeers: 4, uptime: 120 });
      return;
    }
    if (url.pathname === '/mesh/timeline') {
      sendJson(response, []);
      return;
    }
    if (url.pathname === '/mesh/events') {
      response.writeHead(200, {
        'Content-Type': 'text/event-stream',
        'Cache-Control': 'no-cache',
        Connection: 'keep-alive',
      });
      response.write(': connected\n\n');
      sseResponses.add(response);
      request.on('close', () => sseResponses.delete(response));
      return;
    }
    response.writeHead(404);
    response.end();
  });

  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const address = server.address();
  const origin = `http://127.0.0.1:${address.port}`;
  const browser = await chromium.launch({ headless: true, executablePath });
  t.after(async () => {
    for (const response of sseResponses) response.end();
    await browser.close();
    await new Promise(resolve => server.close(resolve));
  });

  const page = await browser.newPage();
  let grokRoute = 'cursor';
  const models = {
    claude: 'claude-opus-5', codex: 'gpt-5.6-sol', gemini: 'gemini-3.7-flash-high', grok: 'cursor-grok-4.6-high',
    glm: 'opencode-go/glm-5.3', deepseek: 'opencode-go/deepseek-v4-pro', kimi: 'kimi-code/k3', qwen: 'opencode-go/qwen3.8-max',
  };
  const availableModels = {
    gemini: ['gemini-3.7-flash-high', 'gemini-3.1-pro-high'],
    grok: ['cursor-grok-4.6-high', 'cursor-grok-4.6-xhigh'],
    glm: ['opencode-go/glm-5.3', 'opencode-go/kimi-k3'],
    deepseek: ['opencode-go/deepseek-v4-pro', 'opencode-go/glm-5.3'],
    qwen: ['opencode-go/qwen3.8-max', 'opencode-go/deepseek-v4-pro'],
  };
  const externalRequests = [];
  page.on('request', (request) => {
    const url = request.url();
    if (!url.startsWith(origin) && !/127\.0\.0\.1:314[1-8]\/(health|mesh\/config)/.test(url)) externalRequests.push(url);
  });
  await page.route(/http:\/\/127\.0\.0\.1:314[1-8]\/mesh\/config/, async (route) => {
    const requestUrl = new URL(route.request().url());
    const agent = { 3141: 'codex', 3142: 'claude', 3143: 'gemini', 3144: 'grok', 3145: 'glm', 3146: 'deepseek', 3147: 'kimi', 3148: 'qwen' }[requestUrl.port];
    const payload = JSON.parse(route.request().postData() || '{}');
    if (agent === 'grok') grokRoute = payload.route || grokRoute;
    if (payload.model) models[agent] = payload.model;
    const configurableModels = ['gemini', 'glm', 'deepseek', 'qwen'].includes(agent) || (agent === 'grok' && grokRoute === 'cursor');
    const configuredModel = agent === 'grok' && grokRoute === 'official' ? 'grok-4.6' : models[agent];
    await route.fulfill({
      status: 200,
      headers: { 'Access-Control-Allow-Origin': origin, 'Access-Control-Allow-Credentials': 'true' },
      contentType: 'application/json',
      body: JSON.stringify({
        ok: true,
        agent,
        route: agent === 'grok' ? grokRoute : (agent === 'gemini' ? 'antigravity' : ['glm', 'deepseek', 'qwen'].includes(agent) ? 'opencode' : agent),
        cliBinary: agent === 'grok' ? (grokRoute === 'official' ? 'grok' : 'cursor-agent') : (agent === 'gemini' ? 'agy' : ['glm', 'deepseek', 'qwen'].includes(agent) ? 'opencode' : agent),
        configuredModel,
        availableModels: agent === 'grok' && grokRoute === 'official' ? ['grok-4.6'] : (availableModels[agent] || [configuredModel]),
        configurableModels,
        authenticated: agent !== 'grok' || grokRoute !== 'official',
        warning: agent === 'grok' && grokRoute === 'official' ? 'CLI oficial não autenticada. Execute `grok login` antes de enviar tarefas.' : null,
      }),
    });
  });
  await page.route(/http:\/\/127\.0\.0\.1:314[1-8]\/health/, async (route) => {
    const port = new URL(route.request().url()).port;
    const agent = { 3141: 'codex', 3142: 'claude', 3143: 'gemini', 3144: 'grok', 3145: 'glm', 3146: 'deepseek', 3147: 'kimi', 3148: 'qwen' }[port];
    await route.fulfill({
      status: 200,
      headers: { 'Access-Control-Allow-Origin': '*' },
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'ok', mode: 'cli',
        configuredModel: agent === 'grok' && grokRoute === 'official' ? 'grok-4.6' : models[agent],
        availableModels: agent === 'grok' && grokRoute === 'official' ? ['grok-4.6'] : (availableModels[agent] || [models[agent]]),
        configurableModels: ['gemini', 'glm', 'deepseek', 'qwen'].includes(agent) || (agent === 'grok' && grokRoute === 'cursor'),
        modelVerified: !['grok', 'kimi'].includes(agent),
        ...(agent === 'grok' ? { route: grokRoute, cliBinary: grokRoute === 'official' ? 'grok' : 'cursor-agent', authenticated: grokRoute !== 'official', provider: 'xai' } : {}),
        ...(agent === 'codex' ? { reasoningEffort: 'xhigh' } : {}),
      }),
    });
  });

  await page.goto(`${origin}/ui`, { waitUntil: 'domcontentloaded' });
  const input = page.getByRole('textbox');

  assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
  await page.getByRole('button', { name: 'Ativar tema claro' }).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'light');
  assert.equal(await page.evaluate(() => localStorage.getItem('meshTheme')), 'light');
  await page.getByRole('button', { name: 'Ativar tema escuro' }).click();
  assert.equal(await page.locator('html').getAttribute('data-theme'), 'dark');
  await page.getByRole('button', { name: /Artefatos/ }).click();
  await page.getByRole('heading', { name: 'Artefatos preservados' }).waitFor();
  await page.getByText('recente.md').waitFor();
  assert.equal(await page.getByText('recente.md').isVisible(), true);
  assert.equal(await page.getByRole('button', { name: 'Baixar artefato recente.md' }).isVisible(), true);
  const artifactDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Baixar artefato recente.md' }).click();
  assert.equal((await artifactDownload).suggestedFilename(), '01-recente.md');
  await page.getByRole('button', { name: 'Concluir' }).click();

  await page.getByRole('button', { name: 'Modelos e CLIs' }).click();
  await page.getByRole('heading', { name: 'Modelos, CLIs e rotas efetivas' }).waitFor();
  await page.waitForFunction(() => document.querySelectorAll('#model-config-body tr').length === 8);
  assert.equal(await page.locator('#model-config-body tr').count(), 8);
  assert.equal(await page.getByLabel('Modelo de execução de gemini').locator('option').count(), 2);
  assert.equal(await page.getByLabel('Modelo de execução de grok').locator('option').count(), 2);
  assert.equal(await page.getByLabel('Modelo de execução de glm').locator('option').count(), 2);
  assert.match(await page.locator('[data-model-agent="gemini"]').innerText(), /2 modelo\(s\) disponíveis/);
  await page.getByLabel('Rota de execução do Grok').selectOption('official');
  await page.getByText(/CLI oficial não autenticada/).waitFor();
  assert.match(await page.locator('[data-model-agent="grok"]').innerText(), /grok-4\.6/);
  assert.match(await page.locator('[data-model-agent="grok"]').innerText(), /login necessário/);
  await page.getByLabel('Rota de execução do Grok').selectOption('cursor');
  await page.getByLabel('Modelo de execução de grok').selectOption('cursor-grok-4.6-xhigh');
  await page.getByText(/Modelo de grok alterado/).waitFor();
  await page.getByLabel('Modelo de execução de gemini').selectOption('gemini-3.1-pro-high');
  await page.getByText(/Modelo de gemini alterado/).waitFor();
  await page.getByLabel('Modelo de execução de glm').selectOption('opencode-go/kimi-k3');
  await page.getByText(/Modelo de glm alterado/).waitFor();
  await page.getByRole('button', { name: 'Concluir' }).click();

  await page.waitForFunction(() => document.querySelector('#sse-badge')?.textContent?.includes('●'));
  tasks.set('child-stream', {
    id: 'child-stream',
    parentTaskId: 'root-fixture',
    status: { state: 'completed', message: { role: 'agent', parts: [{ type: 'text', text: 'child output' }] } },
    metadata: {},
    artifacts: [],
  });
  for (const response of sseResponses) {
    response.write(`event: mesh-event\ndata: ${JSON.stringify({ type: 'working', taskId: 'child-stream', server: 'grok', payload: {} })}\n\n`);
    response.write(`event: task-dialogue\ndata: ${JSON.stringify({
      taskId: 'child-stream',
      role: 'response',
      agent: 'unknown',
      source: 'grok',
      operation: 'stream',
      text: 'Timeout (1800000ms)',
    })}\n\n`);
  }
  await page.locator('#chat .bubble-red').getByText('Timeout (1800000ms)').waitFor();
  assert.equal(await page.locator('.task-run-card[data-task-id="child-stream"]').count(), 0);
  assert.match(await page.locator('#chat .bubble-red').last().locator('xpath=preceding-sibling::*[1]').innerText(), /Grok \/ error/);

  await input.fill('Explique o estado atual');
  await page.getByLabel('Destino do texto livre').selectOption('call');
  await page.getByLabel('Agente alvo').selectOption('grok');
  assert.match(await page.locator('#composer-summary').innerText(), /consulta direta a grok/);
  await page.getByLabel('Destino do texto livre').selectOption('broadcast');

  await input.fill('/help');
  await page.getByRole('button', { name: 'Enviar' }).click();
  await assert.doesNotReject(() => page.getByText('Terminal Commands').waitFor());
  await page.getByRole('button', { name: 'Limpar feed' }).click();
  await assert.doesNotReject(() => page.getByRole('heading', { name: /Uma tarefa/ }).waitFor());
  assert.equal(await page.getByText('Terminal Commands').count(), 0);
  await page.getByRole('button', { name: 'Desfazer' }).click();
  await assert.doesNotReject(() => page.getByText('Terminal Commands').waitFor());

  await input.fill('/comando-inexistente teste');
  await input.press('Enter');
  await page.locator('#composer-error').getByText(/Comando desconhecido/).waitFor();
  assert.equal(await page.locator('#composer-error').getAttribute('role'), 'alert');

  await input.fill('/team --profile=normal Produza uma síntese curta');
  for (const agent of ['gemini', 'grok', 'glm', 'deepseek', 'kimi', 'qwen']) {
    await page.locator(`[data-team-agent="${agent}"]`).click();
  }
  await page.getByText('2 de 8').waitFor();
  await input.press('Enter');
  await page.getByText('Result / team').waitFor();
  const teamBubble = page.locator('#chat .bubble-gold').last();
  const visibleTeamText = await teamBubble.innerText();
  assert.match(visibleTeamText, /SÍNTESE-FINAL/);
  assert.doesNotMatch(visibleTeamText, /CONTRIBUIÇÃO-INDIVIDUAL/);
  await page.getByText('Ver detalhes da auditoria').click();
  assert.equal(await page.getByText('CONTRIBUIÇÃO-INDIVIDUAL').isVisible(), true);
  assert.equal(await page.getByText('Baixar auditoria').isVisible(), true);
  const teamRequest = requests.find(item => item.method === 'mesh/teamAsync');
  assert.deepEqual(teamRequest.params.steps[0].agents, ['claude', 'codex']);

  await input.fill('/ensemble --profile=fast --lang=javascript Implemente approved');
  await input.press('Enter');
  await page.getByText('Result / ensemble').waitFor();
  assert.match(await page.locator('#chat .bubble-gold').last().innerText(), /function approved\(\) \{ return true; \}/);
  const artifactShelf = page.locator('#chat .bubble-gold').last().locator('.artifact-shelf');
  await artifactShelf.getByText('1 artefato preservado').waitFor();
  assert.equal(await artifactShelf.getByText('approved.js').isVisible(), true);
  assert.equal(await artifactShelf.getByRole('button', { name: 'Baixar artefato approved.js' }).isVisible(), true);
  await artifactShelf.getByText('Visualizar conteúdo').click();
  assert.match(await artifactShelf.locator('pre').innerText(), /function approved/);
  assert.equal(await page.locator('#chat .bubble-gold').last().locator('pre br').count(), 0);
  assert.equal(await page.locator('#chat .bubble-gold').last().getByRole('button', { name: 'Copiar bloco de código' }).isVisible(), true);
  const ensembleCard = page.locator('.task-run-card').filter({ hasText: 'Result / ensemble' });
  await ensembleCard.getByText(/Fase 5\/5 · Resultado/).waitFor();
  assert.match(await ensembleCard.locator('.task-metrics').innerText(), /TTFT 350ms/);
  assert.match(await ensembleCard.locator('.task-metrics').innerText(), /tokens 1\.234/);
  assert.match(await ensembleCard.locator('.task-metrics').innerText(), /custo \$0\.042/);
  assert.match(await ensembleCard.locator('.task-phase-timings').innerText(), /cross review 1 1\.2s/);
  const ensembleRequest = requests.find(item => item.method === 'mesh/ensembleAsync');
  assert.equal(ensembleRequest.params.profile, 'fast');
  assert.equal(ensembleRequest.params.rounds, 1);
  assert.equal(ensembleRequest.params.deduplicate, true);
  assert.equal(ensembleRequest.params.early_exit, true);
  assert.deepEqual(ensembleRequest.params.agents, ['claude', 'codex']);
  await page.getByRole('button', { name: 'Todos' }).click();
  await page.getByText('8 de 8').waitFor();

  await input.fill('/status');
  await input.press('Enter');
  await page.getByText(/verificação pendente da primeira execução/).first().waitFor();
  await page.getByTitle(/falha\(s\) histórica\(s\)/).waitFor();
  const cancelResponse = page.waitForResponse(response => response.url().endsWith('/tasks/active-run/cancel'));
  await page.locator('[data-cancel-task="active-run"]').first().click();
  await cancelResponse;
  assert.deepEqual(canceledRequests, ['active-run']);
  const canceledCard = page.locator('.task-run-card[data-task-id="active-run"]');
  await canceledCard.getByText(/cancelamento \d+ms/).waitFor();

  for (let index = 0; index < 360; index++) {
    await input.fill('/help');
    await input.press('Enter');
  }
  assert.ok(await page.locator('#chat > *').count() <= 350);
  assert.equal(await page.getByRole('button', { name: /Carregar mensagens anteriores/ }).isVisible(), true);
  assert.deepEqual(externalRequests, []);
});
