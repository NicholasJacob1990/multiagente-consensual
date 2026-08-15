// ============================================
// mesh-plan.js — Plan & Review iterative loop
// ============================================
// Inspired by claudex (claudex:plan), but native to the mesh and 3-agent capable.
//
// Workflow:
//   0. Author agent (default: claude) writes PLAN.md from a description
//   1..N. For each round:
//      a. Reviewer (default: codex) gets a rotating persona + current PLAN.md
//      b. Reviewer outputs structured findings
//      c. Convergence: if findings says "no material issues" → break
//      d. Author revises PLAN.md addressing findings
//
// Artifacts persisted to ~/.a2a/plans/<plan-id>/:
//   PLAN.md                  ← latest version (author's last revision)
//   PLAN-round-N.md          ← snapshot per round
//   findings-round-N.md      ← reviewer findings per round

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { randomUUID } from 'node:crypto';
import { persistContextSnapshot, resolveThreadId } from './mesh-context.js';
import { enrichPromptIfContinuation } from './mesh-continuation.js';

const DEFAULT_ROUNDS = 3;
const DEFAULT_AUTHOR = 'claude';
const DEFAULT_REVIEWER = 'codex';
const DEFAULT_TIMEOUT_MS = 1200000; // 20 min per agent call
const PLANS_DIR = path.join(os.homedir(), '.a2a', 'plans');
const PLAN_REVIEW_CHARS = Math.max(1000, parseInt(process.env.A2A_PLAN_REVIEW_CHARS, 10) || 30000);
const PLAN_FINDINGS_CHARS = Math.max(1000, parseInt(process.env.A2A_PLAN_FINDINGS_CHARS, 10) || 12000);
const GEMINI_PLAN_TIMEOUT_MS = Math.max(1000, parseInt(process.env.A2A_GEMINI_PLAN_TIMEOUT_MS, 10) || 900000);

function truncateForPrompt(text, limit, label = 'content') {
  const value = String(text || '');
  if (value.length <= limit) return value;
  return `${value.slice(0, limit)}\n\n[TRUNCATED ${value.length - limit} chars from ${label}. Full artifact remains on disk.]`;
}

function timeoutForAgent(agent, timeoutMs) {
  return agent === 'gemini' ? Math.min(timeoutMs, GEMINI_PLAN_TIMEOUT_MS) : timeoutMs;
}

// Per-round reviewer personas. Adapted from claudex/scripts/personas.sh.
const PERSONAS = {
  engineer: {
    label: 'Senior-engineer review',
    prompt: `Você é um engenheiro sênior cético com 15+ anos construindo sistemas distribuídos em larga escala.
Sua missão: caçar falhas de design e premissas quebradas.

- Os requisitos são alcançáveis dadas as restrições?
- Quais premissas implícitas podem estar erradas?
- Onde o design quebra sob carga, falha parcial ou concorrência?
- Há componentes faltando, interfaces indefinidas, seções "just works" sem detalhe?
- O escopo é realista para o prazo e o time?
- Top 3 coisas mais prováveis de explodir na semana 1 de implementação?

Seja específico e acionável. Preocupações vagas não ajudam.`,
  },
  security: {
    label: 'Security & data-integrity review',
    prompt: `Você é um engenheiro de segurança e especialista em integridade de dados.
Sua missão: stress-testar postura de segurança e integridade.

- Auth/authz: quem acessa o quê? Há caminhos de privilege escalation?
- Validação de input: onde dados não-confiáveis entram? São sanitizados?
- Race conditions: que estados inconsistentes operações concorrentes podem produzir?
- Partial-failure recovery: se op X tem sucesso mas Y falha, sistema fica consistente?
- Secrets: credenciais/tokens armazenados, transmitidos e rotacionados corretamente?
- Integridade: backups, replicação, idempotência, audit trail?`,
  },
  ops: {
    label: 'Ops/SRE review',
    prompt: `Você é um SRE que esteve on-call em sistemas de produção.
Sua missão: stress-testar postura operacional.

- Observabilidade: métricas, logs, traces — on-call consegue diagnosticar sem ler source?
- Modos de falha: que alertas disparam? São acionáveis? Taxa de falso-positivo?
- Deploy: estratégia de rollout, canary, rollback, migrations de schema?
- Capacidade: gargalos, story de scaling, projeção de custo?
- Dependências: serviços externos, SLAs de vendor, estratégias de fallback?
- Runbooks: como o on-call responde às 3 da manhã? Playbook está completo?`,
  },
  product: {
    label: 'Product & UX review',
    prompt: `Você é um PM/UX rigoroso focado no usuário final.
Sua missão: validar se o plano resolve o problema certo do jeito certo.

- Qual o usuário-alvo? Que dor ele tem hoje?
- O design da feature é intuitivo ou exige documentação extensa?
- Edge cases visíveis ao usuário (estado vazio, erro, loading, permissão negada)?
- Acessibilidade básica (a11y) considerada?
- Métricas de sucesso definidas e mensuráveis?
- Há simplificação possível sem perder valor?`,
  },
  performance: {
    label: 'Performance review',
    prompt: `Você é um engenheiro de performance com tirocínio em medição rigorosa.
Sua missão: caçar gargalos antes de existirem.

- Hot path identificado? Qual a latência alvo? Como será medida?
- Allocations, GC pressure, alocação de strings desnecessárias?
- N+1 queries, JOINs caros, índices faltando?
- Caching strategy: invalidation, TTL, cache stampede?
- Tamanho de payload (rede, disco, memória)?
- Benchmarks ou load tests previstos antes de produção?`,
  },
};

