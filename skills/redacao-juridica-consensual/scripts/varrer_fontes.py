#!/usr/bin/env python3
"""Varre os normativos locais (estatuto, regimentos, políticas) atrás dos termos da controvérsia
e lista, por arquivo, os artigos ou itens em que aparecem, com o trecho.

Antes de afirmar quem decide, o que a norma interna exige ou que um artigo "não trata do tema",
ler a íntegra; esta varredura aponta onde ler. No caso de referência, o art. 45 do Estatuto
(pessoal efetivo por concurso) só apareceu quando o usuário perguntou, e a competência para
eleger Diretores (art. 30) foi atribuída ao órgão errado.

A busca ignora acentos e caixa. Cada termo é uma expressão regular simples ("concurso",
"cargos? em comiss", "eleg\\w+ pelo Conselho"). Lê .md, .txt e .docx; com o mesmo nome em mais de
um formato, usa o .md. Os PDFs ficam de fora (use a conversão .md que acompanha a fonte).

Exemplos::

    varrer_fontes.py fontes/ concurso carreira efetivo "comiss" "eleg\\w+ pel[oa]"
    varrer_fontes.py fontes/ --termos-de termos.txt --saida varredura.md
"""

from __future__ import annotations

import argparse
import re
import sys
import unicodedata
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
# "Art. 45.", "Art.45", "**Art. 21 -**", "Art. 2º", e itens de regimento "8.6", "5.9"
MARCA_RE = re.compile(r"(?:\*\*)?\b(Art(?:igo)?\.?\s*\d+[º°]?(?:-[A-Z])?)|(?<![\d.,])(\d{1,2}\.\d{1,2})(?=\s+[A-ZÁÉÍÓÚ])")


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


def ler_texto(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        with zipfile.ZipFile(path) as z:
            root = ET.fromstring(z.read("word/document.xml"))
        return "\n".join("".join(t.text or "" for t in p.iter(W + "t")) for p in root.iter(W + "p"))
    return path.read_text(encoding="utf-8", errors="replace")


def arquivos(alvos: list[Path]) -> list[Path]:
    out: dict[tuple[Path, str], Path] = {}
    for a in alvos:
        cands = [a] if a.is_file() else sorted(p for p in a.rglob("*") if p.is_file())
        for p in cands:
            if p.suffix.lower() not in (".md", ".txt", ".docx"):
                continue
            chave = (p.parent, p.stem.replace(".conversao", ""))
            if chave in out and out[chave].suffix.lower() == ".md":
                continue
            out[chave] = p
    return sorted(out.values())


def segmentos(texto: str) -> list[tuple[str, str]]:
    """Divide o texto pelas marcas de artigo ou item; devolve (marca, texto do segmento)."""
    plano = re.sub(r"[ \t]+", " ", texto)
    marcas = list(MARCA_RE.finditer(plano))
    if not marcas:
        return [("(sem divisão)", plano)]
    out = [("(preâmbulo)", plano[:marcas[0].start()])] if marcas[0].start() > 0 else []
    for k, m in enumerate(marcas):
        fim = marcas[k + 1].start() if k + 1 < len(marcas) else len(plano)
        rot = (m.group(1) or m.group(2)).replace("Art.", "Art. ").replace("  ", " ")
        out.append((rot.strip(), plano[m.start():fim]))
    return out


def varrer(alvos: list[Path], termos: list[str], contexto: int = 220) -> list[dict]:
    rx = [(t, re.compile(sem_acento(t))) for t in termos]
    achados = []
    for arq in arquivos(alvos):
        for marca, seg in segmentos(ler_texto(arq)):
            plano = sem_acento(seg)
            hits = [(t, m) for t, r in rx for m in [r.search(plano)] if m]
            if not hits:
                continue
            ini = max(0, hits[0][1].start() - contexto // 2)
            trecho = re.sub(r"\s+", " ", seg[ini:ini + contexto]).strip()
            achados.append({"arquivo": arq.name, "dispositivo": marca, "termos": [t for t, _ in hits], "trecho": trecho})
    return achados


def relatorio(achados: list[dict], termos: list[str]) -> str:
    linhas = [f"# Varredura de fontes — termos: {', '.join(termos)}", ""]
    atual = None
    for a in achados:
        if a["arquivo"] != atual:
            atual = a["arquivo"]
            linhas += ["", f"## {atual}", ""]
        linhas.append(f"- **{a['dispositivo']}** ({', '.join(a['termos'])}): …{a['trecho']}…")
    if not achados:
        linhas.append("Nenhum termo encontrado. Ausência na varredura não prova ausência na norma: conferir a íntegra.")
    return "\n".join(linhas).strip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("alvo", type=Path, help="pasta ou arquivo de fontes")
    ap.add_argument("termos", nargs="*", help="termos ou expressões regulares simples")
    ap.add_argument("--termos-de", type=Path, help="arquivo com um termo por linha")
    ap.add_argument("--contexto", type=int, default=220, help="caracteres de trecho por achado")
    ap.add_argument("--saida", type=Path, help="grava o relatório em Markdown")
    args = ap.parse_args(argv)
    termos = list(args.termos)
    if args.termos_de:
        termos += [t.strip() for t in args.termos_de.read_text(encoding="utf-8").splitlines() if t.strip()]
    if not termos:
        print("informe ao menos um termo", file=sys.stderr)
        return 2
    if not args.alvo.exists():
        print(f"não encontrado: {args.alvo}", file=sys.stderr)
        return 2
    achados = varrer([args.alvo], termos, args.contexto)
    texto = relatorio(achados, termos)
    if args.saida:
        args.saida.write_text(texto, encoding="utf-8")
        print(f"{len(achados)} trechos em {len({a['arquivo'] for a in achados})} arquivos; relatório em {args.saida}")
    else:
        print(texto, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
