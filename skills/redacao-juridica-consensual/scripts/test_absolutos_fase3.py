#!/usr/bin/env python3
"""Testes da fase 3 do check ``absolutos`` de pre_auditoria_parecer.py: juízo de suficiência e escopo restrito.

Rodar na pasta ``scripts``::

    python3 -m unittest test_absolutos_fase3 -v

O teste com o caso real só roda com ``FIXTURES_FASE3=/caminho/da/pasta`` (``v21_clean.docx``);
as fixtures não fazem parte do plugin.
"""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

import parecer_md as pm
import pre_auditoria_parecer as pa

CABECALHO = "**PARECER JURÍDICO**\n\nPrezados colegas,\n\n## I. Exame\n\n"


def doc(*pars: str) -> pm.Documento:
    return pm.parse(CABECALHO + "\n\n".join(f"{i}. {t}" for i, t in enumerate(pars, start=1)) + "\n")


def absolutos(frase: str) -> list:
    return pa.checar_absolutos(doc(frase))


class SuficienciaENormaTests(unittest.TestCase):
    """O absoluto que rege verbo de suficiência ou permissão não afirma fato."""

    CASOS = [
        # as três frases reais da v21 (§§ 52, 55 e 107)
        "Nenhum indício basta sozinho: a cobrança de foros não prova a aquisição pela CDX/UF, nem a menção ao aforamento prova a subsistência do domínio direto.",
        "Nas passagens examinadas, porém, nenhum deles resolve especificamente a coadjudicação Estado–BDX.",
        "Nenhuma dessas vias autoriza a baixa unilateral de possível patrimônio público ou de direitos de terceiros.",
        "Nenhum documento isolado permite concluir pela consolidação.",
        "Nenhuma certidão dispensa a prova do título.",
        "Nenhum dos títulos impõe a nova escritura.",
        "Nenhuma das hipóteses exige baixa imediata.",
        "Nenhum registro pode ser cancelado sem ordem judicial.",
        "Nenhuma delas cabe na via administrativa.",
        "Nenhum averbamento substitui a escritura de resgate.",
        "Nenhum desses elementos, isoladamente, prova a quitação.",
        "Nenhum dos indícios bastam para afirmar o domínio.",
        "O resgate jamais pode ser presumido.",
    ]

    def test_nao_alerta(self):
        for c in self.CASOS:
            with self.subTest(c=c):
                self.assertEqual(absolutos(c), [])


class EscopoRestritoTests(unittest.TestCase):
    CASOS = [
        "Nas passagens examinadas, nenhum autor trata da coadjudicação.",
        "Neste exame, nenhum título posterior a 1986 menciona o domínio direto.",
        "Até o momento, nenhuma certidão da transcrição nº 6.700 foi obtida.",
        "Na documentação analisada, nenhum instrumento de resgate foi localizado.",
        "Nenhum documento nos autos indica a quitação do laudêmio.",
        "Nos autos, nenhum registro trata do resgate.",
        "Nos documentos examinados, todos os títulos se referem à Matrícula nº 9.876.",
    ]

    def test_nao_alerta(self):
        for c in self.CASOS:
            with self.subTest(c=c):
                self.assertEqual(absolutos(c), [])


class FatoAbsolutoTests(unittest.TestCase):
    """Afirmação de fato absoluta, sem citação, continua acusada."""

    CASOS = [
        ("O BDX nunca foi senhorio dos lotes.", "nunca"),
        ("Todos os lotes foram transmitidos à Delta.", "todos"),
        ("A CDI jamais cobrou foros dos lotes 01 e 10.", "jamais"),
        ("Nenhum lote foi transmitido antes de 1982.", "nenhum"),
        ("Nenhuma escritura de resgate foi lavrada.", "nenhuma"),
        ("Os títulos foram juntados nos autos em 2026, e o BDX nunca foi senhorio.", "nunca"),
        ("Nenhum indício basta sozinho, e o BDX nunca foi senhorio.", "nunca"),
    ]

    def test_alerta(self):
        for c, palavra in self.CASOS:
            with self.subTest(c=c):
                achados = absolutos(c)
                self.assertEqual(len(achados), 1, achados)
                self.assertIn(f"({palavra})", achados[0].mensagem)

    def test_suficiencia_nao_esconde_outro_absoluto_da_frase(self):
        achados = absolutos("Nenhuma dessas vias autoriza a baixa, e todos os lotes foram transmitidos.")
        self.assertEqual(len(achados), 1)
        self.assertIn("(todos)", achados[0].mensagem)
        self.assertNotIn("nenhuma", achados[0].mensagem.split("sem citação")[0])


@unittest.skipUnless(os.environ.get("FIXTURES_FASE3"), "defina FIXTURES_FASE3 com a pasta das fixtures reais")
class CasoRealV21Tests(unittest.TestCase):
    def test_v21_sem_alerta_de_absolutos(self):
        import docx_para_md

        origem = Path(os.environ["FIXTURES_FASE3"]) / "v21_clean.docx"
        with tempfile.TemporaryDirectory() as tmp:
            md = Path(tmp) / "v21.md"
            md.write_text(docx_para_md.converter(origem), encoding="utf-8")
            self.assertEqual(pa.checar_absolutos(pm.ler(md)), [])


if __name__ == "__main__":
    unittest.main()
