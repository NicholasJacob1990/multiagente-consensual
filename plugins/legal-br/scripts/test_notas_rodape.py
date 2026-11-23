#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes das notas de rodapé ([^id] no .md -> nota real no .docx) em
parecer_docx.py (converter, nota) e parecer_genes_estilo.py.

    python3 -m unittest -v test_notas_rodape          (na pasta scripts/)

Validação OOXML e renderização são feitas quando disponíveis:
  validador: $DOCX_VALIDATE ou /mnt/skills/public/docx/scripts/office/validate.py
  render:    soffice (LibreOffice) + pdftotext
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import parecer_docx as pd  # noqa: E402

VALIDADOR = Path(os.environ.get("DOCX_VALIDATE",
                                "/mnt/skills/public/docx/scripts/office/validate.py"))
TEM_DOCX = pd.docx is not None
TEM_PANDOC = shutil.which("pandoc") is not None
TEM_RENDER = shutil.which("soffice") is not None and shutil.which("pdftotext") is not None

NOTA1 = "Explicação lateral sobre o cômputo do prazo, com *itálico* e **negrito**."
NOTA2 = "Segunda nota, com linha de continuação recuada."

MD_GENES = f"""\
@CAB PARECER JURÍDICO Nº 00/2026
@CAB Processo|0000.00.0000000/2026-00
@EMENTA EMENTA:|Ementa fictícia para teste de notas.
## I. RELATÓRIO
1. Primeiro parágrafo com nota explicativa[^prazo] e texto depois da nota.

[^prazo]: {NOTA1}

2. Segundo parágrafo, **trecho em negrito**[^seg], fim.
@TXT É o parecer.
[^seg]: Segunda nota, com linha
    de continuação recuada.
"""

MD_PANDOC = f"""\
PARECER Nº 00/2026

EMENTA: Ementa fictícia.

I — RELATÓRIO

Parágrafo de corpo com nota[^a] no meio e *ênfase*[^b].

[^b]: {NOTA2}

Outro parágrafo, sem nota.

[^a]: {NOTA1}
"""


def _partes(docx_path):
    with zipfile.ZipFile(docx_path) as z:
        return {n: z.read(n).decode("utf-8", "replace") for n in z.namelist()
                if n.endswith((".xml", ".rels"))}


def _validar(docx_path, original=None):
    cmd = [sys.executable, str(VALIDADOR), str(docx_path)]
    if original:
        cmd += ["--original", str(original)]
    return subprocess.run(cmd, capture_output=True, text=True, cwd=str(VALIDADOR.parent))


def _pdf_texto(docx_path, pasta):
    subprocess.run(["soffice", "--headless", "--convert-to", "pdf", "--outdir", str(pasta),
                    str(docx_path)], capture_output=True, timeout=180, check=True)
    pdf = Path(pasta) / (Path(docx_path).stem + ".pdf")
    return subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True,
                          text=True, check=True).stdout


class TestExtrairNotasMd(unittest.TestCase):
    def test_ordem_pelo_primeiro_marcador_e_definicao_em_qualquer_lugar(self):
        md = "[^z]: Nota Z.\nTexto[^b] e[^z].\n\n[^b]: Nota B\n    continua.\n"
        texto, notas = pd.extrair_notas_md(md)
        self.assertEqual(notas, ["Nota B continua.", "Nota Z."])
        self.assertEqual(texto.strip(), f"Texto{pd.token_nota(1)} e{pd.token_nota(2)}.")
        self.assertNotIn("[^", texto)

    def test_sem_notas_nao_altera(self):
        md = "Parágrafo (SILVA, 2020, p. 10) sem nota.\n"
        self.assertEqual(pd.extrair_notas_md(md), (md, []))

    def test_cerca_de_codigo_ignorada(self):
        md = "```\nx[^a]\n[^a]: não é nota\n```\n"
        self.assertEqual(pd.extrair_notas_md(md), (md, []))

    def test_erros(self):
        with self.assertRaises(pd.NotaErro):
            pd.extrair_notas_md("Texto[^x].\n")                       # sem definição
        with self.assertRaises(pd.NotaErro):
            pd.extrair_notas_md("T[^x].\n[^x]: a\n[^x]: b\n")         # definição dupla
        with self.assertRaises(pd.NotaErro):
            pd.extrair_notas_md("T[^x] e[^x].\n[^x]: a\n")            # reutilizada


