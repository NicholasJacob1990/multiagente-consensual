#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extrair_assentos.py — lê o texto (OCR) de certidão de matrícula do Registro
de Imóveis e extrai cabeçalho, atos (R-/AV-) e, em loteamentos, a tabela de
lotes por quadra com a nota de transferência de cada lote.

Uso
---
  extrair_assentos.py CERTIDAO.(md|txt) [--quadra NN] [--md] [--json SAIDA]

  sem --md/--json  imprime o Markdown
  --md             imprime o Markdown (pode combinar com --json)
  --json SAIDA     grava o JSON em SAIDA ("-" = stdout)
  --quadra NN      limita a tabela e o destaque à quadra NN

O que sai
---------
* cabeçalho: matrícula nº, folha, livro, continuação, CNM, data de abertura,
  registro anterior, proprietário;
* atos: tipo (R/AV), número, data, protocolo (nº e data) e natureza;
* por quadra: lote, área, nota de transferência — adquirente e assento de
  destino (tipo, nº, fls., livro) —, ou SEM NOTA (linha só com traços "////"
  ou vazia), ou "ilegível (conferir imagem)" quando o OCR não permite ler;
* averbações posteriores que transferem lote (ex.: "Transfere o lote nº 01, da
  quadra nº 01, para a matrícula 91.720") são cruzadas com a tabela;
* destaque "Lotes sem nota de transferência".

Limites: é leitura de OCR. Toda linha usada em parecer ou requerimento deve ser
conferida na imagem da certidão — sobretudo as marcadas "ilegível" e as áreas.
Sem dependências além da biblioteca padrão.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ILEGIVEL = "ilegível (conferir imagem)"
SEM_NOTA = "SEM NOTA"

# ---------------------------------------------------------------- normalização

_AREA = r"\d{1,3}(?:[.\s]\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?"
# lote no início da linha: "01- 3.202,00m²-", "04-A- 5.101,60m²", "04-C-10.000,00m²",
# "07. 10.490,00m?-", "10- 10.414,16m?;"
RE_LOTE = re.compile(
    r"^(?P<lote>\d{1,3})(?:\s*-\s*(?P<letra>[A-Z])(?![a-z]))?\s*[-.:,;–—]?\s*"
    r"(?P<area>" + _AREA + r")\s*m\s*[²2?³°º]?(?![a-zà-ú])\s*(?P<resto>.*)$")
RE_LOTE_SO = re.compile(r"^(?P<lote>\d{1,3}(?:\s*-\s*[A-Z])?)\s*[-.:]?\s*$")
RE_AREA_SO = re.compile(r"^(?:" + _AREA + r")\s*m\s*[²2?³°º]?")
RE_QUADRA = re.compile(r"^Q(?:uadra|d\.?)\s*(?:n[º°o.]*\s*)?(?P<q>\d{1,3})\b\s*[.:\-–]?\s*(?P<resto>.*)$",
                       re.I)
RE_ATO = re.compile(
    r"^(?P<tipo>R|AV|Av)\s*[-.]?\s*(?P<n>\d{1,4})\s*[-/.]\s*(?P<mat>\d[\d.]*)\s*[-–—]\s*"
    r"(?P<data>\d{1,2}/\d{1,2}/\d{2,4})(?P<resto>.*)$")
RE_PAGINA = re.compile(r"^(?:#+\s*P[áa]gina\b|P[áa]gina\s+\d+\s+de\s+\d+|-{3,}$|_Leitura\b|\f)",
                       re.I)
RE_FIM_TABELA = re.compile(r"^(?:Dou f[ée]|CERTIFICO|OBSERVA[ÇC][ÕO]ES|Foi o que)", re.I)
RE_PROT = re.compile(
    r"Prot(?:ocolo)?\.?\s*(?:n[º°o]\.?\s*)?:?\s*(?P<n>\d[\d.]*)"
    r"(?:\s*(?:de|-|–|em)\s*(?P<data>\d{1,2}/\d{1,2}/\d{2,4}))?", re.I)
RE_NATUREZA = re.compile(r"([A-ZÁÉÍÓÚÂÊÔÃÕÇ][A-ZÁÉÍÓÚÂÊÔÃÕÇ /\-]{3,}?)\s*[:\-–]")

# assento de destino ancorado em "fls." + "Lº": "regtº 9.000 fls. 189 Lº 3-J",
# "matrícula nº 24.000 fls. 147 Lº 2-2-AU", "nº 01- 15.000 fls. 106 Lº 2-1-AD",
# "01- 6.584 fls. 146 do Lº nº 2-2-M", "9.301 fls. 21/22 Lº 3-J"
RE_ASSENTO = re.compile(
    r"(?:(?P<ato>\d{1,2})\s*-\s*)?(?<![\d.])(?P<num>\d{1,4}(?:\.\d{3})+|\d+)\s*,?\s*"
    r"fls?\.?\s*(?P<fls>\d+(?:\s*[/\-]\s*\d+)?\s*v?)\s*,?\s*(?:do\s+)?"
    r"L(?:[º°o]|ivro)\.?\s*(?:n[º°o]\.?\s*)?(?P<livro>\d[0-9A-Z]*(?:\s*[-.]\s*[0-9A-Z]+)*)")
RE_TIPO = re.compile(r"(matr[íi]cula|transcri[çc][ãa]o|reg(?:istro|t)?[º°o]?\.?)", re.I)
RE_ADQ = re.compile(
    r"Transfere\s+(?:à|a|á|ao|aos|às|as)\s+(?P<adq>.+?)"
    r"(?=\s*,?\s*(?:conf\b|conf\.|digo\b|veja|para\s+o\s+n|sob\s+o\s+n|$))", re.I)
RE_AV_LOTE = re.compile(
    r"lote\s*n?[º°o.]*\s*(?P<lote>\d{1,3}(?:-[A-Z])?)\s*,?\s*da\s+quadra\s*n?[º°o.]*\s*"
    r"(?P<q>\d{1,3})[^.]*?para\s+a\s+matr[íi]cula\s*(?:n[º°o.]*\s*)?(?P<mat>\d[\d.]*\d)",
    re.I | re.S)


def normalizar(texto: str) -> str:
    """Erros de OCR recorrentes em certidões."""
    t = texto.replace("\xa0", " ").replace("\u200b", "")
    t = re.sub(r"(\d)\s*m\s*[?2³]\b", r"\1m²", t)          # 10.500,00m? -> m²
    t = re.sub(r"(\d)\s*m\s*\?", r"\1m²", t)
    t = re.sub(r"\bL\s*[°o]\s*(?=\.?\s*(?:n[º°o]|\d))", "Lº", t)   # L° 3-J, Lo 3-J
    t = re.sub(r"\bregt\s*[°o]", "regtº", t, flags=re.I)
    t = re.sub(r"\bn\s*[°]\s*", "nº ", t)
    return t


def _lixo(linha: str) -> bool:
    """Ruído típico de OCR de selo/QR code: linhas curtas sem conteúdo."""
    s = linha.strip()
    if not s:
        return False
    if RE_LOTE.match(s) or RE_QUADRA.match(s) or RE_LOTE_SO.match(s):
        return False
    return len(s) <= 6


def _so_tracos(s: str) -> bool:
    s = s.strip()
    return bool(s) and not re.search(r"[0-9A-Za-zÀ-ú]", s) and len(re.findall(r"[/\\|]", s)) >= 3


def _limpa_nota(s: str) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    return re.sub(r"^[\s\-–—.:;,=]+", "", s).strip()


def _fmt_area(a: str) -> str:
    a = re.sub(r"\s", ".", a.strip())
    return f"{a} m²"


def _lote_id(lote: str, letra: str | None) -> str:
    lote = lote.zfill(2)
    return f"{lote}-{letra}" if letra else lote


# ---------------------------------------------------------------- assento

def parse_assento(nota: str) -> dict | None:
    """Assento de destino de uma nota de transferência (o último citado)."""
    ms = list(RE_ASSENTO.finditer(nota))
    if not ms:
        return None
    m = ms[-1]
    antes = nota[:m.start()]
    tipos = list(RE_TIPO.finditer(antes))
    tipo_bruto = tipos[-1].group(1).lower() if tipos else ""
    if tipo_bruto.startswith("matr"):
        tipo = "matrícula"
    elif tipo_bruto.startswith("transc"):
        tipo = "transcrição"
    elif tipo_bruto.startswith("reg"):
        tipo = "regtº"
    else:
        tipo = ""
    livro = re.sub(r"\s*[-.]\s*", "-", m.group("livro")).strip("-")
    fls = re.sub(r"\s+", "", m.group("fls"))
    d = {"tipo": tipo, "ato": m.group("ato"), "numero": m.group("num"),
         "fls": fls, "livro": livro, "duvida": None}
    if re.match(r"\d{4}\.", d["numero"]):
        # "0126.663": o OCR provavelmente colou o nº do ato ("01- 26.663")
        d["duvida"] = "nº com leitura duvidosa no OCR"
    d["texto"] = render_assento(d)
    return d


def render_assento(d: dict) -> str:
    num = f"{d['ato']}- {d['numero']}" if d.get("ato") else d["numero"]
    if d["tipo"] == "regtº" and not d.get("ato"):
        cab = f"regtº {num}"
    elif d["tipo"]:
        cab = f"{d['tipo']} nº {num}"
    else:
        cab = f"nº {num}"
    txt = f"{cab} fls. {d['fls']} Lº {d['livro']}"
    return txt + (" [conferir nº na imagem]" if d.get("duvida") else "")


def classificar_nota(bruta: str) -> dict:
    nota = _limpa_nota(bruta)
    r = {"nota_ocr": nota, "status": None, "nota": None,
         "adquirente": None, "destino": None}
    if not nota or _so_tracos(nota):
        r["status"] = "sem_nota"
        r["nota"] = SEM_NOTA + (" (////)" if nota else " (linha vazia)")
        return r
    destino = parse_assento(nota)
    m = RE_ADQ.search(nota)
    if m:
        adq = re.sub(r"[\s,\-–.;]+$", "", m.group("adq")).strip()
        if adq and adq.lower() not in ("digo",):
            r["adquirente"] = adq
    if destino:
        r.update(status="transferido", destino=destino, nota=destino["texto"])
    elif re.search(r"transf", nota, re.I):
        r.update(status="incompleta", nota="nota sem assento legível — " + ILEGIVEL)
    else:
        r.update(status="ilegivel", nota=ILEGIVEL)
    return r


def _nota_completa(texto: str) -> bool:
    t = _limpa_nota(texto)
    return _so_tracos(t) or RE_ASSENTO.search(t) is not None


# ---------------------------------------------------------------- extração

def _pre_linhas(texto: str) -> list[str]:
    linhas = [ln.strip() for ln in normalizar(texto).split("\n")]
    # junta "02-" + "10.500,00m²- ..." quando o OCR quebrou o lote da área
    out, i = [], 0
    while i < len(linhas):
        ln = linhas[i]
        if RE_LOTE_SO.match(ln):
            j = i + 1
            while j < len(linhas) and not linhas[j]:
                j += 1
            if j < len(linhas) and RE_AREA_SO.match(linhas[j]):
                out.append(f"{ln.rstrip('-.: ')}- {linhas[j]}"); i = j + 1; continue
        out.append(ln); i += 1
    return out


def extrair_cabecalho(plano: str) -> dict:
    cab = {k: None for k in ("matricula", "folha", "livro", "continuacao", "cnm",
                             "data_abertura", "registro_anterior", "proprietario")}
    m = re.search(r"Matr[íi]cula\s+(?:Manuscrita\s+)?n?[º°o.]*\s*(?P<n>\d[\d.]*\d)\s*,\s*"
                  r"(?:Folha|fls?\.?)\s*(?P<f>\d+)\s*,\s*(?:Livro|L[º°o]\.?)\s*(?:n[º°o.]*\s*)?"
                  r"(?P<l>\d[0-9A-Z]*(?:-[0-9A-Z]+)*)", plano, re.I)
    if m:
        cab.update(matricula=m.group("n"), folha=m.group("f"), livro=m.group("l"))
    else:
        m = re.search(r"Matr[íi]cula\s+n?[º°o.]*\s*(\d[\d.]*\d)", plano, re.I)
        if m:
            cab["matricula"] = m.group(1)
    m = re.search(r"continua[çc][ãa]o\s+no\s+(.+?)(?=,|\.\s|$)", plano, re.I)
    if m:
        cab["continuacao"] = m.group(1).strip()
    m = (re.search(r"C[óo]digo\s+Nacional\s+de\s+Matr[íi]cula\s*(?:\(CNM\)\s*)?(?:n[º°o.]*\s*)?:?\s*"
                   r"(\d{6}\.\d\.\d{7}-\d{2})", plano, re.I)
         or re.search(r"\b(\d{6}\.\d\.\d{7}-\d{2})\b", plano))
    if m:
        cab["cnm"] = m.group(1)
    m = re.search(r"datada\s+de\s+(\d{1,2}/\d{1,2}/\d{4})", plano, re.I)
    if not m and cab["matricula"]:
        num = cab["matricula"].replace(".", "")
        m = re.search(rf"(?:^|\s){num}\s*-\s*(\d{{1,2}}/\d{{1,2}}/\d{{4}})", plano)
    if m:
        cab["data_abertura"] = m.group(1)
    m = re.search(r"REGISTRO\s+ANTERIOR\s*:\s*(.{3,200}?)(?:,?\s*dest[ea]\s+(?:Cart[óo]rio|Serventia)"
                  r"|\.\s+(?=[A-ZÁÉÍÓÚ][a-záéíóú])|$)", plano, re.I)
    if m:
        bruto = m.group(1).strip().rstrip(",;.")
        a = parse_assento(bruto)
        cab["registro_anterior"] = (render_assento(a).replace("matrícula nº", "Matrícula")
                                    if a else bruto)
    m = re.search(r"PROPRIET[ÁA]RI[OA]S?\s*:\s*(.+?)(?=,\s*(?:com\s+sede|CGC|CNPJ|CPF|inscrit|"
                  r"brasileir|residente|domiciliad)|;|\.\s|$)", plano, re.I)
    if m:
        cab["proprietario"] = m.group(1).strip()
    return cab


def extrair(texto: str) -> dict:
    linhas = _pre_linhas(texto)
    plano = re.sub(r"\s+", " ", " ".join(l for l in linhas if not _lixo(l)))
    cab = extrair_cabecalho(plano)

    # ---- atos
    atos, atual = [], None
    for ln in linhas:
        m = RE_ATO.match(ln)
        if m:
            atual = {"ato": f"{m.group('tipo').upper()}-{m.group('n')}",
                     "tipo": m.group("tipo").upper(), "numero": int(m.group("n")),
                     "matricula": m.group("mat"), "data": m.group("data"),
                     "protocolo": None, "protocolo_data": None, "natureza": None,
                     "_corpo": [m.group("resto")]}
            atos.append(atual); continue
        if atual is not None:
            if RE_FIM_TABELA.match(ln) and ln.upper().startswith(("CERTIFICO", "OBSERVA")):
                atual = None; continue
            atual["_corpo"].append(ln)
    for a in atos:
        corpo = re.sub(r"\s+", " ", " ".join(x for x in a.pop("_corpo") if not _lixo(x)))
        p = RE_PROT.search(corpo[:400])
        if p:
            a["protocolo"], a["protocolo_data"] = p.group("n"), p.group("data")
        resto = corpo[p.end():] if p and p.start() < 40 else corpo
        resto = re.sub(r"^[\s:\-–]+", "", resto)
        n = RE_NATUREZA.match(resto)
        if n:
            a["natureza"] = n.group(1).strip(" -/")
        a["transferencias_lote"] = [
            {"lote": mm.group("lote").zfill(2), "quadra": mm.group("q").zfill(2),
             "matricula_destino": mm.group("mat")}
            for mm in RE_AV_LOTE.finditer(corpo)] if a["tipo"] == "AV" else []

    # ---- tabela do loteamento
    quadras: dict[str, list] = {}
    q_atual, lote, em_tabela, suspenso = None, None, False, False

    def fecha():
        nonlocal lote
        if lote is not None:
            quadras.setdefault(q_atual, []).append(lote)
        lote = None

    for ln in linhas:
        if not ln or _lixo(ln):
            continue
        if RE_PAGINA.match(ln):
            if em_tabela:
                suspenso = True
            continue
        mq = RE_QUADRA.match(ln)
        if mq:
            fecha()
            q_atual, em_tabela, suspenso = mq.group("q").zfill(2), True, False
            quadras.setdefault(q_atual, [])
            ln = mq.group("resto").strip()
            if not ln:
                continue
        if not em_tabela:
            continue
        if RE_ATO.match(ln) or RE_FIM_TABELA.match(ln):
            fecha(); em_tabela = False; continue
        ml = RE_LOTE.match(ln)
        if ml:
            fecha(); suspenso = False
            lote = {"lote": _lote_id(ml.group("lote"), ml.group("letra")),
                    "area": _fmt_area(ml.group("area")), "_nota": [ml.group("resto")]}
            continue
        if lote is None:
            continue
        nota_ate_agora = " ".join(lote["_nota"])
        if suspenso:
            # após quebra de página só aceita continuação evidente de nota aberta
            if (not _nota_completa(nota_ate_agora) and re.search(r"transf", nota_ate_agora, re.I)
                    and RE_ASSENTO.search(ln)):
                lote["_nota"].append(ln)
            continue
        if not _nota_completa(nota_ate_agora):
            lote["_nota"].append(ln)
    fecha()

    for q, lotes in quadras.items():
        for l in lotes:
            l.update(classificar_nota(" ".join(l.pop("_nota"))))
            l["averbacoes"] = []

    # ---- cruza averbações posteriores de transferência de lote
    for a in atos:
        for t in a.get("transferencias_lote", []):
            for l in quadras.get(t["quadra"], []):
                if l["lote"] == t["lote"]:
                    l["averbacoes"].append(f"{a['ato']} ({a['data']}): matrícula {t['matricula_destino']}")

    sem = [{"quadra": q, **{k: l[k] for k in ("lote", "area", "status", "nota", "nota_ocr",
                                              "averbacoes")}}
           for q, lotes in quadras.items() for l in lotes
           if l["status"] in ("sem_nota", "ilegivel", "incompleta")]
    return {"cabecalho": cab, "atos": atos, "quadras": quadras, "sem_nota": sem}


def filtrar_quadra(res: dict, quadra: str) -> dict:
    q = str(int(quadra)).zfill(2)
    res = dict(res)
    res["quadras"] = {k: v for k, v in res["quadras"].items() if k == q}
    res["sem_nota"] = [s for s in res["sem_nota"] if s["quadra"] == q]
    return res


# ---------------------------------------------------------------- saída

def _c(s) -> str:
    return "—" if s in (None, "", []) else str(s).replace("|", "\\|")


def para_md(res: dict) -> str:
    cab = res["cabecalho"]
    o = [f"# Assentos — Matrícula nº {_c(cab['matricula'])}", "",
         "> Extraído de texto OCR. Conferir cada linha na imagem da certidão antes de "
         "citar em parecer ou requerimento — sobretudo áreas e linhas marcadas "
         f"\"{ILEGIVEL}\".", "", "## Cabeçalho", "", "| Campo | Valor |", "|---|---|"]
    for rot, k in (("Matrícula nº", "matricula"), ("Folha", "folha"), ("Livro", "livro"),
                   ("Continuação", "continuacao"), ("CNM", "cnm"),
                   ("Data de abertura", "data_abertura"), ("Registro anterior", "registro_anterior"),
                   ("Proprietário", "proprietario")):
        o.append(f"| {rot} | {_c(cab[k])} |")
    o += ["", "## Atos", ""]
    if res["atos"]:
        o += ["| Ato | Data | Protocolo | Natureza |", "|---|---|---|---|"]
        for a in res["atos"]:
            prot = a["protocolo"] and (a["protocolo"] + (f" de {a['protocolo_data']}"
                                                         if a["protocolo_data"] else ""))
            o.append(f"| {a['ato']} | {a['data']} | {_c(prot)} | {_c(a['natureza'])} |")
    else:
        o.append("Nenhum ato R-/AV- identificado.")
    for q, lotes in res["quadras"].items():
        o += ["", f"## Quadra {q}", "",
              "| Lote | Área | Nota de transferência | Adquirente | Averbação posterior |",
              "|---|---|---|---|---|"]
        for l in lotes:
            o.append(f"| {l['lote']} | {l['area']} | {_c(l['nota'])} | {_c(l['adquirente'])} | "
                     f"{_c('; '.join(l['averbacoes']))} |")
    o += ["", "## Lotes sem nota de transferência", ""]
    if not res["sem_nota"]:
        o.append("Nenhum.")
    for s in res["sem_nota"]:
        det = s["nota"]
        if s["status"] != "sem_nota" and s["nota_ocr"]:
            det += f" — texto OCR: \"{s['nota_ocr'][:80]}\""
        if s["averbacoes"]:
            det += f" — mas v. {'; '.join(s['averbacoes'])}"
        o.append(f"- **Quadra {s['quadra']}, lote {s['lote']}** ({s['area']}): {det}")
    return "\n".join(o) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("certidao")
    ap.add_argument("--quadra")
    ap.add_argument("--md", action="store_true")
    ap.add_argument("--json", metavar="SAIDA")
    a = ap.parse_args(argv)
    texto = Path(a.certidao).read_text(encoding="utf-8", errors="replace")
    res = extrair(texto)
    if a.quadra:
        res = filtrar_quadra(res, a.quadra)
    if res["cabecalho"]["matricula"] is None:
        print("aviso: número da matrícula não localizado no texto", file=sys.stderr)
    if a.json:
        js = json.dumps(res, ensure_ascii=False, indent=2)
        if a.json == "-":
            print(js)
        else:
            Path(a.json).write_text(js + "\n", encoding="utf-8")
    if a.md or not a.json:
        sys.stdout.write(para_md(res))
    return 0


if __name__ == "__main__":
    sys.exit(main())
