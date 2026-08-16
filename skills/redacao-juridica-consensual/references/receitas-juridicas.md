# Receitas jurídicas reutilizáveis

Estas receitas são deltas declarativos sobre `juridico_consensual_v2`. Não são skills, motores,
comandos ou aprovações independentes. Resolver uma receita documental por artefato e ativar os
overlays somente por pedido explícito ou proposta confirmada.

## Sumário

1. Resolução, persistência e precedência
2. Compilação para o contrato do motor
3. Parecer consensual
4. Petição consensual
5. Recurso consensual
6. Minuta decisória
7. Overlay ensemble jurídico
8. Overlay pacote processual
9. Desambiguação e exemplos

## 1. Resolução, persistência e precedência

Aplicar, do mais forte para o mais fraco:

1. campo explícito do usuário após confirmação;
2. delta do overlay, apenas no eixo que ele governa;
3. delta da receita documental;
4. defaults de `juridico_consensual_v2`;
5. defaults de `debate_agents_v1`.

Registrar metadados da receita no mesmo bloco jurídico do artefato:

```yaml
receita:
  documental: parecer_consensual | peticao_consensual | recurso_consensual | minuta_decisoria
  origem: automatica | explicita | legado
  overrides_usuario:
    requested: {}
    effective: {}
    confirmed: false
  lentes_minimas: []
```

Em `artefato_unico`, persistir em `extensoes_dominio.juridico.receita`. Em pacote, persistir uma
cópia por item em `pacote.itens[].overrides.extensoes_dominio.juridico.receita`; não usar uma única
receita documental para todo o run. Configurações legadas sem receita recebem `origem: legado` e
nenhum delta novo.

Inferir somente a receita documental quando o pedido for inequívoco e mostrar o resultado em
**Entendi assim**. Não pedir que o usuário escolha o nome técnico. Os overlays são opt-in:

- `ensemble_juridico`: aceitar “ensemble N×N”, “todos geram e todos revisam todos”, “deep
  ensemble” ou equivalente; fora disso, apenas propor e aguardar confirmação;
- `pacote_processual`: aceitar pedido de pacote ou de vários artefatos com aprovação/canônico
  próprios; mera menção a dois produtos não ativa pacote silenciosamente.

## 2. Compilação para o contrato do motor

As chaves abreviadas abaixo existem somente nesta referência. Compilá-las antes da confirmação e
persistir apenas nos campos canônicos:

| Delta da receita | Campo canônico |
|---|---|
| `tipo_documento`, `subtipo` | `extensoes_dominio.juridico.tipo_documento`, `.subtipo` |
| `posicao_ou_funcao` | `extensoes_dominio.juridico.posicao_ou_funcao` |
| `perfil_intensidade` | `extensoes_dominio.juridico.defaults.debate.perfil_intensidade` |
| `rodadas` | `debate.rodadas_por_tentativa` e espelho `debate.rodadas` |
| `ciclos` | `debate.ciclos_por_participante` |
| `versoes_padrao` | `ciclo_de_melhoria.tentativas`, `loop.tentativas` e `artefatos.versoes_maximas_por_artefato` |
| `consenso.modo` | `consenso.modo` |
| `consenso.politica_por_tentativa` | `consenso.politica_por_tentativa` e estratégia efetiva |
| `lentes_minimas` | `extensoes_dominio.juridico.receita.lentes_minimas` e ledger tipado |
| `pacote_processual` | `modo_artefatos = pacote_multi_artefato` e bloco `pacote` |
| `ensemble_juridico` | `perfil = ensemble_nxn_v1`, `estrategia_da_equipe.tipo = ensemble_nxn` e bloco `ensemble_nxn` |

Nunca gravar `ensemble_nxn_v1` em `estrategia_da_equipe.tipo` nem substituir
`perfil_base = debate_agents_v1`. `lentes_minimas` são checklists vinculados aos gates; falha
material cria objeção na categoria jurídica correspondente e impede aprovação enquanto aberta.

Na combinação documental + ensemble, tratar os números do ensemble como mínimos. Sem override do
usuário, usar `ciclos efetivos = max(ciclos documentais, ciclos do ensemble)` e `rodadas efetivas =
max(rodadas documentais, rodadas mínimas do ensemble, 3 × ciclos efetivos)`. O ensemble profundo
limita as tentativas externas a 3 por padrão; um número explícito confirmado de 1 a 20 prevalece.

Distinguir eixos:

- N produtores e revisão cruzada de todos por todos: `ensemble_juridico`;
- versões finais independentes sem matriz N×N: `consolidacao_final.modo = multipla_cega`;
- votos de julgadores: `formacao_decisao_colegiada`, não ensemble por si só; escolher separadamente modalidade e método `global`, `analitico` ou `hibrido`.

## 3. `parecer_consensual`

Ativar para resposta técnica a consulta, opinião legal, viabilidade ou risco:

```yaml
tipo_documento: parecer
posicao_ou_funcao: imparcial
lentes_minimas: [questao, fatos, fontes, alternativas, riscos, conclusao]
```

