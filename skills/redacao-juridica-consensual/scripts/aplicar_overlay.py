#!/usr/bin/env python3
"""Aplica alterações controladas a um DOCX revisado por outra pessoa, sem aceitar nem rejeitar as
revisões dela, e gera a visão "tudo aceito".

Substitui o bloco de código repetido a cada rodada (localizar o parágrafo numerado, conferir que o
trecho é único, aplicar o diff por palavras, contar palavras, reescrever respostas a comentários,
validar e gerar a prévia). Requer ``lxml``.

Arquivo de alterações (JSON)::

    {
      "paragrafos": [
        {"n": 13, "texto": "novo texto integral do parágrafo 13"},
        {"n": 46, "acrescentar": " Frase acrescida ao fim."},
        {"n": 51, "antes": "trecho único atual", "depois": "trecho novo"}
      ],
      "respostas": [
        {"id": "221", "texto": "nova resposta integral"},
        {"id": "235", "antes": "trecho da resposta", "depois": "trecho novo"}
      ]
    }

``n`` é o número do parágrafo na numeração automática do Word (parágrafos com ``numPr`` e texto
visível). Cada parágrafo alterado tem de ficar com até ``--max-palavras`` palavras (padrão 120),
salvo ``"permitir_longo": true`` no item.

Exemplos::

    aplicar_overlay.py parecer_v21.docx parecer_v22.docx --alteracoes v22.json --autor "Nicholas Jacob" \\
        --aceito aceito_v22.docx --original revisao_patricia.docx --validador ~/.../docx/scripts/office/validate.py
    aplicar_overlay.py --aceitar parecer_v22.docx aceito_v22.docx
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lxml import etree
    import overlay_docx as O  # noqa: E402
except ImportError:  # pragma: no cover - depende do ambiente
    print("aplicar_overlay.py requer lxml: pip install lxml", file=sys.stderr)
    raise


def _ler(z: zipfile.ZipFile, nome: str):
    try:
        return etree.fromstring(z.read(nome))
    except KeyError:
        return None


def aplicar(entrada: Path, saida: Path, alteracoes: dict, autor: str, data: str, max_palavras: int = 120) -> list[str]:
    """Aplica as alterações e grava ``saida``; devolve o relatório, uma linha por alteração."""
    rel: list[str] = []
    with zipfile.ZipFile(entrada) as z:
        doc = _ler(z, "word/document.xml")
        com = _ler(z, "word/comments.xml")
        infos = z.infolist()
        dados = {i.filename: z.read(i.filename) for i in infos}
    ctx = O.Ctx(doc, autor, data)
    num = O.paragrafos_numerados(doc.find(O.w("body")))
    longos = []
    for alt in alteracoes.get("paragrafos", []):
        n = int(alt["n"])
        if n not in num:
            raise ValueError(f"parágrafo {n} não existe (o documento tem {len(num)} parágrafos numerados)")
        p = num[n]
        atual = O.visible(p)
        if "texto" in alt:
            antes, depois = atual.strip(), alt["texto"]
        elif "acrescentar" in alt:
            antes = atual.rstrip()[-60:]
            depois = antes + alt["acrescentar"]
        else:
            antes, depois = alt["antes"], alt["depois"]
        if atual.count(antes) != 1:
            raise ValueError(f"§ {n}: o trecho aparece {atual.count(antes)} vezes: «{antes[:70]}»")
        O.normalize_runs(p)
        O.replace(p, antes, depois, ctx)
        palavras = len(O.visible(p).split())
        rel.append(f"§ {n}: {palavras} palavras")
        if palavras > max_palavras and not alt.get("permitir_longo"):
            longos.append(f"§ {n} ({palavras})")
    if longos:
        raise ValueError(f"acima de {max_palavras} palavras: {', '.join(longos)}; enxugue ou marque permitir_longo")
    for r in alteracoes.get("respostas", []):
        if com is None:
            raise ValueError("o documento não tem comentários")
        O.responder(com, r["id"], ctx, texto=r.get("texto"), antes=r.get("antes"), depois=r.get("depois"))
        rel.append(f"resposta {r['id']}: reescrita" if "texto" in r else f"resposta {r['id']}: trecho substituído")
    dados["word/document.xml"] = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    if com is not None:
        dados["word/comments.xml"] = etree.tostring(com, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in infos:
            zout.writestr(i, dados[i.filename])
    return rel


def validar(validador: Path, docx: Path, original: Path, autor: str) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, str(validador), str(docx), "--original", str(original), "--author", autor],
                          capture_output=True, text=True)
    ultima = (proc.stdout.strip().splitlines() or proc.stderr.strip().splitlines() or [""])[-1]
    return proc.returncode == 0 and "PASSED" in proc.stdout, ultima


def pdf(docx: Path, pasta: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pasta), str(docx)],
                   capture_output=True, text=True)
    alvo = pasta / (docx.stem + ".pdf")
    return alvo if alvo.exists() else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--aceitar", action="store_true", help="só gera a visão tudo aceito de ENTRADA em SAIDA")
    ap.add_argument("--alteracoes", type=Path, help="JSON com as alterações (ver o cabeçalho)")
    ap.add_argument("--autor", default="Nicholas Jacob")
    ap.add_argument("--data", default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
    ap.add_argument("--max-palavras", type=int, default=120)
    ap.add_argument("--aceito", type=Path, help="grava também a visão tudo aceito")
    ap.add_argument("--pdf", action="store_true", help="com --aceito, converte a visão aceita em PDF (LibreOffice)")
    ap.add_argument("--original", type=Path, help="DOCX de referência para o validador")
    ap.add_argument("--validador", type=Path, help="validate.py da skill docx (confere que só o autor alterou)")
    args = ap.parse_args(argv)

    if not args.entrada.exists():
        print(f"arquivo não encontrado: {args.entrada}", file=sys.stderr)
        return 2
    if args.aceitar:
        O.aceitar_tudo(args.entrada, args.saida)
        print(f"tudo aceito: {args.saida}")
        return 0
    if not args.alteracoes:
        print("informe --alteracoes (ou --aceitar)", file=sys.stderr)
        return 2
    alteracoes = json.loads(args.alteracoes.read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as tmp:
        provisorio = Path(tmp) / args.saida.name
        try:
            rel = aplicar(args.entrada, provisorio, alteracoes, args.autor, args.data, args.max_palavras)
        except (ValueError, AssertionError) as e:
            print(f"RECUSADO: {e}; nada foi gravado.")
            return 1
        shutil.copy(provisorio, args.saida)
    for linha in rel:
        print(linha)
    ok = True
    if args.validador and args.original:
        ok, msg = validar(args.validador, args.saida, args.original, args.autor)
        print(f"validação: {msg}")
    if args.aceito:
        O.aceitar_tudo(args.saida, args.aceito)
        print(f"tudo aceito: {args.aceito}")
        if args.pdf:
            alvo = pdf(args.aceito, args.aceito.parent)
            print(f"PDF: {alvo}" if alvo else "PDF: LibreOffice não encontrado")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
