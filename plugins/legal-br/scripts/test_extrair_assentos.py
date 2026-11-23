#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes de extrair_assentos.py com certidão SINTÉTICA (nomes, números e
cartório fictícios; só a estrutura imita uma certidão real com OCR ruim).

    python3 -m unittest -v test_extrair_assentos      (na pasta scripts/)
"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import extrair_assentos as ea  # noqa: E402

CERTIDAO = """\
## Página 1 — Certidão fictícia

_Leitura: OCR novo._

Valide aqui
este documento
[9.8]
(06)
<L
O
-
“t+

Cartório Fictício de Registro de Imóveis de Vila Exemplo

CERTIFICO, a requerimento da parte interessada, que revendo os livros deste
cartório verifiquei constar a Matrícula nº 4321, Folha 7, Livro 2-3-BX, continuação no
Livro 2-RG - Sistema de Fichas, Código Nacional de Matrícula nº 012345.2.0004321-10
datada de 05/06/1990, da qual segue o seu teor na integra:

4321 - 05/06/1990

IMÓVEL: Um terreno com a área de 20.000m? situado no Bairro Modelo. PROPRIETÁRIA:
Empresa Fictícia de Loteamentos S/A, com sede na Rua Imaginária, 100, CNPJ nº
00.000.000/0001-00; REGISTRO ANTERIOR: Matrícula 1.234, fls. 56, L° nº
2-1-ZZ, deste Cartório.

R-1-4321 - 05/06/1990
Prot. 12.345 de 05/06/90: LOTEAMENTO: Conforme requerimento, o terreno foi
subdividido em lotes, assim descritos:
Quadra 01 01- 1.000,00m²- ////////////////////////////////////////
02- 2.000,00m?- Transfere à Alfa Comércio Ltda, conf. regt° 1.111 fls. 22 L° 3-A.
Quadra 02.

01- 3.000,00m?-

Transfere a Beta Indústria S/A, conf. reg. n/Cartório sob o nº 01-
2.222 fls. 33 Lº 2-1-BB.
(4)
=.
02-A- 1.500,00m²- Transfere a digo, Veja-se matrícula nº 3.333 fls. 44 Lº 2-2-CC.
03- 1.250,50m?;

XQRRTTZ ZZ

04- 2.500,00m?-
Página 1 de 2

---

## Página 2 — Certidão fictícia

Cartório Fictício de Registro de Imóveis de Vila Exemplo
Av. Central, n.º 1, Centro
05-
4.000,00m²- Transfere ao Gama Ltda, Conf. regtº 4.444 fls. 55 Lº 3-D.
06- 1.000,00m²- Transfere à Delta S/A, conf.
Página 2 de 3
Cartório Fictício de Registro de Imóveis de Vila Exemplo
regtº 5.555 fls. 66 Lº 3-E.
07- 900,00m2- Transfere à Épsilon Ltda
Dou fé: (assinatura).

AV-2-4321 - 10/10/2020 - Protocolo: 99999 - 01/10/2020

TRANSFERÊNCIA- Transfere o lote nº. 01, da quadra nº. 01, para a matrícula 50.000,
Livro 2-RG - Sistema de Fichas, desta Serventia. Dou fé.

CERTIFICO MAIS, que o lote nº 01, da quadra nº 02, possui os seguintes limites.
"""


def _lote(res, q, l):
    return next(x for x in res["quadras"][q] if x["lote"] == l)


