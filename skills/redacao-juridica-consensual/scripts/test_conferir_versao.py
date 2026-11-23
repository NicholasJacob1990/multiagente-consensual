"""Testes de ``conferir_versao`` com DOCX sintéticos mínimos e os scripts irmãos reais (subprocesso).

Executar: ``python3 -m unittest test_conferir_versao``.
Os testes que dependem de um script irmão são pulados se ele não existir; o de PDF,
se ``soffice`` não estiver instalado.
"""

from __future__ import annotations

import html
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

import conferir_versao as cv  # noqa: E402

SCRIPT = AQUI / "conferir_versao.py"
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
AUTOR = 'w:author="Teste" w:date="2026-11-04T00:00:00Z"'

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/numbering.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.numbering+xml"/>'
    "</Types>"
)
RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/></Relationships>'
)
DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/numbering" '
    'Target="numbering.xml"/></Relationships>'
)
NUMBERING = (
    f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:numbering xmlns:w="{W_NS}">'
    '<w:abstractNum w:abstractNumId="1"><w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="decimal"/>'
    '<w:lvlText w:val="%1."/></w:lvl></w:abstractNum><w:num w:numId="1"><w:abstractNumId w:val="1"/></w:num>'
    "</w:numbering>"
)
NUM_PPR = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="1"/></w:numPr></w:pPr>'


def t(texto: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{html.escape(texto, quote=False)}</w:t></w:r>'


def par(conteudo: str, numerado: bool = True) -> str:
    """Parágrafo numerado (numPr) com texto simples ou XML de runs já montado."""
    corpo = conteudo if conteudo.startswith("<w:") else t(conteudo)
    return f"<w:p>{NUM_PPR if numerado else ''}{corpo}</w:p>"


def montar(path: Path, paragrafos: list[str]) -> Path:
    corpo = "".join(p if p.startswith("<w:p>") else par(p) for p in paragrafos)
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document xmlns:w="{W_NS}">'
           f'<w:body>{corpo}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", doc)
        z.writestr("word/numbering.xml", NUMBERING)
    return path


BASE = [
    "A consulente pede orientação sobre o registro do lote 01.",
    "O lote foi adquirido em 1971 e consta da Matrícula nº 9.876.",
    "Conclui-se pela averbação, observado o parágrafo 2.",
]
NOVA = [
    "A consulente pede orientação sobre o registro do lote 01.",
    "O lote foi adquirido em 1971 e consta da Matrícula nº 9.876, R-1.",
    "Conclui-se pela averbação, observado o parágrafo 2.",
]


def irmaos(*nomes: str) -> bool:
    return all((AQUI / n).exists() for n in nomes)


def rodar(*args: str, script: Path = SCRIPT) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(script), *args], capture_output=True, text=True, timeout=600)


class UtilidadesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_count_da_arvore_de_paginas(self):
        pdf = (b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
               b"2 0 obj\n<< /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >>\nendobj\n"
               b"3 0 obj\n<< /Type /Page /Parent 2 0 R >>\nendobj\n"
               b"6 0 obj\n<< /Type /Outlines /Count 9 >>\nendobj\n")
        self.assertEqual(cv.contar_paginas_bytes(pdf), 3)

    def test_sem_count_conta_objetos_page(self):
        pdf = b"<< /Type /Page >> << /Type /Page >> << /Type /Catalog >>"
        self.assertEqual(cv.contar_paginas_bytes(pdf), 2)
        self.assertIsNone(cv.contar_paginas_bytes(b"nada"))

    def test_sha256(self):
        p = self.dir / "a.bin"
        p.write_bytes(b"abc")
        self.assertEqual(cv.sha256(p), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
        self.assertIsNone(cv.sha256(None))

    def test_tem_opcao(self):
        ajuda = "usage: x.py [--json JSON] [--pdf PDF] [--max-paginas N]"
        self.assertTrue(cv.tem_opcao(ajuda, "--pdf"))
        self.assertTrue(cv.tem_opcao(ajuda, "--json"))
        self.assertFalse(cv.tem_opcao(ajuda, "--max"))
        self.assertFalse(cv.tem_opcao(ajuda, "--decisoes"))

    def _resultado(self, versao: str, bloqueantes: list[str]) -> dict:
        return {"versao": versao, "sha256": {"anterior": "a" * 64, "nova": "b" * 64, "redline": None},
                "data": "2026-11-04", "modo": "conciso", "resumo": "r", "bloqueantes": bloqueantes,
                "resultado": "reprovada" if bloqueantes else "aprovada"}

    def test_registro_acrescenta_e_substitui(self):
        reg = self.dir / "versoes.json"
        cv.atualizar_registro(reg, self._resultado("v20", ["x"]), "Caso X")
        cv.atualizar_registro(reg, self._resultado("v21", []), None)
        cv.atualizar_registro(reg, self._resultado("v20", []), None)
        d = json.loads(reg.read_text(encoding="utf-8"))
        self.assertEqual(d["caso"], "Caso X")
        self.assertEqual([v["versao"] for v in d["versoes"]], ["v20", "v21"])
        self.assertEqual(d["versoes"][0]["resultado"], "aprovada")
        self.assertEqual(set(d["versoes"][0]), {"versao", "base_sha256", "limpa_sha256", "redline_sha256", "data",
                                                "modo", "resumo", "resultado", "bloqueantes"})

    def test_modelo_de_registro_vazio(self):
        d = json.loads((AQUI / "versoes_modelo.json").read_text(encoding="utf-8"))
        self.assertEqual(d, {"caso": "", "versoes": []})

    def test_nota_com_paginas_acima_e_nao_executado(self):
        r = {"versao": "v2", "data": "2026-11-04", "modo": "conciso", "perfil": "genes",
             "arquivos": {"anterior": "/x/v1.docx", "nova": "/x/v2.docx", "redline": None},
             "sha256": {"anterior": "a" * 64, "nova": "b" * 64, "redline": None},
             "paginas": {"conferidas": True, "n": 31, "limite": 15, "metodo": "pdfinfo", "motivo": "", "acima": True},
             "metricas": {},
             "ferramentas": [{"ferramenta": "pre_auditoria_parecer.py", "status": "achados", "motivo": "",
                              "comando": [], "codigo": 1, "bloqueantes": ["[palavras] § 5: 127 palavras (máximo 120)"],
                              "alertas": ["[ritmo] x"], "resumo": ""},
                             {"ferramenta": "checar_decisoes.py", "status": "não executado",
                              "motivo": "checar_decisoes.py não existe nesta pasta", "comando": [], "codigo": None,
                              "bloqueantes": [], "alertas": [], "resumo": ""}],
             "inventario_md": "", "refutadas": [], "decisoes": [],
             "integridade": {"conferida": False, "ok": None, "falhas": []},
             "bloqueantes": ["pre_auditoria_parecer.py: [palavras] § 5", "páginas: 31 (limite 15)"],
             "nao_executados": ["checar_decisoes.py: checar_decisoes.py não existe nesta pasta"],
             "resultado": "reprovada"}
        nota = cv.montar_nota(r)
        self.assertTrue(nota.startswith("## Conferências automáticas"))
        self.assertIn("ACIMA DO LIMITE (31 > 15)", nota)
        self.assertIn("127 palavras (máximo 120)", nota)
        self.assertIn("**não executado**", nota)
        self.assertNotIn("alerta [ritmo]", nota)  # alertas listados só no modo profundo
        r["modo"] = "profundo"
        self.assertIn("alerta [ritmo] x", cv.montar_nota(r))


class UsoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.a = montar(self.dir / "v1.docx", BASE)

    def tearDown(self):
        self.tmp.cleanup()

    def test_arquivo_inexistente(self):
        r = rodar("--anterior", str(self.a), "--nova", str(self.dir / "nao.docx"), "--sem-pdf")
        self.assertEqual(r.returncode, 2)
        self.assertIn("não encontrado", r.stderr)

    def test_modo_invalido_e_limite_negativo(self):
        self.assertEqual(rodar("--anterior", str(self.a), "--nova", str(self.a), "--modo", "x").returncode, 2)
        self.assertEqual(rodar("--anterior", str(self.a), "--nova", str(self.a), "--max-paginas", "0").returncode, 2)

    def test_registro_invalido(self):
        reg = self.dir / "versoes.json"
        reg.write_text("[1, 2]", encoding="utf-8")
        r = rodar("--anterior", str(self.a), "--nova", str(self.a), "--sem-pdf", "--registro", str(reg))
        self.assertEqual(r.returncode, 2)

    def test_scripts_irmaos_ausentes_viram_nao_executado(self):
        sozinho = self.dir / "sozinho"
        sozinho.mkdir()
        shutil.copy(SCRIPT, sozinho / "conferir_versao.py")
        js = self.dir / "r.json"
        r = rodar("--anterior", str(self.a), "--nova", str(self.a), "--sem-pdf", "--refutadas", str(self.a),
                  "--json", str(js), script=sozinho / "conferir_versao.py")
        self.assertEqual(r.returncode, 0, r.stderr)
        d = json.loads(js.read_text(encoding="utf-8"))
        self.assertEqual(d["resultado"], "incompleta")
        status = {f["ferramenta"]: f["status"] for f in d["ferramentas"]}
        self.assertEqual(status["pre_auditoria_parecer.py"], "não executado")
        self.assertEqual(status["checar_refutadas.py"], "não executado")
        self.assertEqual(status["integridade_docx.py"], "dispensado")
        self.assertIn("não executado", d["nota_md"])

    def test_checar_decisoes_lido_pelo_help(self):
        """O orquestrador monta a chamada pelo ``--help`` e lê os achados do JSON (script fictício)."""
        pasta = self.dir / "com_decisoes"
        pasta.mkdir()
        shutil.copy(SCRIPT, pasta / "conferir_versao.py")
        (pasta / "checar_decisoes.py").write_text(
            "import argparse, json, sys\n"
            "ap = argparse.ArgumentParser()\n"
            "ap.add_argument('--decisoes', required=True)\n"
            "ap.add_argument('textos', nargs='+')\n"
            "ap.add_argument('--json')\n"
            "a = ap.parse_args()\n"
            "acertos = [{'id': 'D1', 'local': 'linha 3', 'trecho': 'trocar a requerente', 'decisao': 'manter CODEMIG'},\n"
            "           {'id': 'D9', 'trecho': 'x', 'severidade': 'bloqueante'}]\n"
            "json.dump({'acertos': acertos}, open(a.json, 'w'))\n"
            "print('2 conflito(s)'); sys.exit(1)\n", encoding="utf-8")
        dec = self.dir / "decisoes.json"
        dec.write_text('{"caso": "C", "decisoes": []}', encoding="utf-8")
        js = self.dir / "r.json"
        r = rodar("--anterior", str(self.a), "--nova", str(self.a), "--sem-pdf", "--decisoes", str(dec),
                  "--json", str(js), script=pasta / "conferir_versao.py")
        self.assertEqual(r.returncode, 1, r.stderr)
        d = json.loads(js.read_text(encoding="utf-8"))
        f = {x["ferramenta"]: x for x in d["ferramentas"]}["checar_decisoes.py"]
        self.assertEqual(f["status"], "achados")
        self.assertIn("--decisoes", f["comando"])
        self.assertEqual(len(f["alertas"]), 1)
        self.assertEqual(len(f["bloqueantes"]), 1)
        self.assertIn("[D1]", d["nota_md"].split("**Decisões**")[1])


@unittest.skipUnless(irmaos("docx_para_md.py", "pre_auditoria_parecer.py", "inventario_fatos.py",
                            "verificar_remissoes.py"), "scripts irmãos ausentes")
class OrquestracaoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.a = montar(self.dir / "v1.docx", BASE)
        self.n = montar(self.dir / "v2.docx", NOVA)

    def tearDown(self):
        self.tmp.cleanup()

    def conferir(self, *extra: str, nova: Path | None = None) -> tuple[subprocess.CompletedProcess, dict]:
        js = self.dir / "saida.json"
        r = rodar("--anterior", str(self.a), "--nova", str(nova or self.n), "--sem-pdf", "--json", str(js), *extra)
        self.assertIn(r.returncode, (0, 1), r.stderr)
        return r, json.loads(js.read_text(encoding="utf-8"))

    def status(self, d: dict) -> dict:
        return {f["ferramenta"]: f for f in d["ferramentas"]}

    def test_versao_limpa_aprovada_e_registro(self):
        reg = self.dir / "versoes.json"
        nota = self.dir / "conferencias.md"
        r, d = self.conferir("--versao", "v2", "--resumo", "acréscimo do R-1", "--data", "2026-11-04",
                             "--registro", str(reg), "--nota-saida", str(nota), "--caso", "Caso teste")
        self.assertEqual(r.returncode, 0, d["bloqueantes"])
        st = self.status(d)
        for f in ("docx_para_md.py", "pre_auditoria_parecer.py", "inventario_fatos.py",
                  "verificar_remissoes.py conferir"):
            self.assertIn(st[f]["status"], ("ok", "achados"), st[f]["motivo"])
        self.assertEqual(st["checar_refutadas.py"]["status"], "dispensado")
        md = nota.read_text(encoding="utf-8")
        self.assertTrue(md.startswith("## Conferências automáticas"))
        self.assertIn(cv.sha256(self.n), md)
        self.assertIn("Fonte (página)", md)  # tabela do inventário, coluna a preencher
        self.assertIn("R-1", md)
        self.assertIn("não conferidas (--sem-pdf)", md)
        self.assertIn("conferir_versao: v2", r.stdout)
        # segunda rodada da mesma versão substitui a entrada; outra versão acrescenta
        self.conferir("--versao", "v2", "--registro", str(reg))
        self.conferir("--versao", "v3", "--registro", str(reg))
        dados = json.loads(reg.read_text(encoding="utf-8"))
        self.assertEqual(dados["caso"], "Caso teste")
        self.assertEqual([v["versao"] for v in dados["versoes"]], ["v2", "v3"])
        self.assertEqual(dados["versoes"][0]["limpa_sha256"], cv.sha256(self.n))
        self.assertEqual(dados["versoes"][0]["base_sha256"], cv.sha256(self.a))

    def test_paragrafo_acima_do_teto_bloqueia(self):
        longo = "O requerimento abrange " + " ".join(f"palavra{i}" for i in range(124)) + "."
        n = montar(self.dir / "v2_longo.docx", NOVA[:2] + [longo] + NOVA[2:])
        r, d = self.conferir("--max-palavras", "120", nova=n)
        self.assertEqual(r.returncode, 1)
        pre = self.status(d)["pre_auditoria_parecer.py"]
        self.assertTrue(any("[palavras]" in b and "máximo 120" in b for b in pre["bloqueantes"]), pre["bloqueantes"])
        self.assertEqual(d["resultado"], "reprovada")
        self.assertIn("[palavras]", d["nota_md"])

    @unittest.skipUnless(irmaos("checar_refutadas.py"), "checar_refutadas.py ausente")
    def test_refutada_bloqueia(self):
        ref = self.dir / "refutadas.json"
        ref.write_text(json.dumps({"caso": "Caso R", "refutadas": [
            {"id": "R1", "padrao": "adquirido em 1971", "regex": False, "por_que": "a aquisição é de 1982",
             "correto": "adjudicado em 1982", "fonte": "SEI 1, p. 2"}]}), encoding="utf-8")
        reg = self.dir / "versoes.json"
        r, d = self.conferir("--refutadas", str(ref), "--registro", str(reg))
        self.assertEqual(r.returncode, 1)
        self.assertTrue(d["refutadas"] and "[R1]" in d["refutadas"][0])
        self.assertIn("[R1]", d["nota_md"].split("**Refutadas**")[1])
        self.assertEqual(json.loads(reg.read_text(encoding="utf-8"))["caso"], "Caso R")

    @unittest.skipUnless(irmaos("conferir_aritmetica.py"), "conferir_aritmetica.py ausente")
    def test_verificacoes_aritmeticas(self):
        ver = self.dir / "verificacoes.json"
        ver.write_text(json.dumps({"caso": "Caso A", "verificacoes": [
            {"id": "A1", "descricao": "soma", "expressao": "9.000 + 876 = 9.876", "no_texto": ["9.876"]}]}),
            encoding="utf-8")
        r, d = self.conferir("--verificacoes", str(ver))
        self.assertEqual(d["aritmetica"], [])
        self.assertIn("todas as contas registradas fecham", d["nota_md"])
        ver.write_text(json.dumps({"caso": "Caso A", "verificacoes": [
            {"id": "A2", "descricao": "conta errada", "expressao": "1 + 1 = 3"}]}), encoding="utf-8")
        r, d = self.conferir("--verificacoes", str(ver))
        self.assertEqual(r.returncode, 1)
        self.assertTrue(d["aritmetica"] and "[A2]" in d["aritmetica"][0])
        self.assertEqual(d["resultado"], "reprovada")

    def test_estilo_repassado(self):
        r, d = self.conferir("--estilo", "executivo")
        self.assertEqual(d["estilo"], "executivo")
        pre = self.status(d)["pre_auditoria_parecer.py"]
        self.assertTrue(any("Resposta objetiva" in b for b in pre["bloqueantes"]), pre["bloqueantes"])

    @unittest.skipUnless(irmaos("integridade_docx.py"), "integridade_docx.py ausente")
    def test_integridade_ok_e_falha(self):
        marcado = (t("O lote foi adquirido em 1971 e consta da Matrícula nº 9.876")
                   + f'<w:ins w:id="1" {AUTOR}>{t(", R-1")}</w:ins>' + t("."))
        red = montar(self.dir / "v2_track.docx", [BASE[0], par(marcado), BASE[2]])
        r, d = self.conferir("--redline", str(red))
        self.assertEqual(r.returncode, 0, d["bloqueantes"])
        self.assertTrue(d["integridade"]["ok"])
        self.assertIsNotNone(d["sha256"]["redline"])
        self.assertIn("ok —", d["nota_md"].split("**Integridade do comparativo**")[1])
        # comparativo errado (sem marcas, igual à base): falha de integridade
        r, d = self.conferir("--redline", str(self.a))
        self.assertEqual(r.returncode, 1)
        self.assertIs(d["integridade"]["ok"], False)
        self.assertIn("**FALHA**", d["nota_md"])

    def test_decisoes(self):
        dec = self.dir / "decisoes.json"
        dec.write_text(json.dumps({"caso": "C", "decisoes": [
            {"id": "D1", "tema": "t", "decisao": "não trocar a requerente", "padroes": ["trocar a requerente"]}]}),
            encoding="utf-8")
        _, d = self.conferir("--decisoes", str(dec))
        f = self.status(d)["checar_decisoes.py"]
        if not (AQUI / "checar_decisoes.py").exists():
            self.assertEqual(f["status"], "não executado")
            self.assertIn("não existe", f["motivo"])
            self.assertEqual(d["resultado"], "incompleta")
        else:
            self.assertNotEqual(f["status"], "dispensado")

    @unittest.skipUnless(shutil.which("soffice") or shutil.which("libreoffice"), "soffice ausente")
    def test_pdf_paginas_acima_do_limite(self):
        texto = "O lote foi adquirido e consta da matrícula, com área e confrontações descritas no título. " * 4
        n = montar(self.dir / "v2_grande.docx", NOVA + [texto] * 60)
        js = self.dir / "pdf.json"
        r = rodar("--anterior", str(self.a), "--nova", str(n), "--max-paginas", "1", "--json", str(js))
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        d = json.loads(js.read_text(encoding="utf-8"))
        self.assertTrue(d["paginas"]["conferidas"], d["paginas"])
        self.assertGreater(d["paginas"]["n"], 1)
        self.assertTrue(d["paginas"]["acima"])
        self.assertIn("ACIMA DO LIMITE", d["nota_md"])


if __name__ == "__main__":
    unittest.main()
