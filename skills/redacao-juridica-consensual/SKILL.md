---
name: redacao-juridica-consensual
description: "Elaborar e revisar iterativamente documento jurídico ou pacote de pareceres, peças e minutas decisórias com os modelos escolhidos. Aplica ao loop briefing, fontes oficiais, estruturas, rubrica e portões jurídicos, com consenso configurável, auditoria, controle de alterações nativo em DOCX e formação colegiada seriatim, per curiam ou opinion of the court. Usar para parecer, petição, recurso, decisão, sentença, voto, acórdão, pacote documental ou outra minuta jurídica com crítica, versões, redline Word, colegiado, múltiplos artefatos ou aprovação em consenso."
---

# Redação Jurídica Consensual

Interprete o texto fornecido após `/multiagente-consensual:redacao-juridica-consensual` como o pedido
jurídico completo.

## Execução portátil no plugin

No Cowork, usar `bridge-agentes` apenas para transportar manifestações às CLIs do Mac pela pasta
compartilhada. Resolver o contrato pelo manifesto indicado, pelo manifesto local válido ou pelo
[manifesto empacotado](../../assets/multiagent-manifest.json), nessa ordem. O transporte não altera
fontes, rubrica, revisão profissional, autoria, hashes nem os gates jurídicos desta skill.

Aplicar o perfil jurídico `juridico_consensual_v2` sobre o motor `debate_agents_v1`. Não implementar um segundo loop: `$loop-debate-agentes` governa papéis, modelos, rodadas, ciclos, tentativas, consenso, frequência, versões, hashes, candidatos, canônicos, pacotes, painel, independência, auditoria, parada e compatibilidade. Esta skill acrescenta apenas briefing, fontes, estruturas, rubrica, restrições e portões jurídicos.

Usar `~/.agents/multiagent-manifest.json` para aliases, seats, rotas e o contrato `veredito_consenso_v1`. Esta skill não mantém consenso, roteamento ou estado paralelos.

## Referências obrigatórias

Leia integralmente, nesta ordem:

1. `$loop-debate-agentes` e `../loop-debate-agentes/references/protocolo.md`;
2. `references/protocolo-juridico.md`;
3. `references/receitas-juridicas.md` após identificar a finalidade e antes de propor defaults;
4. `references/estruturas.md` após identificar o documento;
5. `references/rubrica-juridica.md` antes de avaliar ou aprovar.

Quando o pedido envolver acórdão, votos ou decisão colegiada, leia também `../loop-debate-agentes/references/decisao-colegiada.md` antes da confirmação.

Quando houver DOCX de entrada, saída DOCX iterativa ou pedido de controle de alterações, leia também `references/controle-alteracoes-word.md` antes da confirmação. O comparativo Word é um derivado do canônico limpo; não cria consenso nem aprovação próprios.

Use `$consenso` somente quando o modo deliberativo efetivo estiver ativo. Para pareceres, use `legal-br:parecer` quando disponível para pesquisa e estrutura; na ausência, aplique o protocolo de fontes primárias desta skill. Não altere as skills compostas nem Vorbium.

## Resolver a receita jurídica

Resolver uma receita documental entre `parecer_consensual`, `peticao_consensual`,
`recurso_consensual` e `minuta_decisoria`. Tratar `ensemble_juridico` e `pacote_processual` como
overlays opt-in: ativá-los somente por pedido explícito equivalente ao contrato do motor ou por
proposta exibida e confirmada. Não confundir ensemble com consolidações finais independentes nem
com votos colegiados. Esses presets são apenas deltas sobre este perfil; não criam skills, loops,
consensos ou estados paralelos.

Inferir a receita quando o pedido for inequívoco e mostrá-la na prévia única. A instrução explícita
do usuário prevalece sobre a receita; a receita prevalece sobre os defaults jurídicos, e estes
prevalecem sobre os defaults do motor. Não substituir silenciosamente papéis, modelos, limites ou
gates confirmados. Aplicar integralmente `references/receitas-juridicas.md`.

## Contrato herdado

Configure:

```yaml
perfil_base: debate_agents_v1
perfil_dominio: juridico_consensual_v2
```

O motor é a fonte única das regras operacionais. O perfil jurídico pode tornar um requisito mais estrito ou adicionar um gate, mas não redefinir a mecânica nem exceder 20 versões completas por `artefato_id`, o teto excepcional de 36 rodadas globais ou 12 ciclos por tentativa. O padrão comum continua sendo 8 rodadas globais e 2 ciclos; o `ensemble_nxn_v1` profundo usa especificamente 2 ciclos completos e ao menos 6 rodadas globais. A faixa recomendada vai até 18 rodadas/6 ciclos e a extensão excepcional, somente justificada e confirmada, até 36/12. Runs antigos congelados permanecem imutáveis.

