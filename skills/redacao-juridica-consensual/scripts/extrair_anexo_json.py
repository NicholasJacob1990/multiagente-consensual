#!/usr/bin/env python3
"""Lê o Anexo de Redações Sugeridas (.docx ou .txt) e devolve os itens em JSON.

Serve para recuperar a fonte de dados do Anexo quando ela se perdeu ou ficou para trás em
relação ao arquivo editado à mão: sem isso, regenerar o Anexo a partir de um JSON antigo apaga
as correções feitas depois. Reconhece o formato GENES:

    REGULAMENTO                                  ← grupo (linha toda em maiúsculas)
    Item 12 – Art. 18, caput e §§ 1º, 2º, 4º e 5º
    Classificação: …
    Fundamento: parecer, parágrafos 25, 26, 44 e 46 a 51.
    Observação: …
    Art. 18. … (NR)                              ← blocos de redação, na ordem

Com ``--base`` (o JSON anterior), conserva os campos que o Anexo não mostra (por exemplo,
``classificacao`` resumida e ``unidades_origem``), atualiza os demais e lista o que mudou.

Exemplos::

    extrair_anexo_json.py Anexo.docx --saida anexo_itens.json
    extrair_anexo_json.py Anexo.docx --base anexo_itens_antigo.json --saida anexo_itens.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verificar_remissoes as vr  # noqa: E402

ITEM_RE = re.compile(r"^\s*Item\s+(\d+)\s*[–—-]\s*(.*\S)\s*$")
ROTULO_RE = re.compile(r"^\s*(Classificação|Fundamento|Observação)\s*:\s*(.*\S)\s*$", re.IGNORECASE)
GRUPO_RE = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ0-9 ,;–—()/-]{4,}$")
CAMPOS = {"classificação": "classificacao_detalhe", "observação": "nota"}


def _paragrafos(fundamento: str) -> list[int]:
    out: list[int] = []
    for r in vr.remissoes_paragrafo(fundamento):
        for ref in r.refs:
            out.extend(range(ref.inicio, ref.fim + 1))
    return sorted(dict.fromkeys(out))


def extrair(path: Path) -> list[dict]:
    linhas = [u.texto.strip() for u in vr.ler_unidades(path) if u.texto.strip()]
    itens: list[dict] = []
    grupo = ""
    atual: dict | None = None
    for k, t in enumerate(linhas):
        m = ITEM_RE.match(t)
        if m:
            atual = {"item": int(m.group(1)), "grupo": grupo, "titulo": m.group(2), "classificacao_detalhe": "",
                     "paragrafos_parecer": [], "nota": "", "blocos": []}
            itens.append(atual)
            continue
        seguinte = linhas[k + 1] if k + 1 < len(linhas) else ""
        if GRUPO_RE.match(t) and ITEM_RE.match(seguinte) and not t.startswith("ANEXO –"):
            grupo = t  # só é grupo a linha em maiúsculas que abre um item; títulos dentro dos blocos ficam nos blocos
            continue
        if atual is None:
            continue
        r = ROTULO_RE.match(t)
        if r:
            rot = r.group(1).lower()
            if rot == "fundamento":
                atual["paragrafos_parecer"] = _paragrafos(r.group(2))
            else:
                atual[CAMPOS[rot]] = r.group(2)
            continue
        atual["blocos"].append(t)
    return itens


def _chave(t: str) -> str:
    return " ".join(vr.norm(t).casefold().split())


def _resumo_classificacao(detalhe: str) -> str:
    """'correção necessária (parágrafo 169, ii)' → 'Correção necessária'; vazio quando não reconhece."""
    d = detalhe.casefold()
    if "corre" in d and "necess" in d:
        return "Correção necessária"
    if "recomenda" in d:
        return "Recomendação"
    if "sugest" in d:
        return "Sugestão"
    return ""


def mesclar(novos: list[dict], base: list[dict]) -> tuple[list[dict], list[str]]:
    """Conserva os campos da base que o Anexo não mostra e relata as diferenças por item."""
    por_item = {b["item"]: b for b in base}
    out, dif = [], []
    for n in novos:
        b = por_item.get(n["item"])
        if b is None:
            dif.append(f"item {n['item']}: novo (não estava na base)")
            out.append(n)
            continue
        m = dict(b)
        for k, v in n.items():
            if k == "grupo" and b.get("grupo"):
                if _chave(b["grupo"]) == _chave(v):
                    continue  # mesmo grupo: a base o tem em caixa normal
                dif.append(f"item {n['item']}: grupo mudou ({b['grupo']} → {v})")
                m[k] = v
                continue
            if b.get(k) != v:
                dif.append(f"item {n['item']}: {k} mudou")
            m[k] = v
        # a classificação resumida da base depende da detalhada: se a detalhada mudou, refaz a resumida
        if "classificacao" in b and b.get("classificacao_detalhe") != n.get("classificacao_detalhe"):
            nova = _resumo_classificacao(n.get("classificacao_detalhe", ""))
            if nova != b["classificacao"]:
                dif.append(f"item {n['item']}: classificacao refeita ({b['classificacao']} → {nova or 'indefinida'})")
            m["classificacao"] = nova
        out.append(m)
    for k in sorted(set(por_item) - {n["item"] for n in novos}):
        dif.append(f"item {k}: está na base, mas não no Anexo")
    return out, dif


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("anexo", type=Path)
    ap.add_argument("--base", type=Path, help="JSON anterior do Anexo, para conservar campos e listar diferenças")
    ap.add_argument("--saida", type=Path, help="grava o JSON; padrão: saída padrão")
    args = ap.parse_args(argv)
    for p in (args.anexo, args.base):
        if p is not None and not p.exists():
            print(f"arquivo não encontrado: {p}", file=sys.stderr)
            return 2
    itens = extrair(args.anexo)
    dif: list[str] = []
    if args.base:
        itens, dif = mesclar(itens, json.loads(args.base.read_text(encoding="utf-8")))
    texto = json.dumps(itens, ensure_ascii=False, indent=1) + "\n"
    if args.saida:
        args.saida.write_text(texto, encoding="utf-8")
        print(f"{len(itens)} itens gravados em {args.saida}; {sum(len(i['blocos']) for i in itens)} blocos")
    else:
        print(texto, end="")
    for d in dif:
        print(f"- {d}", file=sys.stderr if not args.saida else sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
