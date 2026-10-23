---
name: busca-acervo
description: "Consulta o acervo doutrinario/pessoal LOCAL (notas e cadernos do Obsidian via qmd + doutrina/livros pesados via ChromaDB) e retorna os trechos mais relevantes com a origem de cada um. Use quando o usuario quiser buscar no acervo, no Obsidian, nos cadernos, na wiki, nos livros ou na doutrina local sobre um tema -- ou pedir 'pesquise no acervo', 'o que tenho sobre X', 'busca semantica na doutrina', 'consulta a base local'. Para pesquisa juridica completa com legislacao + jurisprudencia externa, use /pesquisa-juridica (que ja chama o acervo como passo 0)."
argument-hint: "<termo ou questao a buscar no acervo>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /busca-acervo -- Consulta ao Acervo Local

Buscar no acervo: @$1

Recupera os trechos mais relevantes do acervo doutrinario/pessoal **local** sobre o
tema, combinando duas camadas, e apresenta os resultados com a origem de cada
trecho. Nao busca em fontes externas (para isso, use `/pesquisa-juridica`).

**Importante**: Trechos do acervo sao material de estudo/doutrina **nao verificado
em fonte primaria**. Nao apresente um trecho do acervo como se fosse o texto oficial
de lei, sumula ou acordao -- confirme teses/precedentes na fonte oficial antes de
afirmar. Protocolo completo: `${CLAUDE_PLUGIN_ROOT}/references/acervo-local.md`.

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar, indexar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite/indexe trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Entender a consulta

Identifique o **termo/questao** e, se o usuario informar, **disciplina** e
**profundidade** (rapida = poucos trechos; ampla = mais trechos + modo hibrido).
Se a consulta estiver vaga, peca um esclarecimento curto antes de buscar.

### Etapa 2: Camada 0 -- MCP qmd nativo (SEMPRE)

Execute `mcp__qmd__query` combinando sub-buscas lexica e vetorial. Forneca sempre
um `intent`. Restrinja por coleção quando fizer sentido (`acervo`, `livros`,
`concursos`); omita para buscar em todas.

```
searches = [
  {type: "lex", query: "<termos exatos>"},
  {type: "vec", query: "<pergunta em linguagem natural sobre o tema>"}
]
intent = "<o que estou procurando>"
```

Recupere o conteudo dos melhores hits com `mcp__qmd__get` / `mcp__qmd__multi_get`
(use `minScore: 0.5` para filtrar ruido).

### Etapa 3: Camada 1 -- ChromaDB / hibrida (best-effort)

Enriqueca com a doutrina pesada via script empacotado. Rode o preflight primeiro:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" check
```

Se `pronto_vetorial` for `true`, busque (use `--modo hibrido` para incluir tambem o
qmd-lexical dos cadernos quando o usuario pedir profundidade):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search \
  --consulta "<termo>" [--disciplina "<area>"] [--modo vetorial|hibrido] -n 5
```

A saida e JSON: cada item traz `fonte`, `arquivo`, `titulo`, `autor`, `score`,
`trecho`. Se `check`/`search` indicarem indisponivel (SSD nao montado / Ollama
desligado), **nao insista** -- siga apenas com os resultados da Camada 0 e avise o
usuario que o acervo vetorial esta offline.

### Etapa 4: Consolidar e apresentar

- Funda os resultados das duas camadas e remova duplicatas (mesmo arquivo/trecho).
- Ordene por relevancia.
- Para cada trecho, leia o arquivo de origem com Read quando precisar de mais
  contexto antes de resumir.
- Apresente uma sintese fundamentada nos trechos recuperados, citando a origem.

## Formato de Saida

```
## Acervo Local -- "<termo>"

**Camadas consultadas**: qmd MCP (Camada 0)[; ChromaDB/hibrida (Camada 1)]
**Status Camada 1**: [disponivel | offline -- SSD/Ollama]

### Sintese
[2-4 paragrafos sintetizando o que o acervo traz sobre o tema, com base nos
trechos recuperados]

### Trechos relevantes
1. **[titulo/arquivo]** -- [coleção/fonte], score [x.xx]
   > "<trecho>"
   `caminho/do/arquivo`

2. ...

### Lacunas
[O que o acervo NAO cobriu; sugerir /pesquisa-juridica para legislacao e
jurisprudencia externas se for o caso]
```

> **Nota**: Resultados do acervo local sao material de apoio e podem estar
> desatualizados. Para uma posicao juridica, confirme legislacao e jurisprudencia
> em fontes primarias (use `/pesquisa-juridica`).
