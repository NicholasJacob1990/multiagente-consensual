#!/usr/bin/env python3
"""Testes de conferir_atribuicao.py: termos sem lastro, lastro fraco, quesitos acrescentados e omitidos.

    python3 -m unittest test_conferir_atribuicao -v

O teste com o caso real (CI nº 108/2026, relatório sugerido por terceiro e v21) só roda com
``FIXTURES_FASE3=/caminho/da/pasta``; as fixtures não fazem parte do plugin.
"""

from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import conferir_atribuicao as ca

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

FONTE = """Comunicação Interna nº 10/2026

Em levantamento patrimonial, identificou-se que os lotes 01 e 10 permanecem vinculados à matrícula de origem,
em nome da antiga CDX/UF. O Governador do Estado outorgou a escritura de aforamento.

A equipe compareceu ao Cartório e foi informada de que seria necessária a lavratura de nova escritura pública.

1. Os efeitos jurídicos da adjudicação judicial de 1982 sobre os lotes, inclusive quanto à eventual
subsistência do domínio direto e à necessidade de formalização do resgate.

2. A necessidade e a viabilidade jurídica da lavratura de nova escritura pública, conforme orientação verbal
prestada pelo Cartório, ou a possibilidade de adoção de procedimento administrativo ou registral específico
para regularização.

3. A possibilidade de requerimento administrativo ao Cartório para eventual retificação ou averbação cabível,
observados os direitos dos titulares constantes da matrícula nº 9.876 e os efeitos das indisponibilidades
registradas.

O objetivo é regularizar a situação registral sem novo ato de disposição patrimonial antes da definição da
efetiva situação jurídica.
"""

FIEL = (
    "2. Segundo a consulente, a equipe compareceu ao cartório e foi informada de que seria necessária nova "
    "escritura pública. Daí os três quesitos: primeiro, os efeitos da adjudicação de 1982, inclusive quanto à "
    "eventual subsistência do domínio direto e à necessidade de resgate; segundo, a necessidade e a viabilidade "
    "da nova escritura sugerida, ou de procedimento administrativo ou registral específico; e terceiro, o "
    "cabimento de requerimento administrativo para eventual retificação ou averbação, respeitados os direitos "
    "dos titulares da Matrícula nº 9.876 e os efeitos das indisponibilidades registradas.\n"
)

INFIEL = (
    "Segundo relata a consulente, a desincorporação dos lotes dependeria de nova escritura.\n\n"
    "A GEPAT submeteu três quesitos: primeiro, sobre os efeitos da adjudicação de 1982, inclusive quanto à "
    "necessidade de resgate; segundo, sobre a viabilidade da nova escritura; e terceiro, sobre o cabimento de "
    "requerimento de retificação ou averbação, considerando as indisponibilidades ativas e a divergência de área "
    "física.\n\n"
    "Adota-se como premissa a diretriz fixada pela própria consulente: nenhum ato de disposição deve ser "
    "praticado, evitando-se riscos à governança e encargos.\n"
)


def docx(path: Path, paragrafos: list[str]) -> None:
    corpo = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>" for t in paragrafos)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.fonte = self.dir / "ci.md"
        self.fonte.write_text(FONTE, encoding="utf-8")
        self.cfg = ca.config()
        self.f = ca.preparar_fonte(FONTE, self.cfg)

    def tearDown(self):
        self.tmp.cleanup()

    def arq(self, nome: str, texto: str) -> Path:
        p = self.dir / nome
        p.write_text(texto, encoding="utf-8")
        return p

    def conferir(self, texto: str) -> list[ca.Atribuicao]:
        return ca.conferir(self.f, ca.ler_paragrafos(self.arq("t.md", texto)), "t.md", self.cfg)

    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = ca.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()


