---
name: revisar-contrato
description: "Revisar um contrato com base no playbook de negociacao da organizacao -- identifica desvios, gera sugestoes de redline e fornece analise de impacto comercial. Use ao revisar contratos de fornecedores ou clientes, quando precisar de analise clausula por clausula contra posicoes-padrao, ou ao preparar estrategia de negociacao com redlines priorizados e posicoes de fallback."
argument-hint: "<arquivo ou texto do contrato>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /revisar-contrato -- Revisao de Contrato com Base no Playbook

Revisar um contrato com base no playbook de negociacao da organizacao. Analisar cada clausula, identificar desvios, gerar sugestoes de redline e fornecer analise de impacto comercial.

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados antes de ser utilizada para decisoes juridicas.

## Invocacao

```
/revisar-contrato <arquivo ou URL do contrato>
```

Revisar o contrato: @$1

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Aceitar o Contrato

Aceitar o contrato em qualquer dos seguintes formatos:
- **Upload de arquivo**: PDF, DOCX ou outro formato de documento
- **URL**: Link para o contrato em sistema de armazenamento (Google Drive, SharePoint, etc.)
- **Texto colado**: Texto do contrato colado diretamente na conversa

Se nenhum contrato for fornecido, solicitar ao usuario que forneca um.

**Se o contrato for um PDF**, ele já deve ter sido convertido na Etapa 0 (com OCR).
O OCR é automático — escaneados/garbled são corrigidos e nunca abortam. Detalhes:
`${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 2: Coletar Contexto

Perguntar ao usuario sobre o contexto antes de iniciar a revisao:

1. **De que lado voce esta?** (fornecedor/prestador, cliente/contratante, licenciante, licenciado, parceiro -- ou outro)
2. **Prazo**: Quando isso precisa ser finalizado? (Afeta a priorizacao dos problemas)
3. **Areas de foco**: Alguma preocupacao especifica? (ex: "protecao de dados e critica", "precisamos de flexibilidade no prazo", "propriedade intelectual e a questao-chave")
4. **Contexto do negocio**: Algum contexto comercial relevante? (ex: valor do contrato, importancia estrategica, relacao pre-existente)
5. **Tipo de relacao**: Relacao de consumo (incidencia do CDC) ou relacao paritaria (B2B)?
6. **Jurisdicao**: Ha partes estrangeiras ou operacoes internacionais envolvidas?

Se o usuario fornecer contexto parcial, prosseguir com o que houver e registrar as premissas adotadas.

### Etapa 3: Carregar o Playbook

Buscar o playbook de revisao contratual da organizacao nas configuracoes locais (ex: `legal.local.md` ou arquivos de configuracao similares).

O playbook deve definir:
- **Posicoes-padrao**: Os termos preferidos da organizacao para cada tipo de clausula principal
- **Faixas aceitaveis**: Termos que podem ser aceitos sem escalacao
- **Gatilhos de escalacao**: Termos que exigem revisao por advogado senior ou assessoria externa

**Se nenhum playbook estiver configurado:**
- Informar ao usuario que nenhum playbook foi encontrado
- Oferecer duas opcoes:
  1. Ajudar o usuario a configurar seu playbook (orientar na definicao de posicoes para clausulas-chave)
  2. Prosseguir com uma revisao generica usando padroes amplamente aceitos no mercado brasileiro como baseline
- Se prosseguir genericamente, deixar claro que a revisao se baseia em padroes gerais de mercado, nao nas posicoes especificas da organizacao

### Etapa 4: Analise Clausula por Clausula

Aplicar o seguinte processo de revisao:

1. **Identificar o tipo de contrato**: Prestacao de servicos, licenciamento de software (SaaS), fornecimento de bens, parceria, franquia, distribuicao, locacao, etc. O tipo do contrato afeta quais clausulas sao mais relevantes.
2. **Determinar o lado do usuario**: Fornecedor, cliente, licenciante, licenciado, parceiro. Isso muda fundamentalmente a analise.
3. **Ler o contrato inteiro** antes de sinalizar problemas. As clausulas interagem entre si (ex: uma clausula penal excessiva pode ser parcialmente mitigada por uma limitacao de responsabilidade ampla).
4. **Verificar a incidencia de legislacao especial**: CDC (relacao de consumo), CLT (relacao trabalhista disfaracada), LGPD (tratamento de dados pessoais), Marco Civil (servicos de internet).
5. **Analisar cada clausula material** contra a posicao do playbook.
6. **Considerar o contrato holisticamente**: A alocacao de risco e os termos comerciais estao equilibrados?

Analisar o contrato sistematicamente, cobrindo no minimo:

| Categoria de Clausula | Pontos-Chave de Revisao |
|---|---|
| **Objeto e Escopo** | Definicao clara, obrigacoes de meio vs. resultado, especificacoes tecnicas |
| **Preco e Condicoes de Pagamento** | Valor, forma, periodicidade, reajuste (indice e periodicidade), mora, multa moratoria |
| **Clausula Penal (CC arts. 408-416)** | Valor da multa compensatoria (limite de 10% em consumo, livre em B2B), cumulacao com perdas e danos, proporcionalidade |
| **Limitacao de Responsabilidade** | Teto (valor fixo, multiplo de fees, ou ilimitada), carveouts, bilateral vs. unilateral, danos indiretos/lucros cessantes |
| **Clausula de Indenizacao** | Escopo, bilateral vs. unilateral, teto, hipoteses (PI, dados, danos a terceiros), procedimento |
| **Propriedade Intelectual** | PI pre-existente, PI desenvolvida, cessao vs. licenca, obra por encomenda (LDA art. 4), software (Lei 9.609/98) |
| **Protecao de Dados (LGPD)** | Funcao das partes (controlador/operador), base legal, DPA/contrato de tratamento, suboperadores, notificacao de incidentes, transferencia internacional |
| **Confidencialidade** | Escopo, prazo, excecoes, obrigacao de devolucao/destruicao |
| **Garantias e Declaracoes** | Escopo, disclaimers, prazo de sobrevivencia, vicios redibitorios (CC arts. 441-446) |
| **Prazo e Rescisao/Resiliacao** | Duracao, renovacao, denuncia vazia (CC art. 473), rescisao por inadimplemento (CC arts. 474-475), aviso previo, efeitos |
| **Lei Aplicavel e Foro** | Lei brasileira, foro de eleicao (CPC art. 63), clausula arbitral (Lei 9.307/96), foro do consumidor (CDC art. 101, I) |
| **Cessao e Transferencia** | Consentimento, cessao de posicao contratual (CC art. 299), mudanca de controle |
| **Forca Maior / Caso Fortuito** | Definicao (CC art. 393), notificacao, direitos de rescisao, onerosidade excessiva (CC arts. 478-480) |
| **Seguro** | Tipos de cobertura, valores minimos, comprovacao |
| **CDC -- Clausulas Abusivas** | Se relacao de consumo: verificar art. 51 do CDC (nulidade de clausulas abusivas) |
| **Compliance e Anticorrupcao** | Lei 12.846/2013, declaracoes anticorrupcao, FCPA/UK Bribery Act se partes internacionais |
| **Resolucao de Disputas** | Mediacao, conciliacao, arbitragem (Lei 9.307/96), jurisdicao estatal |

Para cada clausula, avaliar contra o playbook (ou padroes genericos) e notar se esta presente, ausente ou incomum.

#### Orientacao Detalhada por Clausula

##### Clausula Penal (CC arts. 408-416)

**Elementos-chave para revisar:**
- Valor da penalidade (fixo, percentual, ou formula de calculo)
- Se e compensatoria (substitui perdas e danos) ou moratoria (acresce ao adimplemento)
- Limite legal: em relacoes de consumo, o CDC limita multa moratoria a 2% (art. 52, paragrafo 1); no CC, a clausula penal nao pode exceder o valor da obrigacao principal (art. 412)
- Possibilidade de reducao equitativa pelo juiz (CC art. 413)
- Cumulacao com juros, correcao monetaria e honorarios

**Problemas comuns:**
- Clausula penal superior ao valor da obrigacao principal (nula por forca do art. 412 do CC)
- Multa excessiva em relacao de consumo (abusiva pelo art. 51, IV do CDC)
- Clausula penal unilateral (aplicavel apenas a uma parte)
- Ausencia de clausula penal em obrigacoes criticas (deixa a parte sem remedio rapido)

##### Limitacao de Responsabilidade

**Elementos-chave para revisar:**
- Teto de responsabilidade (valor fixo, multiplo do preco contratual, ou ilimitada)
- Se o teto e bilateral ou diferenciado por parte
- Exclusao de danos indiretos, lucros cessantes, danos morais coletivos
- Carveouts (hipoteses excluidas do teto): dolo, culpa grave, violacao de PI, LGPD
- Se o teto se aplica por evento, por ano, ou e agregado

**Problemas comuns:**
- Teto fixado em fracao do valor pago (ex: "valor pago nos ultimos 3 meses" em contrato de baixo valor)
- Carveouts assimetricos favorecendo o redator
- Exclusao de consequential damages sem excecao para dolo/culpa grave
- Em relacoes de consumo: clausula limitativa de responsabilidade pode ser declarada nula (CDC art. 51, I)

##### Propriedade Intelectual

**Elementos-chave para revisar:**
- Titularidade da PI pre-existente (cada parte deve reter a sua)
- Titularidade da PI desenvolvida durante a vigencia: cessao ou licenca?
- Obra por encomenda: na LDA (art. 4), salvo pacto em contrario, a titularidade e do autor; no software (Lei 9.609/98, art. 4), a titularidade e de quem contratou, salvo pacto em contrario
- Licencas: escopo, exclusividade, territorio, sublicenciamento
- Software livre e codigo aberto
- Clausulas de feedback (concessao de direitos sobre sugestoes/melhorias)

**Problemas comuns:**
- Cessao ampla que pode capturar PI pre-existente do contratante
- Silencio sobre titularidade de PI desenvolvida (risco de litigio)
- Clausula de feedback irrestrita conferindo licenca perpetua e irrevogavel
- Escopo de licenca mais amplo que o necessario para a relacao comercial

##### Protecao de Dados (LGPD -- Lei 13.709/2018)

**Elementos-chave para revisar:**
- Identificacao das funcoes: controlador vs. operador (LGPD art. 5, VI e VII)
- Base legal para tratamento (LGPD art. 7)
- Obrigacao de contrato entre controlador e operador (LGPD art. 39)
- Suboperadores: autorizacao e responsabilidade
- Notificacao de incidentes de seguranca (LGPD art. 48): comunicacao a ANPD e titulares
- Transferencia internacional de dados (LGPD arts. 33-36)
- Eliminacao de dados apos encerramento do tratamento (LGPD art. 16)
- Medidas de seguranca e direitos de auditoria
- Finalidade e adequacao do tratamento

**Problemas comuns:**
- Ausencia de contrato de tratamento de dados quando dados pessoais sao processados
- Autorizacao generica para suboperadores sem notificacao
- Transferencia internacional sem salvaguardas adequadas (LGPD art. 33)
- Provisoes inadequadas de eliminacao de dados
- Ausencia de Relatorio de Impacto a Protecao de Dados (RIPD) quando exigivel

##### Prazo, Rescisao e Resiliacao

**Elementos-chave para revisar:**
- Prazo inicial e prazos de renovacao
- Renovacao automatica: periodo de aviso (art. 473, paragrafo unico do CC -- aviso previo compativel com investimentos)
- Resiliacao unilateral (denuncia vazia): disponivel? aviso previo? penalidade por rescisao antecipada?
- Rescisao por inadimplemento (CC art. 475): prazo de cura? o que constitui inadimplemento?
- Efeitos da extincao: devolucao de dados, assistencia na transicao, clausulas de sobrevivencia
- Resolucao por onerosidade excessiva (CC arts. 478-480)

**Problemas comuns:**
- Prazos iniciais longos sem resiliacao por conveniencia
- Renovacao automatica com prazo de aviso curto (ex: 30 dias para renovacao anual)
- Sem periodo de cura para rescisao por inadimplemento
- Clausulas de sobrevivencia que efetivamente estendem o contrato indefinidamente
- Ausencia de regra sobre efeitos da extincao (transicao, dados, acesso)

##### Lei Aplicavel e Resolucao de Disputas

**Elementos-chave para revisar:**
- Lei aplicavel (brasileira; se internacional, LINDB arts. 9-17)
- Foro de eleicao (CPC art. 63 -- so admissivel em contratos paritarios; em consumo, o foro e do domicilio do consumidor: CDC art. 101, I)
- Clausula compromissoria de arbitragem (Lei 9.307/96): regras aplicaveis, sede, idioma, numero de arbitros
- Clausula escalonada (mediacao/conciliacao antes de arbitragem ou litigio)
- Arbitragem: custos (quem arca?), confidencialidade, medidas urgentes

**Problemas comuns:**
- Foro de eleicao em jurisdicao distante do domicilio do consumidor (nula por forca do CDC)
- Clausula arbitral em contrato de adesao de consumo (nula se imposta: CDC art. 51, VII; so valida se o consumidor a instituir: Lei 9.307/96 art. 4, paragrafo 2)
- Foro no exterior em contratos entre partes brasileiras (pode ser ineficaz)
- Ausencia de mecanismo escalonado de resolucao de disputas

### Etapa 5: Identificar Desvios

Classificar cada desvio do playbook usando um sistema de tres niveis:

#### VERDE -- Aceitavel

A clausula esta alinhada ou e melhor que a posicao-padrao da organizacao. Variacoes menores que sao comercialmente razoaveis e nao aumentam o risco materialmente.

**Exemplos:**
- Teto de responsabilidade em 18 meses de fees quando o padrao e 12 meses (melhor para o cliente)
- Prazo de confidencialidade de 2 anos quando o padrao e 3 anos (mais curto, mas razoavel)
- Foro de eleicao em comarca comercialmente estabelecida, proxima da preferida
- Clausula penal dentro dos limites legais e proporcionais

**Acao**: Registrar para conhecimento. Nenhuma negociacao necessaria.

#### AMARELO -- Negociar

A clausula esta fora da posicao-padrao, mas dentro de uma faixa negociavel. O termo e comum no mercado, mas nao e a preferencia da organizacao. Requer atencao e provavelmente negociacao, mas nao escalacao.

**Exemplos:**
- Teto de responsabilidade em 6 meses de fees quando o padrao e 12 meses
- Indenizacao unilateral por violacao de PI quando o padrao e bilateral
- Renovacao automatica com aviso de 30 dias quando o padrao e 60 dias
- Foro de eleicao em jurisdicao aceitavel, mas nao preferida
- Clausula penal acima do padrao de mercado, mas dentro dos limites legais

**Acao**: Gerar linguagem de redline especifica. Fornecer posicao de fallback. Estimar impacto comercial de aceitar vs. negociar.
- **Incluir**: Linguagem de redline especifica para retornar ao padrao
- **Incluir**: Posicao de fallback se a contraparte resistir
- **Incluir**: Impacto comercial de aceitar como esta vs. negociar

#### VERMELHO -- Escalar

A clausula esta fora da faixa aceitavel, aciona um criterio de escalacao definido, ou representa risco material. Requer revisao por advogado senior, assessoria externa, ou aprovacao de tomador de decisao.

**Exemplos:**
- Responsabilidade ilimitada ou ausencia de clausula de limitacao
- Indenizacao unilateral ampla sem teto
- Cessao de PI pre-existente
- Ausencia de contrato de tratamento de dados (LGPD) quando dados pessoais sao processados
- Clausulas abusivas em relacao de consumo (CDC art. 51)
- Foro de eleicao em jurisdicao problematica com arbitragem compulsoria
- Clausula penal superior ao valor da obrigacao principal (CC art. 412)
- Clausula que viola norma de ordem publica (nulidade)

**Acao**: Explicar o risco especifico. Fornecer linguagem alternativa de mercado. Estimar exposicao. Recomendar caminho de escalacao.
- **Incluir**: Por que e VERMELHO (risco especifico com fundamentacao legal)
- **Incluir**: Qual e a posicao padrao de mercado
- **Incluir**: Impacto comercial e exposicao potencial
- **Incluir**: Caminho de escalacao recomendado

### Etapa 6: Consultar Jurisprudencia (via brlaw MCP)

Para cada clausula classificada como AMARELO ou VERMELHO, quando aplicavel:

1. **Pesquisar jurisprudencia relevante** nos tribunais superiores via brlaw MCP:
   - STJ para questoes contratuais infraconstitucionais (responsabilidade civil, clausula penal, relacoes de consumo)
   - STF para questoes constitucionais (liberdade contratual, funcao social do contrato)
   - TST para clausulas com implicacoes trabalhistas

2. **Verificar Sumulas aplicaveis**, especialmente:
   - Sumula 381/STJ: Nos contratos bancarios, e vedado ao julgador conhecer, de oficio, da abusividade das clausulas
   - Sumula 297/STJ: O CDC e aplicavel as instituicoes financeiras
   - Sumula 302/STJ: E abusiva a clausula contratual de plano de saude que limita no tempo a internacao hospitalar
   - Sumula 473/STF: A Administracao pode anular seus proprios atos
   - Sumulas do TST sobre clausulas trabalhistas
   - Outras sumulas vinculantes ou de efeito persuasivo pertinentes

3. **Incluir na analise**: Citar o precedente ou sumula com numero, tribunal e data quando reforcar a posicao de negociacao.

### Etapa 7: Gerar Sugestoes de Redline

Para cada desvio AMARELO e VERMELHO, fornecer:
- **Linguagem atual**: Citar o texto contratual relevante
- **Redline sugerido**: Linguagem alternativa especifica
- **Fundamentacao**: Breve explicacao adequada para compartilhar com a contraparte, incluindo base legal quando pertinente
- **Prioridade**: Se e um must-have ou nice-to-have na negociacao

#### Melhores Praticas para Redlines

1. **Seja especifico**: Fornecer linguagem exata, nao orientacao vaga. O redline deve estar pronto para inserir.
2. **Seja equilibrado**: Propor linguagem firme nos pontos criticos, mas comercialmente razoavel. Redlines excessivamente agressivos atrasam negociacoes.
3. **Explique a fundamentacao**: Incluir fundamentacao breve e profissional, citando dispositivos legais quando relevante.
4. **Forneca posicoes de fallback**: Para itens AMARELO, incluir posicao de fallback se o pedido principal for rejeitado.
5. **Priorize**: Nem todos os redlines sao iguais. Indicar quais sao must-haves e quais sao nice-to-haves.
6. **Considere a relacao**: Ajustar tom e abordagem conforme se trate de fornecedor novo, parceiro estrategico ou fornecedor commodity.

#### Formato do Redline

Para cada redline:
```
**Clausula**: [Referencia da secao e nome da clausula]
**Linguagem atual**: "[citacao exata do contrato]"
**Redline proposto**: "[linguagem alternativa especifica]"
**Fundamentacao**: [1-2 frases explicando por que, com referencia legal quando aplicavel]
**Base Legal**: [Dispositivo legal pertinente, se houver]
**Prioridade**: [Essencial / Importante / Desejavel]
**Fallback**: [Posicao alternativa se o redline principal for rejeitado]
```

### Etapa 8: Resumo de Impacto Comercial

Fornecer uma secao de resumo cobrindo:
- **Avaliacao geral de risco**: Visao de alto nivel do perfil de risco do contrato
- **Top 3 questoes**: Os itens mais importantes a enderencar
- **Estrategia de negociacao**: Abordagem recomendada (quais questoes liderar, o que conceder)
- **Consideracoes de prazo**: Fatores de urgencia que afetam a abordagem de negociacao
- **Aspectos regulatorios**: Incidencia de legislacao especial (CDC, CLT, LGPD, etc.)

#### Framework de Prioridade de Negociacao

**Nivel 1 -- Essenciais (Deal Breakers)**
Questoes em que a organizacao nao pode prosseguir sem resolucao:
- Responsabilidade ilimitada ou protecoes materialmente insuficientes
- Ausencia de protecao de dados pessoais exigida pela LGPD
- Clausulas de PI que podem comprometer ativos essenciais
- Termos que conflitam com obrigacoes regulatorias ou normas de ordem publica
- Clausulas abusivas em relacao de consumo (CDC art. 51)

**Nivel 2 -- Importantes (Preferencias Fortes)**
Questoes que afetam materialmente o risco, mas com margem de negociacao:
- Ajustes no teto de responsabilidade dentro da faixa
- Escopo e bilateralidade da indenizacao
- Flexibilidade de rescisao
- Direitos de auditoria e compliance
- Clausula penal proporcionalmente adequada

**Nivel 3 -- Desejaveis (Candidatos a Concessao)**
Questoes que melhoram a posicao, mas podem ser concedidas estrategicamente:
- Foro de eleicao preferido (se alternativa aceitavel)
- Preferencias de prazo de aviso
- Melhorias menores em definicoes
- Requisitos de certificado de seguro

**Estrategia de negociacao**: Liderar com itens de Nivel 1. Trocar concessoes de Nivel 3 para assegurar vitorias de Nivel 2. Nunca conceder em Nivel 1 sem escalacao.

## Formato de Saida

Estruturar a saida como:

```
## Resumo da Revisao Contratual

