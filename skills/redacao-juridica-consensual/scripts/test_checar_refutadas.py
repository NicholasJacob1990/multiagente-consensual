#!/usr/bin/env python3
"""Testes de checar_refutadas.py com os quatro erros reais que voltaram em reescritas sucessivas.

    python3 -m unittest test_checar_refutadas -v
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import checar_refutadas as cr

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

REGISTRO = {
    "caso": "Lotes 01 e 10",
    "refutadas": [
        {"id": "R1", "regex": True,
         "padrao": r"adjudica\w*[^.;]{0,100}66\s*%\s*/\s*34\s*%|66\s*%\s*/\s*34\s*%[^.;]{0,60}adjudica",
         "por_que": "66%/34% é a divisão do preço da venda de 1986, não a da adjudicação de 1982",
         "correto": "cerca de 64,73% e 35,27%", "fonte": "SEI 100000001, pp. 100–106"},
        {"id": "R2", "regex": True,
         "padrao": r"delta[^.]{0,80}\b(?:compr|adquir)\w*[^.]{0,60}\b1986\b|\b1986\b[^.]{0,80}delta[^.]{0,40}\b(?:compr|adquir)",
         "por_que": "a Delta só entra na cadeia em 2001 (R-11)", "correto": "em 1986 a compradora foi a Alfa",
         "fonte": "SEI 100000002, p. 486"},
        {"id": "R3", "regex": False, "padrao": "reuniu em si o senhorio",
         "por_que": "a consolidação na pessoa do adjudicante não está provada", "correto": "pode ter reunido, a depender da prova"},
        {"id": "R4", "regex": False, "padrao": "mera omissão material",
         "por_que": "o confronto não demonstra que a falha seja só de escrituração"},
    ],
}


def docx(path: Path, paragrafos: list[str]) -> None:
    corpo = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>" for t in paragrafos)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')


class RefutadasTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.reg = self.dir / "refutadas.json"
        self.reg.write_text(json.dumps(REGISTRO, ensure_ascii=False), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cr.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def ids(self, texto: str) -> list[str]:
        dados = cr.carregar(self.reg)
        return [a.id for a in cr.checar_linhas(dados, [(1, texto)], "t")]

    def test_quatro_casos_reais(self):
        self.assertEqual(self.ids("Na adjudicação de 1982, a divisão foi de 66%/34% entre Estado e BDX."), ["R1"])
        self.assertEqual(self.ids("Em 1986, a Delta S/A comprou os lotes da CDX/UF."), ["R2"])
        self.assertEqual(self.ids("Com a adjudicação, o Estado reuniu em si o senhorio e o domínio útil."), ["R3"])
        self.assertEqual(self.ids("Trata-se de mera omissão material do registrador."), ["R4"])

    def test_normalizacao_de_acento_caixa_e_espaco(self):
        self.assertEqual(self.ids("O Estado REUNIU  em si o SENHÓRIO."), ["R3"])
        self.assertEqual(self.ids("Seria mera omissao  material."), ["R4"])
        self.assertEqual(self.ids("A adjudicação fixou 66 % / 34 % das quotas."), ["R1"])

    def test_formas_corretas_nao_acusam(self):
        for t in ("A venda de 1986 dividiu o preço em 66% e 34%, mas a adjudicação de 1982 seguiu 64,73% e 35,27%.",
                  "Em 2001, a Beta vendeu à Delta S/A os lotes.",
                  "Não se demonstrou que o Estado tenha reunido o senhorio.",
                  "O confronto não demonstra que a falha seja exclusivamente material."):
            with self.subTest(t=t):
                self.assertEqual(self.ids(t), [])

    def test_trecho_e_linha(self):
        dados = cr.carregar(self.reg)
        a = cr.checar_linhas(dados, [(7, "Texto antes. O Estado reuniu em si o senhorio direto. Depois.")], "x.md")[0]
        self.assertEqual(a.linha, 7)
        self.assertIn("[reuniu em si o senhorio]", a.trecho)

    def test_cli_md_e_docx(self):
        md = self.dir / "p.md"
        md.write_text("1. Texto sem problema.\n\n2. Seria mera omissão material.\n", encoding="utf-8")
        dx = self.dir / "p.docx"
        docx(dx, ["Introdução.", "O Estado reuniu em si o senhorio."])
        code, out, _ = self.cli("--refutadas", self.reg, md, dx, "--json", self.dir / "a.json")
        self.assertEqual(code, 1)
        self.assertIn("p.md:3", out)
        self.assertIn("p.docx:2", out)
        acertos = json.loads((self.dir / "a.json").read_text(encoding="utf-8"))["acertos"]
        self.assertEqual(sorted(a["id"] for a in acertos), ["R3", "R4"])

    def test_sem_acerto_e_zero(self):
        md = self.dir / "p.md"
        md.write_text("1. Nada a apontar.\n", encoding="utf-8")
        self.assertEqual(self.cli("--refutadas", self.reg, md)[0], 0)

    def test_ignorar_se_descarta_a_negacao(self):
        dados = cr.preparar({"refutadas": [{"id": "R2", "regex": True, "padrao": r"delta[^.]{0,80}\b1986\b",
                                            "ignorar_se": "nao adquiriu|diversamente do que"}]})
        linhas = [(1, "Diversamente do que indica a CI, a Delta S/A não adquiriu do Estado e do BDX em 1986."),
                  (2, "A Delta S/A adquiriu os lotes do Estado em 1986.")]
        self.assertEqual([a.linha for a in cr.checar_linhas(dados, linhas, "t")], [2])

    def test_exemplo_do_docstring_e_json_valido(self):
        doc = cr.__doc__
        ini, fim = doc.index("    {"), doc.index("\n    }\n") + 6
        dados = cr.preparar(json.loads(doc[ini:fim]))
        self.assertEqual([r["id"] for r in dados["refutadas"]], ["R1", "R2", "R3"])

    def test_modelo_vazio_carrega(self):
        modelo = Path(__file__).resolve().parent / "refutadas_modelo.json"
        dados = cr.carregar(modelo)
        self.assertEqual(dados["refutadas"], [])

    def test_erros_de_uso(self):
        ruim = self.dir / "ruim.json"
        ruim.write_text('{"refutadas": [{"id": "R1", "padrao": "(", "regex": true}]}', encoding="utf-8")
        md = self.dir / "p.md"
        md.write_text("x\n", encoding="utf-8")
        self.assertEqual(self.cli("--refutadas", ruim, md)[0], 2)
        self.assertEqual(self.cli("--refutadas", self.reg, self.dir / "nao_existe.md")[0], 2)


if __name__ == "__main__":
    unittest.main()
