---
name: loop-debate-agentes
description: "Criar ou melhorar um ou vários artefatos relacionados num ciclo iterativo em linguagem natural, com até 20 versões completas por artefato: um agente redige, outros debatem e avaliam, revisores autorizados podem publicar candidatas ou novas versões canônicas controladas, ou N produtores geram candidatos que passam por revisão cruzada N×N. Permite escolher modelos para qualquer papel, publicação compartilhada, prototipação paralela, perfis de domínio, ensemble profundo, decisor, auditoria cega e formação colegiada seriatim, per curiam ou opinion of the court. Usar com /loop-debate-agentes, $loop-debate-agentes, /consenso, ensemble_nxn, protótipo multiagente, decisão colegiada, redação multi-LLM, pacote multi-artefato ou melhoria até nota-alvo."
---

# Loop Debate de Agentes

Interprete o texto fornecido após `/multiagente-consensual:loop-debate-agentes` como pedido completo
em linguagem natural.

## Execução portátil no plugin

Quando instalada pelo plugin `multiagente-consensual`, usar o manifesto explicitamente indicado,
depois o manifesto local válido e, na ausência dele, o
[manifesto empacotado](../../assets/multiagent-manifest.json). No Cowork, transportar cada cadeira e
fase pela skill `bridge-agentes` e pela fila descrita em
[cowork-bridge.md](../../references/cowork-bridge.md). A fila não substitui o motor: tentativas,
versões, hashes, autoria, candidatos, canônico, painéis e auditoria permanecem governados aqui.

Orquestrar por padrão um ciclo de dois agentes: **Redator ↔ Avaliador-crítico**. Quando o pedido combinar deliberação e melhoria, usar o fluxo ampliado: **versão congelada → gate deliberativo configurado → decisão e dissensos → avaliação independente → correção pelo responsável pela consolidação → nova versão e nova deliberação conforme a política**. O redator original é o responsável padrão, mas o usuário pode designar outro consolidador. Interpretar tudo em linguagem natural; não exigir flags.

## Separar os dois controles

Tratar sempre como mecanismos diferentes e combináveis:

| Controle | Função | Saída |
|---|---|---|
| `estrategia_da_equipe` | Define como os agentes colaboram dentro de uma tentativa: sem debate, debate adversarial, consenso, supervisor ou outra estratégia | Proposta consolidada sobre uma versão |
| `ciclo_de_melhoria` | Avalia a proposta e decide se o responsável pela consolidação deve gerar outra versão | Versões sucessivas até aprovação ou parada |

Combinações válidas:

- debate sem loop: deliberar uma vez e entregar;
- loop sem debate: redator produz, verificador avalia e o responsável configurado corrige;
- debate dentro do loop: deliberar e consolidar antes da avaliação externa de cada versão;
- consenso dentro do loop: buscar consenso interno e ainda submeter o artefato aos critérios externos.
- ensemble N×N dentro do loop: N produtores geram candidatos, N revisores avaliam todos os candidatos, cada produtor responde e revisa, e somente depois um candidato selecionado ou uma síntese entra nos gates do loop.

O nome `/loop-debate-agentes` não torna o debate obrigatório. A configuração decide separadamente `estrategia_da_equipe` e `ciclo_de_melhoria`. No perfil `debate_agents_v1`, os dois mecanismos ficam ativos.

## Separar a formação da decisão colegiada

Quando o pedido envolver acórdão, votos, decisão colegiada, `seriatim`, `per curiam` ou `opinion of the court`, resolver também `formacao_decisao_colegiada` como terceiro eixo. Ele define como os votos e fundamentos formam e publicam a decisão; não substitui estratégia, loop, consenso nem métodos de preferência. Maioria, unanimidade apenas no dispositivo e decisão de terceiro nunca equivalem a consenso.

Usar `opinion_of_court` como proposta padrão somente quando a camada colegiada estiver ativa. Permitir `seriatim` e `per_curiam` por pedido. Colher adesões por proposição, separar placar do dispositivo e apoio aos fundamentos, preservar votos concorrentes e dissidentes e bloquear `ratio_exigida` quando houver apenas maioria no resultado. Ler [references/decisao-colegiada.md](references/decisao-colegiada.md) integralmente antes da confirmação e validar configuração e recibo com `collegiate_gate.py`.

## Ser a fonte única das regras operacionais

Este contrato é a fonte de verdade para a mecânica do loop: papéis, tentativas, versões e hashes, candidatos, canônicos, painel, independência, auditoria, parada e compatibilidade. `~/.agents/multiagent-manifest.json` é a fonte única compartilhada para seats, rotas, aliases e semântica do gate `veredito_consenso_v1`. Uma skill de domínio deve declarar `perfil_base = debate_agents_v1`, um `perfil_dominio` e somente defaults mais restritivos, rubrica, evidências, estruturas e portões adicionais. Ela não deve copiar nem redefinir o motor ou o consenso.

O perfil de domínio pode reduzir limites, sugerir intensidade e acrescentar gates; não pode ultrapassar os tetos do motor, mudar o significado de consenso, reutilizar aprovação de outro hash nem relaxar independência ou auditoria. Em conflito, prevalece o motor para a mecânica e o gate mais restritivo para a aprovação. Runs já congelados continuam imutáveis.

## Operar um artefato ou um pacote

Resolver `modo_artefatos` como:

- `artefato_unico`: comportamento compatível, com caminhos na raiz do run;
- `pacote_multi_artefato`: dois ou mais itens autônomos, cada qual com `artefato_id`, finalidade, obrigatoriedade, dependências, caminho, estado e overrides confirmados.

Em pacote, o motor mantém por item versões, hashes, ledger, candidatos, notas, deliberação, auditoria e exatamente um canônico aprovado. O pacote possui snapshot compartilhado opcional e um manifesto dos hashes. Só fica aprovado quando todos os itens obrigatórios passam pelos próprios gates e o gate conjunto configurado passa. Alterar um item invalida o manifesto e reabre apenas ele e os dependentes materialmente afetados; itens independentes não perdem aprovação sem causa registrada.

Exemplos:

