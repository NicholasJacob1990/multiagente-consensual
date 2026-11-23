#!/usr/bin/env python3
"""Exporta os comentários de um .docx com o trecho ancorado e o parágrafo numerado onde estão.

Para revisar as respostas do autor a uma rodada de comentários, não basta o texto
do comentário: é preciso o trecho a que ele se prende e o número do parágrafo.
Para cada comentário, este script devolve:

- id, autor e data;
- ``responde_a``: id do comentário a que responde (``w15:paraIdParent`` de
  ``commentsExtended.xml``); vazio quando não é resposta;
- ``resolvido``: marca ``w15:done`` do Word, quando houver;
- trecho ancorado: texto visível (inserções entram, exclusões saem) entre
  ``commentRangeStart`` e ``commentRangeEnd``; sem intervalo, o parágrafo do
  ``commentReference``. Quando o trecho cobre mais de um parágrafo, as quebras
  aparecem como ``¶``;
- número do parágrafo numerado onde está o trecho. A contagem é a do Word:
  parágrafos com ``numPr`` próprio (nível 0, ``numId`` diferente de 0) e texto
  visível não vazio, na visão "tudo aceito" (parágrafo de marca excluída se junta
  ao seguinte; linha de tabela excluída sai), a mesma do ``overlay_docx``. Trecho
  fora de parágrafo numerado traz o último número antes dele ("depois do § N");
- texto do comentário.

O módulo também serve de leitor de .docx para ``verificar_remissoes.py``
(``ler_paragrafos`` e ``ler_comentarios``).

Exemplos::

    exportar_comentarios.py minuta_revisada.docx --saida comentarios.txt --json comentarios.json
    exportar_comentarios.py parecer.docx --autor "Nicholas"

Sai com 0 quando conseguiu ler o arquivo (mesmo sem comentários) e 2 em erro de uso
ou de leitura.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"
W15 = "{http://schemas.microsoft.com/office/word/2012/wordml}"
FORA = (W + "del", W + "moveFrom")
SALTAR = (W + "pPr", W + "txbxContent")
QUEBRA = "¶"


def norm(t: str) -> str:
    t = t.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    return re.sub(r"\s+", " ", t).strip()


def _eventos(el: ET.Element, fora: bool = False):
    """Percorre o parágrafo em ordem: texto visível e marcas de comentário."""
    for c in el:
        tag = c.tag
        if tag in SALTAR:
            continue
        if tag == W + "commentRangeStart":
            yield "ini", c.get(W + "id")
        elif tag == W + "commentRangeEnd":
            yield "fim", c.get(W + "id")
        elif tag == W + "commentReference":
            yield "ref", c.get(W + "id")
        elif tag == W + "t":
            if not fora:
                yield "t", c.text or ""
        elif tag in (W + "tab", W + "br", W + "cr"):
            if not fora:
                yield "t", " "
        elif tag == W + "noBreakHyphen":
            if not fora:
                yield "t", "-"
        else:
            yield from _eventos(c, fora or tag in FORA)


def texto_visivel(p: ET.Element) -> str:
    return norm("".join(v for k, v in _eventos(p) if k == "t"))


def numerado(p: ET.Element) -> bool:
    """Parágrafo com numeração automática própria, no primeiro nível."""
    ppr = p.find(W + "pPr")
    num = ppr.find(W + "numPr") if ppr is not None else None
    if num is None:
        return False
    nid = num.find(W + "numId")
    if nid is not None and nid.get(W + "val") == "0":
        return False
    ilvl = num.find(W + "ilvl")
    return ilvl is None or ilvl.get(W + "val", "0") == "0"


def marca_excluida(p: ET.Element) -> bool:
    """A marca de parágrafo foi excluída: aceito, o parágrafo se funde com o seguinte."""
    ppr = p.find(W + "pPr")
    rpr = ppr.find(W + "rPr") if ppr is not None else None
    return rpr is not None and rpr.find(W + "del") is not None


def linha_excluida(tr: ET.Element) -> bool:
    trpr = tr.find(W + "trPr")
    return trpr is not None and trpr.find(W + "del") is not None


def _paragrafos_xml(body: ET.Element) -> list[ET.Element]:
    """Parágrafos do corpo, inclusive em tabelas, fora de caixas de texto e de linhas de tabela excluídas."""
    out: list[ET.Element] = []

    def visitar(el: ET.Element) -> None:
        for c in el:
            if c.tag == W + "p":
                out.append(c)
            elif c.tag == W + "tr" and linha_excluida(c):
                continue
            elif c.tag not in SALTAR:
                visitar(c)

    visitar(body)
    return out


def paragrafos_aceitos(body: ET.Element) -> list[list[ET.Element]]:
    """Parágrafos na visão "tudo aceito": cada item é a lista de ``w:p`` que viram um só parágrafo
    (os de marca excluída se juntam ao seguinte); o último da lista dá a formatação e a numeração.
    Funciona com ``xml.etree`` e com ``lxml``; ``overlay_docx`` usa a mesma contagem."""
    grupos: list[list[ET.Element]] = []
    atual: list[ET.Element] = []
    for p in _paragrafos_xml(body):
        atual.append(p)
        if not marca_excluida(p):
            grupos.append(atual)
            atual = []
    if atual:
        grupos.append(atual)
    return grupos


def _corpo(z: zipfile.ZipFile) -> list[list[ET.Element]]:
    root = ET.fromstring(z.read("word/document.xml"))
    body = root.find(W + "body")
    return paragrafos_aceitos(body if body is not None else root)


def _eventos_grupo(grupo: list[ET.Element]):
    for p in grupo:
        yield from _eventos(p)


def ler_paragrafos(path: Path | str) -> list[dict]:
    """Parágrafos do corpo (inclusive em tabelas), na visão com alterações aceitas.

    Cada item: ``{"indice": i, "numero": N ou None, "texto": "..."}``; ``numero`` segue
    a contagem de parágrafos numerados com texto.
    """
    with zipfile.ZipFile(path) as z:
        pars = _corpo(z)
    out = []
    n = 0
    for i, g in enumerate(pars):
        texto = norm("".join(v for k, v in _eventos_grupo(g) if k == "t"))
        numero = None
        if texto and numerado(g[-1]):
            n += 1
            numero = n
        out.append({"indice": i, "numero": numero, "texto": texto})
    return out


def ler_comentarios(path: Path | str) -> list[dict]:
    with zipfile.ZipFile(path) as z:
        nomes = set(z.namelist())
        if "word/comments.xml" not in nomes:
            return []
        pars = _corpo(z)
        com = ET.fromstring(z.read("word/comments.xml"))
        ext = ET.fromstring(z.read("word/commentsExtended.xml")) if "word/commentsExtended.xml" in nomes else None

    comentarios: dict[str, dict] = {}
    comentario_do_para: dict[str, str] = {}
    for c in com.findall(W + "comment"):
        cid = c.get(W + "id") or ""
        cps = c.findall(".//" + W + "p")
        for p in cps:
            pid = p.get(W14 + "paraId")
            if pid:
                comentario_do_para[pid] = cid
        comentarios[cid] = {
            "id": cid,
            "autor": c.get(W + "author") or "",
            "data": c.get(W + "date") or "",
            "responde_a": "",
            "resolvido": None,
            "paragrafos": [],
            "depois_do_paragrafo": None,
            "trecho": "",
            "texto_paragrafos": "",
            "texto": "\n".join(t for t in (texto_visivel(p) for p in cps) if t),
        }
    if ext is not None:
        for e in ext.iter(W15 + "commentEx"):
            cid = comentario_do_para.get(e.get(W15 + "paraId") or "")
            if cid is None:
                continue
            pai = comentario_do_para.get(e.get(W15 + "paraIdParent") or "")
            if pai is not None and pai != cid:
                comentarios[cid]["responde_a"] = pai
            if e.get(W15 + "done") is not None:
                comentarios[cid]["resolvido"] = e.get(W15 + "done") in ("1", "true")

    info: list[tuple[int | None, str]] = []
    buf: dict[str, list[str]] = {}
    ini: dict[str, int] = {}
    fim: dict[str, int] = {}
    ref: dict[str, int] = {}
    ativos: list[str] = []
    n = 0
    for i, g in enumerate(pars):
        evs = list(_eventos_grupo(g))
        texto = norm("".join(v for k, v in evs if k == "t"))
        numero = None
        if texto and numerado(g[-1]):
            n += 1
            numero = n
        info.append((numero, texto))
        for cid in ativos:
            buf[cid].append(f" {QUEBRA} ")
        for k, v in evs:
            if k == "ini":
                if v not in ativos:
                    ativos.append(v)
                buf.setdefault(v, [])
                ini.setdefault(v, i)
            elif k == "fim":
                if v in ativos:
                    ativos.remove(v)
                fim[v] = i
            elif k == "ref":
                ref.setdefault(v, i)
            else:
                for cid in ativos:
                    buf[cid].append(v)

    for cid, c in comentarios.items():
        a = ini.get(cid, ref.get(cid))
        if a is None:
            continue
        b = fim.get(cid, ref.get(cid, a))
        b = max(a, b)
        if cid in buf:
            trecho = norm("".join(buf[cid]))
            trecho = re.sub(rf"^(?:{QUEBRA}\s*)+|(?:\s*{QUEBRA})+$", "", trecho).strip()
        else:
            trecho = info[a][1]
        c["trecho"] = trecho
        c["paragrafos"] = [info[k][0] for k in range(a, b + 1) if info[k][0] is not None]
        if not c["paragrafos"]:
            anteriores = [info[k][0] for k in range(0, a) if info[k][0] is not None]
            c["depois_do_paragrafo"] = anteriores[-1] if anteriores else None
        c["texto_paragrafos"] = f" {QUEBRA} ".join(info[k][1] for k in range(a, b + 1) if info[k][1])
    return list(comentarios.values())


def onde(c: dict) -> str:
    if c["paragrafos"]:
        ps = c["paragrafos"]
        return f"§ {ps[0]}" if len(ps) == 1 else f"§§ {ps[0]} a {ps[-1]}"
    if c["depois_do_paragrafo"]:
        return f"parágrafo sem número, depois do § {c['depois_do_paragrafo']}"
    if c["trecho"] or c["texto_paragrafos"]:
        return "parágrafo sem número, antes do primeiro numerado"
    return "sem âncora no corpo"


def relatorio(path: Path, comentarios: list[dict]) -> str:
    linhas = [f"COMENTÁRIOS — {path.name} ({len(comentarios)} comentário{'s' if len(comentarios) != 1 else ''})", ""]
    for c in comentarios:
        cab = f"[{c['id']}] {c['autor'] or 'sem autor'}"
        if c["data"]:
            cab += f" — {c['data']}"
        if c["responde_a"]:
            cab += f" — responde ao [{c['responde_a']}]"
        if c["resolvido"]:
            cab += " — resolvido"
        linhas.append(cab)
        linhas.append(f"Onde: {onde(c)}")
        linhas.append(f"Trecho: «{c['trecho']}»")
        if c["texto_paragrafos"] and c["texto_paragrafos"] != c["trecho"]:
            ctx = c["texto_paragrafos"]
            linhas.append(f"No parágrafo: «{ctx[:600]}{'…' if len(ctx) > 600 else ''}»")
        linhas.append("Comentário: " + c["texto"].replace("\n", "\n  "))
        linhas.append("")
    return "\n".join(linhas).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("docx", type=Path)
    ap.add_argument("--saida", type=Path, help="grava o texto neste arquivo; padrão: saída padrão")
    ap.add_argument("--json", type=Path, help="grava os comentários em JSON")
    ap.add_argument("--autor", help="só os comentários deste autor (trecho do nome, sem diferenciar maiúsculas)")
    args = ap.parse_args(argv)
    if not args.docx.exists():
        print(f"arquivo não encontrado: {args.docx}", file=sys.stderr)
        return 2
    try:
        comentarios = ler_comentarios(args.docx)
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print(f"não foi possível ler {args.docx} como .docx: {e}", file=sys.stderr)
        return 2
    if args.autor:
        alvo = args.autor.casefold()
        comentarios = [c for c in comentarios if alvo in c["autor"].casefold()]
    texto = relatorio(args.docx, comentarios)
    if args.saida:
        args.saida.write_text(texto, encoding="utf-8")
        print(f"{len(comentarios)} comentários gravados em {args.saida}")
    else:
        print(texto, end="")
    if args.json:
        args.json.write_text(json.dumps({"arquivo": str(args.docx), "comentarios": comentarios},
                                        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
