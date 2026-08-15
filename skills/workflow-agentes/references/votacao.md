# Votação multiagente

Usar `votacao_multiagente_v1` para agregar preferências ou estimativas. Fixar método, eleitores, candidatas, tratamento de abstenção, empates e fallback antes dos votos.

## Borda

Cada eleitor ordena M candidatas. A primeira recebe M−1 pontos, a segunda M−2 e a última 0. Somar pontos; maior total vence.

Configuração:

```json
{
  "metodo": "borda",
  "candidatos": ["A", "B", "C"],
  "eleitores": ["claude-opus-juiz", "gpt-codex-juiz", "gemini-pro-juiz"],
  "cedulas_incompletas": "rejeitar",
  "empate": "auditor_holdout",
  "ocultar_autoria": true
}
```

Rejeitar duplicatas e desconhecidos. Se cédulas incompletas forem permitidas, fixar antes se itens omitidos empatam na última posição ou recebem zero.

## Condorcet

Comparar cada par. Um vencedor Condorcet vence cada outro candidato por maioria direta. Registrar matriz e margens.

```json
{
  "metodo": "condorcet",
  "candidatos": ["A", "B", "C"],
  "eleitores": ["claude-opus-juiz", "gpt-codex-juiz", "gemini-pro-juiz"],
  "ciclo": "sem_vencedor",
  "fallback": null
}
```

Não inventar vencedor quando houver ciclo. Fallback como Borda, Copeland, Schulze, juiz holdout ou escolha humana precisa ser confirmado previamente; se não houver, devolver `sem_vencedor_condorcet`.

## Delphi

Delphi não é votação por ranking. É consulta iterativa, anônima e controlada:

1. cada especialista responde e estima confiança sem ver os demais;
2. facilitador publica mediana, intervalo interquartil, argumentos e evidências anonimizados;
3. especialistas revisam posição com justificativa;
4. repetir até estabilidade, limite ou ausência de progresso;
5. registrar convergência e dissenso, sem forçar unanimidade.

```json
{
  "metodo": "delphi",
  "especialistas": ["claude-opus", "gpt-codex", "gemini-pro"],
  "rodadas_maximas": 4,
  "estabilidade_exigida": 2,
  "limiar_mediana": 8.5,
  "limiar_iqr": 1.0,
  "anonimo": true
}
```

Estabilidade exige os limiares por duas rodadas consecutivas. Opinião minoritária com risco material permanece no relatório.
O runtime também aceita `estabilidade` como alias legado, mas rejeita valores divergentes quando os
dois campos aparecem. Estabilidade menor que 2, booleanos e números não finitos (`NaN`/`Infinity`)
são inválidos.

O runtime recebe as rodadas congeladas e calcula mediana, intervalo interquartil, estabilidade e
dissensos sem alegar aprovação:

```text
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/workflow-agentes/scripts/protocol_engine.py" vote --method delphi <rodadas.json>
```

## Integridade

Cada cédula referencia o hash exato das candidatas e fica congelada. Não aceitar voto do mesmo agente duplicado por sessões múltiplas salvo regra explícita. Modelo compartilhado reduz diversidade e deve ser informado.

Usar:

```text
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/workflow-agentes/scripts/protocol_engine.py" vote --method borda <cedulas.json>
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/workflow-agentes/scripts/protocol_engine.py" vote --method condorcet <cedulas.json>
```

A votação seleciona ou descreve convergência; não constitui consenso deliberativo nem aprovação de qualidade.
