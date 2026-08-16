---
description: Monta equipe com papéis distintos entre codex/claude/gemini/grok
argument-hint: <objetivo da equipe>
entrypoint: workflow-agentes
profile: a2a_team
approval-ceiling: none
---
Invoque a tool MCP `mcp__a2a-mesh__a2a_team` com o objetivo abaixo. Deixe a tool decidir os papéis a menos que `$ARGUMENTS` já contenha designações explícitas (ex.: "codex=tester, claude=arquiteto, gemini=pesquisador, grok=oponente"). Retorne o output final consolidado.

A tool devolve um recibo durável por padrão. Guarde o `task_id` e use `a2a_task_wait` em esperas de até 240 segundos, repetindo enquanto o estado for ativo, salvo se o usuário pedir apenas o disparo. Use `a2a_task_status` para retomar acompanhamento; nunca reenvie o pedido só porque uma espera terminou. Se falhar, informe o estado e apresente `partial-output.md` quando existir. O diálogo ao vivo fica no painel A2A.

$ARGUMENTS


<!-- adaptive-output-contract:start -->
Política de saída: adaptive_up_to_native_max. Use somente a extensão necessária, permita até o teto nativo efetivo da rota, não imponha teto global artificial e não obrigue preenchimento. Em integração externa sem controle explícito, repasse a diretiva no prompt e registre o limite como nativo ou desconhecido, sem prometer um número.
<!-- adaptive-output-contract:end -->


<!-- full-filesystem-contract:start -->
Política de arquivos: `project_root_plus_explicit_directories`. Todos os agentes recebem ferramentas locais completas e autoaprovadas sob a identidade do usuário, mas o projeto e diretórios extras são declarados por invocação; a pasta pessoal só entra por opção explícita e nunca silenciosamente. Esses escopos orientam a execução, porém shell irrestrito do mesmo usuário não constitui sandbox do sistema operacional nem boundary contra agente malicioso. A permissão técnica não altera a autoria: por padrão, somente o redator ou consolidador resolvido publica o canônico; em `publicar_canonico`, um revisor autorizado também pode publicar mediante turno, arquivo real, CAS por hash-base, lock, gravação atômica, `fsync`, ledger idempotente e recibo do host. Ações destrutivas e efeitos externos continuam limitados ao pedido. Debates usam 8 rodadas e 2 ciclos por padrão, recomendam até 18/6 e podem chegar a 36/12 enquanto houver bloqueio material e progresso; parar após dois ciclos sem progresso. Chamadas usam 30 minutos por padrão, até 60 em exceção justificada. Sessões nativas são descartáveis por padrão; persistência exige opção explícita.
<!-- full-filesystem-contract:end -->
