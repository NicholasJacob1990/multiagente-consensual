# Grafo/DAG assíncrono

Usar `dag_assincrono_v1` para tarefas com dependências ramificadas, ondas paralelas e joins.

## Estrutura

```json
{
  "nos": [
    {"id": "pesquisa", "agente": "kimi-pesquisador", "saida": "fontes"},
    {"id": "arquitetura", "agente": "claude-opus", "saida": "plano"},
    {"id": "implementacao", "agente": "gpt-codex-executor", "depende_de": ["pesquisa", "arquitetura"]},
    {"id": "auditoria", "agente": "gemini-pro-auditor", "depende_de": ["implementacao"]}
  ],
  "arestas": [
    ["pesquisa", "implementacao"],
    ["arquitetura", "implementacao"],
    ["implementacao", "auditoria"]
  ],
  "joins": {"implementacao": "todos"},
  "max_paralelo": 3,
  "falha_no": "pausar_dependentes"
}
```

Exigir IDs únicos, arestas referindo nós existentes e grafo acíclico. `protocol_engine.py plan` calcula ondas topológicas e rejeita ciclos.

## Execução

1. Congelar o grafo e o snapshot.
2. Marcar nós sem dependências como prontos.
3. Executar até `max_paralelo` nós prontos em sessões separadas.
4. Persistir cada saída antes de liberar dependentes.
5. Aplicar join `todos`, `quorum:k` ou `qualquer` conforme confirmação. `qualquer` cancela ou ignora excedentes somente se isso estiver autorizado.
6. Propagar falha como `pausar_dependentes`, `falhar_subgrafo` ou fallback previsto.
7. Recalcular apenas o subgrafo descendente quando uma saída-base mudar.

Registrar `onda_iniciada`, `no_liberado`, `join_satisfeito`, `join_impossivel` e `subgrafo_invalidado`.

## Assincronia e segurança

Concorrência é uma otimização, não mudança semântica. Se o host executar serialmente, manter a mesma onda lógica. Nós paralelos não compartilham sessão mutável; comunicar apenas por artefatos congelados.

Ações externas precisam de idempotência por nó. Cancelar um nó não desfaz efeitos já produzidos; registrar compensação quando aplicável.

## Resultado

Entregar grafo efetivo, ondas, caminho crítico observado, nós ignorados/cancelados, joins, falhas, hashes e artefatos terminais. Múltiplos terminais permanecem candidatos até uma regra de seleção explícita.