function pickPersona(round, customLensList) {
  if (Array.isArray(customLensList) && customLensList.length) {
    const key = customLensList[(round - 1) % customLensList.length];
    if (PERSONAS[key]) return PERSONAS[key];
  }
  // Default rotation: engineer → security → ops → engineer → ...
  const order = ['engineer', 'security', 'ops'];
  return PERSONAS[order[(round - 1) % order.length]];
}

// Convergence: reviewer signals "nothing material" → loop terminates early
const CONVERGENCE_PATTERNS = [
  /\bno material issues?\b/i,
  /\bnothing material\b/i,
  /\bready to ship\b/i,
  /\blooks good as[- ]is\b/i,
  /\bplan is approved\b/i,
  /\bsem objeções materiais\b/i,
  /\bnenhuma objeção material\b/i,
  /\bpronto para implementação\b/i,
  /\bplano aprovado\b/i,
];

function isConverged(findingsText) {
  if (!findingsText) return false;
  return CONVERGENCE_PATTERNS.some(p => p.test(findingsText));
}

async function callAgent({ meshCaller, agent, prompt, context, timeoutMs }) {
  const result = await meshCaller.executeA2ACall(
    { agent, prompt, timeout_ms: timeoutForAgent(agent, timeoutMs) },
    {
      depth: context.depth - 1, // sem Math.max(1,...) — deixa safety check funcionar
      meshChain: [...context.meshChain],
      taskId: context.taskId,
      selfCallDepth: context.selfCallDepth,
    },
  );
  return result;
}

