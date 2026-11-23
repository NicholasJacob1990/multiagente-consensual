"""Testes de ``integridade_docx`` com DOCX sintéticos mínimos (sem dependências).

Executar: ``python3 -m pytest test_integridade_docx.py`` ou
``python3 -m unittest test_integridade_docx``.
"""

from __future__ import annotations

import html
import io
import json
import re
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import integridade_docx as integ  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
AUTOR = 'w:author="Teste" w:date="2026-11-04T00:00:00Z"'

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "{extra}</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)


def run(texto: str, negrito: bool = False) -> str:
    rpr = "<w:rPr><w:b/></w:rPr>" if negrito else '<w:rPr><w:sz w:val="24"/></w:rPr>'
    saida = ""
    for parte in re.split(r"(\{fn:\d+\})", texto):
        nota = re.fullmatch(r"\{fn:(\d+)\}", parte)
        if nota:
            saida += (
                '<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr>'
                f'<w:footnoteReference w:id="{nota.group(1)}"/></w:r>'
            )
        elif parte:
            saida += f'<w:r>{rpr}<w:t xml:space="preserve">{html.escape(parte, quote=False)}</w:t></w:r>'
    return saida


def paragrafo(conteudo: str | list[tuple[str, bool]], estilo: str | None = None) -> str:
    if isinstance(conteudo, str) and conteudo.startswith("<w:"):
        return conteudo
    if isinstance(conteudo, str):
        conteudo = [(conteudo, False)]
    ppr = f'<w:pPr><w:pStyle w:val="{estilo}"/></w:pPr>' if estilo else '<w:pPr><w:jc w:val="both"/></w:pPr>'
    return "<w:p>" + ppr + "".join(run(texto, negrito) for texto, negrito in conteudo) + "</w:p>"


def criar_docx(caminho: Path, paragrafos: list, notas: dict[str, str] | None = None) -> Path:
    corpo = "".join(
        paragrafo(*item) if isinstance(item, tuple) else paragrafo(item) for item in paragrafos
    )
    documento = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f'<w:body>{corpo}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
    )
    extra = ""
    doc_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{}</Relationships>'
    )
    rel_notas = ""
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as arquivo:
        if notas is not None:
            extra = (
                '<Override PartName="/word/footnotes.xml" '
                'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"/>'
            )
            rel_notas = (
                '<Relationship Id="rId9" '
                'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes" '
                'Target="footnotes.xml"/>'
            )
            corpo_notas = "".join(
                f'<w:footnote w:id="{ident}"><w:p><w:pPr><w:jc w:val="both"/></w:pPr>'
                '<w:r><w:rPr><w:vertAlign w:val="superscript"/></w:rPr><w:footnoteRef/></w:r>'
                f'<w:r><w:t xml:space="preserve"> {html.escape(texto, quote=False)}</w:t></w:r></w:p></w:footnote>'
                for ident, texto in notas.items()
            )
            arquivo.writestr(
                "word/footnotes.xml",
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:footnotes xmlns:w="{W_NS}">'
                '<w:footnote w:type="separator" w:id="-1"><w:p><w:r><w:separator/></w:r></w:p></w:footnote>'
                '<w:footnote w:type="continuationSeparator" w:id="0"><w:p><w:r><w:continuationSeparator/></w:r></w:p></w:footnote>'
                f"{corpo_notas}</w:footnotes>",
            )
        arquivo.writestr("[Content_Types].xml", CONTENT_TYPES.format(extra=extra))
        arquivo.writestr("_rels/.rels", RELS)
        arquivo.writestr("word/_rels/document.xml.rels", doc_rels.format(rel_notas))
        arquivo.writestr("word/document.xml", documento)
    return caminho


REFERENCIAS = [
    "ALMADA, Ana. Registro de imóveis. São Paulo: Foco, 2023.",
    "LOUREIRO, Francisco. Comentários. Rio de Janeiro: Forense, 2019.",
    "RIBEIRO, Luis Paulo. Lei de Registros Públicos comentada. 2019.",
]


