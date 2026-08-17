# Multiagente Consensual

Plugin portátil para Claude Cowork, Claude Code e Codex. Ele empacota os contratos já usados por
`consenso`, `loop-debate-agentes`, `redacao-juridica-consensual` e `workflow-agentes` sem remover as
instalações independentes existentes.

O manual completo atualizado acompanha o pacote em `assets/Manual-completo-comandos-multiagente.pdf`.


### Visão completa do painel

![Página inicial completa do A2A Mesh com atalhos, seleção da equipe e compositor](https://github.com/NicholasJacob1990/multiagente-consensual/releases/download/v1.10.0/a2a-mesh-home-full-v1.10.png)

### Execução observável

![Catálogo do A2A Mesh com modelos selecionáveis do Antigravity, Cursor e OpenCode](https://github.com/NicholasJacob1990/multiagente-consensual/releases/download/v1.10.0/a2a-mesh-models-v1.10.png)

Você não precisa decorar os 29 comandos públicos. O manifesto também registra a skill interna
`bridge-agentes`, usada como transporte do Cowork, totalizando 30 entradas governadas. Comece pelo
resultado desejado:

| Se você quer... | Use... | Resultado |
|---|---|---|
| deixar o sistema escolher o fluxo | `/multiagente` | prévia da estratégia e dos agentes |
| comparar modelos rapidamente | `/a2a-broadcast` | respostas independentes lado a lado |
| fazer um debate curto | `/a2a-debate` | argumentos, juiz e síntese consultiva |
| aprovar a versão exata de um arquivo | `/consenso` | veredito auditável por hash |
| redigir, criticar e corrigir em várias versões | `/loop-debate-agentes` | sucessivas versões até o gate |
| produzir parecer, petição ou recurso | `/redacao-juridica-consensual` | minuta limpa, redline e auditoria |
| distribuir papéis e dependências | `/workflow-agentes` | workflow com handoffs rastreáveis |

Consulte o [guia prático dos comandos](docs/guia-de-comandos.md) para ver a
diferença entre debate, consenso e loop, os comandos próprios do painel e
exemplos completos de código e redação jurídica.

## Instalação única com NPM/NPX

O instalador NPM é separado do pacote importado pelo Cowork. A instalação completa usa:

```bash
npx --yes @nicholasjacob90/multiagente-consensual@latest install --all
```

Para incluir também o runtime A2A local, o bridge MCP e o painel web:

```bash
npx --yes @nicholasjacob90/multiagente-consensual@latest install --all --with-a2a
```

Também é possível instalar ou reparar uma única superfície:

```bash
npx @nicholasjacob90/multiagente-consensual install codex
npx @nicholasjacob90/multiagente-consensual install claude
npx @nicholasjacob90/multiagente-consensual install cursor
npx @nicholasjacob90/multiagente-consensual install opencode
npx @nicholasjacob90/multiagente-consensual install kimi
npx @nicholasjacob90/multiagente-consensual install antigravity
```

O `npx` copia o payload para uma raiz estável em
`~/.local/share/multiagente-consensual/marketplace`, registra marketplaces próprios no Codex e no
Claude Code, sincroniza apenas as superfícies selecionadas, instala o bridge sem copiar credenciais
e gera `cowork/multiagente-consensual.plugin`. O Cowork continua exigindo upload manual desse
arquivo, pois o aplicativo hospedado não aceita instalação silenciosa pela CLI.

## Servidor A2A e painel local

`--with-a2a` instala o pacote complementar `@nicholasjacob90/a2a-mesh`, registra o MCP `a2a-mesh`
no Codex, Claude Code e Cursor quando essas CLIs forem selecionadas e inicia oito servidores vinculados
somente a `127.0.0.1`:

| Agente | Porta |
|---|---:|
| Codex | 3141 |
| Claude | 3142 |
| Gemini/Antigravity | 3143 |
| Grok 4.6 High via Cursor | 3144 |
| GLM 5.3 via OpenCode Go | 3145 |
| DeepSeek V4 Pro via OpenCode Go | 3146 |
| Kimi K3 via Kimi Code | 3147 |
| Qwen 3.8 Max via OpenCode Go | 3148 |

O painel principal fica em `http://127.0.0.1:3142/ui`; o sandbox visual das CLIs fica em
`http://127.0.0.1:3142/sandbox`. O painel acompanha tarefas e eventos em tempo real e executa
chamadas individuais, broadcast, equipes, consenso, debate, ensemble e planejamento. No painel,
selecione visualmente qualquer subconjunto da equipe; **Todos** restaura as oito cadeiras e
`--agents=claude,codex,qwen` substitui a seleção somente naquela execução.

As operações longas são duráveis: painel e MCP recebem um `task_id` imediatamente, enquanto o
servidor continua a execução. O streaming mostra deltas textuais fornecidos pelas CLIs, agente,
fase e estado — nunca raciocínio interno oculto. Os deltas são transitórios no canal ao vivo e um
checkpoint substituível por agente preserva a saída corrente sem consumir o ledger de fases. IDs de
evento persistidos permitem recompor lacunas
após reconexão; `a2a_task_status`, `a2a_task_wait` e `a2a_task_cancel` consultam, aguardam ou cancelam
sem reenviar o trabalho. Saídas parciais de falhas ficam em `partial-output.md`, usando o checkpoint
exato mais novo por agente e, para runs legados, o diálogo cronológico das cadeiras sem snapshot.

O `request_id` é idempotente no ledger compartilhado, não apenas na memória do coordenador. Queda
de SSE é recuperada pelo ID remoto; cancelamento explícito alcança a tarefa filha; e uma transição
terminal compare-and-set impede que resultado tardio substitua `canceled` ou `failed`. Lacunas
extensas do replay são paginadas e sinalizadas ao painel em vez de serem truncadas silenciosamente.
Ao atingir o teto defensivo de eventos, o ledger grava `mesh_gap`, suprime deltas excedentes e ainda
aceita a transição terminal. Assim, uma rajada de tokens não impede que argumentos, síntese e estado
terminal sejam gravados. Se o MCP omitir `request_id`, o bridge usa uma chave estável numa
janela deslizante curta, limitada à sessão do processo MCP. Isso protege retries imediatos sem
confundir janelas ou clientes independentes; para repetição após reinício, informe `request_id`.

O peer `grok` usa exclusivamente `cursor-agent --model cursor-grok-4.6-high`. O runtime confirma o
modelo observado no stream, não usa fallback silencioso e só aceita a resposta após o evento terminal.
GLM 5.3 e DeepSeek V4 Pro usam rotas fixas do OpenCode Go com esforço `max` e exclusão mútua entre
processos para proteger o banco local. Kimi K3 usa exclusivamente o Kimi Code; sem credencial válida
do provedor configurado, o peer continua visível, mas não é marcado como modelo verificado.

```bash
a2a-mesh status
a2a-mesh doctor
a2a-mesh open
a2a-mesh open --sandbox
```

Use `--launchd` junto de `--with-a2a` para iniciar o mesh no login do macOS. Uma configuração MCP
preexistente com o mesmo nome é preservada; `--replace-a2a-mcp` autoriza expressamente sua troca.
O pacote não contém `.env`, chaves, cookies, sessões, bancos nem históricos da máquina de origem.

Diagnóstico e atualização:

```bash
npx @nicholasjacob90/multiagente-consensual status --all
npx @nicholasjacob90/multiagente-consensual doctor --all
npx @nicholasjacob90/multiagente-consensual update --all
npx --yes @nicholasjacob90/multiagente-consensual@latest upgrade --all --with-a2a
```

O último comando força o `npx` a buscar a versão mais recente no registry e atualiza, numa única
execução, as seis superfícies, o plugin, os comandos, as skills e o A2A Mesh fixado por essa versão.
`update` continua disponível para compatibilidade; `upgrade` é o alias recomendado para atualização
completa. Omita `--with-a2a` se quiser atualizar somente o plugin e as superfícies das CLIs.

Antes de sobrescrever arquivos gerenciados, o instalador preserva cópias em
`~/.local/state/multiagente-consensual-backups`. `--dry-run` mostra o plano sem escrever; o
desinstalador remove somente arquivos cujo hash ainda coincide com o registrado e preserva arquivos
modificados pelo usuário. `uninstall --all --purge` também apaga o payload estável e o estado, mas
não apaga credenciais, sessões nem os backups preservados nessa raiz separada.

## Sincronização entre CLIs

Os 30 pontos de entrada públicos podem ser reparados sem excluir comandos particulares:

```bash
python3 scripts/sync_cli_surface.py
```

O sincronizador instala slash commands em Codex, Claude Code, Cursor, OpenCode,
Gemini CLI e, como legado opcional, Grok CLI direto. Também instala os aliases
ausentes como skills portáteis ligadas a `~/.agents/skills`, superfície usada
por Kimi Code e Antigravity. No Kimi, a forma explícita é
`/skill:nome-do-comando`; o Grok novo continua roteado pelo Cursor.

## Superfícies de execução

| Superfície | Como chama outros modelos |
|---|---|
| Claude Code | `multiagent-bridge invoke` ou o adaptador da skill, usando as CLIs do host |
| Codex | adaptador da skill e os mesmos gates determinísticos |
| Cowork | arquivos de pedido/resposta em uma pasta compartilhada, processados pelo bridge no Mac |

O Cowork não alcança `localhost`. Por isso, a fila em pasta compartilhada é o modo recomendado: não
publica um servidor nem expõe as CLIs à internet. Um conector HTTPS autenticado pode ser acrescentado
depois, mas não é necessário para o funcionamento local.

## Instalação no Cowork

O GitHub contém o código-fonte e a documentação, mas o arquivo `.plugin` não é distribuído como
anexo da release. Gere localmente a versão compatível com o Cowork pelo instalador NPM:

```bash
npx --yes @nicholasjacob90/multiagente-consensual@latest install --all --with-a2a
```

No macOS, revele no Finder o pacote gerado:

```bash
open -R "$HOME/.local/share/multiagente-consensual/marketplace/cowork/multiagente-consensual.plugin"
```

Em seguida:

1. Abra o **Claude Desktop** e entre na aba **Cowork**.
2. Abra **Customize → Plugins → Add → Upload plugin**.
3. Selecione
   `~/.local/share/multiagente-consensual/marketplace/cowork/multiagente-consensual.plugin`.
4. Confirme a instalação e habilite o plugin.
5. Nas opções do plugin, cole no campo sensível `bridge_secret` o valor gerado em
   `~/.agents/cowork-bridge-config.json`. Use `multiagent-bridge copy-secret` para copiá-lo sem
   exibi-lo no terminal.
6. Crie uma nova tarefa do Cowork para carregar as skills recém-instaladas.
7. Adicione à tarefa a pasta raiz do trabalho e `~/.agents/cowork-bridge` como pasta compartilhada.
8. No Terminal do Mac, mantenha `multiagent-bridge serve` em execução.

Digite `/` ou clique em `+` na nova tarefa para conferir as skills do plugin. O Cowork exige o
upload manual: o comando `npx` prepara e atualiza o arquivo local, mas não instala silenciosamente
o plugin dentro do aplicativo.

Para iniciar automaticamente a cada login no macOS:

```bash
python3 scripts/install_host.py --launchd
```

O plugin orienta o Cowork a gravar solicitações em `inbox/` e aguardar a resposta em `outbox/`.
Cada pedido usa apenas uma cadeira explicitamente escolhida; a própria skill controla rodadas,
tentativas, hashes, consenso e auditoria.

O arquivo hospedado não publica um diretório `bin/`: dentro do Cowork, a skill chama
`scripts/cowork_bridge.py`. O instalador do host mantém `multiagent-bridge` como wrapper local para
o daemon e para as CLIs do Mac. As duas superfícies preservam o mesmo protocolo e os mesmos gates.

O Cowork assina cada pedido com HMAC por `multiagent-bridge sign-request`; o host congela o prompt,
impede replay, recupera interrupções e encerra toda a árvore da CLI em timeout. O segredo nunca deve
ser gravado na pasta compartilhada.

## Comandos principais

| Família | Comandos | Quando usar |
|---|---|---|
| Entrada e gates | `/multiagente`, `/consenso` | roteamento automático e aprovação por hash |
| Melhoria de artefatos | `/loop-debate-agentes`, `/redacao-juridica-consensual` | crítica, réplica, revisão e novas versões |
| A2A imediato | `/a2a-call`, `/a2a-broadcast`, `/a2a-team`, `/a2a-debate`, `/a2a-consensus`, `/a2a-ensemble` | colaboração rápida entre os oito peers locais |
| Workflows | `/workflow-agentes`, `/pipeline-agentes`, `/dag-agentes`, `/swarm-agentes`, `/map-reduce-agentes` | papéis, dependências e paralelismo |
| Seleção | `/torneio-agentes`, `/votacao-agentes`, `/roteamento-adaptativo` | comparar candidatas ou escolher modelos |
| Conselhos | `/council`, `/council-high`, `/llm-council`, `/multi-debate`, `/pal-council`, `/sage-debate` | deliberação consultiva especializada |

Os exemplos usam a forma curta. Quando a CLI exibir o namespace do plugin, use
`/multiagente-consensual:nome-do-comando`. No Kimi Code, use
`/skill:nome-do-comando`.

As cinco skills principais também podem ser acionadas em linguagem natural. Se o roteamento
automático não ocorrer, use `/multiagente-consensual:multiagente` seguido do objetivo. O comando
confirma qual skill será carregada antes de iniciar. A opção `bridge_secret` não bloqueia a
descoberta do plugin; ela só é exigida quando o Cowork efetivamente assina um pedido ao host.

Os councils e comandos A2A também são preservados, com seus tetos de aprovação originais. Uma
síntese, votação ou seleção nunca vira consenso sem `veredito_consenso_v1` sobre o hash exato.

## Prova de consenso e escopo local

Consenso forte não aceita mais um booleano declaratório. O gate recalcula o arquivo real numa raiz
explícita, resolve cadeiras pelo manifesto e exige, para cada avaliação de estabilidade, um recibo
HMAC do host por cadeira, ligado a nonce, tentativa, rodada, rota, provedor, modelo, execução e hash.
Os nonces são consumidos atomicamente no ledger global
`~/.agents/multiagent-state/nonces.json`; replay entre runs e em `--check-only` é rejeitado. Cada
recibo deve possuir a mesma rodada da avaliação que o referencia. Aprovação e consenso forte
exigem ao menos duas avaliações estáveis; uma rodada única é somente consultiva.
Os nonces só são consumidos depois que todas as regras do veredito passam. Ledger alternativo por
flag ou ambiente requer opt-in adicional explícito.
`consenso_estrito` no gate colegiado incorpora o veredito completo do mesmo hash. Outros resultados
colegiados só efetivam gate forte com arquivo real e um recibo HMAC por voto; sem isso permanecem
`formation_only`.

A formação colegiada separa modalidade de publicação (`seriatim`, `per_curiam` ou
`opinion_of_court`) e método de apuração. `global` (*case-by-case*) continua no
`decisao_colegiada_v1` e é o padrão. `analitico` (*issue-by-issue*) e `hibrido` usam
`decisao_colegiada_v2`, congelam questões e derivação, detectam maiorias cruzadas e, no híbrido,
exigem confirmação bloqueante em segundo ato. Esses modos só são ativados explicitamente; maioria
ou dispositivo derivado nunca equivalem a consenso.
O recibo desse segundo ato assina o hash canônico da cadeira, do booleano `confirma`, do eventual
fundamento divergente, do derivado e da política: inverter a confirmação sem novo recibo falha fechado.

As CLIs continuam com ferramentas completas e autoaprovadas sob a identidade do usuário. O projeto
e diretórios extras são declarados por chamada e a HOME só é adicionada por opção explícita. Isso é
governança auditável, não sandbox do sistema operacional: shell irrestrito do mesmo usuário não é
uma fronteira criptográfica contra agente malicioso. Segredos são removidos do ambiente filho e não
devem entrar em prompts ou pastas compartilhadas.

## Até 20 versões por artefato

`loop-debate-agentes` e `redacao-juridica-consensual` usam 6 versões/tentativas por padrão e aceitam
configuração de 1 a 20 por `artefato_id`. A primeira minuta é v1; cada correção substantiva ou
síntese promovida cria a versão seguinte. A execução para cedo quando os gates fecham e nunca cria
v21. Pareceres, redlines e candidatas não promovidas não contam como versões canônicas.

## Publicação por revisores

O padrão continua seguro: revisores emitem pareceres, patches ou candidatas separadas. Em
`publicar_candidata`, vários agentes podem trabalhar simultaneamente em branches, worktrees ou
arquivos próprios. Em `publicar_canonico`, um revisor explicitamente autorizado publica a próxima
versão canônica sem reincorporação pelo redator; a operação é serializada, exige `base_sha256` e
arquivos reais dentro de um root explícito. O publicador usa lock, estágio no mesmo filesystem,
`fsync`, troca atômica, verificação do hash final e ledger idempotente. Publicações paralelas em
canônicos distintos adquirem primeiro o lock do ledger compartilhado e depois o lock do documento,
sem perder entradas; depois reabrem todos os gates.
Nunca há dois escritores concorrentes no mesmo ponteiro canônico.

## Timeouts e retomada

Chamadas externas usam 30 minutos por padrão e aceitam até 60 minutos somente como exceção
justificada. Loops novos usam limite total padrão de 3 horas, recomendado até 6 horas. Sessões
nativas são descartáveis por padrão e só viram espelhos persistentes por opção explícita. Tarefas
longas devem salvar checkpoint, hashes e recibos e retomar a mesma cadeira por execução isolada ou
sessão confirmada; timeout nunca é aprovação.

Quando expressamente solicitado, `durable_5d_v1` permite que workflows e loops permaneçam
retomáveis por até 432000 segundos — cinco dias corridos. Cada chamada conserva o mesmo timeout,
enquanto `checkpoint.json` é gravado atomicamente após as fronteiras confirmadas. Sono do Mac,
indisponibilidade e tempo offline contam no deadline; não há trabalho sem host ativo. O coordenador
ou bridge retoma o último evento idempotente, respeita os orçamentos diário e total e encerra cedo
por sucesso, falta de progresso, bloqueio, cancelamento, custo, chamadas ou prazo.
O perfil ativo exige `max_segundos`. Repetir um evento só é idempotente quando entrada, saída e
estado coincidem; checkpoints não aceitam o estado `aprovado`, que pertence exclusivamente aos
gates externos.
O relógio injetável por `--now` é reservado a testes e exige `--allow-test-clock`; locks e eventos
idempotentes possuem permissões e limites explícitos.

## Receitas jurídicas automáticas

`redacao-juridica-consensual` resolve automaticamente a receita documental de parecer, petição,
recurso ou minuta decisória e a compila nos campos canônicos do motor. Ensemble N×N e pacote
processual continuam opt-in e podem ser combinados, inclusive por artefato, sem criar skills ou
loops paralelos. Overrides explícitos do usuário sempre prevalecem após confirmação.

## Minutas DOCX com alterações controladas

O perfil `redacao-juridica-consensual` inclui `legal_word_redline_v1`. Depois de cada correção do
redator, ele pode preservar a nova versão limpa e gerar um comparativo incremental. Ao final dos
debates e loops, entrega `minuta-final-limpa.docx` como único canônico aprovado e
`minuta-final-com-alteracoes.docx` como comparação rastreável da base para a final.

O comparador Docxodus roda localmente no Mac e grava revisões OOXML nativas aceitas pelo Microsoft
Word. Diagnóstico:

```bash
python3 skills/redacao-juridica-consensual/scripts/word_redline.py doctor --deep
```

A aprovação sempre adere ao hash do arquivo limpo. Aceitar, rejeitar ou editar parcialmente a cópia
com alterações cria nova versão e exige novo consenso, painel e auditoria aplicáveis.

## Bridge

```bash
multiagent-bridge doctor --deep
multiagent-bridge init
multiagent-bridge register-root --id meu-projeto --path /caminho/do/projeto
multiagent-bridge serve
```

Para testar sem chamar um modelo:

```bash
multiagent-bridge invoke \
  --participant grok \
  --root /caminho/do/projeto \
  --prompt-file /caminho/prompt.md \
  --dry-run
```

Rotas obrigatórias atuais:

- Claude Opus 5 (`claude-opus-5`) → Claude Code CLI;
- Grok → Cursor CLI, modelo `cursor-grok-4.6-high`;
- Kimi → `kimi-secure`, wrapper do Kimi Code CLI oficial, padrão `kimi-code/k3` (1M, esforço `max` obrigatório), faturado pelos créditos OpenCode Go locais;
- Codex → Codex CLI;
- Gemini → Antigravity (`agy`), padrão `gemini-3.7-flash-high`;
- Antigravity → `agy`.
- OpenCode → `opencode-go/glm-5.3` por padrão, preservando qualquer modelo solicitado explicitamente. Kimi, GLM, DeepSeek e Qwen sempre usam esforço `max`; pedidos de rebaixamento falham em vez de serem aplicados silenciosamente.

Não há substituição silenciosa se uma cadeira falhar.

O wrapper Kimi lê a credencial do serviço `multiagente.kimi-opencode-go` no
Keychain e cria o provider temporário por variáveis `KIMI_MODEL_*`. Para migrar
uma instalação antiga que ainda tenha `api_key` no `config.toml`, sem imprimir
o segredo:

```bash
python3 scripts/install_kimi_keychain.py
kimi-secure provider list
```

## Sessões nativas opcionais

O histórico auditável continua centralizado em `~/.agents/runs` e no `outbox` do bridge. Quando for
útil também consultar cada manifestação na CLI de origem, peça em linguagem natural “salve também
as sessões nas respectivas CLIs” ou use:

```bash
multiagent-bridge invoke \
  --participant claude \
  --root /caminho/do/projeto \
  --prompt-file /caminho/do/projeto/prompt.md \
  --persist-native-session
```

O modo é desativado por padrão. Cada invocação recebe uma sessão própria; isso evita misturar
autores, painéis e auditorias cegas. O recibo informa se o espelho foi solicitado, efetivado e
confirmado. Sessões nativas são cópias de conveniência e nunca substituem ledger, hashes, artefatos
ou veredito de consenso.
O UUID enviado à CLI é registrado como `session_requested_id`; só há `session_id` confirmado quando
a saída estruturada ou uma consulta posterior da própria CLI devolve o identificador.
Modelo e sessão são lidos somente do envelope confiável da CLI; ecos aninhados no texto do agente
não contam como observação.
