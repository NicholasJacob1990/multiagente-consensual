---
name: resposta-juridica
description: "Redigir respostas juridicas padronizadas para consultas internas, solicitacoes de areas de negocio, ou comunicacoes externas. Use ao receber consultas sobre LGPD, contratos, trabalhista, compliance, ou ao padronizar respostas da equipe juridica."
argument-hint: "<consulta ou tema>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /resposta-juridica -- Respostas Juridicas Padronizadas

Redigir resposta para: @$1

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica.

## Discovery de MCPs
- **Acervo local (PRIMEIRO)**: MCP `qmd` (`mcp__qmd__query`) e, quando disponivel,
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/busca_acervo.py" search --consulta "TERMO"`
  -- doutrina/cadernos ja sistematizados. Material nao verificado em fonte primaria;
  protocolo: `${CLAUDE_PLUGIN_ROOT}/references/acervo-local.md`
- **brlaw MCP**: Se disponivel, fundamentar com jurisprudencia
- **senado MCP**: Se disponivel, verificar atualizacoes legislativas

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Classificar a Consulta
1. **Origem**: Area de negocio, cliente, externo
2. **Tema**: LGPD, contrato, trabalhista, compliance, societario, tributario
3. **Urgencia**: Imediata, normal, informativa
4. **Formato**: E-mail, parecer curto, nota tecnica

### Etapa 2: Templates por Area

**LGPD**: Resposta a titular, consulta interna sobre base legal, resposta a ANPD, notificacao de incidente
**Contratual**: Aprovacao com/sem ressalvas, rejeicao de clausula, resposta a notificacao extrajudicial
**Trabalhista**: Consulta sobre desligamento, jornada, beneficios, resposta a MPT
**Compliance**: Brindes/hospitalidade, canal de denuncias, conflito de interesses

### Etapa 3: Redigir

```
**De**: Departamento Juridico
**Para**: [destinatario]
**Assunto**: RE: [tema]
**Data**: [data]
**Classificacao**: [Confidencial / Interno]

Prezado(a) [nome],

Em resposta a sua consulta de [data] sobre [tema]:

## Analise
[Resposta fundamentada com legislacao]
**Base legal**: [artigos]

## Orientacao
[Recomendacao pratica]

## Ressalvas
[Condicoes ou limitacoes]

Atenciosamente,
Departamento Juridico
```

### Etapa 4: Revisar
- [ ] Legislacao citada atualizada
- [ ] Linguagem adequada ao destinatario
- [ ] Sem compromisso juridico inadvertido
- [ ] Classificacao de confidencialidade correta
