#!/usr/bin/env python3
"""Confere remissões de um parecer (a parágrafos, a itens do Anexo e a dispositivos) e renumera com segurança.

Dividir parágrafos longos e renumerar um parecer de quase duzentos parágrafos
gera dezenas de remissões erradas: as duas partes de um parágrafo dividido
citadas quando a matéria estava em uma, números antigos sem conversão,
concordância quebrada ("O parágrafos 185 e 186 admite"), dispositivos que não
existem na minuta oficial citados sem a marca "sugerido" e artigos de outra norma
citados sem o diploma. Três subcomandos:

``conferir``
    Lê o parecer (``.docx``: parágrafos com ``numPr`` próprio e texto, contados como
    o Word; ``.md``/``.txt``: linhas ``N. texto``) e, se houver, o Anexo de Redações
    Sugeridas (itens ``Item N – título``), a minuta oficial, a minuta revisada e os
    comentários de um ou mais ``.docx``. Checa:

    - remissão a parágrafo ("parágrafo N", "parágrafos N e M", "parágrafos N a M",
      "parágrafos 31 a 34, 37 e 91", "par. N", "pars. N e M", "parágrafo 103, iii")
      no parecer, nas linhas do Anexo e nos comentários: número inexistente,
      intervalo invertido e numeral romano que não aparece como "(iii)" no
      parágrafo citado são bloqueantes;
    - concordância ("O parágrafos", "do parágrafos", "os parágrafos 3 e 4 admite")
      — alerta;
    - remissão a item do Anexo ("item 5", "itens 4 e 44", "itens 4 a 7",
      "item 54, V") no parecer, no Anexo e nos comentários: item inexistente é
      bloqueante. "item 8.6", "item 3 do Anexo II" e "item 2 do formulário" ficam de
      fora;
    - dispositivo citado ("art. 5º, § 2º", "art. 5º, parágrafo único", "§ 1º do
      art. 2º", "art. 5º, IV") que não existe na minuta oficial, sem "sugerid" na
      mesma oração ou parêntese — alerta; diz quando o dispositivo só existe na
      minuta revisada. Citação cuja oração menciona diploma (Lei, Decreto, IN,
      Estatuto, Constituição...) é de outra norma e fica de fora;
    - artigo sem diploma depois de o mesmo parágrafo citar artigo de diploma
      externo ("Lei nº 15.177/2025, art. 5º ... o art. 12") — informativo, para
      conferir se o artigo é da minuta.

``mapear``
    Alinha o parecer antigo ao novo: cada parágrafo antigo vira um ou mais novos
    (divisão), reconhecidos pelo texto (a parte nova é trecho do antigo, depois de
    normalizar espaços e tirar os números das remissões; pequenas edições são
    toleradas). Grava ``{"mapa": {"antigo": [novos]}, "decisoes": [...]}``; cada
    decisão é uma remissão (no ``--novo`` e nos arquivos ``--em``) a parágrafo antigo
    dividido ou suprimido, com local, oração, partes ("a", "b"... com o número novo e
    as primeiras 30 palavras) e ``"escolha": null``. Quando o numeral romano citado só
    aparece numa das partes, a decisão traz ``"sugestao"``.

``renumerar``
    Aplica o mapa a um ``.txt``, ``.md`` ou ``.json`` (em JSON, todos os campos de
    texto e as listas de inteiros chamadas ``paragrafos_parecer``). Recusa, com
    código 1 e a lista de pendências, se alguma remissão a parágrafo dividido estiver
    sem escolha ("a", "b", "a,b", "todas" ou o número novo): nunca cita todas as
    partes por padrão. Intervalos vão do primeiro número novo do início ao último do
    fim. Ajusta "parágrafo"/"parágrafos" e o artigo ("o"/"os", "do"/"dos", "no"/"nos",
    "ao"/"aos", "pelo"/"pelos") e avisa quando o verbo seguinte pode precisar de
    ajuste.

Exemplos::

    verificar_remissoes.py conferir --parecer parecer.docx --anexo anexo.docx \\
        --minuta-oficial minuta.docx --minuta-revisada minuta_revisada.docx \\
        --comentarios minuta_revisada.docx --json remissoes.json
    verificar_remissoes.py mapear --antigo parecer_v30.docx --novo parecer_v31.md \\
        --em anexo.json --saida mapa.json
    verificar_remissoes.py renumerar --mapa mapa.json --entrada parecer_v31.md --saida parecer_v31_renum.md

Códigos de saída: 0 sem bloqueante (ou renumeração gravada), 1 com bloqueante (ou
renumeração recusada por pendência) e 2 em erro de uso ou de leitura.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exportar_comentarios as ec  # noqa: E402

# ---------------------------------------------------------------- expressões

_NUM = r"\d+(?!\d|[.,]\d|[º°ª])"
_ROM_PAR = r"(?-i:\(?[ivx]{1,6}\)?)(?!\w)"
_SEP = r"(?:\s*,\s*(?:e\s+)?|\s+(?:e|a|at[ée]|ou)\s+)"
_LISTA_PAR = rf"{_NUM}(?:\s*,\s*{_ROM_PAR})?(?:{_SEP}{_NUM}(?:\s*,\s*{_ROM_PAR})?)*"
PAR_REF_RE = re.compile(rf"(?<![\w.])(?P<kw>par[áa]grafos?|pars?\.)\s*(?P<lista>{_LISTA_PAR})", re.IGNORECASE)
# "parágrafo 2 do art. 17", "parágrafos 3 e 4 da Lei": parágrafo de norma, não do parecer.
LEI_DEPOIS_RE = re.compile(
    r"^\s*,?\s*(?:do|da|dos|das)\s+(?:art|lei|decreto|resolu|instru|in\b|estatuto|regimento|c[óo]digo|constitui|portaria)",
    re.IGNORECASE,
)

_NUM_ITEM = r"\d+(?!\d|\.\d)"
_INC_ITEM = r"(?:\s*,\s*(?-i:[IVXL]+)(?!\w))"
_LISTA_ITEM = rf"{_NUM_ITEM}{_INC_ITEM}?(?:{_SEP}{_NUM_ITEM}{_INC_ITEM}?)*"
ITEM_REF_RE = re.compile(rf"\b(?P<kw>itens|item)\s+(?P<lista>{_LISTA_ITEM})", re.IGNORECASE)
ITEM_FORA_RE = re.compile(
    r"^\s*,?\s*(?:d[oa]s?|n[oa]s?)\s+(?:Anexo\s+[IVX]+\b|formul[áa]rio|question[áa]rio|edital|termo|contrato|tabela"
    r"|quadro|cronograma|minuta|regulamento|sum[áa]rio|[íi]ndice|lei|decreto|resolu|instru|in\b|estatuto|regimento|portaria)",
    re.IGNORECASE,
)
ITEM_TITULO_RE = re.compile(r"^\s*Item\s+(\d+)\s*(?:[–—:-]|\.\s)", re.IGNORECASE)
ROTULO_ANEXO_RE = re.compile(r"^\s*(Classificação|Fundamento|Observação|Nota|Justificativa)\s*:", re.IGNORECASE)
PAR_LINHA_RE = re.compile(r"^\s*(\d+)\.\s+(.*\S)\s*$")

VERBOS_SINGULAR = ("cita", "remete", "considera", "admite", "confirma", "inclui", "menciona", "trata",
                   "fundamenta", "alcança", "diz")
ARTIGO_SINGULAR_RE = re.compile(r"\b(o|do|no|ao|pelo)\s+(par[áa]grafos|pars\.)(?=\s*\d)", re.IGNORECASE)
ARTIGO_PLURAL_RE = re.compile(r"\b(os|dos|nos|aos|pelos)\s+(par[áa]grafo|par\.)(?=\s*\d)", re.IGNORECASE)
VERBO_DEPOIS_RE = re.compile(rf"^\s*,?\s*(?:também\s+|ainda\s+)?({'|'.join(VERBOS_SINGULAR)})\b(?!-)", re.IGNORECASE)
PREPOSICAO_ANTES_RE = re.compile(r"\b(?:nos|dos|aos|pelos|em|entre|com|sobre|nestes|desses|destes|nesses)\s+$", re.IGNORECASE)
ARTIGO_ANTES_RE = re.compile(r"(?<!\w)(o|do|no|ao|pelo|os|dos|nos|aos|pelos)\s+$", re.IGNORECASE)

DIPLOMA_RE = re.compile(
    r"\b(?:Lei(?:\s+Complementar)?|Decreto(?:-Lei)?|IN|Instru[çc][ãa]o\s+Normativa|Estatuto(?:\s+Social)?"
    r"|Constitui[çc][ãa]o(?:\s+(?:Federal|Estadual|da\s+Rep[úu]blica))?|CRFB|CF|CR|Pol[íi]tica(?:\s+de\s+[A-ZÀ-Ú][\wÀ-ú]*)?"
    r"|Regimento(?:\s+Interno)?|CLT|LGPD|S[úu]mula(?:\s+Vinculante)?|Resolu[çc][ãa]o|C[óo]digo(?:\s+(?:Civil|Penal|Tribut[áa]rio"
    r"\s+Nacional|de\s+Processo\s+Civil|de\s+Defesa\s+do\s+Consumidor))?|CPC|CTN|CDC|Portaria|Delibera[çc][ãa]o"
    r"|Medida\s+Provis[óo]ria)\b"
    r"(?:\s+(?:Estadual|Federal|Municipal|Conjunta))?"
    r"(?:\s+(?:[A-Z]{2,}\s+)?n?[º°.]?\s*\d[\d./-]*\d)?"
)
ART_QUALQUER_RE = re.compile(r"\barts?\.\s*\d+", re.IGNORECASE)
CIT_ART_RE = re.compile(
    r"\bart\.\s*(?P<art>\d+)\s*[º°]?(?:-(?P<suf>[A-Z])\b)?"
    r"(?:\s*,\s*(?:(?P<pu>par[áa]grafo\s+[úu]nico)|§\s*(?P<par>\d+)\s*[º°]?)(?:\s*,\s*(?P<inc2>(?-i:[IVXLC]+))\b)?"
    r"|\s*,\s*(?P<inc>(?-i:[IVXLC]+))\b)?",
    re.IGNORECASE,
)
CIT_PAR_DO_ART_RE = re.compile(
    r"(?:§\s*(?P<par>\d+)\s*[º°]?|(?P<pu>par[áa]grafo\s+[úu]nico))\s+do\s+art\.\s*(?P<art>\d+)\s*[º°]?(?:-(?P<suf>[A-Z])\b)?",
    re.IGNORECASE,
)
ART_INICIO_RE = re.compile(r"^\s*Art(?:\.\s*|igo\s+|\s+)(\d+)\s*[º°]?(?:\s*-\s*([A-Z])\b)?", re.IGNORECASE)
PAR_INICIO_RE = re.compile(r"^\s*§\s*(\d+)\s*[º°]?")
PU_INICIO_RE = re.compile(r"^\s*Par[áa]grafo\s+[úu]nico\b", re.IGNORECASE)
INC_INICIO_RE = re.compile(r"^\s*([IVXLC]+)\s*(?:[–—-]|\.(?=\s))\s*\S")
ABREVIATURA_RE = re.compile(
    r"\b(?:arts?|incs?|als?|n|cf|p|pp|fls?|v|ex|op|cit|Min|Rel|Des|Dr|Dra|Sr|Sra|Prof|Profa|par|pars)$",
    re.IGNORECASE,
)
FIM_FRASE_RE = re.compile(r"\.(?=\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ\"“(]|\s*$)")


# ---------------------------------------------------------------- estruturas

@dataclass
class Unidade:
    local: str
    texto: str
    numero: int | None = None


@dataclass
class Achado:
    severidade: str  # bloqueante | alerta | info
    regra: str
    local: str
    mensagem: str
    trecho: str = ""


@dataclass
class Ref:
    inicio: int
    fim: int
    faixa: bool = False
    romano: str | None = None
    spans: tuple = ()  # posições (no texto) dos números da referência


@dataclass
class Remissao:
    ini: int
    fim: int
    kw: str
    kw_span: tuple
    lista: str
    refs: list

    @property
    def plural(self) -> bool:
        return len(self.refs) > 1 or any(r.faixa for r in self.refs)


ORDEM = {"bloqueante": 0, "alerta": 1, "info": 2}


# ---------------------------------------------------------------- leitura

def norm(t: str) -> str:
    return ec.norm(t)


def ler_unidades(path: Path) -> list[Unidade]:
    """Parágrafos de um .docx (visão aceita) ou linhas de um .md/.txt."""
    if path.suffix.lower() == ".docx":
        return [Unidade(f"{path.name}:parágrafo {p['indice'] + 1}", p["texto"]) for p in ec.ler_paragrafos(path) if p["texto"]]
    out = []
    for i, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if linha.strip():
            out.append(Unidade(f"{path.name}:linha {i}", norm(linha)))
    return out


def ler_parecer(path: Path) -> list[Unidade]:
    """Unidades do parecer; as numeradas trazem o número do parágrafo."""
    if path.suffix.lower() == ".docx":
        out = []
        for p in ec.ler_paragrafos(path):
            if not p["texto"]:
                continue
            if p["numero"]:
                out.append(Unidade(f"parecer § {p['numero']}", p["texto"], p["numero"]))
            else:
                out.append(Unidade(f"parecer, parágrafo sem número {p['indice'] + 1}", p["texto"]))
        return out
    out = []
    for i, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        m = PAR_LINHA_RE.match(linha)
        if m:
            n = int(m.group(1))
            out.append(Unidade(f"parecer § {n}", norm(m.group(2)), n))
        elif linha.strip():
            out.append(Unidade(f"parecer, linha {i}", norm(linha)))
    return out


def numerados(unidades: list[Unidade]) -> dict[int, str]:
    out: dict[int, str] = {}
    for u in unidades:
        if u.numero is not None:
            out.setdefault(u.numero, u.texto)
    return out


def ler_anexo(path: Path) -> tuple[dict[int, str], list[Unidade]]:
    """Itens do Anexo (número -> título) e as linhas, rotuladas pelo item a que pertencem."""
    itens: dict[int, str] = {}
    linhas: list[Unidade] = []
    atual: int | None = None
    for u in ler_unidades(path):
        m = ITEM_TITULO_RE.match(u.texto)
        if m:
            atual = int(m.group(1))
            itens.setdefault(atual, u.texto)
            continue  # a linha de título define o item; não é remissão
        rot = ROTULO_ANEXO_RE.match(u.texto)
        onde = f"Anexo, item {atual}" if atual is not None else "Anexo, antes do primeiro item"
        if rot:
            onde += f" ({rot.group(1)})"
        linhas.append(Unidade(f"{onde} — {u.local}", u.texto))
    return itens, linhas


# ---------------------------------------------------------------- remissões

def _refs(lista: str, base: int, romano_rx: str) -> list[Ref]:
    refs: list[Ref] = []
    faixa = False
    for t in re.finditer(rf"\d+|at[ée]\b|\bou\b|{romano_rx}|\be\b|\ba\b|,", lista):
        tok = t.group(0)
        if tok.isdigit():
            n = int(tok)
            span = (base + t.start(), base + t.end())
            if faixa and refs:
                refs[-1].fim = n
                refs[-1].faixa = True
                refs[-1].spans = refs[-1].spans + (span,)
            else:
                refs.append(Ref(n, n, spans=(span,)))
            faixa = False
        elif tok.lower() in ("a", "até", "ate"):
            faixa = True
        elif re.fullmatch(romano_rx, tok) and refs and tok not in (",",):
            refs[-1].romano = tok.strip("()")
    return refs


def remissoes_paragrafo(texto: str) -> list[Remissao]:
    """Remissões a parágrafos do próprio documento ("parágrafo 12", "pars. 93 e 94", "parágrafo 103, iii")."""
    out = []
    for m in PAR_REF_RE.finditer(texto):
        if LEI_DEPOIS_RE.match(texto[m.end():m.end() + 40]):
            continue
        refs = _refs(m.group("lista"), m.start("lista"), r"\(?[ivx]{1,6}\)?")
        out.append(Remissao(m.start(), m.end(), m.group("kw"), m.span("kw"), m.group("lista"), refs))
    return out


def remissoes_item(texto: str) -> list[Remissao]:
    """Remissões a itens do Anexo ("item 5", "itens 4 a 7", "item 54, V"); ignora "item 8.6" e itens de outros anexos."""
    out = []
    for m in ITEM_REF_RE.finditer(texto):
        if ITEM_FORA_RE.match(texto[m.end():m.end() + 40]):
            continue
        refs = _refs(m.group("lista"), m.start("lista"), r"[IVXL]+")
        out.append(Remissao(m.start(), m.end(), m.group("kw"), m.span("kw"), m.group("lista"), refs))
    return out


def problemas_concordancia(texto: str) -> list[tuple[str, str]]:
    """(trecho, mensagem) para concordância quebrada em remissões a parágrafos.

    Pega artigo singular com "parágrafos" ("O parágrafos 185 e 186"), artigo plural com
    "parágrafo" ("os parágrafo 5") e "(os) parágrafos X e Y" seguido de verbo no
    singular ("admite", "cita"...). Contrações com preposição ("nos parágrafos 3 e 4,
    trata-se") não contam como sujeito.
    """
    out = []
    for m in ARTIGO_SINGULAR_RE.finditer(texto):
        out.append((texto[m.start():m.end() + 12].strip(), f"artigo singular «{m.group(1)}» com «{m.group(2)}»: usar o plural"))
    for m in ARTIGO_PLURAL_RE.finditer(texto):
        out.append((texto[m.start():m.end() + 12].strip(), f"artigo plural «{m.group(1)}» com «{m.group(2)}»: usar o singular"))
    for r in remissoes_paragrafo(texto):
        if not (r.kw.lower().endswith("s") or r.kw.lower().endswith("s.")) and not r.plural:
            continue
        if PREPOSICAO_ANTES_RE.search(texto[max(0, r.ini - 20):r.ini]):
            continue
        v = VERBO_DEPOIS_RE.match(texto[r.fim:r.fim + 40])
        if v:
            out.append((texto[r.ini:r.fim + v.end()].strip(),
                        f"remissão a mais de um parágrafo seguida de verbo no singular «{v.group(1)}»: concordar no plural"))
    return out


def _fronteiras(texto: str) -> tuple[list[int], list[int]]:
    """Posições que abrem e fecham uma oração: ';', parênteses e ponto final que não é abreviatura."""
    abre, fecha = [], []
    for i, ch in enumerate(texto):
        if ch == ";":
            abre.append(i)
            fecha.append(i)
        elif ch == "(":
            abre.append(i)
        elif ch == ")":
            abre.append(i)
            fecha.append(i)
    for m in FIM_FRASE_RE.finditer(texto):
        if not ABREVIATURA_RE.search(texto[max(0, m.start() - 6):m.start()]):
            abre.append(m.start())
            fecha.append(m.start())
    return sorted(abre), sorted(fecha)


def segmento(texto: str, ini: int, fim: int, fronteiras: tuple[list[int], list[int]] | None = None) -> str:
    """Oração ou parêntese que contém texto[ini:fim]: até o ';', ')' ou ponto final mais próximo de cada lado."""
    abre, fecha = fronteiras or _fronteiras(texto)
    a = max((p for p in abre if p < ini), default=-1) + 1
    b = min((p for p in fecha if p >= fim), default=len(texto))
    return texto[a:b]


def oracao(texto: str, ini: int, fim: int) -> str:
    """Frase da remissão (entre pontos finais ou ';'), sem o número do parágrafo no início."""
    marcas = [i for i, ch in enumerate(texto) if ch == ";"]
    marcas += [m.start() for m in FIM_FRASE_RE.finditer(texto) if not ABREVIATURA_RE.search(texto[max(0, m.start() - 6):m.start()])]
    a = max((p for p in marcas if p < ini), default=-1) + 1
    b = min((p for p in marcas if p >= fim), default=len(texto) - 1) + 1
    return re.sub(r"^\d+\.\s+", "", norm(texto[a:b]))


# ---------------------------------------------------------------- minuta

def estrutura_minuta(unidades: list[Unidade]) -> set[tuple]:
    """Dispositivos da minuta: ('art', a), ('par', a, n), ('pu', a), ('inc', a, contexto, romano)."""
    s: set[tuple] = set()
    art: str | None = None
    ctx: str | None = None
    for u in unidades:
        t = u.texto
        m = ART_INICIO_RE.match(t)
        if m:
            art = m.group(1) + (f"-{m.group(2).upper()}" if m.group(2) else "")
            ctx = None
            s.add(("art", art))
            continue
        if art is None:
            continue
        m = PAR_INICIO_RE.match(t)
        if m:
            ctx = f"§{int(m.group(1))}"
            s.add(("par", art, int(m.group(1))))
            continue
        if PU_INICIO_RE.match(t):
            ctx = "pu"
            s.add(("pu", art))
            continue
        m = INC_INICIO_RE.match(t)
        if m:
            s.add(("inc", art, ctx, m.group(1)))
    return s


def _ordinal(n: str) -> str:
    """Rótulo de artigo ou parágrafo como se escreve: ordinal até o 9 ("art. 2º"), cardinal depois ("art. 10")."""
    num, _, suf = n.partition("-")
    return (f"{num}º" if int(num) < 10 else num) + (f"-{suf}" if suf else "")


def _dispositivo(art: str, par: str | None, pu: bool, inc: str | None) -> tuple[tuple, str]:
    rot = f"art. {_ordinal(art)}" + (", parágrafo único" if pu else (f", § {_ordinal(str(int(par)))}" if par else ""))
    if inc:
        ctx = "pu" if pu else (f"§{int(par)}" if par else None)
        return ("inc", art, ctx, inc), f"{rot}, {inc}"
    if pu:
        return ("pu", art), rot
    if par:
        return ("par", art, int(par)), rot
    return ("art", art), rot


_CADEIA_DEPOIS_RE = re.compile(
    r"^(?:[\s,§º°\d]|\b(?-i:[IVXLC]+)\b|\be\b|par[áa]grafos?\s+[úu]nico|caput|incisos?|al[íi]neas?\s+[a-z]\b)*?"
    r"\b(?:d[aoe]s?|n[ao]s?)\s+",
    re.IGNORECASE,
)


def diploma_da_citacao(texto: str, ini: int, fim: int) -> str | None:
    """Diploma preso à citação: logo antes ("Lei nº 15.177/2025, art. 5º") ou logo depois da cadeia de
    dispositivos ("art. 5º, § 2º, I, da Lei nº 13.303/2016", "art. 22 do Estatuto")."""
    depois = texto[fim:fim + 120]
    m = _CADEIA_DEPOIS_RE.match(depois)
    if m:
        d = DIPLOMA_RE.match(depois, m.end())
        if d:
            return d.group(0)
    antes = texto[max(0, ini - 120):ini]
    for d in DIPLOMA_RE.finditer(antes):
        if re.fullmatch(r"\s*,\s*", antes[d.end():]):
            return d.group(0)
    return None


def citacoes_dispositivo(texto: str) -> list[tuple[int, int, tuple, str]]:
    """Citações simples a dispositivo: (ini, fim, chave, rótulo)."""
    out = []
    ocupados: list[tuple[int, int]] = []
    for m in CIT_PAR_DO_ART_RE.finditer(texto):
        art = m.group("art") + (f"-{m.group('suf')}" if m.group("suf") else "")
        chave, rot = _dispositivo(art, m.group("par"), bool(m.group("pu")), None)
        out.append((m.start(), m.end(), chave, rot))
        ocupados.append(m.span())
    for m in CIT_ART_RE.finditer(texto):
        if any(a <= m.start() < b for a, b in ocupados):
            continue
        art = m.group("art") + (f"-{m.group('suf')}" if m.group("suf") else "")
        chave, rot = _dispositivo(art, m.group("par"), bool(m.group("pu")), m.group("inc2") or m.group("inc"))
        out.append((m.start(), m.end(), chave, rot))
    return sorted(out)


# ---------------------------------------------------------------- conferir

def _conferir_paragrafos(u: Unidade, existentes: dict[int, str], total: int) -> list[Achado]:
    out = []
    for r in remissoes_paragrafo(u.texto):
        trecho = u.texto[r.ini:r.fim]
        for ref in r.refs:
            if ref.faixa and ref.fim < ref.inicio:
                out.append(Achado("bloqueante", "intervalo_invertido", u.local,
                                  f"«{trecho}»: intervalo {ref.inicio} a {ref.fim} invertido", trecho))
                continue
            for n in sorted({ref.inicio, ref.fim}):
                if n not in existentes:
                    out.append(Achado("bloqueante", "remissao_paragrafo", u.local,
                                      f"«{trecho}» aponta para o parágrafo {n}, que não existe (o parecer tem {total})", trecho))
            if ref.romano and ref.inicio in existentes:
                if not re.search(rf"(?<!\w){re.escape(ref.romano)}\)", existentes[ref.inicio]):
                    out.append(Achado("bloqueante", "numeral_romano", u.local,
                                      f"«{trecho}»: o parágrafo {ref.inicio} não tem «({ref.romano})»", trecho))
    for trecho, msg in problemas_concordancia(u.texto):
        out.append(Achado("alerta", "concordancia", u.local, msg, trecho))
    return out


def _conferir_itens(u: Unidade, itens: dict[int, str]) -> list[Achado]:
    out = []
    maior = max(itens) if itens else 0
    for r in remissoes_item(u.texto):
        trecho = u.texto[r.ini:r.fim]
        for ref in r.refs:
            if ref.faixa and ref.fim < ref.inicio:
                out.append(Achado("bloqueante", "intervalo_invertido", u.local,
                                  f"«{trecho}»: intervalo de itens {ref.inicio} a {ref.fim} invertido", trecho))
                continue
            faltam = [n for n in (range(ref.inicio, ref.fim + 1) if ref.faixa else [ref.inicio]) if n not in itens]
            for n in faltam:
                out.append(Achado("bloqueante", "remissao_item", u.local,
                                  f"«{trecho}» aponta para o item {n} do Anexo, que não existe (último item: {maior})", trecho))
    return out


def _conferir_dispositivos(u: Unidade, oficial: set[tuple] | None, revisada: set[tuple] | None) -> list[Achado]:
    out = []
    fr = _fronteiras(u.texto)
    if oficial:
        for ini, fim, chave, rot in citacoes_dispositivo(u.texto):
            seg = segmento(u.texto, ini, fim, fr)
            if "sugerid" in seg.lower() or chave in oficial:
                continue
            if re.search(r"inexistente[\s\"“]*$", u.texto[max(0, ini - 25):ini]):  # o próprio parecer aponta o dispositivo inexistente
                continue
            # diploma na mesma frase, antes do parêntese ("Estatuto Social (art. 22, § 1º)") ou depois de aposto
            # ("art. 140, § 1º (à época, parágrafo único), da Lei nº 6.404/1976"; "…, ambos da Lei…"): outra norma
            if DIPLOMA_RE.search(oracao(u.texto, ini, fim)):
                continue
            msg = f"«{rot}»: dispositivo inexistente na minuta oficial sem a marca 'sugerido'"
            if revisada is not None and chave in revisada:
                msg += " (existe só na minuta revisada)"
            # diploma citado antes no parágrafo: pode ser artigo dele, e não da minuta
            nivel = "info" if DIPLOMA_RE.search(u.texto[:ini]) else "alerta"
            if nivel == "info":
                msg += "; o parágrafo cita outra norma antes: conferir de qual diploma é"
            out.append(Achado(nivel, "dispositivo", u.local, msg, norm(seg)[:200]))
    diploma = None
    for m in ART_QUALQUER_RE.finditer(u.texto):
        seg = segmento(u.texto, m.start(), m.end(), fr)
        d = diploma_da_citacao(u.texto, m.start(), m.end())
        if d:
            diploma = d
        elif diploma:
            out.append(Achado("info", "diploma_implicito", u.local,
                              f"«{m.group(0)}»: artigo sem diploma depois de citar {diploma}: conferir se é da minuta",
                              norm(seg)[:200]))
    return out


def conferir(parecer: Path, anexo: Path | None = None, minuta_oficial: Path | None = None,
             minuta_revisada: Path | None = None, comentarios: list[Path] | None = None) -> dict:
    unidades = ler_parecer(parecer)
    existentes = numerados(unidades)
    total = max(existentes) if existentes else 0
    itens, linhas_anexo = ler_anexo(anexo) if anexo else ({}, [])
    oficial = estrutura_minuta(ler_unidades(minuta_oficial)) if minuta_oficial else None
    revisada = estrutura_minuta(ler_unidades(minuta_revisada)) if minuta_revisada else None
    coment: list[Unidade] = []
    for c in comentarios or []:
        for k in ec.ler_comentarios(c):
            coment.append(Unidade(f"comentário {k['id']} ({k['autor'] or 'sem autor'}) — {c.name}", k["texto"]))

    achados: list[Achado] = []
    if not existentes:
        achados.append(Achado("bloqueante", "remissao_paragrafo", "parecer", "nenhum parágrafo numerado encontrado no parecer"))
    if oficial is not None and not any(k[0] == "art" for k in oficial):
        achados.append(Achado("info", "dispositivo", "minuta oficial",
                              "nenhum artigo reconhecido na minuta oficial; checagem de dispositivos omitida"))
        oficial = None
    for u in unidades + linhas_anexo + coment:
        achados += _conferir_paragrafos(u, existentes, total)
        if anexo:
            achados += _conferir_itens(u, itens)
    for u in unidades:
        achados += _conferir_dispositivos(u, oficial, revisada)

    contagem = {s: sum(a.severidade == s for a in achados) for s in ORDEM}
    return {
        "parecer": str(parecer),
        "paragrafos_numerados": len(existentes),
        "itens_anexo": sorted(itens),
        "dispositivos_minuta_oficial": len(oficial) if oficial else 0,
        "comentarios": len(coment),
        "remissoes_paragrafo": sum(len(remissoes_paragrafo(u.texto)) for u in unidades + linhas_anexo + coment),
        "contagem": contagem,
        "ok": contagem["bloqueante"] == 0,
        "achados": [asdict(a) for a in sorted(achados, key=lambda a: ORDEM[a.severidade])],
    }


def relatorio_conferir(r: dict) -> str:
    linhas = [
        f"REMISSÕES — {Path(r['parecer']).name}",
        f"parágrafos numerados: {r['paragrafos_numerados']} | remissões a parágrafos: {r['remissoes_paragrafo']}"
        f" | itens do Anexo: {len(r['itens_anexo'])} | dispositivos na minuta oficial: {r['dispositivos_minuta_oficial']}"
        f" | comentários: {r['comentarios']}",
        "",
    ]
    for a in r["achados"]:
        linhas.append(f"[{a['severidade'].upper()}] {a['regra']} — {a['local']}: {a['mensagem']}")
    c = r["contagem"]
    linhas += ["", f"Resultado: {'OK' if r['ok'] else 'PENDÊNCIAS'} ({c['bloqueante']} bloqueantes, {c['alerta']} alertas, "
                   f"{c['info']} informativos)"]
    return "\n".join(linhas)


# ---------------------------------------------------------------- mapear

def _paragrafos_numerados(path: Path) -> list[tuple[int, str]]:
    return sorted(numerados(ler_parecer(path)).items())


def _norm_mapa(texto: str) -> list[str]:
    t = PAR_REF_RE.sub(" ", texto)
    return re.findall(r"\w+", t.lower())


def _telhas(palavras: list[str]) -> set[tuple[str, ...]]:
    if len(palavras) < 3:
        return {(p,) for p in palavras}
    return {tuple(palavras[i:i + 3]) for i in range(len(palavras) - 2)}


def contencao(parte: list[str], todo: list[str]) -> float:
    """Quanto de ``parte`` está em ``todo`` (trigramas de palavras); difflib desempata textos curtos."""
    if not parte:
        return 0.0
    a, b = _telhas(parte), _telhas(todo)
    c = len(a & b) / len(a)
    if c < 0.9 and (c >= 0.25 or len(parte) < 12):  # palavra trocada derruba três trigramas: difflib confirma
        sm = difflib.SequenceMatcher(None, parte, todo, autojunk=False)
        c = max(c, sum(bl.size for bl in sm.get_matching_blocks()) / len(parte))
    return c


def alinhar(antigos: list[tuple[int, str]], novos: list[tuple[int, str]], limiar: float = 0.6,
            janela: int = 12) -> dict[int, list[int]]:
    """Mapa número antigo -> números novos, em ordem; um antigo pode virar vários novos (divisão)."""
    pa = [_norm_mapa(t) for _, t in antigos]
    pn = [_norm_mapa(t) for _, t in novos]
    mapa: dict[int, list[int]] = {n: [] for n, _ in antigos}
    origem: dict[int, int] = {}  # índice novo -> índice antigo
    p = 0
    for j in range(len(novos)):
        melhor, alvo = 0.0, None
        for i in range(p, min(len(antigos), p + janela)):
            c = contencao(pn[j], pa[i]) - 0.01 * (i - p)
            if c > melhor:
                melhor, alvo = c, i
        if alvo is not None and melhor >= limiar:
            mapa[antigos[alvo][0]].append(novos[j][0])
            origem[j] = alvo
            p = alvo
    # fusões: antigo sem destino cujo texto está quase todo num novo vizinho
    ultimo = -1
    for i, (n, _) in enumerate(antigos):
        if mapa[n]:
            ultimo = max(j for j, k in origem.items() if k == i)
            continue
        for j in range(max(0, ultimo), min(len(novos), ultimo + 4)):
            if contencao(pa[i], pn[j]) >= 0.8:
                mapa[n] = [novos[j][0]]
                ultimo = j
                break
    return mapa


def _primeiras(texto: str, n: int = 30) -> str:
    ws = texto.split()
    return " ".join(ws[:n]) + (" …" if len(ws) > n else "")


def _unidades_json(obj, nome: str, caminho: str = "$"):
    """(local, texto) dos campos de texto e (local, lista) das listas ``paragrafos_parecer``."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            sub = f"{caminho}.{k}"
            if k == "paragrafos_parecer" and isinstance(v, list) and all(isinstance(x, int) for x in v):
                yield "lista", f"{nome}:{sub}", v
            else:
                yield from _unidades_json(v, nome, sub)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _unidades_json(v, nome, f"{caminho}[{i}]")
    elif isinstance(obj, str):
        yield "texto", f"{nome}:{caminho}", obj


def _ocorrencias(path: Path):
    """(local, contexto, antigo, romano, faixa) de cada número citado em remissão a parágrafo."""
    if path.suffix.lower() == ".json":
        fontes = list(_unidades_json(json.loads(path.read_text(encoding="utf-8")), path.name))
    elif path.suffix.lower() == ".docx":
        fontes = [("texto", u.local, u.texto) for u in ler_unidades(path)]
    else:
        fontes = [("texto", f"{path.name}:linha {i}", linha)
                  for i, linha in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1) if linha.strip()]
    for tipo, local, valor in fontes:
        if tipo == "lista":
            ctx = f"paragrafos_parecer = {valor}"
            for n in valor:
                yield local, ctx, n, None, False
            continue
        for r in remissoes_paragrafo(valor):
            ctx = oracao(valor, r.ini, r.fim)
            for ref in r.refs:
                yield local, ctx, ref.inicio, ref.romano, ref.faixa
                if ref.faixa:
                    yield local, ctx, ref.fim, None, True


