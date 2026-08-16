---
name: consenso
description: "Orquestrar deliberação configurável sobre arquivos locais entre modelos escolhidos caso a caso, com governança do artefato canônico, consenso verificável, decisão ou dissenso explícito e formação colegiada seriatim, per curiam ou opinion of the court, por apuração global, analítica ou híbrida. Usar com /consenso, $consenso, conselho multi-CLI, crítica–réplica–revisão, decisão colegiada, votação case-by-case ou issue-by-issue, acórdão, votos, comparação de arquivos ou seleção de modelos em linguagem natural."
---

# Consenso multi-CLI

Interprete o texto fornecido após `/multiagente-consensual:consenso` como `$ARGUMENTS`. Sem texto,
abra a configuração sobre o artefato atual.

## Execução portátil no plugin

Quando esta skill estiver instalada pelo plugin `multiagente-consensual`, resolver o contrato nesta
ordem: manifesto explicitamente indicado pelo usuário; `~/.agents/multiagent-manifest.json` válido
no host; [manifesto empacotado](../../assets/multiagent-manifest.json). No Cowork, usar a skill
`bridge-agentes` e a fila em pasta compartilhada descrita em
[cowork-bridge.md](../../references/cowork-bridge.md). Não tentar alcançar `localhost` nem presumir
que as CLIs do Mac existam no ambiente isolado. O bridge é somente transporte: esta skill continua
responsável por validar `veredito_consenso_v1`.

Para a estrutura dos recibos, ledger, nonce e limite do modelo de ameaça, usar
[proveniencia-e-aprovacao.md](references/proveniencia-e-aprovacao.md).

Interpretar participantes, modelos, rodadas e ciclos em linguagem natural. Não exigir flags.

Esta skill é a **camada decisória central** do ecossistema. Loop, perfil jurídico, councils e workflows podem produzir posições ou candidatas, mas somente o contrato `veredito_consenso_v1` distingue consenso, decisão sem consenso, parecer consultivo e etapa desativada. Ler primeiro `~/.agents/multiagent-manifest.json`; ele é a fonte única para seats, rotas, aliases, limites centrais e poder de aprovação. `~/.agents/model-routing.yaml` é apenas uma visão gerada para compatibilidade.

Exemplos:

```text
/consenso analise a autenticação e diga qual correção é mais segura
/consenso Claude e Grok revisem o diff atual
/consenso use Codex, Antigravity e Gemini, com 3 ciclos por modelo
/consenso debata com Claude Opus 5 e Grok pelo Cursor 4.6 High em no máximo 10 rodadas
/consenso Claude redige, Grok critica, Gemini revisa e Codex avalia
/consenso verifique se há consenso sobre a versão atual deste documento
/consenso entre @Estrategista, @Oponente e @Revisor; @Supervisor decide; 4 rodadas por tentativa
/consenso faça só uma rodada sobre este trecho, sem corrigir
/consenso Claude redige a primeira versão, Codex critica e Gemini consolida as correções
/consenso avalie separadamente as duas consolidações finais cegas; não escolha nem combine automaticamente
/consenso forme uma opinion of the court, apure adesão por fundamento e publique votos concorrentes e dissidentes
/consenso vote o recurso questão por questão e derive o resultado; informe maiorias cruzadas
/consenso use critério híbrido: vote as questões e só proclame após confirmação bloqueante do dispositivo derivado
```

Quando o pedido incluir produção e melhoria sucessiva de um artefato, usar também `$loop-debate-agentes`. O debate desta skill é a camada deliberativa interna; tentativas de redação, painel quantitativo e auditoria cega pertencem ao loop externo.

## Confirmar antes de executar

Antes da primeira chamada externa, interpretar o pedido e mostrar **Entendi assim** com: modo deliberativo, política por tentativa, efeito na aprovação, eventual formação colegiada com modalidade, método de apuração (`global`, `analitico` ou `hibrido`), regra do resultado, quórum, questões e derivação quando aplicáveis, confirmação bloqueante no híbrido, adesão aos fundamentos, ratio e votos separados, participantes, redator inicial, política das correções, eventual consolidador designado, decisor, estabilidade, rodadas por tentativa, ciclo de melhoria, tentativas máximas, meta média, piso por critério, consolidação final, auditoria final e persistência das sessões nativas. Esperar confirmação explícita.

