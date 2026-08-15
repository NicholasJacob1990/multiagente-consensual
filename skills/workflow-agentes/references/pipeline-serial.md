# Pipeline serial arbitrário

Usar `pipeline_serial_v1` quando a saída de cada etapa for a entrada obrigatória da seguinte.

## Estrutura

```json
{
  "etapas": [
    {"id": "A", "agente": "claude-opus-redator", "tipo": "transformar", "entrada": ["snapshot"], "saida": "rascunho"},
    {"id": "B", "agente": "gpt-codex-critico", "tipo": "avaliar", "entrada": ["A"], "saida": "parecer"},
    {"id": "C", "agente": "gemini-pro-consolidador", "tipo": "transformar", "entrada": ["A", "B"], "saida": "candidato"},
    {"id": "D", "agente": "grok-auditor", "tipo": "gate", "entrada": ["C"], "saida": "auditoria"}
  ],
  "politica_handoff": "hash_e_contrato",
  "falha_etapa": "pausar",
  "repeticoes_por_etapa": 1
}
```

Exigir IDs únicos, pelo menos uma etapa e ordem fechada antes da execução. Tipos: `produzir`, `transformar`, `avaliar`, `gate`, `selecionar`, `publicar`. Publicação ou ação externa exige autorização própria.

## Execução

1. Congelar entrada e contrato da etapa A.
2. Executar uma etapa por vez.
3. Validar formato, hash e critérios de saída antes do handoff.
4. Entregar à etapa seguinte somente as entradas declaradas.
5. Se uma etapa falhar, não avançar. Repetir conforme limite ou pausar.
6. Se uma etapa alterar um artefato, gerar novo hash e manter a versão anterior.
7. Encerrar somente quando a última saída for válida.

Um avaliador não edita por consequência do papel. Para o padrão redator → crítico → consolidador → auditor, B emite parecer, C produz a versão e D apenas audita.

## Reentrada e ramificação

Reexecutar uma etapa invalida todas as saídas posteriores dependentes. Se o fluxo precisar de ramos paralelos ou joins, migrar para `dag_assincrono_v1`; não simular DAG por ordem textual ambígua.

## Resultado

Entregar tabela de handoffs com etapa, agente/modelo, hashes de entrada/saída, tentativas, duração, estado e motivo. Distinguir conclusão do pipeline de aprovação do artefato.

