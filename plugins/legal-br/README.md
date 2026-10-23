# Plugin Juridico Brasileiro para Claude Code

Plugin de produtividade juridica para equipes de direito brasileiro, adaptado do [Anthropic Legal Plugin](https://github.com/anthropics/knowledge-work-plugins/tree/main/legal). Automatiza revisao de contratos, triagem de NDAs, elaboracao de pareceres, verificacao de compliance, pesquisa juridica e due diligence de fornecedores -- tudo integrado com MCPs de tribunais brasileiros, legislacao e dados publicos.

> **Aviso Legal**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados (advogados regularmente inscritos na OAB) antes de ser utilizada para decisoes juridicas. Os padroes e referencias legais neste plugin refletem o ordenamento juridico brasileiro. Se voce opera em outras jurisdicoes, customize o playbook em `.claude/legal.local.md` conforme necessario.

## Personas Alvo

- **Advogado Contratualista** -- Negociacao de contratos, gestao de fornecedores, suporte a negocios
- **Advogado de Produto** -- Revisao de produtos, termos de uso, politicas de privacidade, PI
- **Privacidade / Compliance** -- LGPD, CDC, Lei Anticorrupcao, regulamentacao setorial
- **Contencioso** -- Preservacao de documentos, preparacao para audiencias, pesquisa jurisprudencial

## Instalacao

```
claude plugin marketplace add NicholasJacob1990/multiagente-consensual
claude plugin install legal-br@multiagente-local
```

## Inicio Rapido

### 1. Instalar o plugin

```
claude plugin marketplace add NicholasJacob1990/multiagente-consensual
claude plugin install legal-br@multiagente-local
```

### 2. Configurar seu playbook

Crie um arquivo `legal.local.md` onde Claude possa encontra-lo:

- **Claude Code**: Salve no diretorio `.claude/` do seu projeto

```markdown
# Playbook Juridico

## Posicoes de Revisao Contratual

### Limitacao de Responsabilidade
- Posicao padrao: Teto bilateral em 12 meses de fees pagos/a pagar
- Faixa aceitavel: 6-24 meses de fees
- Gatilho de escalacao: Responsabilidade ilimitada, inclusao de danos consequenciais

### Indenizacao
- Posicao padrao: Indenizacao bilateral para violacao de PI e dados
- Aceitavel: Indenizacao limitada a claims de terceiros
- Gatilho de escalacao: Indenizacao unilateral, sem teto

### Propriedade Intelectual
- Posicao padrao: Cada parte mantem PI pre-existente; cliente e titular dos dados do cliente
- Gatilho de escalacao: Clausulas amplas de cessao de PI, work-for-hire para PI pre-existente

### Protecao de Dados (LGPD)
- Posicao padrao: Exigir DPA/Contrato de Tratamento para qualquer tratamento de dados pessoais
- Requisitos: Notificacao de suboperadores, eliminacao ao termino, notificacao de incidentes
- Gatilho de escalacao: Sem DPA, transferencia internacional sem salvaguardas

### Prazo e Rescisao
- Posicao padrao: Prazo anual com resiliacao por conveniencia mediante aviso de 30 dias
- Aceitavel: Plurianual com resiliacao por conveniencia apos periodo inicial
- Gatilho de escalacao: Renovacao automatica sem aviso, sem rescisao por conveniencia

### Lei Aplicavel e Foro
- Preferido: [Sua comarca]
- Aceitavel: Grandes comarcas comerciais (Sao Paulo, Rio de Janeiro, Brasilia)
- Gatilho de escalacao: Jurisdicoes nao padrao, arbitragem compulsoria em sede desfavoravel

## Padroes de NDA
- Obrigacoes bilaterais exigidas
- Prazo: 2-3 anos padrao, 5 anos para segredos de negocio
- Carveouts padrao: desenvolvimento independente, informacao publica, recebida de terceiro
- Clausula residual: aceitavel se escopo estreito
```

### 3. Conectar MCPs juridicos (recomendado)

O plugin funciona melhor com os seguintes MCPs conectados:

| MCP | Funcionalidade | Uso |
|-----|---------------|-----|
| **brlaw** | Jurisprudencia STF, STJ, TST | Pesquisa de precedentes, sumulas, decisoes |
| **dadosbr** | Dados publicos (CNPJ, DataJud, CEIS/CNEP) | Due diligence, consulta processual, verificacao cadastral |
| **senado** | Legislacao federal | Texto de leis, vigencia, projetos de lei |

O plugin degrada graciosamente quando MCPs nao estao disponiveis -- indicara lacunas e sugerira verificacoes manuais.

## Skills

| Skill | Comando | Descricao |
|-------|---------|-----------|
| Revisao de Contrato | `/revisar-contrato` | Analise contratual contra playbook, classificacao de desvios, geracao de redlines |
| Triagem de NDA | `/triagem-nda` | Triagem de NDA contra criterios padrao, classificacao VERDE/AMARELO/VERMELHO |
| Parecer Juridico | `/parecer` | Elaboracao de parecer com pesquisa de legislacao, jurisprudencia e doutrina |
| Avaliacao de Risco | `/risco-juridico` | Framework de severidade x probabilidade, categorias brasileiras, criterios de escalacao |
| Pesquisa Juridica | `/pesquisa-juridica` | Pesquisa integrada em todos os MCPs juridicos com citacoes ABNT |
| Verificacao de Compliance | `/compliance-check` | LGPD, CDC, CLT, Lei Anticorrupcao, regulamentacao setorial |
| Briefing de Reuniao | `/briefing-reuniao` | Preparacao de reunioes com contexto juridico e acompanhamento de acoes |
| Resposta Juridica | `/resposta-juridica` | Templates para respostas a consultas comuns com gatilhos de escalacao |
| Verificacao de Fornecedor | `/verificacao-fornecedor` | Due diligence de fornecedor: CNPJ, CEIS/CNEP, acordos, compliance LGPD |

## Agente

| Agente | Descricao |
|--------|-----------|
| `analista-juridico` | Agente especializado em analise juridica brasileira com acesso a MCPs de tribunais, legislacao e dados publicos |

## Exemplos de Uso

### Revisao de Contrato

1. Receber contrato de fornecedor por e-mail
2. Executar `/revisar-contrato` e fazer upload do documento
3. Fornecer contexto: "Somos o contratante, prazo ate final do trimestre, foco em LGPD e limitacao de responsabilidade"
4. Receber analise clausula por clausula com flags VERDE/AMARELO/VERMELHO
5. Obter linguagem especifica de redline para itens AMARELO e VERMELHO
6. Compartilhar a analise com a equipe

### Parecer Juridico

1. Receber consulta da area de negocios
2. Executar `/parecer` com a questao
3. O skill pesquisa legislacao, jurisprudencia (STF, STJ, TST via brlaw MCP) e doutrina
4. Receber parecer estruturado com Ementa, Relatorio, Fundamentacao e Conclusao
5. Revisar e ajustar com advogado responsavel

### Due Diligence de Fornecedor

1. Area comercial pede onboarding de novo fornecedor
2. Executar `/verificacao-fornecedor CNPJ-do-fornecedor`
3. Obter automaticamente: dados cadastrais, quadro societario, verificacao CEIS/CNEP
4. Ver analise de lacunas: quais acordos existem e quais faltam
5. Checklist de compliance LGPD se o fornecedor tratara dados pessoais

### Pesquisa Juridica

1. Precisar entender posicao jurisprudencial sobre um tema
2. Executar `/pesquisa-juridica "responsabilidade civil por vazamento de dados pessoais"`
3. Receber memorando com legislacao, precedentes do STJ/STF, e doutrina
4. Todas as citacoes em formato ABNT

## Legislacao de Referencia

| Diploma Legal | Sigla | Ambito |
|---|---|---|
| Constituicao Federal de 1988 | CF/88 | Constitucional |
| Codigo Civil (Lei 10.406/2002) | CC/2002 | Civil |
| Codigo de Processo Civil (Lei 13.105/2015) | CPC/2015 | Processual Civil |
| Codigo de Defesa do Consumidor (Lei 8.078/1990) | CDC | Consumerista |
| CLT (DL 5.452/1943) | CLT | Trabalhista |
| Lei Geral de Protecao de Dados (Lei 13.709/2018) | LGPD | Protecao de Dados |
| Marco Civil da Internet (Lei 12.965/2014) | MCI | Digital |
| Lei Anticorrupcao (Lei 12.846/2013) | -- | Anticorrupcao |
| Lei de Licitacoes (Lei 14.133/2021) | -- | Administrativo |
| Lei de Propriedade Industrial (Lei 9.279/1996) | LPI | PI |
| Lei de Direitos Autorais (Lei 9.610/1998) | LDA | Autoral |

## Orgaos Reguladores

| Orgao | Sigla | Ambito |
|---|---|---|
| Autoridade Nacional de Protecao de Dados | ANPD | Protecao de Dados / LGPD |
| Conselho Administrativo de Defesa Economica | CADE | Concorrencia |
| Banco Central do Brasil | BACEN | Financeiro |
| Comissao de Valores Mobiliarios | CVM | Mercado de Capitais |
| Agencia Nacional de Telecomunicacoes | ANATEL | Telecomunicacoes |
| Agencia Nacional de Vigilancia Sanitaria | ANVISA | Saude |
| Instituto Nacional de Propriedade Industrial | INPI | Propriedade Industrial |
| Tribunal de Contas da Uniao | TCU | Controle Externo |
| Controladoria-Geral da Uniao | CGU | Controle Interno |

## Estrutura de Arquivos

```
legal-plugin-br/
+-- .claude-plugin/
|   +-- plugin.json
+-- skills/
|   +-- revisar-contrato/SKILL.md
|   +-- triagem-nda/SKILL.md
|   +-- parecer/SKILL.md
|   +-- risco-juridico/SKILL.md
|   +-- pesquisa-juridica/SKILL.md
|   +-- compliance-check/SKILL.md
|   +-- briefing-reuniao/SKILL.md
|   +-- resposta-juridica/SKILL.md
|   +-- verificacao-fornecedor/SKILL.md
+-- agents/
|   +-- analista-juridico/AGENT.md
+-- hooks/
|   +-- hooks.json
+-- README.md
```

## Personalizacao

### Configuracao do Playbook

Seu playbook e o coracao do sistema de revisao contratual. Defina suas posicoes em `legal.local.md`:

- **Posicoes-padrao**: Termos contratuais preferidos
- **Faixas aceitaveis**: O que pode ser aceito sem escalacao
- **Gatilhos de escalacao**: Termos que exigem revisao senior ou assessoria externa

### Templates de Resposta

Defina templates para consultas comuns. Templates suportam substituicao de variaveis e incluem gatilhos de escalacao integrados.

### Framework de Risco

Customize a matriz de avaliacao de risco para adequar-se ao apetite de risco da organizacao e categorias especificas do negocio.

## Autor

**Nicholas Jacob**

## Licenca

Uso interno. Baseado no [Anthropic Legal Plugin](https://github.com/anthropics/knowledge-work-plugins/tree/main/legal) (licenca original: Apache 2.0 / conforme repositorio original).
