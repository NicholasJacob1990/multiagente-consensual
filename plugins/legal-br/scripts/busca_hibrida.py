#!/usr/bin/env python3
"""Adaptador — busca servida pelo índice único em ~/.local/share/ssd-index.

Par do `indexar_vetorial.py` adaptado. Mantém a interface que o
`busca_acervo.py` consome: `buscar_vetorial`, `buscar_hibrido_rrf`,
`buscar_lexico`, `FTS_DB`, `PESQUISAR_MATERIAIS_PATH`.

Por que o RRF também precisa ser adaptado, e não só o vetor: o BM25 do plugin é
**por chunk** (`fts(id, content)`, com id casando com o do vetor), enquanto o do
índice único é **por documento**. Trocar só a coleção de vetores faria o RRF
fundir por ids que não se encontram — na prática, RRF nenhum. Então, quando o
índice único assume, ele responde às duas metades.

Implementação anterior preservada em `busca_hibrida_legacy.py`.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import busca_hibrida_legacy as _legacy

for _nome in dir(_legacy):
    if not _nome.startswith("__"):
        globals()[_nome] = getattr(_legacy, _nome)

_SSD_INDEX = Path(os.path.expanduser("~/.local/share/ssd-index"))
_compat = None
_busca = None
if (_SSD_INDEX / "compat.py").exists():
    sys.path.insert(0, str(_SSD_INDEX))
    try:
        import compat as _compat      # noqa: F401
        import search as _busca       # noqa: F401
    except Exception:  # noqa: BLE001
        _compat = _busca = None

# O `busca_acervo.py` checa a existência deste caminho no preflight. Só aponta
# para o banco novo quando ele de fato responde — em modo legacy, reportar o
# banco novo enquanto se consulta o antigo seria informação errada no preflight.
def _fts_db_atual() -> str:
    if _compat is not None and _compat.pronto():
        return str(_SSD_INDEX / "bm25.sqlite")
    return getattr(_legacy, "FTS_DB", "")


FTS_DB = _fts_db_atual()


def _pronto() -> bool:
    return bool(_compat and _busca) and _compat.pronto()


def _formatar(itens, n):
    saida = []
    for r in itens[:n]:
        saida.append({
            "score": r.get("rrf", 0.0),
            "fonte": f"índice único ({'+'.join(r.get('origens', []))})",
            "arquivo": r.get("src", ""),
            "titulo": Path(r.get("src", "")).name,
            "autor": r.get("examinador", "") or r.get("obra", ""),
            "nota_md": r.get("md", ""),
            "trecho": r.get("trecho", ""),
        })
    return saida


def buscar_hibrido_rrf(query, n=5):
    if not _pronto():
        return _legacy.buscar_hibrido_rrf(query, n=n)
    filtros = {"banca": "", "examinador": "", "disciplina": ""}
    fundido = _busca.rrf([_busca.busca_lexica(query, n * 3, filtros),
                          _busca.busca_vetorial(query, n * 3, filtros)])
    return _formatar(fundido, n)


def buscar_vetorial(query, n=5):
    if not _pronto():
        return _legacy.buscar_vetorial(query, n=n)
    filtros = {"banca": "", "examinador": "", "disciplina": ""}
    return _formatar(_busca.busca_vetorial(query, n, filtros), n)


def origem_da_busca() -> str:
    return "ssd-index (único)" if _pronto() else "legacy (plugin)"


if __name__ == "__main__":
    sys.exit(_legacy.main() if hasattr(_legacy, "main") else 0)
