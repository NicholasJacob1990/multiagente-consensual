import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402
import pre_auditoria_parecer as pa  # noqa: E402

GENES = dict(pa.PERFIS["genes"])


def regra(achados, r, sev=None):
    return [a for a in achados if a.regra == r and (sev is None or a.severidade == sev)]


def md(*linhas):
    return pm.parse("\n\n".join(linhas))


EMENTA4 = ["EMENTA", "DIREITO CIVIL. ENFITEUSE.",
           "1. Caso sob exame: consulta sobre lotes.",
           "2. Questões em discussão: (i) extinção; (ii) escritura.",
           "3. Razões conclusivas: prudência ativa.",
           "4. Resposta objetiva aos quesitos: (i) não; (ii) não."]
FRASE_60 = " ".join(["palavra"] * 60) + "."
FRASE_90 = " ".join(["palavra"] * 90) + "."


class TestClassicoForense(unittest.TestCase):
    def test_ementa_estruturada_completa_e_incompleta(self):
        d = md(*EMENTA4, "## I. Relatório", "5. Trata-se de consulta.")
        self.assertFalse(regra(pa.checar_ementa_estruturada(d, True, "classico"), "estilo"))
        d = md("EMENTA", "DIREITO CIVIL.", "1. Caso sob exame: consulta.", "## I. Relatório", "2. Trata-se.")
        a = pa.checar_ementa_estruturada(d, True, "classico")
        self.assertIn("incompleta", a[0].mensagem)
        d = md("EMENTA", "DIREITO CIVIL.", "## I. Relatório", "1. Trata-se.")
        self.assertIn("quatro itens", pa.checar_ementa_estruturada(d, True, "classico")[0].mensagem)

    def test_transcricao_de_ementa_liberada_no_classico_mesmo_com_perfil_que_veda(self):
        d = md(*EMENTA4, "## II. Fundamentação", "5. Confira-se o entendimento do Tribunal:",
               "EMENTA: APELAÇÃO CÍVEL. AFORAMENTO. " + " ".join(["texto"] * 50),
               "- Continuação da ementa transcrita.", "6. O precedente reforça a tese.")
        cfg = dict(GENES, estilo="classico")
        self.assertFalse(regra(pa.auditar(d, cfg), "transcricao"))
        # segunda transcrição na mesma seção: alerta
        d2 = md(*EMENTA4, "## II. Fundamentação", "5. Confira-se:", "EMENTA: A. " + " ".join(["t"] * 50),
                "6. Comentário.", "7. Confira-se ainda:", "EMENTA: B. " + " ".join(["t"] * 50), "8. Fecho.")
        self.assertEqual(len(regra(pa.auditar(d2, cfg), "transcricao")), 1)
        # no executivo o perfil continua vedando
        a = regra(pa.auditar(d, dict(GENES, estilo="executivo")), "transcricao")
        self.assertTrue(a and "veda" in a[0].mensagem)

    def test_ementa_do_proprio_parecer_nao_conta_como_transcricao_nem_estoura_teto(self):
        longa = "DIREITO CIVIL. " + " ".join(["VERBETE."] * 150)
        d = md("EMENTA", longa, *EMENTA4[2:], "## I. Relatório", "5. Trata-se.")
        a = pa.auditar(d, dict(GENES, estilo="classico"))
        self.assertFalse(regra(a, "transcricao"))
        self.assertFalse(regra(a, "palavras"))

    def test_rotulos_variantes_sem_negrito_valem_no_classico(self):
        concl = ["## III. Conclusão", "10. Em síntese.",
                 "11. a) Correções e definições prioritárias: definir a titularidade;",
                 "12. b) Obrigações jurídicas incidentes: preservar os registros;",
                 "13. c) Recomendações facultativas: reunião técnica;",
                 "14. d) Providências a cargo de terceiros e áreas internas: traslados.",
                 "15. É o parecer, sob censura."]
        d = md(*EMENTA4, "## I. Relatório", "5. Trata-se.", *concl)
        self.assertFalse(regra(pa.auditar(d, dict(GENES, estilo="classico")), "conclusao"))
        # sem o estilo clássico, o perfil continua exigindo negrito
        self.assertEqual(len(regra(pa.auditar(d, dict(GENES)), "conclusao")), 4)

    def test_fecho_e_assinatura_em_negrito_e_numerados(self):
        d = md("## I. Relatório", "1. Trata-se.", "## II. Conclusão",
               "2. **Correções necessárias.** x", "3. **Obrigações já incidentes.** x",
               "4. **Recomendações facultativas.** x", "5. **Providências fora do regulamento.** x",
               "6. É o parecer, sob censura.", "Belo Horizonte, 1º de janeiro de 2026.",
               "**[Nome do(a) Advogado(a)]**", "OAB/MG [INFORMAR]", "De acordo: [Gerente da GENES]",
               "**Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)**")
        a = pa.auditar(d, dict(GENES))
        self.assertFalse(regra(a, "fecho"))
        self.assertFalse(regra(a, "assinatura"))
        self.assertFalse(regra(a, "marcador"))