class VocabularioTests(Base):
    def test_graus(self):
        v = ca.Vocabulario("Governador do Estado; obrigação; obtenção de certidões; vendeu", self.cfg)
        self.assertEqual(v.grau("governanca"), "fraco")
        self.assertEqual(v.grau("governador"), "forte")
        self.assertEqual(v.grau("obrigacoes"), "forte")  # plural
        self.assertEqual(v.grau("certidao"), "forte")
        self.assertEqual(v.grau("obter"), "forte")  # infinitivo curto acha "obtenção"
        self.assertEqual(v.grau("vendidos"), "forte")  # particípio acha "vendeu"
        self.assertEqual(v.grau("encargos"), "nenhum")

    def test_termos_sem_stopwords_e_sem_citacao(self):
        ts = ca.termos("A consulente pede análise dos imóveis da matrícula (SEI 100000002, p. 488) e da desincorporação.", self.cfg)
        self.assertEqual(ts, ["desincorporacao"])

    def test_lista_de_quesitos_da_fonte(self):
        self.assertEqual(len(self.f.listas), 1)
        self.assertEqual(len(self.f.listas[0]), 3)
        self.assertTrue(self.f.listas[0][1].startswith("A necessidade e a viabilidade"))


class AtribuicaoTests(Base):
    def test_texto_fiel_sem_acusacao(self):
        ats = self.conferir(FIEL)
        self.assertEqual(len(ats), 2)
        self.assertEqual([a.acusacoes for a in ats], [0, 0], [(a.termos, a.omissoes) for a in ats])

    def test_texto_infiel(self):
        ats = self.conferir(INFIEL)
        termos = {t.termo: t for a in ats for t in a.termos}
        for t in ("desincorporacao", "ativas", "divergencia", "fisica", "riscos", "encargos"):
            self.assertEqual(termos[t].grau, "sem_lastro", t)
        self.assertEqual(termos["governanca"].grau, "lastro_fraco")
        self.assertEqual({termos[t].quesito for t in ("ativas", "divergencia", "fisica")}, {3})
        omissoes = {(o.quesito, o.tipo) for a in ats for o in a.omissoes}
        self.assertEqual(omissoes, {(1, "ressalva"), (2, "alternativa"), (3, "qualificador"), (3, "ressalva")})
        alternativa = next(o for a in ats for o in a.omissoes if o.tipo == "alternativa")
        self.assertIn("procedimento administrativo ou registral especifico", alternativa.trecho_fonte)
        self.assertNotIn("observados", next(o for a in ats for o in a.omissoes if o.quesito == 3 and o.tipo == "ressalva").termos_omitidos)

    def test_frase_nao_atribuida_fica_de_fora(self):
        self.assertEqual(self.conferir("A desincorporação dos lotes é providência posterior.\n"), [])

    def test_termo_acrescentado_ao_quesito(self):
        ats = self.conferir("Os quesitos formulados: 1. os efeitos da adjudicação e do aforamento; 2. a viabilidade da nova "
                            "escritura, ou de procedimento administrativo ou registral específico.\n")
        acrescentados = [t for a in ats for t in a.termos if t.grau == "acrescentado_ao_quesito"]
        self.assertEqual([(t.termo, t.quesito) for t in acrescentados], [("aforamento", 1)])
        self.assertEqual(acrescentados[0].nota, "consta em outra parte da fonte")

    def test_concessiva_so_confere_a_oracao_atribuida(self):
        ats = self.conferir("Embora a CI relate a lavratura de nova escritura, o parecer recomenda prudência quanto aos encargos.\n")
        self.assertEqual(len(ats), 1)
        self.assertEqual(ats[0].acusacoes, 0)

    def test_segundo_no_meio_da_frase(self):
        ats = self.conferir("O exame começa pela cronologia, cuja origem é a matrícula de origem, segundo a consulente: "
                            "lotes vinculados à antiga CDX/UF.\n")
        self.assertEqual(ats[0].acusacoes, 0, ats[0].termos)

    def test_config_extra(self):
        cfg = ca.config({"atribuicao_extra": [r"\bo requerente alega\b"], "stopwords_extra": ["desincorporação"],
                         "equivalencias": [["encargos", "efeitos"]]})
        f = ca.preparar_fonte(FONTE, cfg)
        ats = ca.conferir(f, ca.ler_paragrafos(self.arq("t.md", "O requerente alega desincorporação e encargos.\n")), "t.md", cfg)
        self.assertEqual(len(ats), 1)
        self.assertEqual(ats[0].termos, [])


