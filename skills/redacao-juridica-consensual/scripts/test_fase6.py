"""Testes das ferramentas da Fase 6: densidade, pontas soltas, resolução de marcas e remontagem por roteiro.

Executar: ``python3 -m pytest test_fase6.py`` ou ``python3 -m unittest test_fase6``.
"""
from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import conferir_orfaos as orf  # noqa: E402
import integridade_docx as integ  # noqa: E402
import medir_densidade as dens  # noqa: E402
import reescrever_docx as reesc  # noqa: E402
import resolver_revisoes as resol  # noqa: E402
from test_integridade_docx import criar_docx  # noqa: E402

A = 'w:id="1" w:author="Revisor" w:date="2026-11-01T10:00:00Z"'


def chamar(mod, argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        cod = mod.main(argv)
    return cod, out.getvalue(), err.getvalue()


def num(texto: str, extra: str = "") -> str:
    return ('<w:p><w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="2"/></w:numPr><w:spacing w:after="60"/></w:pPr>'
            f'{extra}<w:r><w:t xml:space="preserve">{texto}</w:t></w:r></w:p>')


class DensidadeTest(unittest.TestCase):
    LONGO = "1. " + " ".join(["palavra"] * 85) + ".\n\n2. Frase curta e direta.\n\n3. É o parecer.\n\n## Referências\n\nAUTOR, Fulano. Obra."

    def test_mede_so_o_corpo_ate_o_fecho(self):
        m = dens.medir(self.LONGO)
        self.assertEqual(m["paragrafos"], 3)
        self.assertEqual(m["frases_acima_80"], 1)
        self.assertEqual(m["paragrafos_frase_unica_acima_70"], 1)

    def test_parenteses_nao_contam_na_frase_e_citacao_nao_conta(self):
        t = "1. O artigo citado " + "(" + " ".join(["x"] * 70) + ")" + " resolve a questão posta.\n\n> " + " ".join(["y"] * 90) + ".\n"
        m = dens.medir(t)
        self.assertEqual(m["frases_acima_60"], 0)
        self.assertEqual(m["frases"], 1)

    def test_meta_de_reducao_reprova_quem_so_dividiu_frases(self):
        ant = "1. " + ", ".join(["trecho longo de exemplo"] * 30) + ".\n"
        nova = "1. " + ". ".join(["Trecho longo de exemplo"] * 29) + ".\n"
        with tempfile.TemporaryDirectory() as d:
            a, n = Path(d) / "a.md", Path(d) / "n.md"
            a.write_text(ant, encoding="utf-8"); n.write_text(nova, encoding="utf-8")
            cod, out, _ = chamar(dens, [str(n), "--anterior", str(a), "--meta-reducao", "25"])
            self.assertEqual(cod, 1)
            self.assertIn("Meta não atingida", out)
            cod, out, _ = chamar(dens, [str(n), "--anterior", str(a)])
            self.assertEqual(cod, 0)
            self.assertIn("falta cortar conteúdo", out)

    def test_meta_exige_anterior(self):
        with tempfile.TemporaryDirectory() as d:
            n = Path(d) / "n.md"; n.write_text("1. Texto.\n", encoding="utf-8")
            self.assertEqual(chamar(dens, [str(n), "--meta-reducao", "10"])[0], 2)


class OrfaosTest(unittest.TestCase):
    BASE = ("PARECER\n\nDIREITO CIVIL. ENFITEUSE. DISTINÇÃO ENTRE RESGATE, COMISSO, CONFUSÃO E CONSOLIDAÇÃO DO DOMÍNIO PLENO. "
            "REQUERIMENTO INFORMATIVO CABÍVEL DESDE LOGO PERANTE O CARTÓRIO.\n\n"
            "1. A enfiteuse admite resgate e comisso; a consolidação reúne os domínios (Lei nº 6.015/1973; VENOSA, 2019).\n\n"
            "2. O Tribunal decidiu assim (TJMG - Apelação Cível 1.0000.19.008116-6/001) e também na Apelação Cível nº 1.0000.22.216039-2/001. "
            "O requerimento informativo é cabível. Aplica-se o Código Civil de 1916 e a Súmula nº 169.\n\n"
            "3. O lote perde 20² − π × 20² ÷ 4 ≈ 85,84 m².\n\n"
            "## Referências\n\n"
            "BRASIL. Lei nº 3.071, de 1º de janeiro de 1916. Código Civil.\n\n"
            "BRASIL. Lei nº 6.015, de 31 de dezembro de 1973.\n\n"
            "BRASIL. Lei nº 7.055, de 3 de agosto de 1977.\n\n"
            "BRASIL. Supremo Tribunal Federal. Súmula nº 169.\n\n"
            "FARIAS, Cristiano Chaves de. Curso de direito civil.\n\n"
            "MINAS GERAIS. Tribunal de Justiça. Apelação Cível nº 1.0000.22.216039-2/001.\n\n"
            "VENOSA, Sílvio de Salvo. Código Civil interpretado.\n\n"
            "## Anexo Único\n\n"
            "1. Instruem o requerimento os documentos. [Relacionar apenas os documentos efetivamente anexados.]\n\n"
            "Belo Horizonte, [data]. [NOME DO REPRESENTANTE]\n")

    def setUp(self):
        self.r = orf.conferir(self.BASE)
        self.por_tipo = {}
        for a in self.r["achados"]:
            self.por_tipo.setdefault(a["tipo"], []).append(a)

    def test_julgado_sem_referencia_bloqueia_e_o_referenciado_passa(self):
        j = self.por_tipo["julgado_sem_referencia"]
        self.assertEqual(len(j), 1)
        self.assertIn("008116", j[0]["mensagem"])
        self.assertFalse(self.r["ok"])

    def test_referencia_nao_citada(self):
        chaves = " | ".join(a["mensagem"] for a in self.por_tipo["referencia_nao_citada"])
        self.assertIn("7.055", chaves)
        self.assertIn("FARIAS", chaves)
        self.assertNotIn("6.015", chaves)       # citada com o ano: "6.015/1973"
        self.assertNotIn("3.071", chaves)       # citada pelo nome: Código Civil de 1916
        self.assertNotIn("VENOSA", chaves)
        self.assertNotIn("169", chaves)

    def test_verbete_da_ementa_sem_corpo(self):
        v = " | ".join(a["mensagem"] for a in self.por_tipo["verbete_sem_corpo"])
        self.assertIn("CONFUSÃO", v)
        self.assertNotIn("ENFITEUSE", v)
        self.assertNotIn("CONSOLIDAÇÃO", v)

    def test_instrucao_editorial_bloqueia_e_campo_so_informa(self):
        self.assertEqual(len(self.por_tipo["instrucao_editorial"]), 1)
        self.assertEqual(self.por_tipo["instrucao_editorial"][0]["gravidade"], "bloqueante")
        self.assertTrue(any("NOME DO REPRESENTANTE" in a["trecho"] for a in self.por_tipo["campo_a_preencher"]))

    def test_conta_com_simbolos(self):
        self.assertEqual(len(self.por_tipo["conta_com_simbolos"]), 1)

    def test_texto_limpo_passa(self):
        limpo = ("1. A regra é a do artigo 693 (Lei nº 5.827/1972; VENOSA, 2019).\n\n## Referências\n\n"
                 "BRASIL. Lei nº 5.827, de 23 de novembro de 1972.\n\nVENOSA, Sílvio. Código Civil interpretado.\n")
        r = orf.conferir(limpo)
        self.assertEqual(r["achados"], [])
        self.assertTrue(r["ok"])


class ResolverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.dir = Path(self._tmp.name)
        corpo = [
            "Título",
            f'<w:p><w:pPr><w:jc w:val="both"/></w:pPr><w:r><w:t xml:space="preserve">Texto </w:t></w:r>'
            f'<w:del {A}><w:r><w:delText xml:space="preserve">antigo</w:delText></w:r></w:del>'
            f'<w:ins {A}><w:r><w:t xml:space="preserve">novo</w:t></w:r></w:ins><w:r><w:t xml:space="preserve"> mantido.</w:t></w:r></w:p>',
            # marca de parágrafo inserida: ao rejeitar, funde com o seguinte
            f'<w:p><w:pPr><w:rPr><w:ins {A}/></w:rPr></w:pPr><w:r><w:t xml:space="preserve">Primeira parte. </w:t></w:r></w:p>',
            "Segunda parte.",
            # marca de parágrafo excluída: ao aceitar, funde com o seguinte
            f'<w:p><w:pPr><w:rPr><w:del {A}/></w:rPr></w:pPr><w:r><w:t xml:space="preserve">Metade um, </w:t></w:r></w:p>',
            "metade dois.",
            f'<w:p><w:pPr><w:jc w:val="center"/><w:pPrChange {A}><w:pPr><w:jc w:val="left"/></w:pPr></w:pPrChange></w:pPr>'
            f'<w:r><w:t>Formato alterado.</w:t></w:r></w:p>',
        ]
        self.ent = criar_docx(self.dir / "e.docx", corpo)

    def tearDown(self):
        self._tmp.cleanup()

    def _doc(self, p):
        with zipfile.ZipFile(p) as z:
            return z.read("word/document.xml").decode("utf-8")

    def test_aceitar_e_rejeitar_conferem_com_a_leitura_logica(self):
        for modo, esperado in (("aceitar", integ.aceitar), ("rejeitar", integ.rejeitar)):
            sai = self.dir / f"{modo}.docx"
            cod, out, _ = chamar(resol, [str(self.ent), str(sai), "--modo", modo])
            self.assertEqual(cod, 0, out)
            x = self._doc(sai)
            self.assertEqual(resol.restantes(x), 0)
            self.assertIn("<w:body>", x)                      # prefixo w: preservado
            self.assertEqual([p for p in integ.ler(sai).paragrafos if p.strip()],
                             [p for p in esperado(self.ent).paragrafos if p.strip()])

    def test_fusoes_e_formato(self):
        chamar(resol, [str(self.ent), str(self.dir / "r.docx"), "--modo", "rejeitar"])
        chamar(resol, [str(self.ent), str(self.dir / "a.docx"), "--modo", "aceitar"])
        r, a = integ.ler(self.dir / "r.docx").paragrafos, integ.ler(self.dir / "a.docx").paragrafos
        self.assertIn("Texto antigo mantido.", r)
        self.assertIn("Texto novo mantido.", a)
        self.assertIn("Primeira parte. Segunda parte.", r)
        self.assertIn("Metade um, metade dois.", a)
        self.assertIn('<w:jc w:val="left"/>', self._doc(self.dir / "r.docx"))
        self.assertNotIn('<w:jc w:val="left"/>', self._doc(self.dir / "a.docx"))

    def test_linha_de_tabela_inserida_some_ao_rejeitar(self):
        tab = (f'<w:tbl><w:tblPr/><w:tblGrid><w:gridCol w:w="100"/></w:tblGrid><w:tr><w:trPr><w:ins {A}/></w:trPr>'
               f'<w:tc><w:tcPr/><w:p><w:ins {A}><w:r><w:t>célula nova</w:t></w:r></w:ins></w:p></w:tc></w:tr></w:tbl>')
        x = resol.resolver_xml("<w:body><w:p><w:r><w:t>antes</w:t></w:r></w:p>" + tab + "</w:body>", "rejeitar")
        self.assertNotIn("<w:tbl>", x)
        self.assertIn("célula nova", resol.resolver_xml("<w:body>" + tab + "</w:body>", "aceitar"))


class ReescreverTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(); self.dir = Path(self._tmp.name)
        self.base = criar_docx(self.dir / "base.docx", [
            ("PARECER", "Title"), num("Primeiro parágrafo."), num("Segundo parágrafo, prolixo e cheio de detalhe."),
            num("Terceiro parágrafo."), ("Referências", "Heading1"), "AUTOR, Fulano. Obra."])

    def tearDown(self):
        self._tmp.cleanup()

    def _montar(self, roteiro: str):
        r = self.dir / "r.txt"; r.write_text(roteiro, encoding="utf-8")
        sai, rel = self.dir / "s.docx", self.dir / "rel.json"
        cod, out, err = chamar(reesc, ["montar", str(self.base), str(r), str(sai), "--relatorio", str(rel)])
        return cod, out + err, sai, rel

    def test_listar_numera_os_paragrafos(self):
        cod, out, _ = chamar(reesc, ["listar", str(self.base)])
        self.assertEqual(cod, 0)
        self.assertIn("§2", out)

    def test_monta_mantendo_reescrevendo_e_com_tabela(self):
        roteiro = ("=b|0\n=n|1\nn|**Rótulo.** Segundo parágrafo, enxuto.\nTW|2000,4000\nTH|Hipótese||Consequência\n"
                   "T|a) Primeira||Escritura\nTL|b) Segunda||Regularização\n=n|3\n=b|4\np|5|OUTRO, Autor. Nova obra.\n=b|6\n")
        cod, out, sai, rel = self._montar(roteiro)
        self.assertEqual(cod, 0, out)
        pars = integ.ler(sai).paragrafos
        self.assertIn("Rótulo. Segundo parágrafo, enxuto.", pars)
        self.assertIn("OUTRO, Autor. Nova obra.", pars)
        with zipfile.ZipFile(sai) as z:
            x = z.read("word/document.xml").decode("utf-8")
        self.assertEqual(x.count("<w:tr>"), 3)
        self.assertIn("<w:tblHeader/>", x)
        self.assertIn("<w:b/><w:bCs/></w:rPr><w:t xml:space=\"preserve\">Rótulo.</w:t>", x)
        d = json.loads(rel.read_text(encoding="utf-8"))
        self.assertEqual([i["texto"] for i in d["nao_mantidos"]], ["Segundo parágrafo, prolixo e cheio de detalhe.", "AUTOR, Fulano. Obra."])

    def test_erros_de_roteiro(self):
        for roteiro, trecho in (("=n|9\n=b|6\n", "parágrafo numerado 9"), ("x|oi\n=b|6\n", "instrução desconhecida"),
                                ("=b|0-5\n", "bloco de seção"), ("TH|a||b\nT|só uma\n=b|6\n", "número de colunas")):
            cod, out, _, _ = self._montar(roteiro)
            self.assertEqual(cod, 2, roteiro)
            self.assertIn(trecho, out)


if __name__ == "__main__":
    unittest.main()
