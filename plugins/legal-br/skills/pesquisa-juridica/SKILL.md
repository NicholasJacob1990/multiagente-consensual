---
name: pesquisa-juridica
description: "Pesquisa juridica integrada que orquestra todos os MCPs juridicos disponiveis -- legislacao (senado), jurisprudencia (brlaw), dados publicos (dadosbr) -- para produzir memorando de pesquisa com citacoes em formato ABNT. Use quando precisar pesquisar jurisprudencia sobre um tema, buscar legislacao aplicavel, consultar processos no DataJud, ou obter visao consolidada de legislacao + jurisprudencia + doutrina sobre uma questao."
argument-hint: "<questao ou tema de pesquisa>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /pesquisa-juridica -- Pesquisa Juridica Integrada

Pesquisar: @$1

Pesquisa juridica integrada que orquestra todos os servidores MCP juridicos disponiveis para produzir memorando de pesquisa estruturado com citacoes em formato ABNT.

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados antes de ser utilizada para decisoes juridicas.

## Invocacao

```
/pesquisa-juridica <questao ou tema de pesquisa>
```

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Aceitar a Questao de Pesquisa

Aceitar a questao de pesquisa e coletar contexto:

1. **Questao ou tema**: Qual e a questao juridica ou tema a ser pesquisado?
2. **Escopo**: Buscar legislacao, jurisprudencia, ou ambos?
3. **Ramo do direito**: Qual area? (civil, trabalhista, tributario, consumidor, administrativo, penal, constitucional, dados pessoais, empresarial, etc.)
4. **Profundidade**: Pesquisa rapida (visao geral) ou pesquisa aprofundada (analise detalhada)?
5. **Periodo**: Ha periodo especifico de interesse? (ex: jurisprudencia dos ultimos 5 anos)
6. **Formato de saida**: Memorando de pesquisa, lista de precedentes, ou analise tematica?

### Etapa 2: Decompor em Sub-consultas

Decompor a questao principal em sub-consultas especificas para cada fonte:

#### Sub-consultas de Legislacao
- Identificar os diplomas legais potencialmente aplicaveis
- Formular termos de busca para a legislacao (via senado MCP, se disponivel)
- Listar artigos e dispositivos especificos a verificar

#### Sub-consultas de Jurisprudencia
- Formular termos de busca otimizados para cada tribunal:
  - **STF**: Questoes constitucionais, sumulas vinculantes, repercussao geral
  - **STJ**: Questoes infraconstitucionais, recursos repetitivos, sumulas
  - **TST**: Questoes trabalhistas, sumulas, OJs
- Preparar variantes de busca (sinonimos, operadores de proximidade, truncamento)
- Identificar palavras-chave e expressoes juridicas relevantes

#### Sub-consultas de Dados Publicos
- Formular consultas para o DataJud (via dadosbr MCP, se disponivel)
- Identificar partes ou temas para consulta processual

### Etapa 2.5: Consultar o Acervo Local (PRIMEIRO)

Antes de buscar em fontes externas, recupere o que o acervo doutrinario/pessoal
local ja tem sobre o tema. Ele complementa -- nao substitui -- legislacao e
jurisprudencia primarias.

1. **Camada 0 (sempre):** MCP `qmd` nativo -- `mcp__qmd__query` com sub-buscas
   `lex` + `vec` nas colecoes `acervo`/`livros`/`concursos`; recupere o conteudo
   dos melhores hits com `mcp__qmd__get` / `mcp__qmd__multi_get`.