def mapear(antigo: Path, novo: Path, em: list[Path] | None = None) -> dict:
    antigos = _paragrafos_numerados(antigo)
    novos = _paragrafos_numerados(novo)
    mapa = alinhar(antigos, novos)
    texto_novo = dict(novos)
    destinos = {x for v in mapa.values() for x in v}
    decisoes = []
    vistos: dict[tuple[str, str, int], int] = {}
    for path in [novo, *(em or [])]:
        for local, ctx, n, romano, faixa in _ocorrencias(path):
            alvos = mapa.get(n)
            if alvos is None or len(alvos) == 1 or (faixa and alvos):
                continue  # fora do mapa, sem divisão, ou ponta de intervalo (vai do primeiro ao último)
            ordem = vistos.get((path.name, ctx, n), 0)
            vistos[(path.name, ctx, n)] = ordem + 1
            d = {
                "id": f"d{len(decisoes) + 1}",
                "local": local,
                "contexto": ctx,
                "antigo": n,
                "ordem": ordem,
                "partes": [{"opcao": chr(ord("a") + k), "numero": x, "inicio": _primeiras(texto_novo.get(x, ""))}
                           for k, x in enumerate(alvos)],
                "escolha": None,
            }
            if not alvos:
                d["nota"] = "parágrafo antigo suprimido: indicar em 'escolha' o número novo"
            if romano:
                d["romano"] = romano
                com = [p["opcao"] for p in d["partes"] if re.search(rf"(?<!\w){re.escape(romano)}\)", texto_novo.get(p["numero"], ""))]
                if len(com) == 1:
                    d["sugestao"] = com[0]
            decisoes.append(d)
    return {
        "antigo": str(antigo),
        "novo": str(novo),
        "mapa": {str(k): v for k, v in mapa.items()},
        "divididos": [k for k, v in mapa.items() if len(v) > 1],
        "suprimidos": [k for k, v in mapa.items() if not v],
        "novos_sem_origem": [n for n, _ in novos if n not in destinos],
        "decisoes": decisoes,
    }