class _Base(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dir = Path(self.td.name)

    def tearDown(self):
        self.td.cleanup()

    def conferir_pacote(self, docx_path, n_notas):
        p = _partes(docx_path)
        fn = p["word/footnotes.xml"]
        self.assertRegex(fn, r'<w:footnote w:type="separator" w:id="-1"')
        self.assertRegex(fn, r'<w:footnote w:type="continuationSeparator" w:id="0"')
        ids = [int(i) for i in re.findall(r'<w:footnote w:id="(\d+)"', fn)]
        self.assertEqual(len(ids), n_notas)
        # nota: 10 pt, recuo 0, espaçamento simples
        for bloco in re.findall(r'<w:footnote w:id="\d+">.*?</w:footnote>', fn, re.S):
            self.assertIn('<w:ind w:left="0" w:right="0" w:firstLine="0"/>', bloco)
            self.assertIn('w:line="240" w:lineRule="auto"', bloco)
            self.assertIn('<w:sz w:val="20"/>', bloco)
            self.assertRegex(bloco, r'<w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/>')
        # referências no corpo, sobrescritas, uma por nota
        dx = p["word/document.xml"]
        refs = re.findall(r'<w:r><w:rPr>(?:(?!</w:rPr>).)*<w:vertAlign w:val="superscript"/>'
                          r'</w:rPr><w:footnoteReference w:id="(\d+)"/></w:r>', dx)
        self.assertEqual(sorted(int(r) for r in refs), sorted(ids))
        self.assertNotIn("ZQNOTA", dx)
        self.assertNotIn("[^", dx)
        # relação, content type e settings
        self.assertRegex(p["word/_rels/document.xml.rels"], r'relationships/footnotes" Target="footnotes.xml"')
        self.assertIn('PartName="/word/footnotes.xml"', p["[Content_Types].xml"])
        st = p["word/settings.xml"]
        self.assertRegex(st, r'<w:footnotePr><w:footnote w:id="-1"/><w:footnote w:id="0"/></w:footnotePr>')
        if "<w:compat" in st:
            self.assertLess(st.index("<w:footnotePr"), st.index("<w:compat"))
        return p


@unittest.skipUnless(TEM_DOCX, "python-docx ausente")
class TestGenes(_Base):
    def gerar(self, md, nome="g"):
        src, out = self.dir / f"{nome}.md", self.dir / f"{nome}.docx"
        src.write_text(md, encoding="utf-8")
        r = subprocess.run([sys.executable, str(AQUI / "parecer_genes_estilo.py"), str(src), str(out)],
                           capture_output=True, text=True)
        return r, out

    def test_duas_notas(self):
        r, out = self.gerar(MD_GENES)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("2 nota(s) de rodapé", r.stdout)
        p = self.conferir_pacote(out, 2)
        self.assertIn("Segunda nota, com linha de continuação recuada.", p["word/footnotes.xml"])
        self.assertIn("<w:i/>", p["word/footnotes.xml"])

    @unittest.skipUnless(VALIDADOR.exists(), "validador OOXML ausente")
    def test_valida_ooxml(self):
        _, out = self.gerar(MD_GENES)
        v = _validar(out)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)
        self.assertIn("PASSED", v.stdout)

    @unittest.skipUnless(TEM_RENDER, "soffice/pdftotext ausentes")
    def test_renderiza_texto_da_nota(self):
        _, out = self.gerar(MD_GENES)
        txt = re.sub(r"\s+", " ", _pdf_texto(out, self.dir))
        self.assertIn("Explicação lateral sobre o cômputo do prazo", txt)
        self.assertIn("Segunda nota, com linha de continuação recuada.", txt)

    def test_marcador_sem_definicao_falha(self):
        r, out = self.gerar("1. Texto[^x].\n", "erro")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("[^x]", r.stderr + r.stdout)

    def test_sem_notas_nao_cria_part(self):
        r, out = self.gerar("1. Texto (AUTOR, 2020, p. 1) sem nota.\n", "sem")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn("word/footnotes.xml", _partes(out))


@unittest.skipUnless(TEM_DOCX and TEM_PANDOC, "python-docx ou pandoc ausente")
class TestConverter(_Base):
    def converter(self, md, nome):
        src, out = self.dir / f"{nome}.md", self.dir / f"{nome}.docx"
        src.write_text(md, encoding="utf-8")
        r = subprocess.run([sys.executable, str(AQUI / "parecer_docx.py"), "converter",
                            str(src), str(out)], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        return out

    def test_duas_notas_no_padrao(self):
        out = self.converter(MD_PANDOC, "c")
        p = self.conferir_pacote(out, 2)
        fn = p["word/footnotes.xml"]
        self.assertLess(fn.index("Explicação lateral"), fn.index("Segunda nota"))  # ordem do corpo
        self.assertIn('w:ascii="Times New Roman"', fn)

    @unittest.skipUnless(VALIDADOR.exists(), "validador OOXML ausente")
    def test_notas_nao_acrescentam_erro_ooxml(self):
        # o .docx do pandoc já traz desvios de schema próprios; comparamos com a
        # mesma conversão sem notas para isolar o que as notas acrescentam
        sem = re.sub(r"^\[\^\w+\]:.*$", "", re.sub(r"\[\^\w+\]", "", MD_PANDOC), flags=re.M)
        base = self.converter(sem, "base")
        out = self.converter(MD_PANDOC, "c")
        v = _validar(out, original=base)
        self.assertEqual(v.returncode, 0, v.stdout + v.stderr)

    @unittest.skipUnless(TEM_RENDER, "soffice/pdftotext ausentes")
    def test_renderiza(self):
        out = self.converter(MD_PANDOC, "c")
        txt = re.sub(r"\s+", " ", _pdf_texto(out, self.dir))
        self.assertIn("Segunda nota, com linha de continuação recuada.", txt)


@unittest.skipUnless(TEM_DOCX, "python-docx ausente")
class TestSubcomandoNota(_Base):
    def test_cria_part_quando_ausente_e_acrescenta_depois(self):
        out = self.dir / "n.docx"
        d = pd.docx.Document()
        d.add_paragraph("Primeiro parágrafo.")
        d.add_paragraph("Segundo parágrafo.")
        d.save(out)
        cmd = [sys.executable, str(AQUI / "parecer_docx.py"), "nota", str(out)]
        r = subprocess.run(cmd + ["--par", "1", "--texto", "Nota avulsa um."],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"nota_id": 1', r.stdout)
        r = subprocess.run(cmd + ["--par", "0", "--texto", "Nota avulsa dois."],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('"nota_id": 2', r.stdout)
        self.conferir_pacote(out, 2)


if __name__ == "__main__":
    unittest.main()
