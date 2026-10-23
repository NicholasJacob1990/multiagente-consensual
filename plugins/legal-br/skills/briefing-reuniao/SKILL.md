---
name: briefing-reuniao
description: "Preparar briefing para reuniao juridica com resumo do caso, pontos de discussao, riscos e posicoes recomendadas. Use antes de reunioes com clientes, parte adversa, mediacao, arbitragem ou reunioes internas."
argument-hint: "<contexto da reuniao>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /briefing-reuniao -- Preparacao de Briefing Juridico

Preparar briefing para: @$1

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica.

## Discovery de MCPs
- **brlaw MCP**: Se disponivel, buscar jurisprudencia relevante
- **dadosbr MCP**: Se disponivel, consultar dados de partes
- **tribunais MCP**: Se disponivel, verificar andamento processual

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Coletar Informacoes
1. **Tipo**: Interna, com cliente, com adversa, mediacao, audiencia
2. **Participantes**: Quem estara e em que qualidade
3. **Objetivo**: O que decidir ou avancar
4. **Materia**: Area do direito e questao
5. **Documentos**: Processos, contratos, pareceres anteriores
6. **Historico**: Reunioes anteriores, decisoes tomadas

### Etapa 2: Pesquisar Contexto (se MCPs disponiveis)
- Andamento processual atualizado
- Jurisprudencia recente
- Dados da contraparte

### Etapa 3: Montar Briefing

```
## Briefing -- [Titulo]
**Data/Hora**: [quando]
**Participantes**: [quem]
**Objetivo**: [1 frase]

## Resumo do Caso
[2-3 paragrafos: fatos essenciais, historico, status atual]

## Pontos de Discussao

### 1. [Ponto Principal]
- **Contexto**: [breve]
- **Nossa posicao**: [o que defendemos]
- **Posicao da contraparte**: [o que esperar]
- **Jurisprudencia**: [se pesquisado via MCP]
- **Recomendacao**: [sugestao]

## Riscos
| Risco | Probabilidade | Impacto | Mitigacao |
|-------|--------------|---------|-----------|

## Limites de Negociacao (se aplicavel)
- **Ideal**: [melhor resultado]
- **Aceitavel**: [minimo aceitavel]
- **Inaceitavel**: [o que nao aceitar]

## Perguntas Esperadas
1. [pergunta + resposta sugerida]

## Proximos Passos
1. [acao apos reuniao]
```
