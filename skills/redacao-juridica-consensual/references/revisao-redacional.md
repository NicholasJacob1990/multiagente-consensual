# Revisão de redação sem mérito

Modo para melhorar a forma de documento jurídico maduro — parecer, peça, minuta normativa, anexo de redações — sem tocar no conteúdo. Usar quando o usuário pedir "melhorias de redação", "tornar mais claro e fluido", "técnica legislativa" ou revisão de coesão, e não auditoria ou nova versão de mérito. A auditoria cega devolve decisão e notas; este modo devolve texto proposto, trecho a trecho.

Para os agentes devolverem só o que todos aprovam, compor com o overlay `emendas_juridicas` (`receitas-juridicas.md`, seção 10), com a classificação `redacional`. Este protocolo vale nos dois casos.

## 1. Escopo travado

Ficam como estão: conclusões e classificações; prazos, competências, requisitos e efeitos; remissões e citações normativas; numeração de parágrafos e dispositivos; trechos travados e decisões expressas do usuário. Erro de mérito notado durante a revisão vai a uma lista própria, sem reescrever. A divisão e a fusão de parágrafos, quando pedidas, seguem a seção 5.

Em minuta oficial revisada com controle de alterações, preferir propostas nos dispositivos já alterados ou acrescidos. Dispositivo que está como no original só muda com defeito relevante (pontuação de enumeração, concordância, ambiguidade, sinonímia) e, mudando, recebe o comentário "Ajuste de redação (técnica legislativa), sem alteração de conteúdo".

## 2. Briefing das cadeiras

Entregar a cada cadeira o documento integral numerado, as diretrizes da tarefa e, para texto normativo, `tecnica-legislativa.md`. Pedir propostas seletivas — só o que melhora clareza, fluidez, estrutura ou técnica — no formato:

| Campo | Conteúdo |
|---|---|
| `documento` | parecer, minuta, anexo ou outro identificador |
| `local` | número do parágrafo, id do dispositivo ou item do anexo |
| `trecho_atual` | cópia literal, curta e única no documento |
| `texto_novo` | redação completa do trecho |
| `motivo` | uma frase |
| `prioridade` | alta, média ou baixa |

Padrões que costumam render propostas úteis:

- **parecer:** período longo com cadeia de apostos dividido em dois; ordem direta; enumeração em ponto e vírgula com paralelismo; gerúndio e "de modo que" encadeados trocados por período novo com conectivo ("Assim,"); retomada explícita do referente depois da divisão ("Ambos os documentos…"); fecho telegráfico ("Ver Anexo, item 4", "Redações no Anexo, itens 4 e 44") integrado à frase ("…, conforme o Anexo, item 4");
- **minuta normativa e anexo:** os da `tecnica-legislativa.md` — uniformidade de nomes e siglas, pontuação de incisos, "e"/"ou" antes do último, tempo verbal, voz ativa com agente, vestígios de versão anterior.

Usar duas famílias de modelo. Uma costuma propor menos e com mais precisão, a outra cobre mais trechos; a sobreposição é pequena, e a união das duas vale mais que a confirmação mútua.

## 3. Consolidação por trecho

1. **Agrupar** as propostas por `local` normalizado (o mesmo parágrafo pode vir como "parecer 2", "§ 2" ou "2").
2. **Consolidar** cada grupo num texto final: adotar uma proposta, fundir as compatíveis ou recusar. Registrar adotadas, descartadas e o motivo.
3. **Verificar** cada texto final por uma sessão independente que não consolidou: sentido jurídico idêntico, testes de alcance da reescrita (`rubrica-juridica.md`), gramática e limite de palavras. O verificador corrige ou devolve; não aprova por amostragem.
4. **Uniformidade:** depois de todos os trechos, uma passada sobre o conjunto procura nomes, siglas e caixa divergentes e o mesmo dispositivo com redações diferentes em lugares distintos. Montar antes o glossário de termos e siglas do próprio documento.
5. **Limite de palavras:** recontar depois de cada fusão. Contam a marca `(NR)`/`(AC)` e os símbolos `§` e `–`. Mirar cerca de 5 palavras abaixo do teto, para a próxima emenda não estourá-lo.