**Documento**: [nome/identificador do contrato]
**Partes**: [nomes e funcoes das partes]
**Seu Lado**: [fornecedor/cliente/etc.]
**Prazo**: [se informado]
**Base da Revisao**: [Playbook / Padroes Genericos]
**Legislacao Especial Incidente**: [CDC / CLT / LGPD / Marco Civil / Nenhuma]

## Constatacoes Principais

[Top 3-5 questoes com flags de severidade]

## Analise Clausula por Clausula

### [Categoria da Clausula] -- [VERDE/AMARELO/VERMELHO]
**O contrato diz**: [resumo da clausula]
**Posicao do playbook**: [seu padrao]
**Desvio**: [descricao da lacuna]
**Base legal**: [dispositivo legal pertinente]
**Jurisprudencia**: [precedente relevante, se encontrado via brlaw MCP]
**Impacto comercial**: [o que isso significa na pratica]
**Sugestao de redline**: [linguagem especifica, se AMARELO ou VERMELHO]

[Repetir para cada clausula principal]

## Estrategia de Negociacao

[Abordagem recomendada, prioridades, candidatos a concessao]

## Proximos Passos

[Acoes especificas a tomar]
```

## Notas

- Se o contrato estiver em idioma diferente do portugues, notar e perguntar se o usuario deseja a revisao no idioma original
- Para contratos muito longos (50+ paginas), oferecer foco nas secoes mais materiais primeiro e depois revisao completa
- Sempre lembrar o usuario de que esta analise deve ser revisada por advogado habilitado antes de ser utilizada para decisoes juridicas
- Verificar se o contrato ja foi registrado em cartorio de titulos e documentos (quando aplicavel)
- Para contratos internacionais, verificar a aplicabilidade da LINDB (Lei de Introducao as Normas do Direito Brasileiro)
