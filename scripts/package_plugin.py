#!/usr/bin/env python3
"""Gera um pacote hospedável e reproduzível (ZIP/.plugin) para o Cowork."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDED_ROOTS = {
    ".claude-plugin",
    ".codex-plugin",
    "assets",
    "commands",
    "references",
    "scripts",
    "skills",
}
# Executáveis auxiliares locais podem permanecer no repositório, mas plugins
# hospedados em claude.ai não podem publicar um diretório bin/ de nível superior.
LOCAL_ONLY_ROOTS = {"bin", "npm"}
LOCAL_ONLY_ROOT_FILES = {".npmignore", "package.json", "package-lock.json"}
HOSTED_EXCLUDED_PATHS = {Path(".claude-plugin/marketplace.json")}
INCLUDED_ROOT_FILES = {"README.md"}
EXCLUDED_NAMES = {
    "__pycache__", ".DS_Store", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".cache"
}
SENSITIVE_NAMES = {
    ".env",
    "credentials.json",
    "secrets.json",
    "cowork-bridge-config.json",
    "multiagent-bridge-config.json",
    "id_rsa",
    "id_ed25519",
}
SENSITIVE_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}


def included(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    if any(part in SENSITIVE_NAMES or part.startswith(".env.") for part in relative.parts) \
            or relative.suffix.lower() in SENSITIVE_SUFFIXES:
        raise RuntimeError(f"arquivo sensível proibido no pacote: {relative}")
    if relative.name in EXCLUDED_NAMES or relative.suffix == ".pyc":
        return False
    # marketplace.json descreve um repositório de distribuição. Em upload
    # direto, sua presença faz o Claude classificar o ZIP como marketplace em
    # vez de carregar plugin.json e descobrir as skills do pacote.
    if relative in HOSTED_EXCLUDED_PATHS:
        return False
    if len(relative.parts) == 1:
        return relative.name in INCLUDED_ROOT_FILES
    return relative.parts[0] in INCLUDED_ROOTS and not any(
        part in EXCLUDED_NAMES for part in relative.parts
    )


def assert_safe_tree() -> None:
    ignored = {"dist", "reviews", "tests"}
    unexpected = []
    for item in ROOT.iterdir():
        if (
            item.name in INCLUDED_ROOTS
            or item.name in INCLUDED_ROOT_FILES
            or item.name in LOCAL_ONLY_ROOT_FILES
            or item.name in LOCAL_ONLY_ROOTS
            or item.name in ignored
            or item.name in EXCLUDED_NAMES
        ):
            continue
        unexpected.append(item.name)
    if unexpected:
        raise RuntimeError("itens inesperados na raiz do plugin: " + ", ".join(sorted(unexpected)))


def package_version() -> str:
    claude = json.loads((ROOT / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
    codex = json.loads((ROOT / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "assets/multiagent-manifest.json").read_text(encoding="utf-8"))
    versions = {claude.get("version"), codex.get("version"), manifest.get("plugin_version")}
    if len(versions) != 1 or None in versions:
        raise RuntimeError("versões divergentes entre plugin Claude, plugin Codex e manifesto")
    return str(versions.pop())


def package_entries() -> list[tuple[str, bytes, int]]:
    entries: list[tuple[str, bytes, int]] = []
    for source in sorted(ROOT.rglob("*")):
        if source.is_symlink():
            raise RuntimeError(f"symlink proibido no pacote: {source.relative_to(ROOT)}")
        if not source.is_file() or not included(source):
            continue
        mode = 0o755 if os.access(source, os.X_OK) else 0o644
        entries.append((str(source.relative_to(ROOT)), source.read_bytes(), mode))
    content_manifest = {
        "schema": "multiagent_package_manifest_v1",
        "plugin_version": package_version(),
        "files": [
            {
                "path": name,
                "sha256": hashlib.sha256(content).hexdigest(),
                "bytes": len(content),
                "mode": oct(mode),
            }
            for name, content, mode in entries
        ],
    }
    encoded = (
        json.dumps(content_manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    entries.append(("PACKAGE-MANIFEST.json", encoded, 0o644))
    return entries


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(ROOT / "dist" / f"{ROOT.name}.plugin"))
    args = parser.parse_args()
    output = Path(args.output).expanduser().resolve()
    assert_safe_tree()
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_name(f".{output.name}.tmp")
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content, mode in package_entries():
            info = zipfile.ZipInfo(name)
            info.date_time = (2026, 1, 1, 0, 0, 0)
            info.create_system = 3
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, content)
    os.replace(tmp, output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
