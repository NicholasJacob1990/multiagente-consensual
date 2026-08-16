# Protocolo persistente do Loop Debate de Agentes

## Contrato de configuração

Gravar no início do run e congelar:

```json
{
  "contrato_motor": "loop_debate_agentes_v2",
  "manifesto_multiagente": {"contrato": "multiagent_local_v1", "versao": 1, "caminho": "~/.agents/multiagent-manifest.json"},
  "estado_root": "~/.agents/runs",
  "perfil": "debate_agents_v1",
  "perfil_base": "debate_agents_v1",
  "perfil_dominio": null,
  "extensoes_dominio": {},
  "saida": {
    "contrato": "adaptive_output_v1",
    "politica": "adaptive_up_to_native_max",
    "controle_efetivo": "native_route_ceiling",
    "preencher_ate_o_teto": false,
    "teto_global_tokens": null,
    "metas_de_palavras": "flexiveis",
    "continuacao": {"ao_truncar_artefato_obrigatorio": "mesma_cadeira", "max_segmentos": 8, "aprovar_incompleto": false}
  },
  "sessoes_nativas": {
    "contrato": "native_session_mirror_v1",
    "persistir_sessoes_nativas": false,
    "escopo": "uma_por_invocacao",
    "historico_central_canonico": true,
    "espelho_nativo_nao_prova_consenso": true,
    "falha_de_confirmacao": "registrar_e_informar"
  },
  "modo_artefatos": "artefato_unico",
  "pacote": {
    "pacote_id": null,
    "politica_aprovacao": "todos_obrigatorios",
    "snapshot_compartilhado": null,
    "auditoria_consistencia_conjunta": false,
    "manifesto_final": "pacote-final.json",
    "itens": [
      {
        "artefato_id": "principal",
        "obrigatorio": true,
        "tipo": "documento",
        "finalidade": "",
        "depende_de": [],
        "caminho": "texto.md",
        "estado": "rascunho",
        "overrides": {}
      }
    ]
  },
  "estrategia": "consenso_com_decisao_final",
  "estrategia_da_equipe": {"tipo": "consenso_com_decisao_final", "politica_por_tentativa": "sempre"},
  "ciclo_de_melhoria": {"tipo": "ate_criterios", "tentativas": 5, "tentativas_maximas_motor": 20},
  "formacao_decisao_colegiada": {
    "contrato": "decisao_colegiada_v1",
    "ativa": false,
    "metodo_apuracao": "global",
    "modalidade": "opinion_of_court",
    "regra_resultado": "maioria_simples",
    "base_calculo": "votos_validos",
    "quorum": 3,
    "ratio_exigida": false,
    "adesao_fundamentos": "proposicao",
    "votos_concorrentes": "publicar",
    "votos_dissidentes": "publicar"
  },
  "tema": "objetivo do artefato",
  "publico": "público-alvo",
  "formato": "tipo de artefato",
  "extensao": "limite aproximado",
  "alvo": 8.5,
  "piso": 7.0,
  "painel": 3,
  "painel_auditoria": 1,
  "motor": "codex",
  "escritor": "claude",
  "redator": {"cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic"},
  "consolidacao_iterativa": {
    "politica": "redator_original",
    "consolidador": null,
    "publicadores_autorizados": [],
    "publicador_da_proxima_versao": null,
    "controle_concorrencia": "base_sha256",
    "gravacao": "atomica",
    "resposta_as_objecoes": "responsavel_pela_consolidacao",
    "troca_durante_run": "exige_nova_confirmacao",
    "falha_do_consolidador": "pausar",
    "registrar_autoria_por_versao": true
  },
  "ensemble_nxn": null,
  "participantes_consenso": [
    {"agente": "@Estrategista", "papel": "estrategista", "cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic"},
    {"agente": "@Oponente", "papel": "oponente", "cli": "grok", "modelo": "cursor-grok-4.6-high", "provedor": "xai"},
    {"agente": "@Revisor", "papel": "revisor", "cli": "gemini", "modelo": "", "provedor": "google"}
  ],
  "criticos": [
    {"cli": "grok", "modelo": "cursor-grok-4.6-high", "provedor": "xai"}
  ],
  "revisor": {"cli": "gemini", "modelo": "", "provedor": "google"},
  "avaliador": {"cli": "codex", "modelo": "gpt-5.6-sol", "esforco": "xhigh", "provedor": "openai", "funcoes": ["avaliar", "criticar", "sugerir"]},
  "contribuicao_revisor": {
    "formatos_permitidos": ["parecer", "patch", "artefato_alternativo"],
    "pode_gerar_alternativo": true,
    "modo_publicacao": "parecer_apenas",
    "publicadores_autorizados": [],
    "publicacao_direta_sem_reincorporacao": false,
    "substituicao_automatica": false
  },
  "painel_avaliacao": [
    {"id": "painel-1", "cli": "codex", "modelo": "gpt-5.6-sol", "esforco": "xhigh", "provedor": "openai", "lente": "iniciante"},
    {"id": "painel-2", "cli": "gemini", "modelo": "", "provedor": "google", "lente": "especialista"},
    {"id": "painel-3", "cli": "grok", "modelo": "cursor-grok-4.6-high", "provedor": "xai", "lente": "editor"}
  ],
  "decisor": {"agente": "@Supervisor", "cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic", "rota": "claude"},
  "auditor": {"cli": "antigravity", "modelo": "", "esforco": "high", "provedor": "google"},
  "painel_avaliacao_cega": [
    {"id": "auditoria-final", "cli": "antigravity", "modelo": "", "esforco": "high", "provedor": "google", "lente": "integral"}
  ],
  "artefatos": {
    "modo": "artefato_unico",
    "versoes_maximas_por_artefato": 20,
    "um_unico_canonico_por_artefato": true,
    "registrar_autoria_por_versao": true,
    "alternativas": "preservar_sem_promover",
    "aprovacao_agregada": "manifesto_de_hashes",
    "canonico_atual": "texto.md",
    "melhor": "melhor.md",
    "diretorio_candidatos": "candidatos",
    "ledger_decisoes": "ledger/decisoes.jsonl",
    "final": "artefato-final.md",
    "um_unico_aprovado": true
  },
  "consolidacao_final": {
    "modo": "multipla_cega",
    "visibilidade": "cega_ate_todos_concluirem",
    "snapshot_sha256": null,
    "selecao": "humana",
    "sintese": "somente_se_solicitada",
    "escolha_automatica": false,
    "candidatos": [
      {"id": "claude-final", "arquivo": "candidatos/finais/claude.md", "autor": {"cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic", "sessao": "nova-sessao-claude"}},
      {"id": "gemini-final", "arquivo": "candidatos/finais/gemini.md", "autor": {"cli": "gemini", "modelo": "modelo-escolhido", "provedor": "google", "sessao": "nova-sessao-gemini"}},
      {"id": "grok-final", "arquivo": "candidatos/finais/grok.md", "autor": {"cli": "grok", "modelo": "modelo-escolhido", "provedor": "xai", "sessao": "nova-sessao-grok"}}
    ]
  },
  "consenso": {"modo": "com_decisor", "politica_por_tentativa": "sempre", "estabilidade": 2, "efeito_na_aprovacao": "consenso_ou_decisao_registrada", "permitir_override_por_artefato": true},
  "debate": {"modo": "consenso_por_tentativa", "rodadas": 8, "rodadas_por_tentativa": 8, "rodadas_maximas_recomendadas": 18, "rodadas_maximas_motor": 36, "ciclos_por_participante": 2, "ciclos_maximos_recomendados": 6, "ciclos_maximos_por_participante": 12, "fases_minimas_por_ciclo": 3, "regra_coerencia": "rodadas_maior_ou_igual_a_tres_vezes_ciclos", "estabilidade": 2, "reexecutar_a_cada_nova_versao": true, "exigir_consenso_estrito": false},
  "loop": {"tentativas": 5, "tentativas_maximas_motor": 20, "corrigir": true, "exigir_consenso_artefato": true, "reabrir_debate": "a_cada_nova_versao"},
  "independencia": {"politica": "automatico", "falha_de_independencia": "pausar", "quorum_minimo": 2, "quorum_minimo_auditoria": 1},
  "timeout_invocacao": {
    "padrao_segundos": 1800,
    "minimo_segundos": 30,
    "maximo_excepcional_segundos": 3600,
    "excepcional_exige_justificativa": true,
    "politica_tarefa_longa": "checkpoint_e_retomada"
  },
  "limites_operacionais": {
    "custo_maximo": null,
    "tempo_maximo_minutos": 180,
    "tempo_maximo_recomendado_minutos": 360
  },
  "execucao_duravel": {"ativa": false},
  "confirmacao": {"obrigatoria": true, "confirmada_em": null}
}
```

