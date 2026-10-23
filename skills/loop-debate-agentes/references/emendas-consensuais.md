# Modo `emendas_consensuais_v2`

Os agentes leem a minuta do redator, debatem e devolvem **só as melhorias em que concordam**. O modo é para minutas já maduras: a pergunta deixa de ser "qual a nota?" e passa a ser "que trechos, exatamente, todos subscreveriam mudar, com que redação e com que classificação?". O redator não reescreve o texto, e a minuta só muda pelas emendas que atingiram a regra de aprovação e pela adesão ao conjunto.

O modo serve a qualquer artefato, e no domínio jurídico a qualquer trabalho: parecer, petição, contestação, recurso, minuta de decisão, voto, contrato. O tipo de documento só muda o conjunto de classificações (ver a tabela abaixo) e o perfil de forma usado na pré-auditoria.

## Contrato v2 e compatibilidade

O v2 exige justificativa estruturada, suporte de toda alteração material e revalidação das variantes. Recibos v1 precisam ser revalidados e novamente votados; runs congelados podem continuar na cópia antiga preservada, sem migração silenciosa.

A justificativa é um objeto com quatro campos textuais não vazios: `defeito`, `suporte`, `consequencia`, `insuficiencia_aplicacao_direta`. Texto livre como “porque sim” não satisfaz a estrutura. A suficiência jurídica desses elementos continua sendo examinada pelos revisores.

A materialidade independe de `tipo`: `precisao`, `acrescimo`, `corte`, `remissao` ou `redacao` não dispensam suporte quando a classificação for material. O suporte pode ser norma, documento, prova ou instrução recebida. `minuta_atual` comprova uma contradição interna pela própria base; uma fonte externa exige corpus recebido e passagem localizada. Presença literal não prova pertinência nem verdade.

O contexto conserva a minuta e o hash do corpus. Na apuração, uma variante com suporte alterado exige `--fontes` com o mesmo corpus validado; novas fontes exigem novo pacote compartilhado e nova validação. Os requisitos são conferidos novamente sobre a variante final, incluindo classificação, justificativa e efeitos reservados. Redações e metadados diferentes não são somados como se fossem a mesma variante.

Em todo tipo de trabalho, declarar `efeitos_reservados`: `renuncia_direito`, `concessao_negocial`, `reconhecimento_fato`, `mudanca_estrategia`, `acordo` ou `ato_externo`. Esses efeitos dependem de `--autorizadas`, independentemente da classificação. Sinais explícitos novos de renúncia, confissão e transação também criam uma reserva conservadora; a detecção lexical não substitui a revisão jurídica nem cobre todo efeito possível. A autorização pode provir de instrução já concedida pelo usuário, nunca da concordância dos modelos.

`confirmar` exige `--apuracao`, além das mesmas `--autorizadas` e `--excluir` utilizadas na aplicação. O resultado é reconstituído antes da adesão: não se aprova texto acrescentado fora das emendas aprovadas e autorizadas.

Documentos mistos, com narrativa e pedidos/listas numerados, recebem IDs globais de bloco. A numeração escrita é preservada; esses IDs não são tratados como números de parágrafo exibidos para conferir remissões.

O modo é uma estratégia do motor, como o `ensemble_nxn_v1`. Não cria outro loop, outro canônico nem outra auditoria; cada rodada de emendas produz uma nova versão completa e conta no limite de versões do artefato.

## Quando usar

Ativar quando o usuário pedir "emendas consensuais", "só as melhorias em que concordam", "o que os agentes aceitariam mudar", "rodada de emendas" ou equivalente, ou quando o texto já tiver passado do ponto em que reescritas inteiras ajudam: auditorias acima de 9, ajustes finos de redação, fontes ou remissões. Não usar para a primeira redação, para reestruturar o documento ou para decidir uma tese controvertida; nesses casos, o ciclo principal ou o ensemble são os instrumentos certos. Não devolver versões integrais concorrentes quando o pedido for revisar uma minuta comum.

## Configuração persistida

```json
{
  "estrategia_da_equipe": {
    "tipo": "emendas_consensuais",
    "contrato": "emendas_consensuais_v2",
    "tipo_documento": "parecer | peca | decisao | generico",
    "proponentes": ["gemini", "codex", "claude"],
    "votantes": ["gemini", "codex", "claude"],
    "regra": "unanimidade",
    "max_emendas_por_cadeira": 15,
    "rodada_de_debate": 1,
    "adesao_ao_conjunto": true,
    "exigir_fonte_literal_para": ["correcao", "fonte"],
    "max_palavras_por_paragrafo": null,
    "trechos_travados": "travados.json",
    "registro_achados": "achados.json",
    "auditoria_final": {"familia_diferente_dos_votantes": true, "pacote_com_hash": true}
  }
}
```

