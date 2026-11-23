#!/usr/bin/env python3
"""Converte um .docx em Markdown que ``parecer_md``/``pre_auditoria_parecer.py`` leem sem perder numeração nem rótulos.

O texto exportado por conversores genéricos perde o que a pré-auditoria precisa: a
numeração automática dos parágrafos (vira texto sem "N."), o negrito do rótulo
inicial ("**Correções necessárias.**") e as notas de rodapé. Regras:

- **Alterações controladas**: vale a visão "tudo aceito" — ``w:del`` e ``w:moveFrom``
  saem, ``w:ins`` e ``w:moveTo`` ficam; parágrafo com a marca excluída junta-se ao
  seguinte (mesma contagem de ``exportar_comentarios``/``overlay_docx``).
- **Numeração automática**: ``numPr`` do parágrafo ou do estilo. Cada ``numId`` tem
  seu contador, por nível, como o Word (o nível acima zera os de baixo), começando no
  ``start`` do nível (ou no ``startOverride``). O prefixo segue o ``lvlText`` e o
  ``numFmt`` do nível: "%1." decimal vira "N. texto" (o corpo numerado), "%1)" em
  letra vira "a) texto", romano vira "I. texto", marcador vira "- texto". Como nos
  demais scripts da skill, só conta parágrafo com texto visível.
- **Rótulo em negrito**: os runs em negrito no início do parágrafo viram
  ``**rótulo**`` (negrito direto no run ou por estilo de caractere); o parágrafo todo
  em negrito vira ``**texto**``.
- **Títulos**: estilo de nome "heading N"/"Heading"/"Título N" ou com ``outlineLvl``, e
  linha não numerada no padrão "I. Texto" (romano, ponto, maiúscula), viram ``## ``.
- **Notas de rodapé**: a chamada vira ``[^n]`` (n na ordem de aparição) e as
  definições ``[^n]: texto`` vão para o fim. Notas de fim viram ``[^fN]``.
- Parágrafos de tabela entram como parágrafos; caixas de texto ficam de fora.
- **Numeração explícita para auditor externo** (``--prefixo-paragrafo``): cada parágrafo
  do CORPO numerado sai como ``§N texto`` em vez de ``N. texto``, e a primeira linha
  passa a ser ``<!-- origem: ARQUIVO.docx | sha256: ... -->`` (hash dos bytes do .docx).
  O corpo é o primeiro ``numId`` (na ordem do documento) com parágrafos de nível 0 que
  não são títulos nem marcadores; N é o contador desse nível, contado como o Word.
  Subníveis do corpo e as demais listas saem como no modo padrão. Serve para o auditor
  citar "§N" sem recontar: um auditor que extraiu o texto sem o §1 "Resposta objetiva."
  (rótulo em negrito) deslocou toda a numeração em −1 e "achou" remissões erradas.
  O modo padrão não muda (``parecer_md``/``pre_auditoria_parecer.py`` dependem dele).

Uso::

    docx_para_md.py ENTRADA.docx SAIDA.md
    docx_para_md.py ENTRADA.docx SAIDA.md --prefixo-paragrafo

Código de saída: 0 quando grava, 2 em erro de uso ou de leitura. ``converter(path)``
devolve o Markdown (``converter(path, prefixo_paragrafo=True)`` no modo "§N");
``notas(path)`` devolve as notas de rodapé (usado por ``inventario_fatos.py`` e
``checar_refutadas.py``); ``paragrafos(path)`` devolve os parágrafos com numId, nível,
número e a marca de corpo (usado por ``conferir_achados_externos.py``);
``sha256_arquivo(path)`` e ``cabecalho_origem(path)`` dão o hash e a linha de origem.
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import exportar_comentarios as ec  # noqa: E402

W = ec.W
FORA = (W + "del", W + "moveFrom")
SALTAR = (W + "pPr", W + "rPr", W + "txbxContent", W + "instrText", W + "delText", W + "delInstrText")
ROMANO_TITULO_RE = re.compile(r"^(?:\*\*)?[IVXLC]+\.\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]")
TITULO_NOME_RE = re.compile(r"^(?:heading(?:\s*\d)?|t[íi]tulo\s*\d+)$", re.IGNORECASE)


def _val(el: ET.Element | None, tag: str) -> str | None:
    if el is None:
        return None
    c = el.find(W + tag)
    return None if c is None else c.get(W + "val", "")


def _ligado(el: ET.Element | None, tag: str) -> bool | None:
    """Propriedade booleana (w:b, w:bCs...): None quando ausente."""
    if el is None:
        return None
    c = el.find(W + tag)
    if c is None:
        return None
    return c.get(W + "val", "true").lower() not in ("0", "false", "off", "none")


# ---------------------------------------------------------------- estilos e numeração

@dataclass
class Estilo:
    nome: str = ""
    base: str | None = None
    negrito: bool | None = None
    num_id: str | None = None
    ilvl: int | None = None
    outline: int | None = None


@dataclass
class Nivel:
    inicio: int = 1
    formato: str = "decimal"
    texto: str = "%1."


@dataclass
class Numeracao:
    estilos: dict[str, Estilo] = field(default_factory=dict)
    abstratos: dict[str, dict[int, Nivel]] = field(default_factory=dict)
    nums: dict[str, tuple[str, dict[int, int]]] = field(default_factory=dict)  # numId -> (abstractNumId, startOverride)
    contadores: dict[str, dict[int, int]] = field(default_factory=dict)

    def estilo(self, sid: str | None, campo: str):
        vistos = set()
        while sid and sid in self.estilos and sid not in vistos:
            vistos.add(sid)
            v = getattr(self.estilos[sid], campo)
            if v is not None:
                return v
            sid = self.estilos[sid].base
        return None

    def nivel(self, num_id: str, ilvl: int) -> Nivel:
        abs_id, _ = self.nums.get(num_id, (num_id, {}))
        return self.abstratos.get(abs_id, {}).get(ilvl, Nivel())

    def proximo(self, num_id: str, ilvl: int) -> str:
        """Avança o contador e devolve o prefixo do parágrafo ("3. ", "a) ", "- ")."""
        _, overrides = self.nums.get(num_id, (num_id, {}))
        cont = self.contadores.setdefault(num_id, {})
        if ilvl in cont:
            cont[ilvl] += 1
        else:
            cont[ilvl] = overrides.get(ilvl, self.nivel(num_id, ilvl).inicio)
        for k in [k for k in cont if k > ilvl]:
            del cont[k]
        nivel = self.nivel(num_id, ilvl)
        if nivel.formato == "bullet":
            return "- "
        if nivel.formato == "none" or not nivel.texto:
            return ""

        def troca(m: re.Match) -> str:
            k = int(m.group(1)) - 1
            n = cont.get(k, overrides.get(k, self.nivel(num_id, k).inicio))
            return formatar(n, self.nivel(num_id, k).formato)

        return re.sub(r"%(\d)", troca, nivel.texto).strip() + " "


def _romano(n: int) -> str:
    out = ""
    for v, s in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                 (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out += s
            n -= v
    return out


def _letra(n: int) -> str:
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(ord("a") + r) + s
    return s


def formatar(n: int, formato: str) -> str:
    if formato == "lowerLetter":
        return _letra(n)
    if formato == "upperLetter":
        return _letra(n).upper()
    if formato == "lowerRoman":
        return _romano(n).lower()
    if formato == "upperRoman":
        return _romano(n)
    if formato == "decimalZero":
        return f"{n:02d}"
    if formato == "ordinal":
        return f"{n}º"
    return str(n)


def ler_numeracao(z: zipfile.ZipFile) -> Numeracao:
    num = Numeracao()
    nomes = set(z.namelist())
    if "word/styles.xml" in nomes:
        for s in ET.fromstring(z.read("word/styles.xml")).findall(W + "style"):
            sid = s.get(W + "styleId") or ""
            ppr, rpr = s.find(W + "pPr"), s.find(W + "rPr")
            npr = ppr.find(W + "numPr") if ppr is not None else None
            ilvl = _val(npr, "ilvl")
            outline = _val(ppr, "outlineLvl")
            num.estilos[sid] = Estilo(
                nome=_val(s, "name") or sid,
                base=_val(s, "basedOn"),
                negrito=_ligado(rpr, "b"),
                num_id=_val(npr, "numId"),
                ilvl=int(ilvl) if ilvl and ilvl.isdigit() else None,
                outline=int(outline) if outline and outline.isdigit() else None,
            )
    if "word/numbering.xml" in nomes:
        raiz = ET.fromstring(z.read("word/numbering.xml"))
        for a in raiz.findall(W + "abstractNum"):
            niveis = {}
            for lvl in a.findall(W + "lvl"):
                i = int(lvl.get(W + "ilvl", "0"))
                inicio = _val(lvl, "start")
                niveis[i] = Nivel(int(inicio) if inicio and inicio.lstrip("-").isdigit() else 1,
                                  _val(lvl, "numFmt") or "decimal", _val(lvl, "lvlText") or "")
            num.abstratos[a.get(W + "abstractNumId") or ""] = niveis
        for n in raiz.findall(W + "num"):
            overrides = {}
            for o in n.findall(W + "lvlOverride"):
                so = _val(o, "startOverride")
                if so and so.isdigit():
                    overrides[int(o.get(W + "ilvl", "0"))] = int(so)
            num.nums[n.get(W + "numId") or ""] = (_val(n, "abstractNumId") or "", overrides)
    return num


# ---------------------------------------------------------------- texto dos parágrafos

@dataclass
class Conversor:
    numeracao: Numeracao
    notas_xml: dict[str, ET.Element] = field(default_factory=dict)
    notas_fim_xml: dict[str, ET.Element] = field(default_factory=dict)
    ordem_notas: list[tuple[str, str, str]] = field(default_factory=list)  # (marca, tipo, id)

    def _negrito_run(self, r: ET.Element, estilo_par: str | None) -> bool:
        rpr = r.find(W + "rPr")
        b = _ligado(rpr, "b")
        if b is not None:
            return b
        rst = _val(rpr, "rStyle")
        if rst:
            v = self.numeracao.estilo(rst, "negrito")
            if v is not None:
                return bool(v)
        return False

    def _nota(self, tipo: str, nid: str) -> str:
        for marca, t, i in self.ordem_notas:
            if t == tipo and i == nid:
                return marca
        n = sum(1 for _, t, _ in self.ordem_notas if t == tipo) + 1
        marca = f"[^{n}]" if tipo == "rodape" else f"[^f{n}]"
        self.ordem_notas.append((marca, tipo, nid))
        return marca

    def segmentos(self, el: ET.Element, estilo_par: str | None, fora: bool = False) -> list[tuple[str, bool]]:
        """(texto, negrito) na ordem do documento, sem o excluído."""
        out: list[tuple[str, bool]] = []
        for c in el:
            tag = c.tag
            if tag in SALTAR:
                continue
            if tag in FORA or fora:
                continue
            if tag == W + "r":
                b = self._negrito_run(c, estilo_par)
                for x in c:
                    t = x.tag
                    if t == W + "t":
                        out.append((x.text or "", b))
                    elif t in (W + "tab", W + "br", W + "cr"):
                        out.append((" ", b))
                    elif t == W + "noBreakHyphen":
                        out.append(("-", b))
                    elif t == W + "footnoteReference":
                        out.append((self._nota("rodape", x.get(W + "id") or ""), False))
                    elif t == W + "endnoteReference":
                        out.append((self._nota("fim", x.get(W + "id") or ""), False))
                    elif t not in SALTAR and t not in FORA and t != W + "rPr":
                        out += self.segmentos(x, estilo_par)
                continue
            out += self.segmentos(c, estilo_par)
        return out

    def texto(self, grupo: list[ET.Element]) -> tuple[str, bool]:
        """Texto Markdown do parágrafo (com o rótulo inicial em negrito) e se ele é todo negrito."""
        segs: list[tuple[str, bool]] = []
        for p in grupo:
            estilo = _val(p.find(W + "pPr"), "pStyle")
            segs += self.segmentos(p, estilo)
        segs = [(s.replace(" ", " "), b) for s, b in segs if s]
        plano = "".join(s for s, _ in segs)
        if not plano.strip():
            return "", False
        prefixo, i = "", 0
        while i < len(segs) and (segs[i][1] or not segs[i][0].strip()):
            prefixo += segs[i][0]
            i += 1
        resto = "".join(s for s, _ in segs[i:])
        # espaços em branco no fim do prefixo voltam para o resto, se o prefixo terminou em branco
        if not prefixo.strip():
            return _espacos(plano), False
        if not resto.strip():
            return f"**{_espacos(prefixo)}**", True
        sep = " " if (prefixo[-1:].isspace() or resto[:1].isspace()) else ""
        return f"**{_espacos(prefixo)}**{sep}{_espacos(resto)}", False


def _espacos(s: str) -> str:
    return re.sub(r"[ \t]+", " ", s).strip()


def _numpr(p: ET.Element, num: Numeracao) -> tuple[str | None, int]:
    ppr = p.find(W + "pPr")
    npr = ppr.find(W + "numPr") if ppr is not None else None
    estilo = _val(ppr, "pStyle")
    num_id = _val(npr, "numId")
    ilvl_s = _val(npr, "ilvl")
    if num_id is None:
        num_id = num.estilo(estilo, "num_id")
    if ilvl_s is None:
        ilvl = num.estilo(estilo, "ilvl") or 0
    else:
        ilvl = int(ilvl_s) if ilvl_s.isdigit() else 0
    if not num_id or num_id == "0":
        return None, 0
    return num_id, ilvl


def _e_titulo(p: ET.Element, num: Numeracao) -> bool:
    ppr = p.find(W + "pPr")
    estilo = _val(ppr, "pStyle")
    if _val(ppr, "outlineLvl") not in (None, "9"):
        return True
    if num.estilo(estilo, "outline") not in (None, 9):
        return True
    nome = num.estilos[estilo].nome if estilo in num.estilos else (estilo or "")
    return bool(TITULO_NOME_RE.match(nome.strip()) or TITULO_NOME_RE.match((estilo or "").strip()))


def _notas_xml(z: zipfile.ZipFile, nome: str, tag: str) -> dict[str, ET.Element]:
    if nome not in z.namelist():
        return {}
    out = {}
    for n in ET.fromstring(z.read(nome)).findall(W + tag):
        if n.get(W + "type") in ("separator", "continuationSeparator", "continuationNotice"):
            continue
        out[n.get(W + "id") or ""] = n
    return out


def _texto_nota(conv: Conversor, nota: ET.Element) -> str:
    partes = []
    for p in nota.findall(W + "p"):
        t, _ = conv.texto([p])
        if t:
            partes.append(t)
    return " ".join(partes).strip()


@dataclass
class Paragrafo:
    """Parágrafo com texto visível, na ordem do documento (visão com alterações aceitas)."""
    indice: int  # posição entre os parágrafos com texto, a partir de 0
    texto: str  # Markdown do parágrafo, sem prefixo de numeração (rótulo inicial em **)
    num_id: str | None
    ilvl: int
    prefixo: str  # "3. ", "a) ", "- " ou "" (como no modo padrão)
    numero: int | None  # valor do contador do nível no Word; None sem numeração
    titulo: bool
    corpo: bool = False  # parágrafo do corpo numerado (numId do corpo, nível 0, não título)

    @property
    def plano(self) -> str:
        return self.texto.replace("**", "")


def _ler(path: Path | str) -> tuple[list[Paragrafo], list[tuple[str, str]]]:
    with zipfile.ZipFile(path) as z:
        num = ler_numeracao(z)
        grupos = ec._corpo(z)
        conv = Conversor(num, _notas_xml(z, "word/footnotes.xml", "footnote"), _notas_xml(z, "word/endnotes.xml", "endnote"))
    pars: list[Paragrafo] = []
    for g in grupos:
        texto, _ = conv.texto(g)
        if not texto:
            continue
        ultimo = g[-1]
        num_id, ilvl = _numpr(ultimo, num)
        prefixo, numero = "", None
        if num_id:
            prefixo = num.proximo(num_id, ilvl)
            numero = num.contadores.get(num_id, {}).get(ilvl)
            if num.nivel(num_id, ilvl).formato in ("bullet", "none"):
                numero = None
        pars.append(Paragrafo(len(pars), texto, num_id, ilvl, prefixo, numero, _e_titulo(ultimo, num)))
    notas_ = []
    for marca, tipo, nid in conv.ordem_notas:
        xml = (conv.notas_xml if tipo == "rodape" else conv.notas_fim_xml).get(nid)
        if xml is not None:
            notas_.append((marca, _texto_nota(conv, xml)))
    return pars, notas_


def numid_corpo(pars: list[Paragrafo]) -> str | None:
    """O primeiro numId, na ordem do documento, com parágrafo de nível 0 numerado que não é título."""
    for p in pars:
        if p.num_id and p.ilvl == 0 and p.numero is not None and not p.titulo:
            return p.num_id
    return None


def _marcar_corpo(pars: list[Paragrafo]) -> list[Paragrafo]:
    corpo = numid_corpo(pars)
    for p in pars:
        p.corpo = bool(corpo) and p.num_id == corpo and p.ilvl == 0 and p.numero is not None and not p.titulo
    return pars


def paragrafos(path: Path | str) -> list[Paragrafo]:
    """Parágrafos com texto do .docx, com numeração do Word e a marca ``corpo`` do corpo numerado."""
    return _marcar_corpo(_ler(path)[0])


def _bloco(p: Paragrafo, prefixo_paragrafo: bool) -> str:
    prefixo = f"§{p.numero} " if (prefixo_paragrafo and p.corpo) else p.prefixo
    if p.titulo:
        return "## " + prefixo + p.texto
    if prefixo:
        return prefixo + p.texto
    if ROMANO_TITULO_RE.match(p.texto):
        return "## " + p.texto
    return p.texto


def converter_blocos(path: Path | str, prefixo_paragrafo: bool = False) -> tuple[list[str], list[tuple[str, str]]]:
    """(blocos Markdown do corpo, [(marca, texto)] das notas). Com ``prefixo_paragrafo``, o corpo sai como "§N"."""
    pars, notas_ = _ler(path)
    _marcar_corpo(pars)
    return [_bloco(p, prefixo_paragrafo) for p in pars], notas_


def sha256_arquivo(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def cabecalho_origem(path: Path | str) -> str:
    return f"<!-- origem: {Path(path).name} | sha256: {sha256_arquivo(path)} -->"


def converter(path: Path | str, prefixo_paragrafo: bool = False) -> str:
    blocos, notas_ = converter_blocos(path, prefixo_paragrafo)
    linhas = ([cabecalho_origem(path)] if prefixo_paragrafo else []) + list(blocos)
    if notas_:
        linhas += [f"{marca}: {texto}" for marca, texto in notas_]
    return "\n\n".join(linhas) + "\n"


def notas(path: Path | str) -> list[tuple[str, str]]:
    return converter_blocos(path)[1]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--prefixo-paragrafo", action="store_true",
                    help='corpo numerado como "§N texto" e cabeçalho com nome e SHA-256 do .docx (para auditor externo)')
    args = ap.parse_args(argv)
    if not args.entrada.exists():
        print(f"arquivo não encontrado: {args.entrada}", file=sys.stderr)
        return 2
    try:
        md = converter(args.entrada, args.prefixo_paragrafo)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print(f"erro de leitura do .docx: {e}", file=sys.stderr)
        return 2
    args.saida.write_text(md, encoding="utf-8")
    if args.prefixo_paragrafo:
        n = sum(1 for l in md.split("\n") if re.match(r"^§\d+ ", l))
        print(f"{args.saida}: {md.count(chr(10) + chr(10)) + 1} blocos, {n} parágrafos do corpo com §N; "
              f"sha256 do .docx {sha256_arquivo(args.entrada)}")
        return 0
    n = sum(1 for l in md.split("\n") if re.match(r"^\d+\. ", l))
    print(f"{args.saida}: {md.count(chr(10) + chr(10)) + 1} blocos, {n} parágrafos numerados")
    return 0


if __name__ == "__main__":
    sys.exit(main())
