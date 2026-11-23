#!/usr/bin/env python3
"""Testes de conferir_achados_externos.py com .docx sintético mínimo (zipfile + XML).

    python3 -m unittest test_conferir_achados_externos -v

Cobre: deslocamento sistemático de −1 (auditor que não contou o §1 com rótulo em negrito),
erro real detectado com sugestão do parágrafo certo, localização por rótulo ("quadro, item a"),
hash divergente (declarado abreviado e entregue) e códigos de saída.

Com ``FIXTURES_FASE3=/caminho`` (v18_clean.docx e grok_achados_remissao.json), roda também o
caso real: deslocamento −1 na maioria dos 12 achados, nenhum erro real e aviso de outra cópia.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import conferir_achados_externos as ca  # noqa: E402

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NUMBERING = f"""<w:numbering xmlns:w="{W_NS}">
<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/><w:lvlText w:val="%1."/></w:lvl></w:abstractNum>
<w:abstractNum w:abstractNumId="3"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="•"/></w:lvl></w:abstractNum>
<w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>
<w:num w:numId="3"><w:abstractNumId w:val="3"/></w:num>
</w:numbering>"""


def r(texto: str, negrito: bool = False) -> str:
    return f'<w:r>{"<w:rPr><w:b/></w:rPr>" if negrito else ""}<w:t xml:space="preserve">{texto}</w:t></w:r>'


def p(*runs: str, num: str | None = None) -> str:
    ppr = f'<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr></w:pPr>' if num else ""
    return f"<w:p>{ppr}{''.join(runs)}</w:p>"


def montar_docx(path: Path, corpo: str) -> None:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')
        z.writestr("word/numbering.xml", NUMBERING)


CORPO = "".join([
    p(r("PARECER", negrito=True)),
    p(r("Resposta objetiva.", negrito=True), r(" Não se deve dar baixa nos lotes agora."), num="1"),  # §1
    p(r("A enfiteuse de 1971 cedeu o domínio útil dos lotes à Gama."), num="1"),  # §2
    p(r("A cláusula de rescisão por paralisação industrial não se confunde com a falência da Gama."), num="1"),  # §3
    p(r("A coadjudicação ao BDX impede a confusão integral dos domínios."), num="1"),  # §4
    p(r("As indisponibilidades averbadas na matrícula exigem cautela e transporte da carga."), num="1"),  # §5
    p(r("A duplicidade de matrículas segue a autotutela do art. 440-BG do Código Nacional de Normas."), num="1"),  # §6
    p(r("Como dito no parágrafo 3, a falência não prova a paralisação."), num="1"),  # §7
    p(r("Síntese.", negrito=True), r(" Como antecipado no parágrafo 1, nada se baixa agora."), num="1"),  # §8
    p(r("Quanto às restrições, ver o parágrafo 5."), num="1"),  # §9
    p(r("A divisão com o banco estadual foi tratada no parágrafo 2."), num="1"),  # §10: erro real (é o §4)
    p(r("Quadro de hipóteses.", negrito=True), r(" A resposta depende da hipótese comprovada:")),
    p(r("a) Domínio da companhia —", negrito=True), r(" favorecida pelo parágrafo 6.")),
    p(r("b) Domínio do Estado —", negrito=True), r(" ver o parágrafo 4.")),
    p(r("Diligência: certidão integral."), num="3"),
    p(r("É o parecer."), num="1"),  # §11
])

# auditor que não contou o §1: o §N dele é o §(N+1) do documento (k = −1)
ACHADOS_DESLOCADOS = [
    {"onde": "§6", "remete": [3], "assunto_em": [2], "assunto": "cláusula de rescisão por paralisação; falência"},
    {"onde": "§7", "remete": [1], "assunto_em": [], "assunto": "resposta objetiva"},
    {"onde": "parágrafo 8", "remete": [5], "assunto_em": [4], "assunto": "indisponibilidades averbadas"},
    {"onde": "quadro, item a", "remete": [6], "assunto_em": [5], "assunto": "duplicidade e autotutela"},
]
ERRO_REAL = {"onde": "§9", "remete": [2], "assunto_em": [3], "assunto": "coadjudicação ao BDX"}


class ConferirTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.docx = self.dir / "v1.docx"
        montar_docx(self.docx, CORPO)
        self.sha = hashlib.sha256(self.docx.read_bytes()).hexdigest()

    def tearDown(self):
        self.tmp.cleanup()

    def conferir(self, achados: list[dict], declarado: str | None = None, entregue: str | None = None) -> dict:
        return ca.conferir(self.docx, {"auditor": "Auditor", "sha256_declarado": declarado, "achados": achados}, entregue)

    def test_deslocamento_sistematico_menos_um(self):
        r = self.conferir(ACHADOS_DESLOCADOS, declarado=self.sha)
        self.assertEqual(r["deslocamento"]["k"], -1)
        self.assertEqual(r["deslocamento"]["texto"], "deslocamento sistemático de −1 em 4 de 4 achados")
        self.assertEqual([a["veredito"] for a in r["achados"]], ["correta (auditor deslocado em −1)"] * 4)
        self.assertEqual([a["onde_documento"] for a in r["achados"][:3]], ["§7", "§8", "§9"])
        self.assertIn("a) Domínio da companhia", r["achados"][3]["onde_documento"])
        self.assertEqual(r["resumo"], {"correta": 4, "erro real": 0, "inconclusivo": 0})
        self.assertEqual(r["hash"]["avisos"], [])

    def test_erro_real_detectado(self):
        r = self.conferir(ACHADOS_DESLOCADOS + [ERRO_REAL])
        self.assertEqual(r["deslocamento"]["texto"], "deslocamento sistemático de −1 em 4 de 5 achados")
        erro = r["achados"][-1]
        self.assertEqual(erro["onde_documento"], "§10")
        self.assertEqual(erro["veredito"], "erro real (o destino citado não trata do assunto; sugere §4)")
        self.assertEqual(erro["sugestao"], 4)
        self.assertEqual(r["resumo"]["erro real"], 1)

    def test_nao_localizado_e_inconclusivo(self):
        r = self.conferir([{"onde": "§40", "remete": [3], "assunto_em": [], "assunto": "rescisão"},
                           {"onde": "anexo, item z", "remete": [3], "assunto_em": [], "assunto": "rescisão"}])
        self.assertEqual([a["veredito"] for a in r["achados"]], ["inconclusivo", "inconclusivo"])
        self.assertEqual(r["deslocamento"]["k"], None)

    def test_sem_deslocamento(self):
        r = self.conferir([{"onde": "§7", "remete": [3], "assunto_em": [3], "assunto": "rescisão por paralisação"}])
        self.assertEqual(r["deslocamento"]["k"], 0)
        self.assertEqual(r["achados"][0]["veredito"], "correta")

    def test_hash_divergente(self):
        r = self.conferir(ACHADOS_DESLOCADOS, declarado="9b2c0e20…e466e5", entregue=self.sha)
        self.assertFalse(r["hash"]["declarado_confere"])
        self.assertTrue(r["hash"]["documento_e_o_entregue"])
        self.assertTrue(any("o auditor leu outra cópia" in a for a in r["hash"]["avisos"]))
        # abreviado que confere (prefixo e sufixo, com "…" ou "...")
        for decl in (f"{self.sha[:8]}…{self.sha[-6:]}", f"{self.sha[:8]}...{self.sha[-6:]}"):
            r = self.conferir(ACHADOS_DESLOCADOS, declarado=decl)
            self.assertTrue(r["hash"]["declarado_confere"], decl)
            self.assertEqual(r["hash"]["avisos"], [])
        # documento conferido diferente do entregue
        r = self.conferir(ACHADOS_DESLOCADOS, declarado=self.sha, entregue="0" * 64)
        self.assertFalse(r["hash"]["documento_e_o_entregue"])
        self.assertTrue(any("não é o entregue" in a for a in r["hash"]["avisos"]))
        # sem declaração
        r = self.conferir(ACHADOS_DESLOCADOS)
        self.assertTrue(any("não declarou" in a for a in r["hash"]["avisos"]))

    def test_cli_codigos_de_saida_e_saidas(self):
        achados = self.dir / "a.json"
        js, md = self.dir / "r.json", self.dir / "r.md"

        def rodar(*args) -> int:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                return ca.main(list(args))

        achados.write_text(json.dumps({"auditor": "X", "sha256_declarado": "9b2c0e20…e466e5",
                                       "achados": ACHADOS_DESLOCADOS}), encoding="utf-8")
        self.assertEqual(rodar("--documento", str(self.docx), "--achados", str(achados), "--sha256-entregue", self.sha,
                               "--json", str(js), "--md", str(md)), 0)
        texto = md.read_text(encoding="utf-8")
        self.assertIn("| achado | onde (auditor → documento) | remete | veredito | motivo |", texto)
        self.assertIn("| §6 → §7 |", texto)
        self.assertIn("o auditor leu outra cópia", texto)
        self.assertEqual(json.loads(js.read_text(encoding="utf-8"))["deslocamento"]["k"], -1)

        achados.write_text(json.dumps({"auditor": "X", "achados": ACHADOS_DESLOCADOS + [ERRO_REAL]}), encoding="utf-8")
        self.assertEqual(rodar("--documento", str(self.docx), "--achados", str(achados)), 1)

        achados.write_text("{não é json", encoding="utf-8")
        self.assertEqual(rodar("--documento", str(self.docx), "--achados", str(achados)), 2)
        self.assertEqual(rodar("--documento", str(self.dir / "falta.docx"), "--achados", str(achados)), 2)
        self.assertEqual(rodar("--documento", str(self.docx)), 2)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE3"), "defina FIXTURES_FASE3 para rodar com o caso real")
class CasoRealTests(unittest.TestCase):
    def test_v18_grok(self):
        base = Path(os.environ["FIXTURES_FASE3"])
        achados = json.loads((base / "grok_achados_remissao.json").read_text(encoding="utf-8"))
        real = "88a17626ff6f9fe35e8877ddb9e429d824e666685738bb5234497b5f1f6b7bdb"
        r = ca.conferir(base / "v18_clean.docx", achados, real)
        self.assertEqual(r["deslocamento"]["k"], -1)
        self.assertGreater(r["deslocamento"]["achados_consistentes"], len(achados["achados"]) // 2)
        self.assertEqual(r["resumo"]["erro real"], 0)
        self.assertTrue(any("o auditor leu outra cópia" in a for a in r["hash"]["avisos"]))


if __name__ == "__main__":
    unittest.main()
