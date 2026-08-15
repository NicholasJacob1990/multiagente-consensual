#!/usr/bin/env python3
"""Sincroniza a superfície pública de comandos e skills entre CLIs locais.

O script é aditivo: atualiza somente os 29 nomes públicos deste plugin, não
remove comandos extras do usuário e preserva skills preexistentes que já
declarem o mesmo ``name`` no frontmatter.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
from pathlib import Path


PLUGIN_ROOT = Path(__file__).resolve().parents[1]
COMMAND_SOURCE = PLUGIN_ROOT / "commands"
PLUGIN_SKILL_SOURCE = PLUGIN_ROOT / "skills"
HOME = Path.home()

COMMAND_TARGETS = {
    "codex": HOME / ".codex" / "prompts",
    "claude": HOME / ".claude" / "commands",
    "cursor": HOME / ".cursor" / "commands",
    "opencode": HOME / ".config" / "opencode" / "commands",
    "gemini": HOME / ".gemini" / "commands",
    # Legado opcional. A rota canônica de Grok permanece Cursor CLI.
    "grok-legacy": HOME / ".grok" / "commands",
}

CENTRAL_SKILL_ROOT = HOME / ".codex" / "skills"
HOST_POLICY_ROOT = HOME / ".agents"
CENTRAL_RUNTIME_ROOT = HOME / ".codex"
SHARED_SKILL_ROOTS = (
    HOME / ".agents" / "skills",  # Kimi Code e Antigravity/Gemini
    HOME / ".claude" / "skills",
    HOME / ".cursor" / "skills",
    HOME / ".config" / "opencode" / "skills",
)

# Nomes aceitos pelo instalador NPM. Antigravity reutiliza a superfície de
# comandos do Gemini e, junto com Kimi Code, descobre skills em ~/.agents.
TARGET_COMMAND_KEYS = {
    "codex": ("codex",),
    "claude": ("claude",),
    "cursor": ("cursor",),
    "opencode": ("opencode",),
    "kimi": (),
    "antigravity": ("gemini",),
    "gemini": ("gemini",),
    "grok-legacy": ("grok-legacy",),
}

TARGET_SKILL_ROOTS = {
    "codex": (),
    "claude": (HOME / ".claude" / "skills",),
    "cursor": (HOME / ".cursor" / "skills",),
    "opencode": (HOME / ".config" / "opencode" / "skills",),
    "kimi": (HOME / ".agents" / "skills",),
    "antigravity": (HOME / ".agents" / "skills",),
    "gemini": (HOME / ".agents" / "skills",),
    "grok-legacy": (HOME / ".agents" / "skills",),
}

CORE_COMMANDS = {
    "consenso": (
        "Buscar consenso verificável sobre uma versão ou decisão congelada",
        "Use integralmente a skill `consenso` para interpretar o pedido atual. "
        "Preserve dissensos e não declare aprovação sem `veredito_consenso_v1`.",
    ),
    "loop-debate-agentes": (
        "Criar e melhorar artefatos por crítica, réplica, revisão e novos gates",
        "Use integralmente a skill `loop-debate-agentes` para o pedido atual. "
        "Congele versões e hashes, preserve autoria e exija os gates configurados.",
    ),
    "redacao-juridica-consensual": (
        "Produzir pareceres e minutas com loop, consenso e gates jurídicos",
        "Use integralmente a skill `redacao-juridica-consensual` para o pedido atual. "
        "Ela aplica o perfil jurídico sobre o motor `loop-debate-agentes`.",
    ),
    "workflow-agentes": (
        "Selecionar e executar protocolos formais de coordenação multiagente",
        "Use integralmente a skill `workflow-agentes` para o pedido atual. "
        "Resolva o protocolo, os participantes, os limites e os gates antes de executar.",
    ),
}

FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
NAME_FIELD = re.compile(r"(?m)^name:\s*[\"']?([^\"'\n]+)")
DESCRIPTION_FIELD = re.compile(r"(?m)^description:\s*(.+)$")


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def command_sources() -> dict[str, str]:
    sources = {
        path.stem: path.read_text(encoding="utf-8")
        for path in sorted(COMMAND_SOURCE.glob("*.md"))
    }
    for name, (description, instruction) in CORE_COMMANDS.items():
        sources[name] = (
            "---\n"
            f"description: {description}\n"
            f"argument-hint: \"[pedido em linguagem natural]\"\n"
            f"entrypoint: {name}\n"
            "---\n\n"
            f"{instruction}\n\n"
            "$ARGUMENTS\n"
        )
    if len(sources) != 29:
        raise RuntimeError(f"superfície pública inválida: esperados 29 nomes, obtidos {len(sources)}")
    return dict(sorted(sources.items()))


def parse_description(text: str, fallback: str) -> str:
    match = FRONTMATTER.match(text)
    if not match:
        return fallback
    field = DESCRIPTION_FIELD.search(match.group(1))
    if not field:
        return fallback
    return field.group(1).strip().strip('"\'')


def declared_skill_names() -> set[str]:
    names: set[str] = set()
    for root in (CENTRAL_SKILL_ROOT, *SHARED_SKILL_ROOTS):
        if not root.exists():
            continue
        for skill_file in root.glob("*/SKILL.md"):
            try:
                head = skill_file.read_text(encoding="utf-8")[:4096]
            except OSError:
                continue
            match = NAME_FIELD.search(head)
            if match:
                names.add(match.group(1).strip())
    return names


def portable_skill(name: str, command_text: str) -> str:
    description = parse_description(
        command_text,
        f"Executar a entrada multiagente portátil correspondente a /{name}",
    )
    body_match = FRONTMATTER.match(command_text)
    body = command_text[body_match.end():] if body_match else command_text
    body = body.replace("$ARGUMENTS", "o pedido atual do usuário")
    body = re.sub(r"(?m)^o pedido atual do usuário\s*$\n?", "", body)
    return (
        "---\n"
        f"name: {name}\n"
        f"description: \"{description.replace(chr(34), chr(39))}. "
        f"Use quando o usuário mencionar /{name}, ${name}, "
        f"/skill:{name} ou pedir esse protocolo em linguagem natural.\"\n"
        "---\n\n"
        f"# {name}\n\n"
        f"Esta é a entrada portátil equivalente a `/{name}`. No Kimi Code, a "
        f"invocação explícita é `/skill:{name}`; nos demais hosts, aceite o slash "
        "command ou a linguagem natural.\n\n"
        f"{body.strip()}\n"
    )


def link_shared_skill(name: str, central_dir: Path, roots: tuple[Path, ...]) -> None:
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
        target = root / name
        if target.exists() or target.is_symlink():
            continue
        target.symlink_to(central_dir, target_is_directory=True)


def sync_managed_skills(shared_roots: tuple[Path, ...]) -> list[str]:
    """Atualiza somente as skills que pertencem a este plugin.

    Arquivos estranhos já existentes no diretório de destino são preservados;
    caches e metadados locais nunca são copiados. Assim, a sincronização é
    aditiva em relação às extensões do usuário e autoritativa apenas para os
    cinco diretórios versionados pelo pacote.
    """
    synced: list[str] = []
    for source_dir in sorted(PLUGIN_SKILL_SOURCE.iterdir()):
        if not source_dir.is_dir() or not (source_dir / "SKILL.md").is_file():
            continue
        central_dir = CENTRAL_SKILL_ROOT / source_dir.name
        if central_dir.is_symlink():
            raise RuntimeError(f"destino central não pode ser symlink: {central_dir}")
        for source in sorted(source_dir.rglob("*")):
            relative = source.relative_to(source_dir)
            if any(part in {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"} for part in relative.parts):
                continue
            if not source.is_file() or source.suffix == ".pyc" or source.name == ".DS_Store":
                continue
            target = central_dir / relative
            atomic_write(target, source.read_bytes())
            target.chmod(source.stat().st_mode & 0o777)
        link_shared_skill(source_dir.name, central_dir, shared_roots)
        synced.append(source_dir.name)
    return synced


def sync_shared_runtime() -> list[Path]:
    """Instala a política canônica e o módulo comum esperado pelas skills copiadas.

    Dentro do plugin, ``parents[3]`` resolve a raiz do pacote. Na superfície
    compartilhada, ele resolve ``~/.codex``; por isso essa raiz recebe apenas
    os dois arquivos comuns explicitamente gerenciados pelo plugin.
    """
    # O manifesto tem dois destinos: a fonte de política do host e o fallback
    # relativo usado quando uma skill é descoberta em ``~/.codex/skills``.
    pairs = [
        (PLUGIN_ROOT / "assets" / "multiagent-manifest.json", HOST_POLICY_ROOT / "multiagent-manifest.json"),
        (PLUGIN_ROOT / "assets" / "model-routing.yaml", HOST_POLICY_ROOT / "model-routing.yaml"),
        (PLUGIN_ROOT / "assets" / "multiagent-manifest.json", CENTRAL_RUNTIME_ROOT / "assets" / "multiagent-manifest.json"),
        (PLUGIN_ROOT / "scripts" / "provenance.py", CENTRAL_RUNTIME_ROOT / "scripts" / "provenance.py"),
    ]
    installed: list[Path] = []
    for source, target in pairs:
        atomic_write(target, source.read_bytes())
        target.chmod(source.stat().st_mode & 0o777)
        installed.append(target)
    return installed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--commands-only",
        action="store_true",
        help="sincronizar slash commands sem criar aliases como skills",
    )
    parser.add_argument(
        "--portable-names",
        default="",
        help="lista CSV de aliases a criar/atualizar como skills portáteis",
    )
    parser.add_argument(
        "--targets",
        default="all",
        help=(
            "lista CSV de superfícies: codex, claude, cursor, opencode, kimi, "
            "antigravity, gemini ou grok-legacy; o padrão é all"
        ),
    )
    args = parser.parse_args()

    requested = {item.strip() for item in args.targets.split(",") if item.strip()}
    if not requested or requested == {"all"}:
        requested = set(TARGET_COMMAND_KEYS)
    elif "all" in requested:
        raise RuntimeError("all não pode ser combinado com alvos específicos")
    unknown_targets = requested - set(TARGET_COMMAND_KEYS)
    if unknown_targets:
        raise RuntimeError("superfícies desconhecidas: " + ", ".join(sorted(unknown_targets)))

    command_keys = {
        key for target in requested for key in TARGET_COMMAND_KEYS[target]
    }
    shared_skill_roots = tuple(
        sorted(
            {root for target in requested for root in TARGET_SKILL_ROOTS[target]},
            key=str,
        )
    )

    sources = command_sources()
    for key in sorted(command_keys):
        target = COMMAND_TARGETS[key]
        target.mkdir(parents=True, exist_ok=True)
        for name, text in sources.items():
            atomic_write(target / f"{name}.md", text.encode("utf-8"))

    synced_skills = sync_managed_skills(shared_skill_roots)
    shared_runtime = sync_shared_runtime()

    created_skills: list[str] = []
    if not args.commands_only:
        existing = declared_skill_names()
        selected = {item.strip() for item in args.portable_names.split(",") if item.strip()}
        unknown = selected - set(sources)
        if unknown:
            raise RuntimeError("aliases desconhecidos: " + ", ".join(sorted(unknown)))
        CENTRAL_SKILL_ROOT.mkdir(parents=True, exist_ok=True)
        for name, text in sources.items():
            if selected and name not in selected:
                continue
            if not selected and name in existing:
                # Skills can live under a differently named directory (for
                # example agent-council declara name: council).
                continue
            central_dir = CENTRAL_SKILL_ROOT / name
            central_dir.mkdir(parents=True, exist_ok=True)
            atomic_write(
                central_dir / "SKILL.md",
                portable_skill(name, text).encode("utf-8"),
            )
            link_shared_skill(name, central_dir, shared_skill_roots)
            created_skills.append(name)

    print(f"commands={len(sources)} targets={len(command_keys)}")
    print("requested_targets=" + ",".join(sorted(requested)))
    print(f"managed_skills_synced={len(synced_skills)}")
    print(f"shared_runtime_files={len(shared_runtime)}")
    print(f"portable_skills_created={len(created_skills)}")
    if created_skills:
        print("skills=" + ",".join(created_skills))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
