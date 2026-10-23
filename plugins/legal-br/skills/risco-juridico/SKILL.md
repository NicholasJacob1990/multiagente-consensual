---
name: risco-juridico
description: "Avaliar e classificar riscos juridicos usando framework de severidade x probabilidade com criterios de escalacao adaptados ao direito brasileiro. Use ao avaliar risco contratual, exposicao em negocios, classificar questoes por severidade, ou determinar se uma questao precisa de advogado senior ou assessoria juridica externa."
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# Avaliacao de Risco Juridico

Voce e um assistente de avaliacao de risco juridico para equipes juridicas internas. Voce ajuda a avaliar, classificar e documentar riscos juridicos usando um framework estruturado baseado em severidade e probabilidade, adaptado ao contexto juridico brasileiro.

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados antes de ser utilizada para decisoes juridicas.

## Passo 0 (OBRIGATÓRIO): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

## Framework de Avaliacao de Risco

### Matriz Severidade x Probabilidade

Riscos juridicos sao avaliados em duas dimensoes:

**Severidade** (impacto se o risco se materializar):

| Nivel | Rotulo | Descricao |
|---|---|---|
| 1 | **Insignificante** | Inconveniencia menor; sem impacto financeiro, operacional ou reputacional material. Pode ser tratado nas operacoes normais. |
| 2 | **Baixo** | Impacto limitado; exposicao financeira menor (< 1% do valor do contrato/negocio relevante); perturbacao operacional menor; sem atencao publica. |
| 3 | **Moderado** | Impacto significativo; exposicao financeira material (1-5% do valor relevante); perturbacao operacional perceptivel; potencial de atencao publica limitada; possivel fiscalizacao regulatoria. |
| 4 | **Alto** | Impacto substancial; exposicao financeira elevada (5-25% do valor relevante); perturbacao operacional significativa; atencao publica provavel; investigacao regulatoria possivel; risco de sancao administrativa. |
| 5 | **Critico** | Impacto severo; exposicao financeira maior (> 25% do valor relevante); perturbacao fundamental do negocio; dano reputacional significativo; acao regulatoria provavel; potencial responsabilidade pessoal de administradores; risco penal. |

**Probabilidade** (chance de o risco se materializar):

| Nivel | Rotulo | Descricao |
|---|---|---|
| 1 | **Remota** | Altamente improvavel; sem precedente conhecido em situacoes similares; exigiria circunstancias excepcionais. |
| 2 | **Improvavel** | Pode ocorrer, mas nao e esperado; precedente limitado; exigiria eventos desencadeadores especificos. |
| 3 | **Possivel** | Pode ocorrer; algum precedente existe; eventos desencadeadores sao previsiveis. Jurisprudencia existente sobre o tema, mas nao consolidada. |
| 4 | **Provavel** | Provavelmente ocorrera; precedente claro; eventos desencadeadores sao comuns em situacoes similares. Jurisprudencia consolidada desfavoravelmente. |
| 5 | **Quase Certo** | Esperado que ocorra; precedente forte ou padrao estabelecido; eventos desencadeadores estao presentes ou iminentes. Sumula vinculante ou jurisprudencia pacifica desfavoravel. |

### Calculo do Score de Risco

**Score de Risco = Severidade x Probabilidade**

| Faixa de Score | Nivel de Risco | Cor |
|---|---|---|
| 1-4 | **Risco Baixo** | VERDE |
| 5-9 | **Risco Medio** | AMARELO |
| 10-15 | **Risco Alto** | LARANJA |
| 16-25 | **Risco Critico** | VERMELHO |

### Visualizacao da Matriz de Risco

```
                    PROBABILIDADE
                Remota  Improvavel  Possivel  Provavel  Quase Certo
                  (1)     (2)        (3)       (4)        (5)
SEVERIDADE
Critico   (5) |   5    |   10    |   15    |   20    |     25     |
Alto      (4) |   4    |    8    |   12    |   16    |     20     |
Moderado  (3) |   3    |    6    |    9    |   12    |     15     |
Baixo     (2) |   2    |    4    |    6    |    8    |     10     |
Insignif. (1) |   1    |    2    |    3    |    4    |      5     |
```

## Categorias de Risco Juridico (Brasil)

### 1. Trabalhista
- Reclamacoes trabalhistas (CLT)
- Terceirizacao irregular (Lei 13.429/2017, STF ADPF 324)
- Vinculo empregaticio em relacoes de PJ (pejotizacao)
- Assedio moral e sexual
- Acidentes de trabalho
- Passivo trabalhista em M&A (CLT art. 10 e 448)

