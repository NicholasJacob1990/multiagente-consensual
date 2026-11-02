from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "redacao-juridica-consensual" / "scripts"
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def docx(path: Path, paragrafos: list[tuple[str, bool]], comentarios: list[tuple[str, str]] = ()) -> Path:
    corpo = []
    for texto, numerado in paragrafos:
        ppr = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr></w:pPr>' if numerado else ""
        corpo.append(f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{escape(texto)}</w:t></w:r></w:p>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {NS}><w:body>{''.join(corpo)}</w:body></w:document>")
        if comentarios:
            cs = "".join(f'<w:comment w:id="{i}" w:author="{a}"><w:p><w:r><w:t>{escape(t)}</w:t></w:r></w:p></w:comment>'
                         for i, (a, t) in enumerate(comentarios))
            z.writestr("word/comments.xml", f"<w:comments {NS}>{cs}</w:comments>")
    return path


# ---------------------------------------------------------------- verificar_remissoes

PARECER = """1. A reserva cabe ao controlador (Parecer AGE nº 16.188/2020, itens 59, 67 e 80); ver itens 74 e 76 daquele parecer.
2. A convocação aguardará a Assembleia (art. 53, § 9º, sugerido; Anexo de Redações Sugeridas, item 7).
3. O prazo de defesa é de dois dias (Anexo de Redações Sugeridas, item 6).
4. Correções necessárias. Impõe-se: (i) harmonizar a defesa (parágrafos 2 e 3).
5. Recomendações. Sugere-se ajustar a convocação (parágrafo 2).
"""

ANEXO = """Item 6 – Art. 23
Classificação: correção necessária (parágrafo 4, i).
Fundamento: parecer, parágrafo 3.
Item 7 – Art. 53
Classificação: recomendação (parágrafo 5).
Fundamento: parecer, parágrafo 2.
"""


def test_item_de_documento_externo_nao_e_item_do_anexo() -> None:
    vr = load("verificar_remissoes")
    assert vr.remissoes_item("(Parecer AGE nº 16.188/2020, itens 59, 67, 74, 76 e 80)") == []
    assert vr.remissoes_item("ver itens 74 e 76 daquele parecer") == []
    assert vr.remissoes_item("(Nota Jurídica nº 345/2019, item 4)") == []
    assert len(vr.remissoes_item("(Anexo de Redações Sugeridas, item 31)")) == 1
    assert len(vr.remissoes_item("o Parecer AGE nº 16.188/2020 e o Anexo de Redações Sugeridas, item 5")) == 1


def test_classificacao_e_respostas_a_reconferir(tmp_path: Path) -> None:
    vr = load("verificar_remissoes")
    par, anexo = tmp_path / "p.md", tmp_path / "a.txt"
    par.write_text(PARECER, encoding="utf-8")
    anexo.write_text(ANEXO, encoding="utf-8")
    r = vr.conferir(par, anexo)
    assert not [a for a in r["achados"] if a["regra"] == "remissao_item"]  # os itens da AGE não contam
    cl = [a for a in r["achados"] if a["regra"] == "classificacao"]
    assert [a["local"] for a in cl] == ["parecer § 2"] and "item 7" in cl[0]["mensagem"]  # § 3 remete a correção: ok
    assert vr.grupos_correcao(vr.numerados(vr.ler_parecer(par))) == {"i": {2, 3}}

    antes = tmp_path / "antes.md"
    antes.write_text(PARECER.replace("aguardará a Assembleia", "aguardará o órgão competente"), encoding="utf-8")
    com = docx(tmp_path / "c.docx", [("x", True)], [("Revisora", "Ver."), ("Autor", "Ajustei o parágrafo 2."),
                                                      ("Autor", "Mantive o parágrafo 3.")])
    r2 = vr.conferir(par, anexo, comentarios=[com], anterior=antes, autor="Autor")
    rev = [a for a in r2["achados"] if a["regra"] == "revisar_resposta"]
    assert len(rev) == 1 and rev[0]["local"].startswith("comentário 1 (Autor)") and "§§ 2" in rev[0]["mensagem"]


# ---------------------------------------------------------------- pacote_auditoria

def test_hash_com_preambulo_e_instrucoes_conferidas(tmp_path: Path) -> None:
    pa, pm = load("pacote_auditoria"), load("parecer_md")
    h = "a" * 64
    ok, msg = pa.verificar("Vou ler as fontes.Vou conferir a contagem.HASH: " + h + "\n\nDecisão: AJUSTAR", h)
    assert ok and "preâmbulo" in msg
    assert pa.verificar("HASH_RECEBIDO: `" + h + "`", h) == (True, "hash confere")
    assert not pa.verificar("\n".join(["linha"] * 25) + "\nHASH: " + h, h)[0]
    doc = tmp_path / "d.md"
    doc.write_text("1. Relatório.\n2. Correções necessárias. Impõe-se: (i) ajustar; e (ii) definir eleitores.\n"
                   "3. Impõe-se, também, (iii) harmonizar.\n", encoding="utf-8")
    avisos = pa.conferir_instrucoes("A correção (ii) (§ 3) e o § 9 tratam disso.", pm.ler(doc))
    assert any("§ 9" in a and "3 parágrafos" in a for a in avisos)
    assert any("correção (ii) no § 3" in a and "está no § 2" in a for a in avisos)
    assert pa.conferir_instrucoes("A correção (ii) (§ 2) basta.", pm.ler(doc)) == []


def test_parecer_md_aceita_tabulacao_depois_do_numero() -> None:
    pm = load("parecer_md")
    assert pm.parse("1.\tPrimeiro.\n2. Segundo.").por_numero() == {1: "Primeiro.", 2: "Segundo."}


# ---------------------------------------------------------------- varrer_fontes e extrair_anexo_json

def test_varrer_fontes_por_artigo_e_sem_acento(tmp_path: Path) -> None:
    vf = load("varrer_fontes")
    (tmp_path / "estatuto.md").write_text(
        "Art.44. O regime é o da CLT. Art.45. A contratação de pessoal efetivo depende de prévio concurso público. "
        "Art.46. O quadro de funções de confiança terá remuneração própria.", encoding="utf-8")
    (tmp_path / "estatuto.conversao.json").write_text("{}", encoding="utf-8")
    (tmp_path / "regimento.txt").write_text("8.6 No caso de desconformidade, a conclusão vai ao Acionista Controlador.",
                                            encoding="utf-8")
    ach = vf.varrer([tmp_path], ["concurso", "confianca", "desconformidade"])
    assert {(a["arquivo"], a["dispositivo"]) for a in ach} == {("estatuto.md", "Art. 45"), ("estatuto.md", "Art. 46"),
                                                                ("regimento.txt", "8.6")}
    assert "Nenhum termo" in vf.relatorio([], ["x"])


def test_extrair_anexo_json_e_mesclar(tmp_path: Path) -> None:
    ea = load("extrair_anexo_json")
    a = tmp_path / "anexo.txt"
    a.write_text("ANEXO – REDAÇÕES SUGERIDAS\nTexto introdutório.\nREGULAMENTO\nItem 1 – Art. 2º\n"
                 "Classificação: correção necessária (parágrafo 169, ii).\nFundamento: parecer, parágrafos 44 e 46 a 48.\n"
                 "Observação: Nota do item.\nDA HABILITAÇÃO\nArt. 2º Texto novo. (NR)\nEDITAL DE CONVOCAÇÃO\n"
                 "Item 2 – Cláusula\nClassificação: recomendação.\n[Edital] Cláusula. (AC)\n", encoding="utf-8")
    itens = ea.extrair(a)
    assert [i["item"] for i in itens] == [1, 2]
    assert itens[0]["grupo"] == "REGULAMENTO" and itens[1]["grupo"] == "EDITAL DE CONVOCAÇÃO"
    assert itens[0]["paragrafos_parecer"] == [44, 46, 47, 48] and itens[0]["nota"] == "Nota do item."
    assert itens[0]["blocos"] == ["DA HABILITAÇÃO", "Art. 2º Texto novo. (NR)"]  # título dentro do item fica nos blocos
    base = [{"item": 1, "grupo": "Regulamento", "classificacao": "Correção necessária", "blocos": ["Art. 2º Antigo. (NR)"]}]
    m, dif = ea.mesclar(itens, base)
    assert m[0]["classificacao"] == "Correção necessária" and m[0]["grupo"] == "Regulamento"
    assert "item 1: blocos mudou" in dif and "item 2: novo (não estava na base)" in dif


# ---------------------------------------------------------------- aplicar_overlay

def test_aplicar_overlay_paragrafos_respostas_e_aceite(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    ap = load("aplicar_overlay")
    od = load("overlay_docx")
    ent = docx(tmp_path / "e.docx", [("Título", False), ("Primeiro parágrafo antigo.", True),
                                      ("Segundo parágrafo.", True), ("Terceiro com trecho único.", True)],
               [("Revisora", "Ajustar."), ("Autor", "De acordo.")])
    alt = {"paragrafos": [{"n": 1, "texto": "Primeiro parágrafo novo."},
                          {"n": 2, "acrescentar": " Frase acrescida."},
                          {"n": 3, "antes": "trecho único", "depois": "trecho trocado"}],
           "respostas": [{"id": "1", "texto": "Ajustei o parágrafo 1."}]}
    sai = tmp_path / "s.docx"
    rel = ap.aplicar(ent, sai, alt, "Autor", "2026-11-02T00:00:00Z")
    assert rel[0] == "§ 1: 3 palavras" and rel[-1] == "resposta 1: reescrita"
    xml = zipfile.ZipFile(sai).read("word/document.xml").decode()
    assert "<w:ins" in xml and "<w:del " in xml and 'w:author="Autor"' in xml
    assert "Ajustei o parágrafo 1." in zipfile.ZipFile(sai).read("word/comments.xml").decode()

    aceito = tmp_path / "a.docx"
    od.aceitar_tudo(sai, aceito)
    xa = zipfile.ZipFile(aceito).read("word/document.xml").decode()
    assert "<w:ins" not in xa and "<w:del" not in xa and "antigo" not in xa
    from lxml import etree
    root = etree.fromstring(zipfile.ZipFile(aceito).read("word/document.xml"))
    assert [od.visible(p) for p in root.iter(od.w("p"))][1:] == [
        "Primeiro parágrafo novo.", "Segundo parágrafo. Frase acrescida.", "Terceiro com trecho trocado."]

    with pytest.raises(ValueError, match="acima de 3 palavras"):
        ap.aplicar(ent, tmp_path / "x.docx", {"paragrafos": [{"n": 1, "acrescentar": " Mais quatro palavras aqui."}]},
                   "Autor", "2026-11-02T00:00:00Z", max_palavras=3)
    with pytest.raises(ValueError, match="aparece 0 vezes"):
        ap.aplicar(ent, tmp_path / "y.docx", {"paragrafos": [{"n": 3, "antes": "inexistente", "depois": "x"}]},
                   "Autor", "2026-11-02T00:00:00Z")
    assert ap.main([str(ent), str(tmp_path / "z.docx"), "--alteracoes", str(_json(tmp_path, alt))]) == 0


def _json(tmp_path: Path, dados: dict) -> Path:
    p = tmp_path / "alt.json"
    p.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    return p
