import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402
import pre_auditoria_parecer as pa  # noqa: E402

LONGO = " ".join(["palavra"] * 100)
TRANSCRICAO = "“" + " ".join(["texto"] * 45) + "”"


def doc(*pars, titulo="I. Relatório"):
    linhas = [f"## {titulo}"] + [f"{i}. {t}" for i, t in enumerate(pars, start=1)]
    return pm.parse("\n\n".join(linhas))


def cats(achados, cat):
    return [a for a in achados if a.regra == cat]


class TestEstilos(unittest.TestCase):
    def test_executivo_exige_resposta_objetiva(self):
        a = pa.auditar(doc("Trata-se de consulta.", "Outro."), {"estilo": "executivo"})
        self.assertTrue(any(x.severidade == "bloqueante" and "Resposta objetiva" in x.mensagem for x in cats(a, "estilo")))
        a = pa.auditar(doc("**Resposta objetiva.** Não dar baixa.", "Trata-se."), {"estilo": "executivo"})
        self.assertFalse([x for x in cats(a, "estilo") if x.severidade == "bloqueante"])

    def test_classico_nao_exige_resposta_objetiva(self):
        a = pa.auditar(doc("Trata-se de consulta.", "Outro."), {"estilo": "classico"})
        self.assertFalse([x for x in cats(a, "estilo") if x.severidade == "bloqueante"])

    def test_executivo_alerta_acima_de_90_sem_bloquear_ate_o_teto(self):
        a = pa.auditar(doc("**Resposta objetiva.** Curta.", LONGO), {"estilo": "executivo", "max_palavras": 120})
        alertas = [x for x in cats(a, "estilo") if x.severidade == "alerta"]
        self.assertEqual(len(alertas), 1)
        self.assertFalse(cats(a, "palavras"))

    def test_classico_admite_uma_transcricao_por_secao(self):
        d = doc("A " + TRANSCRICAO, "B " + TRANSCRICAO)
        a = pa.auditar(d, {"estilo": "classico"})
        self.assertEqual(len(cats(a, "transcricao")), 1)

    def test_perfil_que_veda_transcricao(self):
        d = doc("**Resposta objetiva.** X.", "A " + TRANSCRICAO)
        # a vedação do perfil vale no executivo; no clássico, a transcrição foi liberada (uma por seção)
        a = pa.auditar(d, {"estilo": "executivo", "veda_transcricao": True})
        self.assertEqual(len(cats(a, "transcricao")), 1)
        self.assertIn("veda", cats(a, "transcricao")[0].mensagem)
        a = pa.auditar(d, {"estilo": "classico", "veda_transcricao": True})
        self.assertFalse(cats(a, "transcricao"))

    def test_sem_estilo_nada_muda(self):
        a = pa.auditar(doc("Trata-se.", LONGO, "A " + TRANSCRICAO), {})
        self.assertFalse(cats(a, "estilo") + cats(a, "transcricao"))

    def test_cli_aceita_estilo(self):
        import tempfile
        with tempfile.TemporaryDirectory() as dd:
            p = Path(dd) / "m.md"
            p.write_text("## I. Relatório\n\n1. Trata-se.\n", encoding="utf-8")
            self.assertEqual(pa.main([str(p), "--estilo", "executivo", "--sem-info"]), 1)
            self.assertEqual(pa.main([str(p), "--estilo", "classico", "--sem-info"]), 0)


if __name__ == "__main__":
    unittest.main()