# ---------------------------------------------------------------- renumerar

class Renumerador:
    def __init__(self, dados: dict):
        self.mapa = {int(k): list(v) for k, v in dados.get("mapa", {}).items()}
        self.decisoes = dados.get("decisoes", [])
        self.pendencias: list[dict] = []
        self.avisos: list[dict] = []
        self.convertidas = 0
        self._ordem: dict[tuple[str, int], int] = {}

    def _decisao(self, local: str, ctx: str, n: int) -> dict | None:
        """Decisão do mapa para esta remissão: mesma oração e mesmo número antigo (e mesma ordem na oração)."""
        ordem = self._ordem.get((ctx, n), 0)
        self._ordem[(ctx, n)] = ordem + 1
        cands = [d for d in self.decisoes if d.get("antigo") == n and d.get("contexto") == ctx]
        arquivo = local.split(":")[0]
        for filtro in (lambda d: d.get("local", "").split(":")[0] == arquivo,
                       lambda d: d.get("ordem", 0) == ordem,
                       lambda d: d.get("local") == local):
            if len(cands) > 1:
                cands = [d for d in cands if filtro(d)] or cands
        if len(cands) > 1 and len({json.dumps(d.get("escolha")) for d in cands}) > 1:
            return {"conflito": True}
        return cands[0] if cands else None

    def _resolver(self, local: str, ctx: str, n: int, alvos: list[int], motivo_vazio: str) -> list[int] | None:
        d = self._decisao(local, ctx, n)
        escolha = d.get("escolha") if d else None
        if d and d.get("conflito"):
            motivo = "decisões conflitantes para a mesma remissão"
        elif escolha in (None, "", []):
            motivo = motivo_vazio
        else:
            out = self._aplicar_escolha(escolha, alvos)
            if out:
                return out
            motivo = f"escolha inválida: {escolha!r}"
        self.pendencias.append({"local": local, "contexto": ctx, "antigo": n, "partes": alvos, "motivo": motivo,
                                "decisao": d.get("id") if d and not d.get("conflito") else None})
        return None

    def destino(self, local: str, ctx: str, n: int) -> list[int] | None:
        """Números novos para o antigo ``n`` citado sozinho; None quando falta decisão."""
        alvos = self.mapa.get(n)
        if alvos is None:
            self.avisos.append({"local": local, "mensagem": f"parágrafo antigo {n} fora do mapa: mantido", "contexto": ctx})
            return [n]
        if len(alvos) == 1:
            return alvos
        return self._resolver(local, ctx, n, alvos, "parágrafo antigo dividido sem escolha" if alvos
                              else "parágrafo antigo suprimido sem número novo")

    @staticmethod
    def _aplicar_escolha(escolha, alvos: list[int]) -> list[int]:
        if isinstance(escolha, bool):
            return []
        if isinstance(escolha, int):
            return [escolha]
        if isinstance(escolha, list) and escolha and all(isinstance(x, int) for x in escolha):
            return list(escolha)
        if not isinstance(escolha, str):
            return []
        e = escolha.strip().lower()
        if e == "todas":
            return list(alvos)
        if re.fullmatch(r"\d+", e):
            return [int(e)]
        if not re.fullmatch(r"[a-z](?:\s*(?:,|\be\b)\s*[a-z])*", e):
            return []
        idx = [ord(c) - ord("a") for c in re.findall(r"\b[a-z]\b", re.sub(r"\be\b", ",", e))]
        if not idx or any(i < 0 or i >= len(alvos) for i in idx):
            return []
        return [alvos[i] for i in idx]

    def ponta(self, local: str, ctx: str, n: int, inicio: bool) -> int | None:
        """Ponta de intervalo: o primeiro número novo do início ou o último do fim."""
        alvos = self.mapa.get(n)
        if alvos is None:
            return n
        if alvos:
            return alvos[0] if inicio else alvos[-1]
        ds = self._resolver(local, ctx, n, [], "ponta de intervalo suprimida na versão nova")
        return (ds[0] if inicio else ds[-1]) if ds else None

    def texto(self, valor: str, local: str) -> str:
        trocas = []
        for r in remissoes_paragrafo(valor):
            ctx = oracao(valor, r.ini, r.fim)
            itens: list[tuple] = []  # ("n", numero, romano) | ("f", inicio, fim)
            numeros: list[int] = []  # um por número escrito, quando a forma não muda
            mesma_forma, ok = True, True
            for ref in r.refs:
                if ref.faixa:
                    a = self.ponta(local, ctx, ref.inicio, True)
                    b = self.ponta(local, ctx, ref.fim, False)
                    if a is None or b is None:
                        ok = False
                    elif a == b:
                        itens.append(("n", a, ref.romano))
                        mesma_forma = False
                    else:
                        itens.append(("f", a, b))
                        numeros += [a, b]
                else:
                    ds = self.destino(local, ctx, ref.inicio)
                    if ds is None:
                        ok = False
                        continue
                    mesma_forma = mesma_forma and len(ds) == 1
                    itens += [("n", x, ref.romano if k == len(ds) - 1 else None) for k, x in enumerate(ds)]
                    numeros += ds[:1]
            if not ok:
                continue
            base = r.kw_span[1]
            cauda = valor[base:r.fim]  # espaço + lista
            espaco = cauda[:len(cauda) - len(cauda.lstrip())]
            if mesma_forma:  # troca só os números, preservando separadores e numerais romanos
                spans = [sp for ref in r.refs for sp in ref.spans]
                for (s0, s1), x in sorted(zip(spans, numeros), reverse=True):
                    cauda = cauda[:s0 - base] + str(x) + cauda[s1 - base:]
            else:
                partes = [f"{i[1]} a {i[2]}" if i[0] == "f" else f"{i[1]}" + (f", {i[2]}" if i[2] else "") for i in itens]
                cauda = espaco + (partes[0] if len(partes) == 1 else ", ".join(partes[:-1]) + " e " + partes[-1])
            plural = len(itens) > 1 or any(i[0] == "f" for i in itens)
            kw = _flexionar_kw(r.kw, plural)
            ini, prefixo = r.ini, ""
            art = ARTIGO_ANTES_RE.search(valor[:r.ini])
            if kw != r.kw and art:
                ini = art.start(1)
                prefixo = _flexionar_artigo(art.group(1), plural) + valor[art.end(1):r.ini]
            antes = valor[ini:r.fim]
            depois = prefixo + (kw if kw != r.kw else valor[r.ini:base]) + cauda
            if depois == antes:
                continue
            self.convertidas += 1
            if kw != r.kw:
                self.avisos.append({"local": local, "antes": antes, "depois": depois,
                                    "seguinte": " ".join(valor[r.fim:].split()[:3]),
                                    "mensagem": "número da remissão mudou: conferir a concordância do verbo seguinte"})
            trocas.append((ini, r.fim, depois))
        for ini, fim, depois in sorted(trocas, reverse=True):
            valor = valor[:ini] + depois + valor[fim:]
        return valor

    def lista(self, valor: list[int], local: str) -> list[int]:
        ctx = f"paragrafos_parecer = {valor}"
        out: list[int] = []
        for n in valor:
            ds = self.destino(local, ctx, n)
            for x in ds or []:
                if x not in out:
                    out.append(x)
        if out != valor:
            self.convertidas += 1
        return out

    def json(self, obj, nome: str, caminho: str = "$"):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                sub = f"{caminho}.{k}"
                if k == "paragrafos_parecer" and isinstance(v, list) and all(isinstance(x, int) for x in v):
                    out[k] = self.lista(v, f"{nome}:{sub}")
                else:
                    out[k] = self.json(v, nome, sub)
            return out
        if isinstance(obj, list):
            return [self.json(v, nome, f"{caminho}[{i}]") for i, v in enumerate(obj)]
        if isinstance(obj, str):
            return self.texto(obj, f"{nome}:{caminho}")
        return obj


