# Perfil de parecer GENES/DIJUR — Codemge e Codemig

> Fonte canônica neste repositório: `skills/redacao-juridica-consensual/references/perfil-parecer-genes.md`. Sincronizar as cópias a partir dela.

Perfil consultivo configurável para a unidade indicada. O registro público contém convenções de forma; documentos, versões e históricos de casos concretos permanecem no ambiente do usuário.

## Quando aplicar

Aplicar a pareceres e manifestações consultivas da Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) e da Diretoria Jurídica (DIJUR) da Codemge e da Codemig. Também aplicar quando o usuário pedir "o estilo do rascunho" ou "o padrão GENES".

Instrução expressa do usuário na tarefa prevalece sobre este perfil. Em composição multiagente, levar o perfil ao briefing de redação, de revisão e de auditoria, sem criar dimensão nova de rubrica: as exigências de forma entram como requisitos verificados pelo auditor e pela pré-auditoria (`scripts/pre_auditoria_parecer.py --perfil genes`).

## Parâmetros

| Parâmetro | Padrão | Observação |
|---|---|---|
| `max_palavras_por_paragrafo` | 120 | conferido pela pré-auditoria; acima disso, dividir em ponto de frase. Vale também para cada bloco do Anexo de Redações Sugeridas, contadas a marca `(NR)`/`(AC)` e os símbolos `§` e `–`. O teto não é alvo: o tamanho varia com a matéria, a maioria entre 40 e 90 palavras e poucos acima de 105; a pré-auditoria alerta quando mais de 30% dos parágrafos ficam a menos de 10% do teto |
| `max_paginas` | 15 | o usuário pode ampliar; esse valor pode ser ampliado na tarefa |
| corpo do texto | Times New Roman 10,5 | ver a divergência com o padrão `legal-br` abaixo |
| fecho | "É o parecer, sob censura." | último parágrafo numerado |

Os limites são parâmetros da tarefa, não regras fixas: registrar na prévia o valor adotado e passá-lo à pré-auditoria (`--max-palavras`, `--pdf … --max-paginas`).

## Estrutura

1. **Cabeçalho**, sem número, com rótulo em negrito e conteúdo em redondo, um campo por linha:
   - `PARECER JURÍDICO CONSULTIVO`
   - `PROCESSO SEI Nº:`
   - `INTERESSADA:`
   - `ASSUNTO:`
   - `CONSULENTE:` (nome e cargo de quem assina a consulta)
   - `ÓRGÃO CONSULTIVO:` Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)
2. **`EMENTA CONSULTIVA:`** em caixa-alta, com os enunciados separados por ponto. Termina pela conclusão: "VIABILIDADE JURÍDICA CONDICIONADA…".
3. **Seções** em algarismos romanos, título em negrito e sem número de parágrafo. Exemplos: "I. Relatório e Delimitação da Consulta", "II. Marco Legal, Competência Normativa e Rito de Aprovação", até "Conclusão e Encaminhamentos".
4. **Parágrafos numerados em sequência contínua** do primeiro ao último, inclusive na conclusão, com numeração automática do Word: número alinhado à margem esquerda, tabulação de 1,25 cm até a primeira linha e linhas seguintes na margem. Parágrafo acima de `max_palavras_por_paragrafo` deve ser dividido em ponto de frase que preserve a lógica, sem deixar frase isolada. Espaço depois dos parágrafos numerados: 3 pt. Títulos, cabeçalho, ementa, local e data e assinatura não recebem número.
5. **Remissões internas** "(parágrafo N)": cada item da conclusão aponta exatamente para os parágrafos que tratam do ponto, conferidos por frase-âncora, nunca por faixa aproximada. Toda renumeração é feita por script, com o mapa antigo → novo aplicado às remissões, e conferida pela pré-auditoria com `--anterior`, que acusa remissão inexistente, autorremissão e remissão quebrada pela renumeração. Ao dividir parágrafos, cada remissão ao parágrafo dividido é decidida uma a uma, com a parte que trata da matéria (`verificar_remissoes.py mapear` e `renumerar`), inclusive no Anexo, nos comentários da minuta e nas respostas aos comentários; depois, os intervalos da conclusão são revistos contra o conteúdo e `verificar_remissoes.py conferir` roda sobre o pacote inteiro.
6. **Parágrafo de metodologia** no Relatório (no caso de referência, o § 5), ditado pelo usuário e mantido como trecho travado. Ele declara a natureza técnico-jurídica e opinativa do parecer, a data de corte, o que fica fora do exame (conveniência e oportunidade das opções de gestão; regularidade de atos anteriores) e o método: análise dispositivo por dispositivo, separando em negrito as **correções necessárias (de cunho obrigatório, por afastarem ilegalidade, inconstitucionalidade, violação estatutária ou contradição interna insanável)**, as **obrigações já incidentes por força de norma superior**, a cumprir no edital ou na execução, e as **recomendações de boa técnica, prudência e segurança jurídica (de caráter facultativo ou operacional)**. Adaptar só o objeto e a data de corte.
7. **Conclusão**, nesta ordem:
   - parágrafo que abre com "Pelo exposto", com o juízo de viabilidade condicionada às correções necessárias;
   - quatro grupos, cada um aberto por **rótulo em negrito** no início do parágrafo, com os itens numerados em romanos minúsculos entre parênteses e, em cada item, a remissão "(parágrafo N)":
     - **Correções necessárias.** — o que condiciona a regularidade do texto, separado por documento (regulamento, formulário) quando houver mais de um;
     - **Obrigações já incidentes.** — o que norma superior já impõe, independentemente do texto, a cumprir no edital ou na execução;
     - **Recomendações facultativas.** — boa técnica e prudência, a critério do consulente, indicando o que pode ser feito no edital sem alterar o regulamento;
     - **Providências fora do regulamento.** — atos de outros órgãos (Conselho, Assembleia) ou revisão de outros normativos;
   - providências de instrução a cargo da área consulente, quando houver;
   - restituição dos autos e encaminhamento ao órgão competente.
   Um grupo que se estender por mais de um parágrafo continua sem novo rótulo ("Também são necessárias…").
