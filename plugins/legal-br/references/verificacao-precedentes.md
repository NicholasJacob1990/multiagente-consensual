# Verificação de precedentes em fonte primária

O erro que mais aparece em revisão de parecer não é de tese — é de **dado do
precedente**: relator trocado, turma errada, data da notícia no lugar da data do
julgamento, DJe confundido com julgamento. Cada um desses desmoraliza o parecer
inteiro perante quem confere.

> **Regra do plugin:** nenhum precedente entra no parecer com relator, órgão
> julgador ou data que você não tenha lido **na página do tribunal**. Nem do
> conhecimento do modelo, nem de agregador (JusBrasil, blogs), nem de notícia
> institucional. Se não conseguir confirmar, diga isso ao usuário em vez de
> completar a citação.

## Ordem de prioridade

1. **SCON/STJ e portal do STF** (abaixo) — devolvem relator, turma, data de
   julgamento, DJe/DJEN e a ementa inteira.
2. **brlaw MCP** (`StjLegalPrecedentsRequest`, `StfLegalPrecedentsRequest`,
   `TstLegalPrecedentsRequest`) — bom para *descobrir* precedente por tema, mas
   instável (fica fora do ar por períodos longos). Não conte com ele para fechar
   uma citação.
3. **Firecrawl / WebSearch** — para achar o número do processo e a notícia; nunca
   para extrair relator e data.

## STJ — Cloudflare, e por que CapSolver não resolve

`scon.stj.jus.br` e `processo.stj.jus.br` respondem **403** com
`cf-mitigated: challenge` e `server: cloudflare`. É **Managed Challenge**: não
existe captcha a resolver, então resolvedor de captcha (CapSolver, 2Captcha) não
tem o que enviar. Falham todos: `curl` com User-Agent completo, WebFetch,
firecrawl inclusive com `proxy: stealth`.

**O que funciona: abrir num navegador real** (ferramentas
`mcp__claude-in-chrome__*`). O desafio passa sozinho em ~6 s. O sinal de que
passou é o `title` da aba mudar de `Just a moment...` para o título do site;
então `get_page_text` devolve a página inteira.

Query do SCON por classe e número:

```
https://scon.stj.jus.br/SCON/pesquisar.jsp?b=ACOR&livre=((CLASSE.clas.)+e+@num%3D%22NUMERO%22)+ou+(CLASSE+adj+%22NUMERO%22).suce.&O=JT
```

- `CLASSE`: `RESP`, `ARESP`, `AIRESP` (AgInt no REsp), `AIARESP` (AgInt no AREsp),
  `EDCL`, `HC`, `RMS`
- `NUMERO`: só dígitos, sem pontos — `2165917`, não `2.165.917`
- `.suce.` alcança os recursos sucessivos (o AgInt sobre aquele REsp)
- `b=ACOR` acórdãos; `b=DTXT` decisões monocráticas; `b=SUMU` súmulas. A página
  mostra a contagem em cada base, então dá para ver de imediato onde o processo está.

**Armadilha:** `processo.stj.jus.br/processo/pesquisa/?termo=...` renderiza
**"Sistema indisponível"** mesmo depois de vencido o Cloudflare — o parâmetro
`termo` está morto. Use o SCON.

## STF — só exige User-Agent

Sem WAF nesses endpoints; sem `-A` dá 403, com `-A` funciona:

```bash
UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 \
(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"

# 1) classe + número -> devolve o "incidente" (siga o redirect com -L)
curl -sL -A "$UA" "https://portal.stf.jus.br/processos/listarProcessos.asp?classe=ARE&numeroProcesso=1493517" \
  | grep -o 'incidente=[0-9]*' | sort -u

# 2) com o incidente, as abas:
curl -sL -A "$UA" "https://portal.stf.jus.br/processos/abaInformacoes.asp?incidente=NNNN"  # assunto, origem
curl -sL -A "$UA" "https://portal.stf.jus.br/processos/abaDecisoes.asp?incidente=NNNN"     # relator, órgão, sessão
curl -sL -A "$UA" "https://portal.stf.jus.br/processos/abaAndamentos.asp?incidente=NNNN"   # publicação do acórdão no DJe
```

`jurisprudencia.stf.jus.br/api/search` não responde a POST anônimo — não perca
tempo com ela.

## O que copiar para a referência

Formato completo: **classe, número/UF, relator, órgão julgador, data de
julgamento e data de publicação com a fonte** (DJe ou DJEN — são coisas
diferentes e o STJ passou a usar DJEN).

> BRASIL. Superior Tribunal de Justiça. AgInt no REsp nº 2.165.917/MG. Relatora:
> Min. Nancy Andrighi. Terceira Turma, julgado em 24 de março de 2025, DJEN de
> 27 de março de 2025.

Erros concretos já cometidos e corrigidos por conferência:

| Erro | Causa |
|---|---|
| data de julgamento errada em 2 dias | usei a data da **notícia institucional** |
| "3ª Turma" onde era 4ª | inferência a partir do relator |
| relator ausente na referência | citação copiada de agregador |

## Leia a ementa, não só a citação

Confirmar relator e data é metade do trabalho. Ao abrir o acórdão, **leia a
ementa inteira**: com frequência ela contém argumento melhor do que o motivo
pelo qual você foi buscá-lo — inclusive precedente envolvendo a própria parte do
caso, ou aplicação da tese em situação mais próxima da sua do que a do
precedente-líder. Registre isso no parecer; é o tipo de achado que muda a força
da fundamentação.