def _caixa(modelo: str, palavra: str) -> str:
    return palavra[:1].upper() + palavra[1:] if modelo[:1].isupper() else palavra


def _flexionar_kw(kw: str, plural: bool) -> str:
    base = kw.lower()
    if base in ("par.", "pars."):
        alvo = "pars." if plural else "par."
    else:
        acento = "á" if "á" in base else "a"
        alvo = f"par{acento}grafos" if plural else f"par{acento}grafo"
    return _caixa(kw, alvo)


ARTIGOS = {"o": "os", "do": "dos", "no": "nos", "ao": "aos", "pelo": "pelos"}


def _flexionar_artigo(art: str, plural: bool) -> str:
    base = art.lower()
    if plural:
        alvo = ARTIGOS.get(base, base)
    else:
        alvo = {v: k for k, v in ARTIGOS.items()}.get(base, base)
    return _caixa(art, alvo)


def renumerar(dados: dict, entrada: Path) -> tuple[str, Renumerador]:
    r = Renumerador(dados)
    if entrada.suffix.lower() == ".json":
        obj = r.json(json.loads(entrada.read_text(encoding="utf-8")), entrada.name)
        return json.dumps(obj, ensure_ascii=False, indent=1) + "\n", r
    linhas = entrada.read_text(encoding="utf-8").split("\n")
    out = [r.texto(linha, f"{entrada.name}:linha {i}") if linha.strip() else linha for i, linha in enumerate(linhas, start=1)]
    return "\n".join(out), r