class CliTests(Base):
    def test_codigos_json_e_md(self):
        infiel, fiel = self.arq("infiel.md", INFIEL), self.arq("fiel.md", FIEL)
        code, out, _ = self.cli("--fonte", self.fonte, infiel, "--json", self.dir / "a.json", "--md", self.dir / "a.md")
        self.assertEqual(code, 1)
        self.assertIn("desincorporacao: sem lastro na fonte", out)
        self.assertIn("OMISSÃO no quesito 2 (alternativa)", out)
        dados = json.loads((self.dir / "a.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(dados["resumo"]["omissoes"], 4)
        self.assertIn("# Conferência de atribuição", (self.dir / "a.md").read_text(encoding="utf-8"))
        code, out, _ = self.cli("--fonte", self.fonte, fiel)
        self.assertEqual(code, 0, out)
        self.assertIn("nada atribuído à fonte sem lastro", out)

    def test_json_no_stdout(self):
        code, out, _ = self.cli("--fonte", self.fonte, self.arq("infiel.md", INFIEL), "--json")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["fonte"], "ci.md")

    def test_paragrafos_e_docx(self):
        p = self.dir / "parecer.docx"
        docx(p, ["Segundo a consulente, a desincorporação depende de escritura."])
        code, out, _ = self.cli("--fonte", self.fonte, p)
        self.assertEqual(code, 1)
        self.assertIn("desincorporacao", out)
        md = self.arq("p.md", "1. Segundo a consulente, a desincorporação depende de escritura.\n\n2. Texto neutro.\n")
        code, out, _ = self.cli("--fonte", self.fonte, md, "--paragrafos", "2-3")
        self.assertEqual(code, 0)
        self.assertIn("frases atribuídas: 0", out)

    def test_erros(self):
        self.assertEqual(self.cli("--fonte", self.dir / "nao.md", self.fonte)[0], 2)
        self.assertEqual(self.cli("--fonte", self.fonte, self.fonte, "--paragrafos", "x")[0], 2)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE3"), "defina FIXTURES_FASE3 com a pasta das fixtures reais")
class CasoRealTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(os.environ["FIXTURES_FASE3"])
        self.cfg = ca.config()
        self.fonte = ca.preparar_fonte(ca.ler_fonte(self.dir / "CI_108_2026_pp485-489.md"), self.cfg)

    def test_relatorio_sugerido(self):
        ats = ca.conferir(self.fonte, ca.ler_paragrafos(self.dir / "relatorio_sugerido.md"), "rel", self.cfg)
        termos = {t.termo for a in ats for t in a.termos}
        for t in ("desincorporacao", "governanca", "encargos", "divergencia", "fisica", "ativas"):
            self.assertIn(t, termos)
        alternativas = [o for a in ats for o in a.omissoes if o.quesito == 2 and o.tipo == "alternativa"]
        self.assertTrue(any("procedimento administrativo ou registral especifico" in o.trecho_fonte for o in alternativas))

    def test_v21_paragrafos_2_a_9(self):
        filtro = ca.filtro_paragrafos("2-9")
        pars = [p for p in ca.ler_paragrafos(self.dir / "v21_clean.docx") if filtro(p)]
        ats = ca.conferir(self.fonte, pars, "v21", self.cfg)
        self.assertGreaterEqual(len(ats), 6)
        self.assertLessEqual(sum(a.acusacoes for a in ats), 2, [(a.local, a.termos, a.omissoes) for a in ats if a.acusacoes])


if __name__ == "__main__":
    unittest.main()
