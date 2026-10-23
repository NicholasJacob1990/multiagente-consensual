# Módulos avançados de análise jurídica

Estes módulos complementam o grafo epistêmico e o gate neurossimbólico. Eles produzem recibos independentes, vinculados ao `case_id`, `artifact_id`, consultas, fontes e hashes aplicáveis. Use somente os módulos pertinentes ao trabalho; não transforme uma consulta simples em pacote completo.

Executor comum:

```bash
python3 "$HOME/.codex/skills/analise-juridica-epistemica/scripts/legal_analysis_controls.py" \
  <comando> entrada.json --out recibo.json
```

Comandos:

- `research-fusion` — pesquisa jurisprudencial e doutrinária;
- `precedent-factors` — comparação de casos e conceitos abertos;
- `strategy-tree` — estado processual, movimentos e cenários;
- `credibility-matrix` — apoio à avaliação probatória;
- `elicitation-queue` — perguntas para conhecimento tácito;
- `persuasion-gate` — preservação argumentativa e retórica.

Código `0` significa que o controle determinístico fechou. Código `2` significa recibo produzido com violações. Código `1` significa erro operacional ou entrada inválida. Um recibo conforme não declara correção jurídica substantiva.

## 1. Pesquisa com Jurisbase, QMD e ChromaDB

### Papéis das fontes

| Camada | Papel | Pode verificar fonte primária? |
|---|---|---|
| Jurisbase MCP | legislação, precedentes e decisões oficiais | sim, após leitura e conferência do item |
| QMD | notas, livros, pareceres, cadernos e descoberta semântica | não |
| ChromaDB local | enriquecimento vetorial da doutrina pesada | não |

QMD e ChromaDB geram pistas, fatores, vocabulário e referências a conferir. Nunca marcar seus resultados como `verified_primary`. Um precedente citado no acervo só se torna primário depois de localizado e lido no Jurisbase ou na fonte oficial correspondente.

### Preflight

1. Chamar `mcp__jurisbase__jurisbase_status` e, se necessário, `jurisbase_listar_fontes`. Se o banco não abrir ou a fonte não estiver coletada, registrar `status: unavailable|partial` e a razão. Uma falha de conexão encerra essa camada na tentativa corrente; não repetir chamadas idênticas.
2. Chamar `mcp__qmd__status`. Para cada tema, usar `mcp__qmd__query` com `intent` e combinação `lex` + `vec`; usar `hyde` quando o vocabulário for incerto. Recuperar os melhores documentos com `get` ou `multi_get`. Se a consulta não responder no limite operacional do host, registrar timeout e prosseguir sem alegar cobertura.
3. Consultar primeiro `mcp__acervo__acervo_status`. Se houver fatia vetorial pronta para a disciplina e memória suficiente, usar `mcp__acervo__acervo_buscar` com `modo: rrf`, `n` pequeno e a disciplina adequada. Esse MCP usa o índice `chroma_fatias` e expõe resultados BM25 e vetoriais. Se o MCP não estiver disponível naquela CLI, executar `busca_acervo.py check` do plugin `legal-br` e usar o script somente quando `pronto_vetorial` ou `pronto_rrf` for verdadeiro. O script legado consulta outro store (`.chroma_index`); seu estado não determina o estado do MCP `acervo`. Não reconstruir nenhum índice durante a pesquisa.

### Plano mínimo de consultas

Executar e registrar:

- busca de identidade para números, temas, súmulas e processos conhecidos;
- busca favorável (`stance: supports`);
- busca contrária ou de distinção (`stance: opposes`);
- variantes lexical e conceitual;
- recorte de tribunal, jurisdição e data;
- leitura integral dos candidatos que serão citados.

No Jurisbase, começar pelo acervo já indexado. Usar `ao_vivo: nunca` na primeira busca específica e `motor: auto`; coleta ao vivo só entra quando a finalidade exigir atualidade, a fonte estiver ausente e o fluxo possuir autorização operacional. Para item selecionado, usar `jurisbase_ler_decisao`, `ler_precedente` ou `ler_norma`, conforme o tipo.

### Bundle normalizado

```json
{
  "schema_version": "legal_research_bundle_v1",
  "query_id": "Q-001",
  "as_of": "2026-09-21",
  "requirements": {
    "primary_required": true,
    "negative_claim_requested": false,
    "adverse_search_required": true
  },
  "providers": [
    {
      "id": "jurisbase",
      "role": "primary",
      "status": "available",
      "coverage": {"complete": false, "sources_checked": ["STJ"]},
      "queries": [{"id": "j1", "stance": "supports", "text": "..."}],
      "results": [
        {
          "id": "decisao:123",
          "canonical_key": "jurisbase:decisao:123",
          "title": "...",
          "rank": 1,
          "source_kind": "decision",
          "verified_primary": true,
          "stance": "supports"
        }
      ]
    },
    {
      "id": "qmd",
      "role": "discovery",
      "status": "available",
      "coverage": {},
      "queries": [],
      "results": []
    }
  ]
}
```

`research-fusion` usa RRF com peso maior para a camada primária, deduplica por `canonical_key` e emite `verified`, `verified_no_hits`, `degraded`, `discovery_only` ou `unavailable`. Pesquisa negativa só é válida com cobertura primária explicitamente completa.

## 2. Conceitos abertos e precedentes por fatores

