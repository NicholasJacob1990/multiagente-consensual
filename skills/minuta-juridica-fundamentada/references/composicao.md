# Composição com redação consensual e auditoria

Esta skill define o produto e sua elaboração jurídica direta. A composição é acionada por pedido de consenso ou trabalho multiagente, ou integra uma execução já autorizada. Não cria motor próprio nem presume que duas revisões do mesmo agente sejam independentes.

| Componente | Função |
|---|---|
| Minuta Jurídica Fundamentada | Delimitar o documento, desenvolver a fundamentação e entregar a minuta corrigida |
| Redação Jurídica Consensual | Aplicar briefing, receita, rubrica, fontes e portões jurídicos ao trabalho multiagente |
| Loop Debate de Agentes | Governar equipe, modelos, rotas, versões, limites, consenso, auditoria final e publicação |
| Auditoria Jurídica de Minutas | Conferir sustentação, estratégia e integridade; comparar versões quando houver base |

Resolver nomes e caminhos no catálogo disponível: `$redacao-juridica-consensual` ou `$multiagente-consensual:redacao-juridica-consensual`, e as variantes pertinentes do loop. Ler o contrato selecionado; não presumir equivalência entre cópia local e versão de plugin. Não editar caches para integrar as skills.

Usar a receita adequada do contrato: `parecer_consensual`, `peticao_consensual` ou `recurso_consensual`. Preservar `perfil_base: debate_agents_v1` e `perfil_dominio: juridico_consensual_v2` quando presentes no contrato vigente. Não duplicar seus defaults, contadores, ledgers, estados de aprovação, modelos ou regras de parada.

Levar objetivo, formato, fontes e requisitos da minuta à configuração existente. Aproveitar a autorização já dada. Se o motor exigir uma prévia para a execução solicitada ainda não autorizada, reunir o que precisa ser decidido em uma única prévia concreta, no ponto regido pelo contrato. Isso não bloqueia redação direta ou preparação independente já autorizadas.

Quando disponível, ler `$auditoria-juridica-de-minutas` e sua referência de integração. No modo direto, aplicar a revisão ao rascunho e incorporar as correções dentro do escopo. No modo multiagente, submeter achados pelo fluxo do motor; somente o papel autorizado promove versões. Correção material exige reexaminar os pontos e gates afetados conforme o contrato.

O comparador pode conhecer versões e críticas. O auditor cego final do motor recebe apenas os insumos permitidos em sessão independente; não receberá o relatório comparativo ou o ranking como indução. Não declarar consenso ou aprovação com base somente no relatório da auditoria, na revisão do redator ou na identidade de hashes.

Se uma dependência solicitada não estiver disponível, informar a limitação específica, preservar o pedido multiagente pendente e avançar na produção direta útil que esteja autorizada. Não simular participantes nem apresentar a saída direta como consensual.

Entregar o documento efetivamente produzido e as pendências materiais. O relatório da equipe pode acompanhar a entrega, mas não substituir a minuta.
