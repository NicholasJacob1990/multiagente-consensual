#!/usr/bin/env python3
"""Testes do texto com "§N" explícito: ``docx_para_md.py --prefixo-paragrafo`` e ``pacote_auditoria.py montar --numerado``.

    python3 -m unittest test_pacote_numerado -v

Usa .docx sintético mínimo (zipfile + XML), com o §1 começando por rótulo em negrito
("Resposta objetiva."), o caso que deslocou a numeração de um auditor externo em −1.
"""

from __future__ import annotations

import hashlib
import io
import re
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docx_para_md as dm  # noqa: E402
import pacote_auditoria as pa  # noqa: E402
import parecer_md as pm  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NUMBERING = f"""<w:numbering xmlns:w="{W_NS}">
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2)"/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="3"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="3"/></w:num>
</w:numbering>"""


def r(texto: str, negrito: bool = False) -> str:
    return f'<w:r>{"<w:rPr><w:b/></w:rPr>" if negrito else ""}<w:t xml:space="preserve">{texto}</w:t></w:r>'


def p(*runs: str, num: str | None = None, ilvl: int = 0) -> str:
    ppr = f'<w:pPr><w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num}"/></w:numPr></w:pPr>' if num else ""
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


CORPO = "".join([
    p(r("PARECER", negrito=True)),
    p(r("I. Identificação")),
    p(r("Resposta objetiva.", negrito=True), r(" Não se deve dar baixa nos lotes agora."), num="1"),
    p(r("A enfiteuse de 1971 cedeu o domínio útil à Gama."), num="1"),
    p(r("subitem do corpo"), num="1", ilvl=1),
    p(r("Como antecipado no parágrafo 1, nada se baixa agora."), num="1"),
    p(r("Diligência: certidão integral."), num="3"),
    p(r("Lista do anexo, item um."), num="2"),
    p(r("Lista do anexo, item dois."), num="2"),
])


def montar_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{CORPO}</w:body></w:document>')
        z.writestr("word/numbering.xml", NUMBERING)


def calado(fn, *args) -> tuple[int, str]:
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(io.StringIO()):
        cod = fn(*args)
    return cod, out.getvalue()


class PrefixoParagrafoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.docx = self.dir / "parecer_v1.docx"
        montar_docx(self.docx)
        self.sha = hashlib.sha256(self.docx.read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def test_prefixo_paragrafo_e_cabecalho(self):
        linhas = [l for l in dm.converter(self.docx, prefixo_paragrafo=True).split("\n") if l]
        self.assertEqual(linhas, [
            f"<!-- origem: parecer_v1.docx | sha256: {self.sha} -->",
            "**PARECER**",
            "## I. Identificação",
            "§1 **Resposta objetiva.** Não se deve dar baixa nos lotes agora.",
            "§2 A enfiteuse de 1971 cedeu o domínio útil à Gama.",
            "a) subitem do corpo",
            "§3 Como antecipado no parágrafo 1, nada se baixa agora.",
            "- Diligência: certidão integral.",
            "1. Lista do anexo, item um.",
            "2. Lista do anexo, item dois.",
        ])

    def test_modo_padrao_inalterado(self):
        md = dm.converter(self.docx)
        self.assertNotIn("<!-- origem", md)
        self.assertNotIn("§", md)
        self.assertIn("1. **Resposta objetiva.** Não se deve dar baixa nos lotes agora.", md)
        self.assertIn("3. Como antecipado no parágrafo 1, nada se baixa agora.", md)

    def test_cli_prefixo(self):
        saida = self.dir / "n.md"
        cod, out = calado(dm.main, [str(self.docx), str(saida), "--prefixo-paragrafo"])
        self.assertEqual(cod, 0)
        self.assertIn("3 parágrafos do corpo com §N", out)
        self.assertTrue(saida.read_text(encoding="utf-8").startswith("<!-- origem: parecer_v1.docx | sha256: "))

    def test_paragrafos_marca_o_corpo(self):
        corpo = [(x.numero, x.plano[:20]) for x in dm.paragrafos(self.docx) if x.corpo]
        self.assertEqual([n for n, _ in corpo], [1, 2, 3])
        self.assertTrue(corpo[0][1].startswith("Resposta objetiva."))


class PacoteNumeradoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.docx = self.dir / "parecer_v1.docx"
        montar_docx(self.docx)
        self.sha = hashlib.sha256(self.docx.read_bytes()).hexdigest()
        self.minuta = self.dir / "v1.md"
        self.minuta.write_text(dm.converter(self.docx), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def montar(self, *extra: str) -> tuple[int, str, str]:
        saida = self.dir / "pacote.md"
        cod, out = calado(pa.main, ["montar", *extra, "--saida", str(saida)])
        return cod, out, saida.read_text(encoding="utf-8") if saida.exists() else ""

    def test_pacote_com_numerado(self):
        cod, out, texto = self.montar("--minuta", str(self.minuta), "--numerado", str(self.docx))
        self.assertEqual(cod, 0)
        self.assertIn(f"SHA-256 do DOCX: {self.sha}", texto)
        self.assertEqual(pa.hash_docx_do_pacote(texto), self.sha)
        self.assertIn("Cite os parágrafos pelo número §N deste arquivo e repita o SHA-256 do DOCX auditado", texto)
        self.assertIn(f"`HASH_DOCX: {self.sha}`", texto)
        self.assertIn("===== INÍCIO: MINUTA (sha256", texto)
        self.assertIn("===== INÍCIO: TEXTO NUMERADO DO DOCX (§N)", texto)
        self.assertIn(f"<!-- origem: parecer_v1.docx | sha256: {self.sha} -->", texto)
        self.assertIn("§1 **Resposta objetiva.**", texto)
        self.assertEqual(pa.hash_do_pacote(texto), pm.ler(self.minuta).sha256)
        self.assertIn(f"hash do DOCX numerado {self.sha}", out)

    def test_so_numerado_uma_copia(self):
        cod, _, texto = self.montar("--numerado", str(self.docx))
        self.assertEqual(cod, 0)
        self.assertEqual(texto.count("§1 **Resposta objetiva.**"), 1)
        self.assertNotIn("INÍCIO: MINUTA (sha256", texto)
        m = re.search(r"INÍCIO: MINUTA — TEXTO NUMERADO DO DOCX \(§N\) \(sha256 ([0-9a-f]{64})\)", texto)
        self.assertIsNotNone(m)
        self.assertEqual(pa.hash_do_pacote(texto), m.group(1))

    def test_sem_numerado_retrocompativel(self):
        cod, _, texto = self.montar("--minuta", str(self.minuta))
        self.assertEqual(cod, 0)
        self.assertNotIn("DOCX", texto)
        self.assertEqual(texto, pa.montar(self.minuta, pa.INSTRUCOES_PADRAO))
        self.assertEqual(calado(pa.main, ["montar", "--saida", str(self.dir / "x.md")])[0], 2)

    def test_aviso_de_versao_diferente(self):
        outra = self.dir / "outra.md"
        outra.write_text("1. Um.\n\n2. Dois.\n\n3. Três.\n\n4. Quatro.\n", encoding="utf-8")
        _, out, _ = self.montar("--minuta", str(outra), "--numerado", str(self.docx))
        self.assertIn("a minuta tem 4 parágrafos numerados e o corpo do DOCX numerado tem 3", out)

    def test_verificar_hash_do_docx(self):
        _, _, texto = self.montar("--numerado", str(self.docx))
        pacote = self.dir / "pacote.md"
        h = pa.hash_do_pacote(texto)
        corpo = ("Decisão: aprovado com ressalvas. " + "O §3 remete corretamente ao §1, que traz a resposta objetiva. " * 4)
        resp = self.dir / "resp.md"

        def verificar(linhas: list[str], *extra: str) -> tuple[int, str]:
            resp.write_text("\n".join(linhas + ["", corpo]), encoding="utf-8")
            return calado(pa.main, ["verificar", "--pacote", str(pacote), "--resposta", str(resp), *extra])

        cod, out = verificar([f"HASH_RECEBIDO: {h}", f"HASH_DOCX: {self.sha}"])
        self.assertEqual(cod, 0, out)
        self.assertIn("DOCX numerado: hash do DOCX confere", out)
        cod, out = verificar([f"HASH_RECEBIDO: {h}", f"HASH_DOCX: {'9b2c0e20' + '0' * 50 + 'e466e5'}"])
        self.assertEqual(cod, 1)
        self.assertIn("o auditor leu outra cópia", out)
        cod, out = verificar([f"HASH_RECEBIDO: {h}"])
        self.assertEqual(cod, 1)
        self.assertIn("sem HASH_DOCX", out)
        self.assertEqual(verificar([f"HASH_RECEBIDO: {h}"], "--docx-opcional")[0], 0)


if __name__ == "__main__":
    unittest.main()