Use como defaults jurídicos:

- consenso `estrito + sempre`, estabilidade 2;
- intensidade `comum`, herdando 8 rodadas, 2 ciclos, 6 tentativas/versões por artefato, painel 3, alvo 8,5, piso 7 e auditoria cega 1; o usuário pode configurar de 1 a 20 versões;
- redator original como consolidador iterativo, salvo designação expressa;
- contribuição do revisor em `parecer_apenas` por padrão; permitir `publicar_candidata` para minutas paralelas e `publicar_canonico` somente por autorização expressa, herdando `publicacao_compartilhada` e todos os gates do motor;
- saída `adaptive_up_to_native_max`, herdada do motor: usa somente o necessário e pode chegar ao teto efetivo da rota;
- timeout de 30 minutos por chamada, até 60 minutos somente como exceção justificada; limite total padrão de 3 horas e recomendado de até 6 horas;
- sessões nativas não persistidas por padrão; quando o usuário pedir espelho recuperável na CLI, usar uma por invocação, com checkpoints e retomada para minutas extensas;
- fontes primárias oficiais e revisão profissional obrigatórias;
- auditoria de consistência conjunta em pacote;
- controle de alterações `auto_se_docx_existente`; quando ativo, comparativos incrementais por revisão e comparativo final acumulado da primeira versão para o canônico aprovado.

O perfil jurídico herda integralmente `ensemble_nxn_v1`, inclusive o ensemble profundo. Nesse modo, todos os modelos confirmados podem produzir minutas independentes, revisar cegamente todas as candidatas, replicar e revisar a própria minuta. A seleção ou síntese cria apenas `canonico_selecionado`: o hash exato ainda precisa passar por consenso jurídico, painel, gates de fontes e auditoria cega antes de se tornar o único `canonico_aprovado`. As demais minutas permanecem candidatas auditáveis.

O perfil também herda a formação colegiada. Ativá-la somente para pedido colegiado. Propor `opinion_of_court` como modalidade e `global`/`decisao_colegiada_v1` como método padrão, com adesão por proposição, `ratio_exigida = true` em decisões destinadas a orientar precedentes e publicação de votos concorrentes e dissidentes. Permitir `seriatim` e `per_curiam` por pedido. Ativar `analitico` ou `hibrido`/`decisao_colegiada_v2` somente quando o usuário pedir votação questão por questão ou confirmação do derivado; não inferir de “preliminares” ou “acórdão”. Em simulação brasileira, não suprimir voto vencido: publicá-lo no pacote e preservar seu hash. Maioria apenas no dispositivo ou maioria cruzada sem coalizão aderente ao pacote gera `somente_resultado`, não consenso nem ratio unificada.

São defaults, não comandos rígidos. O usuário pode escolher `com_decisor`, `consultivo` ou `desativado`, as frequências `sempre`, `se_necessario`, `apenas_primeira` ou `nenhum`, outros participantes e limites válidos. Nunca chame maioria, parecer ou decisão de consenso.

## Formar o briefing jurídico

Identifique antes de chamar modelos externos:

- tipo: `parecer`, `peca_de_parte` ou `minuta_decisoria`, e subtipo;
- `artefato_unico` ou `pacote_multi_artefato`; no pacote, finalidade, obrigatoriedade, ordem, dependências e destinatário de cada item;
- jurisdição, órgão, ramo, instância e posição processual ou função institucional;
- finalidade, destinatário, prazo, urgência, sigilo e data de corte;
- fatos alegados, fatos comprovados, lacunas e controvérsias;
- questões jurídicas, resultado pretendido ou dever de imparcialidade;
- documentos, fontes autorizadas, formato de saída e necessidade de DOCX limpo + comparativo com alterações.

Pergunte apenas o indispensável. Não invente nomes, processo, datas, fatos, provas, competência, rito ou posição. Use `[INFORMAR]`, `[CONFIRMAR]` e `[NÃO CONSTA]` quando a lacuna puder permanecer. Em minuta decisória, preserve imparcialidade, contraditório, congruência e fundamentação.

## Construir o conjunto de evidências

- Leia os documentos fornecidos e gere manifesto com caminho, versão e SHA-256.
- Preserve originais; faça OCR quando necessário e disponível.
- Dê aos participantes o mesmo snapshot de evidências e a mesma versão congelada do item avaliado.
- Confirme legislação, atos e precedentes atuais em fonte primária oficial.
- Registre órgão, identificação, relator quando aplicável, datas, trecho, URL ou caminho, data de acesso e hash.
- Separe fato comprovado, alegação, inferência e desconhecido.
- Marque material não confirmado como `[NÃO VERIFICADO — NÃO USAR NA VERSÃO FINAL]`.
- Não envie segredo ou dado pessoal desnecessário a provedor não autorizado.

