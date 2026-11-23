#!/usr/bin/env python3
"""Aceita ou rejeita todas as alterações controladas de um DOCX, sem reescrever o XML.

Serve para obter a base de um comparativo quando o arquivo recebido já vem com marcas
pendentes: ``rejeitar`` devolve o texto original, anterior às marcas; ``aceitar``
devolve o texto como o autor o deixou. Com a base limpa, ``word_redline.py compare``
gera um único comparativo "desde o original" até a versão corrente.

O trabalho é feito no texto do XML, preservando o prefixo ``w:`` e todo o resto do
pacote (o motor nativo de ``word_redline`` recusa XML reserializado com outro prefixo).
Trata: inserções e exclusões de texto, marcas de parágrafo inseridas ou excluídas
(funde os parágrafos, como o Word), movimentações (``moveFrom``/``moveTo``),
alterações de formatação (``rPrChange``, ``pPrChange`` e demais ``*Change``), linhas de
tabela inseridas ou excluídas e as mesmas marcas em notas, cabeçalhos e rodapés.

Depois de gravar, confere o resultado contra a leitura lógica de
``integridade_docx`` (aceitar ou rejeitar) e falha se o texto divergir.

Uso::

    resolver_revisoes.py ENTRADA.docx SAIDA.docx --modo aceitar|rejeitar [--sem-conferir]

Código de saída: 0 ok; 1 divergência na conferência; 2 erro de uso.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path

PARTES = re.compile(r"word/(document|footnotes|endnotes|header\d*|footer\d*)\.xml$")
PAR = re.compile(r"<w:p(?: [^>]*)?>.*?</w:p>|<w:p/>", re.S)
ABRE = re.compile(r"^<w:p(?: [^>]*)?>")


def _marca(tag: str) -> re.Pattern:
    return re.compile(r"<w:pPr>(?:(?!</w:pPr>).)*?<w:rPr>(?:(?!</w:rPr>).)*?<w:%s [^>]*/>" % tag, re.S)


def _corpo(p: str) -> str:
    if p == "<w:p/>":
        return ""
    p = ABRE.sub("", p)[: -len("</w:p>")]
    return re.sub(r"^<w:pPr>.*?</w:pPr>", "", p, count=1, flags=re.S)


def _ppr(p: str) -> str:
    m = re.match(r"<w:p(?: [^>]*)?>(<w:pPr>.*?</w:pPr>)?", p, flags=re.S)
    return (m.group(1) or "") if m else ""


def _fundir(xml: str, sai: tuple[str, ...]) -> str:
    """Parágrafo cuja marca some (inserida ao rejeitar, excluída ao aceitar) junta-se ao seguinte."""
    marcas = [_marca(t) for t in sai]
    partes, pos, pend = [], 0, ""
    for m in PAR.finditer(xml):
        p = m.group(0)
        partes.append(xml[pos:m.start()])
        pos = m.end()
        if any(k.search(p) for k in marcas):
            pend += _corpo(p)
            continue
        partes.append("<w:p>" + _ppr(p) + pend + _corpo(p) + "</w:p>" if pend else p)
        pend = ""
    if pend:
        partes.append("<w:p>" + pend + "</w:p>")
    partes.append(xml[pos:])
    return "".join(partes)


def resolver_xml(xml: str, modo: str) -> str:
    if modo not in ("aceitar", "rejeitar"):
        raise ValueError("modo deve ser aceitar ou rejeitar")
    fica, sai = (("ins", "moveTo"), ("del", "moveFrom")) if modo == "aceitar" else (("del", "moveFrom"), ("ins", "moveTo"))
    # linhas de tabela inseridas/excluídas
    for t in sai:
        xml = re.sub(r"<w:tr(?: [^>]*)?>(?:(?!</w:tr>).)*?<w:trPr>(?:(?!</w:trPr>).)*?<w:%s [^>]*/>.*?</w:tr>" % t, "", xml, flags=re.S)
    xml = re.sub(r"<w:tbl>(?:(?!<w:tr[ >]|</w:tbl>).)*</w:tbl>", "", xml, flags=re.S)   # tabela que ficou sem linhas
    xml = _fundir(xml, sai)
    for t in sai:
        xml = re.sub(r"<w:%s [^>]*>.*?</w:%s>" % (t, t), "", xml, flags=re.S)
    for t in fica:
        xml = re.sub(r"<w:%s [^>]*/>" % t, "", xml)
        xml = re.sub(r"<w:%s [^>]*>|</w:%s>" % (t, t), "", xml)
    xml = re.sub(r"<w:move(?:From|To)Range(?:Start|End)\b[^>]*/>", "", xml)
    xml = xml.replace("<w:delText", "<w:t").replace("</w:delText>", "</w:t>")
    if modo == "aceitar":
        xml = re.sub(r"<w:\w+Change [^>]*>.*?</w:\w+Change>|<w:\w+Change [^>]*/>", "", xml, flags=re.S)
    else:
        xml = re.sub(r"<w:pPr>(?:(?!</w:pPr>).)*?<w:pPrChange [^>]*>(<w:pPr>.*?</w:pPr>|<w:pPr/>)</w:pPrChange></w:pPr>",
                     lambda m: m.group(1), xml, flags=re.S)
        xml = re.sub(r"<w:rPr>(?:(?!</w:rPr>).)*?<w:rPrChange [^>]*>(<w:rPr>.*?</w:rPr>|<w:rPr/>)</w:rPrChange></w:rPr>",
                     lambda m: m.group(1), xml, flags=re.S)
        xml = re.sub(r"<w:\w+Change [^>]*>.*?</w:\w+Change>|<w:\w+Change [^>]*/>", "", xml, flags=re.S)
    return xml.replace("<w:rPr></w:rPr>", "")


def restantes(xml: str) -> int:
    return len(re.findall(r"<w:(?:ins|del|moveFrom|moveTo|\w+Change)[ >]", xml))


def resolver(entrada: Path, saida: Path, modo: str) -> dict:
    info = {"modo": modo, "partes": [], "marcas_antes": 0, "marcas_depois": 0}
    with zipfile.ZipFile(entrada) as z:
        itens = [(i, z.read(i.filename)) for i in z.infolist()]
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zo:
        for i, dados in itens:
            if PARTES.search(i.filename):
                xml = dados.decode("utf-8")
                n = restantes(xml)
                if n:
                    xml = resolver_xml(xml, modo)
                    info["partes"].append(i.filename)
                    info["marcas_antes"] += n
                    info["marcas_depois"] += restantes(xml)
                    dados = xml.encode("utf-8")
            zo.writestr(i.filename, dados)
    return info


def conferir(entrada: Path, saida: Path, modo: str) -> str | None:
    """None se o texto da saída é o que ``integridade_docx`` lê ao aceitar/rejeitar a entrada."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import integridade_docx as integ  # noqa: E402
    esperado = (integ.aceitar if modo == "aceitar" else integ.rejeitar)(entrada)
    obtido = integ.ler(saida)
    a = [p for p in esperado.paragrafos if p.strip()]
    b = [p for p in obtido.paragrafos if p.strip()]
    if a == b:
        return None
    d = integ.primeira_divergencia(a, b) or {}
    return str(d.get("resumo") or "o texto da saída diverge do esperado")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("entrada", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--modo", choices=("aceitar", "rejeitar"), required=True)
    ap.add_argument("--sem-conferir", action="store_true")
    a = ap.parse_args(argv)
    if not a.entrada.is_file():
        print(f"erro: arquivo não encontrado: {a.entrada}", file=sys.stderr)
        return 2
    try:
        info = resolver(a.entrada, a.saida, a.modo)
    except (OSError, ValueError, zipfile.BadZipFile) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    print(f"{a.modo}: {info['marcas_antes']} marca(s) resolvida(s) em {', '.join(info['partes']) or 'nenhuma parte'}; restantes: {info['marcas_depois']}")
    if info["marcas_depois"]:
        print("divergência: sobraram marcas não resolvidas")
        return 1
    if not a.sem_conferir:
        falha = conferir(a.entrada, a.saida, a.modo)
        if falha:
            print(f"divergência: {falha}")
            return 1
        print("conferido: o texto da saída é o esperado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