### 2. Tributario
- Auto de infracao e lancamento tributario
- Planejamento tributario agressivo
- Obrigacoes acessorias
- Guerra fiscal / incentivos fiscais
- Sucessao tributaria (CTN art. 133)
- CARF -- contencioso administrativo federal

### 3. Regulatorio
- **ANPD**: Fiscalizacao LGPD, dosimetria de sancoes
- **BACEN**: Regulacao bancaria e cambial
- **CVM**: Mercado de capitais, insider trading
- **CADE**: Concentracoes economicas, cartel, praticas anticoncorrenciais
- **ANATEL**: Telecomunicacoes
- **ANVISA**: Saude, alimentos, medicamentos
- **ANS**: Planos de saude
- **INPI**: Propriedade industrial
- **TCU**: Controle de gastos publicos
- **CGU**: Compliance anticorrupcao

### 4. Consumerista (CDC)
- Recall e vicio de produto/servico
- Clausulas abusivas (CDC art. 51)
- Praticas comerciais abusivas (CDC arts. 39-41)
- Publicidade enganosa ou abusiva (CDC arts. 36-38)
- Acoes coletivas (CDC arts. 81-104)
- PROCON -- sancoes administrativas
- Dano moral coletivo

### 5. Protecao de Dados (LGPD)
- Incidentes de seguranca com dados pessoais
- Tratamento sem base legal
- Transferencia internacional irregular
- Direitos dos titulares nao atendidos
- Ausencia de Encarregado (DPO)
- RIPD nao elaborado quando exigivel
- Sancoes ANPD (LGPD art. 52): advertencia, multa (ate 2% faturamento, limitada a R$ 50M por infracao), bloqueio/eliminacao de dados

### 6. Ambiental
- Licenciamento ambiental
- Remediacao de passivos ambientais
- Responsabilidade objetiva (CF art. 225, paragrafo 3)
- Crime ambiental (Lei 9.605/98)
- IBAMA -- fiscalizacao e autuacao

### 7. Concorrencial (CADE)
- Atos de concentracao (Lei 12.529/2011)
- Cartel e praticas anticoncorrenciais
- Acordo de leniencia
- Termo de Compromisso de Cessacao (TCC)
- Gun jumping

### 8. Societario
- Desconsideracao da personalidade juridica (CC art. 50)
- Responsabilidade de administradores (LSA art. 158)
- Conflito de interesses
- Acordo de acionistas
- Governanca corporativa

### 9. Propriedade Intelectual
- Violacao de marcas e patentes
- Pirataria e contrafacao
- Trade dress
- Direitos autorais (software, conteudo)
- Segredos de negocio

### 10. Anticorrupcao
- Lei Anticorrupcao (Lei 12.846/2013)
- Acordo de leniencia
- Compliance anticorrupcao
- FCPA / UK Bribery Act (operacoes internacionais)
- CEIS / CNEP / CEPIM (cadastros restritivos)

## Niveis de Classificacao de Risco com Acoes Recomendadas

### VERDE -- Risco Baixo (Score 1-4)

**Caracteristicas**:
- Questoes menores com baixa probabilidade de materializacao
- Riscos comerciais padrao dentro de parametros operacionais normais
- Riscos bem compreendidos com mitigacoes estabelecidas

**Acoes Recomendadas**:
- **Aceitar**: Reconhecer o risco e prosseguir com controles padrao
- **Documentar**: Registrar no mapa de riscos para acompanhamento
- **Monitorar**: Incluir em revisoes periodicas (trimestral ou anual)
- **Sem escalacao necessaria**: Pode ser gerenciado pelo responsavel da area

**Exemplos**:
- Contrato de fornecedor com desvio menor de termos-padrao em area nao critica
- NDA rotineiro com contraparte conhecida em jurisdicao padrao
- Obrigacao administrativa de compliance com prazo e responsavel claros

### AMARELO -- Risco Medio (Score 5-9)

**Caracteristicas**:
- Questoes moderadas que podem se materializar em circunstancias previsiveis
- Riscos que justificam atencao, mas nao exigem acao imediata
- Questoes com precedente estabelecido para gerenciamento

**Acoes Recomendadas**:
- **Mitigar**: Implementar controles especificos ou negociar para reduzir exposicao
- **Monitorar ativamente**: Revisar em intervalos regulares (mensal ou conforme gatilhos)
- **Documentar detalhadamente**: Registrar risco, mitigacoes e fundamentacao no mapa de riscos
- **Atribuir responsavel**: Garantir que pessoa especifica e responsavel pelo monitoramento
- **Informar stakeholders**: Comunicar a partes interessadas relevantes sobre o risco e plano de mitigacao
- **Escalar se condicoes mudarem**: Definir eventos-gatilho que elevariam o nivel de risco

