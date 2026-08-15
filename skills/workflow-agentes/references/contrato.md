# Contrato comum dos workflows

## Sumário

1. Configuração
2. Identidade e independência
3. Estados e eventos
4. Artefatos e hashes
5. Falhas e permissões
6. Integração com outros protocolos

## 1. Configuração

Persistir um `meta.json` compatível com:

```json
{
  "schema_version": 1,
  "perfil": "workflow_agents_v1",
  "protocolo": "pipeline_serial_v1",
  "objetivo": "resultado verificável",
  "entrada": {"tipo": "artefato", "snapshot_sha256": "sha256"},
  "participantes": [
    {
      "id": "cadeira-1",
      "agente": "claude-opus-redator",
      "cli": "claude",
      "modelo": "claude-opus-5",
      "provedor_de_acesso": "claude-code",
      "familia": "anthropic/claude",
      "papel": "redator",
      "sessao": "nova",
      "permissoes": ["read"]
    }
  ],
  "estrutura": {},
  "saida": {
    "contrato": "adaptive_output_v1",
    "politica": "adaptive_up_to_native_max",
    "controle_efetivo": "native_route_ceiling",
    "preencher_ate_o_teto": false,
    "teto_global_tokens": null,
    "continuacao_max_segmentos": 8
  },
  "limites": {
    "max_chamadas": 40,
    "max_paralelo": 4,
    "max_tentativas_por_no": 2,
    "max_segundos": 3600,
    "max_custo": null
  },
  "execucao_duravel": {"ativa": false},
  "falha": {
    "cadeira": "pausar",
    "no": "repetir",
    "reducao_quorum": false,
    "fallbacks_autorizados": []
  },
  "integracao_loop": {
    "modo": "nenhuma",
    "politica_novo_hash": "repetir_se_material"
  },
  "estado": "aguardando_confirmacao"
}
```

`estrutura` segue a referência do protocolo. Campos adicionais são permitidos; os obrigatórios não podem ser removidos durante o run. Configurações antigas permanecem congeladas.

Para permitir execução por até cinco dias corridos, substituir o limite legado e ativar este overlay confirmado:

```json
{
  "limites": {"max_segundos": 432000},
  "execucao_duravel": {
    "contrato": "durable_execution_v1",
    "perfil": "durable_5d_v1",
    "ativa": true,
    "relogio": "tempo_corrido",
    "max_segundos": 432000,
    "offline_conta_no_prazo": true,
    "checkpoint_apos": ["chamada", "rodada", "ciclo", "versao", "no", "onda", "join"],
    "retomar_apos_reinicio": true,
    "gravacao_checkpoint": "atomica",
    "idempotencia": "event_id+input_sha256",
    "orcamento_diario": {"max_chamadas": 100, "max_custo": null},
    "orcamento_total": {"max_chamadas": 500, "max_custo": null}
  }
}
```

O prazo parte de `iniciado_em`, inclui sono do Mac, indisponibilidade e tempo offline e termina no máximo após 432000 segundos. O host não executa enquanto estiver indisponível. O checkpoint atômico registra fronteira, estado, sequência, `event_id`, hashes de entrada e saída e deadline. Reinício do coordenador ou bridge exige `status` e `resume`; a chave `event_id+input_sha256` impede repetição da mesma unidade. Se os quatro limites de chamadas e custo forem nulos, o overlay só valida com `orcamento_ilimitado_confirmado: true`; isso confirma ausência de limite local, não gratuidade nem autorização infinita do provedor.

Quando `ativa=true`, `max_segundos` é obrigatório. Repetir um `event_id` só é idempotente se entrada,
saída e estado forem idênticos. Checkpoints aceitam somente estados operacionais conhecidos;
`aprovado` pertence exclusivamente aos gates externos de consenso, avaliação e auditoria e não pode
ser fabricado pelo coordenador durável.
O parâmetro `--now` é reservado a testes e exige `--allow-test-clock`; produção usa o relógio UTC do
host. O lock do checkpoint usa `O_NOFOLLOW` quando disponível e modo 0600. O número de eventos
idempotentes é limitado pelo orçamento total de chamadas e por um teto defensivo.

