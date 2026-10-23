---
name: compliance-check
description: "Verificar conformidade de praticas, processos ou documentos com a legislacao brasileira aplicavel (LGPD, CDC, CLT, Lei Anticorrupcao, Marco Civil, Lei de Licitacoes). Use ao avaliar se uma atividade atende requisitos regulatorios, ao preparar para auditorias, ou ao verificar adequacao a normas setoriais."
argument-hint: "<pratica, processo ou documento para verificar>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /compliance-check -- Verificacao de Conformidade Regulatoria

Verificar conformidade de: @$1

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica. Toda analise deve ser revisada por profissionais habilitados.

## Discovery de MCPs Disponiveis

Antes de iniciar, verificar quais MCPs juridicos estao acessiveis:
- **senado MCP**: Se disponivel, consultar legislacao atualizada
- **dadosbr MCP**: Se disponivel, verificar CEIS/CNEP e dados de transparencia
- **brlaw MCP**: Se disponivel, buscar jurisprudencia sobre a materia regulatoria

Se nenhum MCP estiver disponivel, operar com conhecimento do modelo e informar ao usuario.

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Identificar o Escopo
Determinar o que esta sendo verificado: atividade/processo, documento, ou sistema/tecnologia.

### Etapa 2: Mapear Legislacao Aplicavel

| Area | Legislacao Principal | Orgao Fiscalizador |
|------|---------------------|-------------------|
| **Protecao de Dados** | LGPD (Lei 13.709/2018) | ANPD |
| **Consumidor** | CDC (Lei 8.078/1990) | PROCON, SENACON |
| **Trabalhista** | CLT (DL 5.452/1943), NRs | MPT, MTE |
| **Anticorrupcao** | Lei 12.846/2013, Lei 12.529/2011 | CGU, CADE |
| **Internet** | Marco Civil (Lei 12.965/2014) | CGI.br |
| **Licitacoes** | Lei 14.133/2021 | TCU, TCEs |
| **Ambiental** | Lei 9.605/1998, PNRS | IBAMA |
| **Societario** | Lei 6.404/1976, CC/2002 | CVM (se S.A. aberta) |
| **Lavagem de Dinheiro** | Lei 9.613/1998 | COAF |

Se MCP senado disponivel: consultar atualizacoes legislativas recentes na materia.

### Etapa 3: Checklist por Norma

#### LGPD (se dados pessoais envolvidos)
- [ ] Base legal para tratamento identificada (art. 7o)
- [ ] Registro de operacoes de tratamento (art. 37)
- [ ] Aviso de privacidade adequado (art. 9o)
- [ ] Encarregado (DPO) designado (art. 41)
- [ ] RIPD para tratamento de alto risco (art. 38)
- [ ] Medidas de seguranca (art. 46)
- [ ] Procedimento para direitos dos titulares (arts. 17-22)
- [ ] Contratos com operadores (art. 39)
- [ ] Transferencia internacional, se aplicavel (arts. 33-36)

#### CDC (se relacao de consumo)
- [ ] Informacao clara (art. 6o, III)
- [ ] Direito de arrependimento 7 dias (art. 49)
- [ ] Garantia legal (art. 26)
- [ ] Sem clausulas abusivas (art. 51)
- [ ] SAC acessivel (Decreto 11.034/2022)

#### CLT (se relacao de trabalho)
- [ ] Registro em CTPS (art. 29)
- [ ] Jornada conforme (art. 58)
- [ ] Remuneracao adequada
- [ ] NRs de seguranca cumpridas

#### Lei Anticorrupcao (se interacao com poder publico)
- [ ] Programa de integridade (art. 7o, VIII)
- [ ] Due diligence de terceiros
- [ ] Canal de denuncias
Se MCP dadosbr disponivel: verificar ceis_cnep_lookup para impedimentos.

### Etapa 4: Classificar Achados

| Status | Significado | Acao |
|--------|------------|------|
| **CONFORME** | Atende ao requisito | Documentar evidencia |
| **PARCIALMENTE CONFORME** | Atende em parte | Plano de acao com prazo |
| **NAO CONFORME** | Nao atende | Acao corretiva imediata |
| **NAO APLICAVEL** | Nao se aplica | Justificar |

### Etapa 5: Relatorio

```
## Relatorio de Conformidade
**Data**: [data]
**Objeto**: [verificado]
**MCPs consultados**: [listar]
**Status geral**: [CONFORME / PARCIALMENTE / NAO CONFORME]

## Detalhamento por Norma
### [Norma] -- [STATUS]
| Item | Requisito | Status | Observacao |
|------|-----------|--------|------------|

## Recomendacoes
### Prioridade Alta (acao imediata)
### Prioridade Media (30-90 dias)
### Prioridade Baixa (melhoria continua)
```
