#!/usr/bin/env python3
"""Acusa sugestões que reabrem decisão já tomada no caso.

Revisores (modelos ou pessoas) voltam a propor o que o usuário já decidiu: trocar a
requerente do anexo para "CODEMGE e/ou CODEMIG", passar a doutrina para nota de
rodapé, numerar o quadro de hipóteses, mudar o fecho. O caso guarda um registro das
decisões, com padrões que reconhecem a proposta contrária; este script procura cada
padrão nos textos (sugestões de revisor, achados JSON, minuta) e acusa o trecho com a
decisão vigente — "decisão já tomada — reabrir?".

Formato do registro (``decisoes.json``; há um modelo vazio em ``decisoes_modelo.json``)::

    {
      "caso": "SEI 0000.01.0000001/2026-01 — lotes 01 e 10",
      "decisoes": [
        {"id": "D1", "tema": "requerente do anexo",
         "decisao": "CODEMIG como interessada; não trocar para CODEMGE nem 'e/ou'",
         "padroes": ["codemge e/ou codemig", "trocar a requerente", "requerente.*codemge"],
         "data": "2026-11-03", "origem": "usuário"},
        {"id": "D4", "tema": "fecho", "decisao": "'É o parecer, sob censura.' (perfil GENES)",
         "padroes": ["sob censura"], "data": "2026-11-05", "origem": "perfil GENES"}
      ]
    }

``padroes`` são expressões regulares do módulo ``re``, escritas sem acento e aplicadas
ao texto normalizado (sem acento, minúsculo, espaços colapsados), como em
``checar_refutadas.py``. Decisão sem padrão (ex.: "perguntar sempre") é listada como
não verificável. Campo opcional ``ignorar_se`` (regex): descarta o acerto quando a
frase o contém.

Para não acusar o texto que CUMPRE a decisão: se a decisão traz entre aspas a forma
adotada ("'É o parecer, sob censura.'"; não conta a forma vedada, precedida de "não",
"nem", "sem": "nem 'e/ou'") e a frase do acerto a contém sem verbo de
mudança (trocar, substituir, remover, retirar, suprimir, alterar, "em vez de",
sugerir, recomendar...), o acerto é descartado. Em achados JSON, os campos com o
texto vigente (``trecho_atual``, ``texto_atual``, ``atual``, ``original``) não são lidos.

Textos: ``.md``/``.txt`` (linha a linha), ``.docx`` (parágrafos e notas) e ``.json``
(todas as cadeias de texto, com o caminho do campo como local).

Uso::

    checar_decisoes.py --decisoes decisoes.json sugestoes_revisor.md achados_grok.json parecer_v22.docx [--json acertos.json]

Código de saída: 1 quando há trecho que reabre decisão, 0 quando não há e 2 em erro
de uso ou de leitura. ``consolidar_correcoes.py --decisoes`` usa ``casar_texto`` e
tira da lista final a proposta que reabre decisão (status ``decisao_ja_tomada``).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checar_refutadas as cr  # noqa: E402

CAMPOS = ("id", "decisao")
CAMPOS_VIGENTES = {"trecho_atual", "texto_atual", "atual", "original", "texto_original"}
ASPAS_RE = re.compile(r"'([^']{3,})'|\"([^\"]{3,})\"|“([^”]{3,})”|‘([^’]{3,})’|«([^»]{3,})»")
MUDANCA_RE = re.compile(
    r"\b(?:troc|substitu|remov|retir|exclu|supri|alter|mud[ae]|elimin|apag|cort|sugir|sugere|sugest|recomend|"
    r"propo|deveria|melhor seria)\w*|\bem vez d|\bno lugar d|\bao inves d",
)


@dataclass
class Acerto:
    arquivo: str
    linha: int
    id: str
    tema: str
    trecho: str
    decisao: str
    data: str = ""
    origem: str = ""
    local: str = ""


def _sem_acento(p: str) -> str:
    """Tira acentos sem mexer na caixa (``\\S`` e ``\\W`` continuam o que são)."""
    return "".join(c for c in unicodedata.normalize("NFKD", p) if not unicodedata.combining(c))


def _so_palavras(t: str) -> str:
    return " ".join(re.findall(r"\w+", cr.normalizar(t)))


def carregar(path: Path | str) -> dict:
    return preparar(json.loads(Path(path).read_text(encoding="utf-8")))


def preparar(dados: dict) -> dict:
    """Valida e compila (``_rxs``, ``_ignorar``, ``_formas``). Decisão sem padrão vai para ``_sem_padrao``."""
    if dados.get("_preparado"):
        return dados
    if not isinstance(dados, dict) or not isinstance(dados.get("decisoes"), list):
        raise ValueError('registro de decisões: esperado {"caso": ..., "decisoes": [...]}')
    validas, sem_padrao = [], []
    for i, d in enumerate(dados["decisoes"]):
        if not isinstance(d, dict):
            raise ValueError(f"decisão {i + 1}: não é objeto JSON")
        if not str(d.get("id", "")).strip() and not str(d.get("decisao", "")).strip():
            continue  # item vazio do modelo
        if any(not str(d.get(c, "")).strip() for c in CAMPOS):
            raise ValueError(f"decisão {i + 1}: campos obrigatórios {', '.join(CAMPOS)}")
        padroes = d.get("padroes") or []
        if isinstance(padroes, str):
            padroes = [padroes]
        padroes = [p for p in padroes if str(p).strip()]
        try:
            d["_rxs"] = [re.compile(_sem_acento(p), re.IGNORECASE) for p in padroes]
            d["_ignorar"] = re.compile(_sem_acento(d["ignorar_se"]), re.IGNORECASE) if d.get("ignorar_se") else None
        except re.error as e:
            raise ValueError(f"decisão {d['id']}: regex inválida ({e})") from e
        d["_formas"] = formas_adotadas(d["decisao"])
        (validas if d["_rxs"] else sem_padrao).append(d)
    dados["decisoes"] = validas
    dados["_sem_padrao"] = sem_padrao
    dados["_preparado"] = True
    return dados


NEGACAO_ANTES_RE = re.compile(r"\b(?:nao|nem|sem|evitar|jamais|nunca|exceto|salvo|nada de)\b[^'\"“‘«]{0,30}$")


def formas_adotadas(decisao: str) -> list[str]:
    """Formas entre aspas que a decisão ADOTA (duas palavras ou mais, sem negação logo antes: "nem 'e/ou'" não conta)."""
    out = []
    for m in ASPAS_RE.finditer(decisao):
        if NEGACAO_ANTES_RE.search(cr.normalizar(decisao[:m.start()])):
            continue
        f = _so_palavras(next(g for g in m.groups() if g))
        if len(f.split()) >= 2:
            out.append(f)
    return out


def _cumpre(d: dict, frase_norm: str) -> bool:
    """A frase traz a forma adotada pela decisão e nenhum verbo de mudança."""
    if not d["_formas"] or MUDANCA_RE.search(frase_norm):
        return False
    palavras = _so_palavras(frase_norm)
    return any(f in palavras for f in d["_formas"])


def casar_texto(registro: dict, texto: str) -> list[tuple[dict, str]]:
    """Decisões que o texto reabre: [(decisão, trecho normalizado casado)]."""
    preparar(registro)
    norm = cr.normalizar(texto)
    out = []
    for d in registro["decisoes"]:
        for rx in d["_rxs"]:
            m = next((m for m in rx.finditer(norm) if m.end() > m.start()
                      and not _descartar(d, cr._frase(norm, m.start(), m.end()))), None)
            if m:
                out.append((d, m.group(0)))
                break
    return out


def _descartar(d: dict, frase: str) -> bool:
    return (d.get("_ignorar") is not None and bool(d["_ignorar"].search(frase))) or _cumpre(d, frase)


def checar_linhas(registro: dict, linhas: list[tuple[int, str]], arquivo: str,
                  locais: dict[int, str] | None = None) -> list[Acerto]:
    preparar(registro)
    out = []
    for n, texto in linhas:
        norm, idx = cr.normalizar_com_indices(texto)
        for d in registro["decisoes"]:
            for rx in d["_rxs"]:
                m = next((m for m in rx.finditer(norm) if m.end() > m.start()
                          and not _descartar(d, cr._frase(norm, m.start(), m.end()))), None)
                if not m:
                    continue
                ini, fim = idx[m.start()], idx[m.end() - 1] + 1
                trecho = (("…" if ini > 60 else "") + texto[max(0, ini - 60):ini] + "[" + texto[ini:fim] + "]"
                          + texto[fim:fim + 60] + ("…" if fim + 60 < len(texto) else ""))
                out.append(Acerto(arquivo, n, str(d["id"]), d.get("tema", ""), " ".join(trecho.split()), d["decisao"],
                                  d.get("data", ""), d.get("origem", ""), (locais or {}).get(n, f"linha {n}")))
                break  # um acerto por decisão e linha
    return out


def _cadeias_json(dados, caminho: str = "") -> list[tuple[str, str]]:
    """Todas as cadeias de texto de um JSON, com o caminho do campo; pula os campos com o texto vigente."""
    out = []
    if isinstance(dados, dict):
        for k, v in dados.items():
            if str(k) in CAMPOS_VIGENTES:
                continue
            out += _cadeias_json(v, f"{caminho}.{k}" if caminho else str(k))
    elif isinstance(dados, list):
        for i, v in enumerate(dados):
            out += _cadeias_json(v, f"{caminho}[{i}]")
    elif isinstance(dados, str) and dados.strip():
        out.append((caminho or "(raiz)", dados))
    return out


def ler_linhas(path: Path) -> tuple[list[tuple[int, str]], dict[int, str]]:
    if path.suffix.lower() == ".json":
        cadeias = _cadeias_json(json.loads(path.read_text(encoding="utf-8")))
        return [(i, t) for i, (_, t) in enumerate(cadeias, start=1)], {i: c for i, (c, _) in enumerate(cadeias, start=1)}
    return cr.ler_linhas(path)


def checar_arquivos(registro: dict, paths: list[Path]) -> list[Acerto]:
    out = []
    for p in paths:
        linhas, locais = ler_linhas(p)
        out += checar_linhas(registro, linhas, p.name, locais)
    return out


def relatorio(registro: dict, acertos: list[Acerto], paths: list[Path]) -> str:
    linhas = [f"DECISÕES JÁ TOMADAS — {registro.get('caso', '')}".rstrip(" —"),
              f"decisões verificáveis: {len(registro['decisoes'])} | textos: {', '.join(p.name for p in paths)}", ""]
    for a in acertos:
        linhas.append(f"[{a.id}] {a.arquivo}:{a.linha} ({a.local}): {a.trecho}")
        quando = ", ".join(x for x in (a.data, a.origem) if x)
        linhas.append(f"    decisão já tomada — reabrir? {a.tema + ': ' if a.tema else ''}{a.decisao}"
                      + (f" ({quando})" if quando else ""))
    if registro.get("_sem_padrao"):
        linhas += ["", "Sem padrão (não verificável aqui): "
                   + "; ".join(f"{d['id']} {d.get('tema', '')}: {d['decisao']}" for d in registro["_sem_padrao"])]
    linhas += ["", f"Resultado: {len(acertos)} trecho(s) que reabrem decisão já tomada" if acertos
               else "Resultado: nenhuma decisão reaberta"]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--decisoes", type=Path, required=True, help="registro JSON das decisões do caso")
    ap.add_argument("textos", type=Path, nargs="+", help=".md, .txt, .docx ou .json")
    ap.add_argument("--json", type=Path, help="grava os acertos em JSON")
    args = ap.parse_args(argv)
    try:
        registro = carregar(args.decisoes)
        for p in args.textos:
            if not p.exists():
                raise OSError(f"arquivo não encontrado: {p}")
        acertos = checar_arquivos(registro, args.textos)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    print(relatorio(registro, acertos, args.textos))
    if args.json:
        args.json.write_text(json.dumps({"caso": registro.get("caso", ""), "acertos": [asdict(a) for a in acertos]},
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if acertos else 0


if __name__ == "__main__":
    sys.exit(main())
