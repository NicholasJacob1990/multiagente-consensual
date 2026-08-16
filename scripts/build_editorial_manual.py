#!/usr/bin/env python3
"""Build the editorial DOCX manual from its canonical Markdown source."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


INK = RGBColor(31, 41, 55)
ACCENT = RGBColor(30, 64, 175)
MUTED = RGBColor(75, 85, 99)


def set_font(run, name: str, size: float, *, bold: bool | None = None) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    if bold is not None:
        run.bold = bold
    if run._element.get_or_add_rPr().rFonts is None:
        run._element.get_or_add_rPr().append(OxmlElement("w:rFonts"))
    fonts = run._element.get_or_add_rPr().rFonts
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(key), name)


def style_font(style, name: str, size: float, color: RGBColor = INK) -> None:
    style.font.name = name
    style.font.size = Pt(size)
    style.font.color.rgb = color
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.rFonts
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for key in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        fonts.set(qn(key), name)


def shade_cell(cell, fill: str) -> None:
    tc_pr = cell._tc.get_or_add_tcPr()
    shading = tc_pr.find(qn("w:shd"))
    if shading is None:
        shading = OxmlElement("w:shd")
        tc_pr.append(shading)
    shading.set(qn("w:fill"), fill)


def repeat_table_header(row) -> None:
    tr_pr = row._tr.get_or_add_trPr()
    if tr_pr.find(qn("w:tblHeader")) is not None:
        return
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    tr_pr.append(header)


def configure_styles(document: Document) -> None:
    styles = document.styles
    normal = styles["Normal"]
    style_font(normal, "Lato", 12)
    normal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    normal.paragraph_format.first_line_indent = Inches(0.42)
    normal.paragraph_format.line_spacing = 1.5
    normal.paragraph_format.space_after = Pt(6)

    heading_tokens = {
        "Title": (24, ACCENT, 0, 14, WD_ALIGN_PARAGRAPH.CENTER),
        "Subtitle": (13, MUTED, 0, 18, WD_ALIGN_PARAGRAPH.CENTER),
        "Heading 1": (18, ACCENT, 18, 8, WD_ALIGN_PARAGRAPH.LEFT),
        "Heading 2": (15, ACCENT, 14, 6, WD_ALIGN_PARAGRAPH.LEFT),
        "Heading 3": (13, MUTED, 11, 5, WD_ALIGN_PARAGRAPH.LEFT),
        "Heading 4": (12, MUTED, 9, 4, WD_ALIGN_PARAGRAPH.LEFT),
    }
    for name, (size, color, before, after, alignment) in heading_tokens.items():
        if name not in styles:
            continue
        style = styles[name]
        style_font(style, "Lato", size, color)
        style.font.bold = name != "Subtitle"
        fmt = style.paragraph_format
        fmt.alignment = alignment
        fmt.first_line_indent = Inches(0)
        fmt.line_spacing = 1.15
        fmt.space_before = Pt(before)
        fmt.space_after = Pt(after)
        fmt.keep_with_next = True

    for name in ("List Bullet", "List Bullet 2", "List Bullet 3", "List Number", "List Number 2", "List Number 3"):
        if name not in styles:
            continue
        style = styles[name]
        style_font(style, "Lato", 12)
        style.paragraph_format.first_line_indent = None
        style.paragraph_format.line_spacing = 1.5
        style.paragraph_format.space_after = Pt(4)

    for name in ("Caption", "Quote", "Intense Quote"):
        if name not in styles:
            continue
        style_font(styles[name], "Lato", 11, MUTED)
        styles[name].paragraph_format.first_line_indent = Inches(0)
        styles[name].paragraph_format.line_spacing = 1.3

    for name in ("Source Code", "Code Block"):
        if name not in styles:
            continue
        style = styles[name]
        style_font(style, "Lato", 10.5, INK)
        fmt = style.paragraph_format
        fmt.alignment = WD_ALIGN_PARAGRAPH.LEFT
        fmt.first_line_indent = Inches(0)
        fmt.left_indent = Inches(0.32)
        fmt.right_indent = Inches(0.12)
        fmt.line_spacing = 1.15
        fmt.space_before = Pt(4)
        fmt.space_after = Pt(7)
        ppr = style.element.get_or_add_pPr()
        for tag in ("w:pBdr", "w:shd"):
            element = ppr.find(qn(tag))
            if element is not None:
                ppr.remove(element)


def normalize_tables(document: Document) -> None:
    """Rebuild Pandoc tables so Word and LibreOffice share the same layout."""
    for original in list(document.tables):
        matrix = [[cell.text for cell in row.cells] for row in original.rows]
        if not matrix:
            continue
        column_count = max(len(row) for row in matrix)
        replacement = document.add_table(rows=len(matrix), cols=column_count)
        for row_index, values in enumerate(matrix):
            for column_index, value in enumerate(values):
                replacement.cell(row_index, column_index).text = value
        original._tbl.addprevious(replacement._tbl)
        original._element.getparent().remove(original._element)


def configure_document(document: Document) -> None:
    configure_styles(document)
    normalize_tables(document)
    for section in document.sections:
        section.top_margin = Inches(0.78)
        section.bottom_margin = Inches(0.72)
        section.left_margin = Inches(0.82)
        section.right_margin = Inches(0.82)
        section.header_distance = Inches(0.35)
        section.footer_distance = Inches(0.35)

    for paragraph in document.paragraphs:
        style_name = paragraph.style.name if paragraph.style else ""
        if style_name.startswith("Heading") or style_name in {"Title", "Subtitle", "Caption", "Quote", "Intense Quote"}:
            paragraph.paragraph_format.first_line_indent = Inches(0)
        elif style_name.startswith("List") or style_name in {"Source Code", "Code Block"}:
            paragraph.paragraph_format.first_line_indent = None
            if style_name in {"Source Code", "Code Block"}:
                ppr = paragraph._p.get_or_add_pPr()
                for tag in ("w:pBdr", "w:shd"):
                    element = ppr.find(qn(tag))
                    if element is not None:
                        ppr.remove(element)
        else:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            paragraph.paragraph_format.first_line_indent = Inches(0.42)
            paragraph.paragraph_format.line_spacing = 1.5
            paragraph.paragraph_format.space_after = Pt(6)
        for run in paragraph.runs:
            if style_name in {"Source Code", "Code Block"}:
                rpr = run._r.get_or_add_rPr()
                run_style = rpr.find(qn("w:rStyle"))
                if run_style is not None:
                    rpr.remove(run_style)
                set_font(run, "Lato", 10.5)
            elif run.font.name is None:
                set_font(run, "Lato", 12)

    for table in document.tables:
        table.style = "Table Grid"
        table.autofit = False
        column_count = len(table.columns)
        column_width = Inches(6.55 / max(column_count, 1))
        for column in table.columns:
            column.width = column_width
        if table.rows:
            repeat_table_header(table.rows[0])
            for cell in table.rows[0].cells:
                shade_cell(cell, "E8EEF8")
        for row_index, row in enumerate(table.rows):
            for cell in row.cells:
                cell.width = column_width
                cell.vertical_alignment = 1
                for paragraph in cell.paragraphs:
                    paragraph.paragraph_format.first_line_indent = Inches(0)
                    paragraph.paragraph_format.line_spacing = 1.15
                    paragraph.paragraph_format.space_after = Pt(3)
                    for run in paragraph.runs:
                        set_font(run, "Lato", 11, bold=True if row_index == 0 else None)

    max_width = Inches(6.55)
    max_height = Inches(8.35)
    for shape in document.inline_shapes:
        scale = min(max_width / shape.width, max_height / shape.height, 1.0)
        if scale < 1.0:
            shape.width = int(shape.width * scale)
            shape.height = int(shape.height * scale)

    # Keep the first section explicit and stable when Pandoc imports a reference file.
    if document.sections and document.sections[0].start_type != WD_SECTION.NEW_PAGE:
        document.sections[0].start_type = WD_SECTION.NEW_PAGE


def append_field(paragraph, instruction: str) -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    command = OxmlElement("w:instrText")
    command.set(qn("xml:space"), "preserve")
    command.text = instruction
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.extend((begin, command, separate, end))


def create_clean_reference(path: Path) -> None:
    document = Document()
    configure_document(document)
    for section in document.sections:
        header = section.header.paragraphs[0]
        header.text = "MANUAL MULTIAGENTE  •  REFERÊNCIA PRÁTICA"
        header.alignment = WD_ALIGN_PARAGRAPH.CENTER
        for run in header.runs:
            set_font(run, "Lato", 9, bold=True)
            run.font.color.rgb = MUTED

        footer = section.footer.paragraphs[0]
        footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
        prefix = footer.add_run("Edição 16  •  Agosto de 2026  •  Página ")
        set_font(prefix, "Lato", 9)
        prefix.font.color.rgb = MUTED
        append_field(footer, "PAGE")
    document.save(path)


def build(source: Path, reference: Path, output: Path, pandoc: str) -> None:
    source = source.resolve()
    reference = reference.resolve()
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="manual-editorial-") as raw:
        temporary = Path(raw) / "manual-pandoc.docx"
        clean_reference = Path(raw) / "reference.docx"
        create_clean_reference(clean_reference)
        subprocess.run(
            [
                pandoc,
                str(source),
                "--from=gfm",
                "--to=docx",
                f"--reference-doc={clean_reference}",
                f"--resource-path={source.parent}",
                "--metadata=title:Manual completo — Multiagente Consensual",
                f"--output={temporary}",
            ],
            check=True,
            cwd=source.parent,
        )
        document = Document(temporary)
        configure_document(document)
        staged = Path(raw) / output.name
        document.save(staged)
        os.replace(staged, output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--pandoc", default=shutil.which("pandoc") or "pandoc")
    args = parser.parse_args()
    build(args.source, args.reference, args.output, args.pandoc)


if __name__ == "__main__":
    main()
