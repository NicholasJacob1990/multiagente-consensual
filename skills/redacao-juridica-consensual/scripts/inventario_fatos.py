#!/usr/bin/env python3
"""Inventário de fatos entre duas versões de uma minuta: números, datas, páginas e citações acrescentados ou suprimidos.

A reescrita que funde parágrafos e "melhora a redação" é onde um valor, uma data
ou uma página entra sem fonte ou some sem que ninguém perceba. Este script extrai
de cada versão os dados verificáveis e lista o que é novo e o que desapareceu,
cada item com a frase em que aparece e uma coluna "fonte (página)" em branco,
para a nota de revisão.

Categorias extraídas (nesta ordem; o trecho já classificado não é reaproveitado):

- ``processo``: número de autos (CNJ, TJ, SEI "0000.01.0000001/2026-01");
- ``valor``: Cr$, Cz$, NCz$, R$, US$ com o número;
- ``percentual``: "64,73%", "10 %";
- ``medida``: área e comprimento ("10.500,00 m²", "2 ha", "20 m", "105 metros");
- ``data``: "16/11/2022", "14 de janeiro de 1971", "16 nov. 2022", "abril de 1985", "28 de novembro";
- ``periodo``: "1983–1987", "2019-2021";
- ``pagina``: "p. 244", "pp. 150–152", "pp. 64, 70 e 295" (um item por página ou intervalo);
- ``dispositivo``: "art. 2.038, § 1º, I, do Código Civil", "arts. 678 e 679", "§ 2º do art. 17";
- ``diploma``: "Lei nº 6.015/1973", "Provimento Conjunto nº 162/2026", "Decreto 1.234/2020";
- ``registro``: matrícula, transcrição, registro, inscrição, livro, folhas, protocolo,
  prenotação, lote, quadra, atos "R-11"/"AV-3" e documentos "SEI 100000001";
- ``identificador``: outro "X nº N" ("CI nº 108/2026", "execução fiscal nº 2621", "RE nº 81.930");
- ``prazo``: "30 dias", "2 anos";
- ``numero``: número com pontuação de milhar ou decimal ("2.683,80", "171,68");
- ``ano``: ano isolado de quatro dígitos ("em 1986").

Ficam de fora as remissões internas ("parágrafo 22", "parágrafos 86 a 88"), o número
do parágrafo ("12. ..."), chamadas de nota ("[^3]") e URLs.

Comparação: ACRÉSCIMO é o item cuja forma escrita não existe na anterior; se o mesmo
fato estava lá com outra forma ("16 de novembro de 2022" → "16/11/2022"), o item é
listado com a observação. SUPRESSÃO é o item da anterior cujo fato não aparece na
nova em forma nenhuma (a página 295 de "pp. 294–298" basta para "p. 295"; o ano
1983 de "1983–1987" basta para "1983").

Uso::

    inventario_fatos.py ANTERIOR NOVA [--md] [--json SAIDA]

``ANTERIOR`` e ``NOVA`` podem ser .md, .txt ou .docx (parágrafos do .docx, com as
alterações aceitas). ``--md`` imprime as tabelas em Markdown, prontas para a nota de
revisão; sem ele, a saída é texto corrido. Código de saída: 1 quando há supressão
(para chamar atenção), 0 quando não há e 2 em erro de uso ou de leitura.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402

MESES = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4, "maio": 5, "junho": 6, "julho": 7,
    "agosto": 8, "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}
MESES_ABREV = {"jan": 1, "fev": 2, "mar": 3, "abr": 4, "maio": 5, "jun": 6, "jul": 7, "ago": 8, "set": 9,
               "out": 10, "nov": 11, "dez": 12}
_MES = "|".join(sorted(MESES, key=len, reverse=True))
_MES_AB = "|".join(sorted(MESES_ABREV, key=len, reverse=True))
_TRACO = r"[–—-]"
_NUM = r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+(?:,\d+)?"
_ANO = r"(?:1[5-9]\d\d|20\d\d)"

URL_RE = re.compile(r"https?://\S+|www\.\S+")
NOTA_RE = re.compile(r"\[\^\d+\]")
REMISSAO_EXTRA_RE = re.compile(r"\bpars?\.\s*\d+(?:\s*(?:,|e|a)\s*\d+)*", re.IGNORECASE)
PREFIXO_PAR_RE = re.compile(r"^\s*\d+\.\s+")

DIPLOMA_NOMES = (r"Lei(?:\s+Complementar|\s+Delegada)?|Decreto(?:-Lei)?|Provimento(?:\s+Conjunto)?|Resolu[çc][ãa]o"
                 r"|Instru[çc][ãa]o\s+Normativa|Portaria|Medida\s+Provis[óo]ria|Emenda\s+Constitucional|Deliberação")
_ORD = r"\d+(?:\.\d+)*[º°ª]?(?:-[A-Z]{1,3})?"
_COMPL = (r"(?:\s*,\s*(?:§§?\s*\d+[º°]?(?:\s*(?:,|e|" + _TRACO + r")\s*\d+[º°]?)*|par[áa]grafo\s+[úu]nico|caput"
          r"|inc(?:iso)?s?\.?\s*[IVXLC]+\b|[IVXLC]+\b(?!\s*\.)|al[íi]neas?\s*[\"“]?[a-z]\b[\"”]?))*")
_DIPLOMA_REF = (r"(?:,?\s*(?:d[aoe]s?|desse|dessa|deste|desta)\s+(?:mesma\s+lei|(?:" + DIPLOMA_NOMES + r")\s+(?:n[º°.]?\s*)?\d[\d./]*\d"
                r"|C[óo]digo(?:\s+(?:Civil|de\s+Processo\s+Civil|Nacional\s+de\s+Normas|de\s+Normas(?:\s+mineiro)?"
                r"|Tribut[áa]rio\s+Nacional|Penal))?(?:\s+de\s+\d{4})?|Constitui[çc][ãa]o(?:\s+Federal|\s+da\s+Rep[úu]blica|\s+do\s+Estado)?"
                r"|CF|CC|CPC|CTN|LRP|RILC))?")

PADROES: list[tuple[str, re.Pattern]] = [
    ("processo", re.compile(r"\b\d{7}-\d{2}\.\d{4}\.\d\.\d{2}\.\d{4}\b|\b\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3}\b"
                            r"|\b\d{4}\.\d{2}\.\d{7}/\d{4}-\d{2}\b")),
    ("valor", re.compile(r"(?:NCz\$|Cz\$|Cr\$|CR\$|R\$|US\$|U\$)\s*(?:" + _NUM + r")(?:\s*(?:mil|milh(?:ão|ões)|bilh(?:ão|ões)))?")),
    ("percentual", re.compile(r"(?<![\d.,])(?:" + _NUM + r")\s*%")),
    ("medida", re.compile(r"(?<![\d.,])(?:(?:" + _NUM + r")\s*(?:,|\be\b|×|\bx\b)\s*)*(?:" + _NUM + r")\s*"
                          r"(?:m²|m2|km²|ha\b|hectares?\b|alqueires?\b|metros\s+quadrados\b|metros\b|m\b(?!\w))")),
    ("data", re.compile(r"\b\d{1,2}/\d{1,2}/(?:\d{4}|\d{2})\b"
                        r"|\b(?:\d{1,2}|1º)\s+de\s+(?:" + _MES + r")(?:\s+de\s+" + _ANO + r")?\b"
                        r"|\b\d{1,2}\s+(?:" + _MES_AB + r")\.?\s+" + _ANO + r"\b"
                        r"|\b(?:" + _MES + r")\s+de\s+" + _ANO + r"\b", re.IGNORECASE)),
    ("periodo", re.compile(r"\b" + _ANO + r"\s*" + _TRACO + r"\s*" + _ANO + r"\b")),
    ("pagina", re.compile(r"\bpp?\.\s*(?:\d+(?:\s*" + _TRACO + r"\s*\d+)?)(?:\s*(?:,|e)\s*\d+(?:\s*" + _TRACO + r"\s*\d+)?(?![\d.,]*\s*(?:m²|%)))*")),
    ("dispositivo", re.compile(r"\barts?\.\s*" + _ORD + r"(?:\s*(?:,|e|a|" + _TRACO + r")\s*" + _ORD + r")*" + _COMPL + _DIPLOMA_REF
                               + r"|(?:§§?\s*\d+[º°]?|par[áa]grafo\s+[úu]nico|inciso\s+[IVXLC]+|al[íi]nea\s+[\"“]?[a-z][\"”]?)"
                               + _COMPL + r"\s+d[oa]\s+art\.\s*" + _ORD + _DIPLOMA_REF)),
    ("diploma", re.compile(r"\b(?:" + DIPLOMA_NOMES + r")(?:\s+(?:CNJ|CNMP|CGJ|STF|STJ|TST|TSE|TJMG|TJ|AGE|RFB|[A-Z]{2,5}/[A-Z]{2}))?"
                           r"\s+(?:n[º°.]?\s*)?\d[\d./]*\d\b")),
    ("registro", re.compile(r"\b(?:SEIs?)\s+\d{6,}(?:\s*(?:,|e)\s*\d{6,})*"
                            r"|\b(?:R|AV|Av)[-.]\s?\d+\b"
                            r"|\b(?:[Mm]atr[íi]culas?|[Tt]ranscri[çc](?:ão|ões)|[Rr]egistros?|[Ii]nscri[çc](?:ão|ões)|[Ll]ivros?"
                            r"|[Pp]rotocolos?|[Pp]renota[çc](?:ão|ões)|[Ff]olhas?|fls?\.|[Ll]otes?|[Qq]uadras?)"
                            r"\s+(?:n[º°.]?\s*)?\d[\d.\-/]*(?:-?[A-Z]\b)?"
                            r"(?:\s*(?:,|e|a)\s*(?:n[º°.]?\s*)?\d[\d.\-/]*(?:-?[A-Z]\b)?)*")),
    ("identificador", re.compile(r"\b[\wÀ-ú][\w./À-ú]*\s+n[º°.]\s*\d[\d.\-/]*\d|\b[\wÀ-ú][\w./À-ú]*\s+n[º°.]\s*\d\b")),
    ("prazo", re.compile(r"\b\d+\s+(?:dias|meses|anos|horas)\b(?:\s+(?:úteis|corridos))?")),
    ("numero", re.compile(r"(?<![\w.,])\d{1,3}(?:\.\d{3})+(?:,\d+)?(?![\w.,]\d)|(?<![\w.,])\d+,\d+(?![\w,]\d)")),
    ("ano", re.compile(r"(?<![\w./-])" + _ANO + r"(?![\w/]|[.,]\d)")),
]


@dataclass
class Item:
    categoria: str
    literal: str
    chave: str
    requisitos: list[str]
    fornece: list[str]
    local: str
    contexto: str
    ocorrencias: int = 1
    locais: list[str] = field(default_factory=list)
    observacao: str = ""
    alternativas: list[list[str]] = field(default_factory=list)

    def presente_em(self, fornecidos: set[str]) -> bool:
        """O fato está presente quando todos os requisitos (ou todos os de uma alternativa) estão."""
        return any(all(r in fornecidos for r in reqs) for reqs in [self.requisitos, *self.alternativas])


# ---------------------------------------------------------------- normalização

def _num(s: str) -> str:
    """'2.683,80' -> '2683.80'; '10' -> '10'."""
    s = s.strip().replace(".", "").replace(",", ".")
    return s


def _limpa(s: str) -> str:
    s = re.sub(r"\s+", " ", s.replace("\u00a0", " ")).strip()
    return re.sub(r"\s*" + _TRACO + r"\s*", "–", s) if re.search(r"\d\s*" + _TRACO + r"\s*\d", s) else s


def _iso(d: int, m: int, a: int) -> str:
    return f"{a:04d}-{m:02d}-{d:02d}"


def _data(lit: str) -> tuple[list[str], list[str]]:
    """(requisitos, fornece) de uma data."""
    t = lit.lower()
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if m:
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        a = a + (1900 if a > 30 else 2000) if a < 100 else a
        k = _iso(d, mes, a)
        return [f"data:{k}"], [f"data:{k}", f"mes:{a:04d}-{mes:02d}", f"dm:{mes:02d}-{d:02d}", f"ano:{a}"]
    m = re.fullmatch(r"(\d{1,2}|1º)\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?", t)
    if m:
        d = 1 if m.group(1) == "1º" else int(m.group(1))
        mes = MESES[m.group(2)]
        if m.group(3):
            a = int(m.group(3))
            return [f"data:{_iso(d, mes, a)}"], [f"data:{_iso(d, mes, a)}", f"mes:{a:04d}-{mes:02d}", f"dm:{mes:02d}-{d:02d}", f"ano:{a}"]
        return [f"dm:{mes:02d}-{d:02d}"], [f"dm:{mes:02d}-{d:02d}"]
    m = re.fullmatch(r"(\d{1,2})\s+(\w+)\.?\s+(\d{4})", t)
    if m:
        d, mes, a = int(m.group(1)), MESES_ABREV[m.group(2)], int(m.group(3))
        return [f"data:{_iso(d, mes, a)}"], [f"data:{_iso(d, mes, a)}", f"mes:{a:04d}-{mes:02d}", f"dm:{mes:02d}-{d:02d}", f"ano:{a}"]
    m = re.fullmatch(r"(\w+)\s+de\s+(\d{4})", t)
    if m:
        mes, a = MESES[m.group(1)], int(m.group(2))
        return [f"mes:{a:04d}-{mes:02d}"], [f"mes:{a:04d}-{mes:02d}", f"ano:{a}"]
    return [f"data:{t}"], [f"data:{t}"]


def _paginas(lit: str) -> list[tuple[str, list[str], list[str]]]:
    """Um item por página ou intervalo: (literal canônico, requisitos, fornece)."""
    corpo = re.sub(r"^pp?\.\s*", "", lit)
    out = []
    for parte in re.split(r"\s*(?:,|\be\b)\s*", corpo):
        m = re.fullmatch(r"(\d+)(?:\s*" + _TRACO + r"\s*(\d+))?", parte.strip())
        if not m:
            continue
        a = int(m.group(1))
        b = int(m.group(2)) if m.group(2) else a
        if b < a or b - a > 300:
            b = a
        paginas = [f"pag:{x}" for x in range(a, b + 1)]
        canon = f"p. {a}" if a == b else f"pp. {a}–{b}"
        out.append((canon, paginas, paginas))
    return out


def _dispositivo(lit: str) -> tuple[list[str], list[str]]:
    """Requisitos de um dispositivo: cada artigo e cada complemento ligado a ele."""
    arts = re.findall(_ORD, re.split(r"\b(?:d[aoe]s?|desse|dessa|deste|desta)\s", lit)[0])
    m_art = re.search(r"\barts?\.\s*(" + _ORD + r"(?:\s*(?:,|e|a|" + _TRACO + r")\s*" + _ORD + r")*)", lit)
    if m_art:
        arts = re.findall(_ORD, m_art.group(1))
    arts = [a.replace(".", "").rstrip("º°ª") for a in arts]
    compl = []
    for c in re.findall(r"§§?\s*\d+[º°]?(?:\s*(?:,|e|" + _TRACO + r")\s*\d+[º°]?)*|par[áa]grafo\s+[úu]nico|inc(?:iso)?s?\.?\s*[IVXLC]+\b"
                        r"|(?<=,\s)[IVXLC]+\b|al[íi]neas?\s*[\"“]?[a-z]\b", lit):
        c = c.lower()
        if c.startswith("§"):
            compl += [f"§{x}" for x in re.findall(r"\d+", c)]
        elif c.startswith("par"):
            compl.append("pu")
        elif c.startswith("al"):
            compl.append("al" + c[-1])
        else:
            compl.append("inc" + re.sub(r"^inc(?:iso)?s?\.?\s*", "", c).upper())
    req = [f"art:{a}" for a in arts] + [f"art:{arts[0] if arts else '?'}:{c}" for c in compl]
    return req, req


def _singular(tipo: str) -> str:
    t = tipo.lower().rstrip(".")
    t = {"fls": "folha", "fl": "folha", "folhas": "folha", "transcrições": "transcrição", "inscrições": "inscrição",
         "prenotações": "prenotação"}.get(t, t)
    return t[:-1] if t.endswith("s") and t not in ("seis",) else t


def _registros(lit: str) -> list[tuple[str, list[str], list[str]]]:
    m = re.match(r"(SEIs?)\s+(.*)", lit)
    if m:
        return [(f"SEI {n}", [f"sei:{n}"], [f"sei:{n}"]) for n in re.findall(r"\d{6,}", m.group(2))]
    m = re.fullmatch(r"(R|AV|Av)[-.]\s?(\d+)", lit)
    if m:
        k = f"{m.group(1).upper()}-{m.group(2)}"
        return [(k, [f"ato:{k}"], [f"ato:{k}"])]
    m = re.match(r"(\S+)\s+(.*)", lit)
    if not m:
        return []
    tipo = _singular(m.group(1))
    corpo = m.group(2)
    nums = [n.rstrip(".-/") for n in re.findall(r"\d[\d.\-/]*(?:-?[A-Z]\b)?", corpo)]
    out = []
    if tipo in ("lote", "quadra") and re.search(r"\d\s+a\s+\d", corpo) and len(nums) == 2:
        a, b = int(nums[0]), int(nums[1])
        chaves = [f"{tipo}:{x}" for x in range(a, b + 1)] if 0 <= b - a <= 100 else [f"{tipo}:{a}-{b}"]
        return [(f"{tipo}s {nums[0]} a {nums[1]}", chaves, chaves)]
    for n in nums:
        norm = n.replace(".", "")
        if tipo in ("lote", "quadra") and norm.isdigit():
            norm = str(int(norm))
        rot = f"{tipo} nº {n}" if tipo in ("matrícula", "matricula", "transcrição", "registro", "inscrição", "protocolo",
                                            "prenotação") else f"{tipo} {n}"
        out.append((rot, [f"{tipo}:{norm}"], [f"{tipo}:{norm}"]))
    return out


def classificar(cat: str, lit: str) -> list[tuple[str, str, list[str], list[str]]]:
    """(literal canônico, chave literal, requisitos, fornece) de cada item contido no trecho."""
    lit = _limpa(lit)
    if cat == "pagina":
        return [(c, f"pagina:{c}", r, f) for c, r, f in _paginas(lit)]
    if cat == "registro":
        return [(c, f"registro:{c.lower()}", r, f) for c, r, f in _registros(lit)]
    if cat == "data":
        r, f = _data(lit)
        return [(lit, f"data:{lit.lower()}", r, f)]
    if cat == "periodo":
        a, b = re.findall(r"\d{4}", lit)
        k = f"periodo:{a}-{b}"
        return [(f"{a}–{b}", k, [k], [k, f"ano:{a}", f"ano:{b}"])]
    if cat == "ano":
        return [(lit, f"ano:{lit}", [f"ano:{lit}"], [f"ano:{lit}"])]
    if cat == "valor":
        m = re.match(r"(\S+?)\s*(\d.*)", lit)
        moeda, resto = (m.group(1), m.group(2)) if m else ("", lit)
        num = re.match(_NUM, resto)
        k = f"valor:{moeda.lower()}:{_num(num.group(0)) if num else resto}"
        return [(f"{moeda} {resto}", k, [k], [k, f"num:{_num(num.group(0))}" if num else k])]
    if cat == "percentual":
        v = _num(lit.rstrip("% "))
        return [(lit.replace(" %", "%"), f"pct:{v}", [f"pct:{v}"], [f"pct:{v}", f"num:{v}"])]
    if cat == "medida":
        m = re.fullmatch(r"(.*?)\s*(m²|m2|km²|ha|hectares?|alqueires?|metros\s+quadrados|metros|m)", lit)
        u = m.group(2).lower() if m else ""
        u = {"m2": "m²", "metros quadrados": "m²", "metros": "m", "hectare": "ha", "hectares": "ha"}.get(u, u)
        valores = re.findall(_NUM, m.group(1) if m else lit)
        if len(valores) > 1 and "×" not in lit and " x " not in lit:  # "105 e 100 metros": dois itens
            return [(f"{v} {u}", f"medida:{_num(v)}{u}", [f"medida:{_num(v)}{u}"], [f"medida:{_num(v)}{u}", f"num:{_num(v)}"])
                    for v in valores]
        chaves = [f"medida:{_num(v)}{u}" for v in valores]
        return [(lit, f"medida:{lit.lower()}", chaves, chaves + [f"num:{_num(v)}" for v in valores])]
    if cat == "dispositivo":
        r, f = _dispositivo(lit)
        return [(lit, f"dispositivo:{lit.lower()}", r, f)]
    if cat == "diploma":
        m = re.match(r"(.*?)\s+(?:n[º°.]?\s*)?(\d[\d./]*\d)$", lit)
        tipo = re.sub(r"\s+(?:CNJ|CNMP|CGJ|STF|STJ|TST|TSE|TJMG|TJ|AGE|RFB|[A-Z]{2,5}/[A-Z]{2})$", "",
                      re.sub(r"\s+", " ", m.group(1))).lower() if m else lit.lower()
        num = m.group(2).replace(".", "") if m else lit
        partes = num.split("/")
        if len(partes) == 2 and len(partes[1]) == 4:
            partes[1] = partes[1][2:]
        k = f"diploma:{tipo}:{'/'.join(partes)}"
        return [(lit, k, [k], [k, f"id:{num}"])]
    if cat == "identificador":
        m = re.match(r"(\S+)\s+n[º°.]\s*(.*)", lit)
        num = m.group(2).replace(".", "") if m else lit.lower()
        return [(lit, f"id:{lit.lower()}", [f"id:{num}"], [f"id:{num}"])]
    if cat == "numero":
        v = _num(lit)
        return [(lit, f"num:{v}", [f"num:{v}"], [f"num:{v}"])]
    if cat == "prazo":
        return [(lit, f"prazo:{lit.lower()}", [f"prazo:{lit.lower()}"], [f"prazo:{lit.lower()}"])]
    if cat == "processo":
        k = "proc:" + re.sub(r"\D", "", lit)
        return [(lit, k, [k], [k])]
    return [(lit, f"{cat}:{lit.lower()}", [f"{cat}:{lit.lower()}"], [f"{cat}:{lit.lower()}"])]


# ---------------------------------------------------------------- extração

FRASE_FIM_RE = re.compile(r"(?<=[.;!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\"“(\-–—•*])")


def _mascarar(texto: str, rx: re.Pattern) -> str:
    return rx.sub(lambda m: " " * len(m.group(0)), texto)


def _frase(texto: str, ini: int, fim: int, largura: int = 260) -> str:
    inicio = 0
    for m in FRASE_FIM_RE.finditer(texto):
        if m.end() <= ini:
            inicio = m.end()
        else:
            break
    m = FRASE_FIM_RE.search(texto, fim)
    final = m.start() if m else len(texto)
    frase = texto[inicio:final].strip()
    if len(frase) > largura:
        centro = ini - inicio
        a = max(0, centro - largura // 2)
        frase = ("…" if a else "") + frase[a:a + largura].strip() + "…"
    return pm.sem_negrito(frase)


def extrair_texto(texto: str, local: str) -> list[Item]:
    """Itens de um parágrafo, na ordem das categorias; cada trecho é usado uma vez."""
    original = texto
    t = PREFIXO_PAR_RE.sub(lambda m: " " * len(m.group(0)), texto, count=1)
    t = _mascarar(t, URL_RE)
    t = _mascarar(t, NOTA_RE)
    t = _mascarar(t, pm.REMISSAO_RE)
    t = _mascarar(t, REMISSAO_EXTRA_RE)
    t = t.replace("**", "  ")
    out = []
    for cat, rx in PADROES:
        for m in list(rx.finditer(t)):
            for canon, chave, req, forn in classificar(cat, m.group(0)):
                it = Item(cat, canon, chave, req, forn, local, _frase(original, m.start(), m.end()))
                if cat == "data" and req[0].startswith("data:") and len(forn) >= 4:
                    # "1º de abril de 1986" × "1º de abril" com o ano dito antes ("daquele ano"): dia, mês e ano presentes
                    it.alternativas = [[forn[2], forn[3]]]
                out.append(it)
        t = _mascarar(t, rx)
    return out


NOTA_DEF_RE = re.compile(r"^\[\^(\w+)\]:\s*")


def ler_unidades(path: Path) -> list[tuple[str, str]]:
    """(rótulo, texto) de cada parágrafo: "§ N" no corpo numerado, "nota N" nas notas de rodapé,
    "linha L" no resto. O .docx passa por ``docx_para_md`` (alterações aceitas, numeração do Word, notas)."""
    if path.suffix.lower() == ".docx":
        import docx_para_md

        doc = pm.parse(docx_para_md.converter(path))
    else:
        doc = pm.ler(path)
    corpo = set()
    esperado = 1
    for b in doc.paragrafos:  # corpo numerado: primeira sequência "N." que começa em 1
        n = b.numero_original if doc.numeracao != "explicita" else b.numero
        if n is None:
            continue
        if n < esperado:
            break
        corpo.add(id(b))
        esperado = n + 1
    out = []
    for b in doc.blocos:
        m = NOTA_DEF_RE.match(b.texto)
        if m:
            out.append((f"nota {m.group(1)}", b.texto[m.end():]))
        elif id(b) in corpo:
            n = b.numero_original if b.numero_original is not None else b.numero
            out.append((f"§ {n}", b.texto))
        else:
            out.append((f"linha {b.linha}", b.texto))
    return out


def inventario(path: Path) -> dict[str, Item]:
    """Itens distintos (pela chave literal) de um documento, com o primeiro contexto e os locais."""
    itens: dict[str, Item] = {}
    for local, texto in ler_unidades(path):
        for it in extrair_texto(texto, local):
            if it.chave in itens:
                itens[it.chave].ocorrencias += 1
                if local not in itens[it.chave].locais:
                    itens[it.chave].locais.append(local)
            else:
                it.locais = [local]
                itens[it.chave] = it
    return itens


def comparar(anterior: dict[str, Item], nova: dict[str, Item]) -> tuple[list[Item], list[Item]]:
    """(acréscimos, supressões)."""
    fornece_ant = {k for it in anterior.values() for k in it.fornece}
    fornece_nova = {k for it in nova.values() for k in it.fornece}
    por_req_ant: dict[str, Item] = {}
    for it in anterior.values():
        for r in it.requisitos:
            por_req_ant.setdefault(r, it)
    acrescimos = []
    for k, it in nova.items():
        if k in anterior:
            continue
        if it.presente_em(fornece_ant):
            antes = next((por_req_ant[r] for r in it.requisitos if r in por_req_ant), None)
            it.observacao = (f"mesmo fato na anterior como «{antes.literal}»" if antes and antes.literal != it.literal
                             else "fato já presente na anterior em outra forma")
        acrescimos.append(it)
    supressoes = [it for k, it in anterior.items() if k not in nova and not it.presente_em(fornece_nova)]
    return acrescimos, supressoes


# ---------------------------------------------------------------- saída

def _celula(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def tabela_md(itens: list[Item], titulo: str, coluna_local: str) -> list[str]:
    linhas = [f"### {titulo} ({len(itens)})", ""]
    if not itens:
        return linhas + ["Nenhum.", ""]
    linhas += [f"| # | Categoria | Item | {coluna_local} | Contexto (frase) | Fonte (página) |",
               "|---:|---|---|---|---|---|"]
    for i, it in enumerate(itens, start=1):
        item = it.literal + (f" ({it.observacao})" if it.observacao else "")
        locais = ", ".join(it.locais[:4]) + (" …" if len(it.locais) > 4 else "")
        linhas.append(f"| {i} | {it.categoria} | {_celula(item)} | {_celula(locais)} | {_celula(it.contexto)} |  |")
    return linhas + [""]


def relatorio_md(ant: Path, nova: Path, acr: list[Item], sup: list[Item]) -> str:
    linhas = [f"## Inventário de fatos — {ant.name} → {nova.name}", "",
              f"Acréscimos: {len(acr)} | Supressões: {len(sup)}", "",
              "Preencher «Fonte (página)» de cada acréscimo; justificar ou desfazer cada supressão.", ""]
    linhas += tabela_md(acr, "Acréscimos (na nova versão, ausentes da anterior)", "§ (nova)")
    linhas += tabela_md(sup, "Supressões (na anterior, ausentes da nova)", "§ (anterior)")
    return "\n".join(linhas)


def relatorio_texto(ant: Path, nova: Path, acr: list[Item], sup: list[Item]) -> str:
    linhas = [f"INVENTÁRIO DE FATOS — {ant.name} → {nova.name}", f"acréscimos: {len(acr)} | supressões: {len(sup)}", ""]
    for titulo, itens in (("ACRÉSCIMOS", acr), ("SUPRESSÕES", sup)):
        linhas.append(f"{titulo}:")
        for it in itens:
            obs = f" [{it.observacao}]" if it.observacao else ""
            linhas.append(f"  [{it.categoria}] {it.literal}{obs} — {', '.join(it.locais[:4])}: «{it.contexto[:160]}»")
        if not itens:
            linhas.append("  nenhum")
        linhas.append("")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("anterior", type=Path)
    ap.add_argument("nova", type=Path)
    ap.add_argument("--md", action="store_true", help="tabelas em Markdown para a nota de revisão")
    ap.add_argument("--json", type=Path, help="grava acréscimos e supressões em JSON")
    args = ap.parse_args(argv)
    for p in (args.anterior, args.nova):
        if not p.exists():
            print(f"arquivo não encontrado: {p}", file=sys.stderr)
            return 2
    try:
        ant, nova = inventario(args.anterior), inventario(args.nova)
    except (OSError, ValueError, KeyError) as e:
        print(f"erro de leitura: {e}", file=sys.stderr)
        return 2
    acr, sup = comparar(ant, nova)
    print(relatorio_md(args.anterior, args.nova, acr, sup) if args.md else relatorio_texto(args.anterior, args.nova, acr, sup))
    if args.json:
        args.json.write_text(json.dumps({
            "anterior": str(args.anterior), "nova": str(args.nova),
            "acrescimos": [asdict(i) for i in acr], "supressoes": [asdict(i) for i in sup],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if sup else 0


if __name__ == "__main__":
    sys.exit(main())