- `regra`: `unanimidade` (padrão), `maioria` ou `qualificada:p/q`. Mudar a regra é decisão do usuário, registrada na prévia.
- `votantes` é o quórum. Cadeira exigida que não respondeu, respondeu sobre outra versão, mandou saída vazia ou estourou o tempo conta como **abstenção**, nunca como adesão. Não substituir cadeira nem reduzir a equipe fora da política já autorizada.
- Proponentes e votantes podem coincidir. A cédula esconde a autoria.
- `trechos_travados` lista o que nenhuma emenda pode tocar: texto ditado pelo usuário, conclusões que ele aprovou, fecho e assinatura.

## Classificações por tipo de documento

Votar `aceitar` é aderir ao diagnóstico, à redação exata e à classificação. Concordar só com o diagnóstico não basta.

| `tipo_documento` | Classificações |
|---|---|
| `parecer` | `correcao_necessaria`, `obrigacao_incidente`, `recomendacao_facultativa`, `providencia_externa`, `redacional` |
| `peca` (petição, contestação, recurso, memorial) | `correcao_necessaria`, `reforco_argumentativo`, `risco_estrategico`, `providencia_externa`, `redacional` |
| `decisao` (sentença, voto, acórdão, decisão administrativa) | `correcao_necessaria`, `aperfeicoamento_fundamentacao`, `recomendacao_facultativa`, `providencia_externa`, `redacional` |
| `generico` | `correcao_necessaria`, `aperfeicoamento_material`, `recomendacao_facultativa`, `providencia_externa`, `redacional` |

- `correcao_necessaria` exige `justificativa_obrigatoriedade`, composta por quatro elementos:
  - o defeito concreto;
  - a norma, o precedente ou a contradição que o demonstra;
  - o efeito sobre validade, admissibilidade, eficácia ou congruência;
  - por que a aplicação direta da norma não resolve.

  Os nomes dos quatro campos são os definidos no contrato v2 acima. Sem isso, a emenda é inválida. O grau de exigência do corpo do texto deve ser o mesmo da conclusão, dos pedidos ou do dispositivo.
- `redacional` não conta como melhoria material. Se só restarem emendas redacionais, o resultado é **"sem novas melhorias materiais consensuais"**, um resultado válido: com os portões fechados, a revisão encerra sem nova versão de mérito.

## Fluxo

As fases são sequenciais. Cada uma grava seu JSON no diretório do run, e `scripts/emendas.py` recusa material de outra versão (hash divergente).

1. **Congelar e pré-auditar.**
   - Gravar a minuta na sua vista atual (num DOCX com revisões, o texto com as alterações aceitas, guardando o histórico só para comparação).
   - Calcular o SHA-256 e rodar a pré-auditoria determinística do domínio (no jurídico, `pre_auditoria_parecer.py`).
   - Achado bloqueante mecânico é corrigido antes, pelo redator.
2. **Propostas cegas.**
   - Cada proponente recebe, em diretório próprio, a minuta, as fontes e o hash. Cegueira, aqui, significa não receber críticas, notas e vereditos anteriores; não significa ficar sem a minuta ou sem as fontes.
   - Cada um devolve um lote no contrato `lote_propostas` de `scripts/emendas_schema.json`. Por emenda:
     - parágrafo e trecho literal único;
     - redação substitutiva exata;
     - tipo e classificação;
     - fundamento, com referência específica (documento e/ou ID SEI ou folha dos autos, versão e dispositivo) e trecho literal da fonte;
     - nível de acesso à fonte;
     - dependências e impacto.
3. **Validação mecânica** (`emendas.py validar --tipo-documento …`). A validação recusa:
   - lotes sobre outro hash;
   - trecho inexistente, ambíguo, que atravesse parágrafos, toque trecho travado ou indique parágrafo errado;
   - classificação fora do conjunto do tipo;
   - correção necessária sem justificativa;
   - dependência em parágrafo inexistente;
   - emenda de mérito sem fonte literal, com fonte literal não localizada ou com fonte de nível `remissao` ou `ausente_no_dossie`. Esses níveis não sustentam a emenda, mas também não provam que o dispositivo foi inventado.

   Além disso, a validação junta emendas idênticas e agrupa as que disputam o mesmo trecho. O excesso de palavras de uma emenda isolada vira alerta, porque outra emenda do mesmo parágrafo pode compensá-lo.
4. **Voto cruzado cego** (`emendas.py cedula`). Cada votante responde no contrato `lote_votos`:
   - `aceitar`;
   - `ajustar`, com redação e/ou classificação alternativa;
   - `rejeitar`.

   O voto vem sempre com motivo. Manifestação genérica ("concordo com as críticas") não é voto.
5. **Apuração** (`emendas.py apurar --votantes …`). Cada variante, isto é, texto mais classificação, precisa atingir a regra sozinha. Quem aceitou a redação original não aderiu ao ajuste. A apuração produz uma destas decisões:
   - `aprovada`;
   - `aprovada_com_ajuste`;
   - `segunda_rodada`: há apoio, mas dividido entre variantes;
   - `dissenso`: há apoio, mas a regra não fecha;
   - `rejeitada`: ninguém apoia;
   - `preterida`: perdeu o grupo de conflito para outra emenda aprovada.
