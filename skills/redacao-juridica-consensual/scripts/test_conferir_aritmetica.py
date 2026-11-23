import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conferir_aritmetica as ca  # noqa: E402


class TestAvaliar(unittest.TestCase):
    def test_numeros_brasileiros(self):
        self.assertAlmostEqual(ca.avaliar("422.167,00 + 552.188,00"), 974355.0)
        self.assertAlmostEqual(ca.avaliar("64,73 + 35,27"), 100.0)
        self.assertAlmostEqual(ca.avaliar("1.000"), 1000.0)

    def test_pi_potencia_sqrt(self):
        self.assertAlmostEqual(ca.avaliar("20^2 - pi*20^2/4"), 85.8407, places=3)
        self.assertAlmostEqual(ca.avaliar("sqrt(16) × 2"), 8.0)

    def test_rejeita_codigo(self):
        with self.assertRaises(ValueError):
            ca.avaliar("__import__('os').system('x')")


class TestConferir(unittest.TestCase):
    def reg(self, **kw):
        v = {"id": "A1", "descricao": "d", "expressao": "422.167,00 + 552.188,00 = 974.355,00"}
        v.update(kw)
        return {"caso": "t", "verificacoes": [v]}

    def test_fecha(self):
        r = ca.conferir(self.reg(), {})
        self.assertTrue(r["ok"])

    def test_nao_fecha(self):
        r = ca.conferir(self.reg(expressao="422.167 + 552.188 = 974.000"), {})
        self.assertFalse(r["ok"])
        self.assertFalse(r["itens"][0]["fecha"])

    def test_tolerancia(self):
        r = ca.conferir(self.reg(expressao="20^2 - pi*20^2/4 = 85,84", tolerancia=0.01), {})
        self.assertTrue(r["ok"])
        r = ca.conferir(self.reg(expressao="20^2 - pi*20^2/4 = 85,84", tolerancia=0.0001), {})
        self.assertFalse(r["ok"])

    def test_no_texto_e_sem_decimais(self):
        r = ca.conferir(self.reg(no_texto=["974.355,00", "552.188"]),
                        {"p.md": "O remanescente de 552.188 m² e o total de 974.355 m²."})
        self.assertTrue(r["ok"])
        r = ca.conferir(self.reg(no_texto=["974.355"]), {"p.md": "O total foi 974.000 m²."})
        self.assertFalse(r["ok"])
        self.assertIn("p.md", r["itens"][0]["faltando_no_texto"])

    def test_nao_no_texto(self):
        r = ca.conferir(self.reg(nao_no_texto=["proporção de 66%"]), {"p.md": "na proporção de 66% e 34%"})
        self.assertFalse(r["ok"])

    def test_cli_codigos(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(json.dumps(self.reg()), encoding="utf-8")
            self.assertEqual(ca.main(["--verificacoes", str(p)]), 0)
            p.write_text(json.dumps(self.reg(expressao="1 + 1 = 3")), encoding="utf-8")
            self.assertEqual(ca.main(["--verificacoes", str(p)]), 1)
            self.assertEqual(ca.main(["--verificacoes", str(Path(d) / "nao_existe.json")]), 2)


if __name__ == "__main__":
    unittest.main()
