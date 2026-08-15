# Bridge entre Cowork e CLIs locais

## Por que existe

O Cowork executa os componentes do plugin, mas seu ambiente isolado não herda automaticamente os
binários nem as sessões autenticadas do Mac. Além disso, conectores do Cowork não alcançam a rede
local. A fila em pasta compartilhada permite que Cowork e host troquem pedidos de modo auditável,
sem publicar as CLIs.

## Diretório

O padrão no host é `~/.agents/cowork-bridge`:

```text
cowork-bridge/
├── inbox/       pedidos atômicos do Cowork
├── processing/  pedidos reclamados pelo bridge
├── outbox/      respostas e recibos
├── failed/      pedidos inválidos ou chamadas que falharam
└── state/       lock e metadados locais
```

O projeto Cowork deve montar essa pasta e a pasta do artefato. Como a VM pode enxergar a pasta com
outro caminho, o modo recomendado usa `root_id`: um identificador cadastrado privadamente no Mac,
mais um `prompt_rel` relativo. O modo com `root` e `prompt_file` absolutos continua disponível para
Claude Code/Codex. O bridge rejeita `/`, a pasta pessoal inteira e raízes não autorizadas.

O ledger antirreplay, os snapshots dos prompts e o lock ficam fora da pasta compartilhada, em
`~/.agents/cowork-bridge-state`, com acesso somente do usuário do Mac.

## Formato do pedido

Nome recomendado: `<uuid>.request.json`.

```json
{
  "bridge_version": 1,
  "request_id": "uuid",
  "participant": "grok",
  "model": "cursor-grok-4.6-high",
  "root_id": "processo-123",
  "prompt_rel": ".multiagent/prompts/critica.md",
  "effort": "high",
  "output_policy": "adaptive_up_to_native_max",
  "persistir_sessoes_nativas": true,
  "timeout": 1800,
  "created_at": "2026-08-12T22:00:00Z",
  "signature_alg": "hmac-sha256",
  "signature": "hexadecimal"
}
```

O Cowork deve construir o objeto inicialmente sem `signature_alg` e `signature`, passá-lo por stdin
ao assinador e deixar que ele publique o arquivo final de forma atômica:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cowork_bridge.py" sign-request --input - \
  --output "/pasta-compartilhada/inbox/<uuid>.request.json"
```

O pacote hospedado não contém `bin/`. Esse ponto de entrada Python é invocado pela skill/command do
plugin e cumpre a mesma função. No Mac, `scripts/install_host.py` continua instalando o comando local
`multiagent-bridge` para operar o daemon e chamar as CLIs autenticadas.

O segredo chega ao processo pela opção sensível `bridge_secret` do plugin, disponibilizada como
`CLAUDE_PLUGIN_OPTION_BRIDGE_SECRET`; ele não aparece no JSON nem deve ser copiado para arquivos.
O host rejeita pedidos sem HMAC válido, request IDs já consumidos, symlinks, nomes divergentes e
arquivos ainda instáveis. Não inclua tokens, senhas nem conteúdo de `.env`.

## Resposta

O bridge congela o prompt em área privada antes da chamada e cria `<request_id>.response.json` com
rota, modelo solicitado, código de saída, timestamps, hashes pré/pós do prompt, hash do adaptador e
hashes das saídas; o texto completo fica em `<request_id>.stdout.txt` e o diagnóstico em
`<request_id>.stderr.txt`. O recibo usa `model_confirmed=false` até a rota fornecer prova estruturada
do modelo efetivo. Uma resposta com `simulation=true` nunca prova execução nem consenso.

Quando `persistir_sessoes_nativas` for `true`, o adaptador também tenta criar uma conversa
recuperável na CLI correspondente. O recibo acrescenta `native_session_persistence_requested`,
`native_session_persistence_effective`, `native_session_persistence_confirmed`, status e id/título.
Use esses campos para navegação e diagnóstico, não como prova de independência ou aprovação. O
`outbox` e o run em `~/.agents/runs` continuam sendo as fontes canônicas. O padrão é `false`.

## Regras para as skills no Cowork

1. Mostrar **Entendi assim** e aguardar confirmação antes de criar o primeiro pedido.
2. Usar exatamente os modelos confirmados.
3. Criar um pedido por cadeira e fase; não pedir ao bridge que invente o debate inteiro.
4. Vincular críticas e vereditos ao hash do artefato.
5. Aguardar a resposta correspondente antes de avançar dependências.
6. Pausar se a rota estiver ausente, falhar ou responder com modelo diferente.
7. Nunca tratar `dry-run`, timeout, resposta parcial ou saída sem hash como avaliação independente.

## Operação no host

```bash
multiagent-bridge init
multiagent-bridge register-root --id processo-123 --path /caminho/do/projeto
multiagent-bridge list-roots
multiagent-bridge serve --poll-interval 1
```

O cadastro de raízes fica fora da pasta compartilhada, em
`~/.agents/cowork-bridge-config.json`, com permissão somente para o usuário.
Ele contém também o segredo HMAC gerado pelo instalador. Copie-o apenas para o campo sensível
`bridge_secret` nas opções do plugin do Cowork com `multiagent-bridge copy-secret`; o comando usa a
área de transferência sem mostrar o valor no terminal. Para comprometimento suspeito, execute
`multiagent-bridge rotate-secret --copy`, atualize o campo sensível e nunca grave o segredo na fila.

Para restringir as pastas que as cadeiras podem receber:

```bash
multiagent-bridge serve \
  --allow-root /caminho/projeto-a \
  --allow-root /caminho/projeto-b
```

`--allow-root` limita quais raízes podem ser escolhidas como workspace do pedido; ele não é sandbox.
Como a política já confirmada é `full_unrestricted`, as CLIs preservam acesso de leitura, criação,
alteração e remoção às pastas acessíveis à conta do usuário. O pedido e a autorização do usuário
continuam delimitando o que pode ser alterado; ações destrutivas ou efeitos externos não ganham
autorização apenas porque o sistema de arquivos está acessível.

Após queda ou reinício, pedidos órfãos em `processing/` geram recibo visível `interrupted`. Em timeout,
o bridge encerra o grupo de processos inteiro. Saída vazia e alteração do prompt durante a chamada
falham; nenhuma dessas condições pode produzir consenso.