```text
/loop-debate-agentes escreva um parecer sobre o caso anexado
/loop-debate-agentes Claude redige e Codex avalia, critica e sugere até aprovar
/loop-debate-agentes você redige; Grok avalia; use 4 tentativas
/loop-debate-agentes Codex redige, Gemini avalia e Antigravity audita no final
/loop-debate-agentes acrescente Claude como segundo crítico e use painel de 3
/loop-debate-agentes melhore este texto; você redige e Claude avalia
/loop-debate-agentes inicie consenso entre @Estrategista, @Oponente e @Revisor; até 4 rodadas por tentativa e 5 tentativas; @Supervisor decide ao final
/loop-debate-agentes faça apenas uma rodada de consenso, sem ciclo de correção
/loop-debate-agentes Claude redige o artefato canônico; Codex critica e pode propor uma alternativa; faça 4 rodadas por versão e até 5 tentativas, com consenso estrito e auditoria cega
/loop-debate-agentes Claude redige a primeira versão, Codex critica e Gemini consolida as versões corrigidas; mantenha Claude como autor inicial
/loop-debate-agentes Claude redige; Codex e Grok revisam em paralelo e publicam candidatas próprias; depois Gemini integra a escolhida no próximo canônico
/loop-debate-agentes permita que Codex, como revisor-publicador, publique diretamente a próxima versão canônica; valide o hash-base e refaça todos os gates
/loop-debate-agentes após o debate, Gemini, Grok e OpenCode produzem consolidações finais cegas; preserve todas e aguarde minha escolha antes de aprovar uma
/loop-debate-agentes Gemini redige, Grok critica e OpenCode revisa; ao final, os modelos que eu indicar produzem candidatas cegas para minha escolha
/loop-debate-agentes use o perfil ensemble N×N profundo com Claude, Codex e Gemini; todos geram, todos revisam todos, faça 2 ciclos e use Grok como juiz
/loop-debate-agentes produza um pacote com relatório e apresentação; aprove cada item separadamente e audite a consistência conjunta
/loop-debate-agentes forme uma decisão colegiada por opinion of the court; apure a maioria por fundamento, publique votos concorrentes e dissidentes e não chame maioria de consenso
/loop-debate-agentes revise esta minuta por até 20 versões completas; pare antes se os gates fecharem e não crie v21
```

Antes de executar, ler [references/protocolo.md](references/protocolo.md). Ele define a configuração persistida, as garantias de independência e a compatibilidade com runs antigos. Quando `perfil = ensemble_nxn_v1`, ler também [references/ensemble-nxn.md](references/ensemble-nxn.md) integralmente antes da confirmação.
Quando `formacao_decisao_colegiada` estiver ativa, ler também [references/decisao-colegiada.md](references/decisao-colegiada.md) integralmente.

## Resolver os papéis

Aplicar estes padrões, salvo pedido explícito:

- redator: o CLI no qual o comando foi iniciado;
- política de consolidação iterativa: `redator_original`;
- publicação do revisor: `parecer_apenas`; `publicar_candidata` ou `publicar_canonico` somente por pedido explícito;
- consolidador designado: nenhum, salvo pedido explícito;
- avaliador-crítico: um único agente que avalia, critica e sugere em todas as tentativas;
- críticos adicionais: nenhum, salvo pedido explícito;
- revisor separado: nenhum, salvo pedido explícito;
- avaliador: Codex quando o redator for Claude; Claude nos demais hosts, salvo coincidência conhecida de modelo/provedor, caso em que usar Codex;
- decisor final: nenhum, salvo pedido explícito;
- auditor: preferir outro modelo/provedor em sessão nova e cega; se não houver alternativa disponível, usar o avaliador em sessão nova, registrar a ausência de independência de modelo e nunca chamá-la de auditoria independente;
- perfil combinado: `debate_agents_v1`;
- tentativas externas no perfil: 6;
- teto do motor: 20 versões completas por `artefato_id`, equivalentes a no máximo 20 tentativas;
- painel de avaliação no perfil: 3 agentes/sessões separados;
- auditoria cega no perfil: 1 sessão nova, salvo painel de auditoria explícito;
- nota-alvo: 8,5 de 10;
- piso por critério: 7,0;
- saída: adaptativa até o teto nativo efetivo de cada rota, sem obrigação de preencher;
- timeout por chamada: 30 minutos; aceitar até 60 minutos somente como exceção justificada;
- limite total do loop: 3 horas por padrão, configurável até 6 horas na faixa recomendada;
- sessões nativas: não persistir por padrão; quando expressamente habilitadas, manter uma sessão separada por invocação e verificar se a CLI confirmou a persistência;
- deliberação: modo e frequência configuráveis; quando o usuário pedir consenso com correção/repetição, usar `estrito + sempre`; nos demais loops, propor `consultivo + se_necessario` e exibir na prévia;
- idioma: o do usuário.

O perfil `ensemble_nxn_v1` é opt-in e não substitui `debate_agents_v1`. Ativá-lo somente quando o usuário disser “ensemble N×N”, “todos geram e todos revisam todos”, “deep ensemble” ou equivalente. Sem participantes indicados, propor N=3 e três cadeiras elegíveis na prévia, mas não chamar nenhuma antes da confirmação.

O padrão “redator = host” vale em todos os CLIs: Claude no Claude, Codex no Codex, Gemini no Gemini, Antigravity no Antigravity, Grok no Grok e OpenCode no OpenCode. Uma escolha explícita pode substituir qualquer padrão. Qualquer participante pode ocupar qualquer papel, inclusive o de consolidador iterativo.

Antes de congelar as cadeiras, ler `~/.agents/multiagent-manifest.json`. Separar sempre seat, modelo pedido e rota usada. A política local exige Claude Opus 5 (`claude-opus-5`) pelo Claude Code, Grok pelo Cursor no modelo fixo `cursor-grok-4.6-high`, Kimi K3 pelo Kimi Code e Gemini 3.7 pelo Antigravity; falha, override incompatível ou manifesto inválido deve pausar e ser informado, nunca provocar fallback cruzado silencioso. Preservar apenas runs históricos já congelados com outra rota. O YAML legado é visão gerada, não autoridade concorrente.

Quando o usuário nomear modelos ou CLIs, usar exatamente os escolhidos nos papéis indicados. Não acrescentar Claude, Codex, o host ou qualquer contraparte por conveniência. Os padrões acima são somente fallback para papéis não informados.

No modo `loop_simples`, sem estratégia de equipe, permitir painel 1. Não aplicar esse valor ao perfil `debate_agents_v1`, cujo padrão é painel 3. Runs existentes preservam o painel congelado.

Não invocar todos os modelos automaticamente. Fixar papéis, modelos, provedores e limites antes da primeira tentativa e não alterá-los silenciosamente no meio do run. Se um modelo não for fixado, registrar que será usado o padrão atual do CLI.

## Preservar a configuração ampliada

O ciclo de dois agentes é o núcleo padrão, não uma remoção das capacidades anteriores. Honrar integralmente configurações com múltiplos críticos, revisor separado, painel ampliado, avaliador e auditor distintos, modelos diferentes por papel ou limites próprios.

Runs existentes mantêm os valores congelados em `meta.json`. Não reduzir painel, remover papel ou trocar modelo de um run iniciado. Em runs novos, ativar os papéis adicionais pedidos em linguagem natural.