## 4. Aprovação e aplicação

- **Quadro comparativo** antes de aplicar: por linha, número, local, trecho com inserções em negrito e supressões riscadas, motivo e fonte. O usuário aprova o conjunto ou parte dele.
- **Aplicação** com controle de alterações por cima do documento vigente, com o autor indicado, sem aceitar nem rejeitar revisões de terceiros. Localizar pelo texto, nunca pelo índice.
- **Espelhamento:** a mudança num dispositivo vale, na mesma rodada, para o bloco do anexo, a minuta e as tabelas que o reproduzem; nas tabelas, aplicar coluna por coluna.
- **Conferência final:** validação do DOCX; `espelho_redacoes.py` (anexo × minuta e redação superada citada no parecer); `verificar_remissoes.py conferir` (remissões a parágrafos, itens e dispositivos no parecer, no anexo e nos comentários); limite de palavras; `pre_auditoria_parecer.py --anterior` no parecer; páginas do PDF. Se a revisão dividiu ou fundiu parágrafos do parecer, seguir a conferência por frentes (`verificacao-e-integridade.md`, seção 5) e reconferir as respostas aos comentários.
- **Registro:** guardar as versões anteriores em pasta própria e anotar no relatório de execução as fontes, os números e o que os verificadores corrigiram.

## 5. Reescrita com reestruturação

Quando o usuário pedir reestruturação — texto didático, parágrafos de tamanho variado, divisão ou fusão de parágrafos —, e não só ajustes trecho a trecho, o escopo travado da seção 1 cede apenas quanto à divisão e à fusão de parágrafos, à ordem das frases dentro de cada seção e, em consequência, à numeração. Conclusões, graus de certeza, fatos, números, citações, o destino de cada remissão e os trechos travados continuam como estão; o número das remissões é refeito no passo 4.

1. **Inventariar:** repartir o documento por seção e montar, para cada trecho, o inventário de números, datas, páginas, dispositivos, julgados, nomes e ressalvas.
2. **Reescrever** com frase-tópico, ordem direta, conectivos explícitos e alternância funcional do tamanho dos parágrafos, marcando toda remissão a parágrafo com o número antigo (`[[§N]]`) e registrando, num mapa à parte, os parágrafos de origem de cada parágrafo novo. Extensão do trecho entre 90% e 120% da original; nenhum parágrafo acima de `max_palavras_por_paragrafo`, nem o documento acima do limite de páginas.
3. **Conferir a fidelidade** em sessão independente: inventário item a item, grau de certeza, cobertura de todos os parágrafos de origem, extensão e legibilidade. O revisor corrige e registra o que corrigiu.
4. **Montar e renumerar:** recalcular a numeração e substituir cada `[[§N]]` pelo **conjunto** dos parágrafos novos que tratam da matéria remetida, a partir do mapa de origem (`verificar_remissoes.py mapear --origem` e `renumerar`), nunca pelo "primeiro parágrafo novo que contém N": essa atalho gerou, em caso real, "parágrafos 13 e 13", "90, 105 e 105" e destinos incompletos ("48 e 49" quando a matéria foi para 48 a 50). Quando o conteúdo de N se repartiu, decidir uma a uma, como na divisão de parágrafos (`perfil-parecer-genes.md`, Estrutura, item 5). Nenhum `[[§` pode restar no texto. Depois, fazer a conferência final da seção 4, inclusive `verificar_remissoes.py conferir` (bloqueia número repetido), `pre_auditoria_parecer.py --anterior --mapa-origem`, `inventario_fatos.py` e a conferência por frentes. Em DOCX, montar sobre a lista de parágrafos com chave por índice original (nunca emparelhar listas de tamanhos diferentes) e fechar com `integridade_docx.py`.
4-A. **Juntar sem acumular funções:** a fusão serve a parágrafos de uma frase que dependem do vizinho. Parágrafo que passe a acumular fato, divergência e consequência deve ser dividido de novo (sinal: mais de ~85 palavras com dois grupos de citação ou mudança de data ou tema no meio).
5. **Entregar** comparativo e versão limpa, em lugar da aplicação trecho a trecho da seção 4, com nota do que foi recusado por divergir das fontes ou do corpo.

