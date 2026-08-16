# A2A Mesh

Runtime complementar do **Multiagente Consensual**. O pacote fornece:

- sete servidores A2A locais para Codex, Claude, Gemini, Grok, GLM, DeepSeek e Kimi;
- bridge MCP `a2a-mesh`;
- painel web de chamadas, debates, consenso, ensemble, equipes e planos;
- sandbox visual com uma sessão de CLI por agente;
- armazenamento SQLite e eventos SSE locais.

![Página inicial do A2A Mesh com título, sete agentes e ações rápidas](https://raw.githubusercontent.com/NicholasJacob1990/multiagente-consensual/main/docs/images/a2a-mesh-home-v1.9.png)

Durante a execução, cada tarefa apresenta fases, agente ativo e telemetria:

![Painel local do A2A Mesh com sete agentes, stepper e telemetria](https://raw.githubusercontent.com/NicholasJacob1990/multiagente-consensual/main/docs/images/a2a-mesh-panel-v1.9.png)

O servidor se vincula exclusivamente a `127.0.0.1`. Credenciais, `.env`, sessões e históricos não
são distribuídos. As CLIs usam a autenticação já existente na máquina do usuário.

## Instalação recomendada

Use o instalador principal:

```bash
npx @nicholasjacob90/multiagente-consensual install --all --with-a2a
```

Ou instale globalmente e gerencie o runtime diretamente:

```bash
npm install --global @nicholasjacob90/a2a-mesh
a2a-mesh install
a2a-mesh status
a2a-mesh open
```

## Endereços locais

| Agente | Servidor | Painel | Sandbox |
|---|---:|---:|---:|
| Codex | `127.0.0.1:3141` | `http://127.0.0.1:3141/ui` | `http://127.0.0.1:3141/sandbox` |
| Claude | `127.0.0.1:3142` | `http://127.0.0.1:3142/ui` | `http://127.0.0.1:3142/sandbox` |
| Gemini | `127.0.0.1:3143` | `http://127.0.0.1:3143/ui` | `http://127.0.0.1:3143/sandbox` |
| Grok | `127.0.0.1:3144` | `http://127.0.0.1:3144/ui` | `http://127.0.0.1:3144/sandbox` |
| GLM 5.3 | `127.0.0.1:3145` | `http://127.0.0.1:3145/ui` | `http://127.0.0.1:3145/sandbox` |
| DeepSeek V4 Pro | `127.0.0.1:3146` | `http://127.0.0.1:3146/ui` | `http://127.0.0.1:3146/sandbox` |
| Kimi K3 | `127.0.0.1:3147` | `http://127.0.0.1:3147/ui` | `http://127.0.0.1:3147/sandbox` |

O Grok é um peer nativo com rota fixa pelo `cursor-agent`, modelo obrigatório
`cursor-grok-4.6-high` e limite padrão de dois processos simultâneos. A execução usa `stream-json`,
confirma `system/init.model` e falha de forma explícita se faltar o evento final `result`.

GLM e DeepSeek são peers nativos pelo OpenCode Go, respectivamente com os modelos fixos
`opencode-go/glm-5.3` e `opencode-go/deepseek-v4-pro`, ambos na variante `max`. Como as duas rotas
compartilham o banco local do OpenCode, o adaptador serializa seus processos para evitar disputa de
lock. O Kimi é invocado exclusivamente pelo Kimi Code com `kimi-code/k3`; sua saúde permanece como
"verificação pendente" até a primeira execução autenticada e não há fallback silencioso.

## Comandos do painel

Abra o painel autenticado com `a2a-mesh open`. Texto comum é enviado a todos
os agentes. Use comandos curtos para escolher outro modo:

| Comando | Ação |
|---|---|
| `/call <agente> <prompt>` | Chama qualquer um dos sete agentes |
| `/broadcast <prompt>` | Consulta todos em paralelo, sem síntese |
| `/consensus <questão>` | Consulta todos e pede síntese ao juiz |
| `/debate <tema>` | Executa rodadas adversariais e julgamento |
| `/ensemble <tarefa>` | Gera código, faz revisão cruzada e sintetiza |
| `/team <objetivo>` | Reúne contribuições paralelas e síntese do juiz |
| `/plan <descrição>` | Alterna autor e revisor sobre um plano persistido |
| `/help` | Mostra a ajuda completa no próprio painel |

Exemplo:

```text
/debate --rounds=6 --judge=claude --order=rotate
PostgreSQL ou SQLite para este produto?
```

O consenso do painel é consultivo. Use o comando principal `/consenso` para
aprovar um arquivo real por hash e recibos independentes.

### Execução durável e streaming

Os comandos do painel são submetidos pelos métodos `mesh/*Async`: a interface recebe um ID em
segundos, libera o campo de entrada e acompanha a tarefa sem manter a requisição original aberta.
Cada delta textual que a CLI realmente fornece aparece ao vivo por SSE, acompanhado do agente e da
fase. Esses deltas não ocupam o ledger append-only: o schema v4 mantém um checkpoint substituível
por tarefa e agente, enquanto fases, argumentos e síntese continuam como eventos duráveis. O painel
não exibe raciocínio interno oculto; se uma CLI só entregar a resposta ao final, ele
mostra estados e fases até o texto ficar disponível.

Cada cartão de execução possui um stepper adaptado ao protocolo escolhido: por exemplo,
`Geração → Revisão cruzada → Revisão → Síntese → Resultado` no ensemble. A mesma faixa
mostra tempo decorrido, TTFT, tokens, custo e tempos por etapa quando esses dados são fornecidos
pela CLI. Cancelamentos registram também o tempo entre o clique e a confirmação do coordenador.
Métricas ausentes aparecem como `—`; o painel não inventa estimativas.

Os eventos possuem IDs persistidos em SQLite. Após queda de rede, recarga da página ou reconexão do
SSE, o painel solicita os eventos posteriores ao último ID e busca o resultado completo da tarefa
terminal. Perder a conexão não reinicia o modelo. Se um stream cair, o coordenador consulta o ID da
tarefa remota já criada; não abre outra sessão silenciosamente. Saída parcial de uma execução
malsucedida é preservada como `partial-output.md`. O recuperador combina, por agente,
o checkpoint exato mais novo quando houver e o diálogo cronológico legado dos demais. Tokens
repetidos legítimos são preservados, mas a resposta final não é duplicada sobre seus próprios deltas.

O replay é paginado em até mil eventos por conexão. Se a lacuna ultrapassar esse teto defensivo,
o servidor emite
`mesh-gap` e o painel busca as páginas restantes pela timeline durável. O botão **Clear** grava um
corte temporal: eventos anteriores não reaparecem ao reconectar. Duas notificações terminais
simultâneas são coalescidas na UI, e estados terminais usam transição compare-and-set para que uma
conclusão tardia nunca sobrescreva cancelamento ou falha.
Ao alcançar o limite defensivo de eventos de uma tarefa, o ledger grava um evento
`mesh_gap`, suprime somente deltas intermediários excedentes e ainda persiste o estado terminal.
Como tokens ao vivo usam checkpoints substituíveis, eles não conseguem saturar esse limite antes
de uma síntese.

No MCP, `a2a_call`, `a2a_broadcast`, `a2a_team`, `a2a_consensus`, `a2a_debate`, `a2a_ensemble` e
`a2a_plan` também devolvem recibo durável por padrão. Use:

- `a2a_task_status` para consultar sem bloquear;
- `a2a_task_wait` para esperar até 240 segundos por chamada, repetindo com o mesmo ID;
- `a2a_task_cancel` para cancelar a tarefa e a chamada de modelo corrente.

`request_id` torna o envio idempotente no ledger SQLite compartilhado, inclusive entre
coordenadores e após reinício. O timeout padrão de cada chamada de modelo é 30 minutos. O
timeout da orquestração completa é 24 horas por padrão e pode ser configurado, caso a caso, por
`operation_timeout_ms` até cinco dias. Término de uma espera MCP nunca cancela a tarefa nem autoriza
reenvio automático. Cancelamento explícito, ao contrário, propaga ao `task_id` remoto conhecido;
cancelamento do usuário não penaliza o circuit breaker como falha do provedor.
Quando o cliente MCP omite `request_id`, o bridge deriva uma chave estável do pedido numa janela
deslizante padrão de 60 segundos e somente na sessão daquele processo MCP. Uma repetição imediata
do host reutiliza a tarefa, mas processos e clientes independentes não colidem. Para repetir de
propósito durante a janela, informe outro `request_id`; para deduplicar após reinício, forneça um
`request_id` explícito.

Reservas idempotentes sem tarefa nunca são devolvidas como tarefas fantasmas: antes do TTL o
cliente recebe erro retriável e, depois dele, outro coordenador pode assumir. Chaves ligadas a
tarefas terminais são podadas após 30 dias por padrão.

O instalador mescla o MCP em `~/.cursor/mcp.json` sem apagar outras entradas. Uma configuração
`a2a-mesh` divergente é preservada, salvo uso explícito de `--replace-mcp`.

## Administração

```bash
a2a-mesh start
a2a-mesh stop
a2a-mesh restart
a2a-mesh status --json
a2a-mesh doctor
a2a-mesh mcp
```

`install --launchd` cria um serviço de usuário no macOS. O painel permanece local e não é publicado
na internet. A remoção normal preserva token, banco e logs; `uninstall --purge` também remove esses
dados depois de parar os processos gerenciados.
