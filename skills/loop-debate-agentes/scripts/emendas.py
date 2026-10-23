#!/usr/bin/env python3
"""Motor mecânico do modo ``emendas_consensuais_v1``.

Os agentes leem a mesma minuta congelada, propõem emendas pontuais às cegas,
votam às cegas nas emendas uns dos outros e só entram no texto as emendas
aprovadas pela regra escolhida. O script não julga mérito: valida, apura e
aplica. Cada subcomando grava JSON para o seguinte e recusa material de outra
versão da minuta (hash divergente).

Fluxo::

    emendas.py validar  --minuta v.md --propostas gemini.json codex.json [--fontes fontes/] --saida validadas.json
    emendas.py cedula   --validadas validadas.json --saida cedula.md
    emendas.py apurar   --validadas validadas.json --votos voto_gemini.json voto_codex.json --saida apuracao.json
    emendas.py segunda-rodada --apuracao apuracao.json --saida validadas2.json   # só se houver ajustes divergentes
    emendas.py aplicar  --minuta v.md --apuracao apuracao.json --saida v_next.md --relatorio emendas.md

Contratos de entrada: ``emendas_schema.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Any

CONTRATO = "emendas_consensuais_v1"
TIPOS = ("correcao", "precisao", "fonte", "remissao", "redacao", "corte", "acrescimo")
VOTOS = ("aceitar", "ajustar", "rejeitar")
PAR_RE = re.compile(r"^(\d+)\. ", re.M)


# ---------------------------------------------------------------- utilidades

def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ler_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gravar_json(path: Path | str, dados: Any) -> None:
    Path(path).write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def palavras(texto: str) -> int:
    return len(texto.replace("**", "").split())


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto).replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", texto).strip().lower()


def limites_paragrafos(minuta: str) -> list[tuple[int, int, int]]:
    """(número, início, fim) de cada parágrafo numerado ``N. texto``, uma linha por parágrafo."""
    out = []
    for m in PAR_RE.finditer(minuta):
        fim = minuta.find("\n", m.start())
        out.append((int(m.group(1)), m.start(), len(minuta) if fim < 0 else fim))
    return out


def paragrafo_em(limites: list[tuple[int, int, int]], pos: int) -> tuple[int, int, int] | None:
    for lim in limites:
        if lim[1] <= pos < lim[2]:
            return lim
    return None


def corpus_fontes(dirs: list[Path]) -> str:
    partes = []
    for d in dirs:
        arquivos = [d] if d.is_file() else sorted(p for p in d.rglob("*") if p.suffix.lower() in {".md", ".txt", ".html", ".htm"})
        for p in arquivos:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if p.suffix.lower() in {".html", ".htm"}:
                txt = re.sub(r"<[^>]+>", " ", txt)
            partes.append(normalizar(txt))
    return "\n".join(partes)


def regra_atingida(sim: int, total: int, regra: str) -> bool:
    if total == 0:
        return False
    if regra == "unanimidade":
        return sim == total
    if regra == "maioria":
        return sim * 2 > total
    if regra.startswith("qualificada:"):
        return sim >= math.ceil(total * Fraction(regra.split(":", 1)[1]))
    raise SystemExit(f"regra desconhecida: {regra}")


# ---------------------------------------------------------------- validar

def validar(minuta: str, lotes: list[dict], travados: list[dict] | None = None, fontes: str | None = None,
            max_palavras: int | None = None, exigir_fonte: tuple[str, ...] = ("correcao", "fonte")) -> dict:
    hash_minuta = sha256_texto(minuta)
    limites = limites_paragrafos(minuta)
    travas = []
    for t in travados or []:
        i = minuta.find(t["texto"])
        if i >= 0:
            travas.append((i, i + len(t["texto"]), t.get("id") or t["texto"][:40]))

    emendas: list[dict] = []
    lotes_recusados = []
    for lote in lotes:
        autor = lote.get("autor", "?")
        if lote.get("hash_minuta") != hash_minuta:
            lotes_recusados.append({"autor": autor, "motivo": "hash_minuta divergente: propostas feitas sobre outra versão"})
            continue
        for p in lote.get("propostas", []):
            emendas.append({**p, "autores": [autor]})

    # convergência: a mesma emenda proposta por mais de um autor vira uma só
    unicas: list[dict] = []
    for e in emendas:
        igual = next((u for u in unicas if u["trecho"] == e["trecho"] and normalizar(u["proposta"]) == normalizar(e["proposta"])), None)
        if igual:
            igual["autores"] += [a for a in e["autores"] if a not in igual["autores"]]
        else:
            unicas.append(e)

    for n, e in enumerate(unicas, start=1):
        e["id"] = f"E{n:02d}"
        motivos, alertas = [], []
        trecho = e.get("trecho", "")
        if e.get("tipo") not in TIPOS:
            motivos.append(f"tipo inválido: {e.get('tipo')!r}")
        ocorrencias = minuta.count(trecho) if trecho else 0
        if ocorrencias != 1:
            motivos.append("trecho não localizado literalmente na minuta" if ocorrencias == 0
                           else f"trecho ambíguo: ocorre {ocorrencias} vezes; ampliar o trecho")
        else:
            ini = minuta.index(trecho)
            e["inicio"], e["fim"] = ini, ini + len(trecho)
            lim = paragrafo_em(limites, ini)
            if lim and e["fim"] > lim[2]:
                motivos.append("trecho atravessa mais de um parágrafo")
            if lim:
                if e.get("paragrafo") not in (None, lim[0]):
                    motivos.append(f"trecho está no parágrafo {lim[0]}, não no {e['paragrafo']}")
                e["paragrafo"] = lim[0]
                novo_par = minuta[lim[1]:ini] + e["proposta"] + minuta[e["fim"]:lim[2]]
                e["palavras_resultantes"] = palavras(PAR_RE.sub("", novo_par, count=1))
                if max_palavras and e["palavras_resultantes"] > max_palavras:
                    # outra emenda do mesmo parágrafo pode compensar; o limite é conferido de novo ao aplicar
                    alertas.append(f"isolada, deixa o parágrafo com {e['palavras_resultantes']} palavras (máximo {max_palavras})")
            for a, b, rotulo in travas:
                if ini < b and a < e["fim"]:
                    motivos.append(f'trecho travado "{rotulo}"')
        e["delta_palavras"] = palavras(e.get("proposta", "")) - palavras(trecho)
        if e.get("tipo") in exigir_fonte:
            literal = e.get("fonte_literal", "").strip()
            if not literal:
                motivos.append("emenda de mérito sem fonte literal")
            elif fontes is not None and normalizar(literal) not in fontes:
                motivos.append("fonte literal não localizada nas fontes fornecidas")
        e["status"] = "invalida" if motivos else "valida"
        e["motivos_invalidade"] = motivos
        e["alertas"] = alertas

    # emendas válidas sobre trechos sobrepostos formam um grupo de conflito: no máximo uma entra
    validas = [e for e in unicas if e["status"] == "valida"]
    grupo = 0
    for i, a in enumerate(validas):
        for b in validas[i + 1:]:
            if a["inicio"] < b["fim"] and b["inicio"] < a["fim"]:
                g = a.get("grupo_conflito") or b.get("grupo_conflito")
                if not g:
                    grupo += 1
                    g = f"C{grupo}"
                a["grupo_conflito"] = b["grupo_conflito"] = g

    return {
        "contrato": CONTRATO,
        "hash_minuta": hash_minuta,
        "lotes_recusados": lotes_recusados,
        "emendas": unicas,
    }


# ---------------------------------------------------------------- cédula

def cedula(validadas: dict, semente: str | None = None, permitir_ajuste: bool | None = None) -> str:
    if permitir_ajuste is None:
        permitir_ajuste = validadas.get("rodada", 1) < 2  # a segunda rodada só escolhe entre variantes
    emendas = [e for e in validadas["emendas"] if e["status"] == "valida"]
    ordem = list(emendas)
    random.Random(semente or validadas["hash_minuta"]).shuffle(ordem)
    ordem.sort(key=lambda e: e.get("paragrafo") or 0)  # embaralha empates e mantém a leitura em ordem de parágrafo
    votos_permitidos = " | ".join(VOTOS if permitir_ajuste else ("aceitar", "rejeitar"))
    linhas = [
        f"# Cédula de votação — {CONTRATO}",
        "",
        f"HASH_MINUTA: {validadas['hash_minuta']}",
        "",
        "Vote em cada emenda abaixo sem saber quem a propôs. Leia a minuta integral e confira o fundamento na fonte "
        "antes de votar. Rejeite a emenda que piore o texto, introduza erro, dependa de fonte não conferida ou exceda o "
        "suporte. "
        + ("Use \"ajustar\" só quando concordar com a ideia e tiver redação melhor para o mesmo trecho; o ajuste "
           "substitui integralmente o trecho atual." if permitir_ajuste else
           "Esta é a rodada final: as variantes de um mesmo trecho concorrem entre si e entra no máximo uma; "
           "aceite somente as que você subscreveria."),
        "",
    ]
    for e in ordem:
        linhas += [
            f"## {e['id']} — parágrafo {e.get('paragrafo', '—')} — {e['tipo']}"
            + (f" — conflita com outras do grupo {e['grupo_conflito']}" if e.get("grupo_conflito") else ""),
            "",
            f"**Trecho atual:** {e['trecho']}",
            "",
            f"**Proposta:** {e['proposta']}",
            "",
            f"**Fundamento:** {e.get('fundamento', '')}",
        ]
        if e.get("fonte_literal"):
            linhas.append(f"\n**Fonte literal ({e.get('fonte_ref', 's/ref.')}):** {e['fonte_literal']}")
        linhas += [f"\n**Variação de palavras:** {e['delta_palavras']:+d}", ""]
    modelo = {
        "votante": "<seu identificador>",
        "hash_minuta": validadas["hash_minuta"],
        "votos": [{"id": e["id"], "voto": "aceitar", "motivo": "...", **({"ajuste": ""} if permitir_ajuste else {})} for e in ordem],
    }
    linhas += [
        "## Resposta",
        "",
        f"Responda só com o JSON abaixo, com um voto por emenda ({votos_permitidos}) e motivo curto em cada um. "
        "O campo hash_minuta deve repetir exatamente o hash acima.",
        "",
        "```json",
        json.dumps(modelo, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- apurar

def apurar(validadas: dict, lotes_votos: list[dict], regra: str = "unanimidade") -> dict:
    hash_minuta = validadas["hash_minuta"]
    votantes, recusados = [], []
    for lote in lotes_votos:
        nome = lote.get("votante", "?")
        if lote.get("hash_minuta") != hash_minuta:
            recusados.append({"votante": nome, "motivo": "hash_minuta divergente"})
        elif nome in [v["votante"] for v in votantes]:
            recusados.append({"votante": nome, "motivo": "votante repetido"})
        else:
            votantes.append(lote)
    total = len(votantes)
    resultado = []
    for e in validadas["emendas"]:
        r = {k: e[k] for k in e if k not in ("status", "motivos_invalidade", "alertas")}
        if e["status"] != "valida":
            resultado.append({**r, "decisao": "invalida", "motivos": e["motivos_invalidade"], "votos": []})
            continue
        votos = []
        for lote in votantes:
            v = next((v for v in lote.get("votos", []) if v.get("id") == e["id"]), None)
            if v is None or v.get("voto") not in VOTOS:
                v = {"id": e["id"], "voto": "abstencao", "motivo": "sem voto válido"}
            votos.append({"votante": lote["votante"], **{k: v.get(k) for k in ("voto", "ajuste", "motivo") if v.get(k) is not None}})
        aceitar = sum(v["voto"] == "aceitar" for v in votos)
        ajustes = [v["ajuste"].strip() for v in votos if v["voto"] == "ajustar" and v.get("ajuste", "").strip()]
        ajustar = sum(v["voto"] == "ajustar" for v in votos)
        favor = aceitar + ajustar
        r["votos"] = votos
        r["placar"] = {"aceitar": aceitar, "ajustar": ajustar, "rejeitar": sum(v["voto"] == "rejeitar" for v in votos),
                       "abstencao": sum(v["voto"] == "abstencao" for v in votos), "votantes": total}
        # cada texto precisa atingir a regra por si: quem aceitou a redação original não aderiu ao ajuste
        por_ajuste: dict[str, list[str]] = {}
        for a in ajustes:
            por_ajuste.setdefault(normalizar(a), []).append(a)
        ajuste_vencedor = next((v[0] for v in por_ajuste.values() if regra_atingida(len(v), total, regra)), None)
        if regra_atingida(aceitar, total, regra):
            r["decisao"], r["texto_aprovado"] = "aprovada", e["proposta"]
        elif ajuste_vencedor is not None:
            r["decisao"], r["texto_aprovado"] = "aprovada_com_ajuste", ajuste_vencedor
        elif regra_atingida(favor, total, regra):
            r["decisao"] = "segunda_rodada"
            r["variantes"] = [e["proposta"]] + list(dict.fromkeys(ajustes))
        elif favor == 0:
            r["decisao"] = "rejeitada"
        else:
            r["decisao"] = "dissenso"
        resultado.append(r)

    # no grupo de conflito, entra só a aprovada com mais aceites; empate vai ao humano
    grupos: dict[str, list[dict]] = {}
    for r in resultado:
        if r.get("grupo_conflito") and r["decisao"] in ("aprovada", "aprovada_com_ajuste"):
            grupos.setdefault(r["grupo_conflito"], []).append(r)
    for g, rs in grupos.items():
        if len(rs) < 2:
            continue
        rs.sort(key=lambda r: (r["placar"]["aceitar"], r["placar"]["ajustar"]), reverse=True)
        empate = (rs[0]["placar"]["aceitar"], rs[0]["placar"]["ajustar"]) == (rs[1]["placar"]["aceitar"], rs[1]["placar"]["ajustar"])
        for r in (rs if empate else rs[1:]):
            r["decisao"] = "dissenso" if empate else "preterida"
            r["motivo_decisao"] = f"conflito no grupo {g}" + (" com empate" if empate else f" com {rs[0]['id']}, mais votada")
            r.pop("texto_aprovado", None)
    # sem consenso próprio e vencida por concorrente aprovada no mesmo trecho: não sobe ao humano
    vencedoras = {r["grupo_conflito"]: r["id"] for r in resultado
                  if r.get("grupo_conflito") and r["decisao"] in ("aprovada", "aprovada_com_ajuste")}
    for r in resultado:
        g = r.get("grupo_conflito")
        if g in vencedoras and r["decisao"] in ("dissenso", "segunda_rodada") and "motivo_decisao" not in r:
            r["decisao"] = "preterida"
            r["motivo_decisao"] = f"conflito no grupo {g} com {vencedoras[g]}, aprovada"

    return {
        "contrato": CONTRATO,
        "hash_minuta": hash_minuta,
        "regra": regra,
        "rodada": validadas.get("rodada", 1),
        "votantes": [v["votante"] for v in votantes],
        "votantes_recusados": recusados,
        "emendas": resultado,
    }


def segunda_rodada(apuracao: dict) -> dict:
    """Converte as emendas com ajustes divergentes em variantes concorrentes, votadas só com aceitar/rejeitar."""
    if apuracao.get("rodada", 1) >= 2:
        raise SystemExit("o modo admite uma única rodada de ajuste; o que não fechou vai ao humano como dissenso")
    emendas = []
    for r in apuracao["emendas"]:
        if r["decisao"] != "segunda_rodada":
            continue
        for k, texto in enumerate(r["variantes"]):
            emendas.append({
                "id": f"{r['id']}{chr(ord('a') + k)}",
                "origem": r["id"],
                "autores": r.get("autores", []) if k == 0 else ["ajuste"],
                "paragrafo": r.get("paragrafo"),
                "tipo": r["tipo"],
                "trecho": r["trecho"],
                "proposta": texto,
                "fundamento": r.get("fundamento", ""),
                "fonte_literal": r.get("fonte_literal", ""),
                "fonte_ref": r.get("fonte_ref", ""),
                "inicio": r["inicio"],
                "fim": r["fim"],
                "delta_palavras": palavras(texto) - palavras(r["trecho"]),
                "grupo_conflito": f"R{r['id']}",
                "status": "valida",
                "motivos_invalidade": [],
            })
    return {"contrato": CONTRATO, "hash_minuta": apuracao["hash_minuta"], "rodada": 2, "lotes_recusados": [], "emendas": emendas}


# ---------------------------------------------------------------- aplicar

def aplicar(minuta: str, apuracoes: list[dict], max_palavras: int | None = None) -> tuple[str, list[dict]]:
    hash_minuta = sha256_texto(minuta)
    aprovadas = []
    for ap in apuracoes:
        if ap["hash_minuta"] != hash_minuta:
            raise SystemExit("a apuração foi feita sobre outra versão da minuta")
        aprovadas += [r for r in ap["emendas"] if r["decisao"] in ("aprovada", "aprovada_com_ajuste")]
    aprovadas.sort(key=lambda r: r["inicio"])
    for a, b in zip(aprovadas, aprovadas[1:]):
        if b["inicio"] < a["fim"]:
            raise SystemExit(f"emendas aprovadas sobrepostas: {a['id']} e {b['id']}")
    texto = minuta
    for r in reversed(aprovadas):
        assert texto[r["inicio"]:r["fim"]] == r["trecho"], r["id"]
        texto = texto[:r["inicio"]] + r["texto_aprovado"] + texto[r["fim"]:]
    if max_palavras:
        excesso = [(n, palavras(texto[i:f].split(". ", 1)[1])) for n, i, f in limites_paragrafos(texto)
                   if palavras(texto[i:f].split(". ", 1)[1]) > max_palavras]
        if excesso:
            raise SystemExit("aplicação recusada; parágrafos acima do limite: "
                             + ", ".join(f"{n} ({q} palavras)" for n, q in excesso)
                             + ". Votar uma emenda de corte no mesmo parágrafo ou levar ao humano.")
    return texto, aprovadas


def relatorio(minuta_path: str, saida_path: str, hash_antes: str, hash_depois: str, apuracoes: list[dict]) -> str:
    def votos_txt(r: dict) -> str:
        return "; ".join(f"{v['votante']}: {v['voto']}" + (f" — {v['motivo']}" if v.get("motivo") else "") for v in r.get("votos", []))

    todas = {}
    for ap in apuracoes:  # a segunda rodada prevalece sobre a primeira para a mesma emenda de origem
        for r in ap["emendas"]:
            todas[r["id"]] = r
    origem_resolvida = {r.get("origem") for r in todas.values() if r.get("origem")}
    regra = apuracoes[-1]["regra"]
    linhas = [
        f"# Relatório de emendas — {CONTRATO}",
        "",
        f"- Minuta de entrada: `{minuta_path}` (sha256 `{hash_antes}`)",
        f"- Minuta de saída: `{saida_path}` (sha256 `{hash_depois}`)",
        f"- Regra de aprovação: {regra}; votantes: {', '.join(apuracoes[0]['votantes'])}",
    ]
    for ap in apuracoes:
        for v in ap.get("votantes_recusados", []):
            linhas.append(f"- Voto recusado de {v['votante']}: {v['motivo']}")
    secoes = [
        ("Aplicadas", ("aprovada", "aprovada_com_ajuste")),
        ("Dissenso — decisão humana", ("dissenso", "segunda_rodada")),
        ("Preteridas por emenda concorrente mais votada", ("preterida",)),
        ("Rejeitadas", ("rejeitada",)),
        ("Inválidas", ("invalida",)),
    ]
    for titulo, decisoes in secoes:
        itens = [r for r in todas.values() if r["decisao"] in decisoes and not (r["decisao"] == "segunda_rodada" and r["id"] in origem_resolvida)]
        linhas += ["", f"## {titulo} ({len(itens)})"]
        for r in sorted(itens, key=lambda r: (r.get("paragrafo") or 0, r["id"])):
            linhas += ["", f"### {r['id']} — parágrafo {r.get('paragrafo', '—')} — {r.get('tipo')} — proposta por {', '.join(r.get('autores', []))}"]
            linhas.append(f"- Antes: {r['trecho']}")
            if r["decisao"] in ("aprovada", "aprovada_com_ajuste"):
                linhas.append(f"- Depois: {r['texto_aprovado']}" + (" (com ajuste)" if r["decisao"] == "aprovada_com_ajuste" else ""))
            else:
                linhas.append(f"- Proposta: {r['proposta']}")
            if r.get("variantes"):
                linhas += [f"- Variante {chr(ord('a') + k)}: {t}" for k, t in enumerate(r["variantes"])]
            if r.get("fundamento"):
                linhas.append(f"- Fundamento: {r['fundamento']}")
            if r.get("motivos"):
                linhas.append(f"- Motivo da invalidade: {'; '.join(r['motivos'])}")
            if r.get("motivo_decisao"):
                linhas.append(f"- Decisão: {r['motivo_decisao']}")
            if r.get("votos"):
                linhas.append(f"- Votos: {votos_txt(r)}")
    linhas += ["", "Próximos passos: rodar a pré-auditoria na minuta de saída, gerar o redline contra a de entrada e enviar à auditoria cega final por outra família de modelo."]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validar")
    v.add_argument("--minuta", type=Path, required=True)
    v.add_argument("--propostas", type=Path, nargs="+", required=True)
    v.add_argument("--travados", type=Path)
    v.add_argument("--fontes", type=Path, nargs="*", help="pastas ou arquivos onde conferir a fonte literal")
    v.add_argument("--max-palavras", type=int)
    v.add_argument("--exigir-fonte", default="correcao,fonte", help="tipos que exigem fonte literal (vírgulas; vazio desliga)")
    v.add_argument("--saida", type=Path, required=True)

    c = sub.add_parser("cedula")
    c.add_argument("--validadas", type=Path, required=True)
    c.add_argument("--saida", type=Path, required=True)
    c.add_argument("--semente")

    a = sub.add_parser("apurar")
    a.add_argument("--validadas", type=Path, required=True)
    a.add_argument("--votos", type=Path, nargs="+", required=True)
    a.add_argument("--regra", default="unanimidade", help="unanimidade | maioria | qualificada:2/3")
    a.add_argument("--saida", type=Path, required=True)

    s = sub.add_parser("segunda-rodada")
    s.add_argument("--apuracao", type=Path, required=True)
    s.add_argument("--saida", type=Path, required=True)

    ap = sub.add_parser("aplicar")
    ap.add_argument("--minuta", type=Path, required=True)
    ap.add_argument("--apuracao", type=Path, nargs="+", required=True, help="primeira rodada e, se houver, a segunda")
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--relatorio", type=Path, required=True)
    ap.add_argument("--max-palavras", type=int, help="limite por parágrafo, conferido no texto final")

    args = p.parse_args(argv)

    if args.cmd == "validar":
        minuta = args.minuta.read_text(encoding="utf-8")
        travados = ler_json(args.travados) if args.travados else None
        fontes = corpus_fontes(args.fontes) if args.fontes else None
        exigir = tuple(t for t in args.exigir_fonte.split(",") if t)
        res = validar(minuta, [ler_json(f) for f in args.propostas], travados, fontes, args.max_palavras, exigir)
        gravar_json(args.saida, res)
        n_val = sum(e["status"] == "valida" for e in res["emendas"])
        print(f"{n_val} válidas, {len(res['emendas']) - n_val} inválidas, {len(res['lotes_recusados'])} lotes recusados")
        for e in res["emendas"]:
            if e["status"] == "invalida":
                print(f"  {e['id']} inválida: {'; '.join(e['motivos_invalidade'])}")
            for a in e.get("alertas", []):
                print(f"  {e['id']} alerta: {a}")
        return 0
    if args.cmd == "cedula":
        validadas = ler_json(args.validadas)
        args.saida.write_text(cedula(validadas, args.semente), encoding="utf-8")
        print(f"cédula gravada em {args.saida}")
        return 0
    if args.cmd == "apurar":
        res = apurar(ler_json(args.validadas), [ler_json(f) for f in args.votos], args.regra)
        gravar_json(args.saida, res)
        cont: dict[str, int] = {}
        for r in res["emendas"]:
            cont[r["decisao"]] = cont.get(r["decisao"], 0) + 1
        print(", ".join(f"{k}: {n}" for k, n in sorted(cont.items())), "| votantes:", ", ".join(res["votantes"]) or "nenhum")
        for v in res["votantes_recusados"]:
            print(f"  voto recusado de {v['votante']}: {v['motivo']}")
        return 0
    if args.cmd == "segunda-rodada":
        res = segunda_rodada(ler_json(args.apuracao))
        gravar_json(args.saida, res)
        print(f"{len(res['emendas'])} variantes para a segunda rodada")
        return 0
    if args.cmd == "aplicar":
        minuta = args.minuta.read_text(encoding="utf-8")
        apuracoes = [ler_json(f) for f in args.apuracao]
        texto, aplicadas = aplicar(minuta, apuracoes, args.max_palavras)
        args.saida.write_text(texto, encoding="utf-8")
        args.relatorio.write_text(relatorio(str(args.minuta), str(args.saida), sha256_texto(minuta), sha256_texto(texto), apuracoes), encoding="utf-8")
        print(f"{len(aplicadas)} emendas aplicadas; sha256 da saída: {sha256_texto(texto)}")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
