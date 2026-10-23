#!/usr/bin/env python3
"""Registro cumulativo de achados de revisão e auditoria (``registro_achados_v1``).

Serve a qualquer trabalho — parecer, petição, recurso, minuta decisória — revisado
em várias rodadas. Cada achado conserva um estado (aberto, parcial, resolvido,
rejeitado, superado) e o histórico de quem o mudou, em que versão (hash) e por quê.
Um achado já resolvido, rejeitado ou superado só reabre com motivo novo
(regressão, fonte nova ou falha identificada na solução); repetir a crítica anterior
não reabre. Achados não materiais (preferência editorial) não impedem o encerramento.

Exemplos::

    achados.py registrar --registro achados.json --minuta v31.md --rodada 3 --entrada auditoria_gemini.json
    achados.py atualizar --registro achados.json --minuta v31.md --id A04 --estado resolvido --razao "§ 48 corrigido"
    achados.py verificar --registro achados.json --minuta v31.md
    achados.py resumo    --registro achados.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any

CONTRATO = "registro_achados_v1"
ESTADOS = ("aberto", "parcial", "resolvido", "rejeitado", "superado")
FECHADOS = ("resolvido", "rejeitado", "superado")
MOTIVOS_REABERTURA = ("regressao", "fonte_nova", "falha_identificada")


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto or "").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", texto).strip().lower()


def novo_registro() -> dict:
    return {"contrato": CONTRATO, "achados": []}


def carregar(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else novo_registro()


def gravar(path: Path, reg: dict) -> None:
    path.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _mesmo(a: dict, b: dict) -> bool:
    """O mesmo achado: id estável informado, ou mesmo trecho e mesma descrição normalizados."""
    if b.get("id") and b["id"] == a["id"]:
        return True
    if b.get("chave") and b["chave"] == a.get("chave"):
        return True
    return bool(b.get("trecho")) and normalizar(b["trecho"]) == normalizar(a.get("trecho")) and \
        normalizar(b.get("descricao")) == normalizar(a.get("descricao"))


def registrar(reg: dict, entrada: list[dict], hash_minuta: str, rodada: int | str) -> list[dict]:
    """Incorpora os achados de uma rodada. Devolve o que aconteceu com cada um."""
    eventos = []
    for novo in entrada:
        existente = next((a for a in reg["achados"] if _mesmo(a, novo)), None)
        por = novo.get("por", "?")
        if existente is None:
            aid = f"A{len(reg['achados']) + 1:02d}"
            reg["achados"].append({
                "id": aid,
                "chave": novo.get("chave"),
                "descricao": novo.get("descricao", ""),
                "paragrafo": novo.get("paragrafo"),
                "trecho": novo.get("trecho", ""),
                "material": novo.get("material", True),
                "classificacao": novo.get("classificacao"),
                "estado": "aberto",
                "historico": [{"rodada": rodada, "hash_minuta": hash_minuta, "estado": "aberto", "por": por,
                               "razao": novo.get("fundamento", "")}],
            })
            eventos.append({"id": aid, "evento": "novo"})
            continue
        if existente["estado"] not in FECHADOS:
            existente["historico"].append({"rodada": rodada, "hash_minuta": hash_minuta, "estado": existente["estado"],
                                           "por": por, "razao": "reiterado"})
            eventos.append({"id": existente["id"], "evento": "reiterado"})
            continue
        reab = novo.get("reabertura") or {}
        if reab.get("motivo") in MOTIVOS_REABERTURA and str(reab.get("explicacao", "")).strip():
            existente["estado"] = "aberto"
            existente["historico"].append({"rodada": rodada, "hash_minuta": hash_minuta, "estado": "aberto", "por": por,
                                           "razao": f"reaberto por {reab['motivo']}: {reab['explicacao']}"})
            eventos.append({"id": existente["id"], "evento": "reaberto", "motivo": reab["motivo"]})
        else:
            existente["historico"].append({"rodada": rodada, "hash_minuta": hash_minuta, "estado": existente["estado"],
                                           "por": por, "razao": "reabertura recusada: sem regressão, fonte nova ou falha identificada"})
            eventos.append({"id": existente["id"], "evento": "reabertura_recusada", "estado": existente["estado"]})
    return eventos


def atualizar(reg: dict, aid: str, estado: str, hash_minuta: str, razao: str, por: str = "redator", rodada: Any = None) -> dict:
    if estado not in ESTADOS:
        raise SystemExit(f"estado inválido: {estado}")
    a = next((a for a in reg["achados"] if a["id"] == aid), None)
    if a is None:
        raise SystemExit(f"achado inexistente: {aid}")
    if estado in ("rejeitado", "superado", "parcial") and not razao.strip():
        raise SystemExit(f"o estado {estado} exige razão (fundamento da rejeição, versão que superou ou o que falta)")
    a["estado"] = estado
    a["historico"].append({"rodada": rodada, "hash_minuta": hash_minuta, "estado": estado, "por": por, "razao": razao})
    return a


def verificar(reg: dict, minuta: str) -> list[dict]:
    """Confronta os estados com o texto atual pelo trecho que motivou cada achado."""
    out = []
    texto = normalizar(minuta)
    for a in reg["achados"]:
        t = normalizar(a.get("trecho"))
        if not t:
            continue
        presente = t in texto
        if a["estado"] == "resolvido" and presente:
            out.append({"id": a["id"], "alerta": "marcado como resolvido, mas o trecho que o motivou continua no texto: conferir regressão"})
        elif a["estado"] in ("aberto", "parcial") and not presente:
            out.append({"id": a["id"], "alerta": "o trecho que o motivou não está mais no texto: conferir se foi resolvido e atualizar o estado"})
    return out


def resumo(reg: dict) -> dict:
    cont = {e: 0 for e in ESTADOS}
    for a in reg["achados"]:
        cont[a["estado"]] += 1
    abertos_materiais = [a["id"] for a in reg["achados"] if a["estado"] in ("aberto", "parcial") and a.get("material", True)]
    return {"por_estado": cont, "abertos_materiais": abertos_materiais,
            "pode_encerrar": not abertos_materiais,
            "mensagem": ("sem achados materiais abertos: a revisão pode encerrar sem nova versão de mérito"
                         if not abertos_materiais else f"achados materiais abertos: {', '.join(abertos_materiais)}")}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("registrar")
    r.add_argument("--registro", type=Path, required=True)
    r.add_argument("--minuta", type=Path, required=True)
    r.add_argument("--rodada", required=True)
    r.add_argument("--entrada", type=Path, required=True, help='JSON: [{"descricao", "trecho", "paragrafo", "material", "por", "reabertura"?}]')
    u = sub.add_parser("atualizar")
    u.add_argument("--registro", type=Path, required=True)
    u.add_argument("--minuta", type=Path, required=True)
    u.add_argument("--id", required=True)
    u.add_argument("--estado", required=True, choices=ESTADOS)
    u.add_argument("--razao", default="")
    u.add_argument("--por", default="redator")
    u.add_argument("--rodada")
    v = sub.add_parser("verificar")
    v.add_argument("--registro", type=Path, required=True)
    v.add_argument("--minuta", type=Path, required=True)
    s = sub.add_parser("resumo")
    s.add_argument("--registro", type=Path, required=True)
    args = ap.parse_args(argv)

    reg = carregar(args.registro)
    if args.cmd == "registrar":
        entrada = json.loads(args.entrada.read_text(encoding="utf-8"))
        eventos = registrar(reg, entrada.get("achados", entrada) if isinstance(entrada, dict) else entrada,
                            sha256_texto(args.minuta.read_text(encoding="utf-8")), args.rodada)
        gravar(args.registro, reg)
        for e in eventos:
            print(f"{e['id']}: {e['evento']}" + (f" ({e.get('motivo') or e.get('estado')})" if e.get("motivo") or e.get("estado") else ""))
        return 0
    if args.cmd == "atualizar":
        a = atualizar(reg, args.id, args.estado, sha256_texto(args.minuta.read_text(encoding="utf-8")), args.razao, args.por, args.rodada)
        gravar(args.registro, reg)
        print(f"{a['id']}: {a['estado']}")
        return 0
    if args.cmd == "verificar":
        alertas = verificar(reg, args.minuta.read_text(encoding="utf-8"))
        for al in alertas:
            print(f"{al['id']}: {al['alerta']}")
        print(f"{len(alertas)} divergências entre estados e texto")
        return 1 if alertas else 0
    res = resumo(reg)
    print(", ".join(f"{k}: {n}" for k, n in res["por_estado"].items()))
    print(res["mensagem"])
    return 0 if res["pode_encerrar"] else 1


if __name__ == "__main__":
    sys.exit(main())