## Interpretar e confirmar em linguagem natural

Antes de criar o run ou chamar qualquer modelo externo:

1. Extrair do pedido `perfil_base`, eventual `perfil_dominio`, `modo_artefatos`, itens e dependências, `estrategia_da_equipe`, `ciclo_de_melhoria`, eventual `formacao_decisao_colegiada` com modalidade, regra de resultado, quórum, adesão aos fundamentos, ratio e votos separados, participantes, papéis, redator inicial, política de consolidação iterativa, eventual consolidador designado, eventual matriz ensemble, decisor, rodadas por tentativa, tentativas de melhoria, alvo, piso, painel, política de independência, saída permitida ao revisor, modo de consolidação final, política de escolha, gate conjunto e auditoria.
2. Interpretar menções como `@Estrategista`, `@Oponente`, `@Revisor` e `@Supervisor` como identificadores de agentes configurados no ambiente, não como nomes de CLI. Resolver separadamente agente, papel, CLI, modelo e provedor. Se a associação ainda não estiver configurada, marcar `modelo não fixado` e pedir apenas o dado indispensável.
3. Mostrar este resumo, adaptado ao caso:

```text
Entendi assim
Perfil-base: debate_agents_v1
Perfil de domínio: nenhum
Modo: artefato único
Artefatos e dependências: artefato principal; nenhuma
Estratégia: Consenso com decisão final
Formação colegiada: não ativa | seriatim | per curiam | opinion of the court
Regra do resultado e quórum: não aplicável | regra confirmada
Adesão aos fundamentos e ratio: não aplicável | configuração confirmada
Votos concorrentes e dissidentes: não aplicável | política confirmada
Participantes: Estrategista, Oponente e Revisor
Decisor: Supervisor
Redator inicial: Claude
Correções e consolidação iterativa: redator original
Consolidador designado: nenhum
Rodadas do debate: até 4 por tentativa
Ciclo de melhoria: revisar e repetir até os critérios
Tentativas de melhoria: até 5
Versões completas por artefato: até 5 de um máximo de 20
Meta média: 8,5
Piso por critério: 7,0
Painel externo: 3 avaliações
Independência: automática, com sessões separadas
Auditoria final: cega e independente
Saída por chamada: adaptativa até o teto nativo; sem preenchimento obrigatório
Sessões nativas nas CLIs: não persistir | persistir como espelho não canônico
Saída do revisor: parecer e artefato alternativo permitido
Consolidação final: uma única versão pelo responsável configurado
Artefatos alternativos: preservados, nunca canônicos automaticamente
Saída aprovada: um canônico por artefato; manifesto do pacote quando aplicável
```

No perfil N×N, acrescentar à prévia:

```text
Perfil: Ensemble N×N profundo
Produtores: N cadeiras identificadas
Revisores: N cadeiras identificadas
Matriz por ciclo: N × N = N² pareceres
Autorrevisão: cega e incluída | excluída
Ciclos N×N: 2 por tentativa
Rodadas globais mínimas: 6 por tentativa
Faixa recomendada: até 6 ciclos e 18 rodadas globais
Teto excepcional: até 12 ciclos e 36 rodadas globais, mediante confirmação
Seleção: juiz independente | humana | consolidador designado
Repetição do ensemble: sempre | se necessário | apenas na primeira
Estimativa máxima: chamadas e artefatos por tentativa
```

4. Esperar confirmação explícita do usuário. A confirmação autoriza as chamadas já descritas, sem nova confirmação por tentativa. Até lá, permitir somente inspeções locais de leitura necessárias para resolver o resumo.
5. Se o pedido for uma forma curta, como `/consenso`, `Buscar consenso` ou “peça consenso da equipe sobre este trecho”, preencher os padrões e abrir a mesma confirmação.

“Faça apenas uma rodada de consenso, sem ciclo de correção” resolve `rodadas_por_tentativa = 1`, `tentativas = 1`, `estabilidade = 1` e `corrigir = false`. Nesse modo, entregar acordo provisório ou dissenso da versão atual sem reescrevê-la. O acordo usa saída consultiva, não `resultado = consenso`, e nunca aprova o artefato.

“Aprovado em consenso”, “somente com consenso” ou expressão equivalente resolve `estrategia_da_equipe.tipo = consenso_estrito` e `debate.exigir_consenso_estrito = true`. Um decisor pode orientar correções, mas não substitui o consenso nesse modo.

“X redige e Y consolida/corrige as próximas versões” resolve `consolidacao_iterativa.politica = consolidador_designado` e grava Y em `consolidacao_iterativa.consolidador`. “O próprio redator corrige” resolve `redator_original`. Não confundir essa política, aplicada entre tentativas, com `consolidacao_final`, que controla uma ou várias candidatas ao fim do loop.

“Ensemble N×N” resolve `perfil = ensemble_nxn_v1` e `estrategia_da_equipe.tipo = ensemble_nxn`. “Deep ensemble” ou “ensemble profundo” resolve profundidade `profundo`, com 2 ciclos completos e ao menos 6 rodadas globais por tentativa. “Máximo recomendado” resolve 6 ciclos e 18 rodadas globais. Em casos excepcionais confirmados, o motor pode estender gradualmente até 12 ciclos e 36 rodadas globais por tentativa. Cada cadeira pode emitir uma crítica, uma réplica e uma revisão por ciclo confirmado.

## Executar o ciclo principal

Aplicar `adaptive_output_v1` a todas as cadeiras. Não impor teto global de tokens nem transformar metas de concisão em truncamento duro. Cada manifestação pode terminar antes do teto quando estiver completa; redator, consolidador e geradores de candidatas podem usar até o limite efetivo oferecido pelo modelo na rota escolhida. Como os CLIs não expõem um controle uniforme de `max_output_tokens`, registrar `native_route_ceiling` quando esse for o único controle disponível, sem inventar um número.

Se um artefato completo ultrapassar uma resposta, continuar com a mesma cadeira e modelo, preferindo a mesma sessão, até oito segmentos por padrão ou outro limite confirmado. Persistir cada segmento e montar o artefato somente em fronteiras de seção ou arquivo, sem repetição nem lacuna. `CONTINUATION_REQUIRED`, término abrupto ou ausência de seção obrigatória impedem congelamento, hash final, nota e aprovação até a completude ser verificada. Uma continuação técnica não cria nova rodada nem novo ciclo; uma alteração substantiva posterior cria nova versão e novo hash normalmente.

Uma **tentativa de melhoria** corresponde a uma versão completa e congelada do artefato. Cada tentativa contém:

