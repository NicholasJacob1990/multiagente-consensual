#!/usr/bin/env python3
"""Confere o espelhamento entre o anexo de redações sugeridas, a minuta e o parecer.

O mesmo dispositivo tem de ter a mesma redação, palavra por palavra, no bloco
do anexo e na minuta revisada. Este script lê os blocos do anexo marcados com
``(NR)`` (nova redação) ou ``(AC)`` (acrescido) e procura cada um na minuta:

- ``igual``: o bloco é um parágrafo, uma célula ou uma linha de tabela da minuta;
- ``contido``: o bloco está dentro do texto corrido da minuta (bloco que reúne
  um inciso e suas alíneas, por exemplo);
- ``por_partes``: bloco que reproduz uma linha de tabela em prosa rotulada
  ("Etapa. Responsável: X; Prazo: Y") ou com as opções entre parênteses
  ("Pergunta? (Sim / Não)"), cujas partes aparecem todas no mesmo parágrafo ou
  na mesma linha de tabela da minuta (partes espalhadas por linhas diferentes
  contam como divergência);
- ``fora_da_minuta``: bloco iniciado por colchete ("[Edital – item a definir]"),
  que não pertence à minuta;
- ``divergente``: nenhum dos casos; o relatório mostra o trecho mais próximo.

Rótulo antes da marca é aceito ("Item 3 (NR): texto", "Linha “X” (AC): texto").
Linhas de classificação, fundamento e observação do item são ignoradas.

Com ``--parecer`` e ``--mudancas``, procura no parecer trechos da redação
superada: para cada par antes/depois, os segmentos que mudaram, com algumas
palavras de contexto, não podem continuar citados no parecer.

Entradas em ``.docx`` (visão com as alterações aceitas: inserções entram,
exclusões saem), ``.md`` ou ``.txt``. O JSON de mudanças é uma lista de objetos
com ``texto_atual`` e ``texto_final`` (ou ``antes`` e ``depois``); entradas
com ``"documento": "parecer"`` são ignoradas.

Exemplo::

    espelho_redacoes.py --anexo anexo.docx --minuta minuta_revisada.docx \\
        --parecer parecer.docx --mudancas mudancas.json --json espelho.json

Sai com código 1 se houver bloco divergente, redação superada no parecer ou se
nenhum bloco (NR)/(AC) for reconhecido no anexo.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
MARCA = re.compile(r"\s*\((NR|AC)\)\s*")
PARTE = re.compile(r"[;.]\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ú /()-]{0,40}:\s)")
OPCOES = re.compile(r"^(.*\S)\s+\(([^()]+)\)\.?$")
META = ("Classificação:", "Fundamento:", "Observação:", "Nota:")
ROTULO = re.compile(r"^[A-ZÁÉÍÓÚÂÊÔÃÕÇ][\wÀ-ú /()-]{0,40}:\s+")


def norm(t: str) -> str:
    t = t.replace(" ", " ").replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", t).strip()


def _texto_p(p: ET.Element) -> str:
    out = []
    for el in p.iter():
        if el.tag == W + "t":
            out.append(el.text or "")
        elif el.tag in (W + "tab",):
            out.append(" ")
        elif el.tag in (W + "br", W + "cr"):
            out.append(" ")
    return "".join(out)


def _fora(el: ET.Element, pais: dict) -> bool:
    """Texto excluído ou movido para fora não entra na visão aceita."""
    while el is not None:
        if el.tag in (W + "del", W + "moveFrom"):
            return True
        el = pais.get(el)
    return False


def ler_docx(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as z:
        root = ET.fromstring(z.read("word/document.xml"))
    pais = {c: p for p in root.iter() for c in p}
    for el in list(root.iter()):
        if el.tag == W + "t" and _fora(el, pais):
            el.text = ""
    body = root.find(W + "body")
    unidades: list[str] = []

    def visitar(el: ET.Element) -> None:
        for c in el:
            if c.tag == W + "p":
                unidades.append(_texto_p(c))
            elif c.tag == W + "tbl":
                for tr in c.iter(W + "tr"):
                    celulas = [" ".join(_texto_p(p) for p in tc.iter(W + "p")) for tc in tr.iter(W + "tc")]
                    unidades.extend(celulas)
                    unidades.append(" || ".join(celulas))
            else:
                visitar(c)

    visitar(body)
    return [norm(u) for u in unidades if norm(u)]


def ler_texto(path: Path) -> list[str]:
    unidades = []
    for linha in path.read_text(encoding="utf-8").splitlines():
        linha = re.sub(r"^\s*(?:[-*>]\s+|\d+\.\s+)", "", linha)
        if linha.strip().startswith("|") and linha.strip().endswith("|"):
            celulas = [norm(c) for c in linha.strip().strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in celulas if c):
                continue
            unidades.extend(celulas)
            unidades.append(" || ".join(celulas))
        else:
            unidades.append(norm(linha))
    return [u for u in unidades if u]


def ler(path: Path) -> list[str]:
    return ler_docx(path) if path.suffix.lower() == ".docx" else ler_texto(path)


def blocos_do_anexo(unidades: list[str], ignorar: tuple[str, ...] = META) -> list[dict]:
    blocos = []
    for u in unidades:
        if u.startswith(ignorar):  # linhas de classificação, fundamento e observação do item
            continue
        m = None
        for m in MARCA.finditer(u):
            pass
        if m is None:
            continue
        if m.end() == len(u):  # marca no fim: o bloco é o texto anterior
            nucleo, rotulo = u[: m.start()], ""
        elif u[m.end():].startswith(":"):  # rótulo antes da marca: o bloco vem depois dos dois-pontos
            nucleo, rotulo = u[m.end():].lstrip(": "), u[: m.start()]
        else:
            continue
        blocos.append({"bloco": u, "rotulo": norm(rotulo), "texto": norm(nucleo), "marca": m.group(1)})
    return blocos


def classificar(bloco: dict, unidades: set[str], corrido: str, lista: list[str]) -> dict:
    t = bloco["texto"]
    if t.startswith("["):
        return {"estado": "fora_da_minuta"}
    if t in unidades:
        return {"estado": "igual"}
    if t in corrido:
        return {"estado": "contido"}
    partes = [ROTULO.sub("", p).strip().rstrip(".") for p in PARTE.split(t)]
    m = OPCOES.match(partes[-1])
    if m:  # opções de resposta entre parênteses ("(Sim / Não)") são outra coluna
        partes[-1:] = [m.group(1), m.group(2)]
    if len(partes) > 1 and all(partes):
        # todas as partes na mesma unidade (parágrafo ou linha de tabela "a || b || c"): responsável e prazo
        # espalhados por linhas diferentes não espelham a linha
        if any(all(p in u for p in partes) for u in lista):
            return {"estado": "por_partes"}
        if all(p in corrido for p in partes):
            proximo, razao = _mais_proximo(t, lista)
            return {"estado": "divergente", "mais_proximo": proximo[:300], "semelhanca": razao,
                    "motivo": "as partes existem na minuta, mas em linhas ou parágrafos diferentes"}
    proximo, razao = _mais_proximo(t, lista)
    return {"estado": "divergente", "mais_proximo": proximo[:300], "semelhanca": razao}


def _mais_proximo(t: str, lista: list[str]) -> tuple[str, float]:
    proximo = max(lista, key=lambda u: difflib.SequenceMatcher(None, t, u, autojunk=False).quick_ratio(), default="")
    razao = difflib.SequenceMatcher(None, t, proximo, autojunk=False).ratio() if proximo else 0.0
    return proximo, round(razao, 2)


def segmentos_superados(antes: str, depois: str, contexto: int = 8, minimo: int = 35) -> list[str]:
    a = re.findall(r"\S+|\s+", norm(antes))
    b = re.findall(r"\S+|\s+", norm(depois))
    segs = []
    for tag, i1, i2, _j1, _j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if tag == "equal":
            continue
        seg = "".join(a[max(0, i1 - contexto): i2 + contexto]).strip()
        if len(seg) >= minimo and seg not in norm(depois):
            segs.append(seg)
    return segs


def conferir(anexo: Path, minuta: Path, parecer: Path | None = None, mudancas: Path | None = None) -> dict:
    lista = ler(minuta)
    unidades = set(lista)
    corrido = " ".join(lista)
    blocos = blocos_do_anexo(ler(anexo))
    for b in blocos:
        b.update(classificar(b, unidades, corrido, lista))
    resultado = {"blocos": blocos, "superadas_no_parecer": []}
    if parecer and mudancas:
        texto_parecer = " ".join(ler(parecer))
        for m in json.loads(mudancas.read_text(encoding="utf-8")):
            if m.get("documento") == "parecer":  # mudança do próprio parecer não é redação de dispositivo
                continue
            antes = m.get("texto_atual", m.get("antes", ""))
            depois = m.get("texto_final", m.get("depois", ""))
            for seg in segmentos_superados(antes, depois):
                if seg in texto_parecer:
                    resultado["superadas_no_parecer"].append({"alvo": m.get("alvo", m.get("id", "")), "trecho": seg})
    contagem: dict[str, int] = {}
    for b in blocos:
        contagem[b["estado"]] = contagem.get(b["estado"], 0) + 1
    resultado["contagem"] = contagem
    resultado["sem_blocos"] = not blocos  # nenhum (NR)/(AC) reconhecido: nada foi conferido
    resultado["ok"] = bool(blocos) and not contagem.get("divergente") and not resultado["superadas_no_parecer"]
    return resultado


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anexo", type=Path, required=True)
    ap.add_argument("--minuta", type=Path, required=True)
    ap.add_argument("--parecer", type=Path)
    ap.add_argument("--mudancas", type=Path, help="JSON com pares texto_atual/texto_final")
    ap.add_argument("--json", type=Path, help="grava o relatório completo")
    args = ap.parse_args(argv)
    if bool(args.parecer) != bool(args.mudancas):
        ap.error("--parecer e --mudancas vão juntos")
    r = conferir(args.anexo, args.minuta, args.parecer, args.mudancas)
    if args.json:
        args.json.write_text(json.dumps(r, ensure_ascii=False, indent=1), encoding="utf-8")
    print("Blocos do anexo:", ", ".join(f"{k} {v}" for k, v in sorted(r["contagem"].items())) or "nenhum")
    if r["sem_blocos"]:
        print("- NENHUM BLOCO (NR)/(AC) reconhecido no anexo: nada foi conferido")
    for b in r["blocos"]:
        if b["estado"] == "divergente":
            print(f"- DIVERGENTE ({b['marca']}) {b['rotulo'] or ''} {b['texto'][:120]}")
            if b.get("motivo"):
                print(f"  {b['motivo']}")
            print(f"  mais próximo ({b['semelhanca']}): {b['mais_proximo'][:120]}")
    for s in r["superadas_no_parecer"]:
        print(f"- REDAÇÃO SUPERADA NO PARECER [{s['alvo']}]: {s['trecho'][:140]}")
    print("OK" if r["ok"] else "PENDÊNCIAS")
    return 0 if r["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
