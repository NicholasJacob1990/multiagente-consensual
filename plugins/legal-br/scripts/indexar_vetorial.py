#!/usr/bin/env python3
"""Adaptador — encaminha para o índice único em ~/.local/share/ssd-index.

Antes havia TRÊS pilhas de indexação sobre o mesmo acervo: esta (do plugin), a de
`~/.local/share/acervo-ingest` e o `ssd-index`. As duas primeiras usavam o mesmo
chunking, com `MAX_CHUNKS = 50`, que **descarta 83,2% do corpus** — medido em
12/08/2026: 12.169 dos 31.367 arquivos passam de 40.000 chars e entram cortados.

Este arquivo preserva toda a interface anterior. A implementação original está em
`indexar_vetorial_legacy.py` e continua sendo usada **enquanto o índice único não
cobrir corpus equivalente** (ver `compat.pronto()`). A troca é automática: não há
janela em que a busca fique pior do que era.

Para reindexar, use o pipeline único:  ~/.local/share/ssd-index/run.sh
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ── tudo da implementação original continua exportado ──────────────────────
import indexar_vetorial_legacy as _legacy

for _nome in dir(_legacy):
    if not _nome.startswith("__"):
        globals()[_nome] = getattr(_legacy, _nome)

# ── camada de compatibilidade do índice único ──────────────────────────────
_SSD_INDEX = Path(os.path.expanduser("~/.local/share/ssd-index"))
_compat = None
if (_SSD_INDEX / "compat.py").exists():
    sys.path.insert(0, str(_SSD_INDEX))
    try:
        import compat as _compat  # noqa: F401
    except Exception:  # noqa: BLE001
        _compat = None


def _usar_indice_unico() -> bool:
    return bool(_compat) and _compat.pronto()


# O preflight do busca_acervo.py lê CHROMA_DIR/ACERVO_RAW DIRETO do módulo (não via
# get_collection). O legado aponta para o Chroma apagado em 16/08/2026 → preflight
# marcava vetorial indisponível e a busca voltava 0. Repontar para o ssd-index quando
# o índice único responde faz o preflight refletir a realidade.
if _usar_indice_unico():
    # O que interessa ao preflight e onde a BUSCA vai bater, que passa a ser
    # `chroma_fatias` quando o manifesto diz que as fatias estao completas.
    # `_compat.get_collection()` continua no monolito (caminho de indexacao).
    CHROMA_DIR = (_compat.indice_de_consulta()
                  if hasattr(_compat, "indice_de_consulta") else _compat.CHROMA_DIR)
    globals()["ACERVO_RAW"] = Path.home() / ".local/share/ssd-index/md"


def get_collection():
    """Coleção do índice único quando ele tiver cobertura; senão, a antiga."""
    if _usar_indice_unico():
        return _compat.get_collection()
    return _legacy.get_collection()


def embed_one(text: str):
    if _usar_indice_unico():
        return _compat.embed_one(text)
    return _legacy.embed_one(text)


def origem_do_indice() -> str:
    return "ssd-index (único)" if _usar_indice_unico() else "legacy (plugin)"


def main():
    # `index` não deve mais construir o índice antigo quando o único já assumiu:
    # seriam duas vetorizações do mesmo material, e a antiga com o chunking ruim.
    if len(sys.argv) > 1 and sys.argv[1] == "index" and _usar_indice_unico():
        print("O índice é mantido por ~/.local/share/ssd-index.")
        print("Para atualizar:  ~/.local/share/ssd-index/run.sh")
        print(f"Estado: {_compat.status()}")
        return 0
    return _legacy.main()


if __name__ == "__main__":
    sys.exit(main() or 0)
