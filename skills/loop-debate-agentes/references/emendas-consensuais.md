# Modo `emendas_consensuais_v1`

Os agentes leem a minuta do redator, debatem às cegas e devolvem **só as melhorias em que concordam**. O modo é para minutas já maduras: a pergunta deixa de ser "qual a nota?" e passa a ser "que trechos, exatamente, todos subscreveriam mudar?". O redator não reescreve o texto, e a minuta só muda pelas emendas que atingiram a regra de aprovação.

O modo é uma estratégia do motor, como o `ensemble_nxn_v1`. Não cria outro loop, outro canônico nem outra auditoria; cada rodada de emendas produz uma nova versão completa e conta no limite de versões do artefato.

## Quando usar

Ativar quando o usuário pedir "emendas consensuais", "só as melhorias em que concordam", "o que os agentes aceitariam mudar", "rodada de emendas" ou equivalente, ou quando o texto já tiver passado do ponto em que reescritas inteiras ajudam: auditorias acima de 9, ajustes finos de redação, fontes ou remissões. Não usar para a primeira redação, para reestruturar o documento ou para decidir uma tese controvertida; nesses casos, o ciclo principal ou o ensemble são os instrumentos certos.

## Configuração persistida

```json
{
  "estrategia_da_equipe": {
    "tipo": "emendas_consensuais",
    "contrato": "emendas_consensuais_v1",
    "proponentes": ["gemini", "codex", "claude"],
    "votantes": ["gemini", "codex", "claude"],
    "regra": "unanimidade",
    "max_emendas_por_cadeira": 15,
    "rodada_de_ajuste": 1,
    "exigir_fonte_literal_para": ["correcao", "fonte"],
    "max_palavras_por_paragrafo": null,
    "trechos_travados": "travados.json",
    "auditoria_final": {"familia_diferente_dos_votantes": true, "pacote_com_hash": true}
  }
}
```

- `regra`: `unanimidade` (padrão), `maioria` ou `qualificada:p/q`. Mudar a regra é decisão do usuário, registrada na prévia.
- Proponentes e votantes podem coincidir. A cédula esconde a autoria, de modo que ninguém vota sabendo de quem é a emenda.
- `trechos_travados` lista o que nenhuma emenda pode tocar: texto ditado pelo usuário, conclusões que ele aprovou, fecho e assinatura. Uma emenda sobre trecho travado é inválida antes do voto.

## Fluxo

As fases são sequenciais; cada uma grava seu JSON no diretório do run, e o script `scripts/emendas.py` recusa material de outra versão (hash divergente).

1. **Congelar e pré-auditar.** Gravar a minuta, calcular o SHA-256 e rodar a pré-auditoria determinística do domínio (no jurídico, `pre_auditoria_parecer.py`). Achado bloqueante mecânico é corrigido antes, pelo redator, sem gastar cadeiras com ele.
2. **Propostas cegas.** Cada proponente recebe, em diretório próprio, a minuta, as fontes e o hash, e devolve um lote no contrato `lote_propostas` de `scripts/emendas_schema.json`: para cada emenda, parágrafo, trecho literal e único, proposta, tipo, fundamento, referência e trecho literal da fonte, e impacto. Instrução fixa: propor só o que melhora com segurança; nada de reescrever parágrafos inteiros quando uma expressão basta; no máximo 15 emendas, em ordem de importância.
3. **Validação mecânica** (`emendas.py validar`). Ela:
   - recusa lotes sobre outro hash e emendas cujo trecho não existe ou é ambíguo, atravessa parágrafos, toca trecho travado ou indica parágrafo errado;
   - recusa emendas de mérito sem fonte literal ou com fonte literal que não está nas fontes fornecidas;
   - junta emendas idênticas de autores diferentes;
   - agrupa as que disputam o mesmo trecho em grupos de conflito.

   O excesso de palavras de uma emenda isolada vira alerta, porque outra emenda do mesmo parágrafo pode compensá-lo.
4. **Voto cruzado cego** (`emendas.py cedula`). Cada votante recebe a minuta integral e a cédula, sem autoria, e responde no contrato `lote_votos`: `aceitar`, `ajustar` (com a redação alternativa completa do trecho) ou `rejeitar`, sempre com motivo. Votante que não repete o hash tem o lote recusado. Ausência de voto conta como abstenção e, na unanimidade, impede a aprovação.
5. **Apuração** (`emendas.py apurar`). Cada texto precisa atingir a regra por si: quem aceitou a redação original não aderiu ao ajuste. A apuração produz uma destas decisões:
   - `aprovada`;
   - `aprovada_com_ajuste`, quando o mesmo ajuste atinge a regra;
   - `segunda_rodada`, quando o apoio se divide entre a original e ajustes;
   - `dissenso`, quando há apoio mas a regra não fecha;
   - `rejeitada`, quando ninguém apoia;
   - `preterida`, quando a emenda perdeu o grupo de conflito para outra aprovada.
6. **Rodada única de ajuste** (`emendas.py segunda-rodada`). As emendas em `segunda_rodada` viram variantes concorrentes, votadas só com aceitar ou rejeitar. O que não fechar vai ao humano. Não há terceira rodada.
7. **Aplicação** (`emendas.py aplicar`). O script aplica as emendas aprovadas da primeira e da segunda rodada sobre a minuta congelada e confere o limite de palavras no texto final; se algum parágrafo exceder o limite, a aplicação é recusada. Grava a nova versão e o relatório com cinco listas: aplicadas, dissenso para decisão humana, preteridas, rejeitadas e inválidas, com votos e motivos.
8. **Pós-checagem.** Rodar de novo a pré-auditoria na versão nova, com `--anterior` (varre parágrafos alterados e remissões após renumeração), gerar o redline contra a versão de entrada e conferi-lo nos dois sentidos.
9. **Auditoria cega final.** Enviar a versão nova, em pacote travado por hash, a um auditor de família diferente da dos votantes. Se o auditor reprovar, o achado volta como proposta na rodada seguinte, não como reescrita direta.

## Entrega

Entregar ao usuário, nesta ordem:

1. a lista de **dissenso**, com a proposta, as variantes e os votos de cada cadeira, porque é ali que estão as decisões dele;
2. o número de emendas aplicadas e o redline;
3. o resultado da pós-checagem e da auditoria final.

Não apresentar emendas rejeitadas ou inválidas como sugestões pendentes. O relatório as preserva para rastreabilidade, não para nova decisão.

## Garantias e limites

- O script não julga mérito. A garantia é de procedimento: só entra texto que todos os votantes viram literalmente e aprovaram pela regra, sobre a mesma versão.
- Consenso entre modelos não prova fato, fonte ou intenção. A exigência de fonte literal localizada nas fontes é a barreira contra fundamento inventado; nos tipos `redacao`, `corte` e `remissao`, ela é dispensada por padrão.
- Proponente que também vota pode aprovar a própria emenda; com unanimidade, isso não basta. Com `maioria`, preferir pelo menos três votantes.
- Emendas são locais. Mudança que exige mexer em vários parágrafos coordenados (renumeração, deslocamento de seção, nova tese) sai do modo e volta ao ciclo principal.