`saida.politica = adaptive_up_to_native_max` permite usar somente o necessário ou chegar ao teto efetivo da rota, sem obrigar preenchimento e sem teto global artificial. Metas de palavras são flexíveis. Se um artefato obrigatório for truncado, continuar a mesma cadeira em segmentos limpos e impedir joins, seleção ou aprovação até validar a completude. Quando a CLI não publicar o limite, registrar `native_route_ceiling`, não um número presumido.

## 2. Identidade e independência

Separar `agente`, `cli`, `modelo`, `provedor_de_acesso`, família efetiva, papel, lente, sessão e permissões. Um gateway único pode acessar famílias diferentes, mas não equivale automaticamente a provedores independentes. Duas identidades do mesmo modelo contam como sessões distintas, não como diversidade de modelo.

Fixar participantes antes da execução. Swarm e roteamento podem alterar a composição somente dentro do pool, regras e limites confirmados. Toda mudança gera evento e nova versão do manifesto.

## 3. Estados e eventos

Estados comuns:

```text
aguardando_confirmacao -> validando -> planejado -> executando
executando -> pausado | falhou | limite | cancelado | concluido
concluido -> candidato_selecionado | entregue
candidato_selecionado -> loop_em_execucao | entregue
loop_em_execucao -> canonico_aprovado | entregue_sem_aprovacao
```

Registrar em `ledger/eventos.jsonl`: `run_criado`, `config_confirmada`, `plano_emitido`, `no_iniciado`, `no_concluido`, `no_falhou`, `artefato_emitido`, `manifesto_alterado`, `selecao_emitida`, `workflow_encerrado` e eventos próprios do protocolo.

Em `durable_5d_v1`, registrar também `checkpoint_persistido`, `run_pausado`, `run_retomado` e `deadline_atingida`. `pausado` é retomável enquanto o deadline e os orçamentos permitirem; `deadline_atingida` transita para `limite` e jamais para aprovação.

Cada evento contém `event_id`, protocolo, instante UTC, nó/etapa, tentativa, agente, modelo, sessão, `input_sha256`, `output_sha256`, estado, custo/tempo quando conhecidos e razão.

## 4. Artefatos e hashes

Persistir entradas imutáveis em `entradas/`, saídas por nó em `saidas/<id>/` e candidatas em `artefatos/candidatos/`. Usar SHA-256. Uma saída deve declarar todos os hashes de entrada usados. Reexecução com mesmas entradas recebe nova tentativa, sem sobrescrever a anterior.

Somente o host grava arquivos locais. Agentes externos devolvem conteúdo ou patch. Um artefato vira `candidato_selecionado` somente após a regra do protocolo e `canonico_aprovado` somente após gates explícitos do loop.

## 5. Falhas e permissões

Aplicar timeout, repetição e backoff por nó. Não repetir ação externa não idempotente sem chave de idempotência e autorização. Não ampliar permissões porque um agente foi recrutado ou roteado. Operação destrutiva ou comunicação externa continua sujeita à autorização original.

Em indisponibilidade, aplicar apenas `pausar`, `repetir`, `falhar` ou fallback previamente listado. Redução de quórum precisa estar habilitada e registrada.

## 6. Integração

Protocolos podem ser compostos como subgrafos, desde que entradas, saídas, limites e responsabilidade estejam declarados. Evitar recursão ilimitada: profundidade máxima padrão 2 e máximo 1 swarm dinâmico por run.

Quando houver `$loop-debate-agentes`, o workflow produz candidatas; o loop controla correção, consenso, nota-alvo e auditoria. Um veredito do workflow não substitui esses gates.
