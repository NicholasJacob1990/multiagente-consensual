---
name: triagem-nda
description: "Triagem rapida de um Acordo/Termo de Confidencialidade (NDA) recebido, classificando como VERDE (aprovacao padrao), AMARELO (revisao por advogado) ou VERMELHO (revisao juridica completa). Use quando um novo NDA chegar da area comercial, ao verificar clausulas de nao-concorrencia, nao-solicitacao ou carveouts ausentes, ou ao decidir se o NDA pode ser assinado sob delegacao padrao."
argument-hint: "<arquivo ou texto do NDA>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /triagem-nda -- Pre-Triagem de NDA

Triagem do NDA: @$1

Triar rapidamente Acordos/Termos de Confidencialidade recebidos contra criterios-padrao de analise. Classificar o NDA para roteamento: aprovacao padrao, revisao por advogado, ou revisao juridica completa.

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados antes de ser utilizada para decisoes juridicas.

## Invocacao

```
/triagem-nda
```

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Aceitar o NDA

Aceitar o NDA em qualquer formato:
- **Upload de arquivo**: PDF, DOCX ou outro formato de documento
- **URL**: Link para o NDA em sistema de documentos
- **Texto colado**: Texto do NDA colado diretamente

Se nenhum NDA for fornecido, solicitar ao usuario que forneca um.

**Se o NDA for um PDF**, ele já deve ter sido convertido na Etapa 0 (com OCR).
O OCR é automático — escaneados/garbled são corrigidos e nunca abortam. Detalhes: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 2: Carregar Playbook de NDA

Buscar criterios de triagem de NDA nas configuracoes locais (ex: `legal.local.md`).

O playbook de NDA deve definir:
- Requisitos de bilateralidade
- Prazos aceitaveis
- Carveouts obrigatorios
- Clausulas proibidas
- Requisitos especificos da organizacao

**Se nenhum playbook de NDA estiver configurado:**
- Prosseguir com defaults razoaveis de mercado brasileiro
- Notar claramente que defaults estao sendo usados
- Defaults aplicados:
  - Obrigacoes bilaterais quando ambas as partes divulgam informacoes
  - Prazo: 2-3 anos padrao, ate 5 anos para segredos de negocio/industria
  - Carveouts padrao obrigatorios: informacao ja publica, ja detida, desenvolvida independentemente, recebida de terceiros sem restricao, exigida por lei/ordem judicial
  - Sem clausula de nao-solicitacao ou nao-concorrencia
  - Sem clausula residual (ou escopo estreito se presente)
  - Foro de eleicao em comarca razoavel
  - Conformidade com LGPD se dados pessoais envolvidos

### Etapa 3: Analise Rapida

Avaliar o NDA contra cada criterio de triagem sistematicamente.

#### 1. Estrutura do Acordo
- [ ] **Tipo identificado**: Bilateral (mutuo), Unilateral (parte reveladora), ou Unilateral (parte receptora)
- [ ] **Adequado ao contexto**: O tipo do NDA e adequado para a relacao comercial? (ex: bilateral para discussoes exploratorias, unilateral para divulgacoes unidirecionais)
- [ ] **Acordo autonomo**: Confirmar que o NDA e um acordo autonomo, nao uma secao de confidencialidade embutida em um contrato comercial maior
- [ ] **Denominacao correta**: Verificar se e Acordo de Confidencialidade, Termo de Confidencialidade e Sigilo, ou denominacao equivalente

#### 2. Definicao de Informacao Confidencial
- [ ] **Escopo razoavel**: Nao excessivamente amplo (evitar "toda e qualquer informacao de qualquer natureza")
- [ ] **Requisitos de marcacao**: Se marcacao e exigida, e praticavel? (marcacao escrita em 30 dias apos divulgacao oral e padrao)
- [ ] **Exclusoes presentes**: Exclusoes padrao definidas (ver Carveouts Padrao abaixo)
- [ ] **Sem inclusoes problematicas**: Nao define informacao publica ou materiais desenvolvidos independentemente como confidenciais

