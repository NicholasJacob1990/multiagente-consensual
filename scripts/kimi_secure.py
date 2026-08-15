#!/usr/bin/env python3
"""Executa o Kimi Code com a credencial OpenCode Go lida do Keychain."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


SERVICE = "multiagente.kimi-opencode-go"
ACCOUNT = os.environ.get("USER") or Path.home().name
KIMI_BINARY = Path.home() / ".kimi-code" / "bin" / "kimi"


def keychain_secret() -> str:
    completed = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVICE,
            "-w",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    secret = completed.stdout.rstrip("\n")
    if completed.returncode != 0 or not secret:
        raise RuntimeError(
            "credencial Kimi/OpenCode Go ausente no Keychain; execute "
            "scripts/install_kimi_keychain.py"
        )
    return secret


def filtered_args(args: list[str]) -> list[str]:
    """Deixa o provider temporário do ambiente resolver o alias canônico."""
    result: list[str] = []
    index = 0
    while index < len(args):
        current = args[index]
        if current in {"--model", "-m"} and index + 1 < len(args):
            if args[index + 1] == "kimi-code/k3":
                index += 2
                continue
        if current == "--model=kimi-code/k3":
            index += 1
            continue
        result.append(current)
        index += 1
    return result


def main() -> int:
    if not KIMI_BINARY.is_file():
        raise RuntimeError(f"binário oficial do Kimi Code ausente: {KIMI_BINARY}")
    environment = os.environ.copy()
    environment.update(
        {
            "KIMI_MODEL_PROVIDER_TYPE": "openai",
            "KIMI_MODEL_BASE_URL": "https://opencode.ai/zen/go/v1",
            "KIMI_MODEL_API_KEY": keychain_secret(),
            "KIMI_MODEL_NAME": "kimi-k3",
        }
    )
    os.execve(str(KIMI_BINARY), [str(KIMI_BINARY), *filtered_args(sys.argv[1:])], environment)
    return 127


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"kimi-secure: {exc}", file=sys.stderr)
        raise SystemExit(2)
