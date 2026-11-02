#!/usr/bin/env python3
"""Monta o adendo de fontes literais a partir dos artigos citados na minuta.

O auditor só pode conferir o que recebe. Este script lê a minuta, encontra as
citações de artigos ("art. 17, § 2º, da Lei nº 13.303/2016", "(Estatuto, art.
22)", "arts. 17 e 19 do Decreto") e copia das fontes o texto **integral** de
cada artigo citado, com parágrafos e incisos. O artigo inteiro evita que o
auditor (ou o redator) afirme que um dispositivo não tem incisos ou não
alcança certo caso olhando só um resumo.

As normas são indicadas por um mapa de apelidos para arquivos (``.md``,
``.txt`` ou ``.html``)::

    {"Lei nº 13.303/2016": "l13303.txt", "Lei": "l13303.txt",
     "Decreto": "d47154.txt", "Estatuto": "Estatuto-Codemig.md"}

Exemplo::

    extrair_adendo.py parecer_v30.md --fontes fontes/ --mapa mapa.json --saida adendo.md --json adendo.json

Citações sem norma identificável ficam fora, salvo com ``--padrao APELIDO``
(útil quando "art. 31", sem mais, é da minuta analisada); elas são listadas à
parte, para conferir. Artigo citado e não localizado na fonte é listado no fim do
adendo: é sinal de citação errada ou de fonte incompleta, e deve ser resolvido
antes da auditoria. O artigo vai inteiro até o cabeçalho do seguinte; sem artigo
seguinte, e longo demais, sai marcado TRUNCADO. Truncado ou não localizado, o
script sai com 1: o adendo não certifica texto integral.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402

NUM = r"\d+(?:\.\d{3})*(?:-[A-Z])?"
_ORD = r"(?:\s*[º°ª])?"
LISTA = rf"{NUM}{_ORD}(?:\s*(?:,|\be\b)\s*{NUM}{_ORD}(?!\d))*"  # "7º e 8º", "7, 8 e 9", "17 e 19"
LIMITE_SEM_FIM = 20000  # último artigo da fonte, sem cabeçalho seguinte: corta aqui e marca como truncado


def ler_fonte(path: Path) -> str:
    txt = path.read_text(encoding="utf-8", errors="ignore")
    if path.suffix.lower() in {".html", ".htm"}:
        txt = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", txt)
        txt = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</tr>|</h\d>", "\n", txt)
        txt = html.unescape(re.sub(r"<[^>]+>", " ", txt))
    txt = txt.replace(" ", " ")
    return "\n".join(re.sub(r"[ \t]+", " ", l).strip() for l in txt.split("\n"))


def _num_padrao(num: str) -> str:
    """'1011' ou '1.011' casam com '1.011', '1011', '1.011º'."""
    digitos = num.replace(".", "")
    sufixo = ""
    if "-" in digitos:
        digitos, sufixo = digitos.split("-", 1)
        sufixo = rf"\s*-\s*{sufixo}"
    grupos = []
    while len(digitos) > 3:
        grupos.insert(0, digitos[-3:])
        digitos = digitos[:-3]
    grupos.insert(0, digitos)
    return r"\.?".join(grupos) + sufixo


# Cabeçalho de artigo: no início da linha (qualquer caixa) ou, nos PDFs convertidos em que vários artigos
# dividem a linha, depois de fim de frase ou de negrito, com "Art" em maiúscula, para não confundir com
# remissões internas como "o art. 122 da Lei".
ART_INICIO = (r"(?:(?im:^[\s>*#_\-–]*(?:art|artigo)\.?\s*)"
              r"|(?:(?<=[.;:!?)\]]\s)|(?<=\*\*))[\s*]*(?:Art|ART|Artigo)\.?\s*)")
TERMINO = r"(?:\s*[º°ª]|o(?=[\s.\-–]))?(?=\s*[.\-–—:]|\*\*|\s|$)"


def artigo_completo(texto_fonte: str, num: str) -> tuple[str, bool] | None:
    """(texto do artigo, integral?). Vai do cabeçalho do artigo ao do seguinte, sem corte; sem
    artigo seguinte, até o fim da fonte, ou até ``LIMITE_SEM_FIM`` caracteres, e aí não é integral."""
    m = re.search(ART_INICIO + _num_padrao(num) + TERMINO, texto_fonte)
    if not m:
        return None
    prox = re.search(ART_INICIO + r"\d+" + TERMINO, texto_fonte[m.end():])
    integral = True
    if prox:
        fim = m.end() + prox.start()
    elif len(texto_fonte) - m.start() <= LIMITE_SEM_FIM:
        fim = len(texto_fonte)
    else:
        fim, integral = m.start() + LIMITE_SEM_FIM, False
    trecho = texto_fonte[m.start():fim].strip(" \n*>#")
    return (trecho if integral else trecho + " […]"), integral


def artigo(texto_fonte: str, num: str) -> str | None:
    r = artigo_completo(texto_fonte, num)
    return r[0] if r else None


def citacoes(doc: pm.Documento, apelidos: list[str], padrao: str | None = None) -> list[dict]:
    alt = "|".join(re.escape(a) for a in sorted(apelidos, key=len, reverse=True))
    fim_apelido = r"(?![\w/])(?!\s*n[º°.])(?!\s+Complementar)(?!\s+Estadual)(?!\s+Federal)"
    p1 = re.compile(rf"\barts?\.\s*(?P<lista>{LISTA})(?P<meio>(?:(?!\barts?\.)[^;()\n]){{0,80}}?)"
                    rf"\b(?:da|do|na|no|desta|deste)\s+(?P<alias>{alt}){fim_apelido}")
    p2 = re.compile(rf"(?:\(|;\s*)(?P<alias>{alt}),\s*arts?\.\s*(?P<lista>{LISTA})")
    solto = re.compile(rf"\barts?\.\s*(?P<lista>{LISTA})")
    achados = []
    for b in doc.paragrafos:
        ocupados: list[tuple[int, int]] = []
        for rx in (p1, p2):
            for m in rx.finditer(b.texto):
                ocupados.append(m.span("lista"))
                for n in re.findall(NUM, m.group("lista")):
                    achados.append({"norma": m.group("alias"), "artigo": n, "paragrafo": b.numero})
        for m in solto.finditer(b.texto):
            if not any(a <= m.start("lista") < z for a, z in ocupados):
                for n in re.findall(NUM, m.group("lista")):
                    achados.append({"norma": padrao, "artigo": n, "paragrafo": b.numero,
                                    "trecho": b.texto[max(0, m.start() - 40):m.end() + 60].strip()})
    return achados


def montar(doc: pm.Documento, mapa: dict[str, str], base: Path, padrao: str | None = None) -> tuple[str, dict]:
    arquivos = {a: (base / f) for a, f in mapa.items()}
    textos = {f: ler_fonte(f) for f in set(arquivos.values()) if f.exists()}
    todas = citacoes(doc, list(mapa), padrao)
    cits = [c for c in todas if c["norma"]]
    sem_norma = [c for c in todas if not c["norma"]]
    # agrupa por arquivo (apelidos diferentes da mesma norma se fundem) e artigo
    grupos: dict[tuple[Path, str], dict] = {}
    for c in cits:
        f = arquivos.get(c["norma"])
        chave = (f, c["artigo"].replace(".", ""))
        g = grupos.setdefault(chave, {"normas": [], "artigo": c["artigo"], "paragrafos": []})
        if c["norma"] not in g["normas"]:
            g["normas"].append(c["norma"])
        if c["paragrafo"] not in g["paragrafos"]:
            g["paragrafos"].append(c["paragrafo"])
    linhas = ["# Adendo de fontes literais", "",
              f"Minuta: sha256 `{doc.sha256}`. Texto integral de cada artigo citado, copiado das fontes indicadas.", ""]
    nao_localizados, sem_fonte, truncados, relat = [], [], [], []
    por_arquivo: dict[Path, list] = {}
    for (f, _), g in grupos.items():
        por_arquivo.setdefault(f, []).append(g)
    for f, gs in sorted(por_arquivo.items(), key=lambda kv: str(kv[0])):
        if f is None or f not in textos:
            sem_fonte += [(g, f) for g in gs]
            continue
        sha = hashlib.sha256(f.read_bytes()).hexdigest()
        linhas += [f"## {' / '.join(gs[0]['normas'])} — `{f.name}` (sha256 `{sha[:16]}…`)", ""]
        for g in sorted(gs, key=lambda g: int(re.sub(r"\D", "", g["artigo"]) or 0)):
            achado = artigo_completo(textos[f], g["artigo"])
            if achado is None:
                relat.append({**g, "arquivo": str(f), "localizado": False, "integral": False})
                nao_localizados.append(g)
                continue
            literal, integral = achado
            relat.append({**g, "arquivo": str(f), "localizado": True, "integral": integral, "caracteres": len(literal),
                          "sha256_trecho": hashlib.sha256(literal.encode("utf-8")).hexdigest()})
            if not integral:
                truncados.append(g)
            marca = "" if integral else " — TRUNCADO (sem o artigo seguinte na fonte; não é texto integral)"
            linhas += [f"### Art. {g['artigo']} — citado nos parágrafos {', '.join(map(str, g['paragrafos']))}{marca}", "",
                       *("> " + l if l else ">" for l in literal.split("\n")), ""]
    if sem_norma:
        linhas += ["## Citações sem norma identificável (fora do adendo)", "",
                   "Conferir se são da própria minuta (use --padrao) ou de norma que falta no mapa.", ""]
        for c in sem_norma:
            linhas.append(f"- Art. {c['artigo']}, parágrafo {c['paragrafo']}: «{c['trecho']}»")
        linhas.append("")
    if nao_localizados or sem_fonte:
        linhas += ["## Citações não localizadas nas fontes", ""]
        for g in nao_localizados:
            linhas.append(f"- Art. {g['artigo']} ({' / '.join(g['normas'])}), parágrafos {', '.join(map(str, g['paragrafos']))}: artigo não encontrado no arquivo.")
        for g, f in sem_fonte:
            relat.append({**g, "arquivo": str(f) if f else None, "localizado": False, "integral": False})
            linhas.append(f"- Art. {g['artigo']} ({' / '.join(g['normas'])}), parágrafos {', '.join(map(str, g['paragrafos']))}: "
                          + ("arquivo da fonte ausente." if f else "norma sem arquivo no mapa."))
    resumo = {"sha256_minuta": doc.sha256, "citacoes": len(cits), "artigos": len(grupos),
              "localizados": sum(r["localizado"] for r in relat), "integrais": sum(r.get("integral", False) for r in relat),
              "truncados": len(truncados), "sem_norma": [{k: c[k] for k in ("artigo", "paragrafo", "trecho")} for c in sem_norma],
              "limite_sem_fim": LIMITE_SEM_FIM, "itens": relat}
    return "\n".join(linhas) + "\n", resumo


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("minuta", type=Path)
    ap.add_argument("--mapa", type=Path, required=True, help="JSON {apelido: arquivo relativo a --fontes}")
    ap.add_argument("--fontes", type=Path, default=Path("."))
    ap.add_argument("--padrao", help="apelido para artigos citados sem norma")
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--json", type=Path)
    args = ap.parse_args(argv)
    mapa = json.loads(args.mapa.read_text(encoding="utf-8"))
    if args.padrao and args.padrao not in mapa:
        ap.error(f"--padrao {args.padrao!r} não está no mapa")
    texto, resumo = montar(pm.ler(args.minuta), mapa, args.fontes, args.padrao)
    args.saida.write_text(texto, encoding="utf-8")
    if args.json:
        args.json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    faltam = resumo["artigos"] - resumo["localizados"]
    print(f"{resumo['citacoes']} citações, {resumo['artigos']} artigos distintos, {resumo['localizados']} localizados "
          f"({resumo['integrais']} integrais, {resumo['truncados']} truncados), {faltam} não localizados, "
          f"{len(resumo['sem_norma'])} citações sem norma identificável")
    for r in resumo["itens"]:
        if not r["localizado"]:
            print(f"  não localizado: art. {r['artigo']} ({' / '.join(r['normas'])}), parágrafos {r['paragrafos']}")
        elif not r["integral"]:
            print(f"  truncado: art. {r['artigo']} ({' / '.join(r['normas'])}): o adendo não traz o texto integral")
    return 1 if faltam or resumo["truncados"] else 0


if __name__ == "__main__":
    sys.exit(main())