8. **Fecho e bloco de assinatura**, sempre, nesta ordem e em linhas separadas:
   - "É o parecer, sob censura." (último parágrafo numerado);
   - "Belo Horizonte, [data]." (local e data, sem número);
   - "[Nome do(a) Advogado(a)]" (em negrito);
   - "OAB/MG [INFORMAR]";
   - "De acordo: [Gerente da GENES]";
   - "Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)" (em negrito).

   Os colchetes desse bloco são campos de preenchimento na assinatura e constituem a única exceção à regra de não deixar `[INFORMAR]` no texto. A data do parecer é a da assinatura: lembrar o usuário de atualizá-la.

## Redação

- **Prosa:** jurídica formal e contínua.
- **Sem informações soltas:**
  - nada de listas telegráficas, marcadores ou parágrafo de uma frase isolada;
  - nada de `[CONFIRMAR]`, `[INFORMAR]` ou `[NÃO CONSTA]` no corpo. Cada lacuna vira uma providência descrita em prosa, com o responsável. Exemplo: "convém que a Secretaria de Governança confirme…".
- **Itens dentro do parágrafo:** enumerações curtas vão em ponto e vírgula, dentro do próprio parágrafo.
- **Redação substitutiva:** proposta entre aspas, no próprio parágrafo, precedida de "Sugere-se a redação:" ou "Sugere-se para o art. N:". Com várias redações para a mesma norma, levá-las a um Anexo de Redações Sugeridas, no formato de `tecnica-legislativa.md`, seção 6, e o parecer remete ao item.
- **Anexos nomeados:** o parágrafo de método declara os anexos do parecer pelo nome ("Acompanham este parecer dois anexos: o Anexo de Redações Sugeridas … e a Minuta Revisada …"), e toda remissão repete o nome ("Anexo de Redações Sugeridas, item 13"), sem a forma curta "Anexo, item 13", que se confunde com os Anexos I, II e III da norma examinada.
- **Remissão ao Anexo:** integrada à frase ("…, conforme o Anexo de Redações Sugeridas, item 13"), e não em fecho telegráfico ("Ver Anexo, item 13", "Redações no Anexo, itens 4 e 44"). Quando a remissão vale para o parágrafo inteiro, fica no fim do parágrafo ou em frase própria, para não se prender só à última frase.
- **Precedente:** citado uma única vez, em uma frase, com órgão, número, relator e data do julgamento; nos demais pontos, remeter ao parágrafo em que foi citado. Não transcrever ementa.
- **Natureza do parecer:** é opinativo. Não chamá-lo de "vinculante" e não usar "orientação técnica vinculante".
- **Sem adjetivação confirmatória** ("plena harmonia", "perfeita consonância", "plena viabilidade") quando a conclusão exige ajustes.
- **Calibração:** prazo, calendário e efeito de alteração ainda não feita são estimativas e vêm rotulados como tais ("Trata-se de estimativa, pois o calendário ainda não tem datas"). Não atestar exequibilidade de calendário sem datas civis.
- **Fatos:** separar fato documentado, premissa e recomendação, e não atribuir aos autos o que não consta deles.
- **Dados pessoais:** não nomear terceiros além do consulente.

