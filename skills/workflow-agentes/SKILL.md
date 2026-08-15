---
name: workflow-agentes
description: "Orquestrar colaboração entre agentes e modelos em sete protocolos formais: pipeline serial, grafo/DAG assíncrono, swarm dinâmico, map-reduce, torneio eliminatório, votação Borda/Condorcet/Delphi e roteamento adaptativo por qualidade, custo e latência. Usar com /workflow-agentes, /pipeline-agentes, /dag-agentes, /swarm-agentes, /map-reduce-agentes, /torneio-agentes, /votacao-agentes ou /roteamento-adaptativo, inclusive quando o resultado deve entrar no loop-debate-agentes para consenso, nota-alvo e auditoria."
---

# Workflows de Agentes

Interprete o texto fornecido após `/multiagente-consensual:workflow-agentes` como objetivo,
participantes e limites do workflow.

## Execução portátil no plugin

Quando o host for Cowork, usar `bridge-agentes` para cada nó ou cadeira externa e a fila em pasta
compartilhada de [cowork-bridge.md](../../references/cowork-bridge.md). Resolver as rotas pelo
manifesto indicado, pelo manifesto local válido ou pelo
[manifesto empacotado](../../assets/multiagent-manifest.json), nessa ordem. O bridge não escolhe o
protocolo, não expande o swarm, não muda o DAG e não converte seleção em aprovação.

Coordenar agentes nomeados, CLIs e modelos por contratos explícitos. Separar sempre identidade, modelo, provedor, papel, sessão e permissão. Nenhum protocolo amplia a autorização do usuário para editar arquivos, executar ações externas ou criar agentes fora do escopo confirmado.

## Resolver o protocolo

| Pedido | Perfil canônico | Referência obrigatória |
|---|---|---|
| “A passa para B, depois C” | `pipeline_serial_v1` | [references/pipeline-serial.md](references/pipeline-serial.md) |
| “execute tarefas dependentes em paralelo” | `dag_assincrono_v1` | [references/dag-assincrono.md](references/dag-assincrono.md) |
| “forme um swarm e ajuste a equipe” | `swarm_dinamico_v1` | [references/swarm-dinamico.md](references/swarm-dinamico.md) |
| “divida, processe e reduza” | `map_reduce_v1` | [references/map-reduce.md](references/map-reduce.md) |
| “faça candidatos se enfrentarem” | `torneio_eliminatorio_v1` | [references/torneio.md](references/torneio.md) |
| “vote por Borda, Condorcet ou Delphi” | `votacao_multiagente_v1` | [references/votacao.md](references/votacao.md) |
| “escolha/troque modelos por desempenho e custo” | `roteamento_adaptativo_v1` | [references/roteamento-adaptativo.md](references/roteamento-adaptativo.md) |

Ler [references/contrato.md](references/contrato.md) integralmente em toda execução e, depois, apenas a referência do protocolo selecionado. Para composição de protocolos, ler cada referência usada e declarar a ordem. Não chamar uma combinação improvisada de novo protocolo.

## Escolher automaticamente sem surpreender

Usar o protocolo mais simples que preserve o pedido:

- dependência linear: pipeline;
- dependências ramificadas: DAG;
- problema divisível em unidades homogêneas: map-reduce;
- exploração aberta com especialidades mutáveis: swarm;
- seleção competitiva de artefatos: torneio;
- agregação de preferências ou estimativas: votação;
- escolha dinâmica de modelo por telemetria: roteamento adaptativo.

Não ativar swarm, roteamento adaptativo ou votação automática quando o usuário indicou uma lista fechada e papéis fixos. Em caso de ambiguidade material, mostrar a interpretação recomendada na prévia; não executar antes da confirmação.

## Resolver participantes e modelos

Aceitar agentes OpenCode nomeados, modelos no formato `provedor/modelo` e CLIs/seats `claude`, `codex`, `gemini`, `antigravity`, `grok`, `kimi` e `opencode`.

Ler `~/.agents/multiagent-manifest.json` e congelar separadamente seat, modelo e rota efetiva. A política exige Claude Opus 5 (`claude-opus-5`) via Claude Code, Grok via Cursor, Kimi K3 via Kimi Code e Gemini 3.7 via Antigravity. Manifesto inválido ou indisponibilidade pausa a cadeira; não autoriza troca silenciosa de CLI, modelo ou provedor. O YAML legado é somente visão gerada.

Quando o usuário escrever `@nome`, resolver nesta ordem:

1. agente configurado no host;
2. arquivo global do OpenCode em `~/.config/opencode/agents/<nome>.md`;
3. alias congelado no manifesto do run;
4. participante não resolvido, que exige somente o dado ausente.

Uma identidade nomeada pode desempenhar vários papéis. Identidades com sufixos como `-redator` ou `-auditor` fixam função e permissões, não criam diversidade de modelo. O roteador pode escolher automaticamente somente dentro do conjunto elegível confirmado.

## Mostrar a prévia

Antes de chamar qualquer modelo externo, mostrar:

```text
Entendi assim
Protocolo: pipeline | DAG | swarm | map-reduce | torneio | votação | roteamento
Objetivo e saída: ...
Participantes elegíveis: ...
Papéis e modelos: ...
Estrutura: etapas | nós/arestas | membros | partições | chave | método | política
Paralelismo máximo: ...
Limites: chamadas, custo, tempo, tentativas e expansões
Execução durável: padrão | até cinco dias corridos com checkpoints e retomada
Saída por chamada: adaptativa até o teto nativo; sem preenchimento obrigatório
Falha de cadeira: pausar | repetir | reduzir com autorização
Persistência: artefatos, hashes e ledger
Sessões nativas nas CLIs: não persistir | persistir como espelho não canônico
Integração com loop: nenhuma | uma vez | a cada nova versão
Ações externas ou destrutivas: nenhuma, salvo autorização já existente
```