2. **Camada 1 (best-effort):** doutrina pesada via ChromaDB/hibrida:
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" check
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search --consulta "TERMO" -n 5
   ```
   Se `check`/`search` indicarem indisponivel (SSD/Ollama), prossiga apenas com a
   Camada 0.

Use os achados do acervo para refinar as sub-consultas das etapas seguintes.
Rotule trechos como "[Acervo local -- nao verificado em fonte primaria]" e
confirme teses/precedentes nas fontes oficiais. Protocolo completo:
`${CLAUDE_PLUGIN_ROOT}/references/acervo-local.md`.

### Etapa 3: Pesquisar Legislacao

**Se senado MCP disponivel:**
- Consultar texto integral de leis, decretos e medidas provisorias
- Verificar vigencia e eventuais alteracoes recentes
- Identificar normas infralegais aplicaveis (decretos regulamentadores, resolucoes)

**Se senado MCP nao disponivel:**
- Buscar o texto oficial via web (Planalto `ccivil_03` -- use sufixo `compilado` para
  texto atualizado --, LexML, DOU). Comandos por fonte: `${CLAUDE_PLUGIN_ROOT}/references/fontes-web.md` (secao 4)
- Se nao verificar em fonte primaria, marcar como nao-verificado
- Para estadual/municipal (fora do Planalto), usar LexML ou firecrawl search `site:`

Legislacao frequentemente relevante por ramo:

| Ramo | Diplomas Principais |
|---|---|
| Civil | CC/2002, CPC/2015, LINDB |
| Consumidor | CDC (Lei 8.078/90), Decreto 2.181/97 |
| Trabalhista | CLT, Lei 13.467/2017 (Reforma), Lei 13.429/2017 (Terceirizacao) |
| Protecao de Dados | LGPD (Lei 13.709/18), Decreto 8.771/16, Regulamentos ANPD |
| Tributario | CTN (Lei 5.172/66), CF arts. 145-162, legislacao especifica por tributo |
| Administrativo | Lei 14.133/21 (Licitacoes), Lei 8.429/92 (Improbidade), Lei 9.784/99 |
| Anticorrupcao | Lei 12.846/13, Decreto 11.129/22 |
| Societario | CC/2002 (arts. 966-1195), LSA (Lei 6.404/76) |
| PI | LPI (Lei 9.279/96), LDA (Lei 9.610/98), Lei do Software (9.609/98) |
| Digital | Marco Civil (Lei 12.965/14), Decreto 8.771/16, AI Act BR (se aprovado) |
| Ambiental | Lei 6.938/81, Lei 9.605/98, Codigo Florestal (Lei 12.651/12) |
| Concorrencial | Lei 12.529/11, Resolucoes CADE |
| Penal | CP, CPP, Lei 9.613/98 (Lavagem), Lei 12.850/13 (Org. Criminosa) |

### Etapa 4: Pesquisar Jurisprudencia (via brlaw MCP)

Executar pesquisas nos tribunais superiores em paralelo quando possivel:

#### Pesquisa no STF (StfLegalPrecedentsRequest)

Quando pertinente (materia constitucional):
1. Formular busca com operadores adequados
2. Analisar resultados da primeira pagina
3. Se pertinentes mas insuficientes, solicitar paginas adicionais
4. Identificar: ADIs, ADCs, ADPFs, Repercussoes Gerais, Sumulas Vinculantes

#### Pesquisa no STJ (StjLegalPrecedentsRequest)

Quando pertinente (materia infraconstitucional):
1. Usar operadores avancados: `e`, `ou`, `nao`, `mesmo`, `com`, `PROX(N)`, `ADJ(N)`
2. Analisar resultados
3. Identificar: Recursos Especiais Repetitivos, Sumulas, Teses firmadas

#### Pesquisa no TST (TstLegalPrecedentsRequest)

Quando pertinente (materia trabalhista):
1. Usar aspas para expressoes exatas
2. Analisar resultados
3. Identificar: Sumulas, OJs, Incidentes de Recursos Repetitivos

#### Estrategia de Refinamento
- Se poucos resultados: ampliar termos, usar sinonimos, truncamento ($)
- Se muitos resultados: refinar com operadores de proximidade, excluir termos irrelevantes
- Se resultados irrelevantes: reformular a busca com terminologia juridica mais precisa
- Sempre buscar em pelo menos 2 formulacoes diferentes

#### Fallback web: JusBrasil autenticado + Firecrawl LOCAL

Quando brlaw falhar/for insuficiente, use as fontes web do usuario. **Rode o
preflight primeiro** e gate o uso pela disponibilidade:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fontes_externas.py" check
```