Os campos `motor` e `escritor` são espelhos legados de `avaliador.cli` e `redator.cli`. Mantê-los para compatibilidade com runs e ferramentas antigos. `alvo`, `piso` e `painel` continuam no topo pelo mesmo motivo.

`sessoes_nativas.persistir_sessoes_nativas` é opcional e vale `false` quando ausente. Em runs novos do loop, o padrão também é `false`. Quando ativado explicitamente,
cada invocação externa solicita uma sessão própria na CLI nativa e persiste o recibo `requested`,
`effective`, `confirmed`, rota e identificador/título. O espelho nunca substitui o ledger central,
não transfere contexto entre cadeiras cegas e não prova consenso, independência ou aprovação.

Uma configuração mínima antiga como `{"motor":"claude","escritor":"codex"}` deve continuar válida. Na leitura, preferir os objetos novos e usar os campos antigos como fallback.

Em runs novos, cada invocação externa usa 1800 segundos por padrão. Aceitar de 30 a 1800 segundos como faixa comum e até 3600 segundos somente como exceção justificada na prévia e no recibo. O limite se aplica a uma chamada, não à vida da sessão nativa nem ao loop inteiro. O loop usa 180 minutos como teto operacional padrão e pode ser confirmado até a faixa recomendada de 360 minutos. Ao se aproximar do timeout, pedir checkpoint completo, persistir recibo e retomar a mesma cadeira/sessão confirmada; não alongar uma única chamada quando a tarefa puder ser dividida por fase, seção, teste ou artefato.

Para trabalhos autorizados por até cinco dias corridos, ativar explicitamente o overlay abaixo; ele não muda os padrões dos runs comuns:

```json
{
  "timeout_invocacao": {
    "padrao_segundos": 1800,
    "maximo_excepcional_segundos": 3600
  },
  "limites_operacionais": {
    "tempo_maximo_minutos": 7200,
    "custo_maximo": null
  },
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

Validar e inicializar `checkpoint.json` com `durable_run.py`. O prazo é contado pelo relógio corrido desde `iniciado_em`; suspensão do Mac, perda de rede e indisponibilidade de CLI não executam trabalho, mas consomem o prazo. Depois de cada chamada e de cada fronteira configurada, persistir atomicamente estado, `event_id`, `input_sha256`, `output_sha256`, hashes do artefato, contadores e recibos antes de iniciar a próxima unidade. Na inicialização do coordenador ou do bridge, executar `resume`: continuar exatamente do último checkpoint válido, sem repetir evento já registrado nem substituir modelo, rota ou sessão silenciosamente.

Um run durável para cedo por aprovação, cancelamento, orçamento, deadline, bloqueio material ou dois ciclos completos sem progresso mensurável. Deadline produz `LIMITE_OPERACIONAL`, nunca aprovação. Quando nenhum orçamento monetário estiver disponível, registrar essa limitação e controlar ao menos chamadas e prazo. Se todos os quatro limites forem nulos, exigir `orcamento_ilimitado_confirmado: true`; isso não significa custo ilimitado garantido pelo provedor. Custos informados precisam ser números finitos e positivos: `NaN`, `Infinity`, booleanos e valores não positivos são inválidos e não equivalem a orçamento confirmado.

Em runs novos, `ciclo_de_melhoria.tentativas` e `loop.tentativas` são espelhos do número máximo de versões completas da cadeia canônica por `artefato_id`. Validar `1 <= tentativas <= 20`; o valor 20 é o teto do motor, enquanto o padrão de `debate_agents_v1` é 6. A primeira versão congelada é tentativa 1. Cada correção substantiva cria novo hash e consome a tentativa/versão seguinte. Uma candidata selecionada, síntese ou edição manual incorporada conta como `v1` se inaugurar a cadeia canônica ou como a versão seguinte se substituir o hash corrente. Pareceres, patches, comparativos Word e candidatos não promovidos não consomem o contador. Em pacote, o limite é aplicado separadamente a cada item.

O exemplo acima demonstra a configuração ampliada e continua válido. Num run simples, `criticos` pode ser vazio, `revisor` pode ser nulo e `painel` pode ser 1. Nunca reduzir uma configuração congelada para transformá-la no modo simples.

## Contrato de saída adaptativa

`adaptive_up_to_native_max` não exige resposta longa: permite que cada chamada termine assim que estiver completa ou use até o teto efetivo oferecido pela combinação modelo, provedor e CLI. Não há `max_output_tokens` global. Quando a rota não expõe um parâmetro próprio, persistir `controle_efetivo = native_route_ceiling` e não declarar um número de tokens. Limite menor pedido pelo usuário prevalece; metas internas de palavras são orientações flexíveis.

Saída incompleta não pode ser congelada nem aprovada. Diante de `CONTINUATION_REQUIRED`, término abrupto ou ausência de seção obrigatória, continuar a mesma cadeira e modelo, preferencialmente na mesma sessão. Persistir e recompor até oito segmentos por padrão em fronteiras de seção ou arquivo, ou o limite confirmado no run. Continuação que apenas completa uma manifestação não consome nova rodada, crítica, réplica ou revisão. Se a continuação alterar conteúdo já concluído, tratá-la como revisão substantiva e aplicar o versionamento normal.

## Herança de perfis de domínio

`perfil_base` identifica o contrato operacional e `perfil_dominio` identifica uma extensão. O executor resolve primeiro este protocolo e depois aplica `extensoes_dominio`. A extensão pode:

- recomendar defaults mais restritivos;
- limitar ciclos, rodadas ou tentativas abaixo do teto do motor;
- acrescentar briefing, tipos de evidência, rubrica, estruturas, estados auxiliares e gates;
- exigir auditoria conjunta de pacote.

A extensão não pode redefinir papéis, hashes, candidatos, semântica do consenso, frequência, independência, parada ou compatibilidade; não pode elevar o teto excepcional de 36 rodadas ou 12 ciclos por participante sem novo contrato explícito; não pode dispensar gates do motor. Se houver conflito, usar a mecânica do motor e o requisito de aprovação mais restritivo. Gravar no run o perfil-base, perfil de domínio, versão de ambos e configuração efetiva já resolvida.

## Contrato genérico de pacote

`modo_artefatos = artefato_unico` preserva os caminhos legados. `pacote_multi_artefato` exige pelo menos dois itens, `artefato_id` único, caminho relativo seguro, finalidade, obrigatoriedade e `depende_de`. Validar que as dependências formam DAG e que nenhum item aponta para ID inexistente.

Cada item mantém seus próprios `tentativa_atual`, versão, hash, ledger, candidatos, avaliação, deliberação, auditoria e estado. Overrides por item podem escolher papéis, intensidade, consenso e limites dentro do contrato-base. O snapshot compartilhado não transfere aprovação. Exatamente um arquivo pode ser `canonico_aprovado` por item.

O manifesto final deve conter `pacote_id`, snapshot, ordem topológica, dependências, itens obrigatórios, caminhos e hashes finais, gates individuais, resultado do gate conjunto e procedência. O pacote só pode ser `pacote_aprovado` quando todos os itens obrigatórios estiverem aprovados e `auditoria_consistencia_conjunta`, quando configurada, referir-se ao manifesto exato. Mudança em qualquer hash invalida o manifesto. Reabrir o item alterado e somente seus dependentes materialmente afetados, registrando a causa.

`estrategia` é o espelho legado de `estrategia_da_equipe.tipo`; `loop.tentativas` espelha `ciclo_de_melhoria.tentativas`; `debate.rodadas` espelha `debate.rodadas_por_tentativa`; e `avaliador` espelha a primeira cadeira de `painel_avaliacao`. Em configurações novas, gravar os dois formatos. `manifesto_multiagente` e `estado_root` registram a fonte canônica e o estado neutro; não são copiados para runs antigos. `participantes_consenso`, `decisor`, `painel_avaliacao`, `painel_avaliacao_cega`, `contribuicao_revisor`, `consolidacao_iterativa`, `ensemble_nxn`, `consenso`, `saida`, `modo_artefatos`, `pacote`, `artefatos`, `perfil_dominio`, `extensoes_dominio`, `consolidacao_final`, `formacao_decisao_colegiada`, `independencia` e `confirmacao` são opcionais para compatibilidade, mas passam a ser gravados quando o pedido usar esses recursos.

Runs antigos sem esses campos preservam o comportamento anterior: `perfil_base = perfil`, `perfil_dominio = null`, `saida.politica = adaptive_up_to_native_max` apenas para novas chamadas não congeladas, `sessoes_nativas.persistir_sessoes_nativas = false`, timeout legado quando já congelado, `modo_artefatos = artefato_unico`, um item implícito `principal`, `contribuicao_revisor.modo_publicacao = parecer_apenas`, `contribuicao_revisor.substituicao_automatica = false`, `consolidacao_iterativa.politica = redator_original`, `consolidacao_iterativa.consolidador = null`, `ensemble_nxn = null`, `formacao_decisao_colegiada.ativa = false`, `formacao_decisao_colegiada.metodo_apuracao = global`, `artefatos.canonico_atual = texto.md`, `artefatos.um_unico_aprovado = true` e `consolidacao_final.modo = redator_unico`. Os modos `pacote_multi_artefato`, `ensemble_nxn_v1`, `consolidador_designado`, `publicacao_compartilhada`, `publicar_candidata`, `publicar_canonico`, `dupla_cega`, `multipla_cega`, qualquer modalidade colegiada e os métodos `analitico` ou `hibrido` nunca são inferidos automaticamente.

Em runs novos, validar `1 <= ciclo_de_melhoria.tentativas == loop.tentativas <= 20`, `1 <= debate.rodadas_por_tentativa <= 36`, `0 <= debate.ciclos_por_participante <= 12` e `rodadas_por_tentativa >= 3 × ciclos_por_participante`. Quando apenas um dos espelhos de tentativas estiver presente, propagá-lo ao outro; quando ambos divergirem, pausar antes da confirmação. `rodadas_por_tentativa` conta fases globais coordenadas; os contadores de crítica, réplica e revisão são individuais por cadeira. Quando somente ciclos forem informados, elevar as rodadas ao mínimo coerente. Quando somente rodadas forem informadas, usar no máximo `min(2, floor(rodadas_por_tentativa ÷ 3))` ciclos; a rodada única explícita usa 0 ciclos. Se ambos forem explícitos e incompatíveis, pedir correção antes da confirmação. Recomendar até 18 rodadas globais/6 ciclos; usar 19–36/7–12 somente com extensão excepcional registrada. Preservar runs legados já congelados sem reescrevê-los.

Padrões de `debate_agents_v1`:

- `ciclo_de_melhoria.tipo = ate_criterios`;
- 6 tentativas;
- máximo configurável de 20 tentativas/versões completas por `artefato_id`;
- painel externo de 3 sessões;
- auditoria cega de 1 sessão nova, salvo número explícito;
- alvo 8,5 e piso 7,0;
- estratégia interna em toda tentativa, salvo `politica_por_tentativa` diferente;
- auditoria cega final;
- consolidação iterativa por `redator_original`; `consolidador_designado` somente por pedido explícito;
- contribuição do revisor em `parecer_apenas`; `publicar_candidata` e `publicar_canonico` somente por pedido explícito;
- consolidação final por `redator_unico`; `dupla_cega` ou `multipla_cega` somente por pedido explícito;
- exatamente um canônico aprovado por artefato, com candidatos alternativos preservados;
- encerramento antecipado por aprovação, sem progresso, bloqueio, cancelamento ou limite operacional.

O modo `loop_simples` pode usar painel 1 e `estrategia_da_equipe.tipo = nenhuma`. Nunca converter silenciosamente `debate_agents_v1` em modo simples.

Padrões de `ensemble_nxn_v1`:

- ativação somente por pedido explícito;
- N=3 proposto e confirmado quando o usuário não indicar participantes;
- N produtores, N revisores e matriz completa cega;
- profundidade `profundo`, com 2 ciclos de crítica → réplica → revisão;
- ao menos 6 rodadas globais no padrão profundo, faixa recomendada até 18/6 e teto excepcional até 36/12;
- até 3 tentativas externas;
- seleção por juiz independente sem aprovação automática;
- consenso sobre o candidato selecionado em cada tentativa;
- painel externo 3, alvo 8,5, piso 7 e auditoria cega 1;
- todos os candidatos e pareceres preservados; exatamente um canônico aprovado por artefato.

Ler e aplicar [ensemble-nxn.md](ensemble-nxn.md) integralmente quando esse perfil estiver ativo. `ensemble_nxn` é alias natural; persistir sempre `ensemble_nxn_v1`.

Não criar o diretório do run nem chamar modelos enquanto `confirmacao.obrigatoria` for verdadeira e `confirmada_em` estiver nulo. A confirmação do usuário congela a configuração resolvida; mudanças posteriores exigem novo resumo e nova confirmação.

## Contrato de confirmação

O resumo apresentado ao usuário deve conter, no mínimo: perfil-base, eventual perfil de domínio, modo de artefatos, itens e dependências, estratégia da equipe, ciclo de melhoria, participantes, redator inicial, política das correções, eventual consolidador designado, modo de publicação do revisor, publicadores autorizados e regra de turno, decisor, modo e frequência do consenso, rodadas por tentativa, tentativas/versões máximas por artefato e teto do motor de 20, meta média, piso por critério, tamanho do painel, política de independência, tipo de saída permitida ao revisor, modo de consolidação final, política para candidatos alternativos, gate conjunto, escolha final e tipo de auditoria. Quando a formação colegiada estiver ativa, incluir modalidade, regra de resultado, base de cálculo, quórum, exigência da ratio, adesão aos fundamentos e publicação de opiniões separadas. No perfil N×N, incluir N, produtores, revisores, matriz e autorrevisão, ciclos, juiz, política de seleção, repetição por tentativa e estimativa máxima de chamadas. Usar rótulos naturais e não expor JSON, flags ou comandos na interface comum.

Uma resposta afirmativa simples confirma exatamente o resumo exibido. Se o usuário corrigir um campo, atualizar somente esse campo e mostrar novamente o resumo completo antes de executar. A confirmação não precisa ser repetida a cada tentativa, pois os limites e participantes já ficam congelados.

## Resolução por host

Se o usuário não indicar redator, detectar o host atual e usar o CLI correspondente. Não inferir que o host precisa ocupar os demais papéis.

| Host | `redator.cli` padrão |
|---|---|
| Claude Code | `claude` |
| Codex | `codex` |
| Gemini 3.7 pelo Antigravity CLI | `gemini` |
| Antigravity CLI | `antigravity` |
| Grok CLI | `grok` |
| Kimi K3 pelo Kimi Code CLI | `kimi` |
| OpenCode | `opencode` |

Ler `~/.agents/multiagent-manifest.json` e distinguir seat semântica, modelo e rota de execução. A política local resolve Codex exclusivamente pelo Codex CLI com `gpt-5.6-sol` e esforço `xhigh`, Grok exclusivamente pelo Cursor com `cursor-grok-4.6-high`, Claude exclusivamente pelo Claude Code com `claude-opus-5`, Kimi K3 pelo Kimi Code e Gemini 3.7 pelo Antigravity. Para novas chamadas Claude, Codex ou Grok, rejeitar override de modelo; runs já congelados preservam sua configuração histórica. A configuração efetiva registra modelo, esforço, rota e provedor. Manifesto ausente/inválido ou indisponibilidade pausa em vez de trocar a rota silenciosamente. `model-routing.yaml` é visão gerada e não pode prevalecer sobre o JSON.

Sem avaliador explícito, usar Codex para um redator Claude e Claude para os demais redatores. Se o modelo/provedor efetivo do redator tornar essa escolha coincidente, trocar o padrão para Codex. No modo simples, esse único agente acumula avaliação, crítica e sugestões. No perfil `debate_agents_v1`, preencher três cadeiras elegíveis em `painel_avaliacao`, preservando diversidade conforme a política e sem chamar todos os CLIs. Para o auditor, preferir um modelo/provedor diferente do redator e do painel, sempre em sessão nova e cega. Se isso não for possível, usar uma cadeira elegível em sessão nova e registrar que a auditoria é cega, mas não independente de modelo. Não criar críticos adicionais ou revisor separado sem pedido explícito.

Toda lista explícita de modelos/CLIs prevalece sobre esses padrões. Usar exatamente os participantes e modelos solicitados em cada papel, sem inserir automaticamente host, Claude, Codex ou outro participante. Um modelo escolhido pode ser informado como alias do CLI ou como `provedor/modelo` quando o CLI aceitar esse formato.

O redator resolvido cria a primeira versão. Por padrão, ele também é o responsável pela consolidação iterativa. Se o usuário designar outro agente/modelo, gravar `consolidacao_iterativa.politica = consolidador_designado` e sua identidade completa; ele cria a segunda versão e as seguintes. Não promover crítico, revisor ou autor de alternativa a consolidador sem essa confirmação.

Se o usuário autorizar que revisores também publiquem o canônico, gravar `consolidacao_iterativa.politica = publicacao_compartilhada`, `contribuicao_revisor.modo_publicacao = publicar_canonico` e a identidade completa de cada cadeira em ambos os `publicadores_autorizados`. Antes de cada correção, resolver exatamente um `publicador_da_proxima_versao`; o turno pode alternar, mas deve ser congelado antes da geração. A autorização permite publicar a próxima versão sem reincorporação pelo redator, não permite aprová-la nem disputar o ponteiro com outro agente.

Para prototipação simultânea, preferir `contribuicao_revisor.modo_publicacao = publicar_candidata`: cada agente trabalha em caminho, branch ou worktree próprio e a integração posterior cria uma nova versão canônica. Usar `publicar_canonico` somente em publicação serializada ou em itens/seções canônicas independentes.

Interpretações naturais:

- “debate sem loop” → `estrategia_da_equipe.tipo = debate_adversarial`, `ciclo_de_melhoria.tipo = nenhuma` e uma única versão.
- “loop sem debate” → `estrategia_da_equipe.tipo = nenhuma` e `ciclo_de_melhoria.tipo = ate_criterios`.
- “novo debate apenas se necessário” → `estrategia_da_equipe.politica_por_tentativa = se_necessario`.
- “use painel de 3 com modelos diferentes” → três cadeiras em `painel_avaliacao` e `independencia.politica = modelo_diferente_do_redator`.
- “não substitua se faltar um avaliador” → `independencia.falha_de_independencia = pausar`.
- “reduza o quórum se necessário” → `independencia.falha_de_independencia = reduzir_quorum`, preservando `quorum_minimo` e maioria.
- “consenso entre @Estrategista, @Oponente e @Revisor” → resolver essas menções no cadastro de agentes e gravá-las em `participantes_consenso`; a menção identifica o agente, não determina por si só CLI ou modelo.
- “@Supervisor decide ao final” → gravar o agente resolvido em `decisor`.
- “4 rodadas por tentativa e até 5 tentativas” → `debate.rodadas_por_tentativa = 4`, `debate.rodadas = 4`, `debate.ciclos_por_participante = 1` quando ciclos não forem informados e `loop.tentativas = 5`.
- “gere até 20 versões da minuta” → `ciclo_de_melhoria.tentativas = loop.tentativas = 20`; v1 é a primeira tentativa, v20 é a última e v21 é proibida nesse run.
- “repita o consenso depois de corrigir” → `debate.modo = consenso_por_tentativa` e `debate.reexecutar_a_cada_nova_versao = true`.
- “aprove somente em consenso” → `estrategia_da_equipe.tipo = consenso_estrito` e `debate.exigir_consenso_estrito = true`; decisão final não substitui acordo.
- “uma rodada, sem corrigir” → uma deliberação da versão corrente com `rodadas_por_tentativa = 1`, `tentativas = 1`, `estabilidade = 1` e `corrigir = false`; o relatório diz `acordo provisório` ou `dissenso`, usa saída consultiva e não emite aprovação.
- “Grok avalia” → `avaliador.cli = grok`, acumulando avaliação, crítica e sugestões.
- “Grok critica também” → adicionar Grok em `criticos` como cadeira adicional.
- “Claude e Gemini criticam” → duas entradas em `criticos`.
- “Codex revisa” → `revisor.cli = codex`.
- “Codex pode propor outra versão” → permitir `patch` e `artefato_alternativo`, sempre com `substituicao_automatica = false`.
- “os revisores podem publicar versões próprias” → `modo_publicacao = publicar_candidata`; preservar cada candidata e não trocar o ponteiro.
- “o revisor também pode publicar o canônico” → `modo_publicacao = publicar_canonico`, `politica = publicacao_compartilhada`, registrar o revisor em `publicadores_autorizados` e congelar o turno por tentativa.
- “todos trabalham simultaneamente no protótipo” → candidatas/branches/worktrees separados por padrão; integrar somente depois da revisão cruzada.
- “X redige e corrige” → usar X como `redator` e `consolidacao_iterativa.politica = redator_original`.
- “X redige e Y consolida/corrige as versões seguintes” → usar X como `redator`, `consolidacao_iterativa.politica = consolidador_designado` e gravar Y em `consolidacao_iterativa.consolidador`.
- “somente Y consolida” → se houver redator já resolvido, manter sua autoria inicial e designar Y para as versões seguintes; se não houver, pedir apenas quem cria a primeira versão. `consolidacao_final.modo = redator_unico` continua significando uma única consolidação final pelo responsável iterativo configurado.
- “X e Y fazem versões finais independentes” → `consolidacao_final.modo = dupla_cega`, exatamente os dois modelos solicitados, duas candidatas preservadas, visibilidade cega e escolha humana.
- “X, Y e Z fazem versões finais independentes” → `consolidacao_final.modo = multipla_cega`, exatamente os modelos solicitados, uma candidata por modelo, visibilidade cega e escolha humana.
- “combine as versões ao final” → permitir síntese somente depois de confirmação explícita; a síntese recebe novo hash e repete todos os gates finais.
- “use Opus 5 como avaliador” → `avaliador.cli = claude`, `avaliador.modelo = claude-opus-5`.
- “OpenCode audita com provider/model” → `auditor.cli = opencode`, modelo conforme informado.
- “você redige” → host atual como `redator`.
- “ensemble N×N” ou “todos geram e todos revisam todos” → `perfil = ensemble_nxn_v1`, `estrategia_da_equipe.tipo = ensemble_nxn` e configuração conforme `ensemble-nxn.md`.
- “ensemble profundo” ou “deep ensemble” → `ensemble_nxn.profundidade = profundo`, `ensemble_nxn.ciclos = 2` e ao menos 6 rodadas.
- “ensemble rápido” → `ensemble_nxn.profundidade = rapido`, `ensemble_nxn.ciclos = 1` e ao menos 3 rodadas.
- “ensemble máximo recomendado” → `ensemble_nxn.profundidade = maximo`, `ensemble_nxn.ciclos = 6` e 18 rodadas; a extensão excepcional pode alcançar 12 ciclos e 36 rodadas se necessária e confirmada.
- “sem autorrevisão” → matriz sem diagonal com N×(N−1) pareceres; informar que não é N×N estrita.
- “use X como juiz do ensemble” → gravar X em `ensemble_nxn.selecao.juiz`; o juiz seleciona ou sintetiza conforme autorização, mas não aprova.
- “cada julgador profere seu voto” ou “decisão seriatim” → ativar `decisao_colegiada_v1` com `modalidade = seriatim`, preservar todos os votos e apurar separadamente resultado e fundamentos.
- “uma decisão em voz única do colegiado” ou “per curiam” → `modalidade = per_curiam`; exigir opinião institucional impessoal e não ocultar voto separado quando a política local mandar publicá-lo.
- “opinião da corte com votos concorrentes e dissidentes” → `modalidade = opinion_of_court`, formar opinião principal pelas proposições que obtiverem adesão suficiente e publicar opiniões separadas conforme a política confirmada.
- “vote no resultado final” ou “case-by-case” → `metodo_apuracao = global` e `contrato = decisao_colegiada_v1`.
- “vote questão por questão”, “premissa a premissa” ou “issue-by-issue” → oferecer `metodo_apuracao = analitico` e `contrato = decisao_colegiada_v2`; congelar questões e regras e aguardar confirmação da prévia.
- “confirme o resultado derivado ao final” → `metodo_apuracao = hibrido`, `contrato = decisao_colegiada_v2` e `politica_confirmacao = bloqueante`.
- “preliminares em separado” sem outro gatilho → manter `global` e apenas oferecer o analítico; não promovê-lo silenciosamente.
- “maioria qualificada de dois terços” → `regra_resultado = maioria_qualificada` e `limiar_qualificado = 0.6666667`; não transformar maioria no resultado em consenso.
- “extraia a ratio comum” → `ratio_exigida = true` e adesão individual por proposição essencial; se o apoio recair apenas sobre o dispositivo, declarar `ratio_status = somente_resultado`.

## Matriz de separação

Registrar no agregado:

- `hold_out_de_cli`: CLI avaliador diferente do CLI redator;
- `hold_out_de_modelo`: modelo avaliador conhecido e diferente do modelo redator conhecido;
- `hold_out_de_provedor`: provedor avaliador conhecido e diferente do provedor redator conhecido;
- `sessao_separada`: verdadeiro quando o avaliador não reutiliza a sessão de redação;
- `auditoria_cega`: verdadeiro somente no modo cego sem histórico.

Modelo vazio ou desconhecido não prova hold-out. Nesse caso registrar `null` ou `false`, acompanhado de `modelo_nao_fixado: true`; nunca presumir independência.

Além da matriz por cadeira, registrar no agregado:

- `identidades_separadas` e `sessoes_separadas`;
- `familias_de_modelo_ativas` e `provedores_ativos`;
- `diversidade_reduzida` quando houver mesmo modelo em sessões distintas;
- `cadeiras_indisponiveis`, `quorum_declarado` e `quorum_efetivo`;
- `politica_de_independencia` e eventual redução de confiabilidade.

## Contrato de cada papel

### Redator

Recebe briefing e fontes. Devolve a primeira versão completa, sem notas para o avaliador e sem pedidos de aprovação. Quando `consolidacao_iterativa.politica = redator_original`, também recebe a síntese do debate, responde às objeções e devolve as versões seguintes. Quando externo, não grava arquivos: o host persiste sua saída.

### Consolidador iterativo

É o redator original por padrão. Quando houver `consolidador_designado`, recebe a versão-base congelada, ledger, fontes, critérios, respostas e candidatos autorizados; decide a incorporação ponto por ponto e devolve a próxima versão completa. Não apaga nem assume a autoria da primeira versão, não sobrescreve diretamente o canônico e não muda tese material sem registrar a decisão. O host valida a base, persiste a saída e registra o autor de cada versão.

O designado não surge por inferência do papel de crítico ou revisor. Troca durante o run exige nova prévia e confirmação. Se ficar indisponível, aplicar `falha_do_consolidador`: pausar por padrão ou usar apenas o fallback já autorizado. Se também ocupar cadeira de avaliação, sua avaliação da própria versão não conta como independente.

### Revisor-publicador

No modo `publicar_canonico`, recebe a versão-base congelada, o ledger, as fontes, as réplicas e o turno de publicação. Pode produzir e publicar a próxima versão canônica sem passar a saída novamente pelo redator. O recibo deve registrar `artefato_id`, tentativa, versão, `base_sha256`, `sha256`, autor, CLI, modelo, provedor, sessão, turno e caminho canônico relativo.

Rejeitar o recibo se o autor não estiver autorizado, o turno pertencer a outra cadeira, o `base_sha256` não corresponder ao ponteiro corrente, a versão não for a sucessora esperada, o limite estiver esgotado ou o destino escapar do item. O ledger de publicação e seus locks devem ser arquivos regulares dentro da raiz autorizada; symlink é proibido mesmo quando aponta para outro arquivo dentro da própria raiz. A troca do ponteiro deve ser atômica; a versão-base permanece imutável no histórico. Depois da publicação, invalidar todos os gates do hash anterior. O publicador não integra painel ou auditoria independente da própria versão.

### Avaliador-crítico

Recebe a versão corrente e, a partir da segunda tentativa, o próprio veredito anterior e a resposta do redator. Em `parecer_apenas`, não edita o documento canônico. Devolve notas, acertos, falhas, crítica principal, sugestões priorizadas e confirmação do que foi resolvido. Em `publicar_candidata`, pode persistir patch ou alternativa completa em caminho próprio. Em `publicar_canonico`, somente a cadeira autorizada e titular do turno pode publicar a próxima versão conforme o contrato do revisor-publicador. Deve manter critérios estáveis entre tentativas.

### Crítico adicional

Recebe texto, fontes e veredito agregado. Devolve: melhor aspecto, falha mais importante, evidência, mudança sugerida e condição que refutaria a crítica. Não altera o artefato.

### Revisor opcional

Recebe texto e críticas anonimizadas. Consolida acordos, explicita conflitos e produz plano curto de revisão. Pode sugerir redação, mas a autoria da versão seguinte permanece com o responsável resolvido por `consolidacao_iterativa`, salvo se esse próprio revisor tiver sido explicitamente designado para o papel.

Painel maior que 1 é opcional. Quando solicitado, executar uma sessão por lente. Isso cria independência de leitura, não necessariamente de modelo.

### Painel externo

Recebe a proposta consolidada da equipe, o artefato congelado, fontes e rubrica. Não participa da redação nem edita o documento. Cada cadeira usa identidade e sessão separadas e devolve veredito próprio; a agregação recalcula mediana por critério, média, piso e maioria fora dos modelos.

`painel_avaliacao` pode combinar CLIs, modelos e provedores. O tamanho efetivo deve corresponder às cadeiras que responderam, nunca apenas ao número declarado. Se uma cadeira falhar, aplicar `independencia.falha_de_independencia`: pausar ou reduzir o quórum com registro explícito. Não trocar a cadeira por outro modelo sem autorização.

### Decisor opcional

Recebe a versão congelada, posições anonimizadas, dissensos, evidências e critérios. Decide ponto por ponto e justifica. Pode resolver matéria interpretativa, estratégica, de risco ou preferência, mas não pode transformar maioria em consenso, dispensar alvo/piso, ignorar erro factual crítico, aprovar outro hash, editar o artefato ou substituir avaliação e auditoria. Uma decisão que exija correção abre nova tentativa.

Com `estrategia = consenso_com_decisao_final`, o decisor pode satisfazer o gate deliberativo sem unanimidade somente quando resolver todos os bloqueios materiais sujeitos a julgamento. Registrar `decisão final sem consenso` e preservar cada dissenso. Com `debate.exigir_consenso_estrito = true`, a decisão não substitui consenso e serve apenas para orientar a próxima correção.

### Auditor

Inicia sessão nova. Não recebe histórico, notas, feedback, identidades, versões anteriores ou melhor versão. Recebe somente artefato candidato, fontes autorizadas, critérios e limites. Sua aprovação confirma robustez, não consenso entre modelos.

## Contrato de artefatos e decisões

Há um único ponteiro canônico corrente e um único destino final por `artefato_id`: na execução simples, normalmente `texto.md` e `artefato-final.md`; no pacote, `artefatos/<artefato_id>/texto.md` e `artefatos/<artefato_id>/artefato-final.md`. Em `redator_original` ou `consolidador_designado`, somente o responsável resolvido produz a próxima versão. Em `publicacao_compartilhada`, também pode produzi-la o revisor autorizado que detenha o turno congelado. Saídas sem autorização nunca sobrescrevem esses caminhos. `consolidacao_final.modo = redator_unico` é nome legado para uma única consolidação final por artefato; não força que o responsável iterativo seja o redator original.

Estados válidos:

- `rascunho_canonico`: versão corrente ainda não aprovada;
- `candidato_alternativo`: patch ou documento proposto contra uma versão-base;
- `candidato_final`: consolidação independente pronta para comparação;
- `candidato_ensemble`: versão independente de um produtor no perfil N×N;
- `canonico_selecionado`: candidato escolhido ou síntese, inclusive do ensemble, ainda aguardando gates;
- `canonico_aprovado`: único hash do item que satisfez os gates deliberativo, de avaliação e de auditoria efetivos.

Cada linha de `ledger/decisoes.jsonl` deve conter pelo menos:

```json
{"id":"obj-001","artefato_id":"principal","tentativa":1,"base_sha256":"...","autor":{"cli":"codex","modelo":"gpt-5.6-sol","provedor":"openai","sessao":"..."},"tipo":"problema_factual","problema":"...","evidencia":["fonte:linha"],"proposta":"...","resposta_responsavel":{"papel":"redator_original","cli":"claude","modelo":"claude-opus-5","status":"aceita_parcialmente","justificativa":"...","evidencia":["fonte:linha"]},"estado":"resolvida"}
```

Usar para `resposta_responsavel.status`: `aceita`, `aceita_parcialmente`, `rejeitada_com_evidencia` ou `esclarecimento_solicitado`. Aceitar `resposta_redator` como alias de compatibilidade em ledgers antigos. Objeção material só fica `resolvida` quando a versão corrente incorpora a decisão ou apresenta evidência suficiente para rejeitá-la.

Cada candidato deve ter manifesto imutável com `id`, `artefato_id`, caminho relativo seguro, `sha256`, `base_sha256`, autor, CLI, modelo, provedor, sessão, tentativa, snapshot de evidências, visibilidade e estado. Cada versão canônica deve registrar também `autor_inicial`, `autor_da_versao`, `papel_publicador`, `turno_publicacao` e `politica_consolidacao_iterativa`. Rejeitar caminho absoluto, `..`, ID duplicado no item, arquivo ausente, hash divergente ou base diferente da versão criticada.

O canônico não é escolhido por ordem de geração, nota isolada ou maioria simples. Exatamente um arquivo por `artefato_id` pode receber `canonico_aprovado`; os demais permanecem consultáveis como candidatos ou histórico. Um pacote pode, portanto, conter vários canônicos aprovados, mas nunca mais de um por item.

## Consolidação final cega múltipla

Nos modos `dupla_cega` e `multipla_cega`, congelar ledger, fontes, rubrica e evidências antes de iniciar e preencher `consolidacao_final.snapshot_sha256`. Criar uma candidata por modelo/CLI explicitamente selecionado, sem acrescentar participantes. Cada autor recebe o mesmo snapshot, produz sua consolidação sem ver as demais e devolve o documento completo ao host. O host persiste todas as candidatas, grava `sha256` e `base_sha256` em cada manifesto e só então libera a comparação.

Executar `comparar-candidatos.sh` para auditar cegamente cada candidata com `painel_avaliacao_cega`, ou com o auditor legado quando o painel não estiver configurado. Gerar recibo com hashes, procedência, rubrica, notas e diffs pareados; não gerar escolha automática. O estado passa a `AGUARDANDO_ESCOLHA_HUMANA`.

Depois da escolha humana, copiar a candidata escolhida para o destino final do item. Se o usuário pedir síntese, produzir um novo arquivo completo e tratá-lo como novo hash. Em ambos os casos, o arquivo final exato precisa passar novamente pelo gate deliberativo configurado, pela avaliação e pela auditoria cega antes de receber `canonico_aprovado`.

## Consenso do artefato

No modo `consenso_por_tentativa`, cada tentativa começa, depois de existir a versão completa, pelo congelamento do ponteiro do item, registro de `artefato_id` e `artefato_sha256` e execução de `$consenso` sobre essa versão exata. Só depois vêm decisão/dissensos e avaliação independente. O veredito deve registrar modo, política, consenso favorável ou ausente, hash, participantes, rodadas, ciclos, bloqueadores, pontos de dissenso e evidências.

Se qualquer gate exigir correção, transformar consenso, dissensos, decisão e avaliação em entradas da próxima versão. Qualquer alteração invalida deliberação, decisão e avaliação vinculadas ao hash anterior; a nova tentativa exige novo hash e executa nova deliberação somente conforme a política congelada. Nunca reutilizar aprovação da versão anterior.

No modo simples legado `consenso_sob_demanda`, mapear para `politica_por_tentativa = se_necessario`. Exigir consenso final somente em `modo = estrito` ou `com_decisor`; em `consultivo`, registrar o parecer; em `desativado + nenhum`, omitir a deliberação e qualquer alegação de consenso.

## Máquina de estados do coordenador local

Usar estes estados no coordenador local do Claude Code ou Codex:

```text
AGUARDANDO_CONFIRMACAO
  → REDIGINDO | GERANDO_CANDIDATOS_NXN