## Trechos travados

Registrar em `travados.json` (formato da pré-auditoria) e não alterar sem nova autorização do usuário:

- o parágrafo de metodologia;
- o fecho e o bloco de assinatura;
- todo trecho que o usuário ditou ou manteve expressamente contra objeção de auditor (no caso de referência, o "ponto 3" e a redação do § 5).

Objeção de auditor a trecho travado vai ao usuário como dissenso, com a fonte que a sustenta; não entra no texto por iniciativa do redator.

## Extensão e formatação

- **Extensão:** até `max_paginas` páginas A4; conferir no PDF gerado.
- **Página adotada no caso de referência, que espelha o rascunho do usuário:**
  - Times New Roman 10,5;
  - entrelinha 1,5;
  - recuo de 2 cm na primeira linha;
  - texto justificado;
  - margens 3 / 2 / 3 / 2 cm;
  - cabeçalho e ementa com entrelinha 1,15;
  - rótulos da conclusão e destaques do § de metodologia em negrito (`**…**` no Markdown).
- **Divergência a decidir com o usuário a cada parecer.** O padrão de página do `legal-br` (`references/parecer-docx.md`) difere em dois pontos:

  | Item | Caso de referência / rascunho | Padrão `legal-br` |
  |---|---|---|
  | Corpo do texto | 10,5 | 12 |
  | Numeração | automática do Word, número na margem e tab de 1,25 cm | automática do Word |
  | Ementa | cerca de 160 palavras | até 80 palavras (`ementa --max 80`) |

  Antes de formatar, resolver pelo contexto se vale o padrão da casa ou o modelo escolhido; perguntar apenas se persistir diferença material. Com corpo 12, o texto passaria do limite de páginas e precisaria ser enxugado.
- **Gerador do formato:** o script `parecer_genes_estilo.py` do plugin `legal-br` (`${CLAUDE_PLUGIN_ROOT}/scripts/parecer_genes_estilo.py ENTRADA.md SAIDA.docx`), que lê os marcadores `@CAB`, `@EMENTA`, `## `, `@DATA`, `@ASS`, `@ASS+`, `@ASN` e `@ASN+` e `**negrito**`. Ao usar `parecer_docx.py numerar`, os rótulos do cabeçalho GENES precisam estar na regex `NAO_NUMERA`.
- **Versões comparadas:** o usuário aceita DOCX com controle de alterações gerado do Markdown por `scripts/md_redline.py BASE.md ALVO.md SAIDA.docx --autor Nicholas`, que valida nos dois sentidos. O autor das revisões é "Nicholas".

## Verificação e auditoria

