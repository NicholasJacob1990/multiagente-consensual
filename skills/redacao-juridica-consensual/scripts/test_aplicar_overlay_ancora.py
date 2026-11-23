"""Testes dos itens por âncora (``ancora``/``depois``, ``ancora_paragrafo``/``texto``) e das opções
``--limpa``, ``--integridade`` e ``--data`` de ``aplicar_overlay``, com DOCX sintéticos mínimos.

Executar: ``python3 -m unittest test_aplicar_overlay_ancora`` (requer ``lxml``).
"""

from __future__ import annotations

import html
import io
import json
import shutil
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aplicar_overlay as AO  # noqa: E402
import integridade_docx as integ  # noqa: E402
import overlay_docx as O  # noqa: E402
from lxml import etree  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
VALIDADOR = Path("/mnt/skills/public/docx/scripts/office/validate.py")

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)

RPR = {
    "n": '<w:rPr><w:sz w:val="24"/></w:rPr>',
    "b": '<w:rPr><w:b/><w:sz w:val="24"/></w:rPr>',
    "i": '<w:rPr><w:i/><w:sz w:val="24"/></w:rPr>',
}
NUMPR = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'


def r(texto: str, fmt: str = "n") -> str:
    return f'<w:r>{RPR[fmt]}<w:t xml:space="preserve">{html.escape(texto, quote=False)}</w:t></w:r>'


def p(*runs: str, numerado: bool = False) -> str:
    return "<w:p>" + (NUMPR if numerado else "") + "".join(runs) + "</w:p>"


CORPO = [
    p(r("EMENTA: ", "b"), r("Adjudicação de lotes em distrito industrial.")),                    # posição 1
    p(r("Primeiro parágrafo numerado, com texto comum."), numerado=True),                          # § 1
    p(r("O prazo é "), r("de cinco anos", "i"), r(" contados da posse."), numerado=True),         # § 2
    p(r("Síntese. ", "b"), r("Como antecipado no parágrafo 1, nada se pratica agora.")),           # posição 4
    "<w:tbl><w:tblPr><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr><w:tblGrid><w:gridCol w:w=\"4000\"/></w:tblGrid>"
    "<w:tr><w:tc><w:tcPr><w:tcW w:w=\"4000\" w:type=\"dxa\"/></w:tcPr>"
    + p(r("Hipótese A: lote vago e sem ocupação.")) + "</w:tc></w:tr></w:tbl>",                    # posição 5
    p(r("a) ", "b"), r("certidão de inteiro teor da Matrícula nº 12.345;")),                       # posição 6
    p(r("b) ", "b"), r("certidão de inteiro teor da Matrícula nº 9.876.")),                         # posição 7
]


def documento(corpo: list[str]) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W_NS}"><w:body>' + "".join(corpo)
        + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>'
    )