GERANDO_CANDIDATOS_NXN
  → CONGELANDO_MATRIZ_NXN
  → REVISAO_CRUZADA_NXN
  → REPLICAS_NXN
  → REVISOES_NXN
      ├→ REVISAO_CRUZADA_NXN
      └→ SELECIONANDO_NXN
SELECIONANDO_NXN
  → VERSAO_CONGELADA | AGUARDANDO_ESCOLHA_HUMANA | SINTETIZANDO_NXN
SINTETIZANDO_NXN
  → VERSAO_CONGELADA
REDIGINDO
  → VERSAO_CONGELADA
VERSAO_CONGELADA
  → DELIBERANDO
  → DECIDINDO
  → CONGELANDO_VOTOS_FINAIS
      → APURANDO_RESULTADO_E_FUNDAMENTOS
          ├→ DECISAO_COLEGIADA_FORMADA
          └→ SEM_RATIO_UNIFICADA
  → AVALIANDO
      ├→ CORRIGINDO → REDIGINDO
      ├→ AUDITANDO
      └→ GERANDO_CANDIDATOS_FINAIS
          → AVALIANDO_CANDIDATOS_CEGAMENTE
          → AGUARDANDO_ESCOLHA_HUMANA
              ├→ CANONICO_SELECIONADO → VERSAO_CONGELADA
              └→ SINTETIZANDO → VERSAO_CONGELADA
