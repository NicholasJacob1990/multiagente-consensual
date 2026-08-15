# Rubrica jurídica e portões de aprovação

## Escala

Pontue de 0 a 10. O padrão exige média mínima 8,5 e piso 7,0 em cada critério. Nota não compensa bloqueio material: os portões objetivos prevalecem sobre a média.

## Cinco critérios compatíveis com o motor

### 1. Clareza

Avalie organização, precisão da linguagem, identificação das questões, legibilidade, terminologia, referências internas e inteligibilidade da conclusão, dos pedidos ou do dispositivo.

### 2. Profundidade

Avalie suficiência do marco normativo, jurisprudência, provas, teses, distinções, argumentos contrários, riscos, alternativas e consequências práticas.

### 3. Coerência

Avalie a cadeia fatos–provas–normas–fundamentos–conclusão e a congruência entre relatório, fundamentação, pedidos e dispositivo. Detecte contradições internas e mudanças de premissa.

### 4. Precisão conceitual

Avalie fidelidade fática e probatória, adequação processual, vigência normativa, classificação das fontes, exatidão das citações, competência, cabimento, tempestividade, legitimidade e demais conceitos pertinentes.

### 5. Qualidade da explicação

Avalie completude, utilidade profissional, resposta às questões, transparência das incertezas, priorização de riscos e exequibilidade das recomendações ou comandos.

## Portões bloqueantes comuns

Reprove independentemente da nota se houver:

- fato material inventado ou prova significativamente deturpada;
- norma, precedente, citação, número de processo, relator ou resultado inventado;
- fonte decisiva não verificada, superada ou citada fora de contexto;
- omissão material de competência, cabimento, tempestividade ou legitimidade quando pertinente;
- conclusão sem suporte suficiente;
- pedido ou dispositivo contraditório, inexequível ou incongruente;
- argumento contrário capaz de alterar o resultado sem enfrentamento;
- exposição não autorizada de dado sigiloso ou pessoal desnecessário;
- alteração do texto depois do hash aprovado;
- objeção material aberta ou dissenso ocultado.
- decisão por maioria rotulada como consenso;
- ratio atribuída ao colegiado sem adesão suficiente às proposições essenciais;
- voto concorrente ou dissidente suprimido contra a política de publicação confirmada;
- opinião principal, certidão ou voto que não corresponda ao mesmo hash proclamado.

## Portão de consistência do pacote

Quando houver mais de um artefato, avalie cada documento separadamente com os cinco critérios e os portões do tipo correspondente. Depois, audite o manifesto conjunto e reprove o pacote se houver:

- divergência não explicada em fatos, partes, datas, provas, fontes ou premissas compartilhadas;
- tese, pedido, conclusão, recomendação ou dispositivo incompatível entre documentos relacionados;
- dependência baseada em versão ou hash superado;
- artefato obrigatório sem o gate deliberativo efetivamente configurado, nota, fontes ou auditoria próprios;
- fusão silenciosa de candidatos ou transferência de aprovação entre documentos.

A aprovação conjunta não produz uma nota compensatória do pacote. Todos os itens obrigatórios precisam satisfazer individualmente média, piso e portões; a consistência conjunta é um gate adicional.

## Controles por tipo

### Parecer

- responde a todas as questões da consulta;
- declara escopo, premissas, data de corte e limitações;
- diferencia conclusão jurídica, juízo de risco e recomendação prática;
- não promete resultado nem omite tese contrária relevante.

### Peça de parte

- instrumento, fase e posição processual são compatíveis;
- fatos e pedidos têm apoio nos documentos e na autorização do cliente;
- pedidos principal, sucessivos, subsidiários e acessórios não se contradizem;
- riscos processuais e probatórios estão identificados.

### Minuta decisória

- mantém imparcialidade e considera as posições relevantes;
- respeita contraditório, limites do pedido e dever de fundamentação;
- prova, ônus e standard decisório são tratados adequadamente;
- o dispositivo resolve com precisão todas as questões necessárias e somente elas.
- em decisão colegiada, quórum, placar, regra de resultado e adesões por fundamento são reproduzíveis;
- a ratio comum é distinguida de concordância apenas no resultado e de argumentos obiter;
- opiniões concorrentes e dissidentes permanecem identificáveis, preservadas e publicadas conforme a política.

## Formato mínimo da avaliação

```text
Hash avaliado:
Artefato ID:
Decisão: APROVAR | REVISAR | DISSENSO

Notas:
- clareza: 0–10
- profundidade: 0–10
- coerência: 0–10
- precisão conceitual: 0–10
- qualidade da explicação: 0–10
- média:
- piso:

Portões bloqueantes:
- nenhum | lista identificada

Pontos aprovados:
Objeções materiais:
Alterações propostas:
Fontes que exigem verificação:
Condições objetivas para aprovação:
```

Cada crítica deve localizar o trecho, explicar o impacto, apontar evidência e propor correção testável. Evite preferências meramente estilísticas quando não alterarem clareza, precisão ou risco.

No modo pacote, gere também um recibo final com `pacote_id`, manifesto de hashes, dependências, itens obrigatórios, estados individuais, inconsistências cruzadas e decisão `PACOTE_APROVADO | REABRIR_ITENS | PACOTE_NAO_APROVADO`.

## Auditoria cega

O auditor recebe apenas a versão exata, o briefing, a rubrica e o snapshot de fontes necessário. Não recebe notas, críticas, identidade do autor ou histórico decisório anterior. Deve confirmar hash, independência, portões, notas e eventuais dissensos.