## Selecionar estrutura e rubrica

Use `references/estruturas.md` para a estrutura do tipo confirmado e `references/rubrica-juridica.md` para notas e gates. O perfil jurídico mantém as cinco dimensões compatíveis com o motor: clareza, profundidade, coerência, precisão conceitual e qualidade da explicação.

O ledger genérico pertence ao motor; acrescente as categorias jurídicas definidas no protocolo, como fonte, vigência, competência, cabimento, tempestividade, legitimidade, contraditório, congruência, pedido/dispositivo e risco.

## Acrescentar os portões jurídicos

Além dos gates efetivos do motor, só aprove o hash exato quando:

- não houver bloqueio jurídico material aberto;
- fatos, provas, normas, precedentes e citações materiais estiverem verificados ou ressalvados de forma incompatível com uso conclusivo;
- competência, cabimento, tempestividade, legitimidade e demais pressupostos pertinentes estiverem enfrentados;
- fatos, fundamentos, pedidos, conclusão e dispositivo forem congruentes;
- argumentos contrários, riscos e incertezas materiais estiverem tratados;
- a estrutura e a rubrica jurídica forem satisfeitas;
- houver auditoria cega do hash final;
- houver revisão profissional antes de assinar, protocolar, enviar ou decidir.

No pacote, o motor governa itens, versões, dependências, canônicos e manifesto. Esta skill acrescenta a auditoria jurídica conjunta: partes, fatos, datas, fontes, premissas, teses, pedidos, conclusões e dispositivos compartilhados não podem se contradizer. A aprovação de um item não é transferida a outro.

## Confirmar sem duplicar a prévia

Use a prévia **Entendi assim** de `$loop-debate-agentes` e acrescente somente:

```text
Perfil de domínio: jurídico consensual v2
Receita documental: parecer_consensual | peticao_consensual | recurso_consensual | minuta_decisoria
Overlays: nenhum | ensemble_juridico | pacote_processual | ambos
Origem da seleção: automática | explícita
Overrides do usuário: nenhum | configuração confirmada
Tipos e subtipos jurídicos:
Jurisdição/órgão/instância:
Posição ou função:
Finalidade e data de corte:
Fontes primárias e documentos:
Portões jurídicos aplicáveis:
Revisão profissional: obrigatória
Consistência jurídica do pacote: ativa | não aplicável
Formação colegiada: não ativa | seriatim | per curiam | opinion of the court
Regra do resultado, quórum e adesão: não aplicável | configuração confirmada
Ratio e votos separados: não aplicável | configuração confirmada
Controle de alterações Word: desativado | automático | ativo
Base do comparativo final: primeira minuta | documento original
Saídas Word: canônico limpo + redline acumulado + redline incremental, se aplicável
Publicação do revisor: parecer apenas | candidatas próprias | canônico controlado
Revisores-publicadores autorizados e turno: não aplicável | configuração confirmada
Timeout por chamada e limite total: 30 min e 3 h | configuração confirmada
Sessões nativas e checkpoints: persistir | descartáveis
```

Mostre a configuração efetiva uma única vez e aguarde confirmação explícita antes de qualquer chamada externa. Não mantenha duas configurações paralelas.

Em runs novos, herdar `persistir_sessoes_nativas: false` do motor; permitir `true` por pedido expresso
quando o usuário quiser espelhos recuperáveis nas CLIs nativas.
Isso cria somente espelhos de trabalho: autos,
fontes, pareceres, minutas, ledger, hashes e artefato canônico continuam na pasta e no run central.
A existência de uma conversa nativa não satisfaz fonte oficial, revisão profissional, consenso,
independência de painel ou auditoria cega.

## Executar e encerrar

Entregue ao motor o briefing, manifesto de fontes, estrutura, rubrica, categorias de objeção e gates jurídicos como `extensoes_dominio.juridico`. O motor executa cada tentativa e cada artefato, inclusive deliberação, consolidação, alternativas, auditoria e manifesto do pacote.

Se `controle_alteracoes_word` estiver ativo, após cada correção substantiva salve primeiro a nova versão limpa e imutável e então gere o comparativo incremental pela ferramenta `scripts/word_redline.py`. Depois que o hash final fechar consenso e gates, publique `minuta-final-limpa.docx` como único canônico e gere `minuta-final-com-alteracoes.docx` contra a base confirmada. A cópia com alterações deve passar pela verificação bidirecional do contrato `legal_word_redline_v1`; alteração manual posterior cria uma nova versão e reabre os gates.

