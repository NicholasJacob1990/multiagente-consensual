#!/usr/bin/env python3
"""Migra o segredo OpenCode Go do Kimi para o Keychain e instala o wrapper."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
CONFIG = Path("~/.kimi-code/config.toml").expanduser()
SERVICE = "multiagente.kimi-opencode-go"
ACCOUNT = os.environ.get("USER") or Path.home().name
LIBEXEC = Path("~/.local/libexec/multiagente").expanduser()
BIN_DIR = Path("~/.local/bin").expanduser()
WRAPPER_SOURCE = PLUGIN_ROOT / "scripts" / "kimi_secure.py"
PROVIDER_BLOCK = re.compile(
    r'(?ms)^\[providers\.(?:opencode-go|"opencode-go")\]\s*\n(?P<body>.*?)(?=^\[|\Z)'
)
API_KEY_LINE = re.compile(r"(?m)^(?P<indent>\s*)api_key\s*=\s*(?P<value>\"(?:[^\"\\]|\\.)*\")\s*\n?")
ZSH_MARKER_START = "# >>> multiagente kimi-secure >>>"
ZSH_MARKER_END = "# <<< multiagente kimi-secure <<<"


def atomic_write(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    tmp.chmod(mode)
    os.replace(tmp, path)


def extract_secret(text: str) -> tuple[str | None, str]:
    block = PROVIDER_BLOCK.search(text)
    if not block:
        raise RuntimeError("provider [providers.opencode-go] não encontrado no config.toml")
    key = API_KEY_LINE.search(block.group("body"))
    if not key:
        return None, text
    try:
        secret = json.loads(key.group("value"))
    except json.JSONDecodeError as exc:
        raise RuntimeError("api_key do provider usa formato TOML não suportado") from exc
    if not isinstance(secret, str) or not secret:
        raise RuntimeError("api_key vazia no provider opencode-go")
    start = block.start("body") + key.start()
    end = block.start("body") + key.end()
    return secret, text[:start] + text[end:]


def keychain_put(secret: str) -> None:
    # Com -w por último, `security` lê e confirma a senha de stdin. O segredo
    # não aparece em argv, stdout, logs nem em arquivo temporário.
    completed = subprocess.run(
        [
            "/usr/bin/security",
            "add-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVICE,
            "-U",
            "-w",
        ],
        input=f"{secret}\n{secret}\n",
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError("não foi possível gravar a credencial no Keychain")
    verify = subprocess.run(
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
    if verify.returncode != 0 or verify.stdout.rstrip("\n") != secret:
        raise RuntimeError("a verificação da credencial no Keychain falhou")


def keychain_exists() -> bool:
    completed = subprocess.run(
        [
            "/usr/bin/security",
            "find-generic-password",
            "-a",
            ACCOUNT,
            "-s",
            SERVICE,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def install_wrapper() -> Path:
    LIBEXEC.mkdir(parents=True, exist_ok=True)
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    target_script = LIBEXEC / "kimi_secure.py"
    atomic_write(target_script, WRAPPER_SOURCE.read_bytes(), 0o700)
    wrapper = BIN_DIR / "kimi-secure"
    content = f"#!/bin/sh\nexec /usr/bin/python3 \"{target_script}\" \"$@\"\n"
    atomic_write(wrapper, content.encode("utf-8"), 0o755)
    return wrapper


def install_zsh_alias(wrapper: Path) -> None:
    zshrc = Path("~/.zshrc").expanduser()
    existing = zshrc.read_text(encoding="utf-8") if zshrc.exists() else ""
    block = (
        f"{ZSH_MARKER_START}\n"
        f"alias kimi='{wrapper}'\n"
        f"alias kimi-original='{Path.home() / '.kimi-code/bin/kimi'}'\n"
        f"{ZSH_MARKER_END}"
    )
    pattern = re.compile(
        re.escape(ZSH_MARKER_START) + r".*?" + re.escape(ZSH_MARKER_END),
        re.DOTALL,
    )
    updated = pattern.sub(block, existing) if pattern.search(existing) else existing.rstrip() + "\n\n" + block + "\n"
    atomic_write(zshrc, updated.encode("utf-8"), 0o600)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--no-shell-alias", action="store_true")
    args = parser.parse_args()

    if not CONFIG.is_file():
        raise RuntimeError(f"configuração do Kimi ausente: {CONFIG}")
    original = CONFIG.read_text(encoding="utf-8")
    secret, sanitized = extract_secret(original)
    if secret is not None:
        keychain_put(secret)
        atomic_write(CONFIG, sanitized.encode("utf-8"), 0o600)
    elif not keychain_exists():
        raise RuntimeError("api_key não está no config.toml nem no Keychain")

    wrapper = install_wrapper()
    if not args.no_shell_alias:
        install_zsh_alias(wrapper)
    print(f"wrapper={wrapper}")
    print(f"config_sanitized={CONFIG}")
    print(f"keychain_service={SERVICE}")
    print("secret_exposed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
