#!/usr/bin/env python3
"""Testes de checar_decisoes.py e da opção ``--decisoes`` de consolidar_correcoes.py.

    python3 -m unittest test_checar_decisoes -v

O teste com o registro real do caso só roda com ``FIXTURES_FASE3=/caminho/da/pasta``
(``decisoes_caso_SEI1790.json`` e ``v21_clean.docx``); as fixtures não fazem parte do plugin.
"""

from __future__ import annotations

import copy
import io
import json
import os
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import checar_decisoes as cd
import consolidar_correcoes as cc

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

REGISTRO = {
    "caso": "SEI 0000.01.0000001/2026-01 — lotes 01 e 10, quadra 04",
    "decisoes": [
        {"id": "D1", "tema": "requerente do anexo",
         "decisao": "CODEMIG como interessada (arts. 16 e 17 da LRP); não trocar para CODEMGE nem 'e/ou'",
         "padroes": ["codemge e/ou codemig", "codemig e/ou codemge", "trocar a requerente", "requerente.*codemge"],
         "data": "2026-11-03", "origem": "usuário"},
        {"id": "D2", "tema": "doutrina", "decisao": "autor-data no texto; nota de rodapé só por pedido",
         "padroes": ["nota de rodap", "notas de rodap"], "data": "2026-11-04", "origem": "usuário"},
        {"id": "D3", "tema": "quadro de hipóteses", "decisao": "alíneas sem numeração (@TXT)",
         "padroes": ["numerar (o quadro|as hip)"], "data": "2026-11-05", "origem": "perfil GENES"},
        {"id": "D4", "tema": "fecho", "decisao": "'É o parecer, sob censura.' (perfil GENES)", "padroes": ["sob censura"],
         "data": "2026-11-05", "origem": "perfil GENES"},
        {"id": "D5", "tema": "modo", "decisao": "perguntar sempre", "padroes": [], "data": "2026-11-04", "origem": "usuário"},
    ],
}

SUGESTOES = """1. No anexo, a requerente deveria ser "CODEMGE e/ou CODEMIG", para cobrir as duas companhias.
2. Sugiro passar a citação de Gomes (2019) para nota de rodapé.
3. Numerar as hipóteses do quadro facilitaria a remissão.
4. Retirar "sob censura" do fecho, que soa arcaico.
5. Fecho: É o parecer, sob censura.
6. Corrigir a remissão ao parágrafo 90.
"""


def docx(path: Path, paragrafos: list[str]) -> None:
    corpo = "".join(f"<w:p><w:r><w:t xml:space=\"preserve\">{t}</w:t></w:r></w:p>" for t in paragrafos)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f'<w:document xmlns:w="{W_NS}"><w:body>{corpo}</w:body></w:document>')


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.reg = self.json("decisoes.json", REGISTRO)

    def tearDown(self):
        self.tmp.cleanup()

    def json(self, nome: str, dados) -> Path:
        p = self.dir / nome
        p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        return p

    def texto(self, nome: str, t: str) -> Path:
        p = self.dir / nome
        p.write_text(t, encoding="utf-8")
        return p


class ChecarDecisoesTests(Base):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cd.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_sugestoes_que_reabrem(self):
        registro = cd.preparar(copy.deepcopy(REGISTRO))
        linhas = [(i, l) for i, l in enumerate(SUGESTOES.splitlines(), start=1)]
        acertos = cd.checar_linhas(registro, linhas, "sug.md")
        self.assertEqual([(a.linha, a.id) for a in acertos], [(1, "D1"), (2, "D2"), (3, "D3"), (4, "D4")])
        self.assertIn("não trocar para CODEMGE", acertos[0].decisao)
        self.assertEqual([d["id"] for d in registro["_sem_padrao"]], ["D5"])

    def test_texto_que_cumpre_a_decisao_nao_e_acusado(self):
        registro = cd.preparar(copy.deepcopy(REGISTRO))
        self.assertEqual(cd.casar_texto(registro, "É o parecer, sob censura."), [])
        self.assertEqual([d["id"] for d, _ in cd.casar_texto(registro, "Substituir «É o parecer, sob censura.» por «É o parecer.»")],
                         ["D4"])

    def test_forma_vedada_entre_aspas_nao_vale_como_cumprimento(self):
        registro = cd.preparar(copy.deepcopy(REGISTRO))
        self.assertEqual(registro["decisoes"][0]["_formas"], [])  # "nem 'e/ou'"
        self.assertEqual(registro["decisoes"][3]["_formas"], ["e o parecer sob censura"])
        self.assertEqual([d["id"] for d, _ in cd.casar_texto(registro, "Requerente: CODEMGE e/ou CODEMIG")], ["D1"])

    def test_ignorar_se(self):
        dados = copy.deepcopy(REGISTRO)
        dados["decisoes"][1]["ignorar_se"] = "a pedido do usuario"
        registro = cd.preparar(dados)
        self.assertEqual(cd.casar_texto(registro, "Doutrina em nota de rodapé, a pedido do usuário."), [])

    def test_cli_md_json_e_docx(self):
        sug = self.texto("sug.md", SUGESTOES)
        achados = self.json("achados.json", {"achados": [
            {"trecho_atual": "Requerente: CODEMGE", "sugestao": "Trocar a requerente para CODEMIG e/ou CODEMGE."},
            {"trecho_atual": "É o parecer, sob censura.", "sugestao": "Manter o fecho."}]})
        minuta = self.dir / "minuta.docx"
        docx(minuta, ["Requerente: CODEMIG, interessada nos termos dos arts. 16 e 17 da LRP.", "É o parecer, sob censura."])
        code, out, _ = self.cli("--decisoes", self.reg, sug, achados, minuta, "--json", self.dir / "a.json")
        self.assertEqual(code, 1)
        self.assertIn("decisão já tomada — reabrir?", out)
        self.assertIn("achados[0].sugestao", out)
        self.assertNotIn("minuta.docx:", out)
        self.assertNotIn("trecho_atual", out)
        dados = json.loads((self.dir / "a.json").read_text(encoding="utf-8"))
        self.assertEqual(len(dados["acertos"]), 5)
        code, out, _ = self.cli("--decisoes", self.reg, minuta)
        self.assertEqual(code, 0, out)
        self.assertIn("Sem padrão (não verificável aqui): D5", out)

    def test_modelo_vazio_e_erros(self):
        modelo = Path(__file__).resolve().parent / "decisoes_modelo.json"
        code, out, _ = self.cli("--decisoes", modelo, self.texto("sug.md", SUGESTOES))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.cli("--decisoes", self.json("ruim.json", {"decisoes": [{"id": "D1", "padroes": ["("],
                                                                                    "decisao": "x"}]}),
                                  self.texto("t.md", "x"))[0], 2)
        self.assertEqual(self.cli("--decisoes", self.json("sem.json", {"decisoes": [{"padroes": ["x"], "decisao": "y"}]}),
                                  self.texto("t.md", "x"))[0], 2)
        self.assertEqual(self.cli("--decisoes", self.reg, self.dir / "nao.md")[0], 2)


