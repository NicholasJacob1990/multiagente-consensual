# Torneio eliminatório entre candidatos

Usar `torneio_eliminatorio_v1` para selecionar entre artefatos comparáveis por confrontos cegos e regra fixa.

## Estrutura

```json
{
  "candidatos": ["A", "B", "C", "D"],
  "seeding": "sorteio_reprodutivel",
  "seed": 42,
  "formato": "eliminacao_simples",
  "juizes_por_confronto": 3,
  "melhor_de": 1,
  "rubrica": ["correcao", "cobertura", "clareza", "risco"],
  "desempate": "juiz_holdout",
  "ocultar_autoria": true,
  "preservar_eliminados": true
}
```

Congelar candidatos, hashes, rubrica, seeding, juízes e desempate antes de revelar conteúdo aos julgadores. O script de plano cria chaves e byes de forma determinística.

## Confronto

1. Rotular candidatos cegamente.
2. Entregar o mesmo par, fontes e rubrica a cada juiz.
3. Exigir preferência `esquerda`, `direita` ou `empate`, notas e fundamento.
4. Agregar por maioria. Aplicar o desempate predefinido, nunca uma regra escolhida depois do resultado.
5. Promover o hash vencedor; preservar o perdedor e o parecer.
6. Repetir até final ou limite.

Para reduzir viés de posição, alternar ordem por juiz. Juiz não edita candidatos. Se mudança ocorrer entre confrontos, ela cria novo candidato e exige reinício ou chave separada.

## Formatos

O padrão é eliminação simples. `dupla_eliminacao` e `todos_contra_todos` só podem ser usados quando explicitamente confirmados e devem registrar a tabela completa. “Melhor de N” repete julgamento em sessões independentes; não significa reescrever o candidato.

## Resultado

Entregar bracket, seed, byes, juízes, votos, notas, desempates, eliminados, finalistas e vencedor. O vencedor recebe `candidato_selecionado`, não `canonico_aprovado`; se qualidade absoluta importar, encaminhar ao loop.