Menções como `@Estrategista` identificam agentes cadastrados. Resolver seu CLI, modelo e provedor sem confundir o nome do agente com o do modelo. Se uma associação indispensável não puder ser descoberta localmente, mostrar o campo como não fixado e pedir somente a informação faltante.

Uma forma curta como `/consenso`, `Buscar consenso` ou “peça consenso da equipe sobre este trecho” abre essa configuração sobre o artefato atual. “Uma rodada, sem corrigir” significa uma única deliberação da versão corrente, sem iniciar o loop de melhoria; usar `estabilidade = 1` e rotular eventual convergência como **acordo provisório consultivo**, nunca como consenso forte ou aprovação.

Se o usuário exigir artefato “aprovado em consenso”, usar consenso estrito: maioria ou decisão de supervisor não substitui o acordo estável, e qualquer dissenso material impede o estado aprovado.

## Configurar o modo deliberativo

Resolver o modo separadamente da frequência:

| Modo | Resultado |
|---|---|
| `estrito` | Consenso estável obrigatório; dissenso material impede aprovação em consenso |
| `com_decisor` | Buscar consenso; o decisor pode resolver matérias julgáveis, sempre como `decisão sem consenso` |
| `consultivo` | Entregar recomendação, posições e dissensos sem criar gate obrigatório |
| `desativado` | Não chamar participantes; devolver o controle ao loop sem deliberação |

Em fluxos com versões, combinar com `sempre`, `se_necessario`, `apenas_primeira` ou `nenhum`. Exigir `desativado + nenhum` em conjunto. Manter `estrito + sempre` como padrão quando o pedido exigir aprovação em consenso; fora disso, mostrar o padrão proposto e aguardar confirmação.

Nunca chamar maioria, votação, recomendação consultiva ou decisão de consenso. Permitir configuração diferente por artefato, desde que cada resultado permaneça vinculado ao próprio hash.

## Formar decisão colegiada sem confundir consenso

Quando houver pedido de acórdão, votos, decisão colegiada, `seriatim`, `per curiam` ou `opinion of the court`, ler integralmente `../loop-debate-agentes/references/decisao-colegiada.md`. Resolver essa camada separadamente do modo de consenso. Por padrão apenas para pedidos colegiados, propor `opinion_of_court`, maioria simples, adesão por proposição e publicação dos votos concorrentes e dissidentes.

Resolver `metodo_apuracao` separadamente da modalidade. Usar `global` e `decisao_colegiada_v1` por padrão: cada cadeira vota no dispositivo. Ativar `analitico` ou `hibrido` e `decisao_colegiada_v2` somente por pedido explícito de votar por questões, premissa a premissa ou confirmar o derivado. Não inferir o modo analítico de “acórdão”, “preliminares” ou “opinião da corte” isoladamente.

Congelar o mesmo hash. No global, decompor fundamentos em proposições e colher dispositivo e adesões. No analítico, congelar questões, floresta de dependências e regras de derivação antes das cédulas; publicar o dispositivo derivado, o resultado por cadeira, as coalizões por questão e qualquer `paradoxo_doutrinario`. No híbrido, exigir ainda confirmação bloqueante em segundo ato. Validar a proclamação com `scripts/collegiate_gate.py`. Uma maioria pode formar decisão colegiada sem formar consenso. Se não houver maioria aderente ao pacote derivado, registrar `ratio_status = somente_resultado`; quando `ratio_exigida = true`, devolver o ponto ao loop. Nunca ocultar dissenso do recibo de auditoria.

## Resolver a configuração

Aplicar estes padrões, salvo pedido explícito:

- modo deliberativo: `estrito`;
- política por tentativa em loop: `sempre`;
- participantes: host atual e sua contraparte Claude/Codex;
- rodadas globais máximas: 8;
- ciclos completos por participante: 2;
- avaliações consecutivas para consenso: 2;
- saída: `adaptive_up_to_native_max`, sem obrigação de preencher o teto;
- acesso técnico: integral e irrestrito dentro das permissões da conta do sistema;
- idioma: o do usuário.
- método de apuração colegiada: `global`; analítico ou híbrido somente por confirmação explícita;

Aceitar configurações como “3 rodadas”, “até 10 rodadas”, “um ciclo”, “quatro ciclos”, “somente Claude e Grok” ou “você também participa”. Limites:

