---
description: "Acionar e diagnosticar os fluxos multiagente do plugin: consenso, loop de melhoria, redação jurídica, workflow formal ou bridge com CLIs locais. Use esta entrada quando o Cowork não selecionar automaticamente uma skill."
argument-hint: "[objetivo, participantes, arquivos e limites]"
---

# Entrada única do Multiagente Consensual

Trate o texto abaixo como pedido completo em linguagem natural:

`$ARGUMENTS`

Antes de executar, responda **Plugin Multiagente Consensual ativo** e mostre **Entendi assim** com
objetivo, arquivos, participantes/modelos, estratégia, rodadas, ciclos, versões, critério de parada
e saída esperada. Aguarde confirmação quando houver chamada a modelo externo, alteração canônica,
custo relevante ou escolha material ainda ambígua.

Selecione e leia integralmente a skill mais específica:

- deliberação, votação ou decisão sobre versão exata →
  `${CLAUDE_PLUGIN_ROOT}/skills/consenso/SKILL.md`;
- redação, crítica, réplica, revisão, versões, ensemble ou melhoria iterativa →
  `${CLAUDE_PLUGIN_ROOT}/skills/loop-debate-agentes/SKILL.md`;
- parecer, petição, recurso, decisão, voto, acórdão ou outra minuta jurídica →
  `${CLAUDE_PLUGIN_ROOT}/skills/redacao-juridica-consensual/SKILL.md`;
- pipeline, DAG, swarm, map-reduce, torneio, votação formal ou roteamento adaptativo →
  `${CLAUDE_PLUGIN_ROOT}/skills/workflow-agentes/SKILL.md`;
- configurar, testar ou diagnosticar a fila Cowork ↔ CLIs do Mac →
  `${CLAUDE_PLUGIN_ROOT}/skills/bridge-agentes/SKILL.md`.

Se `$ARGUMENTS` estiver vazio, não invente um trabalho. Liste as cinco capacidades acima, confirme
que elas foram descobertas e ofereça o diagnóstico do bridge. Não trate criação de pedido na fila
como resposta de modelo, consenso ou aprovação.