- **Fontes:** conferir todo dispositivo em fonte primária — Planalto, ALMG (texto atualizado), portal da Codemge (estatutos, políticas e regimentos) e informativos do STF e do STJ. Para cada dispositivo da Constituição mineira ou de lei estadual que o parecer interprete, procurar no início a orientação da AGE-MG (pareceres normativos no portal da Advocacia-Geral); o Parecer AGE nº 16.188/2020 só apareceu na auditoria final e contrariava um parágrafo inteiro. Ler a **íntegra** dos normativos internos da pasta `fontes/` antes de atribuir competência ou afirmar que um artigo não trata do tema, e varrer os termos da controvérsia com `varrer_fontes.py` (verificação e integridade, seção 6). Preparar o adendo com o texto integral e o localizador de cada artigo citado; auditores sem o texto literal tendem a acusar como inexistentes dispositivos verdadeiros, e redatores com resumo tendem a negar incisos que existem.
- **Antes de cada auditoria:** `pre_auditoria_parecer.py MINUTA.md --perfil genes --travados travados.json --pdf MINUTA.pdf --max-paginas N`, com `--anterior` depois de qualquer inserção. Zero bloqueantes antes de gastar a auditoria. Com Anexo e minuta revisada, rodar também `verificar_remissoes.py conferir` e `espelho_redacoes.py`.
- **Respostas aos comentários:** a cada rodada, exportar os comentários com o trecho ancorado (`exportar_comentarios.py`) e reconferir as respostas do autor contra o texto atual (rubrica, controles por tipo). No pacote de auditoria, incluir essa exportação (`pacote_auditoria.py montar --comentarios`), para o auditor poder certificá-las.
- **Pacote:** `pacote_auditoria.py montar` com dossiê, adendo e minuta; a resposta tem de repetir o hash (`pacote_auditoria.py verificar`). Atualizar o anexo a cada versão: o Codex já auditou duas vezes um anexo desatualizado.
- **Auditoria cruzada:** salvo instrução atual do usuário, a auditoria cega final usa o Gemini 4 Argon (`agy -p … --model gemini-4-argon-high --print-timeout 0 --output-format text`, em diretório isolado) e, quando o usuário rodar, o Codex/GPT com o prompt e o anexo de `auditoria_gpt/`. Uma família aprovou o que a outra barrou (repetição de precedente, contradição entre parágrafos, alcance de vedação, decisor de recurso). O `agy` não oferece `xhigh` para o Argon: usar `high` e avisar. Verificar a disponibilidade e a autenticação da rota antes de usá-la, com prompt mínimo e tempo limite (verificação e integridade, seção 7): o CLI `gemini` antigo foi descontinuado para contas individuais (`IneligibleTierError`); o `agy -p` espera todos os MCPs conectarem e trava se um deles cair (o `--settings` não aceita `mcpServers`; `agy mcp disable NOME` muda a configuração permanente, só com autorização, e deve ser revertido); "Your AI credits balance is too low" (429) é falta de saldo, não do pacote. O Grok oficial (`grok -m grok-4.7 --reasoning-effort xhigh -p …`) narra o andamento antes da linha do hash.
- **Créditos:** rodadas intermediárias em `medium` ou só com as diferenças (`pacote_auditoria.py montar --anterior`); sondar a rota com prompt mínimo antes de pacote grande; se o Antigravity responder 429 por saldo, gerar o pacote em arquivo único para o usuário colar no app do Gemini.
- **Achados de auditor:** são hipóteses até a conferência na fonte. Rejeitar sugestão que contrarie o texto literal da fonte ou trecho travado e registrar o motivo. Depois de corrigir, reauditar o novo hash. Para buscar nota-alvo, pedir antes o diagnóstico do que separa a versão da nota (ver `../loop-debate-agentes/references/custo-e-creditos.md`).
- **Melhorias consensuais:** para refinar minuta madura, usar o overlay `emendas_juridicas` (receitas, seção 10) com `--tipo-documento parecer`: as classificações das emendas são as quatro da conclusão mais `redacional`, os agentes propõem e votam às cegas, debatem uma vez e só entram as emendas em que todos concordam, depois da adesão ao conjunto.
- **Melhorias de redação:** quando o usuário pedir revisão de redação, e não auditoria, seguir `revisao-redacional.md` (referência da Redação Jurídica Consensual): propostas de duas famílias, consolidação e verificação por trecho, passada de uniformidade, quadro comparativo para aprovação e aplicação com controle de alterações, espelhada na minuta e no Anexo.
- **Trabalho em paralelo:** ler as versões compartilhadas autorizadas e gravar os próprios resultados em pasta isolada, preservando arquivos de outras sessões.

## Armadilhas verificadas (Codemge/Codemig, outubro de 2026)

Observações jurídicas datadas do caso de referência, não convenções da casa: reconferir na fonte vigente antes de reutilizar em outro parecer.

- **Fundamento constitucional:** a participação dos empregados na gestão está no art. 7º, XI, da CF. O art. 173, § 1º, IV, trata de acionistas **minoritários**.
- **Lei 12.353/2010:** aplica-se às estatais da União (Lei 13.303, art. 19, § 1º), não à Codemig. A PC-011 a excluiu em 14/10/2020.
- **Comitê de elegibilidade:** está no art. 10 da Lei 13.303, não no art. 24. O CAE é opinativo (Estatuto da Codemig, art. 40, § 6º, XXXV; RI-CAE, item 8.6), e a Junta Eleitoral não revê o mérito dessa análise; a impugnação de eleitor sobre requisito legal é decidida pela Junta (art. 31 da minuta) com manifestação técnica do CAE.
- **Eleição de administradores:** é competência da AG (LSA, art. 122, II; Estatuto, art. 22), não apenas da AGO do art. 132.
- **Participação remunerada em conselhos:** a vedação de mais de dois conselhos é do art. 20 da Lei 13.303 e alcança conselhos de administração e fiscal, não comitês.
- **Prazo de gestão (Decreto 47.154):**
  - art. 21, § 2º: contam os períodos há menos de dois anos;
  - art. 21, § 4º, na redação do Decreto 49.239/2026: retorno após um ano;
  - PC-011, art. 7º, e RCA, item 5.3: dois anos;
  - o caput do art. 21 fala em "regras mínimas", o que admite regra interna mais rigorosa.
