# Fontes Web: Firecrawl Local + JusBrasil autenticado

Protocolo das fontes web do plugin **legal-br**. Usado pela skill
`pesquisa-juridica` (e disponível ao agente `analista-juridico`) para busca/scraping
na web e para jurisprudência/doutrina via conta **JusBrasil** do usuário.

> **Preflight obrigatório** antes de usar qualquer fonte web:
> ```bash
> python3 "${CLAUDE_PLUGIN_ROOT}/scripts/fontes_externas.py" check
> ```
> Leia o JSON (stdout) e gate o uso conforme `firecrawl.usar`, `jusbrasil.pronto` e `guia`.

## 1. Firecrawl LOCAL (busca/scrape geral)

Instância self-hosted em `http://localhost:3002` (key `local-firecrawl-key`). É a
ferramenta de busca web preferida — a conta **cloud** (`api.firecrawl.dev`) está
**sem créditos**, então NÃO use cloud.

**Regra de degradação (gated):**
- `firecrawl.local_up == true` → use firecrawl local.
- `firecrawl.local_up == false` → **não** caia para cloud; use o **WebSearch nativo**
  do Claude e avise o usuário que o firecrawl local está offline.

**Subir o firecrawl local** (precisa do Docker rodando):
```bash
cd ~/Aplicativos/firecrawl && docker compose up -d   # api:3002 + playwright + redis + rabbitmq
```

**Comandos (apontando para o local):**
```bash
# Busca (web)
firecrawl search "site:stj.jus.br TEMA jurisprudencia ementa" \
  --api-url http://localhost:3002 -k local-firecrawl-key --limit 5

# Scrape de uma URL (markdown)
firecrawl scrape "URL" --api-url http://localhost:3002 -k local-firecrawl-key \
  --format markdown
```
Equivalente via alias do usuário: `fc-local search "..."` / `fc-local scrape "..."`.

## 2. JusBrasil autenticado (cookie-first + Playwright fallback)

A conta JusBrasil (Premium, login Gmail OAuth) dá acesso a jurisprudência, íntegras,
doutrina e peças. O acesso é **baseado em cookies** de duas formas complementares:
- **Playwright `storageState`** (`~/.jusbrasil/storage_state.json`) — cookies+localStorage
  da sessão logada; trata Cloudflare e tem **rate-limit anti-ban** (`JB_*` no `.env`).
- **Profile firecrawl `jusbrasil`** — cookies persistidos num contexto de browser real
  (usado por `firecrawl scrape --profile jusbrasil`).

Script: `~/Aplicativos/a2a-gemini/scripts/jusbrasil_search.py`
(override com env `JUSBRASIL_SCRIPT`). Sempre rodado via `uv` (Playwright).

> ⚠️ **Proteja a conta:** respeite o rate-limit embutido (`JB_DELAY_SECONDS`,
> `JB_REQUESTS_PER_DAY_MAX`). Não paralelize chamadas ao JusBrasil. Uso = pesquisa
> jurídica pessoal autenticada.

### Setup (uma vez) — escolha um caminho

**A. Cookie-first (recomendado)** — exporte os cookies do JusBrasil já logado no seu
browser (extensão "Get cookies.txt"/Netscape) e converta para o storageState:
```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/jusbrasil_cookies_to_storage.py" \
  --cookies "~/Downloads/www.jusbrasil.com.br_cookies.txt"
# gera ~/.jusbrasil/storage_state.json ; reexporte+rode de novo quando expirar
# (cf_clearance/__cf_bm duram pouco; o cookie 'user' dura mais)
```

**B. Login OAuth (alternativa)** — login interativo via Playwright:
```bash
cd ~/Aplicativos/a2a-gemini && uv run --with playwright python scripts/jusbrasil_setup.py
```

**(Opcional) Profile firecrawl p/ íntegra cookie-first** — precisa do firecrawl local up:
```bash
firecrawl interact "https://www.jusbrasil.com.br" --profile jusbrasil   # logar no browser
```

### Busca de jurisprudência (lista de decisões)
Motor autenticado = Playwright + storageState (não é o `firecrawl search`):
```bash
cd ~/Aplicativos/a2a-gemini && uv run --with playwright python scripts/jusbrasil_search.py \
  --query "TEMA juridico" [--tribunal stj|stf|trf-1|...] [--pages 2]
# saída: JSON por decisão (tribunal, relator, data, ementa) em .firecrawl/jusbrasil/
```

