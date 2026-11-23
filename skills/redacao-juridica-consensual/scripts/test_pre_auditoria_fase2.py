#!/usr/bin/env python3
"""Testes da fase 2 de pre_auditoria_parecer.py: mapa de origem, vizinhos, equivalências, cobertura, absolutos e refutadas.

Rodar na pasta ``scripts``::

    python3 -m unittest test_pre_auditoria_fase2 -v

O teste com o caso real só roda com ``FIXTURES_FASE2=/caminho/da/pasta`` (v15_chk.md,
v16.md e origem_v15_v16.json); as fixtures não fazem parte do plugin.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import parecer_md as pm
import pre_auditoria_parecer as pa

CABECALHO = "**PARECER JURÍDICO**\n\nPrezados colegas,\n\n## I. Exame\n\n"


def doc(*pars: str, cabecalho: str = CABECALHO, anexo: str = "") -> pm.Documento:
    corpo = "\n\n".join(f"{i}. {t}" for i, t in enumerate(pars, start=1))
    return pm.parse(cabecalho + corpo + "\n\n" + anexo)


def regras(achados, *nomes, sev=("alerta", "bloqueante")):
    return [a for a in achados if a.regra in nomes and a.severidade in sev]


class CorpoNumeradoTests(unittest.TestCase):
    def test_ponte_ids_globais_para_numeros_do_corpo(self):
        d = doc("Primeiro.", "Segundo.", "Terceiro.", anexo="## Anexo\n\n1. Item do anexo.\n\n2. Outro item.")
        self.assertEqual(d.numeracao, "mista")
        corpo = pa.corpo_numerado(d)
        self.assertEqual(sorted(corpo), [1, 2, 3])
        self.assertEqual(pa.texto_proprio(corpo[2]), "Segundo.")
        self.assertNotEqual(corpo[2].numero, 2)  # o ID global inclui título e saudação

    def test_documento_explicito(self):
        d = pm.parse("1. Um.\n\n2. Dois.\n")
        self.assertEqual(sorted(pa.corpo_numerado(d)), [1, 2])

    def test_formatos_de_mapa(self):
        with tempfile.TemporaryDirectory() as t:
            a = Path(t, "a.json")
            a.write_text(json.dumps({"novo_para_antigos": {"1": [1, 2], "2": [3]}}), encoding="utf-8")
            self.assertEqual(pa.ler_mapa_origem(a), {1: [1, 2], 2: [3]})
            b = Path(t, "b.json")
            b.write_text(json.dumps({"mapa": {"1": [1], "2": [1], "3": [2]}}), encoding="utf-8")
            self.assertEqual(pa.ler_mapa_origem(b), {1: [1, 2], 2: [3]})


class MapaOrigemTests(unittest.TestCase):
    ANTIGO = (
        "A escritura de 1986 transmitiu o domínio útil dos lotes.",
        "A sucessão deverá ser averbada na Matrícula nº 9.876 antes do registro.",
        "Os requisitos devem ser observados pela serventia, e não se pode presumir a quitação.",
        "A Matrícula nº 9.876 descreve os lotes 01 e 10 com área de 21.000,00 m².",
        "O laudêmio, por fim, segue a taxa do título.",
    )
    NOVO = (
        "A escritura de 1986 transmitiu o domínio útil dos lotes.",
        # fusão de 2+3+4: modal em forma equivalente, "nº" repetido eliminado
        "A sucessão depende da averbação na Matrícula nº 9.876 antes do registro; observam-se os requisitos pela "
        "serventia, sem que se possa presumir a quitação, e a matrícula descreve os lotes 01 e 10 com área de 21.000,00 m².",
        "O laudêmio, por fim, segue a taxa do título.",
    )
    MAPA = {1: [1], 2: [2, 3, 4], 3: [5]}

    def test_fusao_sem_perda_nao_alerta_com_mapa(self):
        achados = pa.checar_renumeracao(doc(*self.NOVO), doc(*self.ANTIGO), mapa_origem=self.MAPA)
        self.assertEqual(regras(achados, "alcance", "ressalva", "citacao"), [], achados)
        self.assertEqual(regras(achados, "cobertura"), [])

    def test_sem_mapa_o_alinhamento_gera_ruido(self):
        achados = pa.checar_renumeracao(doc(*self.NOVO), doc(*self.ANTIGO))
        self.assertTrue(regras(achados, "alcance", "ressalva", "citacao", "cobertura"))

    def test_ressalva_perdida_de_verdade_continua_alertando(self):
        antigo = ("A averbação depende de anuência expressa do Estado, salvo se o título já a contiver.",
                  "O registro observa a continuidade.",
                  "O laudêmio segue a taxa do título.")
        novo = ("A averbação depende de anuência expressa do Estado, e o registro observa a continuidade.",
                "O laudêmio segue a taxa do título.")
        achados = pa.checar_renumeracao(doc(*novo), doc(*antigo), mapa_origem={1: [1, 2], 2: [3]})
        ressalvas = regras(achados, "ressalva")
        self.assertEqual(len(ressalvas), 1, achados)
        self.assertIn("salvo", ressalvas[0].mensagem)
        self.assertIn("novo 1 ← 1+2", ressalvas[0].mensagem)

    def test_ressalva_no_vizinho_nao_alerta(self):
        antigo = ("A averbação depende de anuência, salvo se o título já a contiver.", "O registro observa a continuidade.")
        novo = ("A averbação depende de anuência.", "Salvo se o título já a contiver, o registro observa a continuidade.")
        achados = pa.checar_renumeracao(doc(*novo), doc(*antigo), mapa_origem={1: [1], 2: [2]})
        self.assertEqual(regras(achados, "ressalva"), [])

    def test_alcance_retirado_de_verdade_alerta(self):
        antigo = ("O pedido pode ser instruído somente com a certidão atualizada.", "Outro assunto qualquer aqui.")
        novo = ("O pedido é instruído com a certidão atualizada.", "Outro assunto qualquer aqui.")
        achados = pa.checar_renumeracao(doc(*novo), doc(*antigo), mapa_origem={1: [1], 2: [2]})
        msgs = " ".join(a.mensagem for a in regras(achados, "alcance"))
        self.assertIn("retirado", msgs)
        self.assertIn("apenas", msgs)

    def test_citacao_integra_perdida_alerta(self):
        antigo = ("Aplica-se o art. 25, §§ 2º e 3º, da Lei nº 9.000/2020.",)
        novo = ("Aplica-se o art. 25, 2º e 3º, da Lei nº 9.000/2020.",)
        achados = pa.checar_renumeracao(doc(*novo), doc(*antigo), mapa_origem={1: [1]})
        cit = regras(achados, "citacao")
        self.assertEqual(len(cit), 1)
        self.assertIn("§§ 2º", cit[0].mensagem)


class EquivalenciasTests(unittest.TestCase):
    def sem_alerta(self, antigo: str, novo: str):
        achados = pa.checar_alcance(antigo, novo, 1)
        self.assertEqual(achados, [], f"{antigo!r} × {novo!r}: {achados}")

    def test_deve_ser_x(self):
        self.sem_alerta("A sucessão deve ser averbada na matrícula.", "Averba-se a sucessão na matrícula.")
        self.sem_alerta("A sucessão deve ser averbada na matrícula.", "Resta a averbar a sucessão na matrícula.")

    def test_nao_se_pode(self):
        self.sem_alerta("Não se pode presumir a quitação.", "Sem que se possa presumir a quitação.")
        self.sem_alerta("Não se pode deduzir a aquisição apenas da designação.", "A designação não basta para deduzir a aquisição.")

    def test_devera_cabera(self):
        self.sem_alerta("A GEPAT deverá pedir certidões.", "Caberá à GEPAT pedir certidões.")

    def test_devem_ser_observados(self):
        self.sem_alerta("Devem ser observados os requisitos do art. 5º.", "Observam-se os requisitos do art. 5º.")
        self.sem_alerta("Devem ser observados os requisitos do art. 5º.", "Requisitos do art. 5º observados.")

    def test_mudanca_real_continua(self):
        achados = pa.checar_alcance("A GEPAT deverá pedir certidões.", "A GEPAT poderá pedir certidões.", 1)
        self.assertTrue(achados)


class CoberturaTests(unittest.TestCase):
    def test_reformulada_vira_info_e_evaporada_alerta(self):
        antigo = doc("Os documentos de origem trazem as mesmas medidas de cento e cinco e cem metros para os dois lotes "
                     "aforados. O arredondamento da esquina explica a diferença encontrada pela serventia no levantamento.",
                     "Fim do texto.")
        novo = doc("Para os dois lotes aforados, as medidas que constam dos documentos de origem são idênticas: cento "
                   "e cinco metros e cem metros.", "Fim do texto.")
        achados = [a for a in pa.checar_renumeracao(novo, antigo, mapa_origem={1: [1], 2: [2]}) if a.regra == "cobertura"]
        info = [a for a in achados if a.severidade == "info"]
        alerta = [a for a in achados if a.severidade == "alerta"]
        self.assertEqual(len(info), 1, achados)
        self.assertEqual(len(alerta), 1, achados)
        self.assertIn("arredondamento", alerta[0].mensagem)


class AbsolutosTests(unittest.TestCase):
    def test_absoluto_sem_citacao(self):
        d = doc("O BDX nunca foi senhorio dos lotes.")
        achados = pa.checar_absolutos(d)
        self.assertEqual(len(achados), 1)
        self.assertIn("nunca", achados[0].mensagem)
        self.assertIn("nada nos autos indica", achados[0].mensagem)

    def test_excecoes(self):
        casos = [
            "O BDX nunca foi senhorio dos lotes (SEI 100000001, p. 31).",
            "A análise prossegue sem presumir que todos os lotes estejam na transcrição.",
            "Não se pode presumir que a transcrição abranja exclusivamente os lotes 03 a 08.",
            "A escritura fala em “todos os direitos e ações” sobre o imóvel.",
            "Foram lavrados o termo, o auto e a carta, todos de 1982.",
            "Nenhum ato de disposição deve ser praticado agora.",
        ]
        for c in casos:
            with self.subTest(c=c):
                self.assertEqual(pa.checar_absolutos(doc(c)), [])

    def test_referencias_ficam_de_fora(self):
        d = pm.parse(CABECALHO + "1. Texto neutro.\n\n## Referências\n\nAUTOR. Todos os direitos reservados. 2020.\n")
        self.assertEqual(pa.checar_absolutos(d), [])


class RefutadasECliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = pa.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_refutada_vira_bloqueante(self):
        minuta = self.dir / "m.md"
        minuta.write_text("1. A adjudicação seguiu a proporção de 66%/34% entre Estado e BDX.\n", encoding="utf-8")
        ref = self.dir / "r.json"
        ref.write_text(json.dumps({"caso": "t", "refutadas": [{"id": "R1", "padrao": "66%/34%", "regex": False,
                                                                "por_que": "é a divisão do preço de 1986",
                                                                "correto": "64,73% e 35,27%", "fonte": "SEI 1, p. 100"}]}),
                       encoding="utf-8")
        code, out, _ = self.cli(minuta, "--refutadas", ref)
        self.assertEqual(code, 1)
        self.assertIn("[BLOQUEANTE] refutada", out)
        self.assertIn("64,73%", out)

    def test_mapa_exige_anterior(self):
        minuta = self.dir / "m.md"
        minuta.write_text("1. Texto.\n", encoding="utf-8")
        mapa = self.dir / "o.json"
        mapa.write_text('{"novo_para_antigos": {"1": [1]}}', encoding="utf-8")
        code, _, err = self.cli(minuta, "--mapa-origem", mapa)
        self.assertEqual(code, 2)
        self.assertIn("--anterior", err)

    def test_cli_com_mapa(self):
        ant, nov, mapa = self.dir / "a.md", self.dir / "n.md", self.dir / "o.json"
        ant.write_text("1. A sucessão deverá ser averbada.\n\n2. Ela também não antecipa o procedimento.\n", encoding="utf-8")
        nov.write_text("1. A sucessão depende de averbação e não antecipa o procedimento.\n", encoding="utf-8")
        mapa.write_text('{"novo_para_antigos": {"1": [1, 2]}}', encoding="utf-8")
        code, out, _ = self.cli(nov, "--anterior", ant, "--mapa-origem", mapa)
        self.assertEqual(code, 0, out)
        self.assertNotIn("[ALERTA] alcance", out)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE2"), "defina FIXTURES_FASE2 para rodar com o caso real")
class CasoRealTests(unittest.TestCase):
    def test_v15_v16_com_mapa(self):
        f = Path(os.environ["FIXTURES_FASE2"])
        novo, antigo = pm.ler(f / "v16.md"), pm.ler(f / "v15_chk.md")
        mapa = pa.ler_mapa_origem(f / "origem_v15_v16.json")
        achados = pa.checar_renumeracao(novo, antigo, mapa_origem=mapa)
        self.assertLess(len(regras(achados, "alcance", "ressalva", "citacao")), 5)
        self.assertLess(len(regras(achados, "cobertura")), 20)
        self.assertFalse([a for a in achados if a.severidade == "bloqueante"])


if __name__ == "__main__":
    unittest.main()
