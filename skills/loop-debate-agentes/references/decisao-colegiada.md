# Formação de decisão colegiada

## Sumário

1. [Separação de controles](#separação-de-controles)
2. [Modalidades](#modalidades)
3. [Critério deliberativo](#critério-deliberativo)
4. [Configuração](#configuração)
5. [Votos, questões, proposições e ratio](#votos-questões-proposições-e-ratio)
6. [Fluxo por modalidade](#fluxo-por-modalidade)
7. [Artefatos e estados](#artefatos-e-estados)
8. [Validação e compatibilidade](#validação-e-compatibilidade)

## Separação de controles

Tratar `formacao_decisao_colegiada` como terceiro eixo, independente de:

- `estrategia_da_equipe`: como as cadeiras colaboram;
- `ciclo_de_melhoria`: quando surge outra versão;
- `consenso.modo`: se o acordo estável é gate;
- métodos de preferência como Borda, Condorcet ou Delphi.

Uma votação pode escolher uma candidata sem formar decisão colegiada. Uma decisão
colegiada por maioria não é consenso. A modalidade define como votos e fundamentos
se convertem em decisão e como o resultado é publicado.

Dentro da formação colegiada, separar ainda `modalidade` de `metodo_apuracao`.
A modalidade controla a voz pública da decisão; o método controla o objeto votado:
dispositivo integral, questões separadas ou questões seguidas de confirmação. Não
inferir um eixo a partir do outro.

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

## Critério deliberativo

### `global` — *case-by-case*

Cada cadeira escolhe diretamente uma `opcao_dispositivo`. Somar as opções e apurar
adesões às proposições dentro da coalizão vencedora. É o comportamento do contrato
`decisao_colegiada_v1` e permanece o padrão universal e retrocompatível.

Usar quando o usuário pedir voto no resultado final, quando a decomposição lógica
não estiver pré-declarada ou quando o caso não justificar uma máquina de derivação.

### `analitico` — *issue-by-issue*

Cada cadeira responde separadamente às questões congeladas. Apurar cada questão
pela mesma regra e base globais; depois derivar o dispositivo por tabela declarada,
total e não ambígua. Usar `decisao_colegiada_v2`.

As dependências formam uma floresta dirigida de pai único: cada questão possui zero
ou um pai já declarado; uma questão pode governar várias filhas. Auto-laço, pai no
futuro, ciclo, dependência com dois pais e mundo sem uma única regra de derivação
reprovam antes do voto. Enumerar somente mundos alcançáveis e limitar a 4096.

Distinguir:

- `abstencao`: cadeira fora de todas as questões;
- `abstencao_na_questao`: cadeira sem resposta naquela questão;
- `prejudicada`: a guarda da questão não foi satisfeita;
- `nao_alcancada`: questão ativa sem resposta no limiar; falha de formação.

Nunca completar questão não alcançada por pluralidade. `com_decisor` pode resolver
somente a questão não alcançada, com fundamento; não pode escolher diretamente o
dispositivo para contornar a derivação.

Apurar e publicar sempre dois resultados:

- `dispositivo_derivado`: função das respostas colegiadas por questão;
- `dispositivo_por_cadeira`: opção que venceria após derivar o pacote individual de
  cada cadeira.

Se a coalizão de cadeiras que chegaria individualmente ao dispositivo derivado não
atingir o limiar global, marcar `paradoxo_doutrinario = true` e
`ratio_status = somente_resultado` quando existirem proposições apuráveis — ou
`pluralidade` quando um decisor tiver de preencher questão não alcançada. Sem
proposições declaradas, usar `nao_aplicavel`: a ausência de fundamentos nunca pode
ser promovida a uma ratio. `unificada` exige cumulativamente coalizão suficiente no
pacote derivado e apoio dessa coalizão a ao menos uma proposição essencial no
limiar. Não escrever “a maioria decidiu” quando não houver maioria aderente ao
pacote. `ratio_exigida = true` reprova qualquer estado diferente de `unificada`.

### `hibrido`

Executar a mesma apuração analítica e, depois, um segundo ato de confirmação do
dispositivo derivado. A única política desta versão é `bloqueante`: se o limiar de
confirmação não for alcançado, não proclamar nem publicar dispositivo e devolver o
ponto ao loop. Não trocar silenciosamente para votação global, não abrir revisão
dirigida dentro do gate e não reutilizar os votos da primeira fase como confirmação.

Congelar a política de confirmação antes das cédulas. Cada confirmação possui nonce
e recibo próprios ligados ao hash do ato completo: cadeira, `confirma`, eventual
fundamento de divergência, dispositivo derivado e política de confirmação. O
`voto_sha256`, a `saida_sha256` e a `posicao_colegiada` do recibo devem coincidir com
esse hash; `derivado_sha256` continua atestando o dispositivo. Consumir todos os nonces
somente após a formação inteira validar; em falha ou queda entre fases, consumir zero.

## Configuração

Persistir em runs novos:

```json
{
  "formacao_decisao_colegiada": {
    "contrato": "decisao_colegiada_v1",
    "metodo_apuracao": "global",
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

Para votação por questões, usar o contrato v2 e congelar questões e derivação antes
da primeira cédula:

```json
{
  "formacao_decisao_colegiada": {
    "contrato": "decisao_colegiada_v2",
    "metodo_apuracao": "analitico",
    "modalidade": "seriatim",
    "regra_resultado": "maioria_simples",
    "base_calculo": "votos_validos",
    "quorum": 3,
    "questoes": [
      {
        "id": "Q1",
        "texto": "A preliminar deve ser acolhida?",
        "texto_sha256": "<sha256>",
        "dominio": ["sim", "nao"],
        "depende_de": null
      }
    ],
    "regras_derivacao": [
      {"se": {"Q1": "sim"}, "opcao": "extinguir"},
      {"se": {"Q1": "nao"}, "opcao": "prosseguir"}
    ],
    "questoes_sha256": "<sha256-do-pacote-canonico>",
    "derivacao_sha256": "<sha256-da-tabela-compilada>"
  }
}
```

No híbrido, acrescentar `politica_confirmacao = bloqueante` e
`confirmacao_sha256`. Não aceitar `decisao_colegiada_v2` com método `global`, nem
reinterpretar recibo v1 como analítico.

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

## Votos, questões, proposições e ratio

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

No método global, cada voto registra cadeira, opção do dispositivo, tipo, hash do
voto e IDs das proposições acompanhadas. No analítico ou híbrido, a cédula não pode
trazer opção primária: registra respostas por questão, `respostas_sha256`, hash da
cédula e adesões às proposições textuais.

Reconhecer `ratio_status = unificada` somente quando ao menos uma proposição
essencial obtiver o apoio exigido pela regra de resultado e integrar a opinião
principal. Se houver maioria no dispositivo sem fundamento essencial comum,
registrar `somente_resultado`. Usar `pluralidade` quando não houver uma coalizão
capaz de formar opinião principal. Usar `nao_aplicavel` apenas quando não houver
proposições jurídicas a apurar.

Se `ratio_exigida = true`, `somente_resultado` ou `pluralidade` reprova o gate
colegiado e devolve os fundamentos ao loop. Não elevar fundamento concorrente,
dissidente ou meramente acessório a ratio.

No v2, proposições e questões não são sinônimos. Questões formam o dispositivo;
proposições expressam adesão ao texto da opinião. O campo `essencial` permanece nas
proposições e não existe nas questões do MVP. Calcular a ratio pelo apoio ao pacote
derivado; não por “pivotalidade” isolada, que falha em fundamentos independentes ou
sobre-determinados.

## Fluxo por modalidade

### Seriatim

```text
votos independentes → debate → votos finais → soma do dispositivo
→ matriz dos fundamentos → compilação dos votos → proclamação
```

### Critério global

```text
votos no dispositivo → placar global → coalizão vencedora
→ adesões às proposições → ratio e opiniões separadas
```

### Critério analítico ou híbrido

```text
questões e regras congeladas → cédulas por questão → apuração de cada questão
→ derivação colegiada + derivações individuais → teste de maiorias cruzadas
→ confirmação bloqueante, se híbrido → ratio e publicação por modalidade
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
decisao/questoes.json
decisao/derivacao.json
decisao/mapa-questoes.json
votos/<cadeira>.md
recibos/formacao-colegiada.json
```

Estados adicionais:

- `VOTOS_INICIAIS_CONGELADOS`;
- `DELIBERANDO_COLEGIADO`;
- `VOTOS_FINAIS_CONGELADOS`;
- `APURANDO_ADESOES`;
- `DECISAO_COLEGIADA_FORMADA`;
- `DISPOSITIVO_DERIVADO`;
- `AGUARDANDO_CONFIRMACAO`;
- `CONFIRMACAO_REJEITADA`;
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

No v2, o recibo da cédula deve ligar `posicao_colegiada` ao hash do vetor de
respostas, conter `questoes_sha256` e `derivacao_sha256` e usar `entrada_sha256`
para o pacote congelado. No híbrido, o segundo recibo liga `posicao_colegiada` ao
hash canônico do ato de confirmação, inclusive o booleano e eventual fundamento,
além de `derivado_sha256` e `confirmacao_sha256`. Trocar o voto, texto, questões,
tabela ou política invalida todos os atos do hash anterior.

Quando `regra_resultado = consenso_estrito` ou o rótulo alegar consenso, incorporar no recibo
colegiado o objeto completo `veredito_consenso` já validado, com recibos assinados e o mesmo hash.
Um booleano declaratório não satisfaz o gate. O recibo de consenso pode referenciar a formação colegiada, mas maioria, unanimidade apenas
no dispositivo ou decisão de terceiro não satisfazem `resultado = consenso`.

Runs antigos sem `formacao_decisao_colegiada` permanecem válidos e não recebem
modalidade por inferência retroativa. Preservar qualquer run já congelado. Em
runs novos, mostrar modalidade, regra de resultado, quórum, adesão aos
fundamentos, exigência de ratio e política de votos separados na prévia. Ausência
de `metodo_apuracao` significa `global`; nunca promover automaticamente um run
legado ou um pedido genérico de acórdão para o modo analítico.
