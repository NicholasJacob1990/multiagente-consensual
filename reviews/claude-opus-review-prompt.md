# Revisão independente do plugin Multiagente Consensual

Atue como revisor principal de arquitetura e segurança. Não altere arquivos. Examine integralmente
o plugin nesta raiz, especialmente:

- `.claude-plugin/plugin.json` e `.claude-plugin/marketplace.json`;
- `.codex-plugin/plugin.json`;
- `skills/consenso`, `skills/loop-debate-agentes`, `skills/redacao-juridica-consensual`,
  `skills/workflow-agentes` e `skills/bridge-agentes`;
- `scripts/cowork_bridge.py`, `scripts/install_host.py`, `scripts/package_plugin.py`;
- `bin/multiagent-bridge`, `assets/multiagent-manifest.json`, `README.md` e testes.

Contexto obrigatório:

- Claude e Claude Opus só podem ser chamados pelo Claude Code CLI.
- Grok só pode ser chamado pelo Cursor CLI, fixado em `cursor-grok-4.6-high`.
- Kimi deve usar o Kimi Code CLI oficial, padrão `kimi-code/k3`; Gemini 3.7 deve usar Antigravity.
- Não pode haver substituição silenciosa de cadeira, rota ou modelo.
- Cowork não alcança localhost; o transporte escolhido é uma fila em pasta compartilhada.
- O bridge é apenas transporte: consenso, tentativas, hashes, autoria, gates e auditoria pertencem
  às skills correspondentes.
- Simulação, seleção, votação, síntese ou simples resposta externa nunca equivalem a aprovação.
- O usuário quer acesso integral às pastas permitido pela conta, mas ações destrutivas continuam
  limitadas ao escopo da tarefa.
- As instalações standalone existentes devem ser preservadas.

Faça uma revisão adversarial e prática. Verifique:

1. bugs que possam perder, duplicar, sobrescrever ou atribuir incorretamente pedidos e respostas;
2. validação de caminhos, UUID, modelo, rota, timeout, saída e raiz autorizada;
3. riscos de execução de arquivos ou prompts trocados durante a chamada;
4. segurança e confiabilidade do LaunchAgent e do empacotamento `.plugin`;
5. compatibilidade razoável com Claude Code, Codex e upload no Cowork;
6. inconsistências entre documentação, manifesto e implementação;
7. se as regras de consenso e artefato canônico continuam verdadeiras;
8. testes faltantes de maior valor.

Retorne exatamente:

```text
VEREDITO: aprovar | aprovar_com_correcoes | reprovar
ACHADOS_CRITICOS:
- ...
ACHADOS_ALTOS:
- ...
ACHADOS_MEDIOS:
- ...
ACHADOS_BAIXOS:
- ...
TESTES_RECOMENDADOS:
- ...
PONTOS_CORRETOS:
- ...
```

Cada achado deve citar `caminho:linha`, impacto e correção concreta. Não invente limitações sem
evidência no código. Se uma categoria estiver vazia, escreva `- nenhum`.
