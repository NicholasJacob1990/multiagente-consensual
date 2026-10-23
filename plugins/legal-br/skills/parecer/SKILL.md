---
name: parecer
description: "Elaborar parecer juridico fundamentado sobre questao de direito brasileiro, com pesquisa de legislacao, jurisprudencia e doutrina, verificacao de precedentes em fonte primaria e entrega em .docx no padrao institucional. Use quando precisar de opiniao juridica estruturada sobre uma questao especifica, quando necessitar fundamentar posicao com precedentes dos tribunais superiores, ou ao preparar subsidio para tomada de decisao juridica."
argument-hint: "<questao juridica ou caso>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /parecer — Elaboração de Parecer Jurídico

Elaborar parecer sobre: @$1

**Importante**: esta ferramenta auxilia fluxos de trabalho jurídicos, mas não
constitui assessoria jurídica. Toda análise deve ser revisada por profissional
habilitado antes de embasar decisão.

## As seis regras duras

Valem em todo parecer produzido por esta skill e prevalecem sobre conveniência
de redação:

1. **Toda afirmação cita fonte** — dispositivo normativo, precedente, documento
   do processo ou obra. Afirmação sem âncora sai do texto ou vira pergunta ao
   usuário. Isso inclui as frases de transição que "todo mundo sabe".
2. **Precedente só entra com relator, órgão julgador e data lidos na página do
   tribunal.** Nunca de memória, nunca de agregador, nunca de notícia
   institucional. → `references/verificacao-precedentes.md`
3. **Gradue a certeza e nunca diga "risco nulo".** Distinga tese consolidada de
   premissa de fato ainda não provada. O que depende de diligência pendente é
   dito assim, com todas as letras.
4. **Simetria de gradação:** teses de mesma natureza recebem o mesmo rótulo. Se
   você chamou uma extensão jurisprudencial de "sustentável e não pacificada",
   não apresente outra da mesma estirpe como assentada.
5. **Ementa ≤ 80 palavras.** Ela é o que a diretoria lê; é índice, não resumo
   executivo. Cada correção que você fizer no corpo tende a inchá-la — meça de
   novo ao final.