- rodadas: 1–36; uma rodada somente quando solicitada expressamente; acima de 8 por pedido ou extensão necessária; faixa operacional recomendada até 18;
- ciclos de crítica–réplica–revisão: 0–12 por participante; faixa operacional recomendada até 6;
- um ciclo completo consome no mínimo três rodadas globais: crítica, réplica e revisão/consolidação;
- rodadas adicionais não concedem ciclos extras: servem para verificar evidências e testar consenso.

Permitir extensão automática de uma unidade completa por vez — 3 rodadas e 1 ciclo — quando ainda houver bloqueio material e progresso mensurável. Registrar motivo, contadores e custo da extensão. Parar após dois ciclos consecutivos sem progresso, no teto confirmado, por cancelamento ou limite de custo/tempo. Acima da faixa recomendada de 18/6, destacar na prévia que a execução é excepcional; nunca exceder 36/12 sem um novo contrato explícito.

Validar `rodadas >= 3 × ciclos`. Quando somente ciclos forem informados, elevar as rodadas ao mínimo coerente; quando somente rodadas forem informadas, usar no máximo `min(2, floor(rodadas ÷ 3))` ciclos, com 0 no modo expresso de rodada única. Se ambos forem explícitos e incompatíveis, pedir correção antes de executar.

Não invocar todos os CLIs automaticamente. Quando houver lista explícita, usar apenas os participantes pedidos. “Debata com X” significa host + X; “debate entre X e Y” significa exatamente X e Y. Sem nomes, usar o padrão host + contraparte. Exigir ao menos duas cadeiras. Não substituir silenciosamente modelo indisponível.

Uma lista explícita de modelos também é fechada: usar exatamente os modelos solicitados, nos papéis indicados. Não acrescentar Claude, Codex, o host ou outro modelo. Aceitar alias do CLI e identificadores `provedor/modelo` quando suportados.

Quando o usuário disser “N rodadas por tentativa”, gravar esse valor separadamente do número de tentativas do loop. Rodadas são interações dentro da deliberação de uma versão; tentativas são versões sucessivas do artefato.

Uma rodada é uma fase coordenada de manifestação sobre a mesma versão. Várias cadeiras podem responder em paralelo nessa fase: a rodada global aumenta uma vez, e cada resposta aumenta o contador individual da cadeira. Assim, 8 rodadas comportam, por exemplo, dois ciclos completos e duas rodadas de verificação.

## Papéis opcionais em artefatos

Quando o debate alimentar um artefato, qualquer CLI/modelo pode ser redator, consolidador iterativo, crítico, revisor, avaliador ou auditor. Por padrão, o redator é o host atual e também corrige as versões seguintes: Claude no Claude, Codex no Codex, Gemini no Gemini, Antigravity no Antigravity, Grok no Grok e OpenCode no OpenCode. Uma escolha explícita pode designar outro consolidador.

Fixar os papéis no início. Separar papel, CLI, modelo, provedor e sessão. O mesmo modelo pode exercer mais de um papel quando escolhido, mas avaliação ou auditoria pelo mesmo modelo do redator deve ser registrada como `hold_out_de_modelo: false` e não pode ser descrita como independente. Auditoria sempre ocorre em sessão nova e cega.

Para participantes que também componham painel ou auditoria, aceitar `automatico`, `modelo diferente do redator`, `provedor diferente`, `modelo escolhido pelo usuário` ou `mesmo modelo em sessão independente`. O último caso é diversidade reduzida, não independência de modelo.

Se uma cadeira diversa estiver indisponível, não substituir silenciosamente. Obedecer à escolha confirmada: pausar ou reduzir o quórum. Redução só pode ocorrer quando ainda houver maioria e o mínimo configurado; informar cadeira ausente, impacto na diversidade e confiabilidade reduzida.

## Consenso sobre artefato produzido

Quando `$loop-debate-agentes` enviar uma versão candidata:

