"""A sincronização das skills não sobrescreve arquivo do pacote alterado localmente."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(tmp_path: Path):
    spec = importlib.util.spec_from_file_location("sync_cli_surface_teste", ROOT / "scripts" / "sync_cli_surface.py")
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    fonte = tmp_path / "pacote" / "skills" / "minha-skill"
    (fonte / "references").mkdir(parents=True)
    (fonte / "SKILL.md").write_text("v1", encoding="utf-8")
    (fonte / "references" / "perfil-orgao.md").write_text("perfil v1", encoding="utf-8")
    (fonte / "references" / "regra.md").write_text("regra v1", encoding="utf-8")
    mod.PLUGIN_SKILL_SOURCE = tmp_path / "pacote" / "skills"
    mod.CENTRAL_SKILL_ROOT = tmp_path / "home" / ".codex" / "skills"
    mod.INSTALL_RECORD = tmp_path / "home" / ".local" / "state" / "registro.json"
    return mod, fonte, mod.CENTRAL_SKILL_ROOT / "minha-skill"


def test_preserva_alteracao_local_e_atualiza_o_resto(tmp_path: Path) -> None:
    mod, fonte, central = load(tmp_path)
    mod.sync_managed_skills(())
    (central / "references" / "regra.md").write_text("regra com nota local", encoding="utf-8")
    (fonte / "references" / "regra.md").write_text("regra v2", encoding="utf-8")
    (fonte / "SKILL.md").write_text("v2", encoding="utf-8")
    preservados: list[str] = []
    mod.sync_managed_skills((), preservados)
    assert (central / "SKILL.md").read_text(encoding="utf-8") == "v2"  # não mexido localmente: atualiza
    assert (central / "references" / "regra.md").read_text(encoding="utf-8") == "regra com nota local"
    assert (central / "references" / "regra.md.distribuido").read_text(encoding="utf-8") == "regra v2"
    assert preservados == ["minha-skill/references/regra.md"]


def test_perfil_personalizado_sem_registro_e_preservado(tmp_path: Path) -> None:
    mod, fonte, central = load(tmp_path)
    (central / "references").mkdir(parents=True)
    (central / "references" / "perfil-orgao.md").write_text("perfil com dados do caso", encoding="utf-8")
    (central / "references" / "regra.md").write_text("regra antiga", encoding="utf-8")
    preservados: list[str] = []
    mod.sync_managed_skills((), preservados)
    assert (central / "references" / "perfil-orgao.md").read_text(encoding="utf-8") == "perfil com dados do caso"
    assert (central / "references" / "regra.md").read_text(encoding="utf-8") == "regra v1"  # sem registro e não personalizável
    assert preservados == ["minha-skill/references/perfil-orgao.md"]
