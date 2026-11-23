# Nota de revisão: modelo

Arquivo idêntico em `legal-br/references/` e em `multiagente-consensual/skills/redacao-juridica-consensual/references/`.

Toda versão entregue (limpa + comparativo) vai acompanhada de uma nota curta, em Markdown, com as seções abaixo, nesta ordem. No modo conciso, cada seção cabe em poucas linhas; no profundo, as tabelas são completas. Seção sem conteúdo sai com "nada a registrar". Não apague a seção.

```markdown
# Nota da revisão vNN: <motivo em poucas palavras>

**Modo:** conciso | profundo. **Base do comparativo:** vMM (última aprovada). **Autor das marcas:** "Revisão vNN".
**Métricas:** palavras A → B (x %); parágrafos numerados A → B; faixa de extensão mín.–máx.; páginas N (limite do perfil: L).

## O que mudou
Uma linha por alteração de conteúdo, com o parágrafo (numeração da versão nova) e o motivo.

## Pontos de revisor externo: veredito
| # | Ponto (com a numeração do revisor) | Veredito | Motivo / fonte |
|---|---|---|---|
| 1 | … | acolhido · em parte · recusado · decisão já tomada | página, dispositivo ou resultado de script |

## Acréscimos materiais e fonte
Tabela de `inventario_fatos.py`, com a coluna "fonte (página)" preenchida; supressões justificadas.

## Densidade (quando houve condensação)
Tabela de `medir_densidade.py`: parágrafos, palavras, média por frase e frases longas, antes e depois.

## Detalhes retirados
Lista do que saiu do corpo, com o destino de cada item: segue no anexo, segue na lista de diligências ou ficou **só nesta nota**. Indicar a versão completa preservada.

## Conferências automáticas
Seção gerada por `conferir_versao.py` (hashes, páginas, pré-auditoria, remissões, inventário, refutadas, decisões, densidade, pontas soltas, integridade).

## Decisões pendentes do usuário
Numeradas, cada uma com a consequência de decidir num sentido e no outro.
```

## Regras
1. **Veredito com fonte.** Recusa exige fonte ou resultado de script, nunca preferência. Ponto que contraria o `decisoes.json` do caso recebe "decisão já tomada" e vai às pendências só se o usuário quiser reabrir.
2. **Numeração do revisor.** Quando a tabela do revisor usar outra numeração, diga qual e por quê (resultado de `conferir_achados_externos.py`), e dê os exemplos na numeração do documento.
3. **Hash.** Se o revisor declarar hash diferente do entregue, registre na primeira linha da seção de vereditos.
4. **Sem mérito novo na nota.** O que muda o parecer vai ao parecer. A nota registra e remete.
5. **Refutadas.** Todo ponto refutado nesta rodada vai ao `refutadas.json` do caso, com padrão, motivo, forma correta e fonte.

6. **Número conferido antes de ir à nota.** Contagens de parágrafos por seção, palavras, páginas e marcas vêm de script rodado sobre o arquivo final, não de estimativa; se o arquivo foi regerado, os números da nota são refeitos.
7. **Achado de revisor que é artefato de extração.** Fórmula "corrompida", espaçamento irregular e palavras coladas costumam vir da leitura de DOCX com marcas pendentes ou de símbolos perdidos. Conferir no documento antes de corrigir e registrar o veredito; para o revisor externo, enviar sempre a versão limpa.
