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

## As sete regras duras

Valem em todo parecer produzido por esta skill e prevalecem sobre conveniência
de redação:

1. **Toda afirmação cita fonte** — dispositivo normativo, precedente, documento
   do processo ou obra. Afirmação sem âncora sai do texto ou vira pergunta ao
   usuário. Isso inclui as frases de transição que "todo mundo sabe". Resumo
   de buscador ou de IA (L3) não é fonte → `references/fontes-web.md`, seção 0.
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
   novo ao final. No estilo clássico forense, os verbetes em caixa alta são
   seguidos da ementa estruturada em quatro itens numerados (caso sob exame;
   questões em discussão; razões conclusivas; resposta objetiva aos quesitos),
   cada item em poucas linhas (`estilos-de-redacao.md`, Perfil B).
6. **Premissas declaradas.** Se conclusões dependem de fato não provado, o
   parecer é **preliminar** e diz de que depende. Errar aqui é o que transforma
   parecer em passivo.
7. **Indício não é título.** Conduta compatível com mais de uma causa jurídica
   (cobrança, pagamento, posse, silêncio) é apresentada com todas as causas
   compatíveis e a norma de cada uma, e não se converte em titularidade. Busque
   ativamente a prova contrária ao achado favorável, inclusive conduta posterior
   silente ou contrária, e registre-a. Silêncio não se presume renúncia nem
   extinção.

## Modo de execução: pergunte sempre

Antes de começar (minuta nova, nova rodada, revisão, acabamento ou anexo),
**pergunte ao usuário se o trabalho será feito no modo conciso ou no modo
profundo**, com a recomendação e a estimativa de custo de cada um, e, na mesma
pergunta, **qual estilo de redação: executivo** (gestor, área técnica,
governança) **ou clássico** (AGE, Tribunal de Contas, juízo), com a
recomendação pelo destinatário. Perfis, núcleo comum (verificação aritmética,
quadro de hipóteses, remissão rotulada) e o que muda em cada estilo:
`${CLAUDE_PLUGIN_ROOT}/references/estilos-de-redacao.md`. Só dispense
a pergunta se o pedido já declarar o modo. O que muda em cada modo, quando
escalar do conciso para o profundo, as invariantes e a caixa de ferramentas
obrigatória estão em `${CLAUDE_PLUGIN_ROOT}/references/modos-de-execucao.md`.
Leia-o antes da Etapa 0.

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

### Etapa 0.5 (OBRIGATÓRIA em dossiê acima de 60 páginas): leitura integral e cobertura

Sobre o `.md` da Etapa 0, monte um **índice página a página** e leia o dossiê
**inteiro, em blocos** (cerca de 40 páginas por subagente). Para cada página
registre documento, data, tipo de fonte (primária | peça da consulente | nota do
usuário | relatório de modelo), fatos relevantes e status (pendente | lida |
ilegível | não verificável no OCR). Busca por palavra-chave serve para localizar, nunca para
concluir que algo "não consta". Não conclua sobre fatos enquanto houver página
pendente no índice.

