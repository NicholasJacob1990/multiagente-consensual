# Rubrica e portões de integridade epistêmica

Use esta referência para revisar, auditar ou aprovar análise jurídica. Quando houver `$loop-debate-agentes`, mapear os critérios para a rubrica já vigente; não criar nota paralela nem alterar alvo, piso ou regras do motor.

## Mapeamento para as cinco dimensões do perfil jurídico

### Clareza

- a questão, o objetivo e o escopo estão explícitos;
- fatos, alegações, inferências, premissas e desconhecidos não se confundem;
- a conclusão responde à decisão prática e indica seus limites.

### Profundidade

- fontes, exceções, alternativas, melhor objeção e consequências práticas foram enfrentadas;
- conhecimento tácito ou informação ausente capaz de mudar a resposta foi identificado;
- os cenários correspondem aos objetivos plausíveis, sem inventá-los.

### Coerência

- existe cadeia verificável entre questão, regra, evidência, aplicação e conclusão;
- a recomendação corresponde ao objetivo declarado;
- ressalvas e próximos passos não contradizem a conclusão.

### Precisão conceitual

- fontes estão classificadas por autoridade, vigência, aderência e nível consultado;
- graus de suporte são expressos sem falsa precisão;
- capacidade técnica, recomendação, permissão e autoridade permanecem distintas.

### Qualidade da explicação

- o destinatário consegue decidir com base na análise;
- decisões humanas pendentes são formuladas concretamente;
- cada informação faltante vem acompanhada de seu efeito;
- próximos passos distinguem preparação de atuação externa.

## Portões bloqueantes

Reprovar ou classificar como condicionada/inconclusiva, independentemente da qualidade da redação, se houver:

- fato, prova, norma, precedente ou citação material inventado ou deturpado;
- fonte decisiva não verificada apresentada como confirmada;
- premissa material oculta;
- inferência apresentada como fato;
- alegação unilateral tratada como prova suficiente sem justificativa;
- objetivo humano presumido quando objetivos plausíveis levariam a recomendações incompatíveis;
- conclusão mais ampla do que a jurisdição, data, fonte ou evidência permitem;
- tese contrária capaz de alterar o resultado sem enfrentamento;
- desconhecido decisivo omitido;
- probabilidade numérica sem método ou base declarados;
- ação externa apresentada como autorizada sem concessão verificável;
- “revisão humana” genérica onde deveria existir decisão humana concreta;
- consenso, maioria ou concordância entre modelos usado como prova de verdade;
- alteração de fato, objetivo, fonte, data de corte ou hash sem reabrir as conclusões dependentes.

## Formato mínimo de avaliação

```text
Objeto e versão/hash:
Escopo da revisão:
Veredito: APTO NO ESCOPO | REVISÃO NECESSÁRIA | CONDICIONADO | INCONCLUSIVO

Questão e objetivo:
Proposições decisivas e respectivas classes:
Fontes materiais e nível verificado:
Inferências e premissas:
Desconhecidos e impacto:
Melhor objeção:
Limites de autoridade:
Portões bloqueantes:
Correções ou decisões necessárias:
Cobertura e limitações da avaliação:
```

No loop, o parecer deve ainda indicar o hash exato, localizar cada achado, apontar evidência e propor condição testável de resolução. O parecer é evidência para os gates; não é aprovação por si mesmo.
