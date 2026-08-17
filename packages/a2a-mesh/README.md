# A2A Mesh

Runtime complementar do **Multiagente Consensual**. O pacote fornece:

- oito servidores A2A locais para Codex, Claude, Gemini, Grok, GLM, DeepSeek, Kimi e Qwen;
- bridge MCP `a2a-mesh`;
- painel web de chamadas, debates, consenso, ensemble, equipes e planos;
- sandbox visual com uma sessão de CLI por agente;
- armazenamento SQLite e eventos SSE locais.

![Página inicial do A2A Mesh com oito agentes e ações rápidas](https://github.com/NicholasJacob1990/multiagente-consensual/releases/download/v1.10.0/a2a-mesh-home-v1.10.png)

Visão completa da página inicial, com atalhos, equipe e compositor:

![Página inicial completa do A2A Mesh com atalhos, seleção da equipe e compositor](https://github.com/NicholasJacob1990/multiagente-consensual/releases/download/v1.10.0/a2a-mesh-home-full-v1.10.png)

Durante a execução, cada tarefa apresenta fases, agente ativo e telemetria:

![Catálogo do A2A Mesh com modelos selecionáveis do Antigravity, Cursor e OpenCode](https://github.com/NicholasJacob1990/multiagente-consensual/releases/download/v1.10.0/a2a-mesh-models-v1.10.png)

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
| Qwen 3.8 Max | `127.0.0.1:3148` | `http://127.0.0.1:3148/ui` | `http://127.0.0.1:3148/sandbox` |

O Grok é um peer nativo com duas rotas explícitas e sem fallback silencioso. A rota padrão usa
`cursor-agent` com `cursor-grok-4.6-high`; a alternativa usa a CLI oficial `grok` com `grok-4.6`
e esforço `xhigh`. A rota Cursor confirma `system/init.model`; a rota oficial confirma o catálogo
da CLI e exige autenticação própria por `grok login`. Ambas têm limite padrão de dois processos.

GLM, DeepSeek e Qwen são peers nativos pelo OpenCode Go. Começam, respectivamente, com
`opencode-go/glm-5.3`, `opencode-go/deepseek-v4-pro` e `opencode-go/qwen3.8-max`, mas cada cadeira
pode receber qualquer modelo atualmente listado por `opencode models`, sempre na variante `max`.
Como as três rotas compartilham o banco local do OpenCode, o adaptador serializa seus
processos para evitar disputa de lock. O Kimi é invocado exclusivamente pelo Kimi Code com
`kimi-code/k3`, por meio do wrapper `kimi-secure`: ele lê do Keychain a mesma credencial OpenCode
Go já cadastrada no host e cria o provider `KIMI_MODEL_*` apenas na memória do processo-filho. A
mesh distingue `credentialAvailable` de `modelVerified`; a primeira chamada autenticada confirma o
modelo efetivo. A chave não entra nos argumentos, no banco ou nos logs, e não há fallback silencioso.

## Comandos do painel

Abra o painel autenticado com `a2a-mesh open`. Texto comum é enviado aos agentes selecionados.
Use os botões da faixa **Equipe** para ligar ou desligar cadeiras e comandos curtos para escolher
outro modo:

| Comando | Ação |
|---|---|
| `/call <agente> <prompt>` | Chama qualquer um dos oito agentes |
| `/broadcast <prompt>` | Consulta a equipe selecionada em paralelo, sem síntese |
| `/consensus <questão>` | Consulta a equipe selecionada e pede síntese ao juiz |
| `/debate <tema>` | Executa rodadas adversariais e julgamento |
| `/ensemble <tarefa>` | Gera código, faz revisão cruzada e sintetiza |
| `/team <objetivo>` | Reúne contribuições paralelas e síntese do juiz |
| `/plan <descrição>` | Alterna autor e revisor sobre um plano persistido |
| `/help` | Mostra a ajuda completa no próprio painel |

A seleção fica salva no navegador. **Todos** restaura as oito cadeiras. Para substituir a seleção
somente numa execução, acrescente `--agents=claude,codex,qwen`; o override vale para broadcast,
consenso, ensemble, debate e team.

O botão **Modelos e CLIs** abre a matriz de proveniência do runtime: agente, binário, rota, modelo
configurado, modelo observado, provedor, esforço e estado. O painel consulta os catálogos reais de
`opencode models`, `cursor-agent --list-models` e `agy models`. Assim, é possível escolher o modelo
de Gemini/Antigravity, de cada cadeira OpenCode e do Grok quando sua rota é Cursor. A linha do Grok
também alterna entre **Cursor CLI** e **xAI CLI oficial**. As escolhas ficam salvas no navegador e
são reaplicadas após reinício. Modelos ausentes são recusados, trocas aguardam tarefas em andamento
e não há fallback silencioso. A rota oficial da xAI permanece em `grok-4.6` e exige `grok login`.

O botão **Artefatos** abre uma biblioteca independente do feed. Ela reúne os artefatos das tarefas
recentes — Markdown, Word, PDF, código, arquivos A2A e saídas parciais recuperáveis — com tarefa de
origem, estado, descrição, tamanho, hash SHA-256, pré-visualização textual quando aplicável e download
individual. Os mesmos itens também aparecem junto ao resultado que os produziu. Arquivos criados por
`write_file` são registrados automaticamente. Nas CLIs nativas, o agente declara os arquivos que criou
ou modificou e o runtime preserva uma cópia imutável antes de concluir a tarefa. O download serve essa
cópia, não o caminho mutável original. O limite padrão é 100 MB por arquivo e pode ser ajustado por
`A2A_ARTIFACT_MAX_BYTES`. Limpar o feed não apaga a biblioteca nem os registros duráveis.

O botão **Claro/Escuro** alterna o tema visual e salva a preferência no navegador. O tema claro usa
contraste editorial sobre fundo branco frio, mas preserva as cores que identificam cada agente.

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
