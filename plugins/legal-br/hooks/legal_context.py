#!/usr/bin/env python3
"""Acrescenta contexto de descoberta; não lê o arquivo nem decide permissões."""
import json
import sys
import unicodedata


def response(event):
    if not isinstance(event, dict) or event.get("tool_name") not in {"Read", "Edit", "Write"}:
        return None
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return None
    filename = tool_input.get("file_path")
    if not isinstance(filename, str):
        return None
    normalized = unicodedata.normalize("NFKD", filename).encode("ascii", "ignore").decode().lower()
    parts = set(normalized.replace("\\", "/").split("/"))
    if not parts.intersection({"contratos", "legal", "juridico", "pareceres", "ndas", "compliance", "regulatorio"}):
        return None
    return {"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "additionalContext": (
            "Este plugin dispõe de skills para pareceres, pesquisa jurídica, revisão de contratos, "
            "NDAs, compliance e risco jurídico. A seleção depende da tarefa atual e das fontes "
            "disponíveis; o diretório do arquivo não inicia pesquisa nem trabalho multiagente."
        ),
    }}


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, TypeError):
        return 0
    result = response(event)
    if result:
        print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
