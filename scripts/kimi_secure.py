#!/usr/bin/env python3
"""Executa o Kimi Code por OAuth ou com a credencial OpenCode Go do Keychain."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Callable, Mapping


SERVICE = "multiagente.kimi-opencode-go"
ACCOUNT = os.environ.get("USER") or Path.home().name
KIMI_BINARY = Path.home() / ".kimi-code" / "bin" / "kimi"
MANAGED_MODEL = "kimi-code/k3"
OPENCODE_MODELS = {
    "opencode-go/kimi-k3": "kimi-k3",
}
MODEL_OVERRIDE_KEYS = (
    "KIMI_MODEL_PROVIDER_TYPE",
    "KIMI_MODEL_BASE_URL",
    "KIMI_MODEL_API_KEY",
    "KIMI_MODEL_NAME",
    "KIMI_MODEL_DISPLAY_NAME",
    "KIMI_MODEL_MAX_CONTEXT_SIZE",
    "KIMI_MODEL_THINKING_EFFORT",
)


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


def requested_model(args: list[str]) -> str:
    """Obtém o alias escolhido sem aceitar modelos implícitos desconhecidos."""
    model = MANAGED_MODEL
    index = 0
    while index < len(args):
        current = args[index]
        if current in {"--model", "-m"} and index + 1 < len(args):
            model = args[index + 1]
            index += 2
            continue
        if current.startswith("--model="):
            model = current.split("=", 1)[1]
        index += 1
    return model


def has_model_argument(args: list[str]) -> bool:
    return any(
        current in {"--model", "-m"} or current.startswith("--model=")
        for current in args
    )


def filtered_args(args: list[str], model: str) -> list[str]:
    """Remove apenas o alias OpenCode, pois o provider efêmero tem precedência."""
    result: list[str] = []
    index = 0
    while index < len(args):
        current = args[index]
        if current in {"--model", "-m"} and index + 1 < len(args):
            if model in OPENCODE_MODELS:
                index += 2
                continue
        if model in OPENCODE_MODELS and current.startswith("--model="):
            index += 1
            continue
        result.append(current)
        index += 1
    return result


def prepare_invocation(
    args: list[str],
    inherited_environment: Mapping[str, str],
    *,
    secret_loader: Callable[[], str] = keychain_secret,
) -> tuple[list[str], dict[str, str]]:
    """Prepara argv/env para OAuth gerenciado ou OpenCode Go sem persistir segredo."""
    model = requested_model(args)
    if model != MANAGED_MODEL and model not in OPENCODE_MODELS:
        raise RuntimeError(f"modelo Kimi não suportado pelo wrapper seguro: {model}")

    environment = dict(inherited_environment)
    for key in MODEL_OVERRIDE_KEYS:
        environment.pop(key, None)

    secret: str | None = None
    if model in OPENCODE_MODELS:
        secret = secret_loader()
    elif model == MANAGED_MODEL:
        try:
            secret = secret_loader()
        except RuntimeError:
            # O OAuth continua operacional mesmo se a opção OpenCode Go não
            # puder ser adicionada ao seletor nesta inicialização.
            secret = None

    if secret:
        environment.update(
            {
                "KIMI_MODEL_PROVIDER_TYPE": "openai",
                "KIMI_MODEL_BASE_URL": "https://opencode.ai/zen/go/v1",
                "KIMI_MODEL_API_KEY": secret,
                "KIMI_MODEL_NAME": OPENCODE_MODELS["opencode-go/kimi-k3"],
                "KIMI_MODEL_DISPLAY_NAME": "Kimi K3 · OpenCode Go",
                "KIMI_MODEL_MAX_CONTEXT_SIZE": "1048576",
                "KIMI_MODEL_THINKING_EFFORT": "max",
            }
        )

    prepared_args = filtered_args(args, model)
    if model == MANAGED_MODEL and not has_model_argument(prepared_args):
        prepared_args = ["--model", MANAGED_MODEL, *prepared_args]
    return prepared_args, environment


def main() -> int:
    if not KIMI_BINARY.is_file():
        raise RuntimeError(f"binário oficial do Kimi Code ausente: {KIMI_BINARY}")
    args, environment = prepare_invocation(sys.argv[1:], os.environ)
    os.execve(str(KIMI_BINARY), [str(KIMI_BINARY), *args], environment)
    return 127


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"kimi-secure: {exc}", file=sys.stderr)
        raise SystemExit(2)
