#!/usr/bin/env python3
"""Confere achados de remissão de auditor externo contra o .docx auditado, antes de aceitá-los.

Motivo: um auditor externo analisou duas vezes o parecer e entregou tabelas de
"remissões erradas" que estavam certas. A extração dele não contou o §1 (parágrafo que
começa com o rótulo em negrito "Resposta objetiva."), e toda a numeração dele ficou
deslocada em −1; além disso, declarou um SHA-256 diferente do arquivo entregue (leu
outra cópia). Este script separa o deslocamento do auditor do erro real do documento.

Entrada (``--achados``)::

    {"auditor": "Grok", "sha256_declarado": "9b2c0e20…e466e5",
     "achados": [{"onde": "§59", "remete": [14], "assunto_em": [13],
                  "assunto": "cláusula de rescisão por paralisação"}, ...]}

- ``onde``: o parágrafo que contém a remissão, na numeração do auditor ("§59", "59",
  "parágrafo 59"), ou um rótulo ("quadro, item a" → o parágrafo que começa com "a)"
  depois do que começa com "Quadro…"), ou um trecho literal do parágrafo;
- ``remete``: os números que a remissão do texto cita;
- ``assunto_em``: onde o auditor diz que o assunto está (na numeração dele; pode ser [ ]);
- ``assunto``: descrição curta do assunto a que a remissão deveria levar.

Convenção do deslocamento: ``k = numeração do auditor − numeração do documento``.
"Auditor deslocado em −1" quer dizer que o §59 dele é o §60 do documento. Para cada
achado e cada k em [−3..3]:

(a) **localização**: o §(onde − k) do documento tem de conter remissão aos números de
    ``remete`` (como o auditor os transcreveu do texto) ou a ``remete − k`` (se ele os
    converteu para a numeração dele); rótulos ("quadro, item a") não dependem de k;
(b) **assunto**: os termos de ``assunto`` (sem acento, radical de 5 letras, sem
    stopwords, com peso IDF; termos ausentes do documento não contam) são procurados em
    todos os parágrafos do corpo, exceto o que contém a remissão; mede-se a cobertura
    dos termos pelo destino citado e pelo melhor parágrafo do documento;
(c) **consistência**: k é consistente com o achado quando (a) vale e, havendo
    ``assunto_em``, ``assunto_em − k`` cai dentro do destino citado (o próprio auditor
    situa o assunto no parágrafo citado, só que com outro número).

O deslocamento sistemático é o k consistente com o maior número de achados
("deslocamento sistemático de −1 em 10 de 12 achados"). Vereditos:

- ``correta`` / ``correta (auditor deslocado em k)``: o destino trata do assunto, ou
  os termos não decidem mas o deslocamento explica a divergência do auditor;
- ``erro real (o destino citado não trata do assunto; sugere §X)``: o destino quase não
  tem os termos do assunto e outro parágrafo os tem (preferindo ``assunto_em − k``);
- ``inconclusivo``: o parágrafo não foi localizado ou os indícios se contradizem.

Hash: o SHA-256 do ``--documento`` é comparado ao ``--sha256-entregue`` e ao
``sha256_declarado`` do auditor (aceita abreviado "9b2c0e20…e466e5" ou "9b2c0e20...e466e5",
comparando prefixo e sufixo); divergência gera o aviso "o auditor leu outra cópia".

Numeração do documento: a do Word, na visão com alterações aceitas, pelo
``docx_para_md.paragrafos`` (corpo = primeiro numId com parágrafos de nível 0).

Uso::

    conferir_achados_externos.py --documento V.docx --achados ACHADOS.json \\
        [--sha256-entregue HASH] [--json SAIDA.json] [--md SAIDA.md]

Código de saída: 0 se nenhum "erro real", 1 se houver erro real, 2 em erro de uso.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import unicodedata
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docx_para_md as dm  # noqa: E402
import parecer_md as pm  # noqa: E402

DESLOCAMENTOS = range(-3, 4)
LIMIAR_TRATA = 0.5  # cobertura do assunto a partir da qual o destino trata dele
LIMIAR_NAO_TRATA = 0.25  # abaixo disso, o destino não trata do assunto
FOLGA_SUGESTAO = 0.3  # o parágrafo sugerido tem de cobrir pelo menos isto a mais que o destino

STOP = set(
    """a o as os de da do das dos e em no na nos nas que se por para com um uma uns umas ao aos à às é ser
    foi não ou mais como sua seu suas seus esse essa este esta isso isto pelo pela pelos pelas já sem há
    ela ele elas eles lhe nem mas porém também entre sobre sob até após ante contra desde perante quando
    onde qual quais quem cujo cuja seja são está estão sido ter tem têm era eram será serão pode podem
    deve devem dever caso ainda apenas cada outro outra outros outras mesmo mesma assim tal tais aqui
    art arts artigo artigos lei nº n parágrafo parágrafos item itens si x vs versus etc cita citado
    """.split()
)


def sem_acento(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", t) if not unicodedata.combining(c)).lower()


_STOP_N = {sem_acento(w) for w in STOP}
_TOKEN_RE = re.compile(r"\d+(?:[.,]\d+)*(?:-[a-z]{1,3}\b)?|[a-z]+")


def termos(texto: str) -> set[str]:
    """Radicais de 5 letras das palavras de conteúdo; números e dispositivos ("440-bf", "81.930") inteiros."""
    out = set()
    for t in _TOKEN_RE.findall(sem_acento(texto)):
        if t[0].isdigit():
            if len(t) >= 2:
                out.add(t)
        elif len(t) >= 3 and t not in _STOP_N:
            out.add(t[:5])
    return out


# ---------------------------------------------------------------- hash

def _hash_norm(h: str | None) -> str | None:
    if not h:
        return None
    return h.strip().strip("`").lower().replace("...", "…").replace(" ", "")


def hash_confere(declarado: str | None, real: str) -> bool | None:
    """True/False quando há declaração; aceita abreviado "prefixo…sufixo". None sem declaração."""
    d = _hash_norm(declarado)
    if not d:
        return None
    real = real.lower()
    if "…" in d:
        pre, _, suf = d.partition("…")
        return bool(pre or suf) and real.startswith(pre) and real.endswith(suf)
    return d == real


def conferir_hash(sha_doc: str, entregue: str | None, declarado: str | None, auditor: str) -> dict:
    """Compara o hash do documento conferido com o entregue e com o declarado pelo auditor."""
    avisos = []
    doc_e_entregue = hash_confere(entregue, sha_doc)
    if doc_e_entregue is False:
        avisos.append(f"o documento conferido (sha256 {sha_doc}) não é o entregue ao auditor ({entregue}); "
                      "refaça a conferência com a cópia entregue")
    declarado_confere = hash_confere(declarado, sha_doc)
    ent = _hash_norm(entregue)
    if declarado_confere is False and ent and re.fullmatch(r"[0-9a-f]{64}", ent) and hash_confere(declarado, ent):
        declarado_confere = True  # o auditor leu o entregue; o problema é o documento conferido (aviso acima)
    if declarado is None:
        avisos.append(f"{auditor} não declarou o SHA-256 do arquivo lido; nada prova que leu a versão entregue")
    elif declarado_confere is False:
        avisos.append(f"o auditor leu outra cópia: {auditor} declarou sha256 {declarado}, mas o DOCX "
                      f"{'entregue' if entregue else 'conferido'} tem {entregue if ent and doc_e_entregue is False else sha_doc}; "
                      "os números de parágrafo dele podem não corresponder aos deste arquivo")
    return {"sha256_documento": sha_doc, "sha256_entregue": entregue, "sha256_declarado": declarado,
            "documento_e_o_entregue": doc_e_entregue, "declarado_confere": declarado_confere, "avisos": avisos}


# ---------------------------------------------------------------- documento

@dataclass
class Documento:
    pars: list[dm.Paragrafo]
    corpo: dict[int, dm.Paragrafo]  # número do corpo -> parágrafo
    idf: dict[str, float]
    termos_corpo: dict[int, set[str]]

    def unidade(self, numero: int) -> list[dm.Paragrafo]:
        """O parágrafo do corpo e as listas que o continuam (marcadores e itens de outro numId)."""
        p = self.corpo.get(numero)
        if p is None:
            return []
        out = [p]
        for q in self.pars[p.indice + 1:]:
            if q.corpo or q.titulo or not q.num_id:
                break
            out.append(q)
        return out


def ler_documento(path: Path) -> Documento:
    pars = dm.paragrafos(path)
    corpo = {p.numero: p for p in pars if p.corpo}  # type: ignore[misc]
    termos_corpo = {n: termos(p.plano) for n, p in corpo.items()}
    df: dict[str, int] = {}
    for ts in termos_corpo.values():
        for t in ts:
            df[t] = df.get(t, 0) + 1
    n = max(len(termos_corpo), 1)
    idf = {t: math.log((n + 1) / (c + 1)) + 1 for t, c in df.items()}
    return Documento(pars, corpo, idf, termos_corpo)


def citados(unidade: list[dm.Paragrafo]) -> set[int]:
    out: set[int] = set()
    for p in unidade:
        for _, nums in pm.remissoes(p.plano):
            out.update(nums)
    return out


# ---------------------------------------------------------------- localização do "onde"

ONDE_NUM_RE = re.compile(r"^\s*(?:§+\s*|par[áa]grafos?\s+|par\.\s*)?(\d+)\s*$", re.IGNORECASE)
ITEM_RE = re.compile(r"\b(?:item|al[íi]nea|letra)\s+\(?([a-z]|\d+|[ivxlc]+)\)?", re.IGNORECASE)


def _inicio(p: dm.Paragrafo) -> str:
    return sem_acento(p.plano).lstrip(" *-—–(")


def localizar_rotulo(doc: Documento, onde: str) -> tuple[list[dm.Paragrafo], str] | None:
    """"quadro, item a" → parágrafo que começa com "a)" depois do que começa com "Quadro"; senão, trecho literal."""
    m = ITEM_RE.search(onde)
    ancora = sem_acento(re.split(r",|\bitem\b|\bal[íi]nea\b|\bletra\b", onde, flags=re.IGNORECASE)[0]).strip(" ,.;:")
    if m and ancora:
        rot = sem_acento(m.group(1))
        for i, p in enumerate(doc.pars):
            if not _inicio(p).startswith(ancora):
                continue
            for j, q in enumerate(doc.pars[i + 1:i + 60], start=i + 1):
                if q.corpo or q.titulo:
                    break
                if re.match(rf"\(?{re.escape(rot)}[).]\s", _inicio(q)):
                    unidade = [q]
                    for r in doc.pars[j + 1:]:
                        if r.corpo or r.titulo or re.match(r"\(?[a-z0-9]{1,4}[).]\s", _inicio(r)) or \
                                sem_acento(r.plano).startswith("em qualquer hipotese"):
                            break
                        unidade.append(r)
                    rotulo = q.plano[:40].rstrip() + ("…" if len(q.plano) > 40 else "")
                    ancora_txt = re.match(r"[^.:;]{1,40}", p.plano.strip(" *"))
                    return unidade, f"«{rotulo}» (após «{ancora_txt.group(0) if ancora_txt else p.plano[:30]}»)"
    alvo = sem_acento(onde).strip()
    if len(alvo) >= 12:
        for p in doc.pars:
            if alvo in sem_acento(p.plano):
                return [p], (f"§{p.numero}" if p.corpo else f"«{p.plano[:40].rstrip()}…»")
    return None


# ---------------------------------------------------------------- assunto

def cobertura(doc: Documento, ts: set[str], numeros) -> float:
    pesos = {t: doc.idf[t] for t in ts if t in doc.idf}
    total = sum(pesos.values())
    if not total:
        return 0.0
    presentes: set[str] = set()
    for n in numeros:
        presentes |= doc.termos_corpo.get(n, set())
    return sum(w for t, w in pesos.items() if t in presentes) / total


@dataclass
class Resultado:
    indice: int
    onde: str
    remete: list[int]
    assunto_em: list[int]
    assunto: str
    onde_documento: str | None = None
    remete_documento: list[int] = field(default_factory=list)
    k: int | None = None
    ks_consistentes: list[int] = field(default_factory=list)
    cobertura_destino: float | None = None
    melhor: list[int] = field(default_factory=list)
    cobertura_melhor: float | None = None
    veredito: str = "inconclusivo"
    motivo: str = ""
    sugestao: int | None = None


@dataclass
class _Analise:
    achado: dict
    numero: int | None  # onde numérico (numeração do auditor)
    rotulo: tuple[list[dm.Paragrafo], str] | None
    loc: dict[int, tuple[list[dm.Paragrafo], list[int], str]]  # k -> (unidade, destino no documento, modo)
    consistentes: list[int]


def _analisar(doc: Documento, a: dict) -> _Analise:
    onde = str(a.get("onde", "")).strip()
    remete = [int(x) for x in a.get("remete") or []]
    assunto_em = [int(x) for x in a.get("assunto_em") or []]
    m = ONDE_NUM_RE.match(onde)
    numero = int(m.group(1)) if m else None
    rotulo = None if m else localizar_rotulo(doc, onde)
    loc: dict[int, tuple[list[dm.Paragrafo], list[int], str]] = {}
    for k in DESLOCAMENTOS:
        unidade = doc.unidade(numero - k) if numero is not None else (rotulo[0] if rotulo else [])
        if not unidade or not remete:
            continue
        cit = citados(unidade)
        if set(remete) <= cit:
            loc[k] = (unidade, sorted(set(remete)), "literal")
        elif k and {r - k for r in remete} <= cit:
            loc[k] = (unidade, sorted({r - k for r in remete}), "convertida")
    consistentes = []
    for k, (_, destino, _) in loc.items():
        if assunto_em:
            if {x - k for x in assunto_em} <= set(destino):
                consistentes.append(k)
        elif numero is not None:
            consistentes.append(k)
    return _Analise(a, numero, rotulo, loc, sorted(consistentes))


def deslocamento_dominante(analises: list[_Analise]) -> tuple[int | None, int]:
    contagem = {k: sum(k in an.consistentes for an in analises) for k in DESLOCAMENTOS}
    melhor = max(contagem.values(), default=0)
    if not melhor:
        return None, 0
    k = min((k for k, c in contagem.items() if c == melhor), key=lambda k: (abs(k), k))
    return k, melhor


def _fmt(nums) -> str:
    return ", ".join(f"§{n}" for n in nums) or "—"


def _desloc(k: int) -> str:
    return f"{k:+d}".replace("-", "−")


def julgar(doc: Documento, an: _Analise, indice: int, k_dom: int | None) -> Resultado:
    a = an.achado
    res = Resultado(indice, str(a.get("onde", "")), [int(x) for x in a.get("remete") or []],
                    [int(x) for x in a.get("assunto_em") or []], str(a.get("assunto", "")))
    res.ks_consistentes = an.consistentes
    if an.consistentes:
        k = k_dom if k_dom in an.consistentes else min(an.consistentes, key=lambda x: (abs(x - (k_dom or 0)), abs(x)))
    elif an.loc:
        k = k_dom if k_dom in an.loc else min(an.loc, key=lambda x: (abs(x - (k_dom or 0)), abs(x)))
    else:
        k = None
    ts = termos(res.assunto)
    if k is None:
        if an.numero is None and an.rotulo is None:
            res.motivo = f"não localizei «{res.onde}» no documento"
        elif an.numero is not None:
            res.motivo = (f"nenhum §{an.numero - 3}…§{an.numero + 3} cita {', '.join(map(str, res.remete))} "
                          "(nem convertidos pelo deslocamento); talvez o auditor tenha lido outra versão")
        else:
            res.onde_documento = an.rotulo[1]
            res.motivo = f"{an.rotulo[1]} não cita {', '.join(map(str, res.remete))}"
        if res.remete and ts:
            cob = cobertura(doc, ts, res.remete)
            res.cobertura_destino = round(cob, 2)
            res.motivo += f"; cobertura do assunto em {_fmt(res.remete)}: {cob:.0%}"
        return res
    unidade, destino, modo = an.loc[k]
    res.k = k if an.numero is not None or res.assunto_em else None
    res.remete_documento = destino
    res.onde_documento = f"§{unidade[0].numero}" if unidade[0].corpo else (an.rotulo[1] if an.rotulo else unidade[0].plano[:40])
    proprio = {p.numero for p in unidade if p.corpo}
    explica = bool(res.assunto_em) and {x - k for x in res.assunto_em} <= set(destino) and k != 0
    deslocado = f" (auditor deslocado em {_desloc(k)})" if (res.k is not None and k != 0) else ""

    if not ts or not any(t in doc.idf for t in ts):
        trata, cob, melhor, cob_melhor = None, None, [], None
    else:
        cob = cobertura(doc, ts, destino)
        scores = {n: cobertura(doc, ts, [n]) for n in doc.corpo if n not in proprio}
        cob_melhor = max(scores.values(), default=0.0)
        melhor = sorted(n for n, s in scores.items() if cob_melhor and s >= 0.85 * cob_melhor)
        if cob >= LIMIAR_TRATA or (cob_melhor and cob >= 0.75 * cob_melhor and cob >= LIMIAR_NAO_TRATA):
            trata = True
        elif cob < LIMIAR_NAO_TRATA and cob_melhor >= LIMIAR_TRATA and cob_melhor - cob >= FOLGA_SUGESTAO:
            trata = False
        else:
            trata = None
        res.cobertura_destino, res.cobertura_melhor, res.melhor = round(cob, 2), round(cob_melhor, 2), melhor[:6]
    nota_modo = "" if modo == "literal" else " (remissão convertida pelo deslocamento)"
    loc_txt = f"{res.onde} do auditor é {res.onde_documento} do documento, que cita {_fmt(destino)}{nota_modo}"
    if trata is True:
        res.veredito = "correta" + deslocado
        res.motivo = f"{loc_txt}; o destino trata do assunto (cobertura {cob:.0%})"
        if explica:
            res.motivo += f"; o auditor situa o assunto em {_fmt(res.assunto_em)}, que é {_fmt(sorted({x - k for x in res.assunto_em}))} aqui"
    elif trata is None and explica:
        res.veredito = "correta" + deslocado
        cob_txt = f"cobertura {cob:.0%}" if cob is not None else "sem termos aproveitáveis"
        res.motivo = (f"{loc_txt}; o auditor situa o assunto em {_fmt(res.assunto_em)}, que é "
                      f"{_fmt(sorted({x - k for x in res.assunto_em}))} aqui ({cob_txt}; termos não decidem sozinhos)")
    elif trata is False and not explica:
        candidatos = [x - k for x in res.assunto_em if x - k in melhor] or \
            sorted(melhor, key=lambda n: (min(abs(n - d) for d in destino), n))
        res.sugestao = candidatos[0] if candidatos else None
        res.veredito = f"erro real (o destino citado não trata do assunto; sugere §{res.sugestao})"
        res.motivo = (f"{loc_txt}; o destino cobre {cob:.0%} dos termos do assunto, e §{res.sugestao} cobre "
                      f"{cobertura(doc, ts, [res.sugestao]):.0%}")
    else:
        res.veredito = "inconclusivo"
        if trata is False:
            res.motivo = (f"{loc_txt}; o deslocamento explica a divergência do auditor, mas o destino cobre só "
                          f"{cob:.0%} dos termos (melhor: {_fmt(melhor[:3])}, {cob_melhor:.0%}); conferir à mão")
        else:
            cob_txt = f"{cob:.0%}" if cob is not None else "sem termos aproveitáveis"
            res.motivo = f"{loc_txt}; cobertura do assunto no destino {cob_txt}, sem indício decisivo; conferir à mão"
    return res


# ---------------------------------------------------------------- relatório

def conferir(documento: Path, achados: dict, sha256_entregue: str | None = None) -> dict:
    doc = ler_documento(documento)
    auditor = str(achados.get("auditor") or "auditor")
    lista = achados.get("achados") or []
    analises = [_analisar(doc, a) for a in lista]
    k_dom, n_dom = deslocamento_dominante(analises)
    resultados = [julgar(doc, an, i, k_dom) for i, an in enumerate(analises, start=1)]
    hash_ = conferir_hash(dm.sha256_arquivo(documento), _hash_norm(sha256_entregue) if sha256_entregue else None,
                          achados.get("sha256_declarado"), auditor)
    m = len(lista)
    if k_dom is None:
        texto = f"nenhum deslocamento consistente em {m} achados"
    else:
        texto = f"deslocamento sistemático de {_desloc(k_dom) if k_dom else '0'} em {n_dom} de {m} achados"
    resumo = {"correta": 0, "erro real": 0, "inconclusivo": 0}
    for r in resultados:
        resumo["erro real" if r.veredito.startswith("erro real") else r.veredito.split(" (")[0]] += 1
    return {
        "documento": str(documento), "auditor": auditor, "paragrafos_corpo": len(doc.corpo),
        "hash": hash_,
        "deslocamento": {"k": k_dom, "achados_consistentes": n_dom, "achados": m, "texto": texto,
                         "convencao": "k = numeração do auditor − numeração do documento"},
        "resumo": resumo,
        "achados": [asdict(r) for r in resultados],
    }


def _cel(t) -> str:
    return str(t).replace("|", "\\|").replace("\n", " ")


def relatorio_md(r: dict) -> str:
    h = r["hash"]
    linhas = [f"# Conferência dos achados de {r['auditor']}", "",
              f"Documento: `{Path(r['documento']).name}` — sha256 `{h['sha256_documento']}` "
              f"({r['paragrafos_corpo']} parágrafos no corpo numerado)", ""]
    if h["sha256_declarado"]:
        linhas.append(f"SHA-256 declarado pelo auditor: `{h['sha256_declarado']}`"
                      + ("" if not h["sha256_entregue"] else f"; entregue: `{h['sha256_entregue']}`"))
    for a in h["avisos"]:
        linhas.append(f"- **Atenção:** {a}")
    s = r["resumo"]
    linhas += ["", f"**{r['deslocamento']['texto'].capitalize()}** ({r['deslocamento']['convencao']}).",
               f"Vereditos: {s['correta']} corretas, {s['erro real']} erros reais, {s['inconclusivo']} inconclusivos.", "",
               "| achado | onde (auditor → documento) | remete | veredito | motivo |",
               "|---|---|---|---|---|"]
    for a in r["achados"]:
        onde = f"{a['onde']} → {a['onde_documento'] or '?'}"
        rem = ", ".join(map(str, a["remete"])) + (f" → {', '.join(map(str, a['remete_documento']))}"
                                                   if a["remete_documento"] and set(a["remete_documento"]) != set(a["remete"]) else "")
        linhas.append(f"| {a['indice']}. {_cel(a['assunto'])} | {_cel(onde)} | {_cel(rem)} | {_cel(a['veredito'])} | {_cel(a['motivo'])} |")
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--documento", type=Path, required=True, help=".docx auditado")
    ap.add_argument("--achados", type=Path, required=True, help="JSON com os achados de remissão do auditor")
    ap.add_argument("--sha256-entregue", help="SHA-256 do .docx entregue ao auditor (aceita abreviado prefixo…sufixo)")
    ap.add_argument("--json", type=Path, help="grava o resultado em JSON")
    ap.add_argument("--md", type=Path, help="grava o relatório em Markdown")
    try:
        args = ap.parse_args(argv)
    except SystemExit as e:
        return 2 if e.code else 0
    for f in (args.documento, args.achados):
        if not f.exists():
            print(f"arquivo não encontrado: {f}", file=sys.stderr)
            return 2
    try:
        achados = json.loads(args.achados.read_text(encoding="utf-8"))
        if not isinstance(achados, dict) or not isinstance(achados.get("achados"), list):
            raise ValueError("esperado objeto com a lista 'achados'")
        r = conferir(args.documento, achados, args.sha256_entregue)
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        print(f"achados inválidos: {e}", file=sys.stderr)
        return 2
    except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
        print(f"erro de leitura do .docx: {e}", file=sys.stderr)
        return 2
    md = relatorio_md(r)
    if args.json:
        args.json.write_text(json.dumps(r, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.md:
        args.md.write_text(md, encoding="utf-8")
    if not args.md and not args.json:
        print(md)
    for a in r["hash"]["avisos"]:
        print(f"atenção: {a}")
    s = r["resumo"]
    print(f"{r['deslocamento']['texto']}; {s['correta']} corretas, {s['erro real']} erros reais, "
          f"{s['inconclusivo']} inconclusivos")
    return 1 if s["erro real"] else 0


if __name__ == "__main__":
    sys.exit(main())
