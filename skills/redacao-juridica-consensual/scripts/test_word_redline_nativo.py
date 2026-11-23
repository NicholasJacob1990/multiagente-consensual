"""Testes do motor nativo de ``word_redline`` com DOCX sintéticos mínimos.

Executar: ``python3 -m pytest test_word_redline_nativo.py`` ou
``python3 -m unittest test_word_redline_nativo``.
"""

from __future__ import annotations

import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integridade_docx as integ  # noqa: E402
import word_redline as wr  # noqa: E402
from test_integridade_docx import criar_docx, paragrafo, run  # noqa: E402

AUTOR = "Revisão Teste"
DATA = "2026-11-04T21:00:00Z"

ABERTURA = ("PARECER JURÍDICO", "Title")
FECHO = "É o parecer, sob censura."


def ler(caminho: Path, parte: str = "word/document.xml") -> str:
    with zipfile.ZipFile(caminho) as arquivo:
        return arquivo.read(parte).decode("utf-8")


def paragrafos_xml(xml: str) -> list[str]:
    return re.findall(r"<w:p[ >].*?</w:p>", xml, flags=re.S)


def inseridos(xml: str) -> list[str]:
    return ["".join(re.findall(r"<w:t[^>]*>([^<]*)</w:t>", m)) for m in re.findall(r"<w:ins [^>]*[^/]>(.*?)</w:ins>", xml, re.S)]


def excluidos(xml: str) -> list[str]:
    return ["".join(re.findall(r"<w:delText[^>]*>([^<]*)</w:delText>", m)) for m in re.findall(r"<w:del [^>]*[^/]>(.*?)</w:del>", xml, re.S)]


class MotorNativoTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def comparar(self, base: list, limpa: list, notas_base=None, notas_limpa=None, **kwargs) -> tuple[Path, dict]:
        b = criar_docx(self.dir / "base.docx", base, notas_base)
        l = criar_docx(self.dir / "limpa.docx", limpa, notas_limpa)
        saida = self.dir / "redline.docx"
        with redirect_stderr(io.StringIO()):
            payload = wr.generate_comparison(
                base=b,
                current=l,
                output=saida,
                author=AUTOR,
                comparison="teste",
                motor="nativo",
                date=DATA,
                force=True,
                **kwargs,
            )
        self.base_path, self.limpa_path = b, l
        return saida, payload

    def conferir(self, saida: Path, **kwargs) -> dict:
        resultado = integ.conferir(self.base_path, self.limpa_path, saida, **kwargs)
        self.assertTrue(resultado["ok"], integ.formatar(resultado))
        return resultado

    # ------------------------------------------------------------------
    def test_alteracao_de_palavra(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, "O prazo para resposta é de dez dias, contados da intimação.", FECHO],
            [ABERTURA, "O prazo para resposta é de quinze dias, contados da intimação.", FECHO],
        )
        xml = ler(saida)
        self.assertEqual(excluidos(xml), ["dez"])
        self.assertEqual(inseridos(xml), ["quinze"])
        self.assertIn(f'w:author="{AUTOR}" w:date="{DATA}"', xml)
        self.assertEqual(len(paragrafos_xml(xml)), 3)
        self.assertEqual(payload["relatorio"]["alterados_por_palavra"], 1)
        self.assertEqual(payload["relatorio"]["substituidos_inteiros"], [])
        self.assertEqual(payload["engine"]["name"], "nativo_diff_por_palavra")
        self.conferir(saida, divididos=0)

    def test_preserva_formatacao_dos_runs(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, [("Objeto:", True), (" situação dominial dos lotes 01 e 10.", False)]],
            [ABERTURA, [("Objeto:", True), (" situação dominial e registral dos lotes 01 e 10.", False)]],
        )
        xml = ler(saida)
        corpo = paragrafos_xml(xml)[1]
        self.assertIn('<w:r><w:rPr><w:b/></w:rPr><w:t xml:space="preserve">Objeto:</w:t></w:r>', corpo)
        insercao = re.search(r"<w:ins [^>]*[^/]>(.*?)</w:ins>", corpo, re.S).group(1)
        self.assertIn('<w:sz w:val="24"/>', insercao)
        self.assertNotIn("<w:b/>", insercao)
        self.assertEqual(inseridos(xml), [" e registral"])
        self.assertEqual(excluidos(xml), [])
        self.conferir(saida)

    def test_divisao_de_paragrafo(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, "A consulente deve pedir certidões ao cartório competente. Depois, deve aguardar a resposta escrita da serventia.", FECHO],
            [ABERTURA, "A consulente deve pedir certidões ao cartório competente.", "Depois, deve aguardar a resposta escrita da serventia.", FECHO],
        )
        xml = ler(saida)
        paragrafos = paragrafos_xml(xml)
        self.assertEqual(len(paragrafos), 4)
        self.assertRegex(paragrafos[1], r"<w:pPr>.*<w:rPr><w:ins [^>]*/></w:rPr></w:pPr>")
        self.assertNotRegex(paragrafos[2], r"<w:rPr><w:ins ")
        self.assertEqual(excluidos(xml), [" "])
        self.assertEqual(inseridos(xml), [])
        self.assertEqual(payload["relatorio"]["divisoes"], 1)
        self.assertEqual(payload["relatorio"]["paragrafos_acrescidos_por_divisao"], 1)
        resultado = self.conferir(saida, divididos=1)
        self.assertEqual(resultado["contagens"]["rejeitar"], 3)

    def test_fusao_de_paragrafos(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, "A consulente deve pedir certidões ao cartório competente.", "Depois, deve aguardar a resposta escrita da serventia.", FECHO],
            [ABERTURA, "A consulente deve pedir certidões ao cartório competente e, depois, aguardar a resposta escrita da serventia.", FECHO],
            fundidos=1,
        )
        xml = ler(saida)
        paragrafos = paragrafos_xml(xml)
        self.assertEqual(len(paragrafos), 4)
        self.assertRegex(paragrafos[1], r"<w:rPr><w:del [^>]*/></w:rPr></w:pPr>")
        self.assertEqual(payload["relatorio"]["fusoes"], 1)
        self.assertEqual(payload["relatorio"]["paragrafos_absorvidos_por_fusao"], 1)
        self.assertIn("Depois", "".join(excluidos(xml)))
        self.assertIn("depois", "".join(inseridos(xml)))
        self.conferir(saida, fundidos=1)

    def test_paragrafo_excluido_e_inserido(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, "Primeiro fundamento sobre a enfiteuse.", "Fundamento que será suprimido integralmente da minuta.", FECHO],
            [ABERTURA, "Primeiro fundamento sobre a enfiteuse.", FECHO, "Belo Horizonte, [data]."],
        )
        xml = ler(saida)
        paragrafos = paragrafos_xml(xml)
        suprimido = next(p for p in paragrafos if "suprimido" in p)
        self.assertRegex(suprimido, r"<w:rPr><w:del [^>]*/></w:rPr></w:pPr>")
        self.assertNotIn("<w:t ", suprimido)
        novo = next(p for p in paragrafos if "Belo Horizonte" in p)
        self.assertRegex(novo, r"<w:rPr><w:ins [^>]*/></w:rPr></w:pPr>")
        self.assertEqual(payload["relatorio"]["excluidos"], 1)
        self.assertEqual(payload["relatorio"]["inseridos"], 1)
        self.conferir(saida)

    def test_notas_de_rodape_preservadas(self) -> None:
        notas = {"1": "LOUREIRO, 2019, comentário ao art. 243."}
        saida, _ = self.comparar(
            [ABERTURA, "A doutrina ampara essas distinções.{fn:1} Essas lições fornecem critérios.", "O prazo é de dez dias.", FECHO],
            [ABERTURA, "A doutrina ampara essas distinções.{fn:1} Essas lições fornecem critérios.", "O prazo é de quinze dias.", FECHO],
            notas_base=notas,
            notas_limpa=notas,
        )
        self.assertEqual(ler(saida, "word/footnotes.xml"), ler(self.limpa_path, "word/footnotes.xml"))
        self.assertIn('<w:footnoteReference w:id="1"/>', ler(saida))
        resultado = self.conferir(saida)
        self.assertEqual(resultado["contagens"]["notas_limpa"], 1)

    def test_nota_alterada_inserida_e_excluida(self) -> None:
        saida, payload = self.comparar(
            [ABERTURA, "Primeira afirmação com apoio.{fn:1}", "Segunda afirmação com apoio antigo.{fn:2}", FECHO],
            [ABERTURA, "Primeira afirmação com apoio.{fn:1}", "Segunda afirmação sem nota.", "Terceira afirmação nova.{fn:2}", FECHO],
            notas_base={"1": "RIBEIRO, 2019, item 2.1.", "2": "ALMADA, 2023, cap. 5."},
            notas_limpa={"1": "RIBEIRO, 2019, item 2.2.", "2": "LOUREIRO, 2019, item 1."},
        )
        notas = ler(saida, "word/footnotes.xml")
        self.assertIn("ALMADA, 2023", "".join(excluidos(notas)))
        self.assertIn("LOUREIRO", "".join(inseridos(notas)))
        self.assertIn("2.2", "".join(inseridos(notas)))
        self.assertGreaterEqual(payload["relatorio"]["notas"]["excluidas"], 1)
        self.conferir(saida)

    def test_estrutura_complexa_substituida_inteira(self) -> None:
        link = (
            '<w:p><w:pPr/><w:r><w:t xml:space="preserve">Consulte </w:t></w:r>'
            '<w:hyperlink r:id="rId5"><w:r><w:t>{}</w:t></w:r></w:hyperlink></w:p>'
        )
        saida, payload = self.comparar(
            [ABERTURA, link.format("o portal do TJMG"), FECHO],
            [ABERTURA, link.format("o portal do CNJ"), FECHO],
        )
        substituidos = payload["relatorio"]["substituidos_inteiros"]
        self.assertEqual(len(substituidos), 1)
        self.assertIn("w:hyperlink", substituidos[0]["motivo"])
        xml = ler(saida)
        self.assertRegex(xml, r"<w:hyperlink r:id=\"rId5\"><w:del ")
        self.conferir(saida)

    def test_hiperlink_excluido_leva_relacao_da_base(self) -> None:
        link = (
            '<w:p><w:pPr/><w:r><w:t xml:space="preserve">Disponível em: </w:t></w:r>'
            '<w:hyperlink r:id="rIdLink"><w:r><w:t>portal do TJMG</w:t></w:r></w:hyperlink></w:p>'
        )
        b = criar_docx(self.dir / "base.docx", [ABERTURA, link, FECHO])
        with zipfile.ZipFile(b) as arquivo:
            partes = {nome: arquivo.read(nome) for nome in arquivo.namelist()}
        partes["word/_rels/document.xml.rels"] = partes["word/_rels/document.xml.rels"].replace(
            b"</Relationships>",
            b'<Relationship Id="rIdLink" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            b'relationships/hyperlink" Target="https://www.tjmg.jus.br/" TargetMode="External"/></Relationships>',
        )
        with zipfile.ZipFile(b, "w") as arquivo:
            for nome, conteudo in partes.items():
                arquivo.writestr(nome, conteudo)
        l = criar_docx(self.dir / "limpa.docx", [ABERTURA, FECHO])
        saida = self.dir / "redline.docx"
        with redirect_stderr(io.StringIO()):
            wr.generate_comparison(
                base=b, current=l, output=saida, author=AUTOR, comparison="t", motor="nativo", date=DATA
            )
        rels = ler(saida, "word/_rels/document.xml.rels")
        novo_id = re.search(r'<w:hyperlink r:id="([^"]+)"><w:del ', ler(saida)).group(1)
        self.assertRegex(rels, rf'Id="{novo_id}"[^>]*Target="https://www.tjmg.jus.br/" TargetMode="External"')
        self.base_path, self.limpa_path = b, l
        self.conferir(saida)

    def test_tabela_mesma_forma_celula_a_celula(self) -> None:
        def tabela(valor: str) -> str:
            return (
                "<w:tbl><w:tblPr/><w:tblGrid><w:gridCol/><w:gridCol/></w:tblGrid><w:tr>"
                f"<w:tc><w:tcPr/>{paragrafo('Área')}</w:tc><w:tc><w:tcPr/>{paragrafo(valor)}</w:tc>"
                "</w:tr></w:tbl>"
            )

        saida, payload = self.comparar(
            [ABERTURA, tabela("10.500,00 m² por lote"), FECHO],
            [ABERTURA, tabela("10.414,16 m² por lote"), FECHO],
        )
        self.assertEqual(payload["relatorio"]["tabelas_celula_a_celula"], 1)
        xml = ler(saida)
        self.assertEqual(excluidos(xml), ["10.500,00"])
        self.assertEqual(inseridos(xml), ["10.414,16"])
        self.conferir(saida)

    def test_perda_de_paragrafos_finais_impossivel_no_nativo(self) -> None:
        # O desalinhamento que apagou as 3 referências finais numa montagem
        # manual não ocorre: o corpo é reconstruído do alinhamento completo.
        refs = ["ALMADA, 2023.", "LOUREIRO, 2019.", "RIBEIRO, 2019."]
        base = [ABERTURA, "Parágrafo um. Parágrafo dois longo o bastante.", ("Referências", "Heading1"), *refs]
        limpa = [ABERTURA, "Parágrafo um.", "Parágrafo dois longo o bastante.", ("Referências", "Heading1"), *refs]
        saida, _ = self.comparar(base, limpa)
        resultado = self.conferir(saida, divididos=1)
        ref = next(item for item in resultado["verificacoes"] if item["nome"] == "referencias")
        self.assertEqual(ref["aceitar"]["entradas"], 3)

    def test_detectar_formatacao_opcional(self) -> None:
        base = [("Título", "Heading1"), [("Objeto:", True), (" texto antigo aqui.", False)]]
        limpa = [("Título", "Title"), [("Objeto:", False), (" texto novo aqui.", False)]]
        saida, _ = self.comparar(base, limpa)
        self.assertNotIn("PrChange", ler(saida))
        saida, _ = self.comparar(base, limpa, detect_format_changes=True)
        xml = ler(saida)
        self.assertRegex(xml, r"<w:pPrChange [^>]*><w:pPr><w:pStyle w:val=\"Heading1\"/></w:pPr></w:pPrChange>")
        self.assertRegex(xml, r"<w:rPrChange [^>]*><w:rPr><w:b/></w:rPr></w:rPrChange>")
        self.conferir(saida)

    def test_motor_auto_sem_docxodus_avisa(self) -> None:
        b = criar_docx(self.dir / "b.docx", [ABERTURA, "Texto antigo do parágrafo."])
        l = criar_docx(self.dir / "l.docx", [ABERTURA, "Texto novo do parágrafo."])
        saida = self.dir / "r.docx"
        manifesto = self.dir / "r.manifest.json"
        with mock.patch.object(wr, "_redlines_python", return_value=None), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()) as erro:
            codigo = wr.main(
                ["compare", "--base", str(b), "--limpa", str(l), "--saida", str(saida),
                 "--autor", AUTOR, "--data", "2026-11-04", "--manifest", str(manifesto)]
            )
        self.assertEqual(codigo, 0)
        self.assertIn("Docxodus", erro.getvalue())
        payload = json.loads(manifesto.read_text(encoding="utf-8"))
        self.assertEqual(payload["engine"]["requested"], "auto")
        self.assertEqual(payload["engine"]["name"], "nativo_diff_por_palavra")
        self.assertEqual(payload["revision_date"], "2026-11-04T00:00:00Z")
        self.assertTrue(any("Docxodus" in aviso for aviso in payload["avisos"]))
        self.assertIn('w:date="2026-11-04T00:00:00Z"', ler(saida))

    def test_motor_docxodus_indisponivel_falha(self) -> None:
        b = criar_docx(self.dir / "b.docx", [ABERTURA, "Texto."])
        with mock.patch.object(wr, "_redlines_python", return_value=None), redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            codigo = wr.main(
                ["compare", "--base", str(b), "--limpa", str(b), "--saida", str(self.dir / "x.docx"), "--motor", "docxodus"]
            )
        self.assertEqual(codigo, 2)

    def test_base_obrigatoria_e_data_invalida(self) -> None:
        b = criar_docx(self.dir / "b.docx", [ABERTURA, "Texto."])
        with self.assertRaises(SystemExit), redirect_stderr(io.StringIO()):
            wr.main(["compare", "--limpa", str(b), "--saida", str(self.dir / "x.docx")])
        with redirect_stderr(io.StringIO()):
            codigo = wr.main(
                ["compare", "--base", str(b), "--limpa", str(b), "--saida", str(self.dir / "x.docx"),
                 "--motor", "nativo", "--data", "ontem"]
            )
        self.assertEqual(codigo, 2)

    def test_integridade_reprovada_bloqueia_saida(self) -> None:
        b = criar_docx(self.dir / "b.docx", [ABERTURA, "Texto antigo."])
        l = criar_docx(self.dir / "l.docx", [ABERTURA, "Texto novo."])
        saida = self.dir / "r.docx"
        falha = {"ok": False, "verificacoes": [], "contagens": {}, "avisos": []}
        with mock.patch.object(integ, "conferir", return_value=falha), mock.patch.object(integ, "formatar", return_value="x"):
            with self.assertRaises(wr.RedlineError):
                wr.generate_comparison(
                    base=b, current=l, output=saida, author=AUTOR, comparison="t", motor="nativo", date=DATA
                )
        self.assertFalse(saida.exists())


if __name__ == "__main__":
    unittest.main()
