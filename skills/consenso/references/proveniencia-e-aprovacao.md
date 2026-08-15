# Proveniência e aprovação forte

`consenso` distingue manifestação externa, deliberação e aprovação. Um JSON preenchido por um
agente não prova execução. Para `resultado = consenso` ou `aprovacao = true`, o gate exige:

1. `run_id`, `tentativa`, `raiz_artefatos`, `artefato_caminho` e SHA-256 do arquivo real;
2. participantes resolvidos pelas cadeiras canônicas do manifesto, sem aliases contados duas vezes;
3. `ledger_deliberacao.rodadas` numerado sobre o mesmo hash;
4. avaliações consecutivas do mesmo hash, cada qual referenciando em `recibos_nonces` exatamente
   uma manifestação por cadeira;
5. recibos `multiagent_provenance_v1` assinados pelo host, contendo rota, provedor, modelo efetivo,
   execução efetiva, sessão nativa confirmada ou execução isolada confirmada, hashes, nonce,
   tentativa e rodada;
6. posição `aprovar`, sem bloqueadores ou dissensos, em todas as manifestações que formam consenso;
7. quórum e diversidade no piso congelado; redução exige autorização e rótulo explícito;
8. estabilidade forte de ao menos duas avaliações consecutivas; estabilidade 1 é somente consultiva;
9. cada recibo possui `rodada` idêntica ao `numero` da avaliação que referencia seu nonce;
10. consumo atômico dos nonces no ledger global do host somente depois de todas as regras do
    veredito passarem e imediatamente antes da transição para `canonico_aprovado`.

O adaptador grava metadados observados da chamada. O host cria o recibo sem aceitar campos de
execução inventados pelo agente:

```bash
python3 scripts/provenance.py attest-invocation template-recibo.json metadata-invocacao.json \
  --artifact /caminho/do/run/minuta.docx \
  --root /caminho/do/run \
  --manifest assets/multiagent-manifest.json
```

Se a saída estruturada da CLI não expuser o modelo efetivo, `modelo_confirmado` permanece falso e o
recibo não satisfaz hold-out estrito. A primitiva `sign-receipt` é reservada à manutenção e exige
opt-in de ambiente; fluxos comuns usam `attest-invocation`.

Exemplo estrutural reduzido:

```json
{
  "schema": "veredito_consenso_v1",
  "run_id": "parecer-2026-08-14",
  "tentativa": 3,
  "modo": "estrito",
  "politica_por_tentativa": "sempre",
  "resultado": "consenso",
  "aprovacao": true,
  "artefato_caminho": "/caminho/do/run/minuta-v3.docx",
  "raiz_artefatos": "/caminho/do/run",
  "artefato_sha256": "<sha256>",
  "participantes": [
    {"cadeira": "claude", "rota": "claude", "modelo": "claude-opus-5", "provedor": "anthropic"},
    {"cadeira": "codex", "rota": "codex", "modelo": "gpt-5.6-sol", "provedor": "openai"}
  ],
  "ledger_deliberacao": {
    "rodadas": [
      {"numero": 1, "fase": "avaliacao", "artefato_sha256": "<sha256>"},
      {"numero": 2, "fase": "reavaliacao", "artefato_sha256": "<sha256>"}
    ],
    "avaliacoes": [
      {"numero": 1, "resultado": "consenso", "artefato_sha256": "<sha256>", "recibos_nonces": ["<nonce-claude-1>", "<nonce-codex-1>"]},
      {"numero": 2, "resultado": "consenso", "artefato_sha256": "<sha256>", "recibos_nonces": ["<nonce-claude-2>", "<nonce-codex-2>"]}
    ]
  },
  "recibos_proveniencia": ["<quatro recibos assinados>"],
  "rodadas_usadas": 2,
  "ciclos_usados": 0,
  "estabilidade_exigida": 2,
  "estabilidade_atingida": true,
  "quorum_declarado": 2,
  "quorum_minimo": 2,
  "bloqueadores": [],
  "dissensos": [],
  "evidencias": ["arquivo e manifestações verificados"],
  "estado": "canonico_aprovado"
}
```

`evidencias`, `bloqueadores` e `dissensos` são listas de textos não vazios. Objetos nulos,
estruturas arbitrárias e textos em branco invalidam o veredito; uma lista apenas formal como
`[null]` nunca satisfaz o gate de aprovação.

Efetivar a aprovação:

```bash
python3 scripts/consensus_gate.py validate-verdict veredito.json
```

O ledger padrão é `~/.agents/multiagent-state/nonces.json`, compartilhado entre runs para impedir
replay cruzado. `--check-only` apenas inspeciona, nunca efetiva a transição e rejeita nonces já
consumidos. O gate colegiado com
`regra_resultado = consenso_estrito` deve incorporar o `veredito_consenso` completo e apontar para
o mesmo hash; um booleano como `consenso_verificado: true` não é prova.
Ledger alternativo por flag ou ambiente exige opt-in adicional explícito; a variável de ambiente
sozinha não redireciona a prova.
O arquivo do ledger e seu lock não podem ser symlinks. Segredos HMAC carregados pelo host ou
injetados programaticamente precisam ter ao menos 32 bytes; chave vazia ou curta falha fechada e
nunca é usada para validar uma transição.

## Limite de segurança

A atestação HMAC impede que recibos não assinados ou alterados sejam aceitos e o ledger impede
replay acidental ou documental. Ela não cria isolamento contra um processo malicioso executado com
shell irrestrito sob o mesmo usuário do host. As CLIs recebem ferramentas completas como solicitado;
por isso, os escopos de diretório são governança auditável, não sandbox do sistema operacional.
Segredos são removidos do ambiente filho e nunca devem entrar em prompts, artefatos ou pastas
compartilhadas. Para adversários ativos, use contas, contêineres ou sandboxes de SO separados.

Uma autorização de publicação declarada na configuração continua sendo governança procedimental do
mesmo usuário, não prova criptográfica de consentimento humano. O recibo HMAC liga a execução ao
host e detecta alteração/replay; não transforma processos do mesmo usuário em principals isolados.