## 6. Texto sugerido por terceiro e técnica de redação

Quando o usuário trouxer um trecho redigido por outra pessoa ou outro modelo ("este relatório não está melhor?", "o anexo desta minuta não está melhor?"), compare em dois eixos, separadamente:

1. **Forma.** Ordem do raciocínio, fluidez, siglas por extenso, enumeração dos quesitos, tom adequado ao destinatário (petição ao cartório, relatório ao gestor). Aproveite o que for melhor.
2. **Conteúdo.** Cada fato, atribuição e pedido do texto sugerido é conferido como afirmação nova: `checar_refutadas.py` com o registro do caso, `conferir_atribuicao.py` contra a peça da consulente e `checar_decisoes.py` contra as decisões registradas. Casos reais: um anexo "mais bem redigido" pedia baixa e prenotação, que a conclusão desaconselha, e repetia erros já refutados (66/34, "reuniu em si o senhorio"); um relatório "mais fluido" atribuía à consulente "desincorporação", "riscos à governança" e um quesito sobre área que ela não formulou.

Entregue a versão híbrida (forma do texto sugerido, conteúdo conferido), com uma tabela "texto sugerido × o que a fonte diz × versão adotada" na nota. Não substitua o trecho inteiro sem essa conferência.

**Técnicas que as rodadas confirmaram** (complementam a seção 5 e a Etapa 6 do `legal-br:parecer`):
- relatório em ordem narrativa, um parágrafo por passo;
- remissão rotulada nos pontos de virada ("na resposta objetiva (parágrafo 1)");
- glosa do termo técnico na primeira ocorrência do corpo;
- frase que apresenta os rótulos de grupo da conclusão como índice;
- súmulas e dispositivos atribuídos um a um;
- marca vista só na imagem tratada como "a conferir na imagem";
- peça a terceiro sem número de documento interno e com cada pedido compatível com a conclusão;
- parágrafo que passe do teto depois de um acréscimo é enxugado na mesma rodada (`conferir_versao.py` acusa).

## 7. Condensação e pontas soltas
Pedido de "menos denso", "mais enxuto" ou "para leitor não técnico" é reescrita com corte, não revisão de frase. Regras em `estilos-de-redacao.md`, seção 6. Procedimento:

1. **Medir antes:** `medir_densidade.py ATUAL.docx`. Diga ao usuário o volume atual e a meta (palavras e páginas).
2. **Roteiro:** `reescrever_docx.py listar BASE.docx` dá os índices; o roteiro mantém blocos (`=b`, `=n`) e traz os parágrafos novos (`n|`), quadros (`TH|`, `T|`, `TL|`) e blocos reformatados (`p|`). O relatório lista os blocos da base não mantidos: cada um foi reescrito ou cortado de propósito.
3. **Montar e comparar:** `reescrever_docx.py montar` gera a limpa; `word_redline.py compare --base APROVADA.docx --current NOVA.docx --motor nativo` gera o comparativo, já com a conferência de integridade.
4. **Medir depois:** `medir_densidade.py NOVA.docx --anterior ATUAL.docx --meta-reducao N`. Frase mais curta com o mesmo volume não cumpre o pedido.
5. **Costurar:** `conferir_orfaos.py NOVA.docx`. Julgado sem entrada nas Referências e instrução editorial entre colchetes bloqueiam; referência sem citação, verbete órfão e conta com símbolos são alertas a resolver ou justificar.
6. **Registrar:** a nota lista o que saiu e onde ficou (anexo, diligências ou só na nota) e preserva a versão completa.

Mudança de lugar de uma seção inteira (por exemplo, Referências antes do Anexo) aparece no comparativo como exclusão e inserção: avise na nota, para o leitor não tomar a mudança por reescrita.