class TestCabecalhoEAtos(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = ea.extrair(CERTIDAO)

    def test_cabecalho(self):
        c = self.res["cabecalho"]
        self.assertEqual(c["matricula"], "4321")
        self.assertEqual(c["folha"], "7")
        self.assertEqual(c["livro"], "2-3-BX")
        self.assertEqual(c["continuacao"], "Livro 2-RG - Sistema de Fichas")
        self.assertEqual(c["cnm"], "012345.2.0004321-10")
        self.assertEqual(c["data_abertura"], "05/06/1990")
        self.assertEqual(c["registro_anterior"], "Matrícula 1.234 fls. 56 Lº 2-1-ZZ")
        self.assertEqual(c["proprietario"], "Empresa Fictícia de Loteamentos S/A")

    def test_atos(self):
        atos = {a["ato"]: a for a in self.res["atos"]}
        self.assertEqual(set(atos), {"R-1", "AV-2"})
        r1 = atos["R-1"]
        self.assertEqual((r1["data"], r1["protocolo"], r1["protocolo_data"]),
                         ("05/06/1990", "12.345", "05/06/90"))
        self.assertEqual(r1["natureza"], "LOTEAMENTO")
        av2 = atos["AV-2"]
        self.assertEqual((av2["protocolo"], av2["protocolo_data"]), ("99999", "01/10/2020"))
        self.assertEqual(av2["transferencias_lote"],
                         [{"lote": "01", "quadra": "01", "matricula_destino": "50.000"}])


class TestTabela(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.res = ea.extrair(CERTIDAO)

    def test_quadras_e_lotes(self):
        self.assertEqual(list(self.res["quadras"]), ["01", "02"])
        self.assertEqual([l["lote"] for l in self.res["quadras"]["02"]],
                         ["01", "02-A", "03", "04", "05", "06", "07"])

    def test_tracos_sem_nota_com_averbacao_posterior(self):
        l = _lote(self.res, "01", "01")
        self.assertEqual(l["status"], "sem_nota")
        self.assertEqual(l["area"], "1.000,00 m²")
        self.assertIn("SEM NOTA", l["nota"])
        self.assertEqual(l["averbacoes"], ["AV-2 (10/10/2020): matrícula 50.000"])

    def test_ocr_ruim_m_interrogacao_e_grau(self):
        l = _lote(self.res, "01", "02")
        self.assertEqual(l["area"], "2.000,00 m²")
        self.assertEqual(l["adquirente"], "Alfa Comércio Ltda")
        self.assertEqual(l["nota"], "regtº 1.111 fls. 22 Lº 3-A")

    def test_quebra_de_linha_entre_lote_e_nota_e_dentro_do_numero(self):
        l = _lote(self.res, "02", "01")
        d = l["destino"]
        self.assertEqual((d["tipo"], d["ato"], d["numero"], d["fls"], d["livro"]),
                         ("regtº", "01", "2.222", "33", "2-1-BB"))
        self.assertEqual(l["nota"], "regtº nº 01- 2.222 fls. 33 Lº 2-1-BB")
        self.assertEqual(l["adquirente"], "Beta Indústria S/A")

    def test_lote_com_letra_e_matricula(self):
        l = _lote(self.res, "02", "02-A")
        self.assertEqual(l["nota"], "matrícula nº 3.333 fls. 44 Lº 2-2-CC")
        self.assertIsNone(l["adquirente"])          # "Transfere a digo," não é nome

    def test_ilegivel(self):
        l = _lote(self.res, "02", "03")
        self.assertEqual(l["status"], "ilegivel")
        self.assertEqual(l["nota"], ea.ILEGIVEL)
        self.assertEqual(l["area"], "1.250,50 m²")

    def test_linha_vazia_antes_de_quebra_de_pagina(self):
        l = _lote(self.res, "02", "04")
        self.assertEqual(l["status"], "sem_nota")      # cabeçalho da página não vira nota
        self.assertNotIn("Cartório", l["nota_ocr"])

    def test_lote_e_area_em_linhas_separadas(self):
        l = _lote(self.res, "02", "05")
        self.assertEqual((l["area"], l["nota"]), ("4.000,00 m²", "regtº 4.444 fls. 55 Lº 3-D"))

    def test_nota_continua_depois_da_quebra_de_pagina(self):
        l = _lote(self.res, "02", "06")
        self.assertEqual(l["nota"], "regtº 5.555 fls. 66 Lº 3-E")
        self.assertEqual(l["adquirente"], "Delta S/A")

    def test_transfere_sem_assento(self):
        l = _lote(self.res, "02", "07")
        self.assertEqual(l["status"], "incompleta")
        self.assertIn(ea.ILEGIVEL, l["nota"])

    def test_destaque_sem_nota(self):
        chaves = [(s["quadra"], s["lote"], s["status"]) for s in self.res["sem_nota"]]
        self.assertEqual(chaves, [("01", "01", "sem_nota"), ("02", "03", "ilegivel"),
                                  ("02", "04", "sem_nota"), ("02", "07", "incompleta")])


class TestFuncoes(unittest.TestCase):
    def test_assento_variantes(self):
        casos = {
            "conf. regtº 77.001 fls. 12/13 Lº 3-Q.": ("regtº", None, "77.001", "12/13", "3-Q"),
            "Transfere para o nº 01- 8.765 fls. 9 Lº 2-1.XY.": ("", "01", "8.765", "9", "2-1-XY"),
            "Conf. regtº n/Cartório sob o nº 01- 6.000 fls. 146 do Lº nº 2-2-M.":
                ("regtº", "01", "6.000", "146", "2-2-M"),
        }
        for nota, esperado in casos.items():
            d = ea.parse_assento(ea.normalizar(nota))
            self.assertEqual((d["tipo"], d["ato"], d["numero"], d["fls"], d["livro"]), esperado, nota)

    def test_numero_duvidoso(self):
        d = ea.parse_assento("matrícula sob o nº 0112.345 fls. 2 Lº 2-1-AA")
        self.assertTrue(d["duvida"])
        self.assertIn("conferir", d["texto"])

    def test_classificacao(self):
        self.assertEqual(ea.classificar_nota("- //////")["status"], "sem_nota")
        self.assertEqual(ea.classificar_nota("")["status"], "sem_nota")
        self.assertEqual(ea.classificar_nota("~~ rr ;; kk")["status"], "ilegivel")


class TestCLI(unittest.TestCase):
    def _roda(self, *args):
        with tempfile.TemporaryDirectory() as td:
            cert = Path(td) / "certidao.md"
            cert.write_text(CERTIDAO, encoding="utf-8")
            saida = Path(td) / "saida.json"
            cmd = [sys.executable, str(AQUI / "extrair_assentos.py"), str(cert), *args]
            cmd = [c.replace("SAIDA", str(saida)) for c in cmd]
            p = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ})
            js = json.loads(saida.read_text(encoding="utf-8")) if saida.exists() else None
            return p, js

    def test_md_padrao(self):
        p, _ = self._roda()
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertIn("## Quadra 02", p.stdout)
        self.assertIn("## Lotes sem nota de transferência", p.stdout)
        self.assertIn("| 01 | 1.000,00 m² | SEM NOTA (////) |", p.stdout)

    def test_json_e_quadra(self):
        p, js = self._roda("--quadra", "1", "--json", "SAIDA")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(p.stdout, "")                     # só JSON, sem --md
        self.assertEqual(list(js["quadras"]), ["01"])
        self.assertEqual([s["lote"] for s in js["sem_nota"]], ["01"])
        self.assertEqual(js["cabecalho"]["cnm"], "012345.2.0004321-10")

    def test_md_e_json_juntos(self):
        p, js = self._roda("--md", "--json", "SAIDA", "--quadra", "02")
        self.assertIn("## Quadra 02", p.stdout)
        self.assertNotIn("## Quadra 01", p.stdout)
        self.assertEqual(list(js["quadras"]), ["02"])


if __name__ == "__main__":
    unittest.main()
