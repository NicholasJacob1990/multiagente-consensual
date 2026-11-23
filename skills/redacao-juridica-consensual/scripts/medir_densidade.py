#!/usr/bin/env python3
"""Mede a densidade de um parecer ou de uma peça e compara duas versões.

"Encurtar as frases" e "reduzir a densidade" são coisas diferentes: uma reescrita
pode derrubar a média de palavras por frase e manter quase todo o volume. Quando
o pedido é "menos denso", "mais enxuto" ou "para leitor não técnico", a medida
que responde é o VOLUME (palavras e parágrafos do corpo), ao lado do ritmo
(frases longas, parágrafos de uma frase só). Este script mede os dois e, com
``--meta-reducao``, acusa a versão que não cortou o que foi pedido.

Conta só o corpo: do início até o fecho ("É o parecer", "Nestes termos" ou
``--fim``), ou até o título de Referências ou de Anexo, o que vier primeiro.
Ementa transcrita e citação recuada (linha iniciada por ``>`` ou ``EMENTA:``)
entram no volume, mas não na medida de frase.

Uso::

    medir_densidade.py NOVA.(docx|md|txt) [--anterior ANTERIOR] [--meta-reducao 25]
                       [--fim "É o parecer"] [--json SAIDA]

Código de saída: 0; 1 se ``--meta-reducao`` foi dada e a redução de palavras ficou
abaixo dela; 2 erro de uso.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

FIM_PADRAO = (r"^\s*(\d+\.\s*)?(\*\*)?É o parecer", r"^\s*(\d+\.\s*)?(\*\*)?Nestes termos", r"^\s*(\d+\.\s*)?(\*\*)?Termos em que")
SECAO_FINAL = re.compile(r"^\s*(#+\s*)?(\*\*)?(Refer[êe]ncias\b|Anexo\b|ANEXO\b)")
FRASE = re.compile(r"(?<=[.;:?!])\s+(?=[A-ZÀ-Ú“\"])")


def ler(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import docx_para_md  # noqa: E402
        return docx_para_md.converter(path)
    return path.read_text(encoding="utf-8")


def corpo(texto: str, fim: str | None = None) -> list[str]:
    padroes = [re.compile(re.escape(fim))] if fim else [re.compile(p) for p in FIM_PADRAO]
    blocos = []
    for linha in texto.split("\n"):
        l = linha.strip()
        if not l or l.startswith("<!--"):
            continue
        if SECAO_FINAL.match(l):
            break
        if l.startswith("#"):
            continue
        blocos.append(l)
        if any(p.search(l) for p in padroes):
            break
    return blocos


def _sem_numero(b: str) -> str:
    return re.sub(r"^\d+\.\s+", "", b)


def _citacao(b: str) -> bool:
    return b.startswith(">") or _sem_numero(b).lstrip("*").startswith("EMENTA:")


def frases(b: str) -> list[int]:
    limpo = re.sub(r"\([^()]*\)", "", _sem_numero(b))
    return [n for n in (len(f.split()) for f in FRASE.split(limpo)) if n > 3]


def medir(texto: str, fim: str | None = None) -> dict:
    bl = corpo(texto, fim)
    prosa = [b for b in bl if not _citacao(b)]
    fr = [n for b in prosa for n in frases(b)]
    pal = [len(_sem_numero(b).split()) for b in bl]
    return {
        "paragrafos": len(bl),
        "palavras": sum(pal),
        "frases": len(fr),
        "media_frase": round(statistics.mean(fr), 1) if fr else 0.0,
        "frases_acima_60": sum(n > 60 for n in fr),
        "frases_acima_80": sum(n > 80 for n in fr),
        "paragrafos_frase_unica_acima_70": sum(1 for b in prosa if len(frases(b)) == 1 and len(_sem_numero(b).split()) > 70),
        "paragrafos_acima_90": sum(n > 90 for n in pal),
    }


ROTULOS = [("paragrafos", "Parágrafos do corpo"), ("palavras", "Palavras do corpo"), ("media_frase", "Média de palavras por frase"),
           ("frases_acima_60", "Frases com mais de 60 palavras"), ("frases_acima_80", "Frases com mais de 80 palavras"),
           ("paragrafos_frase_unica_acima_70", "Parágrafos de frase única com mais de 70 palavras"),
           ("paragrafos_acima_90", "Parágrafos com mais de 90 palavras")]


def comparar(ant: dict | None, nova: dict, meta: float | None) -> dict:
    r = {"nova": nova, "anterior": ant, "meta_reducao": meta, "reducao_palavras_pct": None, "ok": True, "aviso": ""}
    if ant and ant["palavras"]:
        red = round(100 * (ant["palavras"] - nova["palavras"]) / ant["palavras"], 1)
        r["reducao_palavras_pct"] = red
        if meta is not None and red < meta:
            r["ok"] = False
            r["aviso"] = (f"redução de {red}% nas palavras do corpo, abaixo da meta de {meta:g}%: "
                          "as frases podem ter encurtado, mas o volume ficou; cortar conteúdo, não só dividir frases")
        elif nova["media_frase"] < ant["media_frase"] * 0.8 and red < 15:
            r["aviso"] = (f"as frases encurtaram ({ant['media_frase']} → {nova['media_frase']}), mas o volume caiu só {red}%: "
                          "se o pedido era reduzir a densidade, falta cortar conteúdo")
    return r


def relatorio_md(r: dict) -> str:
    ant, nova = r["anterior"], r["nova"]
    L = ["## Densidade", ""]
    if ant:
        L += ["| Medida | Anterior | Nova |", "|---|---|---|"]
        L += [f"| {rot} | {ant[k]} | {nova[k]} |" for k, rot in ROTULOS]
        L += ["", f"Redução de palavras do corpo: {r['reducao_palavras_pct']}%."]
    else:
        L += ["| Medida | Valor |", "|---|---|"] + [f"| {rot} | {nova[k]} |" for k, rot in ROTULOS]
    if r["aviso"]:
        L += ["", ("**Meta não atingida:** " if not r["ok"] else "Aviso: ") + r["aviso"] + "."]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("nova", type=Path)
    ap.add_argument("--anterior", type=Path)
    ap.add_argument("--meta-reducao", type=float, help="redução mínima de palavras do corpo, em %% (pedido de condensação)")
    ap.add_argument("--fim", help="trecho que marca o fecho do corpo")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    if a.meta_reducao is not None and not a.anterior:
        print("erro: --meta-reducao exige --anterior", file=sys.stderr)
        return 2
    try:
        nova = medir(ler(a.nova), a.fim)
        ant = medir(ler(a.anterior), a.fim) if a.anterior else None
    except (OSError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    r = comparar(ant, nova, a.meta_reducao)
    print(relatorio_md(r))
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