- **Recondução:** treinamento (Decreto, art. 40, parágrafo único). As avaliações anuais da PC-011, art. 21, § 2º, regem a proposta de reeleição de indicados pelo acionista; o representante dos empregados só é reconduzido por nova eleição dos pares (Estatuto, art. 25, § 5º), e condicioná-la a avaliações restringiria a garantia do art. 19 da Lei 13.303.
- **Natureza da cadeira e reserva do art. 23, § 1º, da Constituição mineira:** o Parecer AGE nº 16.188/2020 lê a "direção superior", nas estatais, como a soma das cadeiras do Conselho de Administração e da Diretoria, inclusive a do representante. A mesma AGE dirige a reserva ao controlador, na política de indicações, e a tem por atendida por empregado público **de carreira** em qualquer desses órgãos; para o representante não empregado, manda garantir outra vaga. Logo, a reserva não é requisito de elegibilidade nem filtro de concurso. Na Codemig, o eleito é empregado (Estatuto, art. 22, § 1º); se não for de carreira, a reserva é assegurada em outra cadeira: pelo Acionista Controlador, na eleição dos conselheiros, ou pelo Conselho, na dos Diretores. Não escrever que a cadeira "não é de direção superior" (versão anterior desta armadilha, superada). A força vinculante do parecer da AGE para a estatal está por verificar.
- **Quem elege quem:** a AG elege e destitui os conselheiros (LSA, art. 140; Estatuto, art. 22, caput), e o controlador elege a maioria (art. 22, § 5º); o Conselho elege os Diretores (Estatuto, art. 30; PC-011, art. 22). O CAE só opina, para auxiliar os acionistas (RI-CAE, itens 8.1 e 8.6), e a análise de elegibilidade do conselheiro é informada aos acionistas antes da AG (PC-011, art. 21, § 3º): óbice controverso depois da homologação aguarda a deliberação da AG.
- **Carreira, efetivo e confiança:** o Estatuto separa o pessoal efetivo, contratado por concurso (art. 45), do quadro de funções de confiança, assessoramento, assistência, consultoria ou chefia (art. 46), e menciona empregos comissionados (art. 49). "Empregado público de carreira" aponta para o art. 45; "vínculo permanente" (Decreto 47.154, art. 26, III) é outra coisa. Nada disso restringe a candidatura, que é de empregado ativo (Estatuto, art. 22, § 1º; RCA, item 5.9), salvo a vedação ao comissionado sem vínculo permanente.
- **Requisitos e vedações do administrador:**
  - a dispensa do art. 17, § 5º, da Lei 13.303 é faculdade e não está no Decreto, que exige o art. 25 também do representante dos empregados (§ 6º);
  - a lista de formações do art. 55 do Decreto é preferencial, não fechada;
  - experiências de alíneas distintas não se somam (art. 25, §§ 2º e 3º);
  - a lista do TCE-MG não exclui automaticamente, mas a Lei 13.303, art. 17, III, incorpora a LC 64/1990, art. 1º, I, "g" (contas rejeitadas com ato doloso de improbidade, por oito anos).
- **DDI (IN 076/2026):**
  - o art. 11, V, admite leitura de obrigatoriedade para o eleito; o art. 12, § 1º, V, prevê a DDI por demanda;
  - o art. 18, § 1º, **tem** incisos I a III; o inciso I prevê o esclarecimento no próprio procedimento de DDI. O resumo do dossiê os omitia, e uma versão chegou a negá-los;
  - solução adotada (novembro de 2026): DDI do eleito por demanda (art. 12, § 1º, V, modalidade específica para eleição de conselheiros), nos critérios dos demais conselheiros; o regulamento declara que não a torna obrigatória, sem afirmar que a IN a dispensa, e não a converte em requisito dos inscritos. Não escrever "facultativa" sem ressalva: "o regulamento não torna obrigatória a solicitação", sem afastar eventual incidência do art. 11, V;
  - os anexos do art. 27 não estão no PDF, e o Anexo II é voltado a contratações.
- **Competência para controvérsias eleitorais:** citar o CC 164.709/MG (STJ, Segunda Seção) uma única vez e remeter ao parágrafo nas demais menções; a duplicação foi barrada em auditoria.
- **Comissão de Empregados:** tem competência expressa para indicar dois membros da Junta (Regimento Interno, art. 60, VIII). O art. 22 do RI trata do recrutamento amplo apenas dos Vice-Presidentes não estatutários.
- **Lei 15.177/2025 (art. 19-A da Lei 13.303):** a reserva para mulheres é do CA como um todo, e o art. 5º impede o colegiado de deliberar se ela for descumprida. Não restringir a eleição dos empregados por gênero.