### Íntegra de um acórdão (URL) — cookie-first → Playwright fallback
```bash
# 1) Cookie-first: profile firecrawl (precisa firecrawl local up + profile autenticado)
cd ~/Aplicativos/a2a-gemini && uv run --with playwright python scripts/jusbrasil_search.py \
  --url "https://www.jusbrasil.com.br/jurisprudencia/..." --firecrawl --fc-profile jusbrasil

# 2) Fallback: Playwright + storageState (trata Cloudflare)
cd ~/Aplicativos/a2a-gemini && uv run --with playwright python scripts/jusbrasil_search.py \
  --url "https://www.jusbrasil.com.br/jurisprudencia/..."
```
Se a saída disser "Sessão expirada", refaça o `jusbrasil_setup.py`.

## 3. Receitas por tribunal (sites oficiais)

URLs verificadas (jun/2026). Dois modos: **(S) search com `site:`** = robusto, não
depende de formulário; **(D) scrape direto** de URL/portal; **(I) interact** =
necessário quando a busca é SPA (JS) ou formulário POST. Prefixo firecrawl local
omitido por brevidade — sempre acrescente `--api-url http://localhost:3002 -k local-firecrawl-key`.

### STJ — `processo.stj.jus.br/SCON` / `scon.stj.jus.br`
- (S) `firecrawl search "TERMO ementa site:stj.jus.br" --sources web --scrape --limit 5`
- (D) Jurisprudência em Teses: `firecrawl scrape "https://scon.stj.jus.br/SCON/jt/jt.jsp" --format markdown`
- (D) Pesquisa Pronta (temas prontos): `https://processo.stj.jus.br/SCON/pesquisa_pronta/listaPP.jsp`
- (I) Busca livre no SCON (`https://processo.stj.jus.br/SCON/`) usa formulário — `firecrawl interact` para preencher ementa/operadores e paginar.

### STF — `jurisprudencia.stf.jus.br` (SPA) / `portal.stf.jus.br/jurisprudencia`
- (S) `firecrawl search "TERMO repercussão geral site:stf.jus.br" --sources web --scrape --limit 5`
- (I) `https://jurisprudencia.stf.jus.br/` é **SPA JS** — `firecrawl interact` (ou `scrape --wait-for 6000`) para a busca; campos por tese/legislação/relator.
- (D) Portal/serviços: `https://portal.stf.jus.br/jurisprudencia/`

### TST — `tst.jus.br/jurisprudencia` / BANJUR-FALCÃO `jurisprudencia.jt.jus.br`
- (S) `firecrawl search "TERMO súmula OJ site:tst.jus.br" --sources web --scrape --limit 5`
- (D) Consulta unificada: `https://www.tst.jus.br/jurisprudencia`
- (D/I) FALCÃO (Banco Nacional de Jurisprudência Trabalhista, TST + 24 TRTs): `https://jurisprudencia.jt.jus.br/` — busca via interact.

### TRFs — CJF unificada `www2.cjf.jus.br/jurisprudencia` + portais regionais
- (D) Jurisprudência unificada dos TRFs (CJF): `https://www2.cjf.jus.br/jurisprudencia/unificada/` e por região `.../jurisprudencia/trf1/` … `/trf6/`
- TRF1: (D) `https://www.trf1.jus.br/trf1/pesquisa/ementario-de-jurisprudencia` · inteiro teor `https://arquivo.trf1.jus.br/`
- (S) `firecrawl search "TERMO site:trf1.jus.br"` (troque o domínio por trf2…trf6.jus.br)

### TJs — padrão e-SAJ `esaj.<tj>.jus.br/cjsg` (CJSG = 2º grau)
- (S) `firecrawl search "TERMO site:tjsp.jus.br" --sources web --scrape --limit 5` (troque o domínio pelo TJ)
- (I) TJSP — Consulta de Julgados de 2º Grau (formulário POST): `https://esaj.tjsp.jus.br/cjsg/consultaCompleta.do` → resultado em `resultadoCompleta.do`. Use `firecrawl interact` para preencher e paginar.
- O mesmo padrão e-SAJ/CJSG vale para vários TJs (ex.: `esaj.tjms.jus.br/cjsg/...`, `esaj.tjce.jus.br/cjsg/...`). TJs fora do e-SAJ (TJMG, TJRJ, etc.) têm portal próprio — descubra a URL via (S) e então (D)/(I).