6. **Premissas declaradas.** Se conclusões dependem de fato não provado, o
   parecer é **preliminar** e diz de que depende. Errar aqui é o que transforma
   parecer em passivo.

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, íntegras,
doutrina, matrículas, plantas, processos SEI), converta-o para Markdown com OCR
e trabalhe sobre o `.md`, mantido como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
```

Nunca cite trecho de PDF sem gerar o `.md`. Detalhes:
`${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

**Plantas, matrículas e mapas** também são prova documental: leia a imagem, não
só o texto. Escala, carimbo, legenda e o que está **desenhado** (edificações,
lagos, divisas) sustentam ou derrubam premissas. Registre no parecer o que a
peça **não** demonstra — campo de data em branco, ausência de coordenadas,
edificação não demarcada.

### Etapa 1: Delimitar a questão

Aceitar a questão em qualquer formato (texto, arquivo, múltiplas questões). Se
vaga, esclarecer: fatos relevantes; pergunta jurídica exata; partes e em que
qualidade; ramo do direito; prazo; finalidade (decisão interna, subsídio
judicial, defesa, compliance); e se o parecer deve ser imparcial ou sustentar
tese.

**Separe desde já o que é fato provado do que é relato.** Declaração da parte
interessada e "relatos de antigos moradores" são premissas a confirmar, não
fatos — e sustentam boa parte da análise. Liste-as na Etapa 1 e retome-as na
conclusão.

### Etapa 1.5: Consultar o acervo local (PRIMEIRO)

Antes da pesquisa externa, recupere doutrina e cadernos já sistematizados: MCP
`qmd` (coleções `acervo`/`livros`) e
`python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search --consulta "TERMO" -n 5`.
Trate como material **não verificado** em fonte primária. Protocolo:
`${CLAUDE_PLUGIN_ROOT}/references/acervo-local.md`.

### Etapa 2: Legislação aplicável

Constituição → lei federal → legislação especial → regulamentação infralegal →
**normas estaduais e municipais** (frequentemente decisivas em matéria urbana,
ambiental e de patrimônio, e quase sempre esquecidas) → **regulamentos internos**
da entidade envolvida (estatais têm RILC próprio, que prevalece sobre a Lei
14.133/2021).

Confira **vigência e alcance de revogações** — revogação costuma ser parcial.
Cite a revisão/data do regulamento interno consultado.

### Etapa 3: Jurisprudência — descoberta

Para **encontrar** precedentes por tema:

- **brlaw MCP** — `StjLegalPrecedentsRequest`, `StfLegalPrecedentsRequest`,
  `TstLegalPrecedentsRequest`. Instável: fica fora do ar por longos períodos.
  Se falhar, siga adiante sem insistir.
- **Firecrawl / WebSearch** — `site:stj.jus.br`, `site:stf.jus.br`, Jurisprudência
  em Teses, Informativos.

Operadores: STF aceita `E`/`OU`/`NÃO`, aspas, `~N` (proximidade), `$`
(truncamento); STJ aceita `e`/`ou`/`não`/`mesmo`/`com`, `PROX(N)`, `ADJ(N)`, `$`,
`?`; TST prefere aspas em expressões compostas. Comece amplo, refine, e **busque
também o precedente contrário à tese**.

### Etapa 3.5 (OBRIGATÓRIA): verificar cada precedente em fonte primária

Descoberta não é verificação. Antes de citar, abra a página do tribunal e colha
**classe, número/UF, relator, órgão julgador, data de julgamento e publicação
(DJe ou DJEN)**.

- **STJ**: bloqueio Cloudflare (*Managed Challenge*) — resolvedor de captcha não
  serve; use navegador real e a query do SCON.
- **STF**: basta `curl -A` com User-Agent de browser.

Receita completa, com as URLs: `${CLAUDE_PLUGIN_ROOT}/references/verificacao-precedentes.md`.

Ao abrir o acórdão, **leia a ementa inteira** — com frequência ela traz argumento
melhor do que o motivo pelo qual você foi buscá-lo, inclusive precedente
envolvendo a própria parte do caso.

Não conseguindo confirmar, **diga isso ao usuário** e ofereça remover a citação.
Nunca complete relator ou data por inferência.

### Etapa 4: Dados processuais (opcional)

`datajud` MCP para aferir litigiosidade sobre o tema e tendências.

### Etapa 5: Doutrina

| Ramo | Autores de referência |
|---|---|
| Civil/Obrigações | Caio Mário, Orlando Gomes, Pontes de Miranda, Flávio Tartuce |
| Contratos | Orlando Gomes, Silvio Rodrigues, Tartuce, Nelson Rosenvald |
| Consumidor | Cláudia Lima Marques, Ada Pellegrini Grinover, Herman Benjamin |
| Trabalhista | Maurício Godinho Delgado, Sergio Pinto Martins, Vólia Bomfim |
| Tributário | Hugo de Brito Machado, Paulo de Barros Carvalho, Leandro Paulsen |
| Administrativo | Celso Antônio Bandeira de Mello, Di Pietro, Hely Lopes Meirelles |
| Bens públicos / uso privativo | Di Pietro (*Uso privativo de bem público por particular*) |
| Estatais | Alexandre Santos de Aragão, Marçal Justen Filho |
| Constitucional | José Afonso da Silva, Gilmar Mendes, Ingo Sarlet, Barroso |
| Empresarial | Fábio Ulhoa Coelho, André Santa Cruz, Rubens Requião |
| Processual Civil | Fredie Didier Jr., Humberto Theodoro Jr., Scarpinella Bueno |
| Proteção de dados | Danilo Doneda, Bruno Bioni, Laura Schertel Mendes |
| Penal | Bitencourt, Rogério Greco, Nucci |

Formato ABNT NBR 6023; obra, edição e página quando possível.

### Etapa 6: Redigir

Estrutura formal (adapte os títulos ao padrão da casa):

```
PARECER <ÓRGÃO> Nº ___/AAAA
Processo nº ... | Interessada: ... | Origem: ...

EMENTA: [≤ 80 palavras, caixa alta]

I — RELATÓRIO           fatos em ordem cronológica, documentos examinados,
                        premissas adotadas e o que ainda não está provado
II — ... — IX           fundamentação, uma seção por eixo do problema
X — CONCLUSÃO           respostas numeradas (Primeiro., Segundo., ...),
                        cada uma com seu grau de segurança

É o parecer, salvo melhor juízo.
<assinatura / cargo / unidade>

REFERÊNCIAS             uma fonte por item
```

**Ordem das seções**: siga a cadeia de dependência do problema (dominial →
natureza do bem → regime jurídico → instrumentos → riscos → diligências). Cada
seção deve preparar a seguinte.

**Redação em prosa**, parágrafos de 6 a 8 linhas, quebrados em ponto final —
não em listas de tópicos, salvo enumeração de cláusulas ou diligências.

**Escala de segurança**, a declarar em cada conclusão: posição consolidada ·
predominante · sustentável e não pacificada · controversa · minoritária ·
inédita. E separe a segurança **da tese** da segurança **do caso**: a tese pode
ser consolidada e a conclusão continuar condicionada à prova de um fato.

**Ementa** — deve conter apenas: ramo do direito, objeto, regimes especiais
incidentes, natureza jurídica reconhecida, instrumento recomendado, solução
definitiva e a ressalva de preliminaridade. Não é lugar para fundamento,
dispositivo ou raciocínio.

**Antecipe a leitura adversa.** Para cada tese central, escreva a melhor objeção
possível e responda-a no texto. É isso que separa parecer de peça de convencimento.

### Etapa 7: Entregar em `.docx` no padrão institucional

Parecer para juntada não sai em Markdown. Peça ao usuário **um parecer anterior
aprovado** e espelhe a formatação; na ausência, use o padrão da casa.

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts/parecer_docx.py"
python3 "$S" converter parecer.md parecer.docx   # pandoc + formatação + numeração automática
python3 "$S" numerar   parecer.docx              # após inserir parágrafos novos
python3 "$S" ementa    parecer.docx --max 80     # mede a ementa
python3 "$S" nota      parecer.docx --par N --texto "..."
```

Parecer da GENES/DIJUR (Codemge e Codemig): aplicar `${CLAUDE_PLUGIN_ROOT}/references/perfil-parecer-genes.md`
(estrutura, redação sem informações soltas, até 15 páginas, armadilhas já verificadas e
auditoria final só com o Gemini 4 Argon quando pedida). Ele registra a divergência entre o
formato da v07 aprovada (corpo 10,5) e o padrão abaixo (corpo 12): pergunte qual vale.

A numeração de parágrafos é **automática** (campo de lista do Word), nunca
digitada. Padrão, comandos e armadilhas de OOXML:
`${CLAUDE_PLUGIN_ROOT}/references/parecer-docx.md`.

**Edição concorrente**: o usuário edita o `.docx` no Word entre as suas chamadas.
Releia o arquivo antes de cada edição, faça backup a cada rodada e localize
parágrafos **pelo texto**, nunca pelo índice — o índice do `python-docx` não é o
número que o Word exibe.

### Etapa 8: Auditar antes de entregar

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/parecer_docx.py" auditar parecer.docx
```

Pega ementa fora do teto, citação sem relator/data, typos, frase truncada,
parágrafo de corpo sem numeração e perda de nota de rodapé.

Depois, a conferência que só o modelo faz:

1. Conclusão decorre da fundamentação? Todas as questões respondidas?
2. Legislação e jurisprudência **vigentes** e com alcance de revogação conferido?
3. Cada afirmação tem fonte? (regra 1)
4. Precedentes verificados em fonte primária? (regra 2)
5. Gradação presente e **simétrica**? (regras 3 e 4)
6. Premissas não provadas declaradas, e o parecer marcado como preliminar quando
   for o caso? (regra 6)
7. Passou pelas **armadilhas recorrentes**?
   → `${CLAUDE_PLUGIN_ROOT}/references/armadilhas-direito-br.md`
8. Disclaimer presente?

### Etapa 9 (opcional): revisão adversarial

Para parecer de alto valor, submeta a revisão por outros modelos — a skill
`loop-debate-agentes` faz o ciclo com painel e auditoria cega.

**Lição de método:** dê ao revisor **as fontes primárias** (documentos do
processo, íntegras dos acórdãos, regulamentos). Auditoria cega *do debate* é
desejável; cega *das fontes* produz crítica genérica e nota artificialmente
baixa — o mesmo texto avaliado sem e com as fontes teve diferença de quase um
ponto na escala de 10.

Ao receber crítica, **verifique antes de acatar**: revisor erra. Confirme cada
apontamento na fonte primária e incorpore **inline**, no corpo do parecer, nunca
como seção de "respostas à revisão".

## Tipos de parecer

| Tipo | Quando usar |
|---|---|
| Consultivo | resposta a consulta específica |
| Preventivo | análise de risco antes de decidir |
| Opinativo | fundamentar tese já definida |
| Regulatório | conformidade setorial, LGPD |
| Contratual | análise de instrumento ou cláusulas |
| Patrimonial | uso, cessão e alienação de bens; regimes de proteção |
| Trabalhista / Tributário | matéria específica |

## Notas

- Diga expressamente quando **não** encontrou precedente sobre o ponto.
- Havendo divergência, apresente as duas correntes e indique a predominante.
- Questão muito ampla: proponha decomposição.
- Quando a solução jurídica adequada depender de providência de terceiro
  (órgão ambiental, de patrimônio, município), **formule os quesitos** a serem
  submetidos, em vez de presumir a resposta.
- O parecer não substitui advogado. Disclaimer obrigatório ao final.