O Relatório declara a cobertura ("foram examinadas integralmente as N páginas do
Processo SEI ...; as pp. X e Y estão ilegíveis e constam como diligência").
Mantenha com o índice, numa pasta de trabalho do caso, os registros de achados,
cronologia (evento | data | p. | fonte), páginas ilegíveis, conferência da origem
(Etapa 1) e correções (Etapa 9). Nas rodadas seguintes e na revisão adversarial,
entregue e reutilize esses registros: não releia o dossiê inteiro, releia só as
páginas citadas em trecho alterado.

Dois registros a mais na pasta do caso:

- **Registro de refutadas** (`refutadas.json`): toda afirmação que se mostrou
  errada (proporção, data, parte, qualificação jurídica) entra com padrão,
  motivo, forma correta e fonte. Rode `checar_refutadas.py` sobre toda versão
  nova e sobre todo texto recebido (minuta colada pelo usuário, análise de outro
  modelo) antes de aproveitá-lo. Minuta antiga reaparece; o registro a barra.
- **Tabela de assentos**: para matrícula ou certidão no dossiê, extraia por
  script (`${CLAUDE_PLUGIN_ROOT}/scripts/extrair_assentos.py CERTIDAO.md --md`)
  cabeçalho (matrícula, livro, folha, CNM, data, registro anterior), atos R-/AV-
  e, em loteamento, a tabela lote × área × nota de transferência × assento de
  destino. Lotes **sem** nota, ao lado dos demais com nota, são achado em si.

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

**A peça da consulente é alegação, não fonte.** CI, nota técnica, despacho e
minuta anterior são conferidos item a item antes de redigir. Lance cada
afirmação factual (quem, quando, quanto, qual registro) num registro de
conferência da origem, com as colunas: afirmação | página na peça | fonte
primária (pp.) | confere / diverge / não localizada. Só entra no parecer o que
conferiu. Divergência relevante é registrada no Relatório ("a CI indica 1970; a
escritura, à p. 345, é de 1971"). Confusões típicas: sucessor posterior posto
como adquirente original; percentual do preço tomado como proporção dos
créditos; data da sentença tomada como data do trânsito em julgado; ano de
abertura da matrícula. Nota do usuário e relatório de outro modelo seguem a
mesma regra.

**O que se atribui à consulente tem de estar na peça dela.** Toda frase com
"segundo a consulente", "a CI relata", "a GEPAT pede" usa os termos da peça, não
sinônimos que mudam o sentido ("retirada do registro" não é "desincorporação";
"indisponibilidades registradas" não é "indisponibilidades ativas"), e não lhe
atribui motivos que ela não declarou ("evitar riscos à governança"). Conclusão
do parecer extraída da peça é apresentada como do parecer ("este parecer adota
essa premissa e dela extrai…"). Confira com
`conferir_atribuicao.py --fonte CI.md MINUTA.md`.

**Quesitos fiéis.** Transcreva ou parafraseie os quesitos item a item, com a
página, sem acrescentar elementos (a "divergência de área" que a consulente não
perguntou) nem omitir alternativas e ressalvas ("ou a possibilidade de
procedimento específico", "observados os direitos dos titulares"). O mesmo vale
para os pedidos acessórios: "avaliar a conveniência de obter cópias" não é
"indagar como obter cópias".

**Registro de decisões do caso** (`decisoes.json`, na pasta do caso, ao lado do
`refutadas.json`): requerente, forma, estilo, limites e escolhas estratégicas
já decididos pelo usuário, com data e origem. Sugestão de revisor que contrarie
decisão registrada não é aplicada nem relitigada: vai à nota como "decisão já
tomada — reabrir?" (`checar_decisoes.py`; `consolidar_correcoes.py --decisoes`).

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
                        cada uma com seu grau de segurança; ou, para área
                        técnica ou gestor, conclusão didática (abaixo)

É o parecer, salvo melhor juízo.
<assinatura / cargo / unidade>

REFERÊNCIAS             uma fonte por item
```

**Estilo.** O executivo usa a estrutura abaixo, com a resposta objetiva no
início e a conclusão didática. O clássico forense usa ementa estruturada em
quatro itens (que traz a resposta objetiva), estrutura tripartite — I.
Relatório, II. Fundamentação com subtítulos por quesito, III. Conclusão —,
transcrição de ementa (uma por seção ou quesito, com introdução e comentário) e
conclusão em prosa por quesito, com plano em etapas e matriz a) a d). Nos dois,
a fonte por afirmação, o quadro de hipóteses e o Anexo pedido pela consulta são
obrigatórios (`estilos-de-redacao.md`).

**Conclusão didática** (estilo executivo; preferível quando o destinatário for área técnica ou
gestor, ou quando a resposta depender de hipóteses): abra a seção I com um
parágrafo **Resposta objetiva.** (a orientação em linguagem direta, com o grau de
segurança) e organize a conclusão em **Síntese.**; um parágrafo por quesito, com
o rótulo em forma de pergunta (**Quesito 1 — …?**) e a resposta logo em
seguida; **O que [a área] deve fazer, em ordem.**, com passos (1), (2)…;
**Premissas e limites deste parecer.**; e, ao final, um índice curto por
categoria com remissões. Em parecer GENES, siga a forma do perfil
(`perfil-parecer-genes.md`, Estrutura, item 7). Didático não é categórico: a
resposta simplificada carrega as mesmas condicionantes do corpo (Etapa 8, item 9).

**Ordem das seções**: siga a cadeia de dependência do problema (dominial →
natureza do bem → regime jurídico → instrumentos → riscos → diligências). Cada
seção deve preparar a seguinte.

**Redação em prosa**, sem listas de tópicos, salvo enumeração de cláusulas,
hipóteses ou diligências.

**Ritmo.** Alterne o tamanho dos parágrafos conforme a função: curtos (uma ou
duas frases) para enunciar tese, fazer transição ou fechar conclusão parcial;
médios para expor fatos e normas; mais longos, até cerca de 100 palavras, para o
raciocínio que liga fato, norma e consequência. Evite sequências de parágrafos
do mesmo tamanho e parágrafo curto sem função.

**Leitura fácil.** Abra cada parágrafo pela ideia principal (frase-tópico).
Prefira ordem direta, voz ativa e uma ideia principal por frase. Use conectivos
que mostrem a relação entre as ideias ("por isso", "ainda assim", "em outras
palavras"). Explique o termo técnico na primeira vez em que ele decide algo
(domínio útil, senhorio, resgate). Ponha citações e remissões no fim da frase
que sustentam (ou do parágrafo, quando valem para ele inteiro), não no meio
dela. Evite negações encadeadas, gerúndio em série e adjetivação enfática.
Escreva para o destinatário: o gestor da área consulente deve entender o que
fazer sem precisar reler.

**Relatório (seção I) em ordem narrativa.** Quem consulta (unidade por extenso
e sigla, documento, data, encaminhamento e distribuição) → objeto (imóvel ou
ato, e o problema que motivou a consulta) → o fato que gerou a dúvida, com
"segundo a consulente" → quesitos enumerados ("primeiro…, segundo…,
terceiro…"), fiéis à peça → pedidos acessórios → natureza do parecer e data de
corte → base documental → premissa adotada. Um parágrafo para cada passo; a
resposta objetiva vem antes, no §1.

**Remissão rotulada.** Na conclusão e nos pontos de virada, remeta pelo nome e
pelo número: "como antecipado na resposta objetiva (parágrafo 1)", "na síntese
(parágrafo 110) e no plano de ação (parágrafos 123 e 124)". O rótulo protege o
leitor quando a numeração de quem lê difere (ferramenta que não conta o §1,
cópia reformatada).

**Glosa na primeira ocorrência.** Todo termo técnico que decide a leitura recebe
explicação curta na primeira vez em que aparece no corpo, entre parênteses ou
em aposto: "coadjudicação (adjudicação conjunta a dois credores)",
"consolidação (reunião, na mesma pessoa, dos domínios útil e direto)",
"autotutela (procedimento conduzido pelo próprio Oficial, com contraditório
dos titulares)", "prenotação (protocolo de título formalmente apresentado)". A
ementa não conta como primeira ocorrência.

**Rótulos de grupo da conclusão** ("Correções necessárias", "Obrigações já
incidentes"…) são índice, não tarefas: diga isso numa frase antes deles, para o
gestor não confundir "o que falta provar" com "o que fazer nesta semana". O
passo a passo fica no plano de ação.

**Nome correto de norma e fonte.** Quando a peça ou o título chama a norma de
modo diverso da fonte oficial ("decreto-lei" na escritura; "Lei" na ALMG), use
a forma oficial e registre uma vez a denominação do documento. Súmulas e
dispositivos com conteúdos distintos são atribuídos um a um ("a Súmula 169
exige sentença; a Súmula 122 admite a purga até ela"), nunca em bloco.

**Marca vista só na imagem** (carimbo, manuscrito, assinatura) não é fato do
texto: "traria carimbo 'PAGO' (p. 332), a conferir na imagem", salvo se a
leitura da imagem estiver registrada no índice do dossiê.

**Um parágrafo, uma função.** Junte o parágrafo de uma frase que só faz
sentido com o vizinho; mas divida o parágrafo que acumula funções (fato e
divergência de outro documento; leitura incerta e conclusão sobre conduta;
regra e consequência processual). Sinais: mais de ~85 palavras com dois grupos
de citação, ou mudança de data ou de tema no meio ("Em 1976, porém…", "Os
documentos de…").

**Absolutos só com prova.** "Nunca", "sempre", "jamais", "todos", "nenhum"
sobre fato exigem documento citado na mesma frase. Sem ele, escreva o que a
prova permite: "nada nos autos indica que…", "não há documento que…".

**Doutrina** em autor-data no texto, no fim da frase que sustenta (perfil
GENES). Nota de rodapé só quando o perfil ou o usuário pedir; o gerador aceita
a sintaxe `[^id]` / `[^id]: texto`.

**Peça anexa dirigida a terceiro** (requerimento ao Registro de Imóveis,
ofício): não cite documento interno pelo número SEI. Descreva-o pelo que o
destinatário reconhece (escritura, livro, folha, matrícula, protocolo). Marque a
origem de cada dado cadastral (dossiê, usuário, cadastro público) e liste na
nota o que falta conferir. Para o Registro de Imóveis, siga
`${CLAUDE_PLUGIN_ROOT}/references/requerimento-registral.md`.

**Limite de extensão nunca se cumpre por elipse.**

- Diploma sempre completo: "art. 693 do Código Civil de 1916", e não "art. 693
  civil" ou "Código de 1916".
- "Domínio útil" e "domínio direto", e não "o útil" e "o direto".
- Sigla definida na primeira ocorrência.
- Cada parte com nome único, fixado no início do Relatório; nada de "a
  Companhia" quando houver mais de uma.

Para caber no limite, divida o parágrafo (remapeando as remissões internas) ou
corte conteúdo. Se ainda não couber, avise o usuário. Pedido de versão "ENXUTA"
reduz conteúdo, nunca termos.

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

**Quadro de hipóteses** (obrigatório quando titularidade, legitimidade ou regime
dependerem de fato não provado), com as colunas: Hipótese | Prova a favor (pp.) |
Prova contra ou silêncio (pp.) | Consequência jurídica | Legitimado e via |
Diligência que decide. As hipóteses recebem gradação simétrica (regra 4). A
conclusão diz qual diligência discrimina entre elas e o que fazer em cada uma.
Ressalva de alternativa explicativa, uma vez escrita, só sai do texto com fonte
nova.

**Faculdade × obrigação.** Para cada via recomendada (resgate, escritura,
retificação, ação), diga de quem é a faculdade ou o dever, se a outra parte pode
recusar e qual o efeito para cada parte. Reconhecer uma situação jurídica não
impõe, por si, nenhuma via; não chame de "via própria" a que é só uma das
disponíveis.

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

Parecer sobre norma em elaboração (regulamento, edital, estatuto, política): as redações
sugeridas seguem `${CLAUDE_PLUGIN_ROOT}/references/tecnica-legislativa.md` — técnica legislativa
(LC nº 95/1998 por analogia), Anexo de Redações Sugeridas com blocos `(NR)`/`(AC)`, mesmo
texto no anexo e na minuta revisada, remissão ao item integrada à frase do parecer.

A numeração de parágrafos é **automática** (campo de lista do Word), nunca
digitada. Padrão, comandos e armadilhas de OOXML:
`${CLAUDE_PLUGIN_ROOT}/references/parecer-docx.md`.

**Comparativo e integridade.** O comparativo (alterações controladas) é feito
contra a **última versão aprovada pelo usuário**, não contra a base antiga, com
`word_redline.py --base APROVADA.docx` (sem Docxodus instalado, ele usa o motor
nativo, por palavra). Depois de qualquer montagem, rode
`integridade_docx.py --base --limpa --redline`: aceitar tudo deve reproduzir a
limpa e rejeitar tudo, a base, sem perda de parágrafo, referência ou nota. O
validador genérico de DOCX não substitui essa conferência quando houver
parágrafos divididos ou fundidos.

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
   for o caso? Indícios apresentados com todas as causas compatíveis e a prova
   contrária registrada? (regras 6 e 7)
7. Redações sugeridas para a norma examinada coincidem com a minuta revisada e o parecer
   não cita redação superada? (`tecnica-legislativa.md`, seção 6)
8. Passou pelas **armadilhas recorrentes**?
   → `${CLAUDE_PLUGIN_ROOT}/references/armadilhas-direito-br.md`
9. **Corpo × conclusão × ementa × anexos e quadros.** Para cada item da
   conclusão, enunciado da ementa e linha de anexo ou quadro, indique o
   parágrafo-fonte e confira que carrega as mesmas condicionantes ("se
   confirmado", "desde que", "depende de"). Anexo e ementa nunca afirmam o que o
   corpo deixou condicionado.
10. **Léxico categórico.** "Integralmente", "exatamente", "mera", "inequívoco",
    "a via própria", "não pertence", "domínio pleno", "reduz o risco" exigem
    fonte que sustente esse grau. Vale também para a correção feita pelo próprio
    redator. Na dúvida, rebaixe ("é compatível com", "indica").
11. **Fatos novos.** `inventario_fatos.py ANTERIOR NOVA --md`: todo acréscimo
    de número, data, página, valor, área ou dispositivo entra na nota de revisão
    com a fonte (página); toda supressão é justificada.
12. **Coerência peça anexa × conclusão.** Liste o que a conclusão desaconselha
    (ex.: baixa, prenotação como título, afirmação de titularidade) e o que ela
    manda pedir; confira que o anexo não pede o primeiro e pede o segundo.
13. **Refutadas e absolutos.** `pre_auditoria_parecer.py ... --refutadas
    refutadas.json` sem bloqueante; alertas de `absolutos` resolvidos.
13-A. **Densidade e pontas soltas.** Se o usuário pedir texto menos denso, mais
    enxuto ou para leitor não técnico, corte conteúdo, não só divida frases:
    meça antes e depois com `medir_densidade.py --anterior ... --meta-reducao N`
    e siga `estilos-de-redacao.md`, seção 6 (glossário, síntese após a ementa,
    quadro de hipóteses, ordem de corte). Depois de qualquer corte ou reescrita,
    `conferir_orfaos.py` sem bloqueante: julgado citado sem entrada nas
    Referências, instrução editorial entre colchetes no anexo, verbete da ementa
    sem parágrafo, referência que ninguém mais cita, conta só com símbolos. Para
    reescrita com reestruturação, use `reescrever_docx.py` (roteiro) e gere o
    comparativo com `word_redline.py`. Arquivo recebido com marcas pendentes:
    `resolver_revisoes.py` para obter a base (`controle-alteracoes-word.md`).
14. **Um comando por versão.** Em toda versão, inclusive no modo conciso, rode
    `conferir_versao.py --anterior APROVADA.docx --nova NOVA.docx [--redline]
    [--refutadas] [--decisoes] [--verificacoes] --estilo executivo|classico
    [--exige-anexo] [--meta-reducao N] --perfil genes --max-paginas N --registro versoes.json
    --nota-saida conferencias.md` e cole a seção gerada na nota de revisão.
    Use `--exige-anexo` sempre que a consulta pedir minuta ou peça. Com
    `--verificacoes`, as contas registradas do caso (somas, proporções, áreas)
    são refeitas e os números certos são procurados no texto. Ele mede as páginas no PDF: acima do limite do perfil, pergunte uma
    vez se o limite foi ampliado e registre a resposta em `decisoes.json`.
15. Disclaimer presente?

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

**Toda correção é afirmação nova**, venha de auditor, de outro pipeline, do
usuário ou de você. Passa pelas regras 1 a 4 e 7 antes de entrar. Corrigir um
exagero não autoriza o exagero oposto, nem a introdução de precedente, ato ou
via fora do objeto.

Registre cada correção no registro de correções (pasta de trabalho do caso,
Etapa 0.5), com as colunas: id |
origem (auditor/modelo, pipeline, usuário, redator) | trecho antes | trecho
depois | fonte (pp. ou dispositivo) | veredito (confirmado / parcial, restringir
extrapolação / refutado) | decisão (acolhida / em parte / recusada) | motivo.

**Auditor externo** (outro modelo, outro pipeline): entregue o texto com "§N"
explícito (`pacote_auditoria.py montar --numerado PARECER.docx`) e peça que
cite por ele e repita o SHA-256. Ao receber achados de remissão, rode
`conferir_achados_externos.py --documento --achados --sha256-entregue` antes de
corrigir qualquer número: ele detecta deslocamento sistemático da numeração do
auditor (caso real: duas tabelas inteiras deslocadas em −1 porque o auditor não
contou o §1) e cópia diferente da entregue. A nota de revisão segue
`references/nota-de-revisao.md`, com veredito por ponto.

Com vários verificadores, consolide as propostas por script
(`consolidar_correcoes.py`): duplicatas saem, e conflito (mesmo trecho com duas
correções) é decidido pela fonte ou pelo mapa de origem, nunca pela ordem de
chegada. O que for refutado vai também para o registro de refutadas.

Não relitigue achado acolhido; recusa exige fonte. Na rodada seguinte, entregue
o registro ao revisor junto com os demais registros do dossiê, para que exagero
já corrigido não volte. Em parecer de alto valor, faça auditoria cruzada com
outra família de modelo ou com outro pipeline do usuário, sempre com as fontes
primárias.

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
