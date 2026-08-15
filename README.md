# Multiagente Consensual

Plugin portátil para Claude Cowork, Claude Code e Codex. Ele empacota os contratos já usados por
`consenso`, `loop-debate-agentes`, `redacao-juridica-consensual` e `workflow-agentes` sem remover as
instalações independentes existentes.

O manual completo atualizado acompanha o pacote em `assets/Manual-completo-comandos-multiagente.pdf`.

## Instalação única com NPM/NPX

O instalador NPM é separado do ZIP hospedado do Cowork. Depois de publicado no registry, a
instalação completa usa:

```bash
npx @nicholasjacob90/multiagente-consensual install --all
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

Diagnóstico e atualização:

```bash
npx @nicholasjacob90/multiagente-consensual status --all
npx @nicholasjacob90/multiagente-consensual doctor --all
npx @nicholasjacob90/multiagente-consensual update --all
```

Antes de sobrescrever arquivos gerenciados, o instalador preserva cópias em
`~/.local/state/multiagente-consensual-backups`. `--dry-run` mostra o plano sem escrever; o
desinstalador remove somente arquivos cujo hash ainda coincide com o registrado e preserva arquivos
modificados pelo usuário. `uninstall --all --purge` também apaga o payload estável e o estado, mas
não apaga credenciais, sessões nem os backups preservados nessa raiz separada.

## Sincronização entre CLIs

Os 29 pontos de entrada públicos podem ser reparados sem excluir comandos particulares:

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

1. Abra **Customize → Plugins → Add**.
2. Selecione `dist/multiagente-consensual.plugin`.
3. Nas opções do plugin, cole no campo sensível `bridge_secret` o valor gerado em
   `~/.agents/cowork-bridge-config.json`. Use `multiagent-bridge copy-secret` para copiá-lo sem
   exibi-lo no terminal.
4. Crie ou abra um projeto do Cowork e adicione como pasta a raiz do trabalho.
5. Adicione também `~/.agents/cowork-bridge` como pasta compartilhada.
6. No Terminal do Mac, mantenha `multiagent-bridge serve` em execução.

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

- `/multiagente-consensual:multiagente` — entrada única e diagnóstico de ativação
- `/multiagente-consensual:consenso`
- `/multiagente-consensual:loop-debate-agentes`
- `/multiagente-consensual:redacao-juridica-consensual`
- `/multiagente-consensual:workflow-agentes`
- `/multiagente-consensual:pipeline-agentes`
- `/multiagente-consensual:dag-agentes`
- `/multiagente-consensual:swarm-agentes`
- `/multiagente-consensual:map-reduce-agentes`
- `/multiagente-consensual:torneio-agentes`
- `/multiagente-consensual:votacao-agentes`
- `/multiagente-consensual:roteamento-adaptativo`

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