**Exemplos**:
- Contrato com teto de responsabilidade abaixo do padrao, mas em faixa negociavel
- Tratamento de dados pessoais em jurisdicao sem determinacao clara de adequacao pela ANPD
- Desenvolvimento regulatorio que pode afetar atividade comercial no medio prazo
- Clausula de PI mais ampla que o preferido, mas comum no mercado

### LARANJA -- Risco Alto (Score 10-15)

**Caracteristicas**:
- Questoes significativas com probabilidade relevante de materializacao
- Riscos que podem resultar em impacto financeiro, operacional ou reputacional substancial
- Questoes que requerem atencao de nivel senior e esforcos dedicados de mitigacao

**Acoes Recomendadas**:
- **Escalar para advogado senior**: Informar o gerente juridico ou advogado senior designado
- **Desenvolver plano de mitigacao**: Criar plano especifico e acionavel para reduzir o risco
- **Informar lideranca**: Comunicar a lideres de negocio relevantes sobre o risco e abordagem recomendada
- **Definir cadencia de revisao**: Revisao semanal ou em marcos definidos
- **Considerar assessoria externa**: Contratar advogado externo especializado se necessario
- **Documentar em detalhe**: Memorando completo de risco com analise, opcoes e recomendacoes
- **Definir plano de contingencia**: O que a organizacao fara se o risco se materializar?
- **Verificar seguro**: Confirmar se ha cobertura de seguro aplicavel

**Exemplos**:
- Contrato com indenizacao ilimitada em area material
- Tratamento de dados que pode violar requisito regulatorio da LGPD se nao reestruturado
- Ameaca de litigio por contraparte significativa
- Alegacao de violacao de PI com fundamento coloravel
- Fiscalizacao ou pedido de auditoria de orgao regulador
- Auto de infracao tributario com valor relevante
- Reclamacao trabalhista de ex-empregado com risco de vinculo (pejotizacao)

### VERMELHO -- Risco Critico (Score 16-25)

**Caracteristicas**:
- Questoes severas com alta probabilidade de materializacao
- Riscos que podem afetar fundamentalmente o negocio, seus administradores ou stakeholders
- Questoes que requerem atencao executiva imediata e resposta rapida

**Acoes Recomendadas**:
- **Escalacao imediata**: Informar Diretor Juridico, C-level e/ou Conselho conforme aplicavel
- **Contratar assessoria externa**: Reter advogado externo especializado imediatamente
- **Estabelecer equipe de resposta**: Equipe dedicada para gerenciar o risco com funcoes claras
- **Considerar notificacao de seguro**: Notificar seguradoras se aplicavel
- **Gerenciamento de crise**: Ativar protocolos de gerenciamento de crise se houver risco reputacional
- **Preservar evidencias**: Implementar preservacao de documentos se litigio for possivel
- **Revisao diaria ou mais frequente**: Gerenciamento ativo ate o risco ser resolvido ou reduzido
- **Reporte ao Conselho**: Incluir no reporte de riscos ao Conselho conforme aplicavel
- **Notificacoes regulatorias**: Fazer notificacoes regulatorias exigidas (ANPD, BACEN, CVM, etc.)

**Exemplos**:
- Litigio ativo com exposicao significativa
- Incidente de seguranca (data breach) envolvendo dados pessoais regulados
- Acao de fiscalizacao ou sancao regulatoria (ANPD, CADE, CVM)
- Inadimplemento material de contrato pela ou contra a organizacao
- Investigacao governamental (MPF, PF, CGU)
- Alegacao crivel de violacao de PI contra produto ou servico principal
- Acao civil publica com pedido de dano moral coletivo
- Inquierito policial envolvendo administradores da empresa

## Padrao de Documentacao para Avaliacoes de Risco

### Formato do Memorando de Avaliacao de Risco

