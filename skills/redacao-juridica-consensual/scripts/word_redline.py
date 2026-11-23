#!/usr/bin/env python3
"""Gera comparações DOCX com alterações controladas nativas.

O artefato limpo continua canônico. O redline é um derivado auditável que
registra a relação entre uma versão-base (a versão aprovada indicada pelo
usuário em ``--base``) e a versão limpa corrente. As marcas são OOXML nativas
(``w:ins``/``w:del``) reconhecidas pelo Word, com autor (``--autor``) e data
(``--data``).

Motores (``--motor``):

* ``docxodus`` — comparador local Docxodus/WmlComparer (python-redlines);
  comportamento histórico, verificado pelo hash textual bidirecional;
* ``nativo`` — motor embutido, sem dependências: alinha os parágrafos base ×
  limpa (difflib), detecta DIVISÃO (um parágrafo antigo ≈ dois ou três novos
  consecutivos; a primeira parte recebe marca de parágrafo inserida) e FUSÃO
  (o inverso; marca de parágrafo excluída), faz diff POR PALAVRA dentro dos
  parágrafos alterados preservando o ``rPr`` de cada run (rótulo em negrito +
  texto continua com a formatação certa), marca parágrafos novos/excluídos
  inteiros, trata tabelas de mesma forma célula a célula e confere notas de
  rodapé/fim (alteradas, inseridas ou excluídas). Parágrafos com estrutura
  complexa (hiperlinks, campos, imagens, controles de conteúdo) que mudaram
  são substituídos inteiros (exclusão + inserção) e listados no relatório.
  O pacote (estilos, numeração, cabeçalhos, notas) é o da versão limpa;
* ``auto`` (padrão) — Docxodus quando disponível; senão o nativo, com aviso
  no relatório/manifesto.

Depois de gerar, o motor nativo chama ``integridade_docx.conferir`` (aceitar ⇒
limpa, rejeitar ⇒ base, Referências, notas, contagem opcional com
``--divididos``/``--fundidos``) e falha se houver divergência. No Docxodus a
mesma conferência é registrada no manifesto apenas como informação.

Exemplos::

    word_redline.py compare --base v16.docx --current v17.docx \\
        --out v17-alteracoes-v16-v17.docx --autor "Revisão v17" \\
        --data 2026-11-04T21:00:00Z --motor nativo --divididos 3

    word_redline.py finalize --first v01.docx --previous v05.docx \\
        --final v06.docx --out-dir entrega --autor "Redator" --motor auto
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import difflib
import fcntl
import hashlib
import html
import importlib.util
import itertools
import json
import mimetypes
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Iterator
from xml.etree import ElementTree as ET
from xml.parsers import expat


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


def _redlines_python() -> Path | None:
    """Interpretador que executa o Docxodus: o runtime dedicado ou, se o
    pacote ``python_redlines`` for importável no interpretador atual, ele."""

    if REDLINES_PYTHON.is_file():
        return REDLINES_PYTHON
    try:
        if importlib.util.find_spec("python_redlines") is not None:
            return Path(sys.executable)
    except (ImportError, ValueError):
        pass
    return None


def docxodus_disponivel() -> bool:
    return _redlines_python() is not None


def _doctor_payload(deep: bool = False) -> dict[str, object]:
    osascript = shutil.which("osascript")
    redlines_available = docxodus_disponivel()
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
        "native_engine_available": True,
        "motor_auto": "docxodus" if redlines_available else "nativo",
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
            str(_redlines_python() or REDLINES_PYTHON),
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


# ============================================================================
# Motor nativo (sem dependências): alinhamento de parágrafos + diff por palavra
# ============================================================================

NATIVO_LIMIAR_PAR = 0.40
"""Semelhança mínima (caracteres casados) para parear parágrafos base × limpa."""
NATIVO_LIMIAR_REESCRITA = 0.50
"""Abaixo desta semelhança o conteúdo do parágrafo é trocado inteiro (del + ins)."""
NATIVO_PENALIDADE_PARTE = 8.0
"""Custo, em caracteres, de cada parágrafo extra numa divisão ou fusão."""

_TOKEN = re.compile(r"\s+|\w+(?:[.,/\-–]\w+)*|[^\w\s]")
_STAG = re.compile(rb"<[^\"'>]*(?:(?:\"[^\"]*\"|'[^']*')[^\"'>]*)*>")
_ID_ATTR = re.compile(rb'w:id="(-?\d+)"')
_PARA_IDS = re.compile(rb'\s+w14:(?:paraId|textId)="[^"]*"')
_RUN_SIMPLES = {
    "w:tab",
    "w:br",
    "w:cr",
    "w:noBreakHyphen",
    "w:softHyphen",
    "w:sym",
    "w:ptab",
    "w:footnoteReference",
    "w:endnoteReference",
    "w:footnoteRef",
    "w:endnoteRef",
    "w:separator",
    "w:continuationSeparator",
}
_MARCADORES_INICIO = {"w:bookmarkStart", "w:permStart"}
_MARCADORES_FIM = {"w:bookmarkEnd", "w:permEnd"}
_MARCADORES = _MARCADORES_INICIO | _MARCADORES_FIM | {
    "w:proofErr",
    "w:commentRangeStart",
    "w:commentRangeEnd",
}
_CHAVE_NOTA = {"w:footnoteReference": "\ue000", "w:endnoteReference": "\ue001"}
_TIPO_NOTA = {"w:footnoteReference": "footnote", "w:endnoteReference": "endnote"}
_RELACAO = re.compile(rb"<Relationship\b([^>]*?)/?>")
_ATRIBUTO_REL = re.compile(rb'(r:(?:id|embed|link|pict|dm|lo|qs|cs))="([^"]+)"')


class _No:
    __slots__ = ("tag", "start", "stag_end", "end", "children")

    def __init__(self, tag: str, start: int, stag_end: int) -> None:
        self.tag = tag
        self.start = start
        self.stag_end = stag_end
        self.end = stag_end
        self.children: list[_No] = []

    def filho(self, tag: str) -> "_No | None":
        return next((c for c in self.children if c.tag == tag), None)

    def iter(self) -> Iterator["_No"]:
        yield self
        for c in self.children:
            yield from c.iter()


def _arvore(data: bytes) -> _No:
    """Árvore de posições (bytes) dos elementos, preservando o XML original."""

    parser = expat.ParserCreate()
    raiz = _No("#doc", 0, 0)
    raiz.end = len(data)
    pilha = [raiz]

    def inicio(nome: str, _attrs: object) -> None:
        pos = parser.CurrentByteIndex
        casamento = _STAG.match(data, pos)
        if casamento is None:
            raise RedlineError(f"XML inesperado na posição {pos}")
        no = _No(nome, pos, casamento.end())
        pilha[-1].children.append(no)
        pilha.append(no)

    def fim(_nome: str) -> None:
        no = pilha.pop()
        pos = parser.CurrentByteIndex
        vazio = data[no.stag_end - 2 : no.stag_end] == b"/>"
        no.end = no.stag_end if vazio else data.index(b">", pos) + 1

    parser.StartElementHandler = inicio
    parser.EndElementHandler = fim
    parser.Parse(data, True)
    return raiz


def _interno(data: bytes, no: _No) -> bytes:
    if no.end == no.stag_end:
        return b""
    return data[no.stag_end : data.rindex(b"<", no.stag_end, no.end)]


def _unesc(raw: bytes) -> str:
    return html.unescape(raw.decode("utf-8"))


def _esc(texto: str) -> bytes:
    return html.escape(texto, quote=False).encode("utf-8")


def _bruto(data: bytes, no: _No | None) -> bytes:
    return b"" if no is None else data[no.start : no.end]


def _texto_chave(data: bytes, no: _No) -> str:
    """Texto visível com marcadores para notas e objetos (chave de alinhamento)."""

    partes: list[str] = []

    def visitar(atual: _No) -> None:
        for filho in atual.children:
            tag = filho.tag
            if tag in {"w:pPr", "w:rPr", "w:txbxContent", "mc:Fallback", "w:instrText", "w:sdtPr", "w:tcPr", "w:trPr", "w:tblPr", "w:tblGrid"}:
                continue
            if tag == "w:t" or tag == "m:t":
                partes.append(_unesc(_interno(data, filho)))
            elif tag == "w:tab":
                partes.append("\t")
            elif tag in {"w:br", "w:cr"}:
                partes.append("\n")
            elif tag in _CHAVE_NOTA:
                partes.append(_CHAVE_NOTA[tag])
            elif tag in {"w:drawing", "w:pict", "w:object"}:
                partes.append("\ue010")
                visitar(filho)
            else:
                visitar(filho)

    visitar(no)
    return "".join(partes)


def _refs_notas(data: bytes, no: _No) -> list[tuple[str, str]]:
    refs = []
    for item in no.iter():
        if item.tag in _TIPO_NOTA:
            casamento = _ID_ATTR.search(data, item.start, item.stag_end)
            if casamento:
                refs.append((_TIPO_NOTA[item.tag], casamento.group(1).decode()))
    return refs


@dataclasses.dataclass
class _Atomo:
    chave: str
    rpr: bytes
    texto: str | None = None
    bruto: bytes | None = None
    nota: tuple[str, str] | None = None
    quebra: int | None = None

    @property
    def tamanho(self) -> int:
        return len(self.texto) if self.texto is not None else 1


@dataclasses.dataclass
class _Item:
    tipo: str  # "p", "tbl" ou "outro"
    data: bytes
    no: _No
    chave: str
    atomos: list[_Atomo] | None = None
    motivo: str | None = None
    marcadores_inicio: bytes = b""
    marcadores_fim: bytes = b""

    @property
    def ppr(self) -> _No | None:
        return self.no.filho("w:pPr") if self.tipo == "p" else None

    @property
    def stag(self) -> bytes:
        return self.data[self.no.start : self.no.stag_end]

    @property
    def bruto(self) -> bytes:
        return _bruto(self.data, self.no)


def _analisar_paragrafo(data: bytes, no: _No) -> _Item:
    item = _Item("p", data, no, _texto_chave(data, no))
    atomos: list[_Atomo] = []
    inicio: list[bytes] = []
    fim: list[bytes] = []
    motivo = None
    for filho in no.children:
        tag = filho.tag
        if tag == "w:pPr":
            continue
        if tag == "w:r":
            rpr = _bruto(data, filho.filho("w:rPr"))
            for parte in filho.children:
                if parte.tag in {"w:rPr", "w:lastRenderedPageBreak"}:
                    continue
                if parte.tag == "w:t":
                    for token in _TOKEN.findall(_unesc(_interno(data, parte))):
                        atomos.append(_Atomo(token, rpr, texto=token))
                elif parte.tag in _RUN_SIMPLES:
                    bruto = _bruto(data, parte)
                    if parte.tag in _CHAVE_NOTA:
                        casamento = _ID_ATTR.search(bruto)
                        nota = (_TIPO_NOTA[parte.tag], casamento.group(1).decode()) if casamento else None
                        atomos.append(_Atomo(_CHAVE_NOTA[parte.tag], rpr, bruto=bruto, nota=nota))
                    elif parte.tag == "w:tab":
                        atomos.append(_Atomo("\t", rpr, bruto=bruto))
                    elif parte.tag == "w:cr" or (parte.tag == "w:br" and b"w:type" not in bruto):
                        atomos.append(_Atomo("\n", rpr, bruto=bruto))
                    else:
                        atomos.append(_Atomo("\x00" + bruto.decode("utf-8"), rpr, bruto=bruto))
                else:
                    motivo = motivo or f"run com {parte.tag}"
        elif tag in _MARCADORES_INICIO:
            inicio.append(_bruto(data, filho))
        elif tag in _MARCADORES_FIM:
            fim.append(_bruto(data, filho))
        elif tag == "w:proofErr":
            continue
        else:
            motivo = motivo or f"elemento {tag}"
    item.motivo = motivo
    if motivo is None:
        item.atomos = atomos
        item.marcadores_inicio = b"".join(inicio)
        item.marcadores_fim = b"".join(fim)
    return item


def _itens(data: bytes, container: _No, pular: frozenset[str] = frozenset()) -> list[_Item]:
    itens: list[_Item] = []
    for filho in container.children:
        if filho.tag in pular:
            continue
        if filho.tag == "w:p":
            itens.append(_analisar_paragrafo(data, filho))
        elif filho.tag == "w:tbl":
            itens.append(_Item("tbl", data, filho, "\ue020" + _texto_chave(data, filho)))
        else:
            itens.append(_Item("outro", data, filho, "\ue021" + _bruto(data, filho).decode("utf-8")))
    return itens


def _sem_espaco(texto: str) -> list[str]:
    return [token for token in _TOKEN.findall(texto) if not token.isspace()]


def _ler_rels(conteudo: bytes | None) -> dict[str, dict[str, str]]:
    relacoes: dict[str, dict[str, str]] = {}
    for casamento in _RELACAO.finditer(conteudo or b""):
        atributos = {
            chave.decode(): html.unescape(valor.decode("utf-8"))
            for chave, valor in re.findall(rb'([\w:]+)="([^"]*)"', casamento.group(1))
        }
        if "Id" in atributos:
            relacoes[atributos["Id"]] = atributos
    return relacoes


def _nome_rels(parte: str) -> str:
    pasta, nome = posixpath.split(parte)
    return f"{pasta}/_rels/{nome}.rels"


class _MotorNativo:
    """Constrói o ``document.xml`` (e notas) com marcas de revisão.

    ``limpa`` é o pacote de saída (cópia da limpa); relações e mídias da base
    usadas por conteúdo excluído são acrescentadas a ele quando faltarem.
    """

    def __init__(
        self,
        base: dict[str, bytes],
        limpa: dict[str, bytes],
        autor: str,
        data: str,
        detectar_formatacao: bool = False,
    ) -> None:
        self.base = base
        self.limpa = limpa
        self.detectar_formatacao = detectar_formatacao
        self._attrs_fixos = b' w:author="%s" w:date="%s"' % (
            html.escape(autor, quote=True).encode("utf-8"),
            data.encode("ascii"),
        )
        maior = 0
        for pacote in (base, limpa):
            for nome, conteudo in pacote.items():
                if nome.endswith(".xml") and nome.startswith("word/"):
                    for casamento in _ID_ATTR.finditer(conteudo):
                        maior = max(maior, int(casamento.group(1)))
        self._proximo_id = maior + 1
        self._cache_semelhanca: dict[tuple[str, str], tuple[float, int]] = {}
        self._em_nota = False
        self._parte = "word/document.xml"
        self._cache_rels: dict[tuple[str, str], str] = {}
        self.avisos: list[str] = []
        self.relatorio: dict[str, object] = {
            "paragrafos_iguais": 0,
            "alterados_por_palavra": 0,
            "divisoes": 0,
            "paragrafos_acrescidos_por_divisao": 0,
            "fusoes": 0,
            "paragrafos_absorvidos_por_fusao": 0,
            "inseridos": 0,
            "excluidos": 0,
            "tabelas_celula_a_celula": 0,
            "tabelas_substituidas": 0,
            "substituidos_inteiros": [],
            "notas": {"alteradas": 0, "inseridas": 0, "excluidas": 0},
        }
        self._notas: dict[str, dict[str, object]] = {}
        for tipo in ("footnote", "endnote"):
            self._notas[tipo] = {
                "base": self._mapa_notas(base.get(f"word/{tipo}s.xml"), tipo),
                "limpa": self._mapa_notas(limpa.get(f"word/{tipo}s.xml"), tipo),
                "pares": {},  # id limpa -> id base
                "inseridas": set(),
                "copias": {},  # id base -> novo id
            }

    # ------------------------------------------------------------------ util
    def _rid(self) -> bytes:
        valor = self._proximo_id
        self._proximo_id += 1
        return str(valor).encode()

    def _attrs(self) -> bytes:
        return b' w:id="%s"%s' % (self._rid(), self._attrs_fixos)

    def _abre(self, estado: str) -> bytes:
        return b"<w:%s%s>" % (estado.encode(), self._attrs())

    @staticmethod
    def _fecha(estado: str) -> bytes:
        return b"</w:%s>" % estado.encode()

    def _conta(self, chave: str, quantidade: int = 1) -> None:
        if not self._em_nota:
            self.relatorio[chave] = int(self.relatorio[chave]) + quantidade  # type: ignore[arg-type]

    def _substituido(self, item: _Item, motivo: str) -> None:
        if not self._em_nota:
            lista = self.relatorio["substituidos_inteiros"]
            assert isinstance(lista, list)
            lista.append({"trecho": item.chave.replace("\ue000", "")[:80], "motivo": motivo})

    @staticmethod
    def _mapa_notas(conteudo: bytes | None, tipo: str) -> dict[str, object]:
        if conteudo is None:
            return {"data": None, "raiz": None, "notas": {}}
        arvore = _arvore(conteudo)
        raiz = next(no for no in arvore.children)
        notas = {}
        for no in raiz.children:
            if no.tag == f"w:{tipo}":
                casamento = _ID_ATTR.search(conteudo, no.start, no.stag_end)
                if casamento:
                    notas[casamento.group(1).decode()] = no
        return {"data": conteudo, "raiz": raiz, "notas": notas}

    # --------------------------------------------------------------- notas
    def _nota_par(self, tipo: str, id_base: str, id_limpa: str) -> None:
        pares = self._notas[tipo]["pares"]
        assert isinstance(pares, dict)
        pares.setdefault(id_limpa, id_base)

    def _nota_inserida(self, tipo: str, id_limpa: str) -> None:
        inseridas = self._notas[tipo]["inseridas"]
        assert isinstance(inseridas, set)
        inseridas.add(id_limpa)

    def _nota_excluida(self, tipo: str, id_base: str) -> str:
        info = self._notas[tipo]
        copias = info["copias"]
        assert isinstance(copias, dict)
        if id_base not in copias:
            usados = [int(i) for i in info["limpa"]["notas"]] + [int(v) for v in copias.values()]  # type: ignore[index]
            copias[id_base] = str(max(usados + [0]) + 1)
        return copias[id_base]

    def _remapear_refs(self, bruto: bytes, estado: str) -> bytes:
        def trocar(casamento: re.Match[bytes]) -> bytes:
            tipo = casamento.group(1).decode()
            ident = casamento.group(3).decode()
            if estado == "del":
                ident = self._nota_excluida(tipo, ident)
            elif estado == "ins":
                self._nota_inserida(tipo, ident)
            return b"<w:%sReference%sw:id=\"%s\"" % (casamento.group(1), casamento.group(2), ident.encode())

        return re.sub(rb'<w:(footnote|endnote)Reference(\b[^>]*?)w:id="(-?\d+)"', trocar, bruto)

    def _parear_refs(self, velho: _Item, novo: _Item) -> None:
        for (tipo_a, id_a), (tipo_b, id_b) in zip(_refs_notas(velho.data, velho.no), _refs_notas(novo.data, novo.no)):
            if tipo_a == tipo_b:
                self._nota_par(tipo_a, id_a, id_b)

    # -------------------------------------------------------- semelhança
    def _semelhanca(self, texto_a: str, texto_b: str) -> tuple[float, int]:
        chave = (texto_a, texto_b)
        if chave in self._cache_semelhanca:
            return self._cache_semelhanca[chave]
        tokens_a, tokens_b = _sem_espaco(texto_a), _sem_espaco(texto_b)
        total = sum(map(len, tokens_a)) + sum(map(len, tokens_b))
        resultado = (0.0, 0)
        if total:
            matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
            if matcher.real_quick_ratio() >= NATIVO_LIMIAR_PAR / 2 and matcher.quick_ratio() >= NATIVO_LIMIAR_PAR / 2:
                casados = sum(
                    len(token)
                    for bloco in matcher.get_matching_blocks()
                    for token in tokens_a[bloco.a : bloco.a + bloco.size]
                )
                resultado = (2 * casados / total, casados)
        self._cache_semelhanca[chave] = resultado
        return resultado

    def _semelhanca_partes(self, unico: str, partes: list[str]) -> float | None:
        """Pontuação de ``unico`` ≈ concatenação de ``partes`` (divisão/fusão)."""

        tokens_a = _sem_espaco(unico)
        tokens_b: list[str] = []
        dono: list[int] = []
        for indice, parte in enumerate(partes):
            tokens = _sem_espaco(parte)
            tokens_b.extend(tokens)
            dono.extend([indice] * len(tokens))
        total = sum(map(len, tokens_a)) + sum(map(len, tokens_b))
        if not total or not all(_sem_espaco(parte) for parte in partes):
            return None
        matcher = difflib.SequenceMatcher(None, tokens_a, tokens_b, autojunk=False)
        if matcher.quick_ratio() < NATIVO_LIMIAR_PAR:
            return None
        por_parte = [0] * len(partes)
        casados = 0
        for bloco in matcher.get_matching_blocks():
            for deslocamento in range(bloco.size):
                tamanho = len(tokens_b[bloco.b + deslocamento])
                por_parte[dono[bloco.b + deslocamento]] += tamanho
                casados += tamanho
        if 2 * casados / total < NATIVO_LIMIAR_PAR:
            return None
        for indice, parte in enumerate(partes):
            if por_parte[indice] < 0.3 * sum(map(len, _sem_espaco(parte))):
                return None
        return float(casados)

    def _par(self, velho: _Item, novo: _Item) -> float | None:
        if velho.tipo != novo.tipo or velho.tipo == "outro":
            return None
        razao, casados = self._semelhanca(velho.chave, novo.chave)
        return float(casados) if razao >= NATIVO_LIMIAR_PAR else None

    # -------------------------------------------------------- alinhamento
    def _alinhar(self, velhos: list[_Item], novos: list[_Item]) -> list[tuple[str, list[_Item], list[_Item]]]:
        grupos: list[tuple[str, list[_Item], list[_Item]]] = []
        matcher = difflib.SequenceMatcher(
            None, [item.chave for item in velhos], [item.chave for item in novos], autojunk=False
        )
        for op, i1, i2, j1, j2 in matcher.get_opcodes():
            if op == "equal":
                grupos.extend(("eq", [velhos[i]], [novos[j]]) for i, j in zip(range(i1, i2), range(j1, j2)))
            else:
                grupos.extend(self._alinhar_bloco(velhos[i1:i2], novos[j1:j2]))
        return grupos

    def _alinhar_bloco(self, a: list[_Item], b: list[_Item]) -> list[tuple[str, list[_Item], list[_Item]]]:
        n, m = len(a), len(b)
        faixa = None if n * m <= 10000 else max(40, abs(n - m) + 10)
        melhor = [[0.0] * (m + 1) for _ in range(n + 1)]
        escolha: list[list[tuple[str, int, int]]] = [[("", 0, 0)] * (m + 1) for _ in range(n + 1)]
        for i in range(n, -1, -1):
            for j in range(m, -1, -1):
                if i == n and j == m:
                    continue
                candidatos: list[tuple[float, tuple[str, int, int]]] = []
                perto = faixa is None or abs(j - (i * m / n if n else 0)) <= faixa
                if i < n and j < m and perto:
                    pontos = self._par(a[i], b[j])
                    if pontos is not None:
                        candidatos.append((pontos + melhor[i + 1][j + 1], ("mod", 1, 1)))
                    for k in (2, 3):
                        if j + k <= m and a[i].atomos is not None and all(x.atomos is not None for x in b[j : j + k]):
                            pontos = self._semelhanca_partes(a[i].chave, [x.chave for x in b[j : j + k]])
                            if pontos is not None:
                                total = pontos - NATIVO_PENALIDADE_PARTE * (k - 1) + melhor[i + 1][j + k]
                                candidatos.append((total, ("div", 1, k)))
                        if i + k <= n and b[j].atomos is not None and all(x.atomos is not None for x in a[i : i + k]):
                            pontos = self._semelhanca_partes(b[j].chave, [x.chave for x in a[i : i + k]])
                            if pontos is not None:
                                total = pontos - NATIVO_PENALIDADE_PARTE * (k - 1) + melhor[i + k][j + 1]
                                candidatos.append((total, ("fus", k, 1)))
                if i < n:
                    candidatos.append((melhor[i + 1][j], ("del", 1, 0)))
                if j < m:
                    candidatos.append((melhor[i][j + 1], ("ins", 0, 1)))
                pontos, passo = candidatos[0]
                for candidato in candidatos[1:]:
                    if candidato[0] > pontos + 1e-9:
                        pontos, passo = candidato
                melhor[i][j] = pontos
                escolha[i][j] = passo
        grupos: list[tuple[str, list[_Item], list[_Item]]] = []
        i = j = 0
        while i < n or j < m:
            tipo, di, dj = escolha[i][j]
            grupos.append((tipo, a[i : i + di], b[j : j + dj]))
            i, j = i + di, j + dj
        # Exclusões antes das inserções em cada trecho contíguo, para leitura.
        ordenados: list[tuple[str, list[_Item], list[_Item]]] = []
        pendentes: list[tuple[str, list[_Item], list[_Item]]] = []
        for grupo in grupos + [("fim", [], [])]:
            if grupo[0] in {"del", "ins"}:
                pendentes.append(grupo)
                continue
            ordenados.extend(sorted(pendentes, key=lambda g: g[0] != "del"))
            pendentes = []
            if grupo[0] != "fim":
                ordenados.append(grupo)
        return ordenados

    # ------------------------------------------------------------ emissão
    def emitir_itens(self, velhos: list[_Item], novos: list[_Item]) -> bytes:
        saida: list[bytes] = []
        for tipo, vs, ns in self._alinhar(velhos, novos):
            if tipo == "eq":
                saida.append(self._igual(vs[0], ns[0]))
            elif tipo == "del":
                saida.append(self._excluido(vs[0]))
            elif tipo == "ins":
                saida.append(self._inserido(ns[0]))
            elif tipo == "mod":
                saida.append(self._modificado(vs[0], ns[0]))
            else:
                if tipo == "div":
                    self._conta("divisoes")
                    self._conta("paragrafos_acrescidos_por_divisao", len(ns) - 1)
                else:
                    self._conta("fusoes")
                    self._conta("paragrafos_absorvidos_por_fusao", len(vs) - 1)
                saida.append(self._grupo(vs, ns))
        return b"".join(saida)

    def _igual(self, velho: _Item, novo: _Item) -> bytes:
        if novo.tipo == "p":
            self._conta("paragrafos_iguais")
            if (
                self.detectar_formatacao
                and velho.atomos is not None
                and novo.atomos is not None
                and velho.bruto != novo.bruto
            ):
                # Mesmo texto, formatação possivelmente diferente: o diff gera
                # apenas w:rPrChange/w:pPrChange onde houver mudança.
                return self._grupo([velho], [novo], contar=False)
        self._parear_refs(velho, novo)
        return novo.bruto

    def _ppr_marcado(self, item: _Item, marca: str) -> bytes:
        tag = b"<w:%s%s/>" % (marca.encode(), self._attrs())
        ppr, data = item.ppr, item.data
        if ppr is None or ppr.end == ppr.stag_end:
            return b"<w:pPr><w:rPr>" + tag + b"</w:rPr></w:pPr>"
        rpr = ppr.filho("w:rPr")
        if rpr is not None:
            if rpr.end == rpr.stag_end:
                return data[ppr.start : rpr.start] + b"<w:rPr>" + tag + b"</w:rPr>" + data[rpr.end : ppr.end]
            return data[ppr.start : rpr.stag_end] + tag + data[rpr.stag_end : ppr.end]
        posicao = next(
            (c.start for c in ppr.children if c.tag in {"w:sectPr", "w:pPrChange"}),
            data.rindex(b"<", ppr.start, ppr.end),
        )
        return data[ppr.start : posicao] + b"<w:rPr>" + tag + b"</w:rPr>" + data[posicao : ppr.end]

    def _ppr_mudanca(self, velho: _Item, novo: _Item) -> bytes:
        """``pPr`` novo, com ``w:pPrChange`` se a formatação mudou (opt-in)."""

        bruto_novo = _bruto(novo.data, novo.ppr)
        if not self.detectar_formatacao:
            return bruto_novo

        def normal(item: _Item) -> bytes:
            ppr = item.ppr
            if ppr is None:
                return b""
            return b"".join(_bruto(item.data, c) for c in ppr.children if c.tag not in {"w:rPr", "w:sectPr", "w:pPrChange"})

        antigo = normal(velho)
        if antigo == normal(novo):
            return bruto_novo
        mudanca = b"<w:pPrChange%s><w:pPr>%s</w:pPr></w:pPrChange>" % (self._attrs(), antigo)
        if not bruto_novo or bruto_novo.endswith(b"/>"):
            return b"<w:pPr>" + mudanca + b"</w:pPr>"
        return bruto_novo[: -len(b"</w:pPr>")] + mudanca + b"</w:pPr>"

    @staticmethod
    def _stag_base(item: _Item) -> bytes:
        return _PARA_IDS.sub(b"", item.stag)

    # ------------------------------------------- relações do conteúdo-base
    def _remapear_relacoes(self, bruto: bytes) -> bytes:
        """Conteúdo excluído vem da base: seus ``r:id``/``r:embed`` precisam
        existir no pacote de saída (o da limpa)."""

        if b"r:" not in bruto:
            return bruto
        return _ATRIBUTO_REL.sub(
            lambda m: m.group(1) + b'="' + self._relacao_saida(m.group(2).decode()).encode() + b'"', bruto
        )

    def _garantir_tipo(self, caminho: str, original: str) -> None:
        tipos = self.limpa.get("[Content_Types].xml", b"")
        override = re.search(
            rb'<Override\b[^>]*PartName="/%s"[^>]*ContentType="([^"]+)"' % re.escape(original.encode()),
            self.base.get("[Content_Types].xml", b""),
        )
        if override:
            if f'PartName="/{caminho}"'.encode() not in tipos:
                tipos = tipos.replace(
                    b"</Types>",
                    b'<Override PartName="/%s" ContentType="%s"/></Types>' % (caminho.encode(), override.group(1)),
                )
        else:
            extensao = caminho.rsplit(".", 1)[-1].lower()
            if f'Extension="{extensao}"'.encode() not in tipos.lower():
                tipo = mimetypes.guess_type(caminho)[0] or "application/octet-stream"
                tipos = tipos.replace(
                    b"</Types>", b'<Default Extension="%s" ContentType="%s"/></Types>' % (extensao.encode(), tipo.encode())
                )
        self.limpa["[Content_Types].xml"] = tipos

    def _relacao_saida(self, rid: str) -> str:
        chave = (self._parte, rid)
        if chave in self._cache_rels:
            return self._cache_rels[chave]
        nome_rels = _nome_rels(self._parte)
        relacao = _ler_rels(self.base.get(nome_rels)).get(rid)
        if relacao is None:
            self.avisos.append(f"relação {rid} do conteúdo-base não encontrada em {nome_rels}")
            return rid
        alvo = relacao.get("Target", "")
        externo = relacao.get("TargetMode") == "External"
        if not externo:
            pasta = posixpath.dirname(self._parte)
            original = alvo[1:] if alvo.startswith("/") else posixpath.normpath(posixpath.join(pasta, alvo))
            caminho = original
            conteudo = self.base.get(original)
            if conteudo is not None:
                if self.limpa.get(caminho) not in (None, conteudo):
                    dir_alvo, nome_alvo = posixpath.split(original)
                    caminho = posixpath.join(dir_alvo, f"nativo_base_{nome_alvo}")
                    alvo = posixpath.relpath(caminho, pasta)
                if caminho not in self.limpa:
                    self.limpa[caminho] = conteudo
                    self._garantir_tipo(caminho, original)
        saida = _ler_rels(self.limpa.get(nome_rels))
        for ident, existente in saida.items():
            if (
                existente.get("Type") == relacao.get("Type")
                and existente.get("Target") == alvo
                and existente.get("TargetMode") == relacao.get("TargetMode")
            ):
                self._cache_rels[chave] = ident
                return ident
        numero = 1
        while f"rIdNativo{numero}" in saida:
            numero += 1
        novo = f"rIdNativo{numero}"
        elemento = '<Relationship Id="{}" Type="{}" Target="{}"{}/>'.format(
            novo,
            html.escape(relacao.get("Type", ""), quote=True),
            html.escape(alvo, quote=True),
            ' TargetMode="External"' if externo else "",
        ).encode("utf-8")
        atual = self.limpa.get(nome_rels)
        if atual is None:
            atual = (
                b'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                b'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"></Relationships>'
            )
        self.limpa[nome_rels] = atual.replace(b"</Relationships>", elemento + b"</Relationships>")
        self._cache_rels[chave] = novo
        return novo

    def _run_marcado(self, data: bytes, run: _No, estado: str) -> bytes:
        bruto = _bruto(data, run)
        if estado == "del" and b"<w:commentReference" in bruto:
            return b""  # o comentário da base não existe na limpa
        if estado == "del":
            bruto = re.sub(rb"<w:t(?=[\s>/])", b"<w:delText", bruto)
            bruto = bruto.replace(b"</w:t>", b"</w:delText>")
            bruto = re.sub(rb"<w:instrText(?=[\s>/])", b"<w:delInstrText", bruto)
            bruto = bruto.replace(b"</w:instrText>", b"</w:delInstrText>")
        return self._remapear_refs(bruto, estado)

    def _transformar(self, data: bytes, filhos: list[_No], estado: str) -> bytes:
        """Envolve todos os runs em ``w:del``/``w:ins``, preservando contêineres."""

        saida: list[bytes] = []
        runs: list[bytes] = []

        def descarregar() -> None:
            if runs:
                saida.append(self._abre(estado) + b"".join(runs) + self._fecha(estado))
                runs.clear()

        for filho in filhos:
            if filho.tag in {"w:pPr", "w:rPr", "w:sdtPr", "w:sdtEndPr", "w:fldData"}:
                descarregar()
                saida.append(_bruto(data, filho))
                continue
            if filho.tag == "w:r":
                runs.append(self._run_marcado(data, filho, estado))
                continue
            descarregar()
            if filho.tag in _MARCADORES:
                if estado == "ins":
                    saida.append(_bruto(data, filho))
                continue
            if filho.tag.startswith("m:"):
                if estado == "ins":
                    saida.append(_bruto(data, filho))
                self.avisos.append("fórmula (OMML) alterada não é rastreada pelo motor nativo")
                continue
            if filho.children:
                miolo = self._transformar(data, filho.children, estado)
                saida.append(
                    data[filho.start : filho.stag_end] + miolo + data[filho.children[-1].end : filho.end]
                )
            else:
                saida.append(_bruto(data, filho))
        descarregar()
        return b"".join(saida)

    def _paragrafo_inteiro(self, item: _Item, estado: str, marcar: bool = True) -> bytes:
        conteudo = self._transformar(item.data, [c for c in item.no.children if c.tag != "w:pPr"], estado)
        if estado == "del":
            conteudo = self._remapear_relacoes(conteudo)
        stag = self._stag_base(item) if estado == "del" else item.stag
        ppr = self._ppr_marcado(item, estado) if marcar else _bruto(item.data, item.ppr)
        return stag + ppr + conteudo + b"</w:p>"

    def _excluido(self, item: _Item) -> bytes:
        if item.tipo == "p":
            self._conta("excluidos")
            return self._paragrafo_inteiro(item, "del")
        if item.tipo == "tbl":
            self._conta("tabelas_substituidas")
            return self._tabela_marcada(item.data, item.no, "del")
        if item.chave.strip("\ue021").strip():
            self.avisos.append(f"bloco {item.no.tag} da base omitido sem marca de revisão")
        return b""

    def _inserido(self, item: _Item) -> bytes:
        if item.tipo == "p":
            self._conta("inseridos")
            return self._paragrafo_inteiro(item, "ins")
        if item.tipo == "tbl":
            self._conta("tabelas_substituidas")
            return self._tabela_marcada(item.data, item.no, "ins")
        if item.chave.strip("\ue021").strip():
            self.avisos.append(f"bloco {item.no.tag} da limpa incluído sem marca de revisão")
        return item.bruto

    def _modificado(self, velho: _Item, novo: _Item) -> bytes:
        if velho.chave == novo.chave:
            return self._igual(velho, novo)
        if novo.tipo == "tbl":
            return self._tabela(velho, novo)
        if velho.atomos is not None and novo.atomos is not None:
            return self._grupo([velho], [novo])
        motivo = velho.motivo or novo.motivo or "estrutura complexa"
        self._substituido(novo, f"estrutura complexa ({motivo})")
        filhos_velhos = [c for c in velho.no.children if c.tag != "w:pPr"]
        filhos_novos = [c for c in novo.no.children if c.tag != "w:pPr"]
        return (
            novo.stag
            + _bruto(novo.data, novo.ppr)
            + self._remapear_relacoes(self._transformar(velho.data, filhos_velhos, "del"))
            + self._transformar(novo.data, filhos_novos, "ins")
            + b"</w:p>"
        )

    # ------------------------------------------------- diff por palavra
    def _operacoes(self, a: list[_Atomo], b: list[_Atomo]) -> tuple[list[tuple[str, int, int, int, int]], bool]:
        matcher = difflib.SequenceMatcher(None, [x.chave for x in a], [x.chave for x in b], autojunk=False)
        ops = matcher.get_opcodes()
        iguais = sum(sum(x.tamanho for x in a[i1:i2] if x.quebra is None) for op, i1, i2, _, _ in ops if op == "equal")
        total = sum(x.tamanho for x in a if x.quebra is None) + sum(x.tamanho for x in b if x.quebra is None)
        if total and 2 * iguais / total < NATIVO_LIMIAR_REESCRITA:
            return [("replace", 0, len(a), 0, len(b))], True

        def ilha(i1: int, i2: int) -> bool:
            atomos = a[i1:i2]
            if any(x.texto is None for x in atomos):
                return False
            palavras = [x.texto for x in atomos if x.texto and x.texto.strip() and re.match(r"\w", x.texto)]
            return len(palavras) == 0 or (len(palavras) == 1 and len(palavras[0]) <= 3)

        # Absorve "ilhas" mínimas (espaço, pontuação, artigo) entre alterações:
        # o resultado lê como uma substituição contínua, e não como retalhos.
        limpos: list[list[object]] = []
        for indice, (op, i1, i2, j1, j2) in enumerate(ops):
            entre = 0 < indice < len(ops) - 1 and ops[indice - 1][0] != "equal" and ops[indice + 1][0] != "equal"
            if op == "equal" and entre and ilha(i1, i2):
                op = "replace"
            if op != "equal" and limpos and limpos[-1][0] != "equal":
                limpos[-1][0] = "replace"
                limpos[-1][2] = i2
                limpos[-1][4] = j2
            else:
                limpos.append([op, i1, i2, j1, j2])
        return [tuple(item) for item in limpos], False  # type: ignore[misc]

    def _grupo(self, velhos: list[_Item], novos: list[_Item], contar: bool = True) -> bytes:
        """Diff por palavra de 1:1, 1:k (divisão) ou k:1 (fusão)."""

        a: list[_Atomo] = []
        for indice, item in enumerate(velhos):
            if indice:
                a.append(_Atomo("\x00QUEBRA", b"", quebra=indice - 1))
            a.extend(item.atomos or [])
        b: list[_Atomo] = []
        for indice, item in enumerate(novos):
            if indice:
                b.append(_Atomo("\x00QUEBRA", b"", quebra=indice - 1))
            b.extend(item.atomos or [])
        ops, reescrito = self._operacoes(a, b)
        if reescrito:
            self._substituido(novos[0], "reescrita (semelhança abaixo de 50%): conteúdo trocado inteiro")
        elif contar and len(velhos) == len(novos) == 1:
            self._conta("alterados_por_palavra")

        paragrafos: list[bytes] = []
        pecas: list[tuple[str, bytes, bytes | None, str | bytes]] = []
        inicio = novos[0].marcadores_inicio

        def fechar(stag: bytes, ppr: bytes, fim: bytes = b"") -> None:
            nonlocal inicio
            paragrafos.append(stag + ppr + inicio + self._runs(pecas) + fim + b"</w:p>")
            pecas.clear()
            inicio = b""

        for op, i1, i2, j1, j2 in ops:
            if op == "equal":
                for x, y in zip(a[i1:i2], b[j1:j2]):
                    if x.nota and y.nota and x.nota[0] == y.nota[0]:
                        self._nota_par(x.nota[0], x.nota[1], y.nota[1])
                    velho_rpr = x.rpr if self.detectar_formatacao and x.rpr != y.rpr else None
                    pecas.append(("eq", y.rpr, velho_rpr, self._peca(y, "eq")))
                continue
            for x in a[i1:i2]:
                if x.quebra is not None:
                    origem = velhos[x.quebra]
                    fechar(self._stag_base(origem), self._ppr_marcado(origem, "del"))
                else:
                    pecas.append(("del", x.rpr, None, self._peca(x, "del")))
            for y in b[j1:j2]:
                if y.quebra is not None:
                    parte = novos[y.quebra]
                    fechar(parte.stag, self._ppr_marcado(parte, "ins"), parte.marcadores_fim)
                    inicio = novos[y.quebra + 1].marcadores_inicio
                else:
                    pecas.append(("ins", y.rpr, None, self._peca(y, "ins")))
        ultimo = novos[-1]
        ppr_final = self._ppr_mudanca(velhos[0], ultimo) if len(velhos) == len(novos) == 1 else _bruto(ultimo.data, ultimo.ppr)
        fechar(ultimo.stag, ppr_final, ultimo.marcadores_fim)
        return b"".join(paragrafos)

    def _peca(self, atomo: _Atomo, estado: str) -> str | bytes:
        """Texto (``str``, fundido depois num só ``w:t``) ou elemento bruto."""

        if atomo.texto is not None:
            return atomo.texto
        bruto = atomo.bruto or b""
        if atomo.nota and estado in {"del", "ins"}:
            bruto = self._remapear_refs(bruto, estado)
        return bruto

    def _rpr_mudanca(self, novo: bytes, velho: bytes) -> bytes:
        interno = b""
        if velho and not velho.endswith(b"/>"):
            interno = velho[velho.index(b">") + 1 : velho.rindex(b"<")]
        mudanca = b"<w:rPrChange%s><w:rPr>%s</w:rPr></w:rPrChange>" % (self._attrs(), interno)
        if not novo or novo.endswith(b"/>"):
            return b"<w:rPr>" + mudanca + b"</w:rPr>"
        return novo[: novo.rindex(b"<")] + mudanca + b"</w:rPr>"

    def _runs(self, pecas: list[tuple[str, bytes, bytes | None, str | bytes]]) -> bytes:
        saida: list[bytes] = []
        for estado, grupo in itertools.groupby(pecas, key=lambda p: p[0]):
            runs = []
            for (rpr, velho_rpr), subgrupo in itertools.groupby(grupo, key=lambda p: (p[1], p[2])):
                propriedades = self._rpr_mudanca(rpr, velho_rpr) if velho_rpr is not None else rpr
                conteudo = []
                tag = b"w:delText" if estado == "del" else b"w:t"
                for e_texto, pedacos in itertools.groupby((p[3] for p in subgrupo), key=lambda x: isinstance(x, str)):
                    if e_texto:
                        texto = _esc("".join(pedacos))  # type: ignore[arg-type]
                        conteudo.append(b'<%s xml:space="preserve">%s</%s>' % (tag, texto, tag))
                    else:
                        conteudo.extend(pedacos)  # type: ignore[arg-type]
                runs.append(b"<w:r>" + propriedades + b"".join(conteudo) + b"</w:r>")
            corpo = b"".join(runs)
            saida.append(corpo if estado == "eq" else self._abre(estado) + corpo + self._fecha(estado))
        return b"".join(saida)

    # ------------------------------------------------------------ tabelas
    @staticmethod
    def _forma(data: bytes, tabela: _No) -> list[int]:
        return [len([c for c in linha.children if c.tag == "w:tc"]) for linha in tabela.children if linha.tag == "w:tr"]

    def _tabela(self, velho: _Item, novo: _Item) -> bytes:
        if self._forma(velho.data, velho.no) != self._forma(novo.data, novo.no):
            self._conta("tabelas_substituidas")
            return self._tabela_marcada(velho.data, velho.no, "del") + self._tabela_marcada(novo.data, novo.no, "ins")
        self._conta("tabelas_celula_a_celula")
        linhas_velhas = [c for c in velho.no.children if c.tag == "w:tr"]
        saida = [novo.stag]
        indice_linha = 0
        for filho in novo.no.children:
            if filho.tag != "w:tr":
                saida.append(_bruto(novo.data, filho))
                continue
            linha_velha = linhas_velhas[indice_linha]
            indice_linha += 1
            celulas_velhas = [c for c in linha_velha.children if c.tag == "w:tc"]
            saida.append(novo.data[filho.start : filho.stag_end])
            indice_celula = 0
            for parte in filho.children:
                if parte.tag != "w:tc":
                    saida.append(_bruto(novo.data, parte))
                    continue
                celula_velha = celulas_velhas[indice_celula]
                indice_celula += 1
                saida.append(novo.data[parte.start : parte.stag_end])
                saida.append(_bruto(novo.data, parte.filho("w:tcPr")))
                saida.append(
                    self.emitir_itens(
                        _itens(velho.data, celula_velha, frozenset({"w:tcPr"})),
                        _itens(novo.data, parte, frozenset({"w:tcPr"})),
                    )
                )
                saida.append(b"</w:tc>")
            saida.append(b"</w:tr>")
        saida.append(b"</w:tbl>")
        return b"".join(saida)

    def _tabela_marcada(self, data: bytes, tabela: _No, estado: str) -> bytes:
        """Tabela inteira inserida/excluída: linhas com ``w:trPr/w:ins|del``."""

        saida = [data[tabela.start : tabela.stag_end]]
        for filho in tabela.children:
            if filho.tag != "w:tr":
                saida.append(_bruto(data, filho))
                continue
            marca = b"<w:%s%s/>" % (estado.encode(), self._attrs())
            trpr = filho.filho("w:trPr")
            linha = [data[filho.start : filho.stag_end]]
            if trpr is None:
                linha.append(b"<w:trPr>" + marca + b"</w:trPr>")
            for parte in filho.children:
                if parte is trpr:
                    if parte.end == parte.stag_end:
                        linha.append(b"<w:trPr>" + marca + b"</w:trPr>")
                    else:
                        posicao = next((c.start for c in parte.children if c.tag == "w:trPrChange"), data.rindex(b"<", parte.start, parte.end))
                        linha.append(data[parte.start : posicao] + marca + data[posicao : parte.end])
                elif parte.tag == "w:tc":
                    linha.append(data[parte.start : parte.stag_end])
                    for bloco in parte.children:
                        if bloco.tag == "w:p":
                            item = _analisar_paragrafo(data, bloco)
                            linha.append(self._paragrafo_inteiro(item, estado, marcar=False))
                        elif bloco.tag == "w:tbl":
                            linha.append(self._tabela_marcada(data, bloco, estado))
                        else:
                            linha.append(_bruto(data, bloco))
                    linha.append(b"</w:tc>")
                else:
                    linha.append(_bruto(data, parte))
            linha.append(b"</w:tr>")
            saida.extend(linha)
        saida.append(b"</w:tbl>")
        return b"".join(saida)

    # ------------------------------------------------------------ partes
    def documento(self) -> bytes:
        self._parte = "word/document.xml"
        dados_base = self.base["word/document.xml"]
        dados_limpa = self.limpa["word/document.xml"]
        for nome, dados in (("base", dados_base), ("limpa", dados_limpa)):
            if f'xmlns:w="{W_NS}"'.encode() not in dados[:4000]:
                raise RedlineError(f"motor nativo exige o prefixo w: do WordprocessingML ({nome})")
        corpo_base = next(no for no in _arvore(dados_base).iter() if no.tag == "w:body")
        corpo_limpa = next(no for no in _arvore(dados_limpa).iter() if no.tag == "w:body")
        sem_secao = frozenset({"w:sectPr"})
        miolo = self.emitir_itens(
            _itens(dados_base, corpo_base, sem_secao),
            _itens(dados_limpa, corpo_limpa, sem_secao),
        )
        secao = b"".join(_bruto(dados_limpa, c) for c in corpo_limpa.children if c.tag == "w:sectPr")
        fim = corpo_limpa.children[-1].end if corpo_limpa.children else corpo_limpa.stag_end
        return dados_limpa[: corpo_limpa.stag_end] + miolo + secao + dados_limpa[fim:]

    def notas(self, tipo: str) -> bytes | None:
        """Parte de notas com alterações; ``None`` se a da limpa serve como está."""

        info = self._notas[tipo]
        self._parte = f"word/{tipo}s.xml"
        base_info, limpa_info = info["base"], info["limpa"]
        pares, inseridas, copias = info["pares"], info["inseridas"], info["copias"]
        assert isinstance(pares, dict) and isinstance(inseridas, set) and isinstance(copias, dict)
        assert isinstance(base_info, dict) and isinstance(limpa_info, dict)
        if not (pares or inseridas or copias):
            return None
        self._em_nota = True
        try:
            dados_limpa = limpa_info["data"]
            dados_base = base_info["data"]
            if dados_limpa is None:
                if not copias:
                    return None
                raiz = base_info["raiz"]
                partes = [dados_base[: raiz.stag_end]]
                for no in raiz.children:
                    if no.tag == f"w:{tipo}" and b"w:type=" in dados_base[no.start : no.stag_end]:
                        partes.append(_bruto(dados_base, no))
                partes.extend(self._copias_excluidas(tipo))
                partes.append(dados_base[raiz.children[-1].end if raiz.children else raiz.stag_end :])
                return b"".join(partes)
            raiz = limpa_info["raiz"]
            notas_base = base_info["notas"]
            partes = [dados_limpa[: raiz.stag_end]]
            posicao = raiz.stag_end
            for no in raiz.children:
                partes.append(dados_limpa[posicao : no.start])
                posicao = no.end
                casamento = _ID_ATTR.search(dados_limpa, no.start, no.stag_end)
                ident = casamento.group(1).decode() if casamento else None
                if ident in pares and pares[ident] in notas_base:
                    velha = notas_base[pares[ident]]
                    if _texto_chave(dados_base, velha) != _texto_chave(dados_limpa, no):
                        self.relatorio["notas"]["alteradas"] += 1  # type: ignore[index]
                        partes.append(
                            dados_limpa[no.start : no.stag_end]
                            + self.emitir_itens(_itens(dados_base, velha), _itens(dados_limpa, no))
                            + b"</w:%s>" % tipo.encode()
                        )
                        continue
                elif ident in inseridas:
                    self.relatorio["notas"]["inseridas"] += 1  # type: ignore[index]
                    miolo = b"".join(
                        self._paragrafo_inteiro(_analisar_paragrafo(dados_limpa, c), "ins", marcar=False)
                        if c.tag == "w:p"
                        else _bruto(dados_limpa, c)
                        for c in no.children
                    )
                    partes.append(dados_limpa[no.start : no.stag_end] + miolo + b"</w:%s>" % tipo.encode())
                    continue
                partes.append(_bruto(dados_limpa, no))
            partes.extend(self._copias_excluidas(tipo))
            partes.append(dados_limpa[posicao:])
            return b"".join(partes)
        finally:
            self._em_nota = False

    def _copias_excluidas(self, tipo: str) -> list[bytes]:
        info = self._notas[tipo]
        base_info, copias = info["base"], info["copias"]
        assert isinstance(base_info, dict) and isinstance(copias, dict)
        dados = base_info["data"]
        saida = []
        for id_base, id_novo in copias.items():
            no = base_info["notas"].get(id_base)
            if no is None:
                self.avisos.append(f"nota {tipo} {id_base} da base não encontrada")
                continue
            self.relatorio["notas"]["excluidas"] += 1  # type: ignore[index]
            stag = _ID_ATTR.sub(b'w:id="%s"' % id_novo.encode(), dados[no.start : no.stag_end], count=1)
            miolo = b"".join(
                self._paragrafo_inteiro(_analisar_paragrafo(dados, c), "del", marcar=False)
                if c.tag == "w:p"
                else _bruto(dados, c)
                for c in no.children
            )
            saida.append(stag + miolo + b"</w:%s>" % tipo.encode())
        return saida


def _garantir_parte_notas(pacote: dict[str, bytes], tipo: str) -> None:
    """Registra ``word/{tipo}s.xml`` em [Content_Types] e nas relações do documento."""

    nome = f"word/{tipo}s.xml"
    tipos = pacote["[Content_Types].xml"]
    if f'PartName="/{nome}"'.encode() not in tipos:
        tipos = tipos.replace(
            b"</Types>",
            b'<Override PartName="/%s" ContentType="application/vnd.openxmlformats-officedocument.'
            b'wordprocessingml.%ss+xml"/></Types>' % (nome.encode(), tipo.encode()),
        )
        pacote["[Content_Types].xml"] = tipos
    rels_nome = "word/_rels/document.xml.rels"
    rels = pacote.get(rels_nome, b"")
    if f'Target="{tipo}s.xml"'.encode() not in rels:
        rels = rels.replace(
            b"</Relationships>",
            b'<Relationship Id="rIdNativo%ss" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/%ss" Target="%ss.xml"/></Relationships>' % (tipo.encode(), tipo.encode(), tipo.encode()),
        )
        pacote[rels_nome] = rels


def comparar_nativo(
    base: Path,
    limpa: Path,
    saida: Path,
    autor: str,
    data: str,
    detectar_formatacao: bool = False,
) -> dict[str, object]:
    """Gera ``saida`` (DOCX com marcas) a partir de ``base`` e ``limpa``.

    Devolve o relatório do motor (contagens, substituições inteiras, avisos).
    Não confere a integridade; use ``integridade_docx.conferir`` em seguida.
    """

    with zipfile.ZipFile(base) as arquivo:
        pacote_base = {nome: arquivo.read(nome) for nome in arquivo.namelist()}
    with zipfile.ZipFile(limpa) as arquivo:
        infos = arquivo.infolist()
        pacote = {info.filename: arquivo.read(info.filename) for info in infos}
    motor = _MotorNativo(pacote_base, pacote, autor, data, detectar_formatacao)
    pacote["word/document.xml"] = motor.documento()
    for tipo in ("footnote", "endnote"):
        conteudo = motor.notas(tipo)
        if conteudo is None:
            continue
        nome = f"word/{tipo}s.xml"
        if nome not in pacote:
            _garantir_parte_notas(pacote, tipo)
            motor.avisos.append(f"{nome} criado para abrigar notas excluídas da base")
        pacote[nome] = conteudo
    partes_base = {n for n in pacote_base if re.match(r"word/(header|footer)\d*\.xml$", n)}
    for nome in sorted(partes_base | {n for n in pacote if re.match(r"word/(header|footer)\d*\.xml$", n)}):
        if pacote_base.get(nome) != pacote.get(nome):
            texto_base = _texto_chave(pacote_base[nome], _arvore(pacote_base[nome])) if nome in pacote_base else ""
            texto_limpa = _texto_chave(pacote[nome], _arvore(pacote[nome])) if nome in pacote else ""
            if texto_base != texto_limpa:
                motor.avisos.append(f"{nome} difere entre base e limpa e não foi marcado (vale o da limpa)")
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as destino:
        nomes = [info.filename for info in infos]
        for nome in nomes + sorted(set(pacote) - set(nomes)):
            destino.writestr(nome, pacote[nome], compress_type=zipfile.ZIP_DEFLATED)
    relatorio = dict(motor.relatorio)
    relatorio["avisos"] = sorted(set(motor.avisos))
    return relatorio


def normalizar_data(valor: str | None) -> str:
    """Data das revisões em ISO 8601 UTC (``AAAA-MM-DDTHH:MM:SSZ``)."""

    if not valor:
        return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        momento = dt.datetime.fromisoformat(valor.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise RedlineError("--data deve estar em ISO 8601 (AAAA-MM-DD ou AAAA-MM-DDTHH:MM:SSZ)") from exc
    if momento.tzinfo is None:
        momento = momento.replace(tzinfo=dt.timezone.utc)
    return momento.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolver_motor(motor: str) -> tuple[str, list[str]]:
    """Traduz ``auto|docxodus|nativo`` no motor efetivo, com avisos."""

    if motor not in {"auto", "docxodus", "nativo"}:
        raise RedlineError(f"motor desconhecido: {motor}")
    if motor == "nativo":
        return "nativo", []
    if motor == "docxodus":
        _require_redline_engine()
        return "docxodus", []
    if docxodus_disponivel():
        return "docxodus", []
    return "nativo", [
        "Docxodus (python-redlines) indisponível neste ambiente; usado o motor nativo "
        "(diff por palavra, divisões e fusões de parágrafo). Revise o comparativo no Word antes de circular."
    ]


def _integridade():
    try:
        import integridade_docx  # type: ignore[import-not-found]
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import integridade_docx  # type: ignore[import-not-found,no-redef]
    return integridade_docx


def _generate_native(
    *,
    base: Path,
    current: Path,
    output: Path,
    author: str,
    comparison: str,
    date: str,
    manifest_path: Path | None,
    detect_format_changes: bool,
    force: bool,
    motor: str,
    avisos: list[str],
    divididos: int | None,
    fundidos: int | None,
) -> dict[str, object]:
    base = validate_clean_input(base, "versão-base")
    current = validate_clean_input(current, "versão corrente")
    output = output.expanduser().resolve()
    if output in {base, current}:
        raise RedlineError("o redline não pode sobrescrever a base nem o canônico limpo")
    if output.exists() and not force:
        raise RedlineError(f"saída já existe; use --force para substituir: {output}")
    if not author.strip():
        raise RedlineError("autor do redline não pode ser vazio")
    integridade = _integridade()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="word-redline-nativo-") as temp_dir_name:
        redline_temp = Path(temp_dir_name) / "comparison.docx"
        relatorio = comparar_nativo(base, current, redline_temp, author.strip(), date, detect_format_changes)
        ensure_docx_valid(redline_temp)
        resultado = integridade.conferir(base, current, redline_temp, divididos, fundidos)
        if not resultado["ok"]:
            raise RedlineError(
                "a conferência de integridade do redline nativo falhou:\n" + integridade.formatar(resultado)
            )
        _atomic_copy(redline_temp, output, force=force)

    avisos = avisos + list(relatorio.pop("avisos", []))  # type: ignore[arg-type]
    avisos += [f"integridade: {aviso}" for aviso in resultado.get("avisos", [])]  # type: ignore[union-attr]
    for aviso in avisos:
        print(f"aviso: {aviso}", file=sys.stderr)
    payload: dict[str, object] = {
        "contract": "legal_word_redline_v1",
        "generated_at": utc_now(),
        "comparison": comparison,
        "author": author.strip(),
        "revision_date": date,
        "engine": {
            "name": "nativo_diff_por_palavra",
            "requested": motor,
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
            "scope": "texto_visivel_corpo_tabelas_notas_referenciadas",
            "integridade": {
                "ok": resultado["ok"],
                "contagens": resultado["contagens"],
                "verificacoes": [
                    {"nome": item["nome"], "ok": item["ok"]} for item in resultado["verificacoes"]  # type: ignore[union-attr]
                ],
            },
        },
        "relatorio": relatorio,
        "avisos": avisos,
        "governance": {
            "approval_attaches_to": "canonical_clean.sha256",
            "redline_is_canonical": False,
            "manual_resolution_creates_new_version": True,
        },
    }
    if manifest_path is not None:
        _write_json(manifest_path.expanduser().resolve(), payload, force=force)
    return payload


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
    motor: str = "auto",
    date: str | None = None,
    divididos: int | None = None,
    fundidos: int | None = None,
) -> dict[str, object]:
    """Gera o redline ``base`` → ``current`` com o motor escolhido."""

    efetivo, avisos = resolver_motor(motor)
    if efetivo == "nativo":
        return _generate_native(
            base=base,
            current=current,
            output=output,
            author=author,
            comparison=comparison,
            date=normalizar_data(date),
            manifest_path=manifest_path,
            detect_format_changes=detect_format_changes,
            force=force,
            motor=motor,
            avisos=avisos,
            divididos=divididos,
            fundidos=fundidos,
        )
    payload = _generate_docxodus(
        base=base,
        current=current,
        output=output,
        author=author,
        comparison=comparison,
        manifest_path=None,
        detect_format_changes=detect_format_changes,
        force=force,
    )
    payload["avisos"] = list(avisos)
    if date:
        payload["avisos"].append("--data é ignorada pelo Docxodus (o comparador grava a própria data)")  # type: ignore[union-attr]
    # Conferência adicional apenas informativa: o gate do Docxodus continua
    # sendo a verificação bidirecional por hash textual acima.
    try:
        resultado = _integridade().conferir(base, current, output, divididos, fundidos)
        payload["integridade_informativa"] = {"ok": resultado["ok"], "contagens": resultado["contagens"]}
        if not resultado["ok"]:
            payload["avisos"].append("integridade_docx apontou divergência (informativo no Docxodus)")  # type: ignore[union-attr]
    except Exception as exc:  # pragma: no cover - diagnóstico apenas
        payload["integridade_informativa"] = {"erro": str(exc)}
    if manifest_path is not None:
        _write_json(manifest_path.expanduser().resolve(), payload, force=force)
    return payload


def _generate_docxodus(
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
    motor: str = "auto",
    date: str | None = None,
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
        motor=motor,
        date=date,
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
            motor=motor,
            date=date,
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
        "engine": cumulative.get("engine"),
        "avisos": sorted(
            set(cumulative.get("avisos", [])) | set(incremental.get("avisos", []) if incremental else [])  # type: ignore[arg-type]
        ),
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
    report_lines.append(f"- Motor: `{cumulative['engine']['name']}` (solicitado: `{motor}`)")  # type: ignore[index]
    for aviso in payload["avisos"]:  # type: ignore[union-attr]
        report_lines.append(f"- Aviso: {aviso}")
    for rotulo, resultado in (("acumulado", cumulative), ("incremental", incremental)):
        relatorio = resultado.get("relatorio") if resultado else None
        if not relatorio:
            continue
        report_lines.append(
            f"- Motor nativo ({rotulo}): {relatorio['alterados_por_palavra']} parágrafo(s) com diff por palavra, "
            f"{relatorio['divisoes']} divisão(ões), {relatorio['fusoes']} fusão(ões), "
            f"{relatorio['inseridos']} inserido(s), {relatorio['excluidos']} excluído(s), "
            f"{len(relatorio['substituidos_inteiros'])} substituído(s) inteiro(s)"
        )
        for item in relatorio["substituidos_inteiros"]:
            report_lines.append(f"  - substituído inteiro ({item['motivo']}): «{item['trecho']}»")
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


def _add_motor_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--motor",
        choices=("auto", "docxodus", "nativo"),
        default="auto",
        help="auto (padrão): Docxodus se disponível, senão nativo (com aviso); "
        "nativo: diff por palavra embutido, com divisões/fusões e conferência de integridade",
    )
    parser.add_argument(
        "--data",
        help="data das revisões em ISO 8601 (ex.: 2026-11-04T21:00:00Z); padrão: agora (UTC); "
        "ignorada pelo Docxodus",
    )
    parser.add_argument(
        "--author",
        "--autor",
        dest="author",
        default="Redator responsável",
        help="autor gravado nas marcas de revisão",
    )
    parser.add_argument("--detect-format-changes", action="store_true", help="marca também mudanças de formatação")
    parser.add_argument("--force", action="store_true")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    doctor = sub.add_parser("doctor", help="verifica Docxodus, Microsoft Word e osascript")
    doctor.add_argument("--deep", action="store_true")

    inspect = sub.add_parser("inspect", help="inspeciona hash textual e revisões")
    inspect.add_argument("docx")

    compare = sub.add_parser(
        "compare",
        help="gera um redline nativo entre dois DOCX limpos",
        description="Compara a versão aprovada (--base, obrigatória e explícita) com a limpa corrente.",
    )
    compare.add_argument("--base", required=True, help="versão aprovada indicada pelo usuário (base do redline)")
    compare.add_argument("--current", "--limpa", dest="current", required=True, help="versão limpa corrente")
    compare.add_argument("--out", "--saida", dest="out", required=True, help="DOCX com alterações controladas")
    compare.add_argument("--manifest")
    compare.add_argument("--comparison", default="incremental")
    compare.add_argument("--divididos", type=int, help="parágrafos acrescidos por divisão (confere a contagem)")
    compare.add_argument("--fundidos", type=int, help="parágrafos absorvidos por fusão (confere a contagem)")
    _add_motor_args(compare)

    finalize = sub.add_parser("finalize", help="publica minuta limpa e redlines finais")
    finalize.add_argument("--first", required=True)
    finalize.add_argument("--final", required=True)
    finalize.add_argument("--previous")
    finalize.add_argument("--original")
    finalize.add_argument("--base-policy", choices=("first", "original"), default="first")
    finalize.add_argument("--out-dir", required=True)
    finalize.add_argument("--stem", default="minuta")
    _add_motor_args(finalize)
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
                motor=args.motor,
                date=args.data,
                divididos=args.divididos,
                fundidos=args.fundidos,
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
            motor=args.motor,
            date=args.data,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    except (RedlineError, subprocess.TimeoutExpired, _integridade().IntegridadeErro) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
