from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from docx import Document


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "redacao-juridica-consensual" / "scripts" / "word_redline.py"


def load_module():
    spec = importlib.util.spec_from_file_location("word_redline", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_docx(path: Path, paragraphs: list[str]) -> None:
    doc = Document()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)


def test_clean_docx_fingerprint_changes_only_with_visible_text(tmp_path: Path) -> None:
    module = load_module()
    first = tmp_path / "first.docx"
    same = tmp_path / "same.docx"
    changed = tmp_path / "changed.docx"
    make_docx(first, ["RELATÓRIO", "Pedido parcialmente procedente."])
    make_docx(same, ["RELATÓRIO", "Pedido parcialmente procedente."])
    make_docx(changed, ["RELATÓRIO", "Pedido totalmente procedente."])

    assert module.story_sha256(first) == module.story_sha256(same)
    assert module.story_sha256(first) != module.story_sha256(changed)
    assert module.count_revisions(first) == 0


def test_output_names_follow_contract() -> None:
    module = load_module()
    names = module.final_output_names("minuta")
    assert names.clean == "minuta-final-limpa.docx"
    assert names.cumulative == "minuta-final-com-alteracoes.docx"
    assert names.incremental == "minuta-final-alteracoes-ultima-versao.docx"
    assert names.manifest == "manifesto-controle-alteracoes.json"
    assert names.report == "relatorio-de-alteracoes.md"


def test_compare_refuses_input_with_existing_revisions(tmp_path: Path) -> None:
    module = load_module()
    base = tmp_path / "base.docx"
    current = tmp_path / "current.docx"
    make_docx(base, ["Texto-base"])
    make_docx(current, ["Texto atual"])

    module.inject_revision_marker_for_test(base)
    with pytest.raises(module.RedlineError, match="alterações controladas"):
        module.validate_clean_input(base, "base")


@pytest.mark.skipif(
    os.environ.get("RUN_WORD_REDLINE_INTEGRATION") != "1"
    or not (Path.home() / ".agents/tools/python-redlines-0.3.0/bin/python").is_file(),
    reason="integração com o comparador local Docxodus é opt-in",
)
def test_native_docx_compare_accepts_to_current_and_rejects_to_base(tmp_path: Path) -> None:
    base = tmp_path / "minuta-v1.docx"
    current = tmp_path / "minuta-v2.docx"
    out = tmp_path / "minuta-v2-alteracoes.docx"
    manifest = tmp_path / "manifest.json"
    make_docx(
        base,
        [
            "RELATÓRIO",
            "Há indício documental relevante, mas é necessário confirmar a tempestividade.",
            "Julgo improcedente o pedido.",
        ],
    )
    make_docx(
        current,
        [
            "RELATÓRIO",
            "A prova documental confirma o vício e a tempestividade.",
            "A tese contrária foi examinada, mas não supera a prova documental.",
            "Julgo procedente o pedido.",
            "Publique-se.",
        ],
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "compare",
            "--base",
            str(base),
            "--current",
            str(current),
            "--out",
            str(out),
            "--manifest",
            str(manifest),
            "--author",
            "Redator de teste",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert completed.returncode == 0, completed.stderr
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    assert payload["contract"] == "legal_word_redline_v1"
    assert payload["verification"]["accept_all_matches_current"] is True
    assert payload["verification"]["reject_all_matches_base"] is True
    assert payload["redline"]["revision_count"] > 0