class TestMedidasDeEstilo(unittest.TestCase):
    def test_frase_longa_por_estilo_e_parenteses_fora_da_conta(self):
        d = md("## I. Relatório", "1. " + FRASE_60, "2. Curta e direta.")
        self.assertTrue([x for x in pa.checar_frases_estilo(d, 30, 50, "executivo") if x.paragrafo])
        self.assertFalse([x for x in pa.checar_frases_estilo(d, 45, 80, "classico") if x.paragrafo])
        d = md("## I. Relatório", "1. " + FRASE_90)
        self.assertTrue([x for x in pa.checar_frases_estilo(d, 45, 80, "classico") if x.paragrafo])
        cit = "1. O título existe (" + " ".join(["fonte"] * 70) + ") e basta."
        self.assertFalse([x for x in pa.checar_frases_estilo(md("## I", cit), 30, 50, "executivo") if x.paragrafo])

    def test_intensificadores_fora_de_aspas(self):
        d = md("## I. Relatório", "1. Há manifesto conflito de fólio e demonstração inequívoca.",
               "2. A lei fala em “manifesta desproporção”.", "3. Há inconsistência a apurar.")
        a = pa.checar_intensificadores(d)
        self.assertEqual([x.paragrafo for x in a], [1])
        self.assertIn("manifesto", a[0].mensagem)

    def test_numeracao_ausente_bloqueia_no_perfil(self):
        d = md("## I. Relatório", "Trata-se de consulta.", "Outro parágrafo sem número.")
        self.assertTrue(regra(pa.auditar(d, dict(GENES)), "numeracao", "bloqueante"))
        self.assertFalse(regra(pa.auditar(d, dict(pa.PERFIS["generico"])), "numeracao", "bloqueante"))

    def test_resposta_objetiva_antes_do_relatorio(self):
        d = md("EMENTA", "DIREITO CIVIL.", "**Resposta objetiva.** Não dar baixa.", "## I. Relatório",
               "1. Trata-se de consulta.", "2. Segue.")
        a = pa.checar_resposta_objetiva(d, True, "executivo")
        self.assertFalse([x for x in a if x.severidade == "bloqueante"])
        self.assertTrue([x for x in a if x.severidade == "alerta" and "sem número" in x.mensagem])
        d = md("## I. Relatório", "1. **Resposta objetiva.** Não dar baixa.", "2. Trata-se.")
        self.assertFalse(pa.checar_resposta_objetiva(d, True, "executivo"))

    def test_exige_anexo(self):
        d = md("## I. Relatório", "1. Trata-se.")
        self.assertTrue(regra(pa.auditar(d, {"exige_anexo": True}), "anexo", "bloqueante"))
        d = md("## I. Relatório", "1. Trata-se.", "## IX. Anexo Único: Minuta de Requerimento", "1. Requer.")
        self.assertFalse(regra(pa.auditar(d, {"exige_anexo": True}), "anexo"))


if __name__ == "__main__":
    unittest.main()