1. Tratar o hash submetido como objeto congelado de deliberação. Todos possuem permissão técnica de escrita, mas somente o redator, consolidador ou revisor-publicador explicitamente autorizado pelo loop pode publicar a próxima versão canônica. A própria deliberação permanece sem edição.
2. Registrar caminho e hash SHA-256 antes da primeira rodada.
3. Fazer todas as cadeiras avaliarem exatamente o mesmo conteúdo, fontes e critérios.
4. Formular a pergunta como aceitação do artefato: se ele satisfaz objetivo, público, formato, precisão, clareza, coerência e requisitos.
5. Deliberar sobre bloqueadores e ressalvas sem modificar silenciosamente o arquivo congelado. Críticos e revisores podem criar pareceres, patches e candidatos alternativos em caminhos próprios.
6. Vincular o consenso ao hash. Qualquer alteração posterior invalida o veredito e exige nova rodada sobre a nova versão.
7. Se houver dissenso, devolver cada ponto ao loop como entrada da próxima correção pelo responsável resolvido em `consolidacao_iterativa`.
8. Quando `reexecutar_a_cada_nova_versao` estiver ativo, repetir toda esta deliberação em cada tentativa, mesmo que a versão anterior tenha sido aprovada.

O consenso do artefato não remove avaliador, críticos, revisor, painel ou auditor já configurados. Ele confirma que as cadeiras aceitam a versão produzida; os demais gates continuam valendo.

O consenso sempre se vincula ao hash de um único candidato congelado. Pareceres, patches e artefatos alternativos não recebem aprovação por terem sido discutidos e nunca substituem o canônico. Por padrão, o redator original responde às objeções e produz o próximo canônico; se o run confirmar `consolidador_designado`, esse responsável responde, consolida e assina a autoria das versões seguintes. A nova versão recebe novo hash e recomeça a deliberação.

O consenso não escolhe silenciosamente quem corrige. Essa decisão pertence ao loop e deve aparecer na prévia como `redator_original`, `consolidador_designado` ou `publicacao_compartilhada`, separada da consolidação final cega. Se o responsável ou o turno de publicação mudar ou ficar indisponível, exigir nova confirmação ou aplicar apenas o fallback já autorizado.

Quando houver duas ou mais consolidações finais cegas:

1. deliberar e avaliar cada candidata separadamente, sempre pelo hash exato;
2. criar uma candidata para cada modelo explicitamente escolhido, sem inserir participantes adicionais;
3. não revelar nenhuma candidata aos outros autores antes de todas estarem congeladas;
4. não escolher, fundir nem declarar uma vencedora automaticamente;
5. preservar eventual consenso, nota e dissenso próprios de cada candidata;
6. aguardar escolha humana ou pedido explícito de síntese;
7. executar novamente o modo deliberativo configurado sobre o hash escolhido ou sintetizado, conforme a política por tentativa, antes da aprovação final.

Uma síntese é um terceiro artefato, não a soma automática das aprovações anteriores. Toda mudança invalida os gates herdados.

## Decisor final opcional

Se o usuário escolher um decisor, enviar a ele o mesmo hash, posições anonimizadas, dissensos, evidências e critérios depois do debate. O decisor resolve ponto por ponto as matérias interpretativas, estratégicas, de risco ou preferência e justifica a decisão.

Decisão não é consenso: se as cadeiras divergirem, informar o dissenso mesmo quando o decisor autorizar prosseguimento. Na estratégia `consenso_com_decisao_final`, essa autorização pode satisfazer o gate deliberativo quando todos os bloqueios materiais sujeitos a julgamento forem resolvidos; rotular `decisão final sem consenso`. No modo `consenso_estrito`, a decisão apenas orienta a correção. O decisor não pode dispensar alvo ou piso, ignorar erro factual crítico, aprovar outro hash, editar o artefato nem substituir avaliação independente ou auditoria cega. Se exigir correção, aplicar à nova versão a política por tentativa configurada; nunca reabrir ou omitir silenciosamente a deliberação.

## Participantes

Antes de resolver CLIs, ler `~/.agents/multiagent-manifest.json`. Separar `seat` semântica, modelo solicitado e `route` executada. A política estrita exige Claude Opus 5 (`claude-opus-5`) por Claude Code; para Grok, usa Cursor com `cursor-grok-4.6-high` por padrão ou a CLI oficial da xAI com `grok-4.6` quando essa rota for escolhida explicitamente; Kimi K3 usa o Kimi Code CLI oficial e Gemini 3.7 usa o Antigravity. Rejeitar modelos incompatíveis com a rota em runs novos e preservar runs históricos já congelados. Manifesto ausente, inválido ou com rota indisponível causa pausa e relatório; nunca trocar de rota silenciosamente. O YAML legado não pode sobrescrever o JSON canônico.

