#!/usr/bin/env python3
"""Testes de docx_para_md.py com .docx sintético: numeração por numId, rótulos, títulos, alterações e notas.

    python3 -m unittest test_docx_para_md -v

O teste com o caso real só roda com ``FIXTURES_FASE2=/caminho`` (v16.docx).
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import docx_para_md as dm
import parecer_md as pm
import pre_auditoria_parecer as pa

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

NUMBERING = f"""<w:numbering xmlns:w="{W_NS}">
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl>
<w:lvl w:ilvl="1"><w:start w:val="1"/><w:numFmt w:val="lowerLetter"/><w:lvlText w:val="%2)"/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="2"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="3"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="4"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="upperRoman"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="2"><w:abstractNumId w:val="2"/></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="3"/></w:num>
<w:num w:numId="4"><w:abstractNumId w:val="4"/></w:num>
<w:num w:numId="5"><w:abstractNumId w:val="2"/><w:lvlOverride w:ilvl="0"><w:startOverride w:val="7"/></w:lvlOverride></w:num>
</w:numbering>"""

STYLES = f"""<w:styles xmlns:w="{W_NS}">
<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Ttulo1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="TituloNumerado"><w:name w:val="Secao"/><w:pPr><w:numPr><w:numId w:val="4"/></w:numPr><w:outlineLvl w:val="0"/></w:pPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/></w:style>
<w:style w:type="character" w:styleId="Forte"><w:name w:val="Strong"/><w:rPr><w:b/></w:rPr></w:style>
</w:styles>"""


def r(texto: str, negrito: bool = False, estilo: str | None = None) -> str:
    rpr = ""
    if negrito or estilo:
        rpr = "<w:rPr>" + (f'<w:rStyle w:val="{estilo}"/>' if estilo else "") + ("<w:b/>" if negrito else "") + "</w:rPr>"
    return f'<w:r>{rpr}<w:t xml:space="preserve">{texto}</w:t></w:r>'


def p(*runs: str, num: str | None = None, ilvl: int = 0, estilo: str | None = None) -> str:
    ppr = ""
    if num or estilo:
        ppr = "<w:pPr>" + (f'<w:pStyle w:val="{estilo}"/>' if estilo else "")
        if num:
            ppr += f'<w:numPr><w:ilvl w:val="{ilvl}"/><w:numId w:val="{num}"/></w:numPr>'
        ppr += "</w:pPr>"
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def montar(path: Path, corpo: str, notas: str | None = None) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')
        z.writestr("word/numbering.xml", NUMBERING)
        z.writestr("word/styles.xml", STYLES)
        if notas is not None:
            z.writestr("word/footnotes.xml", f'<w:footnotes xmlns:w="{W_NS}">'
                       '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                       f"{notas}</w:footnotes>")


class ConversaoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def converter(self, corpo: str, notas: str | None = None) -> list[str]:
        f = self.dir / "t.docx"
        montar(f, corpo, notas)
        return [l for l in dm.converter(f).split("\n") if l]

    def test_numeracao_por_numid_e_niveis(self):
        linhas = self.converter(
            p(r("Primeiro."), num="1") + p(r("Lista do anexo."), num="2") + p(r("Segundo."), num="1")
            + p(r("subitem"), num="1", ilvl=1) + p(r("outro subitem"), num="1", ilvl=1) + p(r("Terceiro."), num="1")
            + p(r("vazio não conta"), num="0") + p(r("marcador"), num="3") + p(r("começa em sete"), num="5")
            + p(num="1") + p(r("Quarto."), num="1"))
        self.assertEqual(linhas, ["1. Primeiro.", "1. Lista do anexo.", "2. Segundo.", "a) subitem", "b) outro subitem",
                                  "3. Terceiro.", "vazio não conta", "- marcador", "7. começa em sete", "4. Quarto."])

    def test_rotulo_em_negrito_e_titulos(self):
        linhas = self.converter(
            p(r("PARECER", negrito=True), estilo="Title")
            + p(r("Identificação"), estilo="Ttulo1")
            + p(r("Exame do quesito"), estilo="TituloNumerado")
            + p(r("VIII. Conclusão e encaminhamentos"))
            + p(r("Correções necessárias.", negrito=True), r(" ", negrito=True), r("Pedir certidões."), num="1")
            + p(r("Rótulo por estilo.", estilo="Forte"), r(" Texto."), num="1")
            + p(r("Meio "), r("negrito", negrito=True), r(" não vira rótulo."), num="1"))
        self.assertEqual(linhas, [
            "**PARECER**",
            "## Identificação",
            "## I. Exame do quesito",
            "## VIII. Conclusão e encaminhamentos",
            "1. **Correções necessárias.** Pedir certidões.",
            "2. **Rótulo por estilo.** Texto.",
            "3. Meio negrito não vira rótulo.",
        ])

    def test_alteracoes_controladas(self):
        linhas = self.converter(
            p(r("Texto "), f'<w:del w:id="1" w:author="A"><w:r><w:delText>apagado </w:delText></w:r></w:del>',
              f'<w:ins w:id="2" w:author="A">{r("inserido ")}</w:ins>', r("fim."), num="1")
            # parágrafo cuja marca foi excluída junta-se ao seguinte
            + '<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr><w:rPr><w:del w:id="3" w:author="A"/></w:rPr></w:pPr>'
            + r("Começo ") + "</w:p>" + p(r("e continuação."), num="1")
            + p(f'<w:del w:id="4" w:author="A"><w:r><w:delText>parágrafo todo excluído</w:delText></w:r></w:del>', num="1")
            + p(r("Último."), num="1"))
        self.assertEqual(linhas, ["1. Texto inserido fim.", "2. Começo e continuação.", "3. Último."])

    def test_notas_de_rodape(self):
        nota = ('<w:footnote w:id="5"><w:p><w:r><w:footnoteRef/></w:r>'
                + r(" LOUREIRO, 2019, comentário ao art. 243.") + "</w:p></w:footnote>")
        linhas = self.converter(p(r("Doutrina"), '<w:r><w:footnoteReference w:id="5"/></w:r>', r(" ampara."), num="1"), nota)
        self.assertEqual(linhas, ["1. Doutrina[^1] ampara.", "[^1]: LOUREIRO, 2019, comentário ao art. 243."])

    def test_pre_auditoria_reconhece_rotulos_da_conclusao(self):
        corpo = (p(r("I. Exame")) + p(r("Primeiro parágrafo do exame."), num="1")
                 + p(r("VIII. Conclusão")) +
                 "".join(p(r(f"{rot}.", negrito=True), r(" Texto da conclusão."), num="1") for rot in (
                     "Correções necessárias", "Obrigações já incidentes", "Recomendações facultativas",
                     "Providências a cargo de outros órgãos"))
                 + p(r("É o parecer, sob censura."), num="1"))
        f, md = self.dir / "c.docx", self.dir / "c.md"
        montar(f, corpo)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(dm.main([str(f), str(md)]), 0)
        achados = pa.checar_conclusao(pm.ler(md), pa.PERFIS["genes"]["rotulos_conclusao"])
        self.assertEqual(achados, [])
        self.assertIn("6. É o parecer, sob censura.", md.read_text(encoding="utf-8"))

    def test_erro_de_leitura(self):
        ruim = self.dir / "ruim.docx"
        ruim.write_text("não é zip", encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            self.assertEqual(dm.main([str(ruim), str(self.dir / "x.md")]), 2)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE2"), "defina FIXTURES_FASE2 para rodar com o caso real")
class CasoRealTests(unittest.TestCase):
    def test_v16_rotulos_reconhecidos(self):
        f = Path(os.environ["FIXTURES_FASE2"]) / "v16.docx"
        d = pm.parse(dm.converter(f))
        self.assertEqual(pa.checar_conclusao(d, pa.PERFIS["genes"]["rotulos_conclusao"]), [])
        self.assertEqual(len(pa.corpo_numerado(d)), 127)


if __name__ == "__main__":
    unittest.main()
