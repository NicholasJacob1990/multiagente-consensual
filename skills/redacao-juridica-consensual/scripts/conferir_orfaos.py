#!/usr/bin/env python3
"""Acha as pontas soltas que um corte ou uma reescrita deixam num parecer ou numa peça.

Depois de condensar um texto, sobram referências a coisas que saíram: verbete da
ementa sem parágrafo correspondente, entrada das Referências que ninguém mais cita,
julgado citado no corpo que nunca entrou nas Referências, instrução editorial
esquecida entre colchetes no anexo, conta escrita só com símbolos. Nenhuma dessas
falhas aparece na leitura corrida; todas aparecem para o revisor externo.

Verificações:

- ``julgado_sem_referencia`` (bloqueante): julgado identificado no corpo (número do
  TJMG, RE, REsp, ADI, Súmula…) sem entrada nas Referências. Precedente que não foi
  levado às Referências costuma ser precedente que não foi conferido.
- ``referencia_nao_citada`` (alerta): entrada das Referências (autor, lei, provimento,
  julgado) que o corpo e os anexos não citam mais.
- ``verbete_sem_corpo`` (alerta): palavra-chave de verbete da ementa (trecho em caixa
  alta) que não aparece no corpo.
- ``instrucao_editorial`` (bloqueante): instrução entre colchetes deixada no texto
  ("[Relacionar apenas os documentos…]"). Campo a preencher ("[data]", "[NOME…]")
  é só informado.
- ``conta_com_simbolos`` (alerta): conta escrita com π, ÷, √ ou ≈. Os símbolos se
  perdem na extração de texto de outros leitores; escrever por extenso, com os
  valores intermediários.

Uso::

    conferir_orfaos.py DOCUMENTO.(docx|md|txt) [--json SAIDA]

Código de saída: 0 sem bloqueante; 1 com bloqueante; 2 erro de uso.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

TIT_REF = re.compile(r"^\s*(#+\s*)?(\*\*)?Refer[êe]ncias\b", re.I)
TIT_ANEXO = re.compile(r"^\s*(#+\s*)?(\*\*)?Anexo\b", re.I)
JULGADOS = [
    ("TJ", re.compile(r"\b(\d\.\d{4}\.\d{2}\.\d{6}-\d/\d{3})\b")),
    ("RE", re.compile(r"\bRecurso Extraordin[áa]rio(?: com Agravo)? n[ºo°]\s*([\d.]+)|\bRE n?[ºo°]?\s*([\d.]{4,})")),
    ("REsp", re.compile(r"\bRecurso Especial n[ºo°]\s*([\d.]+)|\bREsp n?[ºo°]?\s*([\d.]{4,})")),
    ("ADI", re.compile(r"\b(?:ADI|ADPF|ADC) n?[ºo°]?\s*([\d.]{2,})")),
    ("Súmula", re.compile(r"\bS[úu]mulas?(?: Vinculante)? n[ºo°]\s*(\d+)(?:\s+e n[ºo°]\s*(\d+))?")),
]
NORMAS = re.compile(r"\b(Lei(?: Complementar)?|Decreto(?:-Lei)?|Provimento(?: Conjunto)?|Resolu[çc][ãa]o|S[úu]mula(?: Vinculante)?) n[ºo°]\s*([\d.]+)")
VERBOS_EDITORIAIS = re.compile(r"^\s*(relacionar|inserir|preencher|conferir|ajustar|indicar|completar|verificar|revisar|confirmar|incluir|substituir|adaptar|anexar|juntar|citar)\b", re.I)
SIMBOLOS = re.compile(r"[π÷√≈]")
CODIGOS = {"10406": "codigo civil", "3071": "codigo civil de 1916", "5869": "codigo de processo civil de 1973",
           "13105": "codigo de processo civil", "8078": "defesa do consumidor", "5172": "tributario nacional",
           "6015": "registros publicos", "2848": "codigo penal", "5452": "consolidacao das leis do trabalho"}
PARADAS = {"subsequente", "constituida", "estrita", "imediato", "ativa", "direito", "estadual", "federal", "juridica", "juridico", "minas", "gerais", "codigo", "nacional", "conselho",
           "corregedoria", "justica", "registro", "imoveis", "oficio", "sujeita", "sujeitos", "proprios", "numericamente",
           "conclusiva", "institucional", "administrativo", "administrativa", "favor", "desenvolvimento", "companhia"}


def ler(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import docx_para_md  # noqa: E402
        return docx_para_md.converter(path)
    return path.read_text(encoding="utf-8")


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def _digitos(t: str) -> str:
    return re.sub(r"\D", "", t)


def _numeros(t: str) -> str:
    """Texto com os números sem ponto de milhar, para achar "22.432" em "22.432/2016"."""
    return re.sub(r"(?<=\d)\.(?=\d)", "", t)


def _tem_numero(num: str, texto_numeros: str) -> bool:
    d = _digitos(num)
    return bool(d) and re.search(r"(?<!\d)" + d + r"(?!\d)", texto_numeros) is not None


def secoes(texto: str) -> tuple[list[str], list[str]]:
    """(linhas fora das Referências, entradas das Referências)."""
    fora, refs, em_ref = [], [], False
    for linha in texto.split("\n"):
        l = linha.strip()
        if not l or l.startswith("<!--"):
            continue
        if TIT_REF.match(l):
            em_ref = True
            continue
        if em_ref and (TIT_ANEXO.match(l) or l.startswith("#")):
            em_ref = False
        (refs if em_ref else fora).append(l)
    return fora, refs


def conferir(texto: str) -> dict:
    fora, refs = secoes(texto)
    corpo = "\n".join(fora)
    corpo_plano, refs_txt = _plano(corpo), "\n".join(refs)
    refs_num, corpo_num = _numeros(refs_txt), _numeros(corpo)
    achados: list[dict] = []

    def add(tipo, grav, msg, trecho=""):
        achados.append({"tipo": tipo, "gravidade": grav, "mensagem": msg, "trecho": trecho[:200]})

    if refs:
        vistos = set()
        for classe, pad in JULGADOS:
            for m in pad.finditer(corpo):
                for num in filter(None, m.groups()):
                    d = _digitos(num)
                    if not d or (classe, d) in vistos:
                        continue
                    vistos.add((classe, d))
                    if classe == "TJ":
                        achou = _digitos(num) in _digitos(refs_txt) or _digitos(num)[:-3] in _digitos(refs_txt)
                    else:
                        achou = _tem_numero(num, refs_num)
                    if not achou:
                        add("julgado_sem_referencia", "bloqueante",
                            f"{classe} {num.strip('.')} é citado no corpo e não tem entrada nas Referências: confirmar o julgado e incluí-lo, ou retirar a citação",
                            corpo[max(0, m.start() - 60):m.end() + 40])
        for r in refs:
            cab = r[:160]
            chave, ok = None, True
            ma = re.match(r"^([A-ZÀ-Ú][A-ZÀ-Ú' -]{2,}),", r)
            mj = next(((c, m) for c, p in JULGADOS for m in [p.search(r)] if m), None)
            mn = NORMAS.search(cab)
            if ma:
                chave = ma.group(1).strip()
                ok = _plano(chave.split()[-1] if len(chave.split()[-1]) > 3 else chave) in corpo_plano
            elif mj:
                chave = next(g for g in mj[1].groups() if g)
                ok = (_digitos(chave)[:-3] in _digitos(corpo)) if mj[0] == "TJ" else _tem_numero(chave, corpo_num)
            elif mn:
                chave = f"{mn.group(1)} nº {mn.group(2).rstrip('.')}"
                ok = _tem_numero(mn.group(2), corpo_num) or CODIGOS.get(_digitos(mn.group(2)), "\0") in corpo_plano
            if chave and not ok:
                add("referencia_nao_citada", "alerta", f"«{chave}» consta das Referências e não é citado no corpo nem nos anexos", r)
    for l in fora[:40]:   # a ementa fica no início; caixa alta mais adiante é endereçamento ou citação
        letras = [c for c in l if c.isalpha()]
        if len(l) > 100 and letras and sum(c.isupper() for c in letras) / len(letras) > 0.85 and not l.lstrip("*").startswith("EMENTA:"):
            resto = _plano("\n".join(x for x in fora if x != l))
            for verbete in re.split(r"\.\s+", l):
                for palavra in re.findall(r"[A-ZÀ-Ú]{7,}", verbete):
                    p = _plano(palavra)
                    if p in PARADAS or p[:6] in resto:
                        continue
                    add("verbete_sem_corpo", "alerta", f"verbete da ementa «{palavra}» não tem correspondência no corpo: retirar do verbete ou tratar no texto", verbete.strip())
    for m in re.finditer(r"\[([^\[\]]{3,})\]", corpo):
        dentro = m.group(1).strip()
        if re.fullmatch(r"\^?\w{1,12}|[\d.,\s-]+|s\.\s?[ln]\.|\d+\.\s*reimpr\.?|sic|\.\.\.|…", dentro, re.I):
            continue
        if VERBOS_EDITORIAIS.match(dentro) and len(dentro) > 20:
            add("instrucao_editorial", "bloqueante", "instrução editorial entre colchetes no texto: retirar da peça e levar à lista de providências", m.group(0))
        else:
            add("campo_a_preencher", "informativo", "campo a preencher antes de assinar ou protocolar", m.group(0))
    for l in fora:
        if SIMBOLOS.search(l) and re.search(r"\d", l):
            add("conta_com_simbolos", "alerta", "conta escrita com símbolos (π, ÷, √, ≈): escrever por extenso, com os valores intermediários", SIMBOLOS.search(l).group(0) + " em: " + l[:120])
    bloq = [a for a in achados if a["gravidade"] == "bloqueante"]
    return {"achados": achados, "bloqueantes": len(bloq), "alertas": sum(a["gravidade"] == "alerta" for a in achados), "ok": not bloq}


def relatorio(r: dict) -> str:
    L = ["## Pontas soltas", ""]
    if not r["achados"]:
        return "\n".join(L + ["Nenhuma ponta solta encontrada."])
    for a in r["achados"]:
        L.append(f"- [{a['gravidade'].upper()}] {a['tipo']}: {a['mensagem']}" + (f" — «{a['trecho']}»" if a["trecho"] else ""))
    L += ["", f"Resultado: {r['bloqueantes']} bloqueante(s), {r['alertas']} alerta(s)."]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("documento", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args(argv)
    try:
        r = conferir(ler(a.documento))
    except (OSError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    print(relatorio(r))
    if a.json:
        a.json.write_text(json.dumps(r, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
