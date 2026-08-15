# Swarm dinâmico

Usar `swarm_dinamico_v1` para exploração aberta em que um supervisor pode recrutar, liberar ou substituir especialidades dentro de um pool fechado.

## Estrutura

```json
{
  "supervisor": "claude-opus-juiz",
  "pool_elegivel": ["gpt-codex", "gemini-pro", "grok", "deepseek", "qwen-coder", "kimi"],
  "membros_iniciais": ["gpt-codex", "kimi"],
  "max_membros": 5,
  "max_expansoes": 3,
  "max_geracoes": 4,
  "politica_recrutamento": "lacuna_demonstrada",
  "politica_remocao": "concluido_ou_sem_contribuicao",
  "memoria": "quadro_negro_versionado",
  "sintetizador": "gemini-pro-consolidador"
}
```

“Criar agente” significa iniciar nova cadeira/sessão com identidade elegível; não instalar software, criar conta ou conceder permissão. Um membro novo deve vir do pool confirmado.

## Ciclo

1. Supervisor publica tarefas e lacunas no quadro negro.
2. Membros reivindicam tarefas sem sobreposição desnecessária.
3. Cada membro entrega contribuição com evidências e hash.
4. Supervisor mede cobertura, novidade, conflito e custo.
5. Recrutar somente se houver lacuna material e orçamento.
6. Liberar membro concluído, redundante ou persistentemente improdutivo; preservar seu histórico.
7. Sintetizador produz candidata a partir das contribuições congeladas.
8. Encerrar por cobertura, consenso configurado, ausência de progresso ou limites.

Registrar `membro_recrutado`, `membro_liberado`, `tarefa_reivindicada`, `contribuicao_publicada`, `conflito_detectado` e `geracao_encerrada`.

## Guardrails

- Supervisor não pode recrutar a si próprio com outra identidade para contornar limites.
- Máximo de uma expansão por geração, salvo confirmação diferente.
- Remoção não apaga contribuição nem dissenso.
- Substituição por falha precisa ser fallback autorizado.
- Swarm não decide sozinho ações externas ou destrutivas.
- Se composição ficar estável e dependências forem conhecidas, converter o plano em DAG em vez de manter expansão dinâmica.

## Resultado

Entregar roster por geração, razões de recrutamento/remoção, tarefas, cobertura, contribuições exclusivas, conflitos, custo marginal de cada expansão e candidata sintetizada. Não chamar a candidata de aprovada.