Herdar 8 rodadas, 2 ciclos e 6 versões do perfil, salvo override. Exigir resposta objetiva,
separação entre fatos e premissas, posição principal, alternativas sustentáveis e riscos. Não
produzir parecer meramente confirmatório.

## 4. `peticao_consensual`

Ativar para inicial, contestação, réplica, manifestação, memoriais ou incidente não recursal:

```yaml
tipo_documento: peca_de_parte
lentes_minimas: [fatos, prova, preliminares, merito, pedidos, congruencia]
```

Herdar o perfil comum. Propor `perfil_intensidade: complexo`, 10 rodadas e 3 ciclos quando o
briefing confirmar múltiplas teses materiais, grande volume probatório, questão constitucional ou
risco elevado. Não elevar antes de concluir o briefing nem sem mostrar a proposta na prévia.

## 5. `recurso_consensual`

Ativar para razões ou contrarrazões de apelação, agravo, embargos, recurso especial, recurso
extraordinário ou recurso administrativo:

```yaml
tipo_documento: peca_de_parte
subtipo: recurso
perfil_intensidade: complexo
rodadas: 10
ciclos: 3
lentes_minimas: [cabimento, tempestividade, preparo, legitimidade, interesse, dialeticidade,
                 prequestionamento, fatos, prova, teses, efeitos, pedidos]
```

Aplicar apenas pressupostos pertinentes ao recurso concreto. Verificar decisão recorrida, termo
inicial, prazo, efeitos, limites devolutivos e pedido de reforma, anulação, integração ou
esclarecimento. Não incluir juízo institucional de admissibilidade nesta receita.

## 6. `minuta_decisoria`

Ativar para decisão, sentença, voto, acórdão, despacho decisório, juízo de admissibilidade ou ato
institucional que decida direitos:

```yaml
tipo_documento: minuta_decisoria
posicao_ou_funcao: imparcial
lentes_minimas: [relatorio, contraditorio, fundamentacao, pressupostos, congruencia, dispositivo,
                 efeitos]
```

Herdar o perfil comum. Ativar a formação colegiada somente quando o pedido envolver colegiado,
votos, julgamento ou opinião da corte. Propor `opinion_of_court` e método `global`; permitir
`seriatim`, `per_curiam`, `analitico` e `hibrido` por escolha explícita, sem confundir maioria do
colegiado com consenso dos agentes.

## 7. Overlay `ensemble_juridico`

Ativar somente pelo opt-in definido acima:

```yaml
perfil: ensemble_nxn_v1
estrategia_da_equipe: {tipo: ensemble_nxn}
ensemble_nxn:
  profundidade: profundo
  ciclos: 2
  rodadas_minimas: 6
  matriz_revisao: NxN_cega
  autorrevisao_cega: true
```

Cada autor produz candidato independente, revisa todas as candidatas, recebe críticas agregadas,
replica e revisa a própria minuta. A candidata ou síntese selecionada é somente
`canonico_selecionado` e ainda passa por consenso, painel, gates e auditoria.

Em pacote, confirmar o escopo como `todos` ou lista de `artefato_id`. Persistir ensemble por item em
`pacote.itens[].overrides` quando o escopo não abranger todo o run. Não escolher o escopo por custo
ou conveniência do executor.

## 8. Overlay `pacote_processual`

Ativar somente pelo opt-in definido acima:

```yaml
modo_artefatos: pacote_multi_artefato
pacote:
  politica_aprovacao: todos_obrigatorios
  snapshot_compartilhado: true
  auditoria_consistencia_conjunta: true
```

Resolver receita própria em `pacote.itens[].overrides` para cada artefato. Cada item conserva
versões, hash, consenso, painel, auditoria e estado próprios. Compartilhar fontes e premissas sem
transferir aprovação. Modelar dependências no DAG e reabrir apenas itens materialmente afetados.

## 9. Desambiguação e exemplos

- contrarrazões de recurso → `recurso_consensual`;
- juízo de admissibilidade pelo órgão julgador → `minuta_decisoria`;
- opinião técnica que responde consulta → `parecer_consensual`;
- opinião institucional que decide matéria → `minuta_decisoria`;
- cada modelo gera uma versão final, sem revisão cruzada → `multipla_cega`, não ensemble;
- cada julgador profere voto → formação colegiada, não ensemble por si só.

Se o caso ainda permanecer ambíguo e a escolha alterar estrutura, imparcialidade ou pressupostos,
pedir uma única distinção material. Usar as quatro linhas de receita já previstas na prévia da
skill; não criar uma segunda prévia.

Exemplos naturais:

```text
Prepare um parecer com Claude redator, Codex crítico e Grok auditor.
Use o perfil de recurso para elaborar a apelação; faça até 12 versões.
Use ensemble N×N: todos devem produzir a própria contestação e revisar todas as demais.
Produza um pacote com parecer, recurso e minuta de decisão, com aprovação separada por documento.
```