class ConsolidarComDecisoesTests(Base):
    def cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cc.main([str(a) for a in args])
        return code, out.getvalue(), err.getvalue()

    def test_proposta_que_reabre_decisao_sai_da_lista(self):
        props = self.json("revisor.json", [
            {"paragrafo": "Anexo", "trecho_atual": "Requerente: CODEMIG", "trecho_novo": "Requerente: CODEMGE e/ou CODEMIG",
             "tipo": "redacao", "justificativa": "cobrir as duas companhias"},
            {"paragrafo": 30, "trecho_atual": "(GOMES, 2019)", "trecho_novo": "¹", "tipo": "forma",
             "justificativa": "passar a doutrina para nota de rodapé"},
            {"paragrafo": 139, "trecho_atual": "É o parecer.", "trecho_novo": "É o parecer, sob censura.", "tipo": "forma",
             "justificativa": "fecho do perfil"},
            {"paragrafo": 90, "trecho_atual": "parágrafo 91", "trecho_novo": "parágrafo 90", "tipo": "remissao",
             "justificativa": "remissão errada"},
        ])
        final, rel = self.dir / "final.json", self.dir / "rel.md"
        code, out, _ = self.cli(props, "--decisoes", self.reg, "--saida", final, "--relatorio", rel)
        self.assertEqual(code, 0, out)
        self.assertIn("decisão já tomada: 2", out)
        dados = json.loads(final.read_text(encoding="utf-8"))
        self.assertEqual([c["trecho_novo"] for c in dados["correcoes"]], ["É o parecer, sob censura.", "parágrafo 90"])
        fora = dados["decisao_ja_tomada"]
        self.assertEqual([(c["status"], c["decisoes"][0]["id"]) for c in fora],
                         [("decisao_ja_tomada", "D1"), ("decisao_ja_tomada", "D2")])
        self.assertEqual(fora[1]["decisoes"][0]["campo"], "justificativa")
        texto = rel.read_text(encoding="utf-8")
        self.assertIn("## Decisão já tomada (fora da saída — reabrir?)", texto)
        self.assertIn("[D1] requerente do anexo", texto)

    def test_sem_decisoes_nao_muda_a_saida(self):
        props = self.json("revisor.json", [{"paragrafo": 1, "trecho_atual": "a", "trecho_novo": "nota de rodapé", "tipo": "x"}])
        final = self.dir / "final.json"
        self.assertEqual(self.cli(props, "--saida", final)[0], 0)
        self.assertEqual(set(json.loads(final.read_text(encoding="utf-8"))), {"correcoes"})

    def test_registro_passado_como_entrada_e_recusado(self):
        code, _, err = self.cli(self.reg, "--saida", self.dir / "final.json")
        self.assertEqual(code, 2)
        self.assertIn("--decisoes", err)


@unittest.skipUnless(os.environ.get("FIXTURES_FASE3"), "defina FIXTURES_FASE3 com a pasta das fixtures reais")
class CasoRealTests(unittest.TestCase):
    def test_registro_real(self):
        d = Path(os.environ["FIXTURES_FASE3"])
        registro = cd.carregar(d / "decisoes_caso_SEI1790.json")
        self.assertEqual([x["id"] for x in registro["decisoes"]], ["D1", "D2", "D3", "D4"])
        self.assertEqual(cd.checar_arquivos(registro, [d / "v21_clean.docx"]), [])  # a v21 cumpre as decisões
        linhas = [(1, "Sugiro trocar a requerente para CODEMGE e/ou CODEMIG."), (2, "Mover a doutrina para notas de rodapé.")]
        self.assertEqual([a.id for a in cd.checar_linhas(registro, linhas, "sug")], ["D1", "D2"])


if __name__ == "__main__":
    unittest.main()
