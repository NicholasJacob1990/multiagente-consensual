# Roteamento adaptativo de modelos

Usar `roteamento_adaptativo_v1` para escolher ou trocar modelos por métricas observadas, restrições e orçamento. O roteador atua entre tarefas ou tentativas; nunca troca o modelo no meio de uma resposta.

## Estrutura

```json
{
  "pool": [
    {"id": "claude-opus", "cli": "claude", "modelo": "claude-opus-5", "familia": "anthropic/claude"},
    {"id": "gpt-codex", "modelo": "opencode/gpt-5.3-codex", "familia": "openai/gpt"},
    {"id": "gemini", "modelo": "gemini-3.7-flash-high", "familia": "google/gemini"}
  ],
  "restricoes": {
    "capacidades": ["texto", "tools"],
    "provedores_permitidos": ["anthropic", "opencode", "google"],
    "max_custo_tarefa": null,
    "max_latencia_ms": null,
    "diversidade_para_auditoria": true
  },
  "pesos": {"qualidade": 0.55, "custo": 0.15, "latencia": 0.15, "falha": 0.10, "diversidade": 0.05},
  "exploracao": 0.1,
  "min_amostras": 3,
  "janela": 20,
  "fallback": "pausar",
  "atualizar_apos_gate": true
}
```

## Decisão

1. Filtrar por restrições duras, disponibilidade, autenticação, permissão e modalidade.
2. Normalizar métricas observadas em 0–1; manter `desconhecido` quando ausentes.
3. Calcular:
   ```text
   score = wq*qualidade + wd*diversidade - wc*custo - wl*latencia - wf*falha
   ```
4. Aplicar exploração somente dentro da taxa e do pool confirmados.
5. Registrar ranking, métricas, pesos, modelo escolhido e razão.
6. Fixar a escolha para a tarefa/tentativa.
7. Atualizar métricas somente após resultado verificável; não usar autoavaliação isolada como qualidade.

Cold start usa priors explicitamente marcados ou distribuição equilibrada. Não tratar ausência de preço como custo zero.

`pesos` e `metricas` são objetos JSON. Os pesos devem conter exatamente `qualidade`, `custo`,
`latencia`, `falha` e `diversidade`, somando 1. Cada item do pool pode omitir métricas conhecidas
para receber o prior neutro, mas não pode declarar chaves desconhecidas, vazias, booleanos,
`NaN`, `Infinity` ou valores fora de 0–1.

## Troca e fallback

Trocar entre tentativas quando houver falha, regressão, violação de teto, degradação persistente ou exploração confirmada. Uma troca invalida continuidade de sessão e precisa receber o manifesto necessário.

Fallback `pausar` é padrão. Uma lista ordenada pode ser autorizada; cada uso gera evento. Nunca introduzir modelo fora do pool. Para auditoria, impedir o mesmo modelo/família do produtor quando a política exigir diversidade.

## Antimanipulação

Separar roteador, executor e avaliador quando o risco justificar. Congelar rubrica e pesos antes dos resultados. Detectar poucos dados, drift, custo desatualizado e métricas correlacionadas. Não otimizar somente nota média se piso, fatos críticos ou segurança falharem.

## Resultado

Entregar candidatos elegíveis e excluídos, métricas observadas e desconhecidas, normalização, score, exploração/fallback, modelo escolhido, duração da validade da decisão e desempenho posterior. Roteamento bem-sucedido não equivale a aprovação do artefato.
