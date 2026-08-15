# Formação de decisão colegiada

## Sumário

1. [Separação de controles](#separação-de-controles)
2. [Modalidades](#modalidades)
3. [Configuração](#configuração)
4. [Votos, proposições e ratio](#votos-proposições-e-ratio)
5. [Fluxo por modalidade](#fluxo-por-modalidade)
6. [Artefatos e estados](#artefatos-e-estados)
7. [Validação e compatibilidade](#validação-e-compatibilidade)

## Separação de controles

Tratar `formacao_decisao_colegiada` como terceiro eixo, independente de:

- `estrategia_da_equipe`: como as cadeiras colaboram;
- `ciclo_de_melhoria`: quando surge outra versão;
- `consenso.modo`: se o acordo estável é gate;
- métodos de preferência como Borda, Condorcet ou Delphi.

Uma votação pode escolher uma candidata sem formar decisão colegiada. Uma decisão
colegiada por maioria não é consenso. A modalidade define como votos e fundamentos
se convertem em decisão e como o resultado é publicado.

Ativar esta camada somente quando o usuário pedir decisão colegiada, acórdão,
votos, `seriatim`, `per curiam`, `opinion of the court`, opinião da corte ou
equivalente. Fora desses casos, preservar o fluxo existente.

## Modalidades

### `seriatim`

Cada cadeira produz voto individual completo e identificado. Somar posições no
dispositivo e apurar adesões aos fundamentos separadamente. Exigir `voto_sha256`
de toda cadeira não abstida. Publicar manifestações concorrentes e dissidentes.

Saída mínima:

- certidão ou proclamação do resultado;
- um voto congelado por cadeira;
- placar do dispositivo;
- matriz de adesões às proposições;
- relatório da ratio ou declaração de que ela não é unificada.

Não fabricar fundamento comum pela semelhança textual dos votos.

### `per_curiam`

Produzir uma opinião institucional impessoal, sem atribuição a autor individual.
Separar a forma de publicação da regra de resultado: o texto pode exigir
unanimidade, consenso estrito, maioria simples ou maioria qualificada conforme a
configuração. Maioria continua sendo `decisão por maioria`, não consenso.

Mesmo quando votos separados não forem publicados no corpo principal, preservar
dissensos, autores, razões e hashes no recibo de auditoria. Em contexto brasileiro
que exija publicidade do voto vencido, usar `votos_dissidentes = publicar`.

### `opinion_of_court`

Produzir uma opinião principal aderida pela maioria e permitir manifestações
separadas:

- `concorrente`: concorda com resultado e acrescenta fundamento compatível;
- `concordancia_apenas_resultado`: acompanha o dispositivo por outras razões;
- `dissidente`: rejeita o resultado ou fundamento determinante;
- `abstencao`: não integra votos válidos conforme a base de cálculo confirmada.

A opinião principal pode ter autoria `maioria_nomeada` ou
`relator_da_maioria`. Publicar todo voto não aderente. Esta é a modalidade padrão
quando uma decisão colegiada for pedida sem perfil expresso.

## Configuração

Persistir em runs novos:

```json
{
  "formacao_decisao_colegiada": {
    "contrato": "decisao_colegiada_v1",
    "modalidade": "opinion_of_court",
    "regra_resultado": "maioria_simples",
    "base_calculo": "votos_validos",
    "quorum": 3,
    "limiar_maioria_qualificada": null,
    "adesao_fundamentos": "proposicao",
    "ratio_exigida": true,
    "votos_concorrentes": "publicar",
    "votos_dissidentes": "publicar",
    "publicar_mapa_adesoes": true,
    "proclamacao_congela_votos": true
  }
}
```

Regras de resultado:

- `unanimidade`: todas as cadeiras ativas escolhem o mesmo dispositivo;
- `maioria_simples`: mais da metade da base de cálculo;
- `maioria_qualificada`: limiar confirmado acima de 0,5 e até 1;
- `consenso_estrito`: unanimidade do dispositivo e adesão a todos os fundamentos
  essenciais, além do veredito estável de `$consenso` sobre o mesmo hash;
- `com_decisor`: decisão fundamentada sobre a matéria julgável, sempre rotulada
  `decisão sem consenso` quando não houver acordo estável.

Não usar Borda, Condorcet ou Delphi como substitutos da adesão jurídica aos
fundamentos. Eles podem selecionar uma candidata antes desta etapa.

## Votos, proposições e ratio

Antes da proclamação:

1. congelar o hash do artefato;
2. decompor os fundamentos candidatos em proposições numeradas e imutáveis;
3. colher de cada cadeira o dispositivo e as adesões por proposição ou seção;
4. permitir crítica, réplica e revisão dentro dos limites confirmados;
5. congelar votos e adesões finais;
6. proclamar o resultado e executar o validador determinístico.

Cada proposição registra:

```json
{
  "id": "P1",
  "texto_sha256": "<sha256>",
  "essencial": true
}
```

Cada voto registra, no mínimo, cadeira, opção do dispositivo, tipo, hash do voto
e IDs das proposições acompanhadas.

Reconhecer `ratio_status = unificada` somente quando ao menos uma proposição
essencial obtiver o apoio exigido pela regra de resultado e integrar a opinião
principal. Se houver maioria no dispositivo sem fundamento essencial comum,
registrar `somente_resultado`. Usar `pluralidade` quando não houver uma coalizão
capaz de formar opinião principal. Usar `nao_aplicavel` apenas quando não houver
proposições jurídicas a apurar.

Se `ratio_exigida = true`, `somente_resultado` ou `pluralidade` reprova o gate
colegiado e devolve os fundamentos ao loop. Não elevar fundamento concorrente,
dissidente ou meramente acessório a ratio.

## Fluxo por modalidade

### Seriatim

```text
votos independentes → debate → votos finais → soma do dispositivo
→ matriz dos fundamentos → compilação dos votos → proclamação
```

### Per curiam

```text
proposta institucional → críticas → revisão do texto comum
→ adesão ao hash e às proposições → opinião impessoal → proclamação
```

### Opinion of the Court

```text
posições independentes → coalizão majoritária → minuta da maioria
→ adesão por proposição → concorrências/dissidências → proclamação
```

Uma mudança posterior do artefato, da opinião principal ou de proposição
essencial cria novo hash e invalida votos, placar, ratio, decisão e consenso.

## Artefatos e estados

Usar pacote multi-artefato quando houver votos separados. Cada item continua com
um único canônico próprio; o pacote pode conter:

```text
decisao/principal.md
decisao/certidao.md
decisao/mapa-adesoes.json
votos/<cadeira>.md
recibos/formacao-colegiada.json
```

Estados adicionais:

- `VOTOS_INICIAIS_CONGELADOS`;
- `DELIBERANDO_COLEGIADO`;
- `VOTOS_FINAIS_CONGELADOS`;
- `APURANDO_ADESOES`;
- `DECISAO_COLEGIADA_FORMADA`;
- `SEM_RATIO_UNIFICADA`;
- `DECISAO_COLEGIADA_INVALIDA`.

`DECISAO_COLEGIADA_FORMADA` não equivale a `canonico_aprovado`. O artefato ainda
precisa satisfazer consenso quando exigido, painel, gates de domínio e auditoria.

## Validação e compatibilidade

Validar antes de executar e depois de proclamar:

```text
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/consenso/scripts/collegiate_gate.py" validate-config configuracao-colegiada.json
python3 "${CLAUDE_PLUGIN_ROOT:-$HOME/.codex/skills}/consenso/scripts/collegiate_gate.py" validate-verdict recibo-colegiado.json
```

O gate usa o ledger global `~/.agents/multiagent-state/nonces.json`. Em maioria, unanimidade ou
decisão com terceiro, `gate_colegiado=true` exige arquivo real e um recibo HMAC por voto, ligado à
cadeira, ao hash congelado e à opção votada. Sem essas provas, o resultado permanece
`formation_only`: pode descrever a apuração, mas não efetiva gate forte. Em consenso estrito, as
cadeiras votantes devem coincidir com as do `veredito_consenso` incorporado. Os nonces somente são
consumidos depois que toda a formação colegiada passa, de forma atômica.

Quando `regra_resultado = consenso_estrito` ou o rótulo alegar consenso, incorporar no recibo
colegiado o objeto completo `veredito_consenso` já validado, com recibos assinados e o mesmo hash.
Um booleano declaratório não satisfaz o gate. O recibo de consenso pode referenciar a formação colegiada, mas maioria, unanimidade apenas
no dispositivo ou decisão de terceiro não satisfazem `resultado = consenso`.

Runs antigos sem `formacao_decisao_colegiada` permanecem válidos e não recebem
modalidade por inferência retroativa. Preservar qualquer run já congelado. Em
runs novos, mostrar modalidade, regra de resultado, quórum, adesão aos
fundamentos, exigência de ratio e política de votos separados na prévia.