1. **Versão:** o redator produz a primeira versão; nas tentativas seguintes, o responsável pela consolidação apresenta a versão corrigida.
2. **Estratégia da equipe, quando configurada:** debate, consenso ou supervisão sobre a versão congelada, sem editar o arquivo, produzindo uma proposta consolidada.
3. **Decisão e dissensos:** registrar consenso ou proposta, bloqueadores e pontos ainda controvertidos; o decisor resolve somente matérias sujeitas a julgamento.
4. **Avaliação externa:** o painel independente atribui notas, identifica falhas e fornece sugestões concretas e priorizadas. O painel não herda a posição interna da equipe como nota.
5. **Gate:** se todos os requisitos forem satisfeitos, seguir para a consolidação final configurada e para a auditoria; caso contrário, formar um plano de correção.
6. **Resposta e correção:** o responsável pela consolidação classifica cada sugestão como aceita, aceita parcialmente ou rejeitada, com justificativa breve, e entrega o documento completo corrigido. Essa saída inicia uma nova tentativa, com novo hash e novo gate deliberativo conforme o modo e a política congelados.

Em runs novos, `tentativa_atual` e `versao_atual` avançam juntos: a primeira minuta congelada é `v1`/tentativa 1 e cada correção substantiva cria exatamente a versão/tentativa seguinte. O usuário pode configurar de 1 a 20 versões completas por `artefato_id`; o padrão de `debate_agents_v1` continua 6. Pare assim que os gates fecharem. Não produza `v21`: ao atingir `v20` sem aprovação, encerre como `esgotado`, preserve a melhor versão como não aprovada e informe bloqueios e dissensos.

Pareceres, patches, redlines e candidatos alternativos ou finais não consomem esse contador enquanto permanecerem não canônicos. Quando uma candidata selecionada, síntese ou edição manual entra no fluxo canônico, seu hash conta como uma versão: será `v1` se a cadeia ainda não existir ou a próxima versão se substituir um hash canônico corrente. No ensemble N×N, as revisões internas das famílias candidatas pertencem aos ciclos do ensemble; o contador de até 20 rege a cadeia canônica do `artefato_id`, e a prévia deve estimar separadamente o total de candidatos e chamadas.

Quando a formação colegiada estiver ativa, inserir entre deliberação e avaliação a coleta dos votos finais, a adesão por proposição, a proclamação e a validação determinística do mesmo hash. `DECISAO_COLEGIADA_FORMADA` é apenas um gate intermediário; não equivale a consenso nem a `canonico_aprovado`.

Preservar separadamente a identidade do redator inicial, do consolidador iterativo e a composição do painel durante todo o run. Cada cadeira mantém CLI, modelo, provedor, lente e critérios congelados. Quando o CLI permite, reutilizar somente a sessão daquela cadeira; quando não permite, fornecer à nova sessão o próprio veredito anterior, a resposta do responsável pela consolidação e a versão corrente. Nenhum avaliador edita o documento por força do papel de avaliador; toda alteração canônica pertence ao responsável configurado pela consolidação.

Cada avaliação deve devolver no mínimo:

- notas e veredito;
- acertos principais;
- erros factuais ou conceituais;
- crítica principal;
- sugestões acionáveis em ordem de prioridade;
- confirmação sobre o atendimento das sugestões anteriores.

## Executar o perfil Ensemble N×N

Tratar `ensemble_nxn_v1` como uma estratégia interna do loop, não como aprovação automática:

1. Congelar briefing, fontes, rubrica e `snapshot_sha256` comuns.
2. Fazer N produtores gerarem N candidatos completos e independentes, sem acesso aos demais.
3. Anonimizar autores e distribuir todos os N candidatos a todos os N revisores.
4. Registrar N² pareceres por ciclo quando a matriz completa incluir autorrevisão cega; se ela for excluída, registrar N×(N−1) e não chamar o resultado de matriz N×N estrita.
5. Entregar a cada produtor o agregado anonimizado das críticas ao seu candidato; colher réplica e nova versão completa.
6. Repetir pelo número confirmado de ciclos. Cada ciclo contém crítica → réplica → revisão e consome três rodadas globais.
7. Submeter as candidatas finais ao modo confirmado de seleção. Um juiz pode escolher a melhor candidata ou solicitar síntese, mas não aprová-la.
8. Persistir todas as candidatas, pareceres, réplicas, hashes e procedência. A candidata escolhida ou a síntese recebe estado `canonico_selecionado` e entra no gate deliberativo configurado, painel e auditoria do loop.
9. Se qualquer gate reprovar e a política for `sempre`, iniciar nova tentativa N×N sobre a nova base. Nunca reutilizar parecer ou aprovação de outro hash.

Usar por padrão N=3 após confirmação, profundidade `profundo` com 2 ciclos, até 3 tentativas externas, matriz completa cega, painel 3, alvo 8,5, piso 7 e auditoria cega 1. Aceitar configuração caso a caso. Acima de N=5, mostrar uma confirmação reforçada com custo/tempo e limites operacionais, pois cada ciclo produz N² pareceres.

Estimar chamadas por tentativa como `N gerações + C × (N² críticas + N réplicas + N revisões) + 1 seleção/síntese + painel externo`. Para N=3, C=2 e painel=3, isso resulta em aproximadamente 37 chamadas antes do consenso adicional e da auditoria final. Informar que a combinação de réplica e revisão pelo adaptador pode reduzir as chamadas efetivas sem reduzir as fases lógicas.

Permitir produtores e revisores diferentes, desde que ambos os conjuntos tenham N cadeiras para uma matriz N×N. Se os tamanhos forem diferentes, registrar `ensemble_nxm`, informar a matriz real e nunca rotulá-la N×N. Não substituir cadeira indisponível; pausar ou reduzir somente conforme política previamente confirmada.

Para código com exatamente Claude, Codex e Gemini, o executor pode usar o MCP A2A Mesh como adaptador. Para documentos, outros CLIs/modelos ou rastreabilidade integral, usar a orquestração direta. Em qualquer adaptador, aplicar o contrato de [references/ensemble-nxn.md](references/ensemble-nxn.md); uma síntese devolvida pelo A2A é apenas candidata e precisa dos gates locais.

## Configurar a autoria das correções

Gravar `consolidacao_iterativa.politica` explicitamente em todo run novo:

- `redator_original`: padrão; o autor da primeira versão também responde às objeções e produz todas as versões canônicas seguintes;
- `consolidador_designado`: o redator produz a primeira versão e o modelo/CLI designado responde às objeções, registra as decisões de incorporação e produz as versões canônicas seguintes.
- `publicacao_compartilhada`: o redator e revisores nominalmente autorizados podem publicar versões na cadeia canônica. Resolver e congelar um único `publicador_da_proxima_versao` por tentativa; nunca permitir duas gravações concorrentes no mesmo ponteiro.

