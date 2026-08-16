# Protocolo do perfil Ensemble N×N

## Sumário

1. Contrato e padrões
2. Resolução das cadeiras
3. Matriz cega
4. Ciclo profundo
5. Seleção e canônico
6. Repetição no loop
7. Artefatos e ledger
8. Adaptadores
9. Falhas, custo e sucesso

## 1. Contrato e padrões

Ativar somente por pedido explícito. Gravar `perfil = ensemble_nxn_v1`; aceitar `ensemble_nxn` como alias natural.

```json
{
  "perfil": "ensemble_nxn_v1",
  "estrategia_da_equipe": {
    "tipo": "ensemble_nxn",
    "politica_por_tentativa": "sempre"
  },
  "ciclo_de_melhoria": {"tipo": "ate_criterios", "tentativas": 3},
  "ensemble_nxn": {
    "ativo": true,
    "n": 3,
    "profundidade": "profundo",
    "produtores": [
      {"id": "produtor-1", "cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic", "sessao": "sessao-propria"},
      {"id": "produtor-2", "cli": "codex", "modelo": "gpt-5.6-sol", "provedor": "openai", "sessao": "sessao-propria"},
      {"id": "produtor-3", "cli": "gemini", "modelo": "gemini-3.7-flash-high", "provedor": "google", "sessao": "sessao-propria"}
    ],
    "revisores": [
      {"id": "revisor-1", "cli": "claude", "modelo": "claude-opus-5", "provedor": "anthropic", "sessao": "sessao-revisao"},
      {"id": "revisor-2", "cli": "codex", "modelo": "gpt-5.6-sol", "provedor": "openai", "sessao": "sessao-revisao"},
      {"id": "revisor-3", "cli": "gemini", "modelo": "gemini-3.7-flash-high", "provedor": "google", "sessao": "sessao-revisao"}
    ],
    "matriz": {
      "tipo": "nxn_completa_cega",
      "autorrevisao_cega": true,
      "pareceres_esperados_por_ciclo": 9,
      "anonimizar_autores": true,
      "mesmo_snapshot": true
    },
    "ciclos": 2,
    "ciclos_maximos_recomendados": 6,
    "ciclos_maximos_excepcionais": 12,
    "rodadas_minimas": 6,
    "rodadas_maximas_recomendadas": 18,
    "rodadas_maximas_motor": 36,
    "fases_por_ciclo": ["critica", "replica", "revisao"],
    "selecao": {
      "modo": "melhor_candidato_por_juiz",
      "juiz": {"cli": "opencode", "modelo": "modelo-confirmado", "provedor": "provedor-confirmado", "sessao": "nova-sessao"},
      "pode_sintetizar": false,
      "aprova_automaticamente": false
    },
    "adaptador": "auto",
    "falha_de_cadeira": "pausar",
    "quorum_produtores": 3,
    "quorum_revisores": 3,
    "confirmacao_reforcada_acima_de_n": 5
  },
  "debate": {
    "modo": "consenso_por_tentativa",
    "reexecutar_a_cada_nova_versao": true,
    "estabilidade": 2
  },
  "painel": 3,
  "alvo": 8.5,
  "piso": 7.0,
  "painel_auditoria": 1
}
```

Padrões: N=3 depois de confirmação, 2 ciclos, ao menos 6 rodadas, 3 tentativas, matriz completa cega, consenso após seleção, painel 3, alvo 8,5, piso 7 e auditoria cega 1. `rapido` significa 1 ciclo e ao menos 3 rodadas; `profundo`, 2 ciclos e ao menos 6; `maximo`, 6 ciclos e 18 rodadas. Configuração explícita prevalece se respeitar a relação de três rodadas por ciclo e o teto excepcional de 36 rodadas/12 ciclos.

## 2. Resolução das cadeiras

- Uma lista explícita é fechada. Não acrescentar host ou modelo.
- Sem lista, propor três cadeiras elegíveis e aguardar confirmação.
- `n` deve coincidir com o número de produtores e de revisores no modo N×N estrito.
- Permitir conjuntos diferentes de produtores e revisores, desde que ambos tenham N cadeiras.
- Separar agente, CLI, modelo, provedor, papel, lente e sessão.
- Modelos iguais em sessões diferentes são cadeiras distintas, mas não provam diversidade de modelo.
- Preferir juiz fora das sessões de produção e revisão. Sobreposição deve reduzir a declaração de independência.

Se produtores = N e revisores = M com N diferente de M, executar somente após confirmação como `ensemble_nxm`. Mostrar a matriz N×M e não usar o rótulo N×N.

## 3. Matriz cega

Cada produtor recebe o mesmo briefing, fontes, rubrica, limites e `snapshot_sha256`, mas não recebe candidatos alheios durante a geração. Persistir cada candidato completo com `candidate_id`, autor, sessão, `base_sha256` e `sha256`.

Antes da revisão, substituir autoria por rótulos estáveis `Candidato A`, `B`, `C` etc. Cada revisor recebe todos os candidatos na mesma ordem sorteada ou contrabalanceada e devolve um parecer separado por candidato. Não revelar o mapeamento até todas as revisões do ciclo estarem congeladas.

Com `autorrevisao_cega = true`, cada cadeira revisa também o candidato que produziu sem saber qual é; isso gera N² pareceres. Com `false`, omitir a diagonal, gerar N×(N−1) pareceres e registrar `matriz_sem_diagonal`, não `nxn_completa`.

Cada parecer deve conter: candidato e hash, acertos, bloqueios, erros factuais, nota por critério, crítica principal, alteração proposta, evidência, condição para aprovação, confiança e identidade do revisor no manifesto privado.

## 4. Ciclo profundo