**Firecrawl LOCAL (busca/scrape geral)** -- NUNCA use a cloud (sem creditos):
```bash
# So se preflight.firecrawl.local_up == true:
firecrawl search "site:stj.jus.br jurisprudencia TERMO ementa" \
  --api-url http://localhost:3002 -k local-firecrawl-key --limit 5
firecrawl scrape "URL_DO_ACORDAO" --api-url http://localhost:3002 \
  -k local-firecrawl-key --format markdown
```
Se `local_up == false`: **nao** caia para cloud -- use o **WebSearch nativo** e
avise que o firecrawl local esta offline (`docker compose up -d` em
`~/Aplicativos/firecrawl` para ligar).

**JusBrasil autenticado** (conta Premium do usuario; cookie-first + Playwright
fallback) -- so se `preflight.jusbrasil.pronto == true`:
```bash
# Busca de jurisprudencia (lista de decisoes)
cd ~/Aplicativos/a2a-gemini && uv run --with playwright python scripts/jusbrasil_search.py \
  --query "TEMA" [--tribunal stj|stf|trf-1] [--pages 2]

# Integra de um acordao (cookie-first via profile firecrawl; fallback Playwright)
... scripts/jusbrasil_search.py --url "URL" --firecrawl --fc-profile jusbrasil
```
Se a integra/peca vier em **PDF**, converta antes de citar:
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf" --stdout`
(ver `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`).
Respeite o rate-limit embutido (nao paralelizar). Se a sessao nao existir, o
preflight indica o setup unico. **Protocolo completo (comandos, setup, prioridade):**
`${CLAUDE_PLUGIN_ROOT}/references/fontes-web.md`.

**Quando usar estas fontes:**
- brlaw retornou timeout/Cloudflare ou "Via DataJud" (sem ementas completas)
- Precisa de inteiro teor de decisao (nao apenas ementa)
- Tribunais nao cobertos pelo brlaw (TRFs, TJs) ou doutrina/peças
- Sumulas e OJs

**Ordem de prioridade para jurisprudencia:**
1. brlaw MCP (ementas diretas do STF/STJ/TST)
2. JusBrasil autenticado (integra, TJs/TRFs, doutrina)
3. Firecrawl LOCAL (scrape direto de *.jus.br, busca web)
4. WebSearch nativo (se firecrawl local offline)
5. datajud MCP (metadados processuais, sem ementa)
6. Conhecimento do modelo (ultima opcao, marcar como nao-verificado)

### Etapa 5: Pesquisar Dados Processuais (via dadosbr MCP)

Quando relevante e disponivel:
- `datajud_processos`: Consultar volume e perfil de processos sobre o tema
- Identificar tendencias (aumento/diminuicao de litigiosidade)
- Verificar historico processual de partes especificas (se pertinente)

### Etapa 6: Sintetizar e Citar Fontes

Sintetizar todos os achados em um memorando estruturado com citacoes adequadas.

#### Formato de Citacao (ABNT NBR 10520)

**Legislacao:**
```
BRASIL. [Tipo de norma] n. [numero], de [data]. [Ementa]. Diario Oficial da Uniao,
Brasilia, DF, [data de publicacao].
```
Exemplo:
```
BRASIL. Lei n. 13.709, de 14 de agosto de 2018. Lei Geral de Protecao de Dados
Pessoais (LGPD). Diario Oficial da Uniao, Brasilia, DF, 15 ago. 2018.
```

**Jurisprudencia:**
```
BRASIL. [Tribunal]. [Tipo de decisao] n. [numero]. Relator: Min. [nome].
[Orgao julgador], julgado em [data], publicado em [data].
```
Exemplo:
```
BRASIL. Superior Tribunal de Justica. REsp n. 1.419.697/RS. Relator: Min. Paulo
de Tarso Sanseverino. Segunda Secao, julgado em 12/11/2014, DJe 17/12/2014.
```

**Sumulas:**
```
BRASIL. [Tribunal]. Sumula [n.]. [Texto]. [Data de aprovacao].
```

**Doutrina:**
```
SOBRENOME, Nome. Titulo da obra. [Edicao]. [Local]: [Editora], [Ano]. p. [paginas].
```

### Etapa 7: Gerar Memorando de Pesquisa

## Formato de Saida