Em `consolidador_designado`, registrar agente, CLI, modelo, provedor e sessão. Cada manifesto de versão registra `autor_inicial`, `autor_da_versao` e `base_sha256`. A troca de responsável durante o run exige novo resumo e confirmação; se o designado estiver indisponível, pausar ou aplicar somente o fallback previamente autorizado, nunca retornar silenciosamente ao redator original.

O redator inicial pode continuar participando das réplicas quando isso estiver configurado, mas o consolidador designado assume a decisão editorial e a autoria das versões que produzir. Se o mesmo modelo atuar como consolidador e avaliador, ele não conta como avaliação independente da própria versão; preservar o painel independente ou registrar a redução de separação.

Resolver também `contribuicao_revisor.modo_publicacao`:

- `parecer_apenas`: padrão; pareceres, patches e alternativas permanecem separados do canônico;
- `publicar_candidata`: cada revisor autorizado publica uma candidata imutável em caminho próprio, adequada a trabalho simultâneo e revisão cruzada;
- `publicar_canonico`: ativa `publicacao_compartilhada`; o revisor autorizado pode publicar a próxima versão canônica sem reapresentação pelo redator.

`publicar_canonico` exige pedido explícito, identidade completa em `publicadores_autorizados`, turno congelado, `base_sha256` igual ao canônico corrente, limite de versões disponível e gravação atômica. A publicação cria rascunho canônico, não aprovação: gera novo hash, invalida consenso, notas, decisão e auditoria anteriores e abre nova tentativa. O revisor-publicador não conta como avaliador, painel ou auditor independente da própria versão.

## Manter um único canônico por artefato

Em `artefato_unico`, usar `texto.md` como ponteiro corrente. Em pacote, usar `artefatos/<artefato_id>/texto.md`. No padrão, somente o responsável resolvido por `consolidacao_iterativa` produz a próxima versão canônica. Em `publicacao_compartilhada`, também pode fazê-lo o revisor autorizado e escolhido como publicador da tentativa. Avaliador, crítico ou revisor pode devolver um dos formatos abaixo, conforme a configuração confirmada:

- `parecer`: avaliação estruturada, críticas e condições de aprovação;
- `patch`: alterações propostas contra o hash congelado;
- `artefato_alternativo`: documento completo candidato;
- `parecer_e_alternativo`: parecer e candidato completo.

Em `parecer_apenas` e `publicar_candidata`, patch ou alternativa nunca substitui o ponteiro corrente. O host o persiste sob `candidatos/tentativa-<n>/` ou `artefatos/<artefato_id>/candidatos/tentativa-<n>/`, registra `artefato_id`, autor, CLI, modelo, provedor, sessão, `base_sha256` e `sha256`, e o mantém imutável. Se o hash-base não for o da versão criticada, rejeitar a contribuição como obsoleta.

Registrar cada objeção no ledger do artefato, sempre com `artefato_id`. O responsável pela consolidação responde item por item com `aceita`, `aceita_parcialmente`, `rejeitada_com_evidencia` ou `esclarecimento_solicitado`. Somente depois dessa resposta ele consolida o documento completo. A consolidação abre nova tentativa e invalida deliberação, decisão, avaliação e auditoria do hash anterior.

O candidato alternativo serve como evidência e proposta de redação; não transfere a autoria canônica. A publicação na cadeia só ocorre por `consolidador_designado` ou `publicacao_compartilhada` confirmados. Ser avaliador ou revisor, isoladamente, nunca concede escrita canônica. No modo `publicar_canonico`, a autoria editorial é do revisor-publicador; o host ou adaptador apenas valida o recibo e realiza a troca atômica do ponteiro, sem exigir reincorporação pelo redator.

## Consolidação final cega entre modelos escolhidos

Oferecer `consolidacao_final.modo = multipla_cega` quando o usuário pedir duas ou mais versões finais independentes ou comparação lado a lado. Manter `dupla_cega` como alias compatível quando houver exatamente duas. O padrão legado `redator_unico` significa uma única consolidação final pelo responsável iterativo configurado; não obriga que ele seja o redator original.

No modo cego múltiplo:

1. Congelar o ledger de decisões, o manifesto de fontes, a rubrica e o snapshot de evidências.
2. Usar exatamente os modelos/CLIs indicados pelo usuário como consolidadores finais; qualquer modelo invocável pelos CLIs configurados pode participar, inclusive modelos diferentes dentro do mesmo CLI.
3. Cada participante produz um candidato final completo a partir do mesmo material, em sessão própria.
4. Nenhum participante recebe as consolidações dos demais antes de todos concluírem.
5. Persistir todas as candidatas em `candidatos/finais/` com hashes e procedência; todas permanecem candidatas, nunca aprovadas por geração.
6. Avaliar cada candidata cegamente com a mesma rubrica e o mesmo painel configurado. A avaliação não escolhe vencedora.
7. Gerar comparações pareadas de texto, estrutura, fundamentos, citações, notas, riscos, omissões e argumentos exclusivos.
8. Aguardar escolha humana. Fazer síntese somente por pedido explícito; jamais escolher ou combinar automaticamente.
9. Copiar a versão escolhida, ou a síntese pedida, para o destino final do artefato e executar novamente o gate deliberativo configurado, a avaliação final e a auditoria cega sobre esse hash exato.

Preservar todas as candidatas e os comparativos para auditoria/replay, mas permitir exatamente um arquivo com estado `canonico_aprovado` por `artefato_id`. Se uma síntese introduzir qualquer mudança, tratá-la como nova versão: aprovações das candidatas não valem para o novo hash.

## Distinguir consenso e loop

- **Rodada** pertence à estratégia interna: uma fase coordenada de manifestação entre participantes sobre a mesma versão, como crítica, réplica, revisão, consolidação ou verificação.
- **Ciclo de debate** é uma sequência de pelo menos três rodadas: crítica → réplica → revisão/consolidação.
- **Ciclo N×N** é uma sequência de três fases globais: N² críticas em matriz → N réplicas → N revisões; cada cadeira consome uma crítica, uma réplica e uma revisão por ciclo, ainda que sua crítica contenha pareceres sobre vários candidatos.
- **Tentativa de melhoria** pertence ao loop: uma versão congelada, sua estratégia interna e sua avaliação externa; qualquer correção produz a versão da tentativa seguinte.

Quando houver debate de consenso, aplicar:

