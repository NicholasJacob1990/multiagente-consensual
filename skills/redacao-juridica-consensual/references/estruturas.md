# Estruturas por tipo de documento

Adapte a estrutura à jurisdição, órgão, rito, fase, norma local e pedido confirmado. Não invente formalidades que dependam de informação ausente.

## Pacote multi-artefato

Trate cada parecer, peça ou minuta como documento autônomo com `artefato_id`, tipo, subtipo, finalidade, destinatário, versão e hash próprios. Reutilize o snapshot confirmado de fatos e fontes, mas não reutilize aprovação, resultado deliberativo ou auditoria de outro documento. A mecânica do pacote pertence a `$loop-debate-agentes`; esta referência define somente a estrutura e a consistência jurídicas.

Antes da entrega conjunta:

1. registre a ordem e as dependências entre os documentos;
2. mantenha terminologia, partes, datas, fatos e referências consistentes;
3. confirme que pedidos, conclusões, recomendações e dispositivos não se contradizem;
4. identifique qual documento prevalece quando funções jurídicas diferentes exigirem formulações distintas;
5. produza um manifesto dos canônicos aprovados, sem concatenar ou fundir arquivos por padrão.

Se a alteração de um documento modificar premissa compartilhada, reabra todos os artefatos materialmente afetados. Não reabra itens independentes apenas porque pertencem ao mesmo pacote.

## Parecer jurídico

1. Ementa.
2. Identificação da consulta, consulente e limites do escopo.
3. Relatório dos fatos e documentos, distinguindo alegações, provas e lacunas.
4. Questões jurídicas submetidas.
5. Premissas e data de corte.
6. Marco normativo aplicável e vigência.
7. Jurisprudência pertinente, com contexto, aderência e eventuais distinções.
8. Doutrina relevante, quando confirmada e útil.
9. Aplicação ao caso e alternativas interpretativas.
10. Contra-argumentos, riscos, incertezas e consequências práticas.
11. Conclusão objetiva, respondendo separadamente a cada questão.
12. Ressalvas, providências e recibo de fontes.

Evite parecer meramente confirmatório. Se a posição desejada pelo consulente não for sustentável, diga isso com fundamentação.

## Peça de parte

Inclui petição inicial, contestação, réplica, manifestação, recurso, contrarrazões, memoriais e incidentes.

1. Endereçamento e identificação do processo, somente com dados fornecidos.
2. Qualificação ou referência às partes.
3. Nome e fundamento do instrumento processual.
4. Cabimento, competência, legitimidade, interesse e tempestividade, quando pertinentes.
5. Síntese dos fatos, separando alegação e prova.
6. Questões preliminares, prejudiciais e processuais.
7. Mérito organizado por tese.
8. Enfrentamento das teses contrárias e riscos.
9. Provas existentes e requeridas.
10. Pedidos certos, coerentes e hierarquizados; subsidiários quando autorizados.
11. Valor da causa, fechamento e demais requisitos aplicáveis.

Não crie pedido, renúncia, confissão, fato ou estratégia material sem autorização. Sinalize campos faltantes com marcadores explícitos.

## Minuta decisória

Inclui despacho, decisão interlocutória, sentença, voto e acórdão proposto.

1. Identificação do processo e do ato.
2. Relatório, quando exigido, com posições de todos os interessados.
3. Delimitação das questões a decidir.
4. Admissibilidade, pressupostos e questões preliminares.
5. Fundamentação com contraditório efetivo e exame dos argumentos capazes de alterar a conclusão.
6. Valoração das provas, distribuição do ônus e limites cognitivos aplicáveis.
7. Marco normativo e precedentes, com aderência ao caso.
8. Conclusão fundamentada por questão.
9. Dispositivo preciso, exequível e congruente.
10. Providências processuais, prazos, comunicações, honorários, custas e efeitos, quando cabíveis.

Controle especialmente imparcialidade, fundamentação adequada, vedação a decisão-surpresa, extra/ultra/citra petita e coerência entre razões e dispositivo.

### Pacote de decisão colegiada

Quando a formação colegiada estiver ativa, acrescente ao pacote, sem fundir silenciosamente textos distintos:

1. certidão de julgamento com quórum, regra de resultado, placar e dispositivo;
2. mapa de adesão por proposição essencial, distinguindo resultado, ratio e obiter;
3. opinião principal, quando a modalidade a exigir;
4. votos individuais no `seriatim` ou votos concorrentes/dissidentes nas demais modalidades;
5. proclamação com hashes do artefato julgado, votos e opiniões publicadas.

Em `decisao_colegiada_v2`, acrescente também `decisao/questoes.json`,
`decisao/derivacao.json`, mapa das coalizões por questão, dispositivo derivado,
dispositivo por cadeira e certidão de eventual maioria cruzada. No híbrido,
preserve os atos de confirmação e não publique dispositivo rejeitado.

No `seriatim`, preserve cada voto completo e apresente a convergência real, sem redigir falsa opinião institucional. No `per_curiam`, use autoria institucional impessoal. Na `opinion_of_court`, a opinião principal deve conter somente proposições que atingiram o apoio exigido; fundamentos exclusivos ficam nos votos concorrentes ou dissidentes. Mudança em qualquer texto depois da proclamação exige novo hash e nova apuração.

## Regras comuns de redação

- Prefira linguagem técnica clara, direta e respeitosa.
- Defina siglas e mantenha terminologia consistente.
- Não alongue transcrições de julgados; use trechos estritamente relevantes e contextualizados.
- Vincule cada afirmação decisiva à prova ou fonte correspondente.
- Diferencie regra, precedente vinculante, precedente persuasivo, doutrina e argumento.
- Não afirme unanimidade, pacificação, vigência ou obrigatoriedade sem confirmação.
- Preserve formatação ou modelo do usuário quando fornecido.
- Use `[INFORMAR]`, `[CONFIRMAR]` e `[NÃO CONSTA]` para lacunas legítimas.