#### 3. Obrigacoes da Parte Receptora
- [ ] **Padrao de cuidado**: Cuidado razoavel ou ao menos o mesmo cuidado dispensado as proprias informacoes confidenciais
- [ ] **Restricao de uso**: Limitado a finalidade declarada
- [ ] **Restricao de divulgacao**: Limitado a quem precisa conhecer e esta vinculado por obrigacoes similares
- [ ] **Sem obrigacoes onerosas**: Sem requisitos impraticaveis (ex: criptografar todas as comunicacoes, manter registros fisicos detalhados)

#### 4. Carveouts Padrao
Todos os seguintes carveouts devem estar presentes:
- [ ] **Conhecimento publico**: Informacao que e ou se torna publicamente disponivel sem culpa da parte receptora
- [ ] **Posse anterior**: Informacao ja conhecida pela parte receptora antes da divulgacao
- [ ] **Desenvolvimento independente**: Informacao desenvolvida independentemente sem uso ou referencia a informacao confidencial
- [ ] **Recebimento de terceiros**: Informacao recebida legitimamente de terceiro sem restricao
- [ ] **Obrigacao legal**: Direito de divulgar quando exigido por lei, regulamento ou processo legal/judicial (com notificacao a parte reveladora quando legalmente permitido)

#### 5. Divulgacoes Permitidas
- [ ] **Empregados**: Pode compartilhar com empregados que precisam conhecer
- [ ] **Prestadores/assessores**: Pode compartilhar com prestadores de servico, assessores e consultores profissionais sob obrigacoes similares de confidencialidade
- [ ] **Afiliadas**: Pode compartilhar com empresas do grupo (se necessario para a finalidade)
- [ ] **Legal/regulatorio**: Pode divulgar quando exigido por lei, regulamento ou ordem judicial

#### 6. Prazo e Duracao
- [ ] **Prazo do acordo**: Periodo razoavel para a relacao comercial (1-3 anos e padrao)
- [ ] **Sobrevivencia da confidencialidade**: Obrigacoes sobrevivem por periodo razoavel apos o termino (2-5 anos e padrao; segredos de negocio podem ter prazo maior)
- [ ] **Nao perpetuo**: Evitar obrigacoes de confidencialidade indefinidas ou perpetuas (excecao: segredos de negocio/industria, que podem justificar protecao mais longa)

#### 7. Devolucao e Destruicao
- [ ] **Obrigacao acionada**: Na extincao ou mediante solicitacao
- [ ] **Escopo razoavel**: Devolver ou destruir informacao confidencial e todas as copias
- [ ] **Excecao de retencao**: Permite retencao de copias exigidas por lei, regulamento ou politicas internas de compliance/backup
- [ ] **Certificacao**: Certificacao de destruicao e razoavel; declaracao juramentada e onerosa

#### 8. Remedios
- [ ] **Tutela inibitoria**: Reconhecimento de que violacao pode causar dano irreparavel e medidas de urgencia podem ser adequadas e padrao
- [ ] **Sem danos pre-fixados**: Evitar clausulas de danos liquidados em NDAs
- [ ] **Nao unilateral**: Remedios se aplicam igualmente a ambas as partes (em NDAs bilaterais)
- [ ] **Clausula penal**: Se presente, verificar se esta dentro dos limites do CC art. 412 e e proporcional

#### 9. Clausulas Problematicas a Sinalizar
- [ ] **Sem nao-solicitacao**: NDA nao deve conter clausula de nao-solicitacao de empregados
- [ ] **Sem nao-concorrencia**: NDA nao deve conter clausula de nao-concorrencia (materia trabalhista, exige compensacao: CLT art. 444 c/c CC art. 421)
- [ ] **Sem exclusividade**: NDA nao deve restringir qualquer parte de entrar em discussoes similares com terceiros
- [ ] **Sem standstill**: NDA nao deve conter clausula de standstill (exceto em contexto de M&A)
- [ ] **Sem clausula residual** (ou escopo estreito): Se presente, deve ser limitada a informacao retida na memoria nao auxiliada de individuos e nao deve se aplicar a segredos de negocio ou informacao patenteavel
- [ ] **Sem cessao/licenca de PI**: NDA nao deve conceder quaisquer direitos de propriedade intelectual
- [ ] **Sem direitos de auditoria**: Incomum em NDAs padrao

