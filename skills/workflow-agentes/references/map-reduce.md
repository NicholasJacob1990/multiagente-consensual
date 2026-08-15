# Map-reduce formal

Usar `map_reduce_v1` quando a entrada puder ser particionada em unidades relativamente independentes e combinada por uma operação explícita.

## Estrutura

```json
{
  "entrada": "corpus",
  "particionamento": {
    "tipo": "por_arquivo",
    "itens": ["a", "b", "c"],
    "sobreposicao": 0,
    "manifesto_cobertura": true
  },
  "mappers": ["kimi", "deepseek", "qwen-coder"],
  "funcao_map": "extrair_achados_com_evidencia",
  "chave_shuffle": "tema",
  "reducers": ["claude-opus-consolidador"],
  "funcao_reduce": "deduplicar_e_sintetizar",
  "aridade_reduce": 8,
  "auditor_cobertura": "gemini-pro-auditor"
}
```

## Fases

1. **Partition:** produzir shards imutáveis e manifesto que prove cobertura, exclusões e sobreposição.
2. **Map:** aplicar o mesmo contrato a cada shard; cada achado referencia shard, localização e hash.
3. **Shuffle:** agrupar por chave determinística; itens sem chave vão para `nao_classificados`.
4. **Combine opcional:** reduzir localmente somente se a operação for associativa ou a perda estiver autorizada.
5. **Reduce:** combinar grupos preservando procedência, conflitos e contagens.
6. **Final reduce:** gerar candidata completa.
7. **Audit:** verificar cobertura, duplicação, perda, conflitos e amostra contra fontes.

Não usar map-reduce quando uma unidade depende fortemente da interpretação sequencial de outra; usar pipeline ou DAG.

## Falhas e reexecução

Falha de shard não pode ser ocultada. Repetir o shard ou terminar com cobertura incompleta explicitamente marcada. Nova versão de shard invalida somente grupos dependentes. Não recalcular mapas válidos de hashes idênticos.

Reducers não podem apagar opiniões minoritárias materiais, exceções ou referências para obter texto uniforme. Deduplicação exige chave ou justificativa.

## Resultado

Entregar números de itens, shards, maps esperados/recebidos, cobertura, duplicatas, não classificados, grupos, árvore de redução, perdas autorizadas, hashes e candidata final. Auditoria do map-reduce não substitui auditoria final do loop.