Esperar confirmação explícita. Depois dela, não pedir nova confirmação para decisões já cobertas, mas pausar diante de expansão de escopo, custo acima do teto, novo provedor, nova permissão ou substituição de participante.

## Preparar e executar

1. Criar `~/.agents/runs/workflow-agentes/<slug>/`; aceitar `~/.claude/loops/runs/workflow-agentes/` somente para leitura de runs antigos.
2. Gravar `meta.json` conforme o contrato comum.
3. Criar `estado.md`, `ledger/eventos.jsonl`, `artefatos/`, `entradas/` e `saidas/`.
4. Congelar briefing, fontes, rubrica, participantes, modelos e limites.
5. Validar a configuração:
   ```text
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/workflow-agentes/scripts/protocol_engine.py" validate <meta.json>
   ```
6. Validar sempre `execucao_duravel` com `durable_run.py`. Quando `durable_5d_v1` estiver ativo, inicializar `checkpoint.json`, salvar checkpoint atômico após chamada, nó, onda, join e qualquer rodada/ciclo/versão do loop integrado, e executar `status` + `resume` ao reiniciar o coordenador ou bridge:
   ```text
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/durable_run.py" validate <meta.json>
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/loop-debate-agentes/scripts/durable_run.py" init <meta.json> <checkpoint.json>
   ```
7. Gerar o plano determinístico quando aplicável:
   ```text
   python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/workflow-agentes/scripts/protocol_engine.py" plan <meta.json>
   ```
8. Invocar cada cadeira em sessão própria. Para CLIs externos, reutilizar o adaptador de `$consenso`; no OpenCode, usar o agente nomeado ou `opencode run --model provedor/modelo --agent nome`. Se `persistir_sessoes_nativas: true`, passar `--persist-native-session` e tratar a sessão nativa somente como espelho recuperável da invocação.
9. Aplicar `adaptive_output_v1`: permitir saída somente até o necessário, mas sem teto artificial inferior ao máximo efetivo da rota. Metas de concisão são flexíveis. Se um artefato obrigatório for truncado, continuar a mesma cadeira em segmentos limpos; seleção e joins aguardam a saída completa.
10. Persistir saída completa, política e controle de saída efetivos, hash-base, hash resultante, autoria, sessão, tempo, custo quando disponível e estado. Registrar separadamente a sessão lógica do workflow e o recibo da sessão nativa (`requested`, `effective`, `confirmed`, id/título); o ledger central permanece canônico.
11. Validar joins, votos, chaves de redução ou decisões de roteamento antes de promover uma saída.
12. Toda seleção, voto, torneio ou roteamento deve registrar `aprovacao: false`; quando houver consenso, validar `veredito_consenso_v1` pela skill `$consenso`.
13. Encerrar com recibo completo; nunca chamar seleção, voto ou síntese de consenso sem o gate correspondente.

Se o host não suportar concorrência real, executar uma onda assíncrona de forma serial e registrar `execucao_serializada_pelo_host = true`. Não alterar dependências ou semântica.

## Compor com o loop de melhoria

Quando o usuário pedir correção iterativa, consenso, meta, piso ou auditoria:

1. executar o workflow escolhido para produzir uma ou mais candidatas;
2. congelar os hashes e selecionar conforme o protocolo;
3. encaminhar exatamente a candidata selecionada para `$loop-debate-agentes`;
4. tratar escolha, voto, ranking ou redução como proposta, nunca aprovação;
5. se o loop produzir novo hash, aplicar a política confirmada: `nao_repetir`, `repetir_se_material` ou `repetir_sempre`.

O `ensemble_nxn_v1` continua pertencendo a `$loop-debate-agentes`. Usar torneio quando houver confrontos eliminatórios; usar ensemble N×N quando todos revisarem todos.

## Limites e falhas

Runs comuns preservam seus limites confirmados. Quando o usuário pedir trabalho por dias, ativar explicitamente `durable_5d_v1` com no máximo 432000 segundos corridos. O Mac não trabalha dormindo ou offline, mas esse intervalo conta no deadline. Um coordenador/bridge ativo retoma o checkpoint após reinício; sem ele, a execução fica pausada e retomável. Encerrar cedo por sucesso, cancelamento, orçamento, deadline, bloqueio ou dois ciclos completos sem progresso mensurável.

- Não adicionar modelo, provedor, CLI ou agente fora do conjunto confirmado.
- Não substituir cadeira silenciosamente.
- Não permitir que o swarm cresça além de `max_membros`, `max_expansoes` e orçamento.
- Não executar DAG cíclico; devolver o ciclo detectado.
- Não aceitar map sem cobertura nem reduce sem procedência.
- Não inventar vencedor Condorcet quando houver ciclo.
- Não alterar a regra de desempate após ver os resultados.
- Não usar métricas inexistentes como se fossem observadas; marcar `desconhecido`.
- Não reutilizar saída ou aprovação de outro hash.
- Não permitir que juiz, votação ou roteador dispensem auditoria solicitada.

Parar por sucesso, limite, cancelamento, dependência impossível, falta de quórum, ciclo inválido, ausência de progresso ou expansão não autorizada.

## Entregar

Informar protocolo e versão, participantes efetivos, modelos/provedores/sessões, plano executado, paralelismo real, artefatos e hashes, falhas e substituições autorizadas, custo/tempo observado, dissensos, regra de seleção e razão de parada. Quando houver loop, distinguir claramente `candidato_selecionado` de `canonico_aprovado`.
