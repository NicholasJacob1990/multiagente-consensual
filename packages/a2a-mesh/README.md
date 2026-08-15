# A2A Mesh

Runtime complementar do **Multiagente Consensual**. O pacote fornece:

- servidores A2A locais para Codex, Claude, Gemini e Grok 4.6 High via Cursor;
- bridge MCP `a2a-mesh`;
- painel web de chamadas, debates, consenso, ensemble, equipes e planos;
- sandbox visual com uma sessão de CLI por agente;
- armazenamento SQLite e eventos SSE locais.

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

O Grok é um peer nativo com rota fixa pelo `cursor-agent`, modelo obrigatório
`cursor-grok-4.6-high` e limite padrão de dois processos simultâneos. A execução usa `stream-json`,
confirma `system/init.model` e falha de forma explícita se faltar o evento final `result`.

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
