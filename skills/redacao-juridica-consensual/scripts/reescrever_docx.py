#!/usr/bin/env python3
"""Remonta um DOCX a partir de um roteiro: blocos mantidos da base e parágrafos novos.

Para a reescrita com reestruturação (condensar, reordenar seções, trocar alíneas por
quadro), editar parágrafo a parágrafo não escala. Aqui a versão nova é descrita num
roteiro de texto: cada linha mantém blocos da base, sem tocar em sua formatação, ou
traz um parágrafo novo. O resultado é a versão LIMPA; o comparativo sai depois, com
``word_redline.py compare --base BASE --current SAIDA --motor nativo``, e a conferência
com ``integridade_docx.py``.

Subcomandos::

    reescrever_docx.py listar BASE.docx [--json SAIDA]     # índices dos blocos e nº dos parágrafos
    reescrever_docx.py montar BASE.docx ROTEIRO.txt SAIDA.docx [--num-id N] [--relatorio SAIDA.json]

Roteiro (uma instrução por linha; linha vazia ou iniciada por ``#`` é ignorada):

- ``=b|12`` ou ``=b|12-20``: mantém os blocos da base com esses índices;
- ``=n|5`` ou ``=n|5-9``: mantém os parágrafos numerados nº 5 (a 9) da base;
- ``n|texto``: parágrafo numerado novo, no formato dos parágrafos numerados da base;
  ``**rótulo**`` vira negrito;
- ``p|12|texto``: parágrafo novo com o formato do bloco 12 (título, data, entrada das
  Referências…), aproveitando a formatação de caractere do primeiro trecho;
- ``TW|1900,2400,2400,2371``: larguras das colunas da próxima tabela (em twips; sem
  isso, colunas iguais na largura útil da página);
- ``TH|a||b||c`` (linha de cabeçalho, em negrito, repetida em cada página),
  ``T|a||b||c`` (linha comum) e ``TL|rótulo||texto`` (linha com a primeira célula em
  negrito): linhas consecutivas formam uma tabela.

O relatório lista os blocos da base que o roteiro não manteve: é a conferência de que
nada sumiu por descuido (cada bloco fora da lista foi reescrito ou cortado de propósito).

Código de saída: 0 ok; 2 erro de uso ou de roteiro.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import zipfile
from collections import Counter
from pathlib import Path

BLOCO = re.compile(r"<w:p(?: [^>]*)?>.*?</w:p>|<w:p/>|<w:tbl>.*?</w:tbl>|<w:sectPr.*?</w:sectPr>|<w:sectPr[^>]*/>", re.S)
esc = lambda s: html.escape(s, quote=False)


class RoteiroErro(ValueError):
    pass


def abrir(base: Path) -> tuple[dict[str, bytes], list[str], str, int, int]:
    with zipfile.ZipFile(base) as z:
        arquivos = {n: z.read(n) for n in z.namelist()}
        ordem = z.namelist()
    x = arquivos["word/document.xml"].decode("utf-8")
    if "<w:body>" not in x:
        raise RoteiroErro("document.xml sem <w:body> com prefixo w:")
    b0, b1 = x.find("<w:body>") + 8, x.rfind("</w:body>")
    arquivos["__ordem__"] = "\n".join(ordem).encode()
    return arquivos, BLOCO.findall(x[b0:b1]), x, b0, b1


def texto(bloco: str) -> str:
    return html.unescape("".join(re.findall(r"<w:t(?: [^>]*)?>([^<]*)</w:t>", bloco)))


def num_id_padrao(blocos: list[str]) -> str | None:
    c = Counter(m.group(1) for b in blocos if b.startswith("<w:p") for m in [re.search(r'<w:numId w:val="(\d+)"/>', b)] if m)
    return c.most_common(1)[0][0] if c else None


def listar(blocos: list[str], num_id: str | None) -> list[dict]:
    out, n = [], 0
    for i, b in enumerate(blocos):
        tipo = "tabela" if b.startswith("<w:tbl") else "secao" if b.startswith("<w:sectPr") else "paragrafo"
        num = None
        if tipo == "paragrafo" and num_id and f'<w:numId w:val="{num_id}"/>' in b and texto(b).strip():
            n += 1
            num = n
        est = re.search(r'<w:pStyle w:val="([^"]+)"/>', b)
        out.append({"i": i, "n": num, "tipo": tipo, "estilo": est.group(1) if est else "", "texto": texto(b)})
    return out


def _faixa(s: str) -> range:
    m = re.fullmatch(r"\s*(\d+)\s*(?:-\s*(\d+))?\s*", s)
    if not m:
        raise RoteiroErro(f"faixa inválida: {s!r}")
    a, b = int(m.group(1)), int(m.group(2) or m.group(1))
    if b < a:
        raise RoteiroErro(f"faixa invertida: {s!r}")
    return range(a, b + 1)


def _runs(t: str, rpr_base: str = "") -> str:
    out = ""
    for k, parte in enumerate(re.split(r"\*\*", t)):
        if not parte:
            continue
        rpr = rpr_base
        if k % 2:
            rpr = (rpr_base[:-len("</w:rPr>")] if rpr_base else "<w:rPr>") + "<w:b/><w:bCs/></w:rPr>"
        out += f'<w:r>{rpr}<w:t xml:space="preserve">{esc(parte)}</w:t></w:r>'
    return out


def _celula(t: str, w: int, negrito: bool) -> str:
    rpr = "<w:rPr>" + ("<w:b/><w:bCs/>" if negrito else "") + '<w:sz w:val="20"/><w:szCs w:val="20"/></w:rPr>'
    return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/></w:tcPr><w:p><w:pPr><w:spacing w:before="40" w:after="40" w:line="240" '
            f'w:lineRule="auto"/><w:ind w:firstLine="0"/><w:jc w:val="left"/></w:pPr><w:r>{rpr}<w:t xml:space="preserve">{esc(t.strip())}</w:t></w:r></w:p></w:tc>')


def _tabela(linhas: list[tuple[str, list[str]]], larguras: list[int] | None, util: int) -> str:
    ncol = len(linhas[0][1])
    if any(len(c) != ncol for _, c in linhas):
        raise RoteiroErro("tabela com linhas de número de colunas diferente")
    larg = larguras or [util // ncol] * ncol
    if len(larg) != ncol:
        raise RoteiroErro(f"TW tem {len(larg)} larguras e a tabela tem {ncol} colunas")
    trs = ""
    for tipo, cols in linhas:
        trpr = "<w:trPr><w:cantSplit/>" + ("<w:tblHeader/>" if tipo == "TH" else "") + "</w:trPr>"
        trs += "<w:tr>" + trpr + "".join(_celula(c, w, tipo == "TH" or (tipo == "TL" and j == 0)) for j, (c, w) in enumerate(zip(cols, larg))) + "</w:tr>"
    bordas = "".join(f'<w:{k} w:val="single" w:sz="4" w:space="0" w:color="000000"/>' for k in ("top", "left", "bottom", "right", "insideH", "insideV"))
    return (f'<w:tbl><w:tblPr><w:tblW w:w="{sum(larg)}" w:type="dxa"/><w:tblBorders>{bordas}</w:tblBorders><w:tblLayout w:type="fixed"/>'
            '<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
            + "".join(f'<w:gridCol w:w="{w}"/>' for w in larg) + "</w:tblGrid>" + trs + "</w:tbl>"
            '<w:p><w:pPr><w:spacing w:after="60" w:line="240" w:lineRule="auto"/><w:ind w:firstLine="0"/></w:pPr></w:p>')


def largura_util(x: str) -> int:
    sz, mar = re.search(r'<w:pgSz [^>]*w:w="(\d+)"', x), re.search(r"<w:pgMar [^>]*>", x)
    if not sz:
        return 9000
    esq = re.search(r'w:left="(\d+)"', mar.group(0)) if mar else None
    dire = re.search(r'w:right="(\d+)"', mar.group(0)) if mar else None
    return int(sz.group(1)) - int(esq.group(1) if esq else 1440) - int(dire.group(1) if dire else 1440)


def montar(blocos: list[str], roteiro: str, num_id: str | None, util: int) -> tuple[list[str], dict]:
    itens = listar(blocos, num_id)
    por_num = {it["n"]: it["i"] for it in itens if it["n"]}
    ppr_num = None
    if num_id:
        prim = next((b for b in blocos if f'<w:numId w:val="{num_id}"/>' in b), None)
        ppr_num = re.search(r"<w:pPr>.*?</w:pPr>", prim, flags=re.S).group(0) if prim else None
        ppr_num = re.sub(r"<w:rPr>.*?</w:rPr>|<w:rPr/>|<w:keepNext/>", "", ppr_num, flags=re.S) if ppr_num else None
    out, tab, larg, mantidos, novos = [], [], None, set(), 0

    def fecha():
        nonlocal larg
        if tab:
            out.append(_tabela(list(tab), larg, util))
            tab.clear()
            larg = None

    for nl, linha in enumerate(roteiro.split("\n"), 1):
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        k, sep, r = linha.partition("|")
        k = k.strip()
        try:
            if not sep:
                raise RoteiroErro("falta o separador |")
            if k == "TW":
                fecha()
                larg = [int(v) for v in r.split(",")]
                continue
            if k in ("TH", "T", "TL"):
                tab.append((k, r.split("||")))
                continue
            fecha()
            if k == "=b":
                for i in _faixa(r):
                    if i >= len(blocos):
                        raise RoteiroErro(f"bloco {i} não existe na base (0 a {len(blocos) - 1})")
                    out.append(blocos[i]); mantidos.add(i)
            elif k == "=n":
                for n in _faixa(r):
                    if n not in por_num:
                        raise RoteiroErro(f"parágrafo numerado {n} não existe na base")
                    out.append(blocos[por_num[n]]); mantidos.add(por_num[n])
            elif k == "n":
                if not ppr_num:
                    raise RoteiroErro("a base não tem parágrafo numerado para servir de formato (use --num-id)")
                out.append(f"<w:p>{ppr_num}{_runs(r)}</w:p>"); novos += 1
            elif k == "p":
                i, _, t = r.partition("|")
                i = int(i)
                if i >= len(blocos) or not blocos[i].startswith("<w:p"):
                    raise RoteiroErro(f"bloco {i} não é parágrafo da base")
                ppr = re.search(r"<w:pPr>.*?</w:pPr>", blocos[i], flags=re.S)
                rr = re.search(r"<w:r(?: [^>]*)?>(<w:rPr>.*?</w:rPr>)", blocos[i], flags=re.S)
                out.append(f"<w:p>{ppr.group(0) if ppr else ''}{_runs(t, rr.group(1) if rr else '')}</w:p>"); novos += 1
            else:
                raise RoteiroErro(f"instrução desconhecida: {k!r}")
        except (RoteiroErro, ValueError) as e:
            raise RoteiroErro(f"linha {nl}: {e}") from None
    fecha()
    fora = [it for it in itens if it["i"] not in mantidos and it["texto"].strip()]
    if not any(b.startswith("<w:sectPr") for b in out) and any(b.startswith("<w:sectPr") for b in blocos):
        raise RoteiroErro("o roteiro não manteve o bloco de seção (o último da base): inclua-o com =b")
    rel = {"blocos_base": len(blocos), "mantidos": len(mantidos), "novos": novos, "blocos_saida": len(out),
           "nao_mantidos": [{"i": it["i"], "n": it["n"], "texto": it["texto"][:80]} for it in fora]}
    return out, rel


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("listar", help="lista os blocos da base, com índice e nº do parágrafo")
    l.add_argument("base", type=Path); l.add_argument("--json", type=Path); l.add_argument("--num-id")
    m = sub.add_parser("montar", help="monta a versão limpa a partir do roteiro")
    m.add_argument("base", type=Path); m.add_argument("roteiro", type=Path); m.add_argument("saida", type=Path)
    m.add_argument("--num-id", help="numId dos parágrafos numerados do corpo (padrão: o mais frequente)")
    m.add_argument("--relatorio", type=Path)
    a = ap.parse_args(argv)
    try:
        arquivos, blocos, x, b0, b1 = abrir(a.base)
        num_id = a.num_id or num_id_padrao(blocos)
        if a.cmd == "listar":
            itens = listar(blocos, num_id)
            for it in itens:
                rot = f"§{it['n']}" if it["n"] else it["tipo"][:3]
                print(f"{it['i']:>4} {rot:>5} {it['estilo'][:10]:<10} {it['texto'][:90]}")
            if a.json:
                a.json.write_text(json.dumps(itens, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
            return 0
        out, rel = montar(blocos, a.roteiro.read_text(encoding="utf-8"), num_id, largura_util(x))
    except (OSError, KeyError, zipfile.BadZipFile, RoteiroErro) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    ordem = arquivos.pop("__ordem__").decode().split("\n")
    arquivos["word/document.xml"] = (x[:b0] + "".join(out) + x[b1:]).encode("utf-8")
    with zipfile.ZipFile(a.saida, "w", zipfile.ZIP_DEFLATED) as zo:
        for nome in ordem:
            zo.writestr(nome, arquivos[nome])
    print(f"blocos: {rel['blocos_base']} na base, {rel['mantidos']} mantidos, {rel['novos']} novos, {rel['blocos_saida']} na saída")
    print(f"blocos da base não mantidos (reescritos ou cortados): {len(rel['nao_mantidos'])}")
    if a.relatorio:
        a.relatorio.write_text(json.dumps(rel, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