```
## Memorando de Pesquisa Juridica

**Tema**: [questao ou tema pesquisado]
**Data**: [data da pesquisa]
**Ramo(s) do Direito**: [areas identificadas]
**Escopo**: [legislacao, jurisprudencia, ambos]
**Fontes Consultadas**: [acervo local (qmd/ChromaDB), brlaw/senado/dadosbr MCP, JusBrasil autenticado, Firecrawl local/WebSearch]

---

### 1. Resumo Executivo

[2-3 paragrafos sintetizando os principais achados: legislacao aplicavel,
posicao jurisprudencial predominante, e conclusao preliminar]

### 2. Legislacao Aplicavel

#### 2.1. Constituicao Federal
[Dispositivos constitucionais relevantes, se houver]

#### 2.2. Legislacao Federal
[Leis, decretos e normas infralegais aplicaveis, com artigos especificos]

#### 2.3. Regulamentacao Administrativa
[Resolucoes, instrucoes normativas, etc.]

### 3. Jurisprudencia

#### 3.1. Supremo Tribunal Federal (STF)
[Precedentes encontrados, com citacao completa e analise de aplicabilidade]

**Sumulas Vinculantes aplicaveis**: [se houver]
**Repercussoes Gerais relevantes**: [se houver]

#### 3.2. Superior Tribunal de Justica (STJ)
[Precedentes encontrados, com citacao completa e analise de aplicabilidade]

**Sumulas aplicaveis**: [se houver]
**Recursos Repetitivos relevantes**: [se houver]

#### 3.3. Tribunal Superior do Trabalho (TST)
[Precedentes encontrados, se questao trabalhista]

**Sumulas e OJs aplicaveis**: [se houver]

### 4. Doutrina de Referencia

[Autores e obras relevantes sobre o tema]

### 5. Dados Processuais

[Se consultado via dadosbr MCP: volume de processos, tendencias, perfil de litigiosidade]

### 6. Sintese e Posicao Predominante

[Analise consolidada: qual e a posicao predominante na legislacao e jurisprudencia?]

| Aspecto | Posicao | Grau de Consolidacao |
|---|---|---|
| [Aspecto 1] | [Posicao encontrada] | [Pacifica/Majoritaria/Controversa/Minoritaria/Inedita] |
| [Aspecto 2] | [Posicao encontrada] | [Pacifica/Majoritaria/Controversa/Minoritaria/Inedita] |

### 7. Lacunas e Limitacoes

[O que nao foi encontrado, fontes nao consultadas, areas que exigem pesquisa adicional]

### 8. Referencias

[Lista completa de todas as fontes citadas em formato ABNT NBR 6023]

---

**Nota**: Esta pesquisa foi elaborada com auxilio de inteligencia artificial e tem
carater meramente informativo. Nao constitui assessoria juridica. Toda decisao
juridica deve ser tomada com base na orientacao de advogado regularmente inscrito na OAB.
As fontes citadas devem ser verificadas em suas versoes originais atualizadas.
```

## Modos de Pesquisa

### Pesquisa Rapida (Visao Geral)
- Foco nos precedentes mais relevantes (1-2 paginas por tribunal)
- Legislacao principal com artigos-chave
- Sumulas aplicaveis
- Tempo estimado: rapido

### Pesquisa Aprofundada (Analise Detalhada)
- Multiplas paginas de resultados por tribunal
- Todas as variantes de busca
- Legislacao primaria e secundaria
- Dados processuais (se disponivel)
- Doutrina de referencia
- Analise de evolucao jurisprudencial
- Tempo estimado: mais demorado, mas abrangente

## Notas

- Sempre indicar claramente quando um resultado foi obtido via MCP (fonte primaria) vs. conhecimento interno (pode estar desatualizado)
- Registrar as queries exatas usadas em cada MCP para reprodutibilidade
- Se nenhum MCP juridico estiver disponivel, a pesquisa se baseara no conhecimento interno com aviso explicito ao usuario
- Recomendacoes de fontes complementares: Westlaw Brazil, Vlex, JusBrasil, LegisWeb, Planalto.gov.br
- Para pesquisa de legislacao estadual ou municipal, indicar que os MCPs disponiveis cobrem primariamente legislacao federal e jurisprudencia dos tribunais superiores
