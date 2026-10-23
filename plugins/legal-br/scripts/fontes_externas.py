#!/usr/bin/env python3
"""
fontes_externas.py — Preflight das fontes web do plugin legal-br:
  - Firecrawl LOCAL (self-hosted, localhost:3002) como ferramenta de busca/scrape
  - Acesso autenticado ao JusBrasil (cookie-first via profile firecrawl +
    fallback Playwright/storageState)

Saida sempre em JSON, para o agente gatear o uso de cada fonte.

Uso:
  python3 fontes_externas.py check
"""
import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path

FIRECRAWL_LOCAL_URL = os.environ.get("FIRECRAWL_API_URL", "http://localhost:3002")
JUSBRASIL_SCRIPT = os.environ.get(
    "JUSBRASIL_SCRIPT",
    str(Path.home() / "Aplicativos/a2a-gemini/scripts/jusbrasil_search.py"),
)
JB_STORAGE_STATE = os.environ.get(
    "JB_STORAGE_STATE", str(Path.home() / ".jusbrasil/storage_state.json")
)


def _http_up(url, timeout=2.5):
    try:
        import requests
        r = requests.get(url, timeout=timeout)
        return True, r.status_code
    except Exception as e:
        return False, str(e)[:120]


def preflight():
    s = {"firecrawl": {}, "jusbrasil": {}, "tooling": {}}

    # Firecrawl local
    up, info = _http_up(FIRECRAWL_LOCAL_URL.rstrip("/") + "/")
    s["firecrawl"]["local_url"] = FIRECRAWL_LOCAL_URL
    s["firecrawl"]["local_up"] = up
    s["firecrawl"]["local_detalhe"] = info
    s["firecrawl"]["cli"] = bool(shutil.which("firecrawl"))
    # fonte de busca geral recomendada
    s["firecrawl"]["usar"] = (
        "firecrawl-local" if (up and s["firecrawl"]["cli"]) else "websearch-nativo"
    )

    # JusBrasil
    storage = Path(os.path.expanduser(JB_STORAGE_STATE))
    s["jusbrasil"]["storage_state"] = str(storage)
    s["jusbrasil"]["sessao_salva"] = storage.exists()
    if storage.exists():
        age_days = (time.time() - storage.stat().st_mtime) / 86400
        s["jusbrasil"]["sessao_idade_dias"] = round(age_days, 1)
    s["jusbrasil"]["script"] = JUSBRASIL_SCRIPT
    s["jusbrasil"]["script_existe"] = os.path.exists(JUSBRASIL_SCRIPT)
    s["jusbrasil"]["pronto"] = (
        s["jusbrasil"]["sessao_salva"] and s["jusbrasil"]["script_existe"]
    )

    # Tooling
    s["tooling"]["uv"] = bool(shutil.which("uv"))

    # Guia de acao
    s["guia"] = []
    if not s["firecrawl"]["local_up"]:
        s["guia"].append(
            "Firecrawl local DOWN — suba com: cd ~/Aplicativos/firecrawl && "
            "docker compose up -d (precisa do Docker rodando). Ate la, use WebSearch nativo."
        )
    if not s["jusbrasil"]["sessao_salva"]:
        s["guia"].append(
            "Sessao JusBrasil ausente — capture 1x: cd ~/Aplicativos/a2a-gemini && "
            "uv run --with playwright python scripts/jusbrasil_setup.py"
        )
    if not s["jusbrasil"]["script_existe"]:
        s["guia"].append(
            f"Script JusBrasil nao encontrado em {JUSBRASIL_SCRIPT} "
            "(defina JUSBRASIL_SCRIPT se moveu)."
        )
    if not s["guia"]:
        s["guia"].append("Fontes web prontas (firecrawl local + JusBrasil).")
    return s


def main():
    p = argparse.ArgumentParser(description="Preflight das fontes web (legal-br)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="Reporta disponibilidade de firecrawl local + JusBrasil")
    args = p.parse_args()
    if args.cmd == "check":
        print(json.dumps(preflight(), ensure_ascii=False, indent=2))
        return 0


if __name__ == "__main__":
    sys.exit(main())