- padrão de 8 rodadas; aceitar 1–36 em runs novos, usando uma rodada somente quando pedida expressamente; recomendar até 18 e reservar 19–36 para extensão excepcional justificada;
- padrão de 2 ciclos completos por tentativa;
- aceitar 0–12 ciclos por tentativa; recomendar até 6 e reservar 7–12 para extensão excepcional justificada;
- cada participante tem direito a uma crítica, uma réplica e uma revisão por ciclo confirmado;
- validar `rodadas_por_tentativa >= 3 × ciclos_por_participante`;
- quando somente os ciclos forem informados, elevar as rodadas ao mínimo coerente, respeitando o máximo de 36;
- quando somente as rodadas forem informadas, usar no máximo `min(2, floor(rodadas ÷ 3))` ciclos completos; no modo expresso de rodada única, usar 0 ciclos;
- quando ambos forem informados e forem incompatíveis, não alterar silenciosamente: pedir aumento das rodadas ou redução dos ciclos;
- consenso precisa permanecer válido em 2 avaliações consecutivas, salvo o modo explícito de rodada única, que usa estabilidade 1 e recebe rótulo próprio;
- dissenso final deve ser informado ponto por ponto.

Permitir extensão automática de 3 rodadas e 1 ciclo por vez quando houver simultaneamente bloqueio material aberto e progresso mensurável. A faixa recomendada termina em 18 rodadas/6 ciclos; a faixa excepcional termina em 36/12 e precisa aparecer na prévia e no recibo. Parar após dois ciclos consecutivos sem progresso, no teto confirmado, por cancelamento ou limite de custo/tempo. Valor superior a 36 rodadas ou 12 ciclos exige novo contrato explícito; nunca ampliar silenciosamente. Preservar sem mutação runs antigos já congelados com outros limites e identificá-los como configuração legada.

No loop principal:

- padrão de 6 tentativas/versões completas por artefato;
- aceitar outro teto explícito entre 1 e 20; 20 é o teto do motor para runs novos;
- não transformar erro, interrupção ou esgotamento em aprovação;
- parar por sucesso confirmado, sem progresso, bloqueio ou teto esgotado.

`rodadas_por_tentativa` e `tentativas` são limites independentes. Por exemplo, 4 rodadas e 5 tentativas permitem no máximo 20 rodadas de debate e resolvem 1 ciclo completo por tentativa quando nenhum número de ciclos for indicado. O limite de críticas, réplicas e revisões de cada participante é o número de ciclos confirmado para aquela tentativa.

Uma rodada global pode colher manifestações paralelas de várias cadeiras na mesma fase. Cada resposta incrementa o contador individual do participante, enquanto a fase incrementa `rodadas_usadas` uma única vez. Um ciclo completo consome no mínimo três rodadas globais.

Configurar também `politica_debate_por_tentativa`:

- `sempre`: estratégia interna em toda nova versão; padrão de `debate_agents_v1` e de consenso por tentativa;
- `se_necessario`: reabrir apenas diante de mudança material, bloqueador ou pedido do painel;
- `apenas_primeira`: deliberar a versão inicial e usar apenas avaliação/correção nas seguintes;
- `nenhum`: loop sem debate.

Resolver separadamente `consenso.modo`:

- `estrito`: consenso estável do mesmo hash é obrigatório;
- `com_decisor`: buscar consenso e, se ele falhar, admitir decisão fundamentada apenas sobre matérias julgáveis, sempre rotulada `decisão final sem consenso`;
- `consultivo`: colher parecer e dissensos sem gate deliberativo vinculante;
- `desativado`: não deliberar nem alegar consenso.

Usar somente as combinações coerentes: `desativado + nenhum`; qualquer outro modo com `sempre`, `se_necessario` ou `apenas_primeira`. O padrão de `debate_agents_v1` é `estrito + sempre` quando o usuário pedir aprovação em consenso. Se o pedido for apenas melhoria iterativa sem consenso, inferir `consultivo + se_necessario` e mostrar isso na prévia. Nunca converter maioria, recomendação consultiva ou decisão em consenso.

## Verificar disponibilidade

Usar o adaptador compartilhado de `$consenso`:

```text
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/consenso/scripts/cli_adapter.py" doctor --deep
```

Participantes reconhecidos: `claude`, `codex`, `gemini`, `antigravity`, `grok`, `kimi` e `opencode`; o adaptador resolve seats e rotas pelo manifesto. Se um participante explicitamente escolhido estiver ausente ou sem autenticação, parar antes da primeira tentativa e informar a ação necessária. Não simular nem substituir uma cadeira sem autorização.

Herdar de `$consenso` a opção `persistir_sessoes_nativas`. Em runs novos do loop, ativá-la por padrão;
em runs legados sem o campo, preservar `false`. Quando ativa,
criar um espelho recuperável por invocação nas CLIs que o suportam e registrar no `meta.json` e em
cada evento `requested`, `effective`, `confirmed`, rota e identificador/título. Não reutilizar uma
sessão entre autores cegos, painel e auditor; a persistência não elimina a exigência de sessões
independentes. O ledger do run continua canônico, e espelho nativo ausente ou não confirmado deve ser
informado sem apagar a resposta central já preservada.

Usar timeout de 1800 segundos por chamada. Permitir 30–1800 segundos na faixa comum e 1801–3600 somente quando a tarefa pesada justificar a exceção na prévia. Usar 180 minutos como limite total padrão do loop e permitir até 360 minutos na faixa recomendada.

Quando o usuário pedir trabalho por dias, oferecer como perfil opt-in `durable_5d_v1`, por até 432000 segundos, equivalentes a cinco dias corridos. Não transformar isso numa chamada única: manter o timeout por invocação, congelar orçamento diário e total e persistir `checkpoint.json` atomicamente depois de cada chamada, rodada, ciclo, versão e demais fronteiras aplicáveis. Tempo offline conta contra o deadline. O coordenador ou bridge deve retomar o último checkpoint válido após reinício; se não estiver ativo, o run permanece retomável, mas não executa trabalho sozinho. Não repetir `event_id+input_sha256`, não substituir rota/modelo e nunca converter timeout ou deadline em aprovação.

## Preparar o run

1. Resolver objetivo, público, formato, extensão, fontes autorizadas e critérios.
2. Resolver cada papel em linguagem natural, mostrar o bloco **Entendi assim** e aguardar confirmação explícita antes da primeira chamada externa.
3. Criar um diretório em `~/.agents/runs/debate-agentes/<slug>/`. Ler runs antigos também em `~/.claude/loops/runs/debate-agentes/`, sem regravá-los ou migrá-los silenciosamente.
4. Gravar `meta.json` de acordo com o protocolo de referência, mantendo também os campos legados.
5. Validar que `ciclo_de_melhoria.tentativas`, `loop.tentativas` e o limite efetivo do item estejam entre 1 e 20 e sejam coerentes com `python3 scripts/loop_limits.py validate-config <meta.json>`; rejeitar a configuração antes da primeira chamada se algum valor exceder 20.
6. Validar sempre o overlay com `python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/durable_run.py" validate <meta.json>`. Quando `durable_5d_v1` estiver ativo, inicializar `checkpoint.json` com o subcomando `init`; antes de continuar após reinício, usar `status` e `resume`; depois de cada fronteira, usar `checkpoint` com identificador e hashes idempotentes.
7. Validar autoria com `python3 scripts/publication_policy.py validate-config <meta.json>`; em cada
   publicação canônica, usar o subcomando `publish` com root e ledger explícitos conforme
   [publicacao-canonica.md](references/publicacao-canonica.md). `validate-receipt` sozinho nunca troca
   o ponteiro.