Um ciclo N×N tem três fases globais:

1. `critica`: N revisores produzem a matriz de pareceres; uma resposta em lote conta como uma crítica usada por revisor, embora gere N registros.
2. `replica`: cada produtor recebe somente o agregado anonimizado relativo ao próprio candidato e responde ponto por ponto.
3. `revisao`: cada produtor entrega nova versão completa do próprio candidato, com novo hash.

Executar 2 ciclos e ao menos 6 rodadas globais no padrão profundo. Recomendar no máximo 6 ciclos e 18 rodadas globais; permitir extensão gradual, justificada e confirmada, até o teto excepcional de 12 ciclos e 36 rodadas globais. Cada cadeira pode emitir uma crítica, uma réplica e uma revisão por ciclo confirmado, portanto seus três contadores individuais têm como limite o número de ciclos da tentativa. Validar `rodadas >= 3 × ciclos` antes da confirmação. Congelar a matriz e os hashes antes do ciclo seguinte. Parecer de base obsoleta não pode ser reaproveitado.

## 5. Seleção e canônico

Modos permitidos:

- `melhor_candidato_por_juiz`: juiz independente ranqueia e escolhe um candidato existente;
- `selecao_humana`: preservar comparativo e aguardar escolha;
- `sintese_por_consolidador`: somente por pedido explícito; o responsável de `consolidacao_iterativa` cria novo candidato completo;
- `sintese_pelo_juiz`: somente quando explicitamente confirmado; registrar o juiz como autor do novo candidato.

O juiz recebe candidatos anonimizados, matriz, réplicas, rubrica e evidências. Deve preservar dissensos e pode retornar `nenhum_apto`. Escolha, maioria, nota ou síntese não aprovam o artefato. A versão selecionada ou sintetizada passa a `canonico_selecionado`, recebe hash e segue para consenso, painel e auditoria.

Exatamente um hash pode chegar a `canonico_aprovado`. Todos os demais continuam candidatos auditáveis.

## 6. Repetição no loop

Aplicar `estrategia_da_equipe.politica_por_tentativa`:

- `sempre`: repetir toda a geração e matriz em cada nova tentativa;
- `se_necessario`: repetir diante de mudança material, bloqueador ou solicitação do painel;
- `apenas_primeira`: usar N×N na primeira tentativa e depois a política normal de consolidação iterativa;
- `nenhum`: inválido com perfil N×N ativo; equivale a desativar o perfil após nova confirmação.

Qualquer correção, escolha ou síntese cria novo hash. Consenso, decisão, notas e auditoria de outro hash ficam inválidos. O feedback externo da tentativa anterior entra no snapshot seguinte, sem revelar identidades cegas desnecessárias.

## 7. Artefatos e ledger

Usar:

```text
candidatos/ensemble/tentativa-<t>/ciclo-<c>/<candidate_id>.md
revisoes/ensemble/tentativa-<t>/ciclo-<c>/<reviewer_id>/<candidate_id>.json
ledger/ensemble.jsonl
```

Registrar eventos `ensemble_iniciado`, `candidato_gerado`, `matriz_congelada`, `parecer_emitido`, `replica_emitida`, `candidato_revisado`, `selecao_ensemble_emitida`, `sintese_ensemble_emitida` e `ensemble_encerrado`.

Cada registro deve conter tentativa, ciclo, fase, `snapshot_sha256`, `candidate_id`, `base_sha256`, `sha256`, autor privado, rótulo cego, revisor, sessão, estado e timestamps. O relatório final mostra autoria; os prompts cegos não.

## 8. Adaptadores

`adaptador = auto` pode selecionar:

- `a2a_mesh`: somente para código com exatamente Codex, Claude e Gemini quando o MCP estiver disponível;
- `cli_adapter`: para qualquer combinação confirmada de Claude, Codex, Gemini, Antigravity, Grok e OpenCode;
- adaptador equivalente previamente configurado, sem substituição silenciosa.

O A2A Mesh aceita subconjunto configurável de Codex, Claude, Gemini e Grok 4.6 pela rota explicitamente selecionada (Cursor por padrão ou CLI oficial xAI), até 12 ciclos de revisão e qualquer peer elegível como juiz. O executor honra `agents`; não acrescenta participantes omitidos silenciosamente. Quando o adaptador não comportar os ciclos confirmados, não reduzir a configuração: usar orquestração direta ou pausar e explicar a limitação. Se o A2A não devolver candidatos, pareceres e hashes individualizados, registrar `rastreabilidade_reduzida` e não usá-lo em execução que exija auditoria integral; preferir orquestração direta.

## 9. Falhas, custo e sucesso

Por tentativa, estimar chamadas de modelo como:

```text
N gerações + C × (N² críticas + N réplicas + N revisões) + 1 seleção + painel
```

Se réplica e revisão forem combinadas por um adaptador, registrar a fórmula e a contagem efetiva. Para N=3, C=2 e painel=3, a estimativa-base é 37 chamadas antes do consenso adicional e da auditoria final.

Acima de N=5, exigir confirmação reforçada com estimativa de chamadas, custo/tempo e limites operacionais. Nunca reduzir N, ciclos, matriz ou quórum silenciosamente. Se uma cadeira falhar, pausar por padrão; redução autorizada deve registrar a matriz efetiva e não pode conservar o rótulo estrito se as dimensões mudarem.

Sucesso exige, sobre o mesmo hash final do artefato: matriz concluída conforme configuração, nenhum bloqueio material aberto, consenso ou gate deliberativo permitido, alvo e piso no painel externo, auditoria cega favorável e exatamente um canônico aprovado para esse `artefato_id`. O juiz do ensemble não substitui nenhum desses gates.