def corpo_base() -> list:
    return [
        ("PARECER JURÍDICO", "Title"),
        "O prazo para resposta é de dez dias, contados da intimação.",
        "A consulente deve pedir certidões. Depois, deve aguardar a resposta do cartório.",
        ("Referências", "Heading1"),
        *REFERENCIAS,
    ]


class IntegridadeTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.base = criar_docx(self.dir / "base.docx", corpo_base())
        limpa = corpo_base()
        limpa[1] = "O prazo para resposta é de quinze dias, contados da intimação."
        limpa[2:3] = ["A consulente deve pedir certidões.", "Depois, deve aguardar a resposta do cartório."]
        self.limpa = criar_docx(self.dir / "limpa.docx", limpa)
        redline = corpo_base()
        redline[1] = (
            '<w:p><w:pPr/>' + run("O prazo para resposta é de ")
            + f'<w:del w:id="1" {AUTOR}><w:r><w:delText>dez</w:delText></w:r></w:del>'
            + f'<w:ins w:id="2" {AUTOR}><w:r><w:t>quinze</w:t></w:r></w:ins>'
            + run(" dias, contados da intimação.") + "</w:p>"
        )
        redline[2:3] = [
            f'<w:p><w:pPr><w:rPr><w:ins w:id="3" {AUTOR}/></w:rPr></w:pPr>'
            + run("A consulente deve pedir certidões.")
            + f'<w:del w:id="4" {AUTOR}><w:r><w:delText xml:space="preserve"> </w:delText></w:r></w:del></w:p>',
            paragrafo("Depois, deve aguardar a resposta do cartório."),
        ]
        self.redline = criar_docx(self.dir / "redline.docx", redline)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_redline_valido_com_divisao(self) -> None:
        resultado = integ.conferir(self.base, self.limpa, self.redline, divididos=1)
        self.assertTrue(resultado["ok"], integ.formatar(resultado))
        self.assertEqual(resultado["contagens"]["base"], 7)
        self.assertEqual(resultado["contagens"]["aceitar"], 8)
        self.assertEqual(resultado["contagens"]["rejeitar"], 7)

    def test_aceitar_e_rejeitar_unem_marcas_de_paragrafo(self) -> None:
        aceito = integ.aceitar(self.redline)
        rejeitado = integ.rejeitar(self.redline)
        self.assertIn("A consulente deve pedir certidões.", aceito.paragrafos)
        self.assertIn(
            "A consulente deve pedir certidões. Depois, deve aguardar a resposta do cartório.",
            rejeitado.paragrafos,
        )
        self.assertIn("O prazo para resposta é de quinze dias, contados da intimação.", aceito.paragrafos)
        self.assertIn("O prazo para resposta é de dez dias, contados da intimação.", rejeitado.paragrafos)

    def test_contagem_divididos_errada_falha(self) -> None:
        resultado = integ.conferir(self.base, self.limpa, self.redline, divididos=2)
        self.assertFalse(resultado["ok"])
        falhas = [item["nome"] for item in resultado["verificacoes"] if not item["ok"]]
        self.assertEqual(falhas, ["contagem_paragrafos"])

    def test_perda_dos_tres_ultimos_paragrafos_no_redline(self) -> None:
        # Montagem desalinhada: o redline perdeu as 3 últimas referências.
        redline = corpo_base()[:-3]
        perdido = criar_docx(self.dir / "perdido.docx", redline)
        limpa = criar_docx(self.dir / "limpa_igual.docx", corpo_base())
        resultado = integ.conferir(self.base, limpa, perdido)
        self.assertFalse(resultado["ok"])
        primeira = resultado["primeira_divergencia"]
        self.assertEqual(primeira["verificacao"], "aceitar_reproduz_limpa")
        self.assertEqual(primeira["indice"], 4)
        self.assertEqual(primeira["esperado"], REFERENCIAS[0][:80])
        self.assertEqual(primeira["obtido"], "(ausente)")
        self.assertIn("3 parágrafo(s) esperado(s) ausente(s) a partir do índice 4", primeira["resumo"])
        ref = next(item for item in resultado["verificacoes"] if item["nome"] == "referencias")
        self.assertFalse(ref["ok"])
        self.assertEqual(ref["aceitar"]["entradas"], 0)
        self.assertEqual(ref["base"]["entradas"], 3)

    def test_perda_na_limpa_e_no_redline_detectada_pela_contagem(self) -> None:
        # Limpa e redline perderam as referências juntas: só base + contagem acusam.
        limpa = criar_docx(self.dir / "limpa_perdida.docx", corpo_base()[:-3])
        redline = criar_docx(self.dir / "redline_perdido.docx", corpo_base()[:-3])
        resultado = integ.conferir(self.base, limpa, redline, divididos=0)
        falhas = {item["nome"] for item in resultado["verificacoes"] if not item["ok"]}
        self.assertIn("contagem_paragrafos", falhas)
        self.assertIn("rejeitar_reproduz_base", falhas)
        self.assertIn("marcas_presentes", falhas)
        self.assertTrue(any("Referências difere" in aviso for aviso in resultado["avisos"]))

    def test_exclusao_marcada_das_referencias_com_limpa_integra_falha(self) -> None:
        # Exclusão rastreada passa no validador genérico (lado "rejeitar"), mas
        # aceitar já não reproduz a limpa — falso negativo que este script evita.
        redline = corpo_base()
        redline[-3:] = [
            f'<w:p><w:pPr><w:rPr><w:del w:id="{10 + k}" {AUTOR}/></w:rPr></w:pPr>'
            f'<w:del w:id="{20 + k}" {AUTOR}><w:r><w:delText>{html.escape(texto, quote=False)}</w:delText></w:r></w:del></w:p>'
            for k, texto in enumerate(REFERENCIAS)
        ]
        marcado = criar_docx(self.dir / "marcado.docx", redline)
        limpa = criar_docx(self.dir / "limpa_igual.docx", corpo_base())
        resultado = integ.conferir(self.base, limpa, marcado)
        nomes = {item["nome"]: item["ok"] for item in resultado["verificacoes"]}
        self.assertTrue(nomes["rejeitar_reproduz_base"])
        self.assertFalse(nomes["aceitar_reproduz_limpa"])
        self.assertFalse(nomes["referencias"])

    def test_notas_de_rodape(self) -> None:
        corpo = corpo_base()
        corpo[1] = "O prazo para resposta é de dez dias.{fn:1}"
        base = criar_docx(self.dir / "nb.docx", corpo, notas={"1": "Art. 198 da Lei nº 6.015/1973."})
        limpa = criar_docx(self.dir / "nl.docx", corpo, notas={"1": "Art. 198 da Lei nº 6.015/1973."})
        redline_ok = criar_docx(self.dir / "nr.docx", corpo, notas={"1": "Art. 198 da Lei nº 6.015/1973."})
        self.assertTrue(integ.conferir(base, limpa, redline_ok)["ok"])
        self.assertEqual(integ.aceitar(redline_ok).notas, [" Art. 198 da Lei nº 6.015/1973."])
        redline_ruim = criar_docx(self.dir / "nr2.docx", corpo, notas={"1": "Art. 199 da Lei nº 6.015/1973."})
        resultado = integ.conferir(base, limpa, redline_ruim)
        falhas = {item["nome"] for item in resultado["verificacoes"] if not item["ok"]}
        self.assertEqual(falhas, {"notas_aceitar", "notas_rejeitar"})

    def test_cli_codigos_de_saida_e_json(self) -> None:
        saida_json = self.dir / "resultado.json"
        with redirect_stdout(io.StringIO()) as saida:
            codigo = integ.main(
                ["--base", str(self.base), "--limpa", str(self.limpa), "--redline", str(self.redline),
                 "--divididos", "1", "--json", str(saida_json)]
            )
        self.assertEqual(codigo, 0, saida.getvalue())
        self.assertTrue(json.loads(saida_json.read_text(encoding="utf-8"))["ok"])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(
                integ.main(["--base", str(self.base), "--limpa", str(self.limpa), "--redline", str(self.base)]), 1
            )
            self.assertEqual(
                integ.main(["--base", str(self.base), "--limpa", str(self.dir / "nao.docx"), "--redline", str(self.redline)]),
                2,
            )
        with self.assertRaises(SystemExit) as erro, redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            integ.main(["--base", str(self.base)])
        self.assertEqual(erro.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