6. **Rodada única de debate** (`emendas.py segunda-rodada`).
   - As emendas em `segunda_rodada` e em `dissenso` voltam como variantes concorrentes, com os motivos da rodada anterior sem autoria.
   - Vota-se só aceitar ou rejeitar.
   - Mudar a posição anterior exige `razao_nova`, isto é, o argumento ou a fonte que convenceu. Sem ela, o voto conta como abstenção.
   - O que não fechar vai ao humano. Não há terceira rodada.
   - Depois do debate, as manifestações já não são independentes entre si. Por isso a auditoria final tem sessão própria.
7. **Aplicação** (`emendas.py aplicar`). O script aplica as aprovadas sobre a minuta congelada e recusa o resultado nestes casos:
   - emendas sobrepostas;
   - dependência não atendida (a emenda exige ajuste num parágrafo que nenhuma emenda aprovada tocou);
   - parágrafo acima do limite.

   Grava a candidata e o relatório.
8. **Adesão ao conjunto** (`emendas.py conjunto` e `emendas.py confirmar`).
   - Alterações aceitáveis isoladamente podem se contradizer quando combinadas, mudar o alcance de outro parágrafo ou deixar a conclusão, o pedido, o dispositivo ou uma remissão incompatíveis.
   - Cada votante recebe a lista de alterações aplicadas e responde `aceito` ou `conflito`, indicando as emendas envolvidas.
   - Só com adesão pela regra e sem conflito a candidata substitui a base.
   - Havendo conflito, reaplicar com `--excluir` as emendas envolvidas, se o conjunto sem elas fizer sentido, e levar o conflito ao humano. Ou levar a harmonização ao ciclo principal.
9. **Pós-checagem.**
   - Rodar a pré-auditoria na versão nova com `--anterior`. Ela acusa remissões quebradas, palavras de alcance acrescentadas ou retiradas ("até", "sempre", "somente", "deverá"), ressalvas que sumiram e frases da versão anterior sem correspondente.
   - Gerar o redline contra a versão de entrada e conferi-lo nos dois sentidos.
   - Atualizar o registro de achados.
10. **Auditoria cega final.**
    - Enviar a versão nova, em pacote travado por hash, a um auditor de família diferente da dos votantes, sem o histórico deliberativo.
    - A aprovação do conjunto de emendas não se transfere ao arquivo final: ele passa pelos gates do contrato vigente.
    - Se o auditor reprovar, o achado volta como proposta na rodada seguinte, não como reescrita direta.

## Registro cumulativo de achados

`scripts/achados.py` mantém, entre rodadas e auditorias, o estado de cada achado (`aberto`, `parcial`, `resolvido`, `rejeitado`, `superado`), com hash, autor e razão de cada mudança.

- **Reabertura:** achado já fechado só reabre com motivo `regressao`, `fonte_nova` ou `falha_identificada`, explicado. A mesma crítica repetida é registrada como reabertura recusada.
- **Verificação contra o texto:** `achados.py verificar` confronta os estados com o texto atual. Acusa achado resolvido cujo trecho voltou e achado aberto cujo trecho já não existe.
- **Encerramento:** `achados.py resumo` diz se ainda há achado **material** aberto. Preferência editorial (`"material": false`) fica no relatório e não impede o encerramento.

Antes de propor, o revisor confere a solução no arquivo atual. Não exigir novidade de toda auditoria.

## Entrega

Entregar ao usuário, nesta ordem:

1. **Dissenso e objeções materiais sem consenso:** proposta, variantes e votos de cada cadeira. A falta de consenso não torna falso o achado de uma única cadeira, e um bloqueio material aberto impede declarar o documento aprovado.
2. **Alterações aplicadas:** lista curta com trecho atual, redação acordada, classificação e razão, mais o resultado da adesão ao conjunto e o redline.
3. **Pós-checagem e auditoria final:** os resultados de ambas.

Divergências apenas editoriais ficam no relatório detalhado. Não apresentar emendas rejeitadas ou inválidas como sugestões pendentes.

## Garantias e limites

- **Garantia de procedimento:** o script não julga mérito. Só entra texto que as cadeiras exigidas viram literalmente e aprovaram, pela regra, sobre a mesma versão, com a mesma classificação e no mesmo conjunto.
- **Fonte:** consenso entre modelos não prova fato, fonte ou intenção. A exigência de fonte literal localizada é a barreira contra fundamento inventado. Mudança puramente `redacional` pode dispensá-la; alteração material exige suporte independentemente do tipo.
- **Voto do proponente:** quem propõe pode votar na própria emenda. Na unanimidade, isso não basta para aprová-la. Na `maioria`, preferir ao menos três votantes.
- **Alcance local:** emendas são locais. Mudança que exige mexer em vários parágrafos coordenados (renumeração, deslocamento de seção, nova tese) sai do modo e volta ao ciclo principal. Dependências declaradas cobrem o caso intermediário: um reparo que exige acompanhar a conclusão ou o pedido.
- **Instruções do usuário:** limites editoriais e auditores escolhidos seguem as instruções atuais do usuário. A skill não restaura um limite que ele afastou, e um documento anexado também não.