def gravar_docx(caminho: Path, corpo: list[str] = CORPO) -> Path:
    with zipfile.ZipFile(caminho, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/document.xml", documento(corpo))
    return caminho


def raiz(caminho: Path):
    return etree.fromstring(zipfile.ZipFile(caminho).read("word/document.xml"))


def paragrafos(caminho: Path) -> list:
    return list(raiz(caminho).iter(O.w("p")))


def negrito(run) -> bool:
    rpr = run.find(O.w("rPr"))
    return rpr is not None and rpr.find(O.w("b")) is not None


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.entrada = gravar_docx(self.tmp / "base.docx")
        self.saida = self.tmp / "redline.docx"

    def aplicar(self, itens: list[dict], **kw) -> list[str]:
        return AO.aplicar(self.entrada, self.saida, {"paragrafos": itens}, "Revisor", "2026-11-05T18:00:00Z", **kw)

    def main(self, itens: list[dict], *extra: str) -> tuple[int, str]:
        alt = self.tmp / "alt.json"
        alt.write_text(json.dumps({"paragrafos": itens}, ensure_ascii=False), encoding="utf-8")
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            rc = AO.main([str(self.entrada), str(self.saida), "--alteracoes", str(alt), "--autor", "Revisor", *extra])
        return rc, out.getvalue() + err.getvalue()

    def aceito(self) -> list[str]:
        return integ.aceitar(self.saida).paragrafos

    def rejeitado(self) -> list[str]:
        return integ.rejeitar(self.saida).paragrafos


class TestAncora(Base):
    def test_paragrafo_sem_numero_com_rotulo_negrito(self):
        rel = self.aplicar([{"ancora": "nada se pratica agora", "depois": "nenhum ato de disposição se pratica agora"}])
        self.assertIn("parágrafo sem número (posição 4)", rel[0])
        self.assertEqual(self.aceito()[3], "Síntese. Como antecipado no parágrafo 1, nenhum ato de disposição se pratica agora.")
        self.assertEqual(self.rejeitado(), integ.ler(self.entrada).paragrafos)
        alvo = paragrafos(self.saida)[3]
        primeiro = next(alvo.iter(O.w("r")))
        self.assertTrue(negrito(primeiro))
        self.assertEqual(O.run_text(primeiro), "Síntese. ")
        self.assertIs(primeiro.getparent(), alvo)  # rótulo intocado (fora de w:ins/w:del)
        inseridos = [x for i in alvo.iter(O.w("ins")) for x in i.iter(O.w("r"))]
        self.assertTrue(inseridos)
        self.assertFalse(any(negrito(x) for x in inseridos))

    def test_ancora_atravessa_dois_runs(self):
        self.aplicar([{"ancora": "é de cinco anos contados", "depois": "é de dez anos contados"}])
        self.assertEqual(self.aceito()[2], "O prazo é de dez anos contados da posse.")
        self.assertEqual(self.rejeitado(), integ.ler(self.entrada).paragrafos)
        alvo = paragrafos(self.saida)[2]
        ins = [x for i in alvo.iter(O.w("ins")) for x in i.iter(O.w("r"))]
        dele = [x for d in alvo.iter(O.w("del")) for x in d.iter(O.w("r"))]
        self.assertEqual("".join(O.run_text(x) for x in ins), "dez")
        self.assertEqual("".join(x.findtext(O.w("delText")) for x in dele), "cinco")
        italico = lambda x: x.find(O.w("rPr")).find(O.w("i")) is not None  # noqa: E731
        self.assertTrue(all(italico(x) for x in ins + dele))  # herda o itálico do run substituído
        # o texto comum em volta continua sem itálico
        comuns = [x for x in alvo.iter(O.w("r")) if O.run_text(x) in ("O prazo é ", " contados da posse.")]
        self.assertEqual(len(comuns), 2)
        self.assertFalse(any(italico(x) for x in comuns))

    def test_ancora_atravessa_rotulo_negrito_e_texto(self):
        self.aplicar([{"ancora": "EMENTA: Adjudicação de lotes", "depois": "EMENTA: Adjudicação conjunta de lotes"}])
        self.assertEqual(self.aceito()[0], "EMENTA: Adjudicação conjunta de lotes em distrito industrial.")
        alvo = paragrafos(self.saida)[0]
        ins = [x for i in alvo.iter(O.w("ins")) for x in i.iter(O.w("r"))]
        self.assertEqual("".join(O.run_text(x) for x in ins).strip(), "conjunta")
        self.assertFalse(any(negrito(x) for x in ins))
        self.assertFalse(list(alvo.iter(O.w("del"))))

    def test_ancora_em_tabela(self):
        rel = self.aplicar([{"ancora": "lote vago", "depois": "lote desocupado"}])
        self.assertIn("tabela", rel[0])
        self.assertIn("Hipótese A: lote desocupado e sem ocupação.", self.aceito())

    def test_ancora_em_paragrafo_numerado_respeita_limite(self):
        longo = " ".join(["palavra"] * 10)
        with self.assertRaisesRegex(ValueError, r"acima de 8 palavras: § 1"):
            self.aplicar([{"ancora": "texto comum", "depois": longo}], max_palavras=8)
        self.aplicar([{"ancora": "texto comum", "depois": longo, "permitir_longo": True}], max_palavras=8)
        # parágrafo sem número: só relata a contagem
        rel = self.aplicar([{"ancora": "nada se pratica agora", "depois": longo}], max_palavras=8)
        self.assertIn("palavras", rel[0])

    def test_ancora_ausente(self):
        with self.assertRaisesRegex(ValueError, "não encontrada em nenhum parágrafo"):
            self.aplicar([{"ancora": "trecho que não existe", "depois": "x"}])
        with self.assertRaisesRegex(ValueError, r"espaços normalizados aparece em: § 2"):
            self.aplicar([{"ancora": "O prazo  é", "depois": "x"}])
        rc, out = self.main([{"ancora": "trecho que não existe", "depois": "x"}])
        self.assertEqual(rc, 1)
        self.assertIn("RECUSADO", out)
        self.assertFalse(self.saida.exists())

    def test_ancora_duplicada_lista_os_paragrafos(self):
        with self.assertRaises(ValueError) as cm:
            self.aplicar([{"ancora": "certidão de inteiro teor", "depois": "certidão atualizada"}])
        msg = str(cm.exception)
        self.assertIn("aparece 2 vezes", msg)
        self.assertIn("posição 6", msg)
        self.assertIn("posição 7", msg)
        rc, out = self.main([{"ancora": "certidão de inteiro teor", "depois": "x"}], "--limpa", str(self.tmp / "l.docx"))
        self.assertEqual(rc, 1)
        self.assertFalse(self.saida.exists())
        self.assertFalse((self.tmp / "l.docx").exists())

    def test_ancora_duplicada_no_mesmo_paragrafo(self):
        with self.assertRaisesRegex(ValueError, r"aparece 2 vezes .*§ 1 «.*» \(2×\)"):
            self.aplicar([{"ancora": "um", "depois": "x"}])  # "numerado" e "comum", ambos no § 1

    def test_itens_aplicados_em_ordem_e_tipos_antigos_inalterados(self):
        self.aplicar([
            {"n": 2, "antes": "da posse", "depois": "da imissão na posse"},
            {"ancora": "imissão na posse", "depois": "imissão definitiva na posse"},
            {"n": 1, "acrescentar": " Frase acrescida."},
        ])
        aceito = self.aceito()
        self.assertEqual(aceito[2], "O prazo é de cinco anos contados da imissão definitiva na posse.")
        self.assertEqual(aceito[1], "Primeiro parágrafo numerado, com texto comum. Frase acrescida.")

    def test_item_sem_tipo(self):
        with self.assertRaisesRegex(ValueError, "sem 'n', 'ancora' nem 'ancora_paragrafo'"):
            self.aplicar([{"depois": "x"}])
        with self.assertRaisesRegex(ValueError, "sem 'depois'"):
            self.aplicar([{"ancora": "lote vago"}])


class TestAncoraParagrafo(Base):
    def test_preserva_rotulo_negrito(self):
        novo = "Síntese. Conforme a resposta objetiva, nenhum ato de disposição deve ser praticado agora."
        rel = self.aplicar([{"ancora_paragrafo": "Síntese. Como", "texto": novo,
                             "atual": "Síntese. Como antecipado no parágrafo 1, nada se pratica agora."}])
        self.assertIn("rótulo em negrito preservado", rel[0])
        self.assertEqual(self.aceito()[3], novo)
        self.assertEqual(self.rejeitado(), integ.ler(self.entrada).paragrafos)
        alvo = paragrafos(self.saida)[3]
        primeiro = next(alvo.iter(O.w("r")))
        self.assertTrue(negrito(primeiro))
        self.assertEqual(O.run_text(primeiro), "Síntese. ")
        self.assertIs(primeiro.getparent(), alvo)
        inseridos = [x for i in alvo.iter(O.w("ins")) for x in i.iter(O.w("r"))]
        self.assertFalse(any(negrito(x) for x in inseridos))

    def test_rotulo_preservado_mesmo_com_texto_muito_diferente(self):
        novo = "a) Vistoria."
        self.aplicar([{"ancora_paragrafo": "a) certidão", "texto": novo}])
        self.assertEqual(self.aceito()[5], novo)
        alvo = paragrafos(self.saida)[5]
        primeiro = next(alvo.iter(O.w("r")))
        self.assertEqual(O.run_text(primeiro), "a) ")
        self.assertIs(primeiro.getparent(), alvo)
        inseridos = [x for i in alvo.iter(O.w("ins")) for x in i.iter(O.w("r"))]
        self.assertEqual("".join(O.run_text(x) for x in inseridos), "Vistoria.")
        self.assertFalse(any(negrito(x) for x in inseridos))

    def test_sem_o_mesmo_rotulo_troca_tudo(self):
        rel = self.aplicar([{"ancora_paragrafo": "Síntese.", "texto": "Resumo. Nada se pratica agora."}])
        self.assertNotIn("preservado", rel[0])
        self.assertEqual(self.aceito()[3], "Resumo. Nada se pratica agora.")

    def test_atual_divergente_e_inicio_ambiguo(self):
        with self.assertRaisesRegex(ValueError, "campo 'atual' não confere"):
            self.aplicar([{"ancora_paragrafo": "Síntese.", "texto": "Síntese. X.", "atual": "outro texto"}])
        with self.assertRaisesRegex(ValueError, "nenhum parágrafo começa por"):
            self.aplicar([{"ancora_paragrafo": "Inexistente", "texto": "X."}])
        corpo = CORPO + [p(r("Síntese. ", "b"), r("Outra síntese."))]
        gravar_docx(self.entrada, corpo)
        with self.assertRaisesRegex(ValueError, "2 parágrafos começam por"):
            self.aplicar([{"ancora_paragrafo": "Síntese.", "texto": "Síntese. X."}])


class TestOpcoes(Base):
    ITENS = [
        {"ancora": "nada se pratica agora", "depois": "nenhum ato se pratica agora"},
        {"ancora": "é de cinco anos", "depois": "é de dez anos"},
        {"ancora_paragrafo": "b) certidão", "texto": "b) certidão atualizada da Matrícula nº 9.876."},
    ]

    def test_limpa_e_integridade_em_documento_limpo(self):
        limpa = self.tmp / "limpa.docx"
        rc, out = self.main(self.ITENS, "--limpa", str(limpa), "--integridade", "--data", "2026-11-05")
        self.assertEqual(rc, 0, out)
        self.assertIn("integridade_docx: OK", out)
        self.assertTrue(self.saida.exists() and limpa.exists())
        doc_limpa = integ.ler(limpa)
        self.assertEqual(doc_limpa.marcas, 0)
        self.assertEqual(doc_limpa.paragrafos, self.aceito())
        self.assertIn("O prazo é de dez anos contados da posse.", doc_limpa.paragrafos)
        self.assertTrue(integ.conferir(self.entrada, limpa, self.saida)["ok"])
        datas = {e.get(O.w("date")) for e in raiz(self.saida).iter(O.w("ins"), O.w("del"))}
        self.assertEqual(datas, {"2026-11-05T00:00:00Z"})
        autores = {e.get(O.w("author")) for e in raiz(self.saida).iter(O.w("ins"), O.w("del"))}
        self.assertEqual(autores, {"Revisor"})

    def test_aceito_continua_valendo(self):
        aceito = self.tmp / "aceito.docx"
        rc, out = self.main(self.ITENS, "--aceito", str(aceito))
        self.assertEqual(rc, 0, out)
        self.assertEqual(integ.ler(aceito).paragrafos, self.aceito())

    def test_integridade_divergente_nao_grava(self):
        limpa = self.tmp / "limpa.docx"

        def aceitar_errado(entrada, saida):  # simula limpa que não corresponde ao redline
            shutil.copy(self.entrada, saida)

        with mock.patch.object(AO.O, "aceitar_tudo", aceitar_errado):
            rc, out = self.main(self.ITENS, "--limpa", str(limpa), "--integridade")
        self.assertEqual(rc, 1)
        self.assertIn("DIVERGÊNCIA", out)
        self.assertIn("RECUSADO: a integridade divergiu", out)
        self.assertFalse(self.saida.exists())
        self.assertFalse(limpa.exists())

    def test_integridade_sem_limpa(self):
        rc, out = self.main(self.ITENS, "--integridade")
        self.assertEqual(rc, 0, out)
        self.assertIn("integridade_docx: OK", out)

    def test_data_iso(self):
        self.assertEqual(AO.data_iso("2026-11-05"), "2026-11-05T00:00:00Z")
        self.assertEqual(AO.data_iso("2026-11-05T18:00:00Z"), "2026-11-05T18:00:00Z")
        self.assertEqual(AO.data_iso("2026-11-05T15:00:00-03:00"), "2026-11-05T18:00:00Z")
        with self.assertRaises(SystemExit):
            self.main(self.ITENS, "--data", "5/11/2026")
        self.assertFalse(self.saida.exists())

    @unittest.skipUnless(VALIDADOR.exists(), "validate.py da skill docx ausente")
    def test_validador_com_original(self):
        rc, out = self.main(self.ITENS, "--original", str(self.entrada), "--validador", str(VALIDADOR),
                            "--integridade")
        self.assertEqual(rc, 0, out)
        self.assertIn("validação:", out)


if __name__ == "__main__":
    unittest.main()