Usar `scripts/cli_adapter.py` para participantes externos:

| Nome natural | Adaptador | Observação |
|---|---|---|
| Claude | `claude` | Aceitar modelo/alias informado |
| Codex | `codex` | Aceitar modelo informado |
| Gemini | `gemini` | Rota `agy`, padrão `gemini-3.7-flash-high`; aceitar override explícito disponível na conta |
| Antigravity | `antigravity` | Comando `agy`, padrão `gemini-3.7-flash-high`, acesso integral com aprovação automática |
| Grok | `grok` | Cursor CLI com `cursor-grok-4.6-high` (padrão) ou CLI oficial xAI com `grok-4.6` (seleção explícita) |
| Kimi | `kimi` | Kimi Code CLI oficial, padrão `kimi-code/k3`, 1.048.576 tokens, esforço `max` obrigatório e provedor efetivo OpenCode Go |
| OpenCode | `opencode` | Provedor/modelo no formato do CLI; Kimi, GLM, DeepSeek e Qwen usam esforço `max` obrigatório |

O host ocupa sua cadeira sem iniciar cópia recursiva de si mesmo. Se o usuário selecionar um modelo específico, repassar `--model`; caso contrário, usar o padrão atual do CLI e informar que ele não foi fixado. Modelos distintos servidos pelo mesmo provedor continuam sendo cadeiras distintas, mas declarar o provedor compartilhado. Personas não contam como modelos independentes.

Depois da confirmação e antes da primeira rodada, executar:

```text
python3 scripts/cli_adapter.py doctor --deep
```

Se uma cadeira explicitamente pedida estiver ausente ou sem autenticação, parar antes do debate e informar o comando de autenticação correspondente. Nunca simular a cadeira nem escolher outro modelo sem autorização.

Validar configuração e veredito pela mesma implementação determinística:

```text
python3 scripts/consensus_gate.py validate-config <config-consenso.json>
python3 scripts/consensus_gate.py validate-verdict <veredito-consenso.json>
python3 scripts/collegiate_gate.py validate-config <configuracao-colegiada.json>
python3 scripts/collegiate_gate.py validate-verdict <recibo-colegiado.json>
```

Os comandos usam por padrão o ledger host-only global
`~/.agents/multiagent-state/nonces.json`. `--check-only` consulta esse mesmo ledger sem efetivar a
transição e falha se algum nonce já tiver sido consumido. Um caminho alternativo só deve ser usado
em teste isolado ou migração explicitamente controlada; um ledger dentro do run não protege contra
replay entre runs.
Overrides por `--nonce-ledger` ou `MULTIAGENT_NONCE_LEDGER` exigem também
`--allow-custom-nonce-ledger` ou `MULTIAGENT_ALLOW_CUSTOM_NONCE_LEDGER=1`.

Uma saída de `--dry-run` possui `simulation: true`, `verdict: null` e valor apenas diagnóstico. Councils ou MCPs sem prova de sessão/modelo ficam limitados ao modo consultivo; seus resultados podem alimentar o loop, mas não satisfazem consenso estrito.

## Persistência das sessões nativas

Em runs novos e legados, o padrão é `persistir_sessoes_nativas: false`; use `true` apenas por pedido
expresso ou quando a recuperação na CLI nativa for necessária. Runs sem o campo continuam
descartáveis. Quando o usuário disser “não salve nas CLIs” ou equivalente, resolver `false` e
mostrá-lo na prévia. Depois da confirmação, passar
`--persist-native-session` ao adaptador em cada manifestação externa.

O escopo padrão é uma sessão nativa por invocação, preservando a independência entre cadeiras e
fases cegas. Cada recibo deve registrar `requested`, `effective`, `confirmed`, rota, identificador ou
título recuperável e o vínculo com a chamada. Falha de confirmação não pode ser ocultada: preserve a
manifestação no ledger central e informe que o espelho nativo ficou não confirmado. Sessões nativas
são apenas espelhos convenientes; `~/.agents/runs`, o ledger do fluxo e o `outbox` do bridge continuam
canônicos. Histórico visível em CLI ou app nunca prova independência, consenso ou aprovação.