#### 10. LGPD e Protecao de Dados
- [ ] **Dados pessoais identificados**: Se dados pessoais serao compartilhados, esta previsto no NDA?
- [ ] **Base legal adequada**: Se dados pessoais envolvidos, ha base legal para o tratamento (LGPD art. 7)?
- [ ] **Obrigacoes de seguranca**: Medidas de seguranca adequadas para dados pessoais
- [ ] **Notificacao de incidentes**: Obrigacao de notificar em caso de incidente envolvendo dados pessoais
- [ ] **Eliminacao de dados pessoais**: Provisoes especificas para eliminacao de dados pessoais ao termino

#### 11. Foro de Eleicao e Lei Aplicavel
- [ ] **Jurisdicao razoavel**: Comarca comercialmente estabelecida
- [ ] **Consistencia**: Lei aplicavel e foro devem ser na mesma jurisdicao ou jurisdicoes relacionadas
- [ ] **Sem arbitragem compulsoria** (em NDAs padrao): Litigio e geralmente preferido para disputas de NDA
- [ ] **Foro do consumidor**: Se relacao de consumo, foro deve ser o do domicilio do consumidor (CDC art. 101, I)

### Etapa 4: Classificar

Com base nos resultados da triagem, atribuir uma classificacao:

#### VERDE -- Aprovacao Padrao

**Todos** os seguintes devem ser verdadeiros:
- NDA e bilateral (ou unilateral na direcao apropriada)
- Todos os carveouts padrao estao presentes
- Prazo esta na faixa padrao (1-3 anos, sobrevivencia 2-5 anos)
- Sem clausulas de nao-solicitacao, nao-concorrencia ou exclusividade
- Sem clausula residual, ou clausula residual de escopo estreito
- Jurisdicao de foro razoavel
- Remedios padrao (sem danos liquidados desproporcionais)
- Divulgacoes permitidas incluem empregados, prestadores e assessores
- Provisoes de devolucao/destruicao incluem excecao de retencao legal/compliance
- Definicao de informacao confidencial tem escopo razoavel
- Se dados pessoais envolvidos, clausulas de LGPD adequadas

**Roteamento**: Aprovar via delegacao padrao de autoridade. Sem necessidade de revisao por advogado.
- **Acao**: Prosseguir para assinatura com delegacao padrao de autoridade

#### AMARELO -- Revisao por Advogado Necessaria

**Um ou mais** dos seguintes estao presentes, mas o NDA nao e fundamentalmente problematico:
- Definicao de informacao confidencial e mais ampla que o preferido, mas nao irrazoavel
- Prazo e mais longo que o padrao, mas dentro da faixa de mercado (ex: 5 anos para prazo, 7 anos para sobrevivencia)
- Falta um carveout padrao que poderia ser adicionado sem dificuldade
- Clausula residual presente, mas de escopo estreito (memoria nao auxiliada)
- Foro de eleicao em comarca aceitavel, mas nao preferida
- Assimetria menor em NDA bilateral (ex: uma parte tem divulgacoes permitidas ligeiramente mais amplas)
- Requisitos de marcacao presentes, mas praticaveis
- Devolucao/destruicao sem excecao explicita de retencao (provavelmente implicita, mas deve ser adicionada)
- Clausulas incomuns, mas nao prejudiciais
- Clausulas de LGPD presentes, mas incompletas

