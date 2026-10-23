#!/usr/bin/env python3
"""Monta o pacote de auditoria travado por hash e confere a resposta do auditor.

O pacote reúne instruções, dossiê, adendo de fontes literais e minuta, cada parte
delimitada e com seu SHA-256. A primeira linha da resposta do auditor tem de
repetir o hash da minuta: resposta sem ele, ou com outro, foi dada sobre outra
versão (ou sobre anexo desatualizado) e é descartada. Isso já aconteceu duas
vezes no mesmo caso; o hash torna o erro detectável na hora.

Com ``--anterior``, monta o pacote só com as diferenças (parágrafos alterados ou
novos, com o vizinho de cada lado), para rodadas intermediárias mais baratas.

Exemplos::

    pacote_auditoria.py montar --minuta v30.md --dossie dossie.md --adendo adendo.md --instrucoes prompt.md --saida pacote.md
    pacote_auditoria.py montar --minuta v31.md --anterior v30.md --instrucoes prompt.md --saida pacote_diff.md
    pacote_auditoria.py verificar --pacote pacote.md --resposta resposta_gemini.md
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402

CONTRATO = "pacote_auditoria_v1"
CHARS_POR_TOKEN = 3.5
ALERTA_TOKENS = 120_000
HASH_RE = re.compile(r"HASH_RECEBIDO:\s*`?([0-9a-f]{64})`?", re.IGNORECASE)
CAB_RE = re.compile(r"^SHA-256 da minuta: ([0-9a-f]{64})$", re.M)

INSTRUCOES_PADRAO = """Você é auditor jurídico independente. Leia integralmente a minuta e confira cada afirmação
de direito no adendo de fontes literais; o que não estiver no adendo, trate como não verificado
e diga isso, em vez de presumir. Não afirme que um dispositivo não existe, não tem incisos ou não
alcança um caso sem ter lido o texto integral dele no adendo. Separe certeza de estimativa."""


def parte(nome: str, texto: str) -> str:
    sha = pm.sha256_texto(texto)
    return f"===== INÍCIO: {nome} (sha256 {sha}) =====\n{texto.rstrip()}\n===== FIM: {nome} =====\n"


def diferencas(anterior: pm.Documento, atual: pm.Documento, palavras_indice: int = 14) -> str:
    mapa = pm.alinhar_paragrafos(anterior, atual)
    inverso = {v: k for k, v in mapa.items()}
    antigos, novos = anterior.por_numero(), atual.por_numero()
    alterados = [n for n in novos if n not in inverso or antigos[inverso[n]] != novos[n]]
    removidos = [n for n in antigos if n not in mapa]
    mostrar = sorted({v for n in alterados for v in (n - 1, n, n + 1) if v in novos})
    linhas = [
        f"Versão anterior: sha256 {anterior.sha256}. Parágrafos alterados ou novos: "
        + (", ".join(map(str, alterados)) or "nenhum")
        + (f". Parágrafos suprimidos da anterior: {', '.join(map(str, removidos))}" if removidos else "")
        + ". Os demais parágrafos estão idênticos aos da versão anterior; a versão integral está disponível a pedido.",
        "",
    ]
    for n in mostrar:
        if n in alterados:
            if n in inverso:
                linhas += [f"[{n} — ALTERADO; era o {inverso[n]}] ANTES: {antigos[inverso[n]]}", f"[{n}] DEPOIS: {novos[n]}", ""]
            else:
                linhas += [f"[{n} — NOVO] {novos[n]}", ""]
        else:
            linhas += [f"[{n} — contexto, sem alteração] {novos[n]}", ""]
    for n in removidos:  # reescritos a ponto de não alinhar, ou suprimidos: o auditor precisa do texto anterior
        linhas += [f"[{n} da versão anterior — SUPRIMIDO OU REESCRITO EM OUTRO PARÁGRAFO] {antigos[n]}", ""]
    # índice da versão integral: permite conferir remissões a parágrafos que não vieram no pacote
    linhas += ["ÍNDICE DA VERSÃO INTEGRAL (primeiras palavras de cada parágrafo, para conferir remissões):", ""]
    for n, t in novos.items():
        ws = pm.sem_negrito(t).split()
        linhas.append(f"[{n}] {' '.join(ws[:palavras_indice])}{' …' if len(ws) > palavras_indice else ''}")
    return "\n".join(linhas)


def montar(minuta: Path, instrucoes: str, dossie: Path | None = None, adendo: Path | None = None,
           anterior: Path | None = None, formato_resposta: str | None = None) -> str:
    doc = pm.ler(minuta)
    blocos = [
        f"# Pacote de auditoria — {CONTRATO}",
        "",
        f"SHA-256 da minuta: {doc.sha256}",
        "",
        "Regra de recebimento: a primeira linha da sua resposta deve ser exatamente",
        f"`HASH_RECEBIDO: {doc.sha256}`",
        "Resposta sem essa linha, ou com outro hash, será descartada como feita sobre outra versão.",
        "",
        parte("INSTRUÇÕES", instrucoes),
    ]
    if formato_resposta:
        blocos.append(parte("FORMATO DA RESPOSTA", formato_resposta))
    if dossie:
        blocos.append(parte("DOSSIÊ", dossie.read_text(encoding="utf-8")))
    if adendo:
        blocos.append(parte("ADENDO DE FONTES LITERAIS", adendo.read_text(encoding="utf-8")))
    if anterior:
        blocos.append(parte("MINUTA — SÓ AS DIFERENÇAS", diferencas(pm.ler(anterior), doc)))
    else:
        blocos.append(parte("MINUTA", doc.bruto))
    return "\n".join(blocos)


def hash_do_pacote(texto: str) -> str | None:
    m = CAB_RE.search(texto)
    return m.group(1) if m else None


def verificar(resposta: str, esperado: str) -> tuple[bool, str]:
    primeiras = [l for l in resposta.strip().split("\n") if l.strip()][:3]
    for l in primeiras:
        m = HASH_RE.search(l)
        if m:
            if m.group(1).lower() == esperado:
                return True, "hash confere"
            return False, f"hash divergente: a resposta cita {m.group(1)[:16]}…, esperado {esperado[:16]}…"
    return False, "a resposta não repete o hash nas primeiras linhas"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("montar")
    m.add_argument("--minuta", type=Path, required=True)
    m.add_argument("--instrucoes", type=Path, help="prompt do auditor; padrão: instruções mínimas de auditoria cega")
    m.add_argument("--formato-resposta", type=Path)
    m.add_argument("--dossie", type=Path)
    m.add_argument("--adendo", type=Path)
    m.add_argument("--anterior", type=Path, help="monta só com as diferenças em relação a esta versão")
    m.add_argument("--saida", type=Path, required=True)
    v = sub.add_parser("verificar")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--pacote", type=Path)
    g.add_argument("--hash")
    v.add_argument("--resposta", type=Path, required=True)
    args = ap.parse_args(argv)

    if args.cmd == "montar":
        instr = args.instrucoes.read_text(encoding="utf-8") if args.instrucoes else INSTRUCOES_PADRAO
        fmt = args.formato_resposta.read_text(encoding="utf-8") if args.formato_resposta else None
        texto = montar(args.minuta, instr, args.dossie, args.adendo, args.anterior, fmt)
        args.saida.write_text(texto, encoding="utf-8")
        tokens = int(len(texto) / CHARS_POR_TOKEN)
        print(f"pacote gravado em {args.saida}: {len(texto):,} caracteres, ~{tokens:,} tokens; hash da minuta {hash_do_pacote(texto)}")
        if tokens > ALERTA_TOKENS:
            print(f"atenção: acima de {ALERTA_TOKENS:,} tokens; sondar créditos antes, usar esforço medium em rodada "
                  "intermediária ou montar só as diferenças com --anterior")
        return 0
    esperado = args.hash or hash_do_pacote(args.pacote.read_text(encoding="utf-8"))
    if not esperado:
        print("pacote sem linha 'SHA-256 da minuta'", file=sys.stderr)
        return 2
    ok, msg = verificar(args.resposta.read_text(encoding="utf-8"), esperado.lower())
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
