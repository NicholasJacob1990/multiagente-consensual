# Revisão de redação sem mérito

Modo para melhorar a forma de documento jurídico maduro — parecer, peça, minuta normativa, anexo de redações — sem tocar no conteúdo. Usar quando o usuário pedir "melhorias de redação", "tornar mais claro e fluido", "técnica legislativa" ou revisão de coesão, e não auditoria ou nova versão de mérito. A auditoria cega devolve decisão e notas; este modo devolve texto proposto, trecho a trecho.

Para os agentes devolverem só o que todos aprovam, compor com o overlay `emendas_juridicas` (`receitas-juridicas.md`, seção 10), com a classificação `redacional`. Este protocolo vale nos dois casos.

## 1. Escopo travado

Ficam como estão: conclusões e classificações; prazos, competências, requisitos e efeitos; remissões e citações normativas; numeração de parágrafos e dispositivos; trechos travados e decisões expressas do usuário. Erro de mérito notado durante a revisão vai a uma lista própria, sem reescrever.

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
- **Conferência final:** validação do DOCX; `espelho_redacoes.py` (anexo × minuta e redação superada citada no parecer); limite de palavras; `pre_auditoria_parecer.py --anterior` no parecer; páginas do PDF.
- **Registro:** guardar as versões anteriores em pasta própria e anotar no relatório de execução as fontes, os números e o que os verificadores corrigiram.
