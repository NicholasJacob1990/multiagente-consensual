# Consulta ao Acervo Local (ChromaDB + qmd/Obsidian)

Protocolo de recuperação do acervo doutrinário/pessoal local, usado pelo agente
`analista-juridico` e pelas skills de pesquisa do plugin **legal-br**. O acervo
local complementa — **não substitui** — as fontes primárias (legislação via
senado, jurisprudência via brlaw/Firecrawl).

## Camadas de recuperação (ordem de prioridade)

### Camada 0 — MCP qmd nativo (SEMPRE disponível, 1º passo)

Use o servidor `qmd` já conectado no Claude Code. É local (`~/.cache/qmd`), não
depende de SSD externo. Cobre as coleções `acervo`, `livros`, `concursos` e
outras (notas, cadernos, doutrina indexada).

Ferramenta: `mcp__qmd__query` — combine sub-buscas léxica (BM25) e vetorial:

```
searches = [
  {type: "lex", query: "<termos exatos>"},
  {type: "vec", query: "<pergunta em linguagem natural>"}
]
intent   = "<o que você está procurando>"
collection = "acervo"   # ou "livros" / "concursos"; omita p/ buscar em todas
```

Recupere o conteúdo dos melhores hits com `mcp__qmd__get` / `mcp__qmd__multi_get`.

### Camada 1 — Script empacotado (best-effort, enriquecimento semântico)

Profundidade semântica sobre a **doutrina pesada** (livros, informativos,
pesquisas de examinadores) via ChromaDB, mais a opção de busca **híbrida**
(qmd-lexical + ChromaDB num só comando).

**Pré-condições** (degrade silenciosamente se faltar qualquer uma): acervo local configurado por `LEGALBR_ACERVO_RAW`, Ollama rodando (`nomic-embed-text`), `chromadb`
instalado no `python3` do sistema. O ChromaDB store vive em
o caminho definido por `LEGALBR_CHROMA_DIR`.

Entrypoint canônico (saída sempre em JSON):

```bash
# 1) Preflight — verifique disponibilidade ANTES de tentar buscar
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" check

# 2) Busca vetorial (ChromaDB) — doutrina/livros
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search \
  --consulta "repartição de receitas tributárias" -n 5

# 3) Busca híbrida (qmd-lexical + ChromaDB)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search \
  --modo hibrido --disciplina "Direito Financeiro" \
  --consulta "operações de crédito por antecipação de receita" -n 5
```

Se `check` retornar `pronto_vetorial: false` (ou o `search` trouxer
`"disponivel": false`), **não insista no script** — siga apenas com a Camada 0
(MCP qmd) e as fontes externas.

> Os scripts internos `indexar_vetorial.py` (ChromaDB direto) e `busca_hibrida.py`
> (saída legível para humano) também estão em `scripts/`; `busca_acervo.py` é o
> wrapper recomendado para uso pelo agente (preflight + JSON).

## Regra de degradação

1. Sempre rode a **Camada 0** (MCP qmd) primeiro — é local e confiável.
2. Tente a **Camada 1** (script) para enriquecer com doutrina. Se indisponível,
   apenas registre "acervo vetorial indisponível (SSD/Ollama)" e prossiga.
3. Só então parta para as fontes externas (senado/brlaw/Firecrawl).

## Como citar fontes do acervo local

Fontes do acervo são material de estudo/doutrina **não verificado em fonte
primária**. Cite o caminho do arquivo e rotule explicitamente:

```
[Acervo local — não verificado em fonte primária]
Arquivo: <ACERVO_RAW>/<arquivo>.md
Trecho: "<...>"
```

Nunca apresente um trecho do acervo como se fosse o texto oficial de uma lei,
súmula ou acórdão. Quando o acervo apontar uma tese/precedente, **confirme** o
dado na fonte primária (senado/brlaw/Firecrawl) antes de afirmar.
