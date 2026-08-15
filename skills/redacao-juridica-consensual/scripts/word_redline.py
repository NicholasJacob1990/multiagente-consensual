#!/usr/bin/env python3
"""Gera comparações DOCX com alterações controladas nativas.

O artefato limpo continua canônico. O redline é um derivado auditável que
registra a relação entre uma versão-base e a versão limpa corrente. O comparador
local Docxodus grava marcações OOXML ``w:ins``/``w:del`` reconhecidas pelo Word.
O script também valida, resolvendo as marcações de forma determinística, que
aceitar tudo reproduz o texto corrente e rejeitar tudo reproduz o texto-base.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import fcntl
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
WORD_APP = Path("/Applications/Microsoft Word.app")
REDLINES_PYTHON = Path.home() / ".agents" / "tools" / "python-redlines-0.3.0" / "bin" / "python"
DOCX_PARTS = (
    "word/document.xml",
    "word/footnotes.xml",
    "word/endnotes.xml",
)
REVISION_NAMES = {
    "ins",
    "del",
    "moveFrom",
    "moveTo",
    "moveFromRangeStart",
    "moveFromRangeEnd",
    "moveToRangeStart",
    "moveToRangeEnd",
}


class RedlineError(RuntimeError):
    """Erro de contrato ou de geração do redline."""


@dataclasses.dataclass(frozen=True)
class FinalOutputNames:
    clean: str
    cumulative: str
    incremental: str
    manifest: str
    report: str


def final_output_names(stem: str) -> FinalOutputNames:
    safe = stem.strip().removesuffix(".docx")
    if not safe or safe in {".", ".."} or "/" in safe or "\\" in safe:
        raise RedlineError("stem deve ser um nome de arquivo simples")
    return FinalOutputNames(
        clean=f"{safe}-final-limpa.docx",
        cumulative=f"{safe}-final-com-alteracoes.docx",
        incremental=f"{safe}-final-alteracoes-ultima-versao.docx",
        manifest="manifesto-controle-alteracoes.json",
        report="relatorio-de-alteracoes.md",
    )


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _story_parts(names: list[str]) -> list[str]:
    result = [part for part in DOCX_PARTS if part in names]
    result.extend(sorted(name for name in names if name.startswith("word/header") and name.endswith(".xml")))
    result.extend(sorted(name for name in names if name.startswith("word/footer") and name.endswith(".xml")))
    return result


def story_payload(path: Path | str) -> str:
    """Extrai texto visível e fronteiras de parágrafo das histórias principais."""

    docx = Path(path)
    ensure_docx_valid(docx)
    records: list[str] = []
    with zipfile.ZipFile(docx) as archive:
        for part in _story_parts(archive.namelist()):
            root = ET.fromstring(archive.read(part))
            part_records: list[str] = []
            for paragraph in root.iter(f"{{{W_NS}}}p"):
                pieces: list[str] = []
                for node in paragraph.iter():
                    name = _local_name(node.tag)
                    if name in {"t", "delText", "instrText", "delInstrText"}:
                        pieces.append(node.text or "")
                    elif name == "tab":
                        pieces.append("\t")
                    elif name in {"br", "cr"}:
                        pieces.append("\n")
                    elif name == "noBreakHyphen":
                        pieces.append("‑")
                    elif name == "softHyphen":
                        pieces.append("\u00ad")
                part_records.append("P\t" + "".join(pieces))
            # Comparadores podem acrescentar partes vazias de notas. Elas não
            # alteram o conteúdo visível e não devem invalidar a equivalência.
            if part == "word/document.xml" or part_records:
                records.append(f"PART\t{part}")
                records.extend(part_records)
    return "\n".join(records)


def story_sha256(path: Path | str) -> str:
    return hashlib.sha256(story_payload(path).encode("utf-8")).hexdigest()


def ensure_docx_valid(path: Path | str) -> None:
    docx = Path(path)
    if docx.suffix.lower() != ".docx":
        raise RedlineError(f"arquivo deve terminar em .docx: {docx}")
    if not docx.is_file():
        raise RedlineError(f"arquivo DOCX não encontrado: {docx}")
    try:
        with zipfile.ZipFile(docx) as archive:
            if "word/document.xml" not in archive.namelist():
                raise RedlineError(f"pacote sem word/document.xml: {docx}")
            broken = archive.testzip()
            if broken is not None:
                raise RedlineError(f"entrada corrompida no DOCX {docx}: {broken}")
    except zipfile.BadZipFile as exc:
        raise RedlineError(f"DOCX inválido: {docx}") from exc


def count_revisions(path: Path | str) -> int:
    docx = Path(path)
    ensure_docx_valid(docx)
    total = 0
    with zipfile.ZipFile(docx) as archive:
        for part in _story_parts(archive.namelist()):
            root = ET.fromstring(archive.read(part))
            for element in root.iter():
                name = _local_name(element.tag)
                if name in REVISION_NAMES or name.endswith("PrChange"):
                    total += 1
    return total


def validate_clean_input(path: Path | str, role: str) -> Path:
    docx = Path(path).expanduser().resolve()
    ensure_docx_valid(docx)
    revisions = count_revisions(docx)
    if revisions:
        raise RedlineError(
            f"{role} já contém {revisions} alterações controladas; "
            "aceite ou rejeite essas revisões antes de iniciar nova comparação"
        )
    return docx


def _doctor_payload(deep: bool = False) -> dict[str, object]:
    osascript = shutil.which("osascript")
    redlines_available = REDLINES_PYTHON.is_file()
    payload: dict[str, object] = {
        "contract": "legal_word_redline_v1",
        "platform": sys.platform,
        "word_app": str(WORD_APP),
        "word_installed": WORD_APP.exists(),
        "osascript": osascript,
        "redlines_python": str(REDLINES_PYTHON),
        "redlines_available": redlines_available,
        "available": redlines_available,
        "engine": "docxodus_wmlcomparer",
        "output": "native_ooxml_tracked_changes",
    }
    if deep and sys.platform == "darwin" and WORD_APP.exists() and bool(osascript):
        result = _run_osascript(
            'tell application "Microsoft Word" to return version',
            [],
            timeout=30,
        )
        payload["word_version"] = result.strip()
    return payload


def _require_redline_engine() -> None:
    payload = _doctor_payload()
    if not payload["available"]:
        raise RedlineError(
            "controle de alterações exige o runtime local python-redlines/Docxodus; "
            f"diagnóstico: {json.dumps(payload, ensure_ascii=False)}"
        )


def _run_osascript(script: str, args: list[str], timeout: int = 180) -> str:
    osascript = shutil.which("osascript")
    if osascript is None:
        raise RedlineError("osascript não encontrado")
    completed = subprocess.run(
        [osascript, "-e", script, *args],
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        if "not authorized" in detail.lower() or "not permitted" in detail.lower():
            detail += " — autorize o terminal/CLI em Ajustes do Sistema > Privacidade e Segurança > Automação"
        raise RedlineError(f"Microsoft Word não concluiu a operação: {detail}")
    return completed.stdout.strip()


@contextlib.contextmanager
def word_lock(timeout: float = 180.0) -> Iterator[None]:
    lock_dir = Path.home() / ".agents" / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / "word-redline.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RedlineError("tempo esgotado aguardando o Microsoft Word")
                time.sleep(0.25)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _native_compare(base: Path, current: Path, output: Path, author: str, detect_format_changes: bool) -> None:
    runner = r'''from pathlib import Path
import sys
from python_redlines import DocxodusEngine

base, current, output, author, detect_formats = sys.argv[1:]
engine = DocxodusEngine()
content, stdout, stderr = engine.run_redline(
    author,
    original=Path(base),
    modified=Path(current),
    engine="wmlcomparer",
    detect_format_changes=(detect_formats == "true"),
)
Path(output).write_bytes(content)
if stdout:
    print(stdout, end="")
if stderr:
    print(stderr, file=sys.stderr, end="")
'''
    completed = subprocess.run(
        [
            str(REDLINES_PYTHON),
            "-c",
            runner,
            str(base),
            str(current),
            str(output),
            author,
            "true" if detect_format_changes else "false",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RedlineError(f"comparador Docxodus não concluiu a operação: {detail}")
    if not output.is_file():
        raise RedlineError("o comparador Docxodus não produziu o DOCX comparativo")


def _resolve_revision_tree(root: ET.Element, mode: str) -> None:
    if mode not in {"accept", "reject"}:
        raise RedlineError(f"modo de resolução inválido: {mode}")

    remove_when_accepting = {"del", "moveFrom"}
    remove_when_rejecting = {"ins", "moveTo"}
    unwrap_when_accepting = {"ins", "moveTo"}
    unwrap_when_rejecting = {"del", "moveFrom"}
    range_markers = {
        "moveFromRangeStart",
        "moveFromRangeEnd",
        "moveToRangeStart",
        "moveToRangeEnd",
    }

    paragraphs_to_merge: set[ET.Element] = set()
    # Revisão em pPr/rPr altera o marcador de parágrafo. Rejeitar uma inserção
    # de marcador (ou aceitar sua exclusão) funde o parágrafo com o seguinte;
    # não significa, por si só, excluir todo o texto do parágrafo.
    for parent in list(root.iter()):
        for paragraph in list(parent):
            if _local_name(paragraph.tag) != "p":
                continue
            ppr = next((node for node in paragraph if _local_name(node.tag) == "pPr"), None)
            paragraph_revision = None
            if ppr is not None:
                paragraph_revision = next(
                    (
                        _local_name(node.tag)
                        for node in ppr.iter()
                        if _local_name(node.tag) in {"ins", "del"}
                    ),
                    None,
                )
            if (mode == "reject" and paragraph_revision == "ins") or (
                mode == "accept" and paragraph_revision == "del"
            ):
                paragraphs_to_merge.add(paragraph)

    for parent in list(root.iter()):
        for child in list(parent):
            name = _local_name(child.tag)
            should_remove = (
                name in range_markers
                or name.endswith("PrChange")
                or (mode == "accept" and name in remove_when_accepting)
                or (mode == "reject" and name in remove_when_rejecting)
            )
            if should_remove:
                parent.remove(child)
                continue

            should_unwrap = (
                (mode == "accept" and name in unwrap_when_accepting)
                or (mode == "reject" and name in unwrap_when_rejecting)
            )
            if should_unwrap:
                index = list(parent).index(child)
                parent.remove(child)
                for nested in list(child):
                    parent.insert(index, nested)
                    index += 1

    for parent in list(root.iter()):
        children = list(parent)
        for index, paragraph in enumerate(children):
            if paragraph not in paragraphs_to_merge or paragraph not in list(parent):
                continue
            following = next(
                (
                    candidate
                    for candidate in children[index + 1 :]
                    if candidate in list(parent) and _local_name(candidate.tag) == "p"
                ),
                None,
            )
            if following is not None:
                for node in list(following):
                    if _local_name(node.tag) != "pPr":
                        following.remove(node)
                        paragraph.append(node)
                parent.remove(following)
            else:
                visible = any(
                    _local_name(node.tag) in {"t", "instrText"} and bool(node.text)
                    for node in paragraph.iter()
                )
                if not visible:
                    parent.remove(paragraph)

    if mode == "reject":
        for node in root.iter():
            name = _local_name(node.tag)
            if name == "delText":
                node.tag = f"{{{W_NS}}}t"
            elif name == "delInstrText":
                node.tag = f"{{{W_NS}}}instrText"


def resolve_revisions_ooxml(redline: Path, output: Path, mode: str) -> None:
    ensure_docx_valid(redline)
    with zipfile.ZipFile(redline, "r") as source:
        entries: list[tuple[zipfile.ZipInfo, bytes]] = []
        for info in source.infolist():
            data = source.read(info.filename)
            if info.filename in _story_parts(source.namelist()):
                root = ET.fromstring(data)
                _resolve_revision_tree(root, mode)
                data = ET.tostring(root, encoding="utf-8", xml_declaration=True)
            entries.append((info, data))
    with zipfile.ZipFile(output, "w") as target:
        for info, data in entries:
            target.writestr(info, data)


def _resolve_revisions(redline: Path, output: Path, mode: str) -> None:
    resolve_revisions_ooxml(redline, output, mode)
    if not output.is_file():
        raise RedlineError(f"não foi produzida a cópia com revisões {mode}")


def _atomic_copy(source: Path, destination: Path, force: bool = False) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and not force:
        raise RedlineError(f"saída já existe; use --force para substituir: {destination}")
    with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=destination.suffix, delete=False) as handle:
        temp_path = Path(handle.name)
    try:
        shutil.copy2(source, temp_path)
        ensure_docx_valid(temp_path)
        os.replace(temp_path, destination)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_json(path: Path, payload: dict[str, object], force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise RedlineError(f"manifesto já existe; use --force para substituir: {path}")
    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".json")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _write_text(path: Path, text: str, force: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not force:
        raise RedlineError(f"relatório já existe; use --force para substituir: {path}")
    fd, temp_name = tempfile.mkstemp(dir=path.parent, suffix=".md")
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(temp_path, path)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def _file_record(path: Path, state: str) -> dict[str, object]:
    return {
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "story_sha256": story_sha256(path),
        "state": state,
    }


def generate_comparison(
    *,
    base: Path,
    current: Path,
    output: Path,
    author: str,
    comparison: str,
    manifest_path: Path | None = None,
    detect_format_changes: bool = False,
    force: bool = False,
) -> dict[str, object]:
    _require_redline_engine()
    base = validate_clean_input(base, "versão-base")
    current = validate_clean_input(current, "versão corrente")
    output = output.expanduser().resolve()
    if output in {base, current}:
        raise RedlineError("o redline não pode sobrescrever a base nem o canônico limpo")
    if output.exists() and not force:
        raise RedlineError(f"saída já existe; use --force para substituir: {output}")
    if not author.strip():
        raise RedlineError("autor do redline não pode ser vazio")

    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="word-redline-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        base_copy = temp_dir / "original.docx"
        current_copy = temp_dir / "revised.docx"
        redline_temp = temp_dir / "comparison.docx"
        accepted = temp_dir / "accepted.docx"
        rejected = temp_dir / "rejected.docx"
        shutil.copy2(base, base_copy)
        shutil.copy2(current, current_copy)

        with word_lock():
            _native_compare(base_copy, current_copy, redline_temp, author.strip(), detect_format_changes)
            ensure_docx_valid(redline_temp)
            _resolve_revisions(redline_temp, accepted, "accept")
            _resolve_revisions(redline_temp, rejected, "reject")

        accepted_revisions = count_revisions(accepted)
        rejected_revisions = count_revisions(rejected)
        accepted_matches = story_sha256(accepted) == story_sha256(current)
        rejected_matches = story_sha256(rejected) == story_sha256(base)
        if accepted_revisions or rejected_revisions or not accepted_matches or not rejected_matches:
            raise RedlineError(
                "a verificação bidirecional falhou: aceitar deve reproduzir o texto corrente "
                "e rejeitar deve reproduzir o texto-base"
            )

        revisions = count_revisions(redline_temp)
        changed = story_sha256(base) != story_sha256(current)
        if changed and revisions == 0:
            raise RedlineError("o texto mudou, mas o Word não registrou revisões")
        _atomic_copy(redline_temp, output, force=force)

    payload: dict[str, object] = {
        "contract": "legal_word_redline_v1",
        "generated_at": utc_now(),
        "comparison": comparison,
        "author": author.strip(),
        "engine": {
            "name": "docxodus_wmlcomparer",
            "native_word_track_changes": True,
            "local_offline_processing": True,
            "detect_format_changes": detect_format_changes,
        },
        "base": _file_record(base, "base_imutavel"),
        "canonical_clean": _file_record(current, "canonico_limpo"),
        "redline": {
            **_file_record(output, "derivado_nao_canonico"),
            "revision_count": count_revisions(output),
        },
        "verification": {
            "accept_all_matches_current": True,
            "reject_all_matches_base": True,
            "accepted_revision_count": 0,
            "rejected_revision_count": 0,
            "scope": "texto_visivel_em_documento_cabecalhos_rodapes_notas",
        },
        "governance": {
            "approval_attaches_to": "canonical_clean.sha256",
            "redline_is_canonical": False,
            "manual_resolution_creates_new_version": True,
        },
    }
    if manifest_path is not None:
        _write_json(manifest_path.expanduser().resolve(), payload, force=force)
    return payload


def finalize_outputs(
    *,
    first: Path,
    final: Path,
    out_dir: Path,
    stem: str,
    author: str,
    previous: Path | None = None,
    original: Path | None = None,
    base_policy: str = "first",
    detect_format_changes: bool = False,
    force: bool = False,
) -> dict[str, object]:
    names = final_output_names(stem)
    out_dir = out_dir.expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    first = validate_clean_input(first, "primeira versão")
    final = validate_clean_input(final, "versão final")
    if original is not None:
        original = validate_clean_input(original, "documento original")
    if previous is not None:
        previous = validate_clean_input(previous, "versão anterior")
    if base_policy == "original" and original is None:
        raise RedlineError("--base-policy original exige --original")

    clean_output = out_dir / names.clean
    cumulative_output = out_dir / names.cumulative
    incremental_output = out_dir / names.incremental
    manifest_output = out_dir / names.manifest
    report_output = out_dir / names.report
    _atomic_copy(final, clean_output, force=force)

    cumulative_base = original if base_policy == "original" else first
    cumulative = generate_comparison(
        base=cumulative_base,
        current=clean_output,
        output=cumulative_output,
        author=author,
        comparison=f"cumulative:{base_policy}->final",
        detect_format_changes=detect_format_changes,
        force=force,
    )
    incremental: dict[str, object] | None = None
    if previous is not None:
        incremental = generate_comparison(
            base=previous,
            current=clean_output,
            output=incremental_output,
            author=author,
            comparison="incremental:previous->final",
            detect_format_changes=detect_format_changes,
            force=force,
        )

    payload: dict[str, object] = {
        "contract": "legal_word_redline_bundle_v1",
        "generated_at": utc_now(),
        "base_policy": base_policy,
        "canonical_clean": _file_record(clean_output, "canonico_limpo"),
        "cumulative_redline": cumulative["redline"],
        "incremental_redline": incremental["redline"] if incremental else None,
        "verification": {
            "cumulative": cumulative["verification"],
            "incremental": incremental["verification"] if incremental else None,
        },
        "governance": {
            "consensus_and_audit_hash": sha256_file(clean_output),
            "redlines_are_derivatives": True,
            "accept_or_reject_manually_requires_new_hash_and_new_gates": True,
        },
    }
    _write_json(manifest_output, payload, force=force)

    report_lines = [
        "# Relatório de alterações da minuta",
        "",
        f"- Gerado em: `{payload['generated_at']}`",
        f"- Autor das revisões no Word: `{author}`",
        f"- Base acumulada: `{base_policy}`",
        f"- Canônico limpo: `{clean_output.name}`",
        f"- SHA-256 canônico: `{sha256_file(clean_output)}`",
        f"- Redline acumulado: `{cumulative_output.name}`",
        f"- Revisões acumuladas: `{cumulative['redline']['revision_count']}`",
    ]
    if incremental is not None:
        report_lines.extend(
            [
                f"- Redline incremental: `{incremental_output.name}`",
                f"- Revisões incrementais: `{incremental['redline']['revision_count']}`",
            ]
        )
    report_lines.extend(
        [
            "",
            "Aceitar todas as revisões reproduz o texto do canônico limpo; rejeitar todas ",
            "reproduz o texto-base da comparação. Os arquivos com alterações são derivados ",
            "de acompanhamento e não recebem consenso ou aprovação por herança.",
            "",
            "Qualquer edição, aceitação parcial ou rejeição manual cria uma nova versão, que ",
            "deve ser salva como minuta limpa, receber novo hash e repetir os gates aplicáveis.",
            "",
        ]
    )
    _write_text(report_output, "\n".join(report_lines), force=force)
    return payload


def inject_revision_marker_for_test(path: Path | str) -> None:
    """Insere marcador mínimo somente para testes unitários do gate de entrada."""

    docx = Path(path)
    with zipfile.ZipFile(docx, "r") as source:
        document = ET.fromstring(source.read("word/document.xml"))
        paragraph = next(document.iter(f"{{{W_NS}}}p"))
        run = next((child for child in list(paragraph) if _local_name(child.tag) == "r"), None)
        if run is None:
            run = ET.SubElement(paragraph, f"{{{W_NS}}}r")
            text = ET.SubElement(run, f"{{{W_NS}}}t")
            text.text = "teste"
        index = list(paragraph).index(run)
        paragraph.remove(run)
        ins = ET.Element(f"{{{W_NS}}}ins", {f"{{{W_NS}}}id": "999999"})
        ins.append(run)
        paragraph.insert(index, ins)
        document_bytes = ET.tostring(document, encoding="utf-8", xml_declaration=True)
        entries = [(info, source.read(info.filename)) for info in source.infolist()]
    with zipfile.ZipFile(docx, "w", zipfile.ZIP_DEFLATED) as target:
        for info, data in entries:
            target.writestr(info, document_bytes if info.filename == "word/document.xml" else data)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="verifica Microsoft Word e osascript")
    doctor.add_argument("--deep", action="store_true")

    inspect = sub.add_parser("inspect", help="inspeciona hash textual e revisões")
    inspect.add_argument("docx")

    compare = sub.add_parser("compare", help="gera um redline nativo entre dois DOCX limpos")
    compare.add_argument("--base", required=True)
    compare.add_argument("--current", required=True)
    compare.add_argument("--out", required=True)
    compare.add_argument("--manifest")
    compare.add_argument("--author", default="Redator responsável")
    compare.add_argument("--comparison", default="incremental")
    compare.add_argument("--detect-format-changes", action="store_true")
    compare.add_argument("--force", action="store_true")

    finalize = sub.add_parser("finalize", help="publica minuta limpa e redlines finais")
    finalize.add_argument("--first", required=True)
    finalize.add_argument("--final", required=True)
    finalize.add_argument("--previous")
    finalize.add_argument("--original")
    finalize.add_argument("--base-policy", choices=("first", "original"), default="first")
    finalize.add_argument("--out-dir", required=True)
    finalize.add_argument("--stem", default="minuta")
    finalize.add_argument("--author", default="Redator responsável")
    finalize.add_argument("--detect-format-changes", action="store_true")
    finalize.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "doctor":
            print(json.dumps(_doctor_payload(args.deep), ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        if args.command == "inspect":
            path = Path(args.docx).expanduser().resolve()
            ensure_docx_valid(path)
            print(
                json.dumps(
                    {
                        "path": str(path),
                        "sha256": sha256_file(path),
                        "story_sha256": story_sha256(path),
                        "revision_count": count_revisions(path),
                    },
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
        if args.command == "compare":
            manifest = Path(args.manifest) if args.manifest else Path(args.out).with_suffix(".manifest.json")
            payload = generate_comparison(
                base=Path(args.base),
                current=Path(args.current),
                output=Path(args.out),
                manifest_path=manifest,
                author=args.author,
                comparison=args.comparison,
                detect_format_changes=args.detect_format_changes,
                force=args.force,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
            return 0
        payload = finalize_outputs(
            first=Path(args.first),
            final=Path(args.final),
            previous=Path(args.previous) if args.previous else None,
            original=Path(args.original) if args.original else None,
            base_policy=args.base_policy,
            out_dir=Path(args.out_dir),
            stem=args.stem,
            author=args.author,
            detect_format_changes=args.detect_format_changes,
            force=args.force,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (RedlineError, subprocess.TimeoutExpired) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