# ---------------------------------------------------------------- CLI

def _existe(*paths: Path | None) -> str | None:
    for p in paths:
        if p is not None and not p.exists():
            return f"arquivo não encontrado: {p}"
    return None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("conferir", help="confere remissões a parágrafos, itens do Anexo e dispositivos")
    c.add_argument("--parecer", type=Path, required=True, help="parecer em .docx, .md ou .txt")
    c.add_argument("--anexo", type=Path, help="Anexo de Redações Sugeridas (.docx ou .txt)")
    c.add_argument("--minuta-oficial", type=Path)
    c.add_argument("--minuta-revisada", type=Path)
    c.add_argument("--comentarios", type=Path, nargs="+", help=".docx cujos comentários também são conferidos")
    c.add_argument("--json", type=Path, help="grava o relatório completo")
    m = sub.add_parser("mapear", help="alinha parecer antigo e novo e lista as decisões de remissão")
    m.add_argument("--antigo", type=Path, required=True)
    m.add_argument("--novo", type=Path, required=True)
    m.add_argument("--em", type=Path, nargs="+", help="outros arquivos com remissões ao parecer (.docx, .txt, .md, .json)")
    m.add_argument("--saida", type=Path, help="grava o mapa em JSON; padrão: saída padrão")
    r = sub.add_parser("renumerar", help="aplica o mapa (com as escolhas preenchidas) a um texto ou JSON")
    r.add_argument("--mapa", type=Path, required=True)
    r.add_argument("--entrada", type=Path, required=True, help=".txt, .md ou .json")
    r.add_argument("--saida", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "conferir":
        erro = _existe(args.parecer, args.anexo, args.minuta_oficial, args.minuta_revisada, *(args.comentarios or []))
        if erro:
            print(erro, file=sys.stderr)
            return 2
        res = conferir(args.parecer, args.anexo, args.minuta_oficial, args.minuta_revisada, args.comentarios)
        if args.json:
            args.json.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(relatorio_conferir(res))
        return 0 if res["ok"] else 1

    if args.cmd == "mapear":
        erro = _existe(args.antigo, args.novo, *(args.em or []))
        if erro:
            print(erro, file=sys.stderr)
            return 2
        res = mapear(args.antigo, args.novo, args.em)
        texto = json.dumps(res, ensure_ascii=False, indent=1) + "\n"
        if args.saida:
            args.saida.write_text(texto, encoding="utf-8")
            print(f"mapa gravado em {args.saida}: {len(res['mapa'])} parágrafos antigos, divididos {res['divididos'] or 'nenhum'}, "
                  f"suprimidos {res['suprimidos'] or 'nenhum'}, novos sem origem {res['novos_sem_origem'] or 'nenhum'}; "
                  f"{len(res['decisoes'])} decisões a preencher em 'escolha'")
        else:
            print(texto, end="")
        return 0

    erro = _existe(args.mapa, args.entrada)
    if erro:
        print(erro, file=sys.stderr)
        return 2
    if args.entrada.suffix.lower() not in (".txt", ".md", ".json"):
        print("--entrada deve ser .txt, .md ou .json", file=sys.stderr)
        return 2
    texto, rn = renumerar(json.loads(args.mapa.read_text(encoding="utf-8")), args.entrada)
    if rn.pendencias:
        print(f"RECUSADO: {len(rn.pendencias)} remissões sem decisão; nada foi gravado.")
        for p in rn.pendencias:
            partes = ", ".join(map(str, p["partes"])) or "nenhuma"
            print(f"- {p['local']} [{p['decisao'] or 'sem decisão no mapa'}]: parágrafo antigo {p['antigo']} "
                  f"(partes novas: {partes}) — {p['motivo']}. Oração: «{p['contexto'][:160]}»")
        return 1
    args.saida.write_text(texto, encoding="utf-8")
    print(f"{rn.convertidas} remissões convertidas; gravado em {args.saida}")
    for a in rn.avisos:
        if "antes" in a:
            print(f"- {a['local']}: «{a['antes']}» → «{a['depois']}» (seguinte: «{a['seguinte']}») — {a['mensagem']}")
        else:
            print(f"- {a['local']}: {a['mensagem']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