**Roteamento**: Sinalizar questoes especificas para revisao por advogado. Advogado pode provavelmente resolver com redlines menores em uma unica revisao.
- **Acao**: Advogado pode provavelmente resolver em uma unica revisao

#### VERMELHO -- Questoes Significativas

**Um ou mais** dos seguintes estao presentes:
- **Unilateral quando bilateral e necessario** (ou direcao errada para a relacao)
- **Carveouts criticos ausentes** (especialmente desenvolvimento independente ou obrigacao legal)
- **Clausulas de nao-solicitacao ou nao-concorrencia** embutidas no NDA
- **Clausulas de exclusividade ou standstill** sem contexto comercial apropriado
- **Prazo irrazoavel** (10+ anos, ou perpetuo sem justificativa de segredo de negocio)
- **Definicao excessivamente ampla** que poderia capturar informacao publica ou materiais desenvolvidos independentemente
- **Clausula residual ampla** que efetivamente cria licenca de uso da informacao confidencial
- **Cessao ou licenca de PI** escondida no NDA
- **Danos liquidados ou penalidades desproporcionais**
- **Direitos de auditoria** sem escopo ou aviso razoavel
- **Foro altamente desfavoravel** com arbitragem compulsoria
- **Ausencia de clausulas de LGPD** quando dados pessoais sao claramente envolvidos
- **O documento nao e na verdade um NDA** (contem termos comerciais substantivos, exclusividade, ou outras obrigacoes alem da confidencialidade)

**Roteamento**: Revisao juridica completa necessaria. Nao assinar. Requer negociacao, contraproposta com NDA padrao da organizacao, ou rejeicao.
- **Acao**: Nao assinar; requer negociacao ou contraproposta

### Etapa 5: Gerar Relatorio de Triagem

Emitir um relatorio estruturado:

```
## Relatorio de Triagem de NDA

**Classificacao**: [VERDE / AMARELO / VERMELHO]
**Partes**: [nomes das partes]
**Tipo**: [Bilateral / Unilateral (reveladora) / Unilateral (receptora)]
**Prazo**: [duracao]
**Foro de Eleicao**: [comarca]
**Lei Aplicavel**: [jurisdicao]
**Base da Revisao**: [Playbook / Padroes de Mercado]
**Dados Pessoais Envolvidos**: [Sim/Nao]

## Resultados da Triagem

| Criterio | Status | Observacoes |
|---|---|---|
| Obrigacoes Bilaterais | [OK/ALERTA/FALHA] | [detalhes] |
| Escopo da Definicao | [OK/ALERTA/FALHA] | [detalhes] |
| Prazo | [OK/ALERTA/FALHA] | [detalhes] |
| Carveouts Padrao | [OK/ALERTA/FALHA] | [detalhes] |
| Clausulas Problematicas | [OK/ALERTA/FALHA] | [detalhes] |
| LGPD | [OK/ALERTA/FALHA/N.A.] | [detalhes] |
| Foro de Eleicao | [OK/ALERTA/FALHA] | [detalhes] |
| [etc.] | | |

## Questoes Encontradas

### [Questao 1 -- AMARELO/VERMELHO]
**O que**: [descricao]
**Risco**: [o que pode dar errado]
**Base Legal**: [dispositivo legal, se aplicavel]
**Correcao Sugerida**: [linguagem especifica ou abordagem]

[Repetir para cada questao]

## Recomendacao

[Proximo passo especifico: aprovar, enviar para revisao com notas especificas, ou rejeitar/contrapropor]

## Proximos Passos

1. [Item de acao 1]
2. [Item de acao 2]
```

### Etapa 6: Sugestao de Roteamento

Com base na classificacao, recomendar o proximo passo apropriado:

| Classificacao | Acao Recomendada | Prazo Tipico |
|---|---|---|
| VERDE | Aprovar e rotear para assinatura conforme delegacao de autoridade | Mesmo dia |
| AMARELO | Enviar para revisor designado com questoes especificas sinalizadas | 1-2 dias uteis |
| VERMELHO | Encaminhar para advogado para revisao completa; preparar contraproposta ou NDA padrao | 3-5 dias uteis |