O limite de 20 conta somente versões completas promovidas à cadeia canônica do item, de `v01` a `v20`. Redlines, pareceres e candidatas não promovidas são derivados ou candidatos e não consomem esse contador. Uma síntese, candidata escolhida ou edição manual promovida conta como `v01` se inaugurar a cadeia, ou consome a próxima versão se substituir a minuta corrente. Se `v20` ainda reprovar, não crie `v21`: entregue a melhor minuta como não aprovada e relate os bloqueios jurídicos e dissensos.

Não resumir peça, parecer ou minuta apenas para caber em meta de palavras do debate. Se o documento exigido ultrapassar uma resposta, usar o protocolo de continuação do motor com a mesma cadeira e só congelar o hash jurídico quando todas as seções, pedidos, fundamentos e citações obrigatórios estiverem completos.

Ao encerrar:

- publique no máximo um `canonico_aprovado` por `artefato_id`;
- preserve autoria, intermediários, candidatos, ledger, fontes, hashes e recibos;
- em `com_decisor`, informe `decisão final sem consenso` quando aplicável;
- em `consultivo` ou `desativado`, diga que a aprovação decorre dos gates jurídicos e de qualidade, não de consenso;
- se um gate exigido não fechar, entregue a melhor versão como `não aprovada` e relate o dissenso ponto a ponto;
- não protocole, assine, envie nem profira decisão sem autorização expressa.

## Pedidos naturais aceitos

```text
Claude redige o parecer e Codex critica e verifica fontes; use consenso estrito e até cinco tentativas.

Revise esta minuta por até 20 versões completas. Cada versão deve passar pelos gates jurídicos configurados; pare antes se houver aprovação e não gere v21.

Codex cria a contestação, Gemini revisa e Claude é o auditor; faça debate consultivo apenas se necessário.

Produza um pacote com parecer, petição e minuta de decisão. Use o mesmo snapshot, mas aprovação e auditoria próprias por documento e consistência jurídica conjunta.

Use 10 rodadas e 3 ciclos na petição; no parecer use o padrão 8 e 2.

Claude cria a primeira versão e Gemini consolida as correções seguintes; preserve a autoria inicial.

Claude cria a minuta inicial. Codex e Grok revisam simultaneamente e publicam candidatas próprias; depois Gemini integra a candidata escolhida no próximo canônico e reabre consenso e auditoria.

Claude cria a minuta inicial e Codex atua como revisor-publicador. Autorize Codex a publicar a próxima versão canônica sem nova incorporação por Claude, mas somente contra o hash-base corrente; registre sua autoria e refaça todos os gates jurídicos.

Use ensemble N×N profundo com Claude Opus 5, Codex e Kimi. Dê a todos o mesmo conjunto de autos, fatos, fontes e critérios; cada modelo produz cegamente uma minuta completa. Execute matriz cega 3×3, incluindo autorrevisão cega, e dois ciclos de crítica, réplica e revisão. Cada autor revisa a própria minuta. Preserve as três candidatas e encarregue o Codex, em sessão independente, de selecionar a melhor ou produzir uma síntese fundamentada. A seleção não aprova: submeta o hash exato a consenso estrito, painel independente de três sessões, média 8,5, piso 7, verificação das fontes e auditoria cega final. Se houver bloqueio material ou dissenso relevante, não declare consenso; relate os pontos e encaminhe-os para decisão humana. Publique somente uma minuta canônica aprovada e preserve as demais para auditoria.

Forme um colegiado com Claude, Codex e Grok em modo opinion of the court. Cada modelo apresenta posição inicial, participa de dois ciclos de crítica, réplica e revisão e adere separadamente ao dispositivo e a cada fundamento essencial. Publique a opinião da maioria, votos concorrentes e dissidentes. Se houver maioria somente no resultado, não declare ratio unificada; revise a minuta ou registre o dissenso. Submeta o pacote exato aos gates jurídicos e à auditoria cega.

Claude redige e corrige a minuta; Codex e Grok criticam. Ative o controle de alterações do Word. A cada revisão, preserve a versão limpa e gere um comparativo incremental. Depois de todas as rodadas e loops, publique somente `minuta-final-limpa.docx` como canônico aprovado e `minuta-final-com-alteracoes.docx` como comparação rastreável da primeira minuta com a final. Se eu alterar o redline no Word, trate o resultado como nova versão e refaça consenso e auditoria.
```
