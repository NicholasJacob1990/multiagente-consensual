---
name: bridge-agentes
description: "Conectar Claude Cowork às CLIs locais Claude Code, Codex, Cursor/Grok, Kimi Code/K3, OpenCode e Antigravity/Gemini por uma fila auditável em pasta compartilhada. Usar para configurar, diagnosticar ou transportar uma fase de consenso, loop, ensemble ou workflow entre Cowork e o host."
---

# Bridge de agentes para Cowork

Interprete o texto fornecido após `/multiagente-consensual:bridge-agentes` como pedido em linguagem
natural. Antes de chamar um modelo externo, mostre **Entendi assim** e aguarde confirmação explícita.

Leia integralmente [references/cowork-bridge.md](../../references/cowork-bridge.md) antes de criar ou
processar pedidos.

## Detectar a superfície

- Se `multiagent-bridge` e as CLIs estiverem disponíveis, execute no modo host.
- Se o ambiente puder manipular apenas os arquivos compartilhados, execute no modo Cowork/fila.
- Nunca conclua que um modelo respondeu apenas porque um arquivo de pedido foi criado.

## Modo Cowork

Localize, entre as pastas montadas no projeto, uma pasta com `inbox/` e `outbox/`. Se não existir,
explique que o usuário precisa compartilhar a pasta inicializada pelo host. Não tente usar localhost.

Para cada manifestação externa:

1. congele o artefato e o prompt em arquivos, com SHA-256;
2. use um `root_id` já cadastrado no host e `prompt_rel` relativo, sem `..`;
3. gere UUID e JSON sem assinatura conforme a referência;
4. em runs novos, inclua `persistir_sessoes_nativas: false`; use `true` somente quando o usuário
   pedir espelhos recuperáveis nas CLIs nativas;
5. passe o JSON por stdin a `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/cowork_bridge.py" sign-request`;
   esse é o ponto de entrada hospedável declarado pela própria skill, e o plugin fornece o segredo
   sensível sem gravá-lo no prompt nem na pasta compartilhada;
6. aguarde `<uuid>.response.json` e leia as saídas indicadas;
7. valide request id, cadeira, rota, modelo, código de saída, hashes e o recibo de persistência nativa;
8. incorpore a manifestação ao ledger do fluxo;
9. exclua temporários apenas quando não forem recibos necessários à auditoria.

Usar `timeout: 1800` por padrão. Aceitar até `3600` somente como exceção justificada. Para tarefas
mais longas, criar checkpoint e novo pedido de continuação na mesma sessão confirmada, em vez de
ampliar indefinidamente uma chamada.

Se a sessão não permitir aguardar, informe o request id e retome pelo mesmo id quando o usuário
voltar. Não crie pedido duplicado.

## Modo host

Use:

```text
multiagent-bridge doctor --deep
multiagent-bridge init
multiagent-bridge register-root --id meu-projeto --path /caminho/do/projeto
multiagent-bridge serve
```

Na instalação do plugin, configurar a opção sensível `bridge_secret` com o valor de mesmo nome em
`~/.agents/cowork-bridge-config.json`; usar `multiagent-bridge copy-secret` para não mostrá-lo no
terminal. Nunca copiar esse segredo para a pasta compartilhada.

O bridge lê o manifesto empacotado pelo plugin por padrão, mas respeita `MULTIAGENT_MANIFEST` quando
o usuário apontar explicitamente outro manifesto válido. Rota ou modelo incompatível pausa a cadeira.

Para solicitar o espelho nativo em uma chamada direta:

```text
multiagent-bridge invoke --participant claude --root /pasta/do/caso --prompt-file /pasta/do/caso/prompt.md --persist-native-session
```

Esse modo é opcional e desativado por padrão. A resposta central continua no ledger e no `outbox`;
o recibo informa se a sessão nativa foi solicitada, efetivada e confirmada, além do id ou título
recuperável quando a CLI o expuser. Uma conversa nativa nunca é o artefato canônico nem prova consenso.

## Composição

Esta skill é apenas transporte. `consenso` continua responsável pelo veredito;
`loop-debate-agentes`, pelas versões e tentativas; `workflow-agentes`, pelo protocolo; e
`redacao-juridica-consensual`, pelos gates jurídicos. Um recibo do bridge não é aprovação.
