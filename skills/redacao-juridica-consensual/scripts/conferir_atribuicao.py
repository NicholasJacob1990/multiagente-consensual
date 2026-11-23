#!/usr/bin/env python3
"""Confere se o que um texto atribui à fonte (a consulente, a CI, a área técnica) está na fonte.

Relatórios e sínteses de terceiros costumam pôr na boca da consulente o que ela não
disse: "desincorporação", "riscos à governança", "encargos", "divergência de área
física", "indisponibilidades ativas"; ou resumem os quesitos deixando de fora a
alternativa ("ou procedimento administrativo ou registral específico") ou a
ressalva ("observados os direitos dos titulares") que lhes dá o alcance. Este
script localiza, no TEXTO, as frases que atribuem algo à FONTE e compara o
vocabulário delas com o da fonte.

Frases atribuídas (lista ``ATRIBUICAO``, configurável): "segundo (relata) a
consulente", "a (própria) consulente relata/pede/indaga/solicita/pondera/fixa/
submeteu/constatou...", "a GEPAT submeteu...", "a CI (nº ...) diz/pede...", "na CI",
"a equipe (técnica) da consulente", "a área técnica solicitou", "quesitos",
"premissa ... fixada pela própria consulente", "a consulta tem por objeto"...

Termos de conteúdo: palavras com 5 letras ou mais, sem acento e em minúsculas, fora
das stopwords (função gramatical e vocabulário jurídico genérico do caso: consulta,
parecer, imóveis, lotes, matrícula, cartório...; e o próprio vocabulário de
atribuição: relata, pondera, premissa, quesitos...). A comparação é pelo radical de
5 letras, com três graus:

- ``sem_lastro``: nenhuma palavra da fonte tem o mesmo radical;
- ``lastro_fraco``: a fonte só tem palavras de mesmo radical mas de outra família
  (prefixo comum menor que o termo menos 2 letras: "governança" × "Governador") e
  nem isso aparece no trecho da fonte mais parecido com a frase;
- ``acrescentado_ao_quesito``: termo do quesito resumido que não está no quesito
  correspondente da fonte.

``EQUIVALENCIAS`` (configurável) junta radicais de paráfrase corrente
("cabimento"/"cabível"/"possibilidade", "respeitados"/"observados",
"sugerida"/"orientação"), para não acusar a mera troca de palavra.

Quesitos: se a frase enumera ("primeiro…, segundo…, terceiro…", "1.", "2.", "(i)",
"a)"), cada item é alinhado com o item de mesmo número da lista numerada da fonte
mais parecida ("1. Os efeitos…", "2. A necessidade…"). Além dos termos
acrescentados, acusa ``omissao``: alternativa com "ou", ressalva com "observados",
"ressalvados", "respeitados", "inclusive", "salvo", "exceto", "desde que", e o
qualificador "eventual(is)", quando o item resumido não cobre ao menos 30% dos
termos do segmento — ou de cada parte coordenada por "e a/o/os/as/à/ao" ("eventual
subsistência do domínio direto e à necessidade de resgate") — ou, no caso de
"eventual", perde o qualificador. Na fonte
``.docx`` a lista de quesitos só é reconhecida se o número estiver no texto.

Configuração (``--config ARQ.json``, todos os campos opcionais)::

    {"atribuicao": ["regex sem acento", ...],         # substitui a lista padrão
     "atribuicao_extra": ["\\\\bo requerente (pede|informa)\\\\b"],
     "stopwords_extra": ["distrito", "quadra"],
     "equivalencias": [["cabimento", "cabivel"], ["respeitados", "observados"]]}

Uso::

    conferir_atribuicao.py --fonte CI_108.md relatorio_sugerido.md
    conferir_atribuicao.py --fonte CI_108.md parecer_v21.docx --paragrafos 2-9 --json achados.json --md achados.md

``--json`` e ``--md`` sem arquivo escrevem no stdout (no lugar do relatório em texto).
Código de saída: 1 quando houver termo sem lastro, lastro fraco, termo acrescentado
ao quesito ou omissão; 0 quando não houver; 2 em erro de uso ou de leitura.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checar_refutadas as cr  # noqa: E402

RADICAL = 5
MIN_LETRAS = 5
COBERTURA_MINIMA = 0.3

ATRIBUICAO = [
    r"\bsegundo (?:relata |informa |narra |consta d)?(?:a|o) (?:propri[ao] )?(?:consulente|gepat|codin|area tecnica|ci\b|comunicacao interna)",
    r"\b(?:conforme|consoante|de acordo com) (?:relata |informa )?a (?:propria )?(?:consulente|gepat|area tecnica|ci\b|comunicacao interna)",
    r"\ba (?:propria )?consulente,? (?:\w+,? ){0,2}?(?:relat|inform|narr|ped|indag|solicit|ponder|fix|submet|constat|afirm|registr|"
    r"esclarec|observ|apont|entend|requer|question|encaminh|identific|destac|ressalt|sustent|aleg|propo|suger|levant|consign)\w*",
    r"\ba (?:equipe (?:tecnica )?da )?(?:gepat|codin)\b,? (?:\w+,? ){0,2}?(?:relat|inform|narr|ped|indag|solicit|ponder|fix|submet|"
    r"constat|afirm|registr|esclarec|observ|apont|entend|requer|question|encaminh|identific|destac|ressalt|comparec|levant|consult|"
    r"formul|suger|consign)\w*",
    r"\ba (?:ci|comunicacao interna)(?: \(ci\))?(?: n[o.]* ?[\d./]+)?,? (?:\w+,? ){0,2}?(?:diz|dis|afirm|relat|inform|narr|ped|indag|"
    r"solicit|ponder|fix|submet|constat|registr|esclarec|observ|apont|requer|question|identific|destac|ressalt|consign|menciona)\w*",
    r"\bna (?:ci|comunicacao interna)\b",
    r"\b(?:d?a|pela|com a) equipe (?:tecnica )?da (?:consulente|gepat|codin)\b",
    r"\b(?:orientacao|diretriz|informacao|resposta) verbal\b",
    r"\ba area tecnica (?:\w+ ){0,2}?(?:solicit|ped|inform|relat|indag|requer|apont|constat|registr|suger)\w*",
    r"\b(?:os|tres|dois|quatro|cinco|seguintes|estes|esses|aqueles) (?:\w+ )?quesitos\b",
    r"\bquesitos? (?:formulad|submetid|apresentad|propost|post|enunciad|da consulente|da gepat|da ci\b)\w*",
    r"\bpremissa\b.{0,120}?\b(?:fixad|indicad|estabelecid|definid|adotad|posta|tracad)\w* pela (?:propria )?(?:consulente|gepat|ci\b)",
    r"\b(?:diretriz|orientacao)\b.{0,40}?\b(?:fixad|indicad|estabelecid|definid)\w* pela (?:propria )?(?:consulente|gepat|ci\b)",
    r"\ba consulta (?:tem por objeto|versa|trata)\b",
]

STOPWORDS = set("""
sobre quanto quanta quantos entre pelos pelas desde ainda tambem sendo tendo assim diante disso desse dessa deste desta
destes destas desses dessas esses essas estes estas aquele aquela aqueles aquelas outro outra outros outras mesmo mesma
mesmos mesmas quais porque porem contudo todavia apenas somente antes depois durante perante conforme segundo primeiro
primeira terceiro terceira quarto quarta quinto seguinte seguintes inclusive eventual eventuais especialmente
especificamente sempre nunca quando onde ainda poderia poderiam dependeria seria seriam foram sejam estar estao esteve
tenha tinha haver havia houve havera possui possuem tratar trata tratase referidos referidas referido referida
respectivos respectivas respectivo respectiva presente presentes partir forma modo termos acerca junto frente nesse
nessa neste nesta nestes nestas nesses nessas naquele naquela sentido ambos ambas algum alguma alguns algumas nenhum
nenhuma todos todas quaisquer qualquer tanto enquanto embora porquanto mediante atraves dentre entao devem deveria
deverao podem pode fazer feito feita feitos feitas cujos cujas sejam estas certo certa certos certas maior menor
muito muitos muita muitas pouco poucos tres quatro cinco daqui desta dele dela deles delas nelas neles pelas
consulta consultas consulente consulentes parecer pareceres imoveis imovel lotes matricula matriculas quadra quadras
distrito distritos industrial industriais montes claros codemig codemge gepat codin genes companhia companhias
gerencia gerencias orgao juridica juridicas juridico juridicos analise analises exame documento documentos processo
processos comunicacao interna estado minas gerais cartorio cartorios registro registros objeto materia questao
questoes situacao relativo relativa relativos relativas acerca tocante respeito
relata relatam relatou relato informa informou informam narra narrou pede pediu pedem pedido pedidos indaga indagou
solicita solicitou solicitam solicitacao pondera ponderou fixa fixou fixada fixado submeteu submete submetidos constatou
constata afirma afirmou registra registrou esclarece esclareceu observa observou aponta apontou entende entendeu requer
questiona encaminha encaminhou identificou destaca ressalta sustenta alega propoe sugere sugeriu levantou consigna
formula formulou formulada formulado formulados formuladas consultivo consultiva considerando pecas autos folhas
premissa premissas diretriz propria proprio quesito quesitos equipe tecnica tecnico tecnicos tecnicas adotase adota
""".split())

EQUIVALENCIAS = [
    ["cabimento", "cabivel", "cabiveis", "possibilidade"],
    ["respeitados", "observados", "ressalvados", "preservados"],
    ["sugerida", "sugerido", "orientacao", "indicada", "recomendada"],
    ["analisar", "examinar", "exame"],
    ["cartorio", "serventia"],
    ["exigiria", "exige", "exigir", "necessaria", "necessario", "necessidade"],
    ["global", "total", "totalizando"],
]

MARCADOR_ORDINAL_RE = re.compile(r"\b(primeir|segund|terceir|quart|quint|sext|setim|oitav|non|decim)[oa]s?\b\s*[,:]")
ORDINAIS = ["primeir", "segund", "terceir", "quart", "quint", "sext", "setim", "oitav", "non", "decim"]
MARCADOR_NUM_RE = re.compile(r"(?:(?<=\s)|(?<=^)|(?<=[:;]))\(?(\d{1,2}|[ivx]{1,4}|[a-h])[.)]\s+(?=[a-z])")
RESSALVA_RE = re.compile(r"\b(observad[oa]s?|ressalvad[oa]s?|respeitad[oa]s?|inclusive|salvo|exceto|desde que)\b")
EVENTUAL_RE = re.compile(r"\beventua(?:l|is)\b")
HEDGE_RE = re.compile(r"\b(?:eventua(?:l|is)|possive(?:l|is)|se for o caso|quando cabive(?:l|is)|porventura|se houver)\b")
OU_RE = re.compile(r"\bou\b")
COORDENACAO_RE = re.compile(r"\s+e\s+(?=(?:a|o|as|os|ao|aos)\s)")
FIM_SEGMENTO_RE = re.compile(r"[,;:]|\.(?!\d)|$")
FRASE_RE = re.compile(r"(?<=[.!?])\s+(?=[\"“(«]?[A-ZÀ-Ý0-9])")
CITACAO_RE = re.compile(r"\([^()]*?(?:\bpp?\.\s*\d|\bSEIs?\b|\bfls?\.\s*\d|\barts?\.\s*\d)[^()]*\)", re.IGNORECASE)
PALAVRA_RE = re.compile(r"[a-z]+")
QUESITO_FONTE_RE = re.compile(r"^\s*\(?(\d{1,2})[.)]\s+(\S.*)$")


# ---------------------------------------------------------------- vocabulário

@dataclass
class Config:
    atribuicao: list[re.Pattern]
    stopwords: set[str]
    grupos: dict[str, int]  # radical -> grupo de equivalência


def config(dados: dict | None = None) -> Config:
    dados = dados or {}
    pads = list(dados.get("atribuicao") or ATRIBUICAO) + list(dados.get("atribuicao_extra") or [])
    try:
        rxs = [re.compile(p, re.IGNORECASE) for p in pads]
    except re.error as e:
        raise ValueError(f"padrão de atribuição inválido: {e}") from e
    stop = STOPWORDS | {cr.normalizar(s) for s in dados.get("stopwords_extra") or []}
    grupos: dict[str, int] = {}
    for g, lista in enumerate(list(EQUIVALENCIAS) + list(dados.get("equivalencias") or [])):
        alvo = next((grupos[cr.normalizar(p)[:RADICAL]] for p in lista if cr.normalizar(p)[:RADICAL] in grupos), g + 1000)
        for p in lista:
            grupos[cr.normalizar(p)[:RADICAL]] = alvo
    return Config(rxs, stop, grupos)


def palavras(texto_norm: str) -> list[str]:
    return PALAVRA_RE.findall(texto_norm)


def termos(texto: str, cfg: Config) -> list[str]:
    """Termos de conteúdo (normalizados, na ordem, sem repetição) — fora as citações entre parênteses."""
    vistos, out = set(), []
    for w in palavras(cr.normalizar(CITACAO_RE.sub(" ", texto))):
        if len(w) >= MIN_LETRAS and w not in cfg.stopwords and w not in vistos:
            vistos.add(w)
            out.append(w)
    return out


def _prefixo_comum(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


PLURAIS = (("oes", "ao"), ("aes", "ao"), ("ais", "al"), ("eis", "el"), ("ois", "ol"), ("ns", "m"))
PARTICIPIO_RE = re.compile(r"(?:(?<=[a-z]{3})id|(?<=[a-z]{3})ad)(?:o|a|os|as)$")


def forma_base(w: str) -> str:
    """Flexão reduzida: plural ("obrigações" → "obrigação") e particípio ("vendidos" → "vende", "registradas" → "registra")."""
    for suf, rep in PLURAIS:
        if w.endswith(suf) and len(w) > len(suf) + 3:
            return w[: -len(suf)] + rep
    m = PARTICIPIO_RE.search(w)
    if m:
        return w[: m.start()] + ("e" if m.group(0).startswith("i") else "a")
    if w.endswith("s") and len(w) > MIN_LETRAS:
        return w[:-1]
    return w


def _infinitivo(t: str) -> str | None:
    """Prefixo de busca do infinitivo curto ("obter" → "obte", que acha "obtenção")."""
    return t[:-1] if re.search(r"[aei]r$", t) and len(t) - 1 >= RADICAL - 1 else None


class Vocabulario:
    """Palavras de um trecho da fonte, indexadas pelo radical (e pelo grupo de equivalência)."""

    def __init__(self, texto_ou_palavras, cfg: Config):
        ws = palavras(cr.normalizar(texto_ou_palavras)) if isinstance(texto_ou_palavras, str) else list(texto_ou_palavras)
        self.cfg = cfg
        self.por_radical: dict[str, set[str]] = {}
        self.por_prefixo4: dict[str, set[str]] = {}
        for w in ws:
            for x in {w, forma_base(w)}:
                if len(x) >= RADICAL - 1:
                    self.por_radical.setdefault(x[:RADICAL], set()).add(x)
                    self.por_prefixo4.setdefault(x[:RADICAL - 1], set()).add(x)
        self.grupos = {cfg.grupos[r] for r in self.por_radical if r in cfg.grupos}

    def _equivalente(self, t: str) -> bool:
        return any(self.cfg.grupos.get(x[:RADICAL]) in self.grupos for x in {t, forma_base(t)})

    def _infinitivo_acha(self, t: str) -> bool:
        p = _infinitivo(t)
        return bool(p) and any(w.startswith(p) for w in self.por_prefixo4.get(p[:RADICAL - 1], ()))

    def tem_radical(self, t: str) -> bool:
        return (any(x[:RADICAL] in self.por_radical for x in {t, forma_base(t)}) or self._equivalente(t)
                or self._infinitivo_acha(t))

    def grau(self, t: str) -> str:
        """"forte" (mesma família), "fraco" (só o radical) ou "nenhum"."""
        if self._equivalente(t) or self._infinitivo_acha(t):
            return "forte"
        achou = False
        for x in {t, forma_base(t)}:
            ws = self.por_radical.get(x[:RADICAL])
            if not ws:
                continue
            achou = True
            exigido = max(RADICAL, len(x) - 2)
            if any(_prefixo_comum(x, w) >= min(exigido, len(w)) for w in ws):
                return "forte"
        return "fraco" if achou else "nenhum"


# ---------------------------------------------------------------- leitura

@dataclass
class Paragrafo:
    linha: int
    numero: int | None
    texto: str
    local: str


def ler_paragrafos(path: Path) -> list[Paragrafo]:
    """Parágrafos de .md/.txt (linha a linha; número do "N." inicial) ou .docx (visão com alterações aceitas)."""
    if path.suffix.lower() == ".docx":
        import exportar_comentarios as ec

        out = []
        for p in ec.ler_paragrafos(path):
            if p["texto"]:
                i = p["indice"] + 1
                local = f"§ {p['numero']}" if p["numero"] else f"parágrafo {i}"
                out.append(Paragrafo(i, p["numero"], p["texto"], local))
        return out
    out = []
    for i, l in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not l.strip():
            continue
        m = re.match(r"^\s*(\d+)\.\s+", l)
        numero = int(m.group(1)) if m else None
        out.append(Paragrafo(i, numero, l.strip(), f"§ {numero}" if numero else f"linha {i}"))
    return out


def ler_fonte(path: Path) -> str:
    """Texto da fonte, com parágrafos separados por linha em branco."""
    if path.suffix.lower() == ".docx":
        return "\n\n".join(p.texto for p in ler_paragrafos(path))
    return path.read_text(encoding="utf-8")


def frases(texto: str) -> list[str]:
    return [f.strip() for f in FRASE_RE.split(texto) if f.strip()]


@dataclass
class Fonte:
    texto: str
    frases: list[str]
    vocab: Vocabulario
    vocab_frases: list[Vocabulario]
    listas: list[list[str]]  # listas numeradas (1., 2., 3....) da fonte


def preparar_fonte(texto: str, cfg: Config) -> Fonte:
    blocos = [re.sub(r"\s+", " ", b).strip() for b in re.split(r"\n\s*\n", texto)]
    fs = [f for b in blocos if b for f in frases(b)]
    return Fonte(texto, fs, Vocabulario(texto, cfg), [Vocabulario(f, cfg) for f in fs], listas_numeradas(texto))


def listas_numeradas(texto: str) -> list[list[str]]:
    """Sequências "1.", "2.", "3."... da fonte; cada item vai até a linha em branco ou ao próximo número."""
    itens: list[tuple[int, str]] = []
    atual: list[str] | None = None
    num = 0
    for linha in texto.splitlines() + [""]:
        m = QUESITO_FONTE_RE.match(linha)
        if m:
            if atual is not None:
                itens.append((num, " ".join(atual)))
            num, atual = int(m.group(1)), [m.group(2).strip()]
        elif not linha.strip():
            if atual is not None:
                itens.append((num, " ".join(atual)))
            atual = None
        elif atual is not None:
            atual.append(linha.strip())
    listas: list[list[str]] = []
    for n, t in itens:
        if n == 1:
            listas.append([t])
        elif listas and n == len(listas[-1]) + 1:
            listas[-1].append(t)
    return listas


# ---------------------------------------------------------------- análise

@dataclass
class Termo:
    termo: str
    grau: str  # sem_lastro | lastro_fraco | acrescentado_ao_quesito
    quesito: int | None = None
    nota: str = ""


@dataclass
class Omissao:
    quesito: int
    tipo: str  # alternativa | ressalva | qualificador
    trecho_fonte: str
    termos_omitidos: list[str]


@dataclass
class Atribuicao:
    arquivo: str
    local: str
    linha: int
    gatilho: str
    frase: str
    trecho_fonte: str
    termos: list[Termo] = field(default_factory=list)
    omissoes: list[Omissao] = field(default_factory=list)

    @property
    def acusacoes(self) -> int:
        return len(self.termos) + len(self.omissoes)


def gatilho(frase_norm: str, cfg: Config) -> re.Match | None:
    achados = [m for rx in cfg.atribuicao for m in [rx.search(frase_norm)] if m]
    return min(achados, key=lambda m: m.start()) if achados else None


CONCESSIVA_RE = re.compile(r"^(?:embora|conquanto|ainda que|se bem que|apesar de|nao obstante|mesmo que)\b")
VIRGULA_RE = re.compile(r"[,;](?!\d)")
SEGUNDO_RE = re.compile(r"^(?:segundo|conforme|consoante|de acordo com)\b")


def escopo_atribuido(frase: str, m: re.Match) -> str:
    """Parte da frase que é atribuída à fonte.

    "Embora a CI relate X, o parecer Y" → só "Embora a CI relate X"; "…, cuja área era Z, segundo a
    consulente: W" → "cuja área era Z … W" (a oração antes do "segundo" e o que vem depois dele); nos
    demais casos, a frase inteira."""
    norm, idx = cr.normalizar_com_indices(frase)
    original = lambda a, b: frase[idx[a]: idx[b - 1] + 1] if b > a else ""  # noqa: E731
    lead = len(norm) - len(norm.lstrip())
    if CONCESSIVA_RE.match(norm.lstrip()) and m.start() < (VIRGULA_RE.search(norm, lead) or m).start() + 1:
        v = VIRGULA_RE.search(norm, m.end())
        return original(0, v.start()) if v else frase
    if SEGUNDO_RE.match(m.group(0)) and norm[:m.start()].strip():
        antes = [v.end() for v in VIRGULA_RE.finditer(norm, 0, max(0, m.start() - 2))]
        a = antes[-1] if antes else 0
        return (original(a, m.start()) + " " + original(m.end(), len(norm))).strip()
    return frase


def trecho_mais_parecido(ts: list[str], fonte: Fonte, max_frases: int = 3) -> tuple[int, int]:
    """Janela de 1 a ``max_frases`` frases consecutivas da fonte com mais termos em comum (penalizando o tamanho)."""
    melhor, ini, fim = -1.0, 0, 0
    for i in range(len(fonte.frases)):
        for k in range(1, max_frases + 1):
            if i + k > len(fonte.frases):
                break
            acertos = sum(1 for t in ts if any(v.tem_radical(t) for v in fonte.vocab_frases[i:i + k]))
            score = acertos - 0.75 * (k - 1)
            if score > melhor:
                melhor, ini, fim = score, i, i + k
    return ini, fim


def _itens_enumerados(frase: str) -> list[tuple[int, str]]:
    """Itens de uma enumeração ("primeiro, …; segundo, …" ou "1. … 2. …"), com o número de cada um."""
    norm, idx = cr.normalizar_com_indices(frase)
    marcas: list[tuple[int, int, int]] = []  # (número, início da marca, fim da marca) em ``norm``
    esperado = 0
    for m in MARCADOR_ORDINAL_RE.finditer(norm):
        k = ORDINAIS.index(m.group(1)) + 1
        if k == esperado + 1:
            marcas.append((k, m.start(), m.end()))
            esperado = k
    if len(marcas) < 2:
        marcas, esperado = [], 0
        for m in MARCADOR_NUM_RE.finditer(norm):
            g = m.group(1)
            if g.isdigit():
                k = int(g)
            elif re.fullmatch(r"[ivx]+", g) and (g != "i" or esperado == 0):  # "i)" abre romanos; "i" depois de "h)" seria letra
                k = _romano(g)
            else:
                k = "abcdefgh".index(g) + 1 if g in "abcdefgh" else 0
            if k == esperado + 1:
                marcas.append((k, m.start(), m.end()))
                esperado = k
    if len(marcas) < 2:
        return []
    out = []
    for j, (k, _, fim) in enumerate(marcas):
        prox = marcas[j + 1][1] if j + 1 < len(marcas) else len(norm)
        a, b = idx[fim] if fim < len(idx) else len(frase), idx[prox - 1] + 1 if prox > fim else len(frase)
        item = frase[a:b].strip()
        item = re.sub(r"[;,]?\s*\be\s*$", "", item).strip(" ;,.")
        out.append((k, item))
    return out


def _romano(s: str) -> int:
    valores = {"i": 1, "v": 5, "x": 10}
    total = 0
    for i, c in enumerate(s):
        v = valores[c]
        total += -v if i + 1 < len(s) and valores[s[i + 1]] > v else v
    return total


def segmentos_de_alcance(texto: str) -> list[tuple[str, str]]:
    """(tipo, segmento) da fonte que delimitam o alcance: alternativas ("ou …"), ressalvas e "eventual"."""
    norm = cr.normalizar(texto)
    achados: list[tuple[int, int, str]] = []
    for rx, tipo in ((RESSALVA_RE, "ressalva"), (OU_RE, "alternativa"), (EVENTUAL_RE, "qualificador")):
        for m in rx.finditer(norm):
            fim = FIM_SEGMENTO_RE.search(norm, m.end())
            achados.append((m.start(), fim.start() if fim else len(norm), tipo))
    achados.sort(key=lambda x: (x[0], -x[1]))
    out, ate = [], -1
    for a, b, tipo in achados:
        if a < ate:  # aninhado em segmento anterior ("inclusive quanto à eventual …", "procedimento administrativo ou registral")
            continue
        out.append((tipo, norm[a:b].strip()))
        ate = b
    return out


def conferir_quesitos(itens: list[tuple[int, str]], fonte: Fonte, cfg: Config,
                      ja_acusados: set[str]) -> tuple[list[Termo], list[Omissao]]:
    """Alinha cada item com o quesito de mesmo número da lista da fonte mais parecida."""
    if not fonte.listas:
        return [], []

    def parecenca(lista: list[str]) -> float:
        s = 0.0
        for k, item in itens:
            if k <= len(lista):
                ti, tf = set(t[:RADICAL] for t in termos(item, cfg)), set(t[:RADICAL] for t in termos(lista[k - 1], cfg))
                s += len(ti & tf) / math.sqrt(max(1, len(ti)) * max(1, len(tf)))
        return s

    lista = max(fonte.listas, key=parecenca)
    if parecenca(lista) <= 0:
        return [], []
    novos: list[Termo] = []
    omissoes: list[Omissao] = []
    for k, item in itens:
        if k > len(lista):
            for t in termos(item, cfg):
                if t not in ja_acusados and not fonte.vocab.tem_radical(t):
                    novos.append(Termo(t, "sem_lastro", k, "quesito sem correspondente na fonte"))
            continue
        q = lista[k - 1]
        vq = Vocabulario(q, cfg)
        vitem = Vocabulario(item, cfg)
        for t in termos(item, cfg):
            if t in ja_acusados:
                continue
            if not vq.tem_radical(t):
                nota = "consta em outra parte da fonte" if fonte.vocab.tem_radical(t) else "não consta da fonte"
                novos.append(Termo(t, "acrescentado_ao_quesito", k, nota))
        item_norm = cr.normalizar(item)
        for tipo, seg in segmentos_de_alcance(q):
            if tipo == "qualificador":
                alvo = [t for t in termos(seg, cfg)]
                if alvo and any(vitem.tem_radical(t) for t in alvo) and not HEDGE_RE.search(item_norm):
                    omissoes.append(Omissao(k, tipo, seg, [palavras(seg)[0]]))
                continue
            faltam: list[str] = []
            for parte in COORDENACAO_RE.split(seg):  # "… do domínio direto e à necessidade …": cada parte conta
                ts = [t for t in termos(parte, cfg) if not RESSALVA_RE.fullmatch(t)]
                cobertos = [t for t in ts if vitem.tem_radical(t)]
                if ts and len(cobertos) < max(1, math.ceil(COBERTURA_MINIMA * len(ts))):
                    faltam += [t for t in ts if t not in cobertos]
            if faltam:
                omissoes.append(Omissao(k, tipo, seg, faltam))
    return novos, omissoes


def conferir_frase(frase: str, gat: re.Match, fonte: Fonte, cfg: Config, arquivo: str, par: Paragrafo) -> Atribuicao:
    do_gatilho = set(palavras(gat.group(0)))  # a própria fórmula de atribuição ("a CI relate") não é conteúdo
    ts = [t for t in termos(escopo_atribuido(frase, gat), cfg) if t not in do_gatilho]
    # o trecho mais parecido é escolhido só pelos termos de lastro forte: "governança" não puxa "Governador"
    ini, fim = trecho_mais_parecido([t for t in ts if fonte.vocab.grau(t) == "forte"], fonte)
    trecho = " ".join(fonte.frases[ini:fim])
    vtrecho = Vocabulario(trecho, cfg)
    acusados: list[Termo] = []
    for t in ts:
        g = fonte.vocab.grau(t)
        if g == "nenhum":
            acusados.append(Termo(t, "sem_lastro"))
        elif g == "fraco" and not vtrecho.tem_radical(t):
            exemplos = ", ".join(sorted(fonte.vocab.por_radical.get(t[:RADICAL], set()))[:3])
            acusados.append(Termo(t, "lastro_fraco", nota=f"a fonte só tem {exemplos}"))
    at = Atribuicao(arquivo, par.local, par.linha, gat.group(0), frase, trecho, acusados)
    itens = _itens_enumerados(frase)
    if itens:
        for t in acusados:
            t.quesito = next((k for k, item in itens if t.termo in termos(item, cfg)), None)
        novos, omissoes = conferir_quesitos(itens, fonte, cfg, {t.termo for t in acusados})
        at.termos += novos
        at.omissoes = omissoes
    return at


def conferir(fonte: Fonte, paragrafos: list[Paragrafo], arquivo: str, cfg: Config) -> list[Atribuicao]:
    out = []
    for p in paragrafos:
        for f in frases(p.texto):
            g = gatilho(cr.normalizar(f), cfg)
            if g:
                out.append(conferir_frase(f, g, fonte, cfg, arquivo, p))
    return out


def filtro_paragrafos(spec: str | None):
    """"2-9,12" -> função que diz se o parágrafo numerado entra."""
    if not spec:
        return lambda p: True
    nums: set[int] = set()
    for parte in spec.split(","):
        parte = parte.strip()
        if re.fullmatch(r"\d+\s*[-–]\s*\d+", parte):
            a, b = (int(x) for x in re.split(r"\s*[-–]\s*", parte))
            nums.update(range(a, b + 1))
        elif parte.isdigit():
            nums.add(int(parte))
        elif parte:
            raise ValueError(f"--paragrafos: intervalo inválido {parte!r}")
    return lambda p: p.numero in nums


# ---------------------------------------------------------------- saída

ROTULO = {"sem_lastro": "sem lastro na fonte", "lastro_fraco": "lastro fraco (só radical de outra família)",
          "acrescentado_ao_quesito": "acrescentado ao quesito"}


def _curto(s: str, n: int = 220) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n - 1] + "…"


def resumo(ats: list[Atribuicao]) -> dict:
    termos_ = [t for a in ats for t in a.termos]
    return {"frases_atribuidas": len(ats), "frases_com_acusacao": sum(1 for a in ats if a.acusacoes),
            "sem_lastro": sum(t.grau == "sem_lastro" for t in termos_),
            "lastro_fraco": sum(t.grau == "lastro_fraco" for t in termos_),
            "acrescentado_ao_quesito": sum(t.grau == "acrescentado_ao_quesito" for t in termos_),
            "omissoes": sum(len(a.omissoes) for a in ats)}


def relatorio_texto(ats: list[Atribuicao], fonte: Path, textos: list[Path]) -> str:
    r = resumo(ats)
    linhas = [f"CONFERÊNCIA DE ATRIBUIÇÃO — fonte: {fonte.name} | textos: {', '.join(p.name for p in textos)}",
              f"frases atribuídas: {r['frases_atribuidas']} | com acusação: {r['frases_com_acusacao']} | "
              f"sem lastro: {r['sem_lastro']} | lastro fraco: {r['lastro_fraco']} | acrescentados a quesito: "
              f"{r['acrescentado_ao_quesito']} | omissões: {r['omissoes']}", ""]
    for a in ats:
        if not a.acusacoes:
            continue
        linhas.append(f"{a.arquivo} {a.local} (linha {a.linha}) [{a.gatilho}]: «{_curto(a.frase)}»")
        for t in a.termos:
            q = f" (quesito {t.quesito})" if t.quesito else ""
            linhas.append(f"    - {t.termo}: {ROTULO[t.grau]}{q}" + (f" — {t.nota}" if t.nota else ""))
        for o in a.omissoes:
            linhas.append(f"    - OMISSÃO no quesito {o.quesito} ({o.tipo}): a fonte diz «{_curto(o.trecho_fonte, 160)}»"
                          f" — falta: {', '.join(o.termos_omitidos)}")
        linhas.append(f"    trecho mais parecido da fonte: «{_curto(a.trecho_fonte, 260)}»")
    sem = list(dict.fromkeys(f"{a.arquivo} {a.local}" for a in ats if not a.acusacoes))
    if sem:
        linhas += ["", "Frases atribuídas sem acusação: " + "; ".join(sem)]
    total = r["sem_lastro"] + r["lastro_fraco"] + r["acrescentado_ao_quesito"] + r["omissoes"]
    linhas += ["", f"Resultado: {total} acusação(ões) em {r['frases_com_acusacao']} frase(s) atribuída(s)" if total
               else "Resultado: nada atribuído à fonte sem lastro"]
    return "\n".join(linhas)


def relatorio_md(ats: list[Atribuicao], fonte: Path, textos: list[Path]) -> str:
    r = resumo(ats)
    linhas = ["# Conferência de atribuição", "", f"Fonte: `{fonte.name}` | textos: {', '.join(f'`{p.name}`' for p in textos)}", "",
              f"Frases atribuídas: {r['frases_atribuidas']} | com acusação: {r['frases_com_acusacao']} | sem lastro: "
              f"{r['sem_lastro']} | lastro fraco: {r['lastro_fraco']} | acrescentados a quesito: {r['acrescentado_ao_quesito']} | "
              f"omissões: {r['omissoes']}", ""]
    for a in ats:
        if not a.acusacoes:
            continue
        linhas += [f"## {a.arquivo}, {a.local}", "", f"> {_curto(a.frase, 600)}", ""]
        linhas += [f"- **{t.termo}** — {ROTULO[t.grau]}" + (f" (quesito {t.quesito})" if t.quesito else "")
                   + (f"; {t.nota}" if t.nota else "") for t in a.termos]
        linhas += [f"- **omissão no quesito {o.quesito}** ({o.tipo}): a fonte diz «{_curto(o.trecho_fonte, 300)}»; falta "
                   f"{', '.join(o.termos_omitidos)}" for o in a.omissoes]
        linhas += ["", f"Trecho mais parecido da fonte: «{_curto(a.trecho_fonte, 500)}»", ""]
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fonte", type=Path, required=True, help="documento da consulente (.md, .txt ou .docx)")
    ap.add_argument("textos", type=Path, nargs="+", help="textos a conferir (.md, .txt ou .docx)")
    ap.add_argument("--paragrafos", help="só os parágrafos numerados indicados (ex.: 2-9,12)")
    ap.add_argument("--config", type=Path, help="JSON com atribuicao/atribuicao_extra/stopwords_extra/equivalencias")
    ap.add_argument("--json", nargs="?", const="-", help="grava as acusações em JSON (sem arquivo: stdout)")
    ap.add_argument("--md", nargs="?", const="-", help="grava o relatório em Markdown (sem arquivo: stdout)")
    args = ap.parse_args(argv)
    try:
        for p in [args.fonte, *args.textos] + ([args.config] if args.config else []):
            if not p.exists():
                raise OSError(f"arquivo não encontrado: {p}")
        cfg = config(json.loads(args.config.read_text(encoding="utf-8")) if args.config else None)
        filtro = filtro_paragrafos(args.paragrafos)
        fonte = preparar_fonte(ler_fonte(args.fonte), cfg)
        ats: list[Atribuicao] = []
        for p in args.textos:
            ats += conferir(fonte, [x for x in ler_paragrafos(p) if filtro(x)], p.name, cfg)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    dados = {"fonte": args.fonte.name, "resumo": resumo(ats),
             "atribuicoes": [asdict(a) | {"acusacoes": a.acusacoes} for a in ats]}
    stdout_usado = False
    if args.json:
        txt = json.dumps(dados, ensure_ascii=False, indent=2) + "\n"
        if args.json == "-":
            sys.stdout.write(txt)
            stdout_usado = True
        else:
            Path(args.json).write_text(txt, encoding="utf-8")
    if args.md:
        txt = relatorio_md(ats, args.fonte, args.textos)
        if args.md == "-":
            sys.stdout.write(txt)
            stdout_usado = True
        else:
            Path(args.md).write_text(txt, encoding="utf-8")
    if not stdout_usado:
        print(relatorio_texto(ats, args.fonte, args.textos))
    return 1 if any(a.acusacoes for a in ats) else 0


if __name__ == "__main__":
    sys.exit(main())