8. Validar a seção de consenso com `consensus_gate.py validate-config` antes da primeira chamada; qualquer veredito precisa passar por `validate-verdict` antes de alterar estado.
9. Em artefato único, criar `estado.md`, `texto.md`, `ledger/decisoes.jsonl`, `candidatos/` e, após uma primeira versão válida, `melhor.md`.
10. Em pacote, criar `pacote.json`, `pacote-final.json` e, para cada item, `artefatos/<artefato_id>/{texto.md,melhor.md,artefato-final.md,ledger/decisoes.jsonl,candidatos/}`. Validar IDs únicos, caminhos relativos e DAG de dependências sem ciclo.
11. No perfil N×N, criar também `candidatos/ensemble/`, `revisoes/ensemble/` e `ledger/ensemble.jsonl` dentro do escopo do artefato conforme a referência.
12. Não incluir segredos, `.env`, tokens, credenciais ou chaves em prompts.

Quando houver arquivos locais, criar um manifesto com raiz, caminhos relativos e hashes SHA-256. Todos os papéis que analisam fontes devem receber o mesmo manifesto. O redator externo devolve o artefato completo pela saída; somente o host grava o arquivo local.

## Executar a primeira tentativa

1. Selecionar o artefato corrente respeitando a ordem de dependências e entregar ao redator objetivo, público, formato, extensão e fontes autorizadas.
2. O redator produz uma versão completa no ponteiro corrente; congelar e registrar `artefato_id` e hash.
3. Se a política deliberativa mandar executar nesta tentativa, realizar o debate sobre essa versão antes da avaliação quantitativa.
4. Registrar a decisão, os bloqueadores e os dissensos. Se houver decisor, aplicar sua decisão dentro dos limites definidos abaixo.
5. O avaliador faz leitura integral, pontua, critica e sugere mudanças priorizadas.
6. Persistir a contribuição conforme `modo_publicacao`: parecer separado, candidata própria ou, se o avaliador/revisor estiver autorizado e tiver o turno, nova versão canônica validada contra o hash corrente.
7. Se qualquer gate reprovar, devolver consenso, dissensos, decisão, avaliação e candidatos ao responsável pela consolidação para produzir a próxima versão.
8. Se os gates aprovarem, executar a consolidação final configurada e a auditoria cega antes de declarar sucesso.

## Executar tentativas seguintes

Quando qualquer gate reprovar:

1. O responsável pela consolidação responde item por item às críticas e sugestões.
2. Registrar as respostas no ledger; sugestões rejeitadas exigem evidência ou fundamento explícito.
3. O responsável pela consolidação corrige e entrega nova versão completa, preservando a autoria inicial e registrando a autoria desta versão. Essa versão abre uma nova tentativa.
4. Congelar o novo hash. Executar ou omitir a deliberação conforme `consenso.modo` e `politica_por_tentativa`; nunca reutilizar o veredito do hash anterior.
5. O mesmo avaliador compara a versão com o veredito anterior e reavalia; se houver críticos adicionais ou revisor separado, mantê-los nos pontos definidos pela configuração.
6. Promover `texto.md` para `melhor.md` somente se a média subir e nenhuma mediana cair mais de 0,5. Caso contrário, restaurar a melhor versão e tentar uma abordagem diferente.
7. Registrar em `estado.md` a tentativa, papéis efetivos, versão/modelo quando conhecido, notas, mudança atacada, resultado e contadores.

Antes de solicitar a correção do passo 3, verificar o teto efetivo do item. Se `versao_atual` já for igual a `tentativas_maximas` ou a 20, não solicitar outra correção: transitar para `ESGOTADO` e emitir o recibo de não aprovação. Nunca contornar o limite renomeando a saída, reiniciando o contador ou tratando uma síntese como derivado.

Há dois aliases legados compatíveis:

- `consenso_por_tentativa`: ativar quando o pedido disser para buscar consenso, corrigir e repetir; executar o consenso completo sobre cada nova versão;
- `consenso_sob_demanda`: equivale à política `se_necessario`; escalar somente diante das condições abaixo. Só exigir consenso final se o modo deliberativo efetivo for `estrito` ou `com_decisor`.

No modo sob demanda, escalar quando ocorrer pelo menos uma destas condições:

- a mesma objeção material permanece sem solução por 2 tentativas;
- redator e avaliador discordam sobre fato, tese, risco ou critério decisivo;
- aparece nova fonte capaz de alterar a conclusão;
- a correção exigiria mudança material de tese ou estrutura;
- o usuário pede expressamente o debate.

No modo sob demanda, o consenso intermediário pode resolver apenas o ponto controvertido. No modo por tentativa, ele sempre avalia o artefato completo e pode também deliberar sobre pontos específicos. Depois, devolver o resultado ao responsável pela consolidação e retomar o mesmo loop, com os mesmos papéis e contadores.

## Obter consenso sobre cada versão

No modo `consenso_por_tentativa`, executar `$consenso` sobre o **artefato produzido** em toda tentativa, antes da avaliação independente. No modo sob demanda, aplicar este mesmo contrato quando houver gatilho. Em `consultivo`, o parecer não bloqueia por si; em `desativado + nenhum`, não invocar `$consenso` nem alegar acordo.

1. Congelar a versão candidata e registrar seu hash SHA-256.
2. Entregar exatamente essa versão, as fontes autorizadas, o objetivo e os critérios aos participantes.
3. Perguntar se o artefato satisfaz os requisitos e quais bloqueadores impedem sua aceitação.
4. Proibir edição durante o consenso; as cadeiras apenas deliberam sobre a versão congelada.
5. Exigir a estabilidade configurada quando o modo for `estrito` ou `com_decisor`; no consultivo, registrar concordâncias e dissensos sem convertê-los em gate vinculante.
6. Com consenso favorável, registrar o hash aprovado e seguir para decisão, avaliação e auditoria conforme a configuração do run.
7. Com dissenso material, enviar os pontos ao decisor quando a estratégia for `consenso_com_decisao_final`. Se ele exigir correção, devolver ao responsável pela consolidação na próxima tentativa; se resolver todos os bloqueios sujeitos a julgamento e autorizar prosseguimento, seguir registrando `decisão sem consenso`. Sem decisor, ou em consenso estrito, devolver o dissenso ao responsável pela consolidação. O novo hash invalida a deliberação anterior e executa uma nova somente conforme a política congelada.