Um UUID enviado à CLI é apenas `session_requested_id`. `session_id` e `confirmed=true` só podem ser
gravados quando a saída estruturada ou uma consulta posterior da própria CLI devolver o
identificador em campo de envelope confiável. Nunca promover o UUID solicitado ou um eco dentro do
texto gerado a sessão observada por inferência. Da mesma forma, confirmar modelo somente por campos
de envelope/uso definidos pela CLI; menções aninhadas pelo agente não provam modelo efetivo.

Usar 1800 segundos como timeout de cada chamada. Aceitar até 3600 segundos apenas como exceção
justificada; acima disso, dividir o trabalho e retomar a sessão confirmada. O timeout limita a
invocação corrente, não apaga o ledger central nem define a expiração da sessão nativa.

## Resolver o escopo local

1. Usar primeiro caminhos, arquivos anexados ou seleções mencionados pelo usuário.
2. Se ele disser “estes arquivos”, usar os arquivos anexados ou o contexto ativo.
3. Se disser “diff”, usar os arquivos alterados no Git.
4. Sem caminhos explícitos, localizar arquivos prováveis com `rg --files` e buscas por símbolos/termos.
5. Incluir implementação, dependências diretas, testes e configuração relevante.
6. Limitar o pacote a 20 arquivos de texto. Se exceder e não houver priorização segura, pedir uma única clarificação curta.
7. Excluir segredos, `.env`, credenciais, tokens, chaves privadas, caches e artefatos gerados.

Criar um manifesto compartilhado com raiz, caminhos relativos e hashes SHA-256. Todas as cadeiras devem examinar exatamente essa lista. Arquivos adicionais só entram quando justificados e adicionados ao manifesto para todos.

## Invocar com segurança

Aplicar por padrão o contrato `adaptive_output_v1` do manifesto. `adaptive_up_to_native_max` significa: responder somente na extensão necessária, mas poder usar até o teto efetivo disponibilizado pela rota para o modelo, sem `max_tokens` global artificial. Não confundir esse teto com a janela total de contexto. Uma meta de palavras por fase é flexível e pode ser excedida para preservar completude; um limite menor só prevalece quando o usuário o pedir expressamente.

Quando a CLI não expuser controle explícito de saída, registrar `output_control = native_route_ceiling` e não prometer um número de tokens. Se uma saída obrigatória aparentar truncamento ou terminar com `CONTINUATION_REQUIRED`, continuar com a mesma cadeira, modelo e sessão quando possível, em segmentos com fronteira limpa. Não aprovar artefato incompleto. A continuação não consome crítica, réplica ou revisão adicional quando apenas completa a manifestação já iniciada.

Criar um prompt temporário por cadeira e fase sem interpolar seu conteúdo em shell. Invocar:

```text
python3 scripts/cli_adapter.py invoke --participant NOME --root RAIZ --prompt-file ARQUIVO [--model MODELO] [--effort NIVEL] [--output-policy adaptive_up_to_native_max] [--persist-native-session]
```

O adaptador não usa shell. O nível de esforço só deve ser enviado quando a rota o oferece; o Antigravity aceita `--effort`. Kimi K3, GLM, DeepSeek e Qwen usam `max` obrigatoriamente e não podem ser rebaixados. Na rota OpenCode, modelos não chineses continuam aceitando o nível solicitado ou o padrão nativo. Remover temporários ao terminar. Não incluir `.env`, credenciais, tokens, chaves privadas ou conteúdo fora do manifesto.

## Rodada 1 — análise cega

Cada cadeira analisa o mesmo manifesto sem ver posições alheias e retorna:

```text
CADEIRA: CLI | MODELO | PROVEDOR
RECOMENDAÇÃO: posição curta
ACHADOS: afirmações com evidência caminho:linha
BLOQUEADORES: problemas críticos ainda não resolvidos, ou “nenhum”
O_QUE_MUDARIA_MINHA_OPINIÃO: condição concreta
CONFIANÇA: alta | média | baixa
```

Não compartilhar posições nesta rodada. Anonimizar saídas como `Cadeira A`, `B`, `C` antes da crítica; guardar o mapeamento apenas para o relatório final.

## Ciclos de crítica–réplica–revisão