AUDITANDO
  → APROVADO | SEM_PROGRESSO | BLOQUEADO | ESGOTADO | CANCELADO | LIMITE_OPERACIONAL
```

Executar essa máquina no escopo de um `artefato_id`. No pacote, o coordenador acrescenta:

```text
ITENS_OBRIGATORIOS_APROVADOS
  → CONGELANDO_MANIFESTO
  → AUDITANDO_CONSISTENCIA_CONJUNTA
      ├→ PACOTE_APROVADO
      ├→ REABRINDO_ITENS_AFETADOS
      └→ PACOTE_NAO_APROVADO
```

Regras de transição:

- `AGUARDANDO_CONFIRMACAO` não chama modelos nem cria run.
- `VERSAO_CONGELADA` exige `tentativa_atual`, `versao_atual` e `artefato_sha256_atual`.
- todo estado por artefato exige `artefato_id`; o alias implícito `principal` é aceito em runs simples antigos.
- estados N×N só existem quando `perfil = ensemble_nxn_v1`; cada transição exige manifests e hashes da tentativa/ciclo correntes.
- `SELECIONANDO_NXN` nunca transita diretamente para `APROVADO`; seleção ou síntese produz `canonico_selecionado` e segue aos gates normais.
- `DELIBERANDO` e `DECIDINDO` podem ser omitidos quando `estrategia_da_equipe.tipo = nenhuma`; os estados colegiados só existem quando `formacao_decisao_colegiada.ativa = true`.
- a proclamação congela os votos finais, a opção vencedora, as adesões por proposição, a ratio possível, as opiniões separadas e seus hashes; resultado colegiado formado ainda segue para `AVALIANDO`.
- `SEM_RATIO_UNIFICADA` só pode prosseguir quando `ratio_exigida = false`; quando verdadeira, abre correção, nova deliberação ou decisão humana, sem alegar consenso.
- `DELIBERANDO`, `DECIDINDO`, estados colegiados, `AVALIANDO` e `AUDITANDO` sempre referenciam o mesmo hash.
- `CORRIGINDO` invalida os gates do hash corrente; a saída volta a `REDIGINDO`, incrementa a tentativa e recebe novo hash.
- `CORRIGINDO` só pode voltar a `REDIGINDO` quando `versao_atual < min(tentativas_maximas, 20)`; no teto, transita para `ESGOTADO` sem gerar outra minuta.
- os estados de candidatos finais só existem em `consolidacao_final.modo = dupla_cega` ou `multipla_cega`; a comparação nunca transita sozinha para aprovação.
- `AGUARDANDO_ESCOLHA_HUMANA` só avança mediante escolha explícita ou pedido explícito de síntese.
- após escolha ou síntese, marcar no estado `consolidacao_final_concluida = true`; quando esse hash voltar a `AVALIANDO`, seguir para `AUDITANDO`, sem gerar novas candidatas finais.
- `SINTETIZANDO` sempre cria novo hash e volta ao gate deliberativo antes da auditoria.
- `AUDITANDO` só é alcançado quando avaliação e gate deliberativo forem favoráveis para o hash final exato.
- nenhum estado terminal de falha pode ser convertido em `APROVADO` por ausência de resposta.
- `PACOTE_APROVADO` exige manifesto do conjunto exato de hashes; qualquer alteração volta a `CONGELANDO_MANIFESTO` e reabre os itens materialmente afetados.

Registrar eventos equivalentes a `configuracao_confirmada`, `versao_congelada`, `candidato_alternativo_registrado`, `debate_concluido`, `decisao_emitida`, `resposta_responsavel_registrada`, `avaliacao_emitida`, `correcao_solicitada`, `nova_versao`, `candidatos_finais_congelados`, `comparacao_cega_emitida`, `candidato_escolhido`, `sintese_solicitada`, `auditoria_emitida` e `execucao_encerrada`. No perfil N×N, registrar também os eventos definidos em `ensemble-nxn.md`. Aceitar `resposta_redator_registrada` de runs antigos. Esses eventos pertencem ao histórico local do run no Claude Code ou Codex.

## Contadores

Manter separadamente por `artefato_id`, além dos totais do pacote:

- `tentativa_atual` e `tentativas_maximas`;
- `versao_atual`, `versoes_maximas_por_artefato` e `artefato_sha256_atual`;
- por tentativa: sugestões aceitas, parciais, rejeitadas e resolvidas;
- por tentativa: `rodadas_usadas` e `rodadas_por_tentativa`;
- por rodada: `fase`, participantes convocados, respostas válidas e manifestações ausentes;
- total do run: `rodadas_usadas_total` e `rodadas_maximas_teoricas`;
- por participante e por tentativa: `criticas_usadas`, `replicas_usadas`, `revisoes_usadas`;
- `avaliacoes_consecutivas_de_consenso`;
- `artefato_sha256_consensuado`;
- `artefato_sha256_decidido`, quando houver decisor;
- quando colegiado: método de apuração, cadeiras e votos/cédulas válidos, opção vencedora ou derivada, adesões por proposição essencial, limiar aplicável, `ratio_status`, hashes da opinião principal e das opiniões separadas; no v2, questões e derivação congeladas, coalizões por questão, coalizão do pacote, resultado por cadeira, paradoxo doutrinário e confirmação híbrida;
- `artefato_sha256_final`, `candidatos_sha256` e estado de cada candidato;
- objeções abertas, aceitas, parciais, rejeitadas com evidência e resolvidas no ledger;
- chamadas externas por papel e modelo.
- no perfil N×N: N declarado e efetivo, candidatos, pareceres esperados/recebidos, células ausentes, ciclos, réplicas, revisões, matriz efetiva, juiz, seleção e chamadas estimadas/reais.

Uma fase coordenada incrementa a rodada global uma vez, ainda que várias cadeiras respondam em paralelo. Cada participante pode emitir uma crítica, uma réplica e uma revisão por ciclo confirmado; assim, o teto de cada um desses contadores individuais é igual ao número de ciclos da tentativa. Um ciclo completo consome ao menos três rodadas globais; validar essa relação antes de congelar a configuração. Registrar também os totais do run para transparência. Uma nova versão reinicia os contadores individuais da deliberação, não os totais acumulados.

## Compatibilidade de execução

O executor deve resolver:

1. modo normal: cada cadeira de `painel_avaliacao`; se ausente, `avaliador` → `motor` → padrão;
2. modo cego: cada cadeira de `painel_avaliacao_cega`; se ausente, `auditor` → `avaliador` → `motor` → padrão;
3. redator: `redator` → `escritor` → host;
4. publicador iterativo: em `publicacao_compartilhada`, usar o `publicador_da_proxima_versao` autorizado; em `consolidador_designado`, usar o consolidador; caso contrário, usar o redator resolvido;
5. modelo/esforço: objeto do papel → variável de ambiente específica → padrão do CLI.
6. perfil N×N: `ensemble_nxn.produtores`, `ensemble_nxn.revisores` e `ensemble_nxn.selecao.juiz`; não derivar todas as cadeiras dos campos legados.
7. seat/rota: resolver primeiro a escolha explícita do papel e depois `~/.agents/multiagent-manifest.json`; o manifesto entra acima do padrão do CLI e abaixo do modelo explicitamente pedido, sem alterar sua identidade. Registrar a procedência e pausar se a combinação violar rota estrita.

No painel misto, cada cadeira mantém próprio CLI, modelo, provedor, esforço, lente, identidade e sessão. O executor não pode aplicar o `avaliador` legado a todas as cadeiras quando `painel_avaliacao` existir.

Variáveis de ambiente podem substituir a configuração somente para diagnóstico explícito e devem aparecer na procedência do resultado.

## Critério de sucesso

Painel externo e auditoria cega precisam, cada um, satisfazer:

- média geral maior ou igual a `alvo`;
- todas as medianas por critério maiores ou iguais a `piso`;
- maioria de vereditos recalculados como aprovado;
- nenhum erro factual crítico sem resposta.

No perfil `debate_agents_v1`, o painel declarado é 3. O agregado só é confiável quando a política de independência e o quórum mínimo forem atendidos. Uma redução autorizada deve aparecer no veredito e nunca pode converter falta de maioria em aprovação.

No perfil `ensemble_nxn_v1`, exigir também a matriz declarada concluída ou a degradação autorizada e rotulada, todos os candidatos/revisões vinculados aos hashes corretos, seleção registrada e nenhuma aprovação herdada do juiz do ensemble. Uma matriz N×M não pode ser relatada como N×N.

Além disso, o hash exato do artefato entregue precisa satisfazer o modo deliberativo efetivo: consenso estável em `estrito`; consenso ou decisão final que resolva os bloqueios julgáveis em `com_decisor`; parecer e dissensos registrados em `consultivo`; gate dispensado em `desativado + nenhum`. Quando configurado, o decisor deve autorizar o mesmo hash. Alteração posterior, ainda que pequena, invalida deliberação, decisão e avaliação anteriores.

Quando `formacao_decisao_colegiada.ativa = true`, exigir contrato coerente com o método: `decisao_colegiada_v1` para `global`; `decisao_colegiada_v2` para `analitico` ou `hibrido`. Validar no mesmo hash quórum, regra de resultado, votos ou cédulas finais únicos, adesões aos fundamentos, política de opiniões separadas, proclamação e gate colegiado. No v2, exigir também questões, tabela e hashes congelados, apuração por questão, derivação, comparação com derivações individuais e, no híbrido, confirmação bloqueante. Se `ratio_exigida = true`, somente `ratio_status = unificada` fecha o gate. `decisao_por_maioria`, `decisao_por_maioria_qualificada`, `somente_resultado` e dispositivo derivado sem coalizão de pacote nunca recebem o rótulo `consenso`. A decisão formada é portão intermediário; não promove o arquivo a `canonico_aprovado` sem os demais gates.

Também são obrigatórios: nenhum bloqueio material aberto no ledger; exatamente um `canonico_aprovado` por artefato; nenhuma candidata tratada como aprovada por herança; e, no modo duplo, escolha humana registrada ou síntese explicitamente solicitada. A comparação entre candidatas não substitui os gates do arquivo final escolhido ou sintetizado. Em pacote, exigir todos os itens obrigatórios aprovados e o gate conjunto sobre o manifesto exato.

O resultado não é sucesso quando o executor falha, o teto é atingido, um gate efetivamente exigido não fecha, o auditor não roda ou a separação prometida não pode ser comprovada. O consenso e a decisão resolvem desacordo material durante o loop sem substituir os demais gates configurados.