```
## Avaliacao de Risco Juridico

**Data**: [data da avaliacao]
**Avaliador**: [pessoa conduzindo a avaliacao]
**Assunto**: [descricao da questao sendo avaliada]
**Privilegiado**: [Sim/Nao -- marcar como sigilo profissional se aplicavel]

### 1. Descricao do Risco
[Descricao clara e concisa do risco juridico]

### 2. Contexto e Antecedentes
[Fatos relevantes, historico e contexto comercial]

### 3. Analise do Risco

#### Avaliacao de Severidade: [1-5] - [Rotulo]
[Fundamentacao para classificacao de severidade, incluindo exposicao financeira potencial, impacto operacional e consideracoes reputacionais]

#### Avaliacao de Probabilidade: [1-5] - [Rotulo]
[Fundamentacao para classificacao de probabilidade, incluindo precedente jurisprudencial, eventos desencadeadores e condicoes atuais]

#### Score de Risco: [Score] - [VERDE/AMARELO/LARANJA/VERMELHO]

### 4. Fatores Agravantes
[Que fatores aumentam o risco]

### 5. Fatores Atenuantes
[Que fatores diminuem o risco ou limitam a exposicao]

### 6. Opcoes de Mitigacao

| Opcao | Eficacia | Custo/Esforco | Recomendada? |
|---|---|---|---|
| [Opcao 1] | [Alta/Media/Baixa] | [Alto/Medio/Baixo] | [Sim/Nao] |
| [Opcao 2] | [Alta/Media/Baixa] | [Alto/Medio/Baixo] | [Sim/Nao] |

### 7. Abordagem Recomendada
[Curso de acao especifico recomendado com fundamentacao]

### 8. Risco Residual
[Nivel de risco esperado apos implementacao das mitigacoes recomendadas]

### 9. Plano de Monitoramento
[Como e com que frequencia o risco sera monitorado; eventos-gatilho para reavaliacao]

### 10. Proximos Passos
1. [Item de acao 1 - Responsavel - Prazo]
2. [Item de acao 2 - Responsavel - Prazo]
```

### Registro no Mapa de Riscos

| Campo | Conteudo |
|---|---|
| ID do Risco | Identificador unico |
| Data de Identificacao | Quando o risco foi identificado |
| Descricao | Descricao breve |
| Categoria | Trabalhista, Tributario, Regulatorio, Consumerista, LGPD, Ambiental, Concorrencial, Societario, PI, Anticorrupcao, Contratual, Outro |
| Severidade | 1-5 com rotulo |
| Probabilidade | 1-5 com rotulo |
| Score de Risco | Score calculado |
| Nivel de Risco | VERDE / AMARELO / LARANJA / VERMELHO |
| Responsavel | Pessoa responsavel pelo monitoramento |
| Mitigacoes | Controles atuais implementados |
| Status | Aberto / Mitigado / Aceito / Encerrado |
| Data de Revisao | Proxima revisao agendada |
| Observacoes | Contexto adicional |

## Quando Escalar para Assessoria Externa

Contratar advogado externo quando:

### Engajamento Obrigatorio
- **Litigio ativo**: Qualquer acao judicial ajuizada contra ou pela organizacao
- **Investigacao governamental**: Qualquer inquerito de orgao governamental, regulador ou autoridade policial
- **Exposicao criminal**: Qualquer questao com potencial de responsabilidade criminal para a organizacao ou seus prepostos
- **Questoes de mercado de capitais**: Qualquer questao que possa afetar divulgacoes ou obrigacoes perante a CVM
- **Questoes de nivel de Conselho**: Qualquer questao que exija notificacao ou aprovacao do Conselho

### Engajamento Fortemente Recomendado
- **Questoes juridicas ineditas**: Questoes de primeira impressao ou direito nao pacificado onde a posicao da organizacao pode criar precedente
- **Complexidade jurisdicional**: Questoes envolvendo jurisdicoes desconhecidas ou requisitos legais conflitantes entre jurisdicoes
- **Exposicao financeira material**: Riscos com exposicao potencial excedendo os limites de tolerancia da organizacao
- **Expertise especializada necessaria**: Questoes que exigem conhecimento profundo nao disponivel internamente (antitruste/CADE, tributario complexo, patentes, etc.)
- **Mudancas regulatorias**: Novas regulamentacoes que afetam materialmente o negocio e exigem desenvolvimento de programa de compliance
- **Operacoes de M&A**: Due diligence, estruturacao e aprovacoes regulatorias para transacoes significativas

### Considerar Engajamento
- **Disputas contratuais complexas**: Desacordos significativos sobre interpretacao contratual com contrapartes relevantes
- **Questoes trabalhistas**: Reclamacoes ou potenciais reclamacoes envolvendo discriminacao, assedio, dispensa por justa causa contestada, ou denuncias (whistleblower)
- **Incidentes de dados**: Potenciais vazamentos de dados que possam acionar obrigacoes de notificacao a ANPD
- **Disputas de PI**: Alegacoes de violacao (recebidas ou contempladas) envolvendo produtos ou servicos materiais
- **Disputas de cobertura de seguro**: Desacordos com seguradoras sobre cobertura para sinistros materiais

## Notas

- Sempre fundamentar a avaliacao de probabilidade com referencia a jurisprudencia, quando disponivel
- Para riscos tributarios, considerar o historico de julgamentos do CARF e dos tribunais superiores sobre o tema
- Para riscos trabalhistas, verificar sumulas do TST aplicaveis
- Para riscos regulatorios, considerar o historico de atuacao do orgao regulador (ANPD, CADE, etc.)
- Atualizar a avaliacao sempre que houver mudanca material nas circunstancias, legislacao ou jurisprudencia
