#!/usr/bin/env python3
"""Testes de consolidar_correcoes.py, inclusive o caso real simplificado de "(parágrafos 90, 105 e 105)".

    python3 -m unittest test_consolidar_correcoes -v
"""

from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import consolidar_correcoes as cc

TRECHO = "(parágrafos 90, 105 e 105)"
PROPOSTA_A = {"paragrafo": 121, "trecho_atual": TRECHO, "trecho_novo": "(parágrafos 90 e 105)", "tipo": "remissao",
              "justificativa": "número repetido; na v15 a remissão era aos parágrafos 133 e 158", "fonte": "v15, § 181"}
PROPOSTA_B = {"paragrafo": 121, "trecho_atual": TRECHO, "trecho_novo": "(parágrafos 72, 90 e 105)", "tipo": "remissao",
              "justificativa": "número repetido; completar com a incorporação", "fonte": "leitura do corpo"}
# formato novo_para_antigos: o 133 foi para o 90, o 158 para o 105, o 99 para o 72
MAPA = {"novo_para_antigos": {"72": [99], "90": [133], "105": [158]}}


class ConsolidarTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def json(self, nome: str, dados) -> Path:
        p = self.dir / nome
        p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return p

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cc.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def saida(self) -> list[dict]:
        return json.loads((self.dir / "final.json").read_text(encoding="utf-8"))["correcoes"]

    def test_caso_real_com_mapa_escolhe_a_variante_coerente(self):
        a = self.json("verif_remissoes.json", [PROPOSTA_A])
        b = self.json("verif_coerencia.json", {"correcoes": [PROPOSTA_B]})
        mapa = self.json("mapa.json", MAPA)
        code, out, _ = self.cli(a, b, "--mapa", mapa, "--saida", self.dir / "final.json", "--relatorio", self.dir / "rel.md")
        self.assertEqual(code, 0, out)
        final = self.saida()
        self.assertEqual([c["trecho_novo"] for c in final], ["(parágrafos 90 e 105)"])
        rel = (self.dir / "rel.md").read_text(encoding="utf-8")
        self.assertIn("**Decisão:** escolhida", rel)
        self.assertIn("[133, 158]", rel)

    def test_formato_do_mapear(self):
        a = self.json("a.json", [PROPOSTA_A, PROPOSTA_B])
        mapa = self.json("mapa.json", {"mapa": {"99": [72], "133": [90], "158": [105]}, "decisoes": []})
        code, _, _ = self.cli(a, "--mapa", mapa, "--saida", self.dir / "final.json")
        self.assertEqual(code, 0)
        self.assertEqual([c["trecho_novo"] for c in self.saida()], ["(parágrafos 90 e 105)"])

    def test_remissao_original_indica_a_outra_variante(self):
        b = dict(PROPOSTA_B, remissao_original="parágrafos 99, 133 e 158")
        a = self.json("a.json", [dict(PROPOSTA_A, justificativa="número repetido"), b])
        mapa = self.json("mapa.json", MAPA)
        self.cli(a, "--mapa", mapa, "--saida", self.dir / "final.json")
        self.assertEqual([c["trecho_novo"] for c in self.saida()], ["(parágrafos 72, 90 e 105)"])

    def test_sem_mapa_fica_pendente_e_fora_da_saida(self):
        a = self.json("a.json", [PROPOSTA_A])
        b = self.json("b.json", [PROPOSTA_B])
        code, out, _ = self.cli(a, b, "--saida", self.dir / "final.json", "--relatorio", self.dir / "rel.md")
        self.assertEqual(code, 1)
        self.assertEqual(self.saida(), [])
        self.assertIn("CONFLITO PENDENTE", (self.dir / "rel.md").read_text(encoding="utf-8"))
        self.assertIn("1 pendentes", out)

    def test_sem_remissao_original_fica_pendente(self):
        a = self.json("a.json", [dict(PROPOSTA_A, justificativa="número repetido", fonte=""), PROPOSTA_B])
        code, _, _ = self.cli(a, "--mapa", self.json("m.json", MAPA), "--saida", self.dir / "final.json")
        self.assertEqual(code, 1)
        self.assertEqual(self.saida(), [])

    def test_duplicatas_somam_origens(self):
        c1 = {"paragrafo": 5, "trecho_atual": "o Estado  reuniu", "trecho_novo": "o Estado pode ter reunido", "tipo": "fato",
              "justificativa": "calibrar"}
        c2 = dict(c1, trecho_atual="o Estado reuniu", justificativa="mesma coisa")
        a, b = self.json("a.json", [c1]), self.json("b.json", [c2])
        code, out, _ = self.cli(a, b, "--saida", self.dir / "final.json")
        self.assertEqual(code, 0)
        final = self.saida()
        self.assertEqual(len(final), 1)
        self.assertEqual(final[0]["origem"], ["a.json", "b.json"])
        self.assertIn("duplicadas: 1", out)

    def test_conflito_de_redacao_nao_e_decidido(self):
        c1 = {"paragrafo": 5, "trecho_atual": "A orientação", "trecho_novo": "Em síntese, a orientação", "tipo": "redacao",
              "justificativa": "x"}
        c2 = dict(c1, trecho_novo="A recomendação")
        code, _, _ = self.cli(self.json("a.json", [c1, c2]), "--mapa", self.json("m.json", MAPA), "--saida", self.dir / "final.json")
        self.assertEqual(code, 1)
        self.assertEqual(self.saida(), [])

    def test_contraprova_pareada(self):
        cs = [
            {"paragrafo": 1, "trecho_atual": "66%/34%", "trecho_novo": "64,73% e 35,27%", "tipo": "fato", "justificativa": "créditos"},
            {"paragrafo": 2, "trecho_atual": "a Delta comprou", "trecho_novo": "a Alfa comprou", "tipo": "fato", "justificativa": "R-10"},
            {"paragrafo": 3, "trecho_atual": "mera omissão material", "trecho_novo": "omissão", "tipo": "fato", "justificativa": "y"},
            {"paragrafo": 4, "trecho_atual": "sempre", "trecho_novo": "em regra", "tipo": "calibracao", "justificativa": "z"},
        ]
        a = self.json("verif_fatos.json", cs)
        d = self.json("contraprova_fatos.json", {"decisoes": [
            {"indice": 1, "veredito": "aceita"},
            {"indice": 2, "veredito": "rejeitada", "motivo": "a compradora de 1986 era mesmo outra"},
            {"indice": 3, "veredito": "ajustada", "trecho_atual": "mera omissão material",
             "trecho_novo": "falha cuja natureza depende de prova"},
        ]})
        code, out, _ = self.cli(a, d, "--saida", self.dir / "final.json", "--relatorio", self.dir / "rel.md")
        final = {c["trecho_atual"]: c["trecho_novo"] for c in self.saida()}
        self.assertEqual(final, {"66%/34%": "64,73% e 35,27%", "mera omissão material": "falha cuja natureza depende de prova"})
        self.assertEqual(code, 1)  # a 4ª ficou sem decisão
        rel = (self.dir / "rel.md").read_text(encoding="utf-8")
        self.assertIn("sem decisão da contraprova pareada", rel)
        self.assertIn("rejeitada", rel)

    def test_contraprova_pareada_pelo_campo_arquivo_e_indice_zero(self):
        a = self.json("a.json", [{"paragrafo": 1, "trecho_atual": "x1", "trecho_novo": "y1"}])
        b = self.json("b.json", [{"paragrafo": 2, "trecho_atual": "x2", "trecho_novo": "y2"}])
        d = self.json("d.json", {"arquivo": "a.json", "decisoes": [{"indice": 0, "veredito": "refutada"}]})
        code, _, _ = self.cli(a, b, d, "--saida", self.dir / "final.json")
        self.assertEqual(code, 0)
        self.assertEqual([c["trecho_atual"] for c in self.saida()], ["x2"])

    def test_erros_de_uso(self):
        self.assertEqual(self.cli(self.json("x.json", {"foo": 1}), "--saida", self.dir / "f.json")[0], 2)
        self.assertEqual(self.cli(self.json("d.json", {"decisoes": []}), "--saida", self.dir / "f.json")[0], 2)


if __name__ == "__main__":
    unittest.main()