Executar até o número resolvido de ciclos. O padrão é 2 ciclos por cadeira;
o caso pode configurar até 6 na faixa recomendada e até 12 excepcionalmente, com justificativa,
progresso mensurável e controle de custo. Em cada ciclo composto:

1. **Rodada de crítica:** cada cadeira recebe as posições anonimizadas, reconhece o argumento mais forte e formula uma crítica principal baseada em `caminho:linha`. Uma resposta de crítica conta como uma crítica usada, mesmo que aborde vários pares.
2. **Rodada de réplica:** cada cadeira recebe as críticas dirigidas a ela e responde à objeção mais forte sem acessar identidades.
3. **Rodada de revisão/consolidação:** cada cadeira mantém ou altera sua posição. Mudança exige nomear a evidência ou falha específica; ausência disso invalida a mudança.
4. **Contagem:** registrar por cadeira `críticas usadas`, `réplicas usadas` e `revisões usadas`; nenhuma pode exceder o limite de ciclos confirmado para a tentativa.
5. **Avaliação:** testar consenso após a revisão. Encerrar cedo quando ele permanecer válido por duas avaliações consecutivas.

Incluir a diretiva: não mudar por maioria, repetição ou pressão por consenso; mudar somente diante de argumento válido e evidência identificada. O host participante deve sustentar análise própria, não atuar apenas como sintetizador.

Se ainda houver rodadas globais depois de consumir os ciclos, usá-las somente para conferir evidência factual contestada, executar verificações de leitura e reavaliar o consenso. Não ultrapassar o limite de ciclos confirmado para a tentativa.

## Testar o resultado deliberativo

No modo `estrito` ou `com_decisor`, marcar consenso somente quando todas as condições forem verdadeiras:

1. As recomendações são semanticamente equivalentes.
2. Não existe bloqueador crítico isolado sem resposta baseada nos arquivos.
3. Os achados centrais são compatíveis com as mesmas evidências locais.
4. Todas as cadeiras têm confiança média ou alta, ou uma abstenção é explicitamente justificada.
5. O resultado permanece estável em 2 avaliações consecutivas; no modo explicitamente limitado a uma rodada, uma única avaliação só pode produzir `acordo provisório consultivo`, nunca consenso forte ou aprovação.

Para um artefato, exigir também que todas as posições se refiram ao mesmo hash e que nenhuma cadeira mantenha bloqueador que impeça sua entrega. Concordância apenas sobre “como corrigir depois” não é consenso favorável sobre a versão atual.

Continuar somente enquanto houver desacordo material, ciclos ou verificações úteis e rodadas disponíveis. Não transformar maioria em consenso. Não prolongar a deliberação para apagar dissenso válido.

Em `com_decisor`, se essas condições falharem, encaminhar os pontos ao decisor conforme o contrato e rotular o resultado `decisão sem consenso`. Em `consultivo`, não testar aprovação por consenso: entregar acordos, divergências, evidências e recomendação agregada. Em `desativado`, não fazer chamadas externas nem emitir veredito deliberativo.

## Entregar o resultado

Se houver consenso, retornar:

- `Consenso alcançado em N rodadas e C ciclos`;
- recomendação conjunta;
- evidências decisivas com `caminho:linha`;
- caminho e hash SHA-256 do artefato consensuado, quando aplicável;
- ressalvas e condição que invalidaria o consenso.

Sem consenso, retornar:

- `Sem consenso após N rodadas e C ciclos`;
- posição final de cada cadeira com CLI, modelo e provedor;
- pontos de dissenso enumerados individualmente;
- para cada ponto, posições e respectivas evidências `caminho:linha`;
- tipo: factual, interpretativo, estratégico, de risco ou de preferência;
- consequências práticas de cada posição;
- informação ou teste que permitiria decidir.

Em `com_decisor`, acrescentar decisão ponto a ponto, fundamento, hash e a indicação `decisão sem consenso`. Em `consultivo`, entregar recomendação não vinculante, acordos, dissensos e evidências sem usar o veredito “aprovado em consenso”. Em `desativado`, informar que a etapa foi omitida pela configuração e não produzir relatório fictício de participantes.

Sempre informar configuração resolvida, participantes efetivamente ativos, falhas, contadores individuais, arquivos analisados e confiabilidade da execução. Não modificar o projeto durante a deliberação. Se a solicitação também autorizar implementação, modificar somente depois do veredito.