O agente extrai fatores materiais do caso e de precedentes primários já verificados. Não usar similaridade textual como substituto da comparação jurídica.

```json
{
  "schema_version": "precedent_factor_bundle_v1",
  "case_id": "CASO-1",
  "factors": [
    {"id": "F1", "value": "present", "weight": 3},
    {"id": "F2", "value": "unknown", "weight": 2}
  ],
  "precedents": [
    {
      "id": "P1",
      "verified_primary": true,
      "outcome": "supports",
      "factors": {"F1": "present", "F2": "absent"}
    }
  ]
}
```

O recibo expõe fatores coincidentes, distinções e desconhecidos, além do melhor caso favorável e contrário entre os verificados. O índice de similaridade é transparência de comparação, não probabilidade de êxito nem decisão automática.

## 3. Estratégia processual

Representar o estado processual por fatos já confirmados e grants existentes. Cada movimento declara pressupostos, autoridade, reversibilidade e respostas plausíveis.

```json
{
  "schema_version": "procedural_strategy_bundle_v1",
  "case_id": "CASO-1",
  "state": {"facts": ["prazo_aberto"], "grants": []},
  "objectives": [{"id": "O1", "priority": "must"}],
  "actions": [
    {
      "id": "A1",
      "preconditions": ["prazo_aberto"],
      "authority_required": true,
      "grant_id": null,
      "authority_owner": "cliente",
      "reversible": false,
      "responses": [{"id": "R1", "satisfies": ["O1"]}]
    }
  ]
}
```

O controle separa ações inviáveis, bloqueadas por autoridade, viáveis e robustas. Uma ação é robusta somente quando todos os cenários declarados preservam os objetivos `must`. Não inferir probabilidades.

## 4. Credibilidade e matriz probatória

Registrar evidências favoráveis, contrárias e neutras e avaliar dimensões separadas: consistência interna, corroboração, oportunidade de percepção, incentivo e cadeia de custódia.

O comando `credibility-matrix` identifica contradições e lacunas dimensionais. Ele nunca produz nota global de credibilidade nem veredito sobre mentira ou verdade. A apreciação humana permanece explícita.

## 5. Conhecimento tácito e elicitação

Converter lacunas em perguntas atribuídas a uma pessoa. Cada desconhecido declara:

- impacto: `low|medium|high|decisive`;
- quantidade de ramos estratégicos afetados (`branching`, 1–4);
- reversibilidade: `reversible|costly|irreversible`;
- facilidade de obtenção (`ease`, 1–4);
- efeito de permanecer sem resposta.

`elicitation-queue` ordena as perguntas por impacto decisório. O número produzido é prioridade operacional, não confiança nem probabilidade. Nunca inferir resposta do silêncio.

## 6. Persuasão e qualidade estilística

Antes da reescrita, congelar o mapa argumentativo. Cada entrada tem `id`, função (`thesis`, `fact`, `authority`, `rebuttal`, `request`), obrigatoriedade e fontes. A minuta devolve um manifesto dos IDs preservados e de qualquer afirmação nova.

`persuasion-gate` bloqueia:

- tese, objeção, ressalva ou pedido obrigatório removido;
- afirmação nova sem fonte;
- redação produzida contra hash-base diferente.

O gate confirma preservação do conteúdo, não excelência retórica. O revisor humano e o perfil forense controlam clareza, ênfase, ritmo e adequação ao destinatário.

## Uso proporcional

| Produto | Módulos mínimos |
|---|---|
| parecer fundamentado | pesquisa, fatores quando houver conceito aberto, elicitação e persuasão |
| petição ou recurso | pesquisa, fatores, estratégia, elicitação e persuasão |
| controvérsia probatória | acrescentar credibilidade |
| consulta simples | somente pesquisa e gate epistêmico, se necessário |

Cada módulo ativo deve produzir recibo. Alteração das fontes, do estado, dos fatores, do objetivo, do mapa argumentativo ou do artefato invalida apenas os recibos dependentes.

## Alcance dos recibos

Cada recibo inclui `input_sha256`, calculado dos bytes do bundle recebido. Guarde também o bundle, as respostas brutas dos provedores e os hashes das fontes lidas. `conforms: true` significa apenas que o controle descrito para aquele módulo passou sobre a entrada fornecida; não prova que o agente extraiu todos os fatos, que o índice estava atualizado ou que a tese jurídica é correta.

Em `research-fusion`, `verified_no_hits` refere-se somente aos tribunais, coleções, datas e consultas expressamente registrados como cobertos no bundle. Não autoriza a frase irrestrita “não existe precedente”. Uma busca contrária no QMD não substitui a busca contrária no provedor primário. Quando QMD e Jurisbase apontam ao mesmo `canonical_key`, o recibo preserva ambas as origens e usa os metadados do item primário verificado.

Em `precedent-factors`, `similarity` é a fração do peso total dos fatores do caso que coincide com o precedente; `coverage` indica quanto desse peso foi efetivamente comparável. Nenhum dos dois números é probabilidade de êxito. Um precedente sem fatores comparáveis não pode ser escolhido como melhor paradigma.

Em `persuasion-gate`, `claim_ids` é um manifesto elaborado por quem leu a minuta. O script confirma a consistência desse manifesto com o mapa congelado; a presença real e o alcance de cada tese no texto exigem conferência independente no documento exato. O gate epistêmico verifica o hash do artefato e o auditor examina o conteúdo.
