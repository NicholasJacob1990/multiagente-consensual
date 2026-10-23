---
name: verificacao-fornecedor
description: "Realizar due diligence de fornecedor brasileiro: consulta CNPJ, certidoes, impedimentos (CEIS/CNEP), lista suja, processos judiciais e avaliacao de risco. Use ao avaliar novo fornecedor, antes de contratacao, ou em auditorias periodicas de terceiros."
argument-hint: "<CNPJ ou nome do fornecedor>"
---


Nos comandos desta skill, `${CLAUDE_PLUGIN_ROOT}` designa a raiz do plugin `legal-br`. Se o host não definir a variável, localize essa raiz a partir deste arquivo (`../../`) e use o caminho absoluto no comando. A ausência da variável não impede a leitura dos recursos empacotados.

# /verificacao-fornecedor -- Due Diligence de Fornecedor

Verificar fornecedor: @$1

**Importante**: Esta ferramenta auxilia em fluxos de trabalho juridicos, mas nao constitui assessoria juridica.

## Discovery de MCPs Disponiveis

Verificar quais MCPs estao acessiveis e adaptar o workflow:
- **dadosbr MCP**: cnpj_lookup, cnpj_intelligence, ceis_cnep_lookup, lista_suja_lookup, datajud_processos, transparencia_lookup
- **tribunais MCP**: Consulta de processos por parte
- **brlaw MCP**: Jurisprudencia relevante

Se MCP dadosbr NAO estiver disponivel: informar ao usuario e sugerir fontes manuais (Portal da Transparencia, Receita Federal, DataJud).

## Workflow

### Etapa 0 (OBRIGATÓRIA): PDF → Markdown com OCR

Antes de **ler, citar ou analisar** qualquer PDF (anexos, contratos, NDAs, íntegras, doutrina, matrículas, processos SEI), **converta-o para Markdown com OCR** e trabalhe sobre o `.md` gerado, mantendo-o como **cópia citável**:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf"
# grava ARQUIVO.md (OCR automático em páginas escaneadas/garbled) + status JSON; nunca aborta
```

Nunca cite trechos de PDF sem antes gerar o `.md`. O OCR é automático (default `--ocr auto`: escaneados/garbled são corrigidos). Flags e estratégias: `${CLAUDE_PLUGIN_ROOT}/references/pdf-para-md.md`.

### Etapa 1: Identificar o Fornecedor
1. **CNPJ** ou razao social
2. **Tipo de contratacao**: Servicos, produtos, tecnologia
3. **Valor estimado** do contrato
4. **Criticidade**: Fornecedor critico para operacao?
5. **Dados pessoais**: Tera acesso a dados pessoais?

### Etapa 2: Consultas Automatizadas (se MCPs disponiveis)

Se MCP dadosbr disponivel:
1. **cnpj_lookup**: Situacao cadastral, data abertura, capital, CNAE, socios
2. **cnpj_intelligence**: Estrutura societaria, empresas relacionadas
3. **ceis_cnep_lookup**: Empresas inidoneas e punidas → FLAG VERMELHO se positivo
4. **lista_suja_lookup**: Trabalho escravo → FLAG VERMELHO se positivo
5. **datajud_processos**: Volume como reu, tipos predominantes
6. **transparencia_lookup**: Contratos com poder publico

Se MCP tribunais disponivel: buscar processos detalhados.

### Etapa 3: Analise de Risco

| Criterio | Peso | GREEN | YELLOW | RED |
|----------|------|-------|--------|-----|
| Situacao CNPJ | Alto | Ativa, >3 anos | Ativa, <3 anos | Inapta/Baixada |
| CEIS/CNEP | Critico | Sem registros | -- | Qualquer registro |
| Lista Suja | Critico | Sem registros | -- | Qualquer registro |
| Processos judiciais | Medio | <5 como reu | 5-20 | >20 ou execucoes |
| Capital social | Baixo | Compativel | Abaixo do ideal | Incompativel |

### Etapa 4: Relatorio

```
## Due Diligence -- [Razao Social]
**CNPJ**: [numero]
**Data**: [data]
**MCPs consultados**: [listar]
**Classificacao de Risco**: [BAIXO / MEDIO / ALTO / CRITICO]

## Dados Cadastrais
[detalhes]

## Verificacoes de Impedimento
| Verificacao | Resultado | Detalhes |
|------------|-----------|----------|
| CEIS/CNEP | [LIMPO/IMPEDIDO] | |
| Lista Suja | [LIMPO/CONSTA] | |

## Processos Judiciais
[resumo]

## Recomendacao
[APROVAR / APROVAR COM RESSALVAS / REPROVAR]
```

## Notas
- Certidoes negativas devem ser solicitadas diretamente ao fornecedor
- Para contratacoes >R$ 100.000, recomendar due diligence presencial