Por padrão, redator e avaliador participam. Incluir críticos, revisor ou outros modelos quando já estiverem configurados ou quando o usuário pedir. O consenso é um gate adicional e não elimina nenhum papel ou verificação previamente escolhido.

## Aplicar o decisor final

Quando configurado, o decisor recebe a versão congelada, as posições anonimizadas, os dissensos, as evidências e os critérios. Ele deve decidir ponto por ponto, justificar a escolha e indicar se o artefato pode prosseguir.

O decisor pode resolver dissenso interpretativo, estratégico, de risco ou preferência. Não pode:

- declarar consenso inexistente; sua saída é uma decisão final, não unanimidade;
- dispensar média-alvo, piso por critério ou erro factual crítico;
- aprovar versão diferente do hash deliberado;
- substituir avaliação independente ou auditoria cega;
- editar o artefato; correções permanecem com o responsável resolvido por `consolidacao_iterativa`.

Se a decisão exigir alteração, iniciar nova tentativa. Se restar dissenso, registrá-lo ponto por ponto mesmo quando o decisor autorizar prosseguimento.

Na estratégia `consenso_com_decisao_final`, o gate deliberativo pode ser satisfeito por consenso estável **ou** por decisão final sobre todos os bloqueios materiais sujeitos a julgamento. Na estratégia `consenso_estrito`, somente o consenso estável satisfaz o gate. Em ambos os casos, erro factual crítico, meta, piso e auditoria permanecem obrigatórios.

## Preservar independência

Separar **CLI**, **modelo**, **provedor**, **papel** e **sessão**. Nomes de personas ou lentes não criam independência de modelo.

- O avaliador-crítico deve preferencialmente usar outro modelo/provedor e permanecer o mesmo durante as tentativas.
- Críticos adicionais e revisor separado são opcionais e podem usar qualquer modelo escolhido.
- No perfil `debate_agents_v1`, redator, painel regular e auditoria cega têm identidades e sessões separadas.
- O painel deve preferencialmente incluir modelo ou família diferente do redator. Se o usuário escolher o mesmo, permitir, registrar `hold_out_de_modelo: false` e chamar o resultado de avaliação separada, não independente de modelo.
- Auditor sempre usa sessão nova, sem histórico. Preferir modelo/provedor diferente do redator e do avaliador.
- Uma auditoria com o mesmo modelo do redator nunca deve ser descrita como auditoria independente de modelo.

Aceitar as políticas:

- `automatico`: escolher membros elegíveis conforme risco, qualidade, custo e disponibilidade;
- `modelo_diferente_do_redator`: exigir diversidade de modelo/família;
- `provedor_diferente`: exigir separação de provedor;
- `escolhido_pelo_usuario`: congelar a composição informada;
- `mesmo_modelo_sessao_independente`: permitir somente quando aceito para o risco e rotular `diversidade_reduzida`.

Se um membro diverso estiver indisponível, nunca substituí-lo silenciosamente. Aplicar a política congelada `falha_de_independencia`: `pausar` ou `reduzir_quorum`. Redução de quórum só é válida se ainda houver maioria, o mínimo configurado for preservado e o relatório informar cadeira ausente, impacto na diversidade e confiabilidade reduzida.

O auditor recebe somente: artefato final, fontes autorizadas, público, formato, critérios, alvo e piso. Não recebe versões anteriores, notas, críticas, identidades, justificativas nem o resultado do painel.

## Avaliar e parar

Usar:

```text
"${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/avaliar.sh" <run-dir>
"${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/avaliar.sh" <run-dir> --cego
"${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/comparar-candidatos.sh" <run-dir>
```

Sucesso exige as condições abaixo para cada artefato obrigatório:

1. avaliação normal com média maior ou igual ao alvo e todas as subnotas maiores ou iguais ao piso;
2. gate deliberativo efetivo sobre o hash exato: consenso estável em `estrito`; consenso ou decisão final registrada em `com_decisor`; parecer registrado sem bloqueio próprio em `consultivo`; gate dispensado em `desativado + nenhum`;
3. auditoria cega nova satisfazendo os mesmos limites.

Em pacote, exigir ainda que todos os itens obrigatórios estejam aprovados, que o manifesto contenha seus hashes exatos e que o gate conjunto configurado aprove a consistência. Não usar nota compensatória do pacote nem transferir aprovação entre itens.

Quando houver decisor, sua autorização precisa referir-se ao mesmo hash. Se o gate for satisfeito sem consenso, nunca escrever “consenso alcançado”; escrever `decisão final sem consenso` e listar todo dissenso remanescente.

Outras paradas:

- `sem-progresso`: duas tentativas consecutivas com ganho menor que 0,2;
- `bloqueado`: duas falhas consecutivas do executor ou participante indispensável indisponível;
- `esgotado`: teto confirmado de tentativas/versões atingido, nunca superior a 20 por artefato em run novo.
- `cancelado`: cancelamento explícito do usuário;
- `limite_operacional`: teto de custo ou tempo atingido.

Em qualquer parada sem sucesso, entregar `melhor.md`, a melhor nota obtida e declarar explicitamente que o alvo não foi confirmado.

## Entregar o resultado

Informar:

- caminho e conteúdo do melhor artefato por `artefato_id`;
- caminho e hash do único canônico aprovado por artefato, ou indicação explícita dos itens sem aprovação;
- candidatos alternativos e finais preservados, com seus hashes, sem confundi-los com o canônico;
- no modo duplo, comparação cega e escolha humana ou síntese explicitamente solicitada;
- papéis efetivos com CLI, modelo, provedor e independência real;
- tentativas/versões completas, rodadas e ciclos consumidos, inclusive o teto efetivo de até 20;
- média final, medianas por critério, menor subnota e auditoria cega;
- consenso ou pontos de dissenso remanescentes;
- decisões finais e respectivos fundamentos, quando houver decisor;
- falhas, indisponibilidades e limites atingidos;
- chamadas por ponto de nota ganho, taxa de tentativas úteis e divergência entre painel e auditor.
- no perfil N×N: matriz declarada e efetiva, candidatos por produtor, pareceres esperados e recebidos, ciclos, juiz, modo de seleção, estimativa e chamadas reais.
- no modo pacote: manifesto de hashes, dependências, estado de cada item, resultado do gate conjunto e itens reabertos.

Não esconder dissenso para produzir uma conclusão mais limpa. Não declarar aprovação sem avaliação, gate deliberativo do hash e auditoria verificáveis.