Para classificacoes AMARELO e VERMELHO:
- Identificar a pessoa ou funcao especifica que deve revisar (se a organizacao tiver regras de roteamento definidas)
- Incluir resumo breve das questoes adequado para o revisor entender rapidamente os pontos-chave
- Se a organizacao tiver um NDA padrao, recomendar envio como contraproposta para NDAs classificados como VERMELHO

## Questoes Comuns em NDAs e Posicoes Padrao (Mercado Brasileiro)

### Questao: Definicao Excessivamente Ampla de Informacao Confidencial
**Posicao padrao**: Informacao confidencial deve ser limitada a informacao nao publica divulgada em conexao com a finalidade declarada, com exclusoes claras.
**Abordagem de redline**: Estreitar a definicao para informacao que e marcada ou identificada como confidencial, ou que uma pessoa razoavel entenderia como confidencial dada a natureza da informacao e circunstancias da divulgacao.

### Questao: Carveout de Desenvolvimento Independente Ausente
**Posicao padrao**: Deve incluir carveout para informacao desenvolvida independentemente sem referencia ou uso da informacao confidencial da parte reveladora.
**Risco se ausente**: Pode criar alegacoes de que produtos ou funcionalidades desenvolvidos internamente derivaram da informacao confidencial da contraparte.
**Abordagem de redline**: Adicionar carveout padrao de desenvolvimento independente.

### Questao: Nao-Solicitacao de Empregados
**Posicao padrao**: Clausulas de nao-solicitacao nao cabem em NDAs. Sao apropriadas em contratos de trabalho, acordos de M&A, ou contratos comerciais especificos. No Brasil, clausula de nao-concorrencia exige compensacao adequada (principio da reciprocidade, CLT art. 444, CC art. 421).
**Abordagem de redline**: Excluir a clausula inteiramente. Se a contraparte insistir, limitar a solicitacao direcionada (nao recrutamento geral) e definir prazo curto (12 meses).

### Questao: Clausula Residual Ampla
**Posicao padrao**: Resistir clausulas residuais. Se necessaria, limitar a: (a) ideias gerais, conceitos, know-how ou tecnicas retidos na memoria nao auxiliada de individuos com acesso autorizado; (b) excluir explicitamente segredos de negocio e informacao patenteavel; (c) nao conceder licenca de PI.
**Risco se ampla demais**: Efetivamente concede licenca para usar informacao confidencial da parte reveladora para qualquer fim.

### Questao: Obrigacao de Confidencialidade Perpetua
**Posicao padrao**: 2-5 anos a partir da divulgacao ou termino, o que for mais tardio. Segredos de negocio podem justificar protecao enquanto mantiverem o status de segredo.
**Abordagem de redline**: Substituir obrigacao perpetua por prazo definido. Oferecer carveout para segredos de negocio com protecao mais longa.

### Questao: Clausula Penal Desproporcional
**Posicao padrao**: Se houver clausula penal, deve respeitar o limite do CC art. 412 (nao exceder valor da obrigacao principal) e ser proporcional a natureza do NDA. Multas muito altas em NDAs podem ser reduzidas judicialmente (CC art. 413).
**Abordagem de redline**: Reduzir a clausula penal ou substituir por referencia a perdas e danos efetivos.

## Notas

- Se o documento nao e realmente um NDA (ex: rotulado como NDA mas contem termos comerciais substantivos), sinalizar imediatamente como VERMELHO e recomendar revisao contratual completa
- Para NDAs que sao parte de um acordo maior (ex: secao de confidencialidade em MSA), notar que o contexto do acordo mais amplo pode afetar a analise
- Sempre notar que esta e uma ferramenta de triagem e advogado deve revisar quaisquer itens sobre os quais o usuario tenha incerteza
- Verificar conformidade com sigilo profissional (OAB) quando aplicavel