> Para tribunais via formulário/SPA, **prefira o JusBrasil autenticado** (seção 2) ou
> o **brlaw MCP** quando cobrir o tribunal — costuma sair mais limpo que dirigir o
> formulário oficial com `interact`. Use o scrape oficial sobretudo para **inteiro
> teor** de uma URL já identificada.

## 4. Legislação (texto oficial)

Para **legislação federal**, prefira o **senado MCP** (texto consolidado, versão na
data) antes de raspar a web. Use os sites abaixo para inteiro teor oficial, normas
infralegais e legislação estadual/municipal (que o MCP não cobre). Prefixo firecrawl
local omitido — acrescente `--api-url http://localhost:3002 -k local-firecrawl-key`.

### Planalto — `planalto.gov.br/ccivil_03` (texto oficial federal)
- (D) Lei ordinária: `firecrawl scrape "https://www.planalto.gov.br/ccivil_03/leis/l8429.htm" --format markdown`
- **Texto atualizado** = sufixo `compilado` (ex.: `.../decreto-lei/del2848compilado.htm` = CP; `del5452compilado.htm` = CLT). CF: `/ccivil_03/constituicao/constituicao.htm`. Lei complementar: `/ccivil_03/LEIS/LCP/LcpNN.htm`. Leis por ano: `/ccivil_03/_ato2023-2026/2024/lei/_leis2024.htm`.
- (S) descobrir a URL: `firecrawl search "Lei 14.133 compilado site:planalto.gov.br"`
- Portal da Legislação: `https://www4.planalto.gov.br/legislacao`

### LexML — `lexml.gov.br` (busca unificada + estadual/municipal + URN)
- (S) `firecrawl search "TERMO site:lexml.gov.br"` — legislação, jurisprudência, proposições e **doutrina**, federal/estadual/municipal.
- (D) busca direta (scrape): `https://www.lexml.gov.br/busca/search?keyword=TERMO`
- Cada norma tem **URN persistente** (`urn:lex:br:...`) — bom para citar link estável.

### Senado / Câmara (legislação federal + tramitação)
- senado MCP = via preferida (texto consolidado). Web: `https://www25.senado.leg.br/web/atividade/legislacao` · texto compilado por data em `https://normas.leg.br`
- Câmara: `https://www2.camara.leg.br/atividade-legislativa/legislacao`

### DOU / Imprensa Nacional — `in.gov.br/consulta` (infralegal e atos recentes)
- (D/I) `https://www.in.gov.br/consulta` — portarias, resoluções, nomeações, atos publicados (edições desde 1990). Formulário → `interact` ou monte a URL de consulta.
- (S) `firecrawl search "TERMO portaria site:in.gov.br"`

### Estadual / Municipal
- Não está no Planalto. Use (S) `firecrawl search "lei estadual TERMO site:<diario-oficial-do-estado>"` ou LexML; depois (D) scrape do texto. Para o RJ, ex.: ALERJ/`gov-rj`; confirme o domínio via (S).

## Ordem de prioridade (legislação)
1. **senado MCP** (texto consolidado federal, versão na data)
2. **Planalto** `ccivil_03` (texto oficial federal — use `compilado`)
3. **LexML** (busca unificada, URN, estadual/municipal, doutrina)
4. **DOU** `in.gov.br` (normas infralegais e atos recentes)
5. **Firecrawl local / WebSearch nativo** (estadual/municipal e o que faltar)
6. Conhecimento do modelo (última opção, marcar como não-verificado)

## Ordem de prioridade (jurisprudência)
1. **brlaw MCP** (ementas diretas STF/STJ/TST)
2. **JusBrasil autenticado** (íntegra, tribunais não cobertos pelo brlaw, doutrina)
3. **Firecrawl local** (scrape direto de `*.jus.br`, busca web)
4. **WebSearch nativo** (se firecrawl local offline)
5. Conhecimento do modelo (última opção, marcar como não-verificado)

Sempre confirme dados do JusBrasil/scrape no inteiro teor oficial quando a decisão
for citada como fundamento.
