#!/usr/bin/env python3
"""Testes de inventario_fatos.py em pares sintéticos de versões.

    python3 -m unittest test_inventario_fatos -v

O teste com o caso real só roda com ``FIXTURES_FASE2=/caminho`` (v15_chk.md e v16.md).
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import inventario_fatos as inv

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

ANTERIOR = """\
## I. Fatos

1. A escritura de 15 de janeiro de 1986 foi registrada em 1º de abril de 1986 na Matrícula nº 9.876 (SEI 100000001, pp. 35–36).

2. Os créditos somavam Cr$ 161.477.249,34, e a área era de 10.500,00 m² por lote (art. 2.038, § 1º, I, do Código Civil).

3. Como se viu no parágrafo 1 e nos parágrafos 2 a 4, a Lei nº 6.015/1973 rege o registro; o prazo é de 30 dias.

4. O R-9 e a AV-3 constam da transcrição nº 6.700, fls. 116, Livro 3-G; os lotes 03 a 08 ficaram de fora.
"""

NOVA = """\
## I. Fatos

1. A escritura de 15 de janeiro de 1986, registrada em 1º de abril daquele ano na Matrícula nº 9.876 (SEI 100000001, p. 35), menciona foro de Cr$ 2.683,80 em 1976.

2. Os créditos somavam Cr$ 161.477.249,34 e correspondiam a 64,73% do total; a área era de 10.500,00 m² por lote (art. 2.038, § 1º, I, do Código Civil).

3. A Lei nº 6.015/1973 rege o registro (parágrafos 7 e 9); o prazo é de 30 dias, e houve pagamentos em 1983–1987 e em 16/11/2022.

4. O R-9 e a AV-3 constam da transcrição nº 6.700, fls. 116, Livro 3-G; os lotes 03 a 08 ficaram de fora (pp. 36 e 40).
"""


def itens(texto: str) -> list[tuple[str, str]]:
    return [(i.categoria, i.literal) for i in inv.extrair_texto(texto, "x")]


class ExtracaoTests(unittest.TestCase):
    def test_categorias(self):
        got = itens("Em 14 de janeiro de 1971, pelo valor de R$ 1.234,56 (10%), com 2.683,80 m², conforme o art. 5º, "
                    "§ 2º, da Lei nº 8.666/1993 e a Matrícula nº 12.345 (pp. 150–152; p. 244), em 1986 e 2019–2021.")
        cats = {c for c, _ in got}
        for esperado in ("data", "valor", "percentual", "medida", "dispositivo", "registro", "pagina", "ano", "periodo"):
            self.assertIn(esperado, cats, got)
        self.assertIn(("pagina", "pp. 150–152"), got)
        self.assertIn(("pagina", "p. 244"), got)
        self.assertIn(("periodo", "2019–2021"), got)
        self.assertIn(("ano", "1986"), got)

    def test_remissao_interna_e_numero_do_paragrafo_ficam_de_fora(self):
        got = itens("12. Como dito nos parágrafos 86 a 88 e no parágrafo 9.876, nada mais.")
        self.assertEqual(got, [])

    def test_numero_com_pontuacao(self):
        self.assertIn(("numero", "171,68"), itens("A diferença é de 171,68 no conjunto."))

    def test_datas_equivalentes(self):
        a = inv.Item("data", "16 de novembro de 2022", "", *inv._data("16 de novembro de 2022"), "", "")
        r, f = inv._data("16/11/2022")
        self.assertEqual(a.requisitos, r)


class ComparacaoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.ant = self.dir / "v1.md"
        self.nova = self.dir / "v2.md"
        self.ant.write_text(ANTERIOR, encoding="utf-8")
        self.nova.write_text(NOVA, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = inv.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_acrescimos_e_supressoes(self):
        acr, sup = inv.comparar(inv.inventario(self.ant), inv.inventario(self.nova))
        lits = {i.literal for i in acr}
        for esperado in ("Cr$ 2.683,80", "64,73%", "1983–1987", "16/11/2022", "p. 40"):
            self.assertIn(esperado, lits)
        # "pp. 35–36" virou "p. 35" + "pp. 36 e 40": nenhuma página sumiu; "1º de abril de 1986" virou "1º de abril daquele ano"
        self.assertEqual(sup, [], [i.literal for i in sup])
        self.assertFalse([i for i in acr if i.literal in ("7", "9")])  # remissões internas

    def test_supressao_real_da_codigo_1(self):
        self.nova.write_text(NOVA.replace("Cr$ 161.477.249,34", "um valor elevado"), encoding="utf-8")
        code, out, _ = self.cli(self.ant, self.nova)
        self.assertEqual(code, 1)
        self.assertIn("161.477.249,34", out.split("SUPRESSÕES")[1])

    def test_markdown_e_json(self):
        code, out, _ = self.cli(self.ant, self.nova, "--md", "--json", self.dir / "inv.json")
        self.assertEqual(code, 0)
        self.assertIn("| # | Categoria | Item | § (nova) | Contexto (frase) | Fonte (página) |", out)
        self.assertIn("### Supressões", out)
        self.assertIn("| § 1 |", out)
        dados = json.loads((self.dir / "inv.json").read_text(encoding="utf-8"))
        self.assertEqual(dados["supressoes"], [])
        self.assertTrue(any(a["literal"] == "Cr$ 2.683,80" for a in dados["acrescimos"]))

    def test_docx(self):
        dx = self.dir / "v2.docx"
        pars = [l.split(". ", 1)[1] for l in NOVA.splitlines() if l[:1].isdigit()]
        corpo = "".join(
            f'<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'
            f'<w:r><w:t xml:space="preserve">{t}</w:t></w:r></w:p>' for t in pars)
        num = (f'<w:numbering xmlns:w="{W_NS}"><w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/>'
               f'<w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>'
               f'<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num></w:numbering>')
        with zipfile.ZipFile(dx, "w") as z:
            z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')
            z.writestr("word/numbering.xml", num)
        acr, sup = inv.comparar(inv.inventario(self.ant), inv.inventario(dx))
        self.assertEqual(sup, [])
        self.assertIn("§ 1", next(i for i in acr if i.literal == "Cr$ 2.683,80").locais)

    def test_arquivo_inexistente(self):
        self.assertEqual(self.cli(self.ant, self.dir / "nao.md")[0], 2)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE2"), "defina FIXTURES_FASE2 para rodar com o caso real")
class CasoRealTests(unittest.TestCase):
    def test_v15_v16(self):
        f = Path(os.environ["FIXTURES_FASE2"])
        acr, sup = inv.comparar(inv.inventario(f / "v15_chk.md"), inv.inventario(f / "v16.md"))
        lits = " ".join(i.literal for i in acr)
        for esperado in ("2.683,80", "16/11/2022", "1983–1987", "2019–2021"):
            self.assertIn(esperado, lits)
        self.assertFalse([i for i in sup if i.categoria in ("numero", "valor", "percentual", "medida")])


if __name__ == "__main__":
    unittest.main()