export function createPlanExecutor({ meshCaller, peers, selfId, maxDepth, meshStore, meshBus, authToken, selfUrl }) {
  async function execute(params, callContext = {}) {
    const description = String(params.description || params.prompt || '').trim();
    if (!description) throw new Error('Plan requires a description');

    const rounds = Math.max(1, Math.min(36, parseInt(params.rounds, 10) || DEFAULT_ROUNDS));
    const author = String(params.author || DEFAULT_AUTHOR).toLowerCase();
    const reviewer = String(params.reviewer || DEFAULT_REVIEWER).toLowerCase();
    const timeoutMs = Math.max(60000, parseInt(params.timeout_ms, 10) || DEFAULT_TIMEOUT_MS);
    const lensList = Array.isArray(params.lenses)
      ? params.lenses.map(l => String(l).toLowerCase().trim()).filter(l => PERSONAS[l])
      : null;

    const allAvailable = [...Object.keys(peers), selfId];
    if (!allAvailable.includes(author)) throw new Error(`Author '${author}' not available (got: ${allAvailable.join(', ')})`);
    if (!allAvailable.includes(reviewer)) throw new Error(`Reviewer '${reviewer}' not available (got: ${allAvailable.join(', ')})`);
    if (author === reviewer) throw new Error(`Author and reviewer must differ; both are '${author}'`);

    const planId = randomUUID();
    const threadId = resolveThreadId(params, callContext, `plan-${planId}`);
    const planDir = path.join(PLANS_DIR, planId);
    fs.mkdirSync(planDir, { recursive: true });

    const context = {
      depth: (callContext.depth ?? maxDepth) - 1,
      meshChain: callContext.meshChain || [],
      taskId: `plan-${planId}`,
      selfCallDepth: callContext.selfCallDepth || 0,
    };
    const { prompt: descriptionForPrompt } = enrichPromptIfContinuation(description, { meshChain: context.meshChain, threadId }, meshStore);

    const emitDialogue = (phase, agent, role, text, extra = {}) => {
      if (!meshBus) return;
      meshBus.publish({
        taskId: context.taskId,
        type: 'dialogue',
        payload: { operation: 'plan', phase, agent, role, text: String(text).slice(0, 100000), ...extra },
      });
    };

    emitDialogue(
      'setup', '*', 'system',
      `Plan iniciado: "${description.slice(0, 200)}" | author=${author} | reviewer=${reviewer} | rounds=${rounds} | dir=${planDir}`,
    );

    // ---- Round 0: author writes initial plan ----
    const authorInitialPrompt = `Escreva um PLAN.md técnico detalhado para:

${descriptionForPrompt}

Estrutura obrigatória:
- **Objetivo** (1-2 frases: o quê e por quê)
- **Contexto** (estado atual relevante, restrições)
- **Solução proposta** (arquitetura, componentes, interfaces)
- **Etapas** (ordem numerada de implementação)
- **Dependências** (serviços, libs, APIs externas)
- **Critérios de aceite** (como saber que está pronto)
- **Riscos conhecidos** (top 3, com mitigação)
- **Estimativa** (ordem de grandeza)

Seja específico, técnico, sem generalidades. Cite arquivos/linhas quando relevante.`;

    emitDialogue('author', author, 'system', `${author} escrevendo plano inicial...`);
    const initialPlan = await callAgent({ meshCaller, agent: author, prompt: authorInitialPrompt, context, timeoutMs });
    let currentPlan = String(initialPlan || '').trim();
    if (!currentPlan || currentPlan.toLowerCase().startsWith('error:')) {
      throw new Error(`Author ${author} failed to write initial plan: ${currentPlan.slice(0, 200)}`);
    }
    fs.writeFileSync(path.join(planDir, 'PLAN-round-0.md'), currentPlan);
    fs.writeFileSync(path.join(planDir, 'PLAN.md'), currentPlan);
    emitDialogue('author', author, 'plan', currentPlan, { round: 0 });

    // ---- Rounds 1..N: review + revise ----
    let lastFindings = '';
    let converged = false;
    let actualRound = 0;
    const roundLog = [];

    for (let r = 1; r <= rounds; r++) {
      actualRound = r;
      const persona = pickPersona(r, lensList);

      emitDialogue(`round-${r}`, '*', 'system', `Rodada ${r}/${rounds} — ${persona.label} (${reviewer})`);

      // Reviewer critique
      const reviewerPrompt = `${persona.prompt}

---

## Plano sob revisão (rodada ${r}/${rounds}):

${truncateForPrompt(currentPlan, PLAN_REVIEW_CHARS, `PLAN.md round ${r}`)}

---

Forneça findings ESTRUTURADOS:

**Findings críticos** (must-fix antes de implementar):
- ...

**Findings importantes** (should-fix):
- ...

**Sugestões opcionais** (nice-to-have):
- ...

**Veredito**: Se NENHUM finding crítico ou importante for válido, escreva EXATAMENTE a frase "no material issues" no veredito. Caso contrário, descreva em 1-2 frases o que ainda precisa ser endereçado.`;

      emitDialogue(`round-${r}`, reviewer, 'system', `${reviewer} revisando como ${persona.label}...`);
      const findings = await callAgent({ meshCaller, agent: reviewer, prompt: reviewerPrompt, context, timeoutMs });
      lastFindings = String(findings || '').trim();
      fs.writeFileSync(path.join(planDir, `findings-round-${r}.md`), lastFindings);
      emitDialogue(`round-${r}`, reviewer, 'findings', lastFindings, { round: r, persona: persona.label });
      roundLog.push({ round: r, persona: persona.label, converged: false });

      if (isConverged(lastFindings)) {
        emitDialogue(`round-${r}`, '*', 'system', `Convergência: reviewer aprovou o plano na rodada ${r}.`);
        converged = true;
        roundLog[roundLog.length - 1].converged = true;
        break;
      }

      // Author revises
      const revisePrompt = `Você escreveu este plano (PLAN.md):

${truncateForPrompt(currentPlan, PLAN_REVIEW_CHARS, `PLAN.md round ${r}`)}

---

O revisor (${persona.label}) apontou:

${truncateForPrompt(lastFindings, PLAN_FINDINGS_CHARS, `findings round ${r}`)}

---

Reescreva o PLAN.md COMPLETO endereçando os findings críticos e importantes (mantenha o que está OK). Adicione no topo uma seção "## Mudanças nesta revisão" listando o que mudou e por quê.`;

      emitDialogue(`round-${r}`, author, 'system', `${author} revisando o plano...`);
      const revised = await callAgent({ meshCaller, agent: author, prompt: revisePrompt, context, timeoutMs });
      const revisedText = String(revised || '').trim();
      if (!revisedText || revisedText.toLowerCase().startsWith('error:')) {
        emitDialogue(`round-${r}`, author, 'error', `Falha ao revisar: ${revisedText.slice(0, 200)}`);
        break;
      }
      currentPlan = revisedText;
      fs.writeFileSync(path.join(planDir, `PLAN-round-${r}.md`), currentPlan);
      fs.writeFileSync(path.join(planDir, 'PLAN.md'), currentPlan);
      emitDialogue(`round-${r}`, author, 'plan', currentPlan, { round: r });
    }

    emitDialogue(
      'complete', '*', 'system',
      `Plan concluído. Rodadas: ${actualRound}. ${converged ? 'Convergiu.' : 'Round limit atingido.'} Artifacts: ${planDir}`,
    );

    const result = {
      planId,
      planDir,
      planPath: path.join(planDir, 'PLAN.md'),
      description,
      rounds: actualRound,
      maxRounds: rounds,
      converged,
      author,
      reviewer,
      lensList: lensList || ['engineer', 'security', 'ops'],
      finalPlan: currentPlan,
      lastFindings,
      roundLog,
    };

    persistContextSnapshot(meshStore, {
      threadId,
      taskId: context.taskId,
      mode: 'plan',
      title: description,
      summary: currentPlan,
      decisions: [
        converged ? `Plan converged after ${actualRound}/${rounds} round(s).` : `Plan reached round limit after ${actualRound}/${rounds} round(s).`,
      ],
      nextSteps: converged ? ['Implement from PLAN.md.'] : ['Review lastFindings before implementation.'],
      errors: [],
      artifacts: [{ kind: 'plan', path: result.planPath }],
      metadata: {
        planId,
        planDir,
        author,
        reviewer,
        rounds: actualRound,
        maxRounds: rounds,
        converged,
      },
    }, '[mesh-plan]');

    return result;
  }

  function formatPlanResult(result) {
    if (!result) return 'Plan failed.';
    return `# Plan ${result.planId}

**Status**: ${result.converged ? '✅ Convergiu' : '⏱  Round limit'} após ${result.rounds}/${result.maxRounds} rodada(s)
**Author**: ${result.author} | **Reviewer**: ${result.reviewer}
**Lentes**: ${result.lensList.join(' → ')}
**Artifacts**: \`${result.planDir}\`

---

${result.finalPlan}`;
  }

  return { execute, formatPlanResult, PERSONAS };
}
