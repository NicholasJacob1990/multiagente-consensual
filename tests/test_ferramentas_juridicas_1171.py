"""Regressões dos defeitos que a auditoria do Codex (GPT-6.1 Sol) reproduziu na 1.17.0."""
from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "redacao-juridica-consensual" / "scripts"
NS = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
NUM = '<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr></w:pPr>'
NUM_MARCA_EXCLUIDA = ('<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="3"/></w:numPr>'
                      '<w:rPr><w:del w:id="90" w:author="Revisora" w:date="2026-10-30T00:00:00Z"/></w:rPr></w:pPr>')


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def docx_xml(path: Path, corpo: str, comentarios: str = "") -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {NS}><w:body>{corpo}</w:body></w:document>")
        if comentarios:
            z.writestr("word/comments.xml", f"<w:comments {NS}>{comentarios}</w:comments>")
    return path


def p(texto: str, ppr: str = NUM, extra: str = "") -> str:
    return f'<w:p>{ppr}<w:r><w:t xml:space="preserve">{texto}</w:t>{extra}</w:r></w:p>'


# ---------------------------------------------------------------- overlay

def test_normalize_runs_preserva_nota_e_split_nao_duplica() -> None:
    pytest.importorskip("lxml")
    od = load("overlay_docx")
    from lxml import etree
    xml = (f'<w:p {NS}><w:r><w:rPr><w:b/></w:rPr><w:t>Antes</w:t><w:footnoteReference w:id="2"/>'
           '<w:tab/><w:t>depois da nota.</w:t></w:r></w:p>')
    par = etree.fromstring(xml)
    assert od.visible(par) == "Antes\tdepois da nota."  # o texto inteiro do run, antes de normalizar
    ctx = od.Ctx(par, "Autor", "2026-11-02T00:00:00Z")
    od.replace(par, "depois da nota", "depois da nota de rodapé", ctx)
    s = etree.tostring(par).decode()
    assert s.count("footnoteReference") == 1 and od.visible(par) == "Antes\tdepois da nota de rodapé."
    assert all(len([c for c in r if c.tag != od.w("rPr")]) == 1 for r in par.iter(od.w("r")))


def test_responder_recusa_comentario_de_outro_autor_e_preimagem() -> None:
    pytest.importorskip("lxml")
    od = load("overlay_docx")
    from lxml import etree
    com = etree.fromstring(f'<w:comments {NS}><w:comment w:id="1" w:author="Revisora"><w:p><w:r><w:t>Ver.</w:t></w:r></w:p>'
                           '</w:comment><w:comment w:id="2" w:author="Autor"><w:p><w:r><w:t>Ajustei.</w:t></w:r></w:p>'
                           '</w:comment></w:comments>')
    ctx = od.Ctx(com, "Autor", "2026-11-02T00:00:00Z")
    with pytest.raises(ValueError, match="é de «Revisora»"):
        od.responder(com, "1", ctx, texto="Outra coisa.")
    with pytest.raises(ValueError, match="mudou desde a leitura"):
        od.responder(com, "2", ctx, texto="Novo.", atual="Mantive.")
    assert od.responder(com, "2", ctx, texto="Novo.", atual="Ajustei.") == "Novo."


def test_aceite_remove_linha_excluida_e_conta_como_o_exportador(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    od, ec = load("overlay_docx"), load("exportar_comentarios")
    from lxml import etree
    linha_excluida = ('<w:tbl><w:tr><w:trPr><w:del w:id="91" w:author="Revisora" w:date="2026-10-30T00:00:00Z"/></w:trPr>'
                      '<w:tc><w:p><w:r><w:t>Linha excluída</w:t></w:r></w:p></w:tc></w:tr>'
                      '<w:tr><w:tc><w:p><w:r><w:t>Linha mantida</w:t></w:r></w:p></w:tc></w:tr></w:tbl>')
    corpo = p("A", NUM_MARCA_EXCLUIDA) + p("B") + p("C") + linha_excluida
    ent = docx_xml(tmp_path / "e.docx", corpo)
    numerados = [x for x in ec.ler_paragrafos(ent) if x["numero"]]
    assert [(x["numero"], x["texto"]) for x in numerados] == [(1, "AB"), (2, "C")]
    root = etree.fromstring(zipfile.ZipFile(ent).read("word/document.xml"))
    g = od.grupos_numerados(root.find(od.w("body")))
    assert sorted(g) == [1, 2] and len(g[1]) == 2
    od.aceitar_tudo(ent, tmp_path / "a.docx")
    xa = zipfile.ZipFile(tmp_path / "a.docx").read("word/document.xml").decode()
    assert "Linha excluída" not in xa and "Linha mantida" in xa
    assert "Linha excluída" not in " ".join(x["texto"] for x in ec.ler_paragrafos(ent))


def test_aplicar_valida_antes_de_gravar_e_confere_hash(tmp_path: Path, capsys) -> None:
    pytest.importorskip("lxml")
    ap = load("aplicar_overlay")
    ent = docx_xml(tmp_path / "e.docx", p("Primeiro parágrafo.") + p("Segundo parágrafo."))
    alt = tmp_path / "alt.json"
    alt.write_text(json.dumps({"paragrafos": [{"n": 1, "antes": "Primeiro", "depois": "O primeiro"}]}), encoding="utf-8")
    reprova = tmp_path / "reprova.py"
    reprova.write_text("print('FAILED: alteração de outro autor'); raise SystemExit(1)\n", encoding="utf-8")
    saida, aceito = tmp_path / "s.docx", tmp_path / "a.docx"
    saida.write_bytes(b"versao anterior")
    args = [str(ent), str(saida), "--alteracoes", str(alt), "--autor", "Autor", "--aceito", str(aceito)]
    assert ap.main(args + ["--validador", str(reprova), "--original", str(ent)]) == 1
    assert saida.read_bytes() == b"versao anterior" and not aceito.exists()
    assert "RECUSADO: a validação reprovou" in capsys.readouterr().out
    assert ap.main(args + ["--sha256", "0" * 64]) == 1 and saida.read_bytes() == b"versao anterior"
    assert ap.main(args) == 0 and aceito.exists() and zipfile.is_zipfile(saida)


def test_aplicar_em_paragrafo_com_marca_excluida(tmp_path: Path) -> None:
    pytest.importorskip("lxml")
    ap = load("aplicar_overlay")
    vazio = '<w:p><w:pPr><w:rPr><w:del w:id="92" w:author="Revisora" w:date="2026-10-30T00:00:00Z"/></w:rPr></w:pPr></w:p>'
    ent = docx_xml(tmp_path / "e.docx", vazio + p("Texto único.") + p("A", NUM_MARCA_EXCLUIDA) + p("B"))
    rel = ap.aplicar(ent, tmp_path / "s.docx", {"paragrafos": [{"n": 1, "antes": "único", "depois": "só"}]}, "Autor",
                     "2026-11-02T00:00:00Z")
    assert rel == ["§ 1: 2 palavras"]
    with pytest.raises(ValueError, match="junta 2 parágrafos com texto"):
        ap.aplicar(ent, tmp_path / "t.docx", {"paragrafos": [{"n": 2, "acrescentar": " C"}]}, "Autor", "2026-11-02T00:00:00Z")


# ---------------------------------------------------------------- remissões

def test_intervalo_com_ponta_dividida_exige_decisao(tmp_path: Path) -> None:
    vr = load("verificar_remissoes")
    dados = {"mapa": {"1": [1, 2], "2": [3, 4], "3": [5]}, "decisoes": []}
    rn = vr.Renumerador(dados)
    assert rn.texto("Ver os parágrafos 1 a 2.", "x:linha 1") == "Ver os parágrafos 1 a 2." and len(rn.pendencias) == 2
    antigo, novo = tmp_path / "antigo.md", tmp_path / "novo.md"
    antigo.write_text("1. Alfa beta gama delta épsilon zeta eta.\n2. Teta iota capa lambda mi ni csi.\n"
                      "3. Ver os parágrafos 1 a 2 sobre o tema.\n", encoding="utf-8")
    novo.write_text("1. Alfa beta gama delta.\n2. Épsilon zeta eta.\n3. Teta iota capa lambda.\n4. Mi ni csi.\n"
                    "5. Ver os parágrafos 1 a 2 sobre o tema.\n", encoding="utf-8")
    m = vr.mapear(antigo, novo)
    pontas = [d for d in m["decisoes"] if d.get("ponta")]
    assert [d["ponta"] for d in pontas] == ["inicio", "fim"] and "pode citar mais" in pontas[0]["nota"]
    for d in pontas:
        d["escolha"] = "todas" if d["ponta"] == "inicio" else "a"
    rn = vr.Renumerador(m)
    assert rn.texto("Ver os parágrafos 1 a 2 sobre o tema.", f"{novo.name}:linha 5") == "Ver os parágrafos 1 a 3 sobre o tema."
    assert not rn.pendencias


def test_intervalo_confere_todos_os_numeros_e_listas_de_dispositivos() -> None:
    vr = load("verificar_remissoes")
    u = vr.Unidade("parecer § 5", "Conforme os parágrafos 1 a 3, o prazo é curto.", 5)
    achados = vr._conferir_paragrafos(u, {1: "a", 3: "c", 5: "e"}, 5)
    assert [a.mensagem for a in achados if a.regra == "remissao_paragrafo"] == [
        "«parágrafos 1 a 3» aponta para o parágrafo 2, que não existe (o parecer tem 5)"]
    chaves = {c[2] for c in vr.citacoes_dispositivo("Os arts. 7º, 8º e 999, e o art. 23, §§ 1º e 99, tratam do tema.")}
    assert {("art", "7"), ("art", "8"), ("art", "999"), ("par", "23", 1), ("par", "23", 99)} <= chaves


def test_diploma_solto_na_frase_nao_absolve_dispositivo_da_minuta() -> None:
    vr = load("verificar_remissoes")
    oficial = vr.estrutura_minuta([vr.Unidade("minuta", "Art. 22 Texto."), vr.Unidade("minuta", "§ 3º Texto.")])
    u = vr.Unidade("parecer § 1", "A Lei nº 13.303/2016 não dispensa o art. 999, § 8º, da minuta.", 1)
    assert [a.severidade for a in vr._conferir_dispositivos(u, oficial, None) if a.regra == "dispositivo"] == ["alerta"]
    u = vr.Unidade("parecer § 2", "Os arts. 17 e 19 da Lei nº 13.303/2016 tratam disso.", 2)
    assert [a for a in vr._conferir_dispositivos(u, oficial, None) if a.regra == "dispositivo"] == []


def test_remissoes_internas_da_minuta_revisada(tmp_path: Path) -> None:
    vr = load("verificar_remissoes")
    parecer = tmp_path / "p.md"
    parecer.write_text("1. Relatório.\n", encoding="utf-8")
    revisada = tmp_path / "r.txt"
    revisada.write_text("Art. 1º Este regulamento rege a eleição.\nArt. 2º Observado o art. 1º e o art. 7º, § 2º, "
                        "e o art. 19 da Lei nº 13.303/2016, a comissão decide.\n", encoding="utf-8")
    r = vr.conferir(parecer, minuta_revisada=revisada)
    internas = [a for a in r["achados"] if a["regra"] == "remissao_interna_minuta"]
    assert [a["mensagem"].split("»")[0] for a in internas] == ["«art. 7º, § 2º"]


# ---------------------------------------------------------------- adendo

def test_adendo_reconhece_ordinais_e_marca_truncado(tmp_path: Path) -> None:
    ea, pm = load("extrair_adendo"), load("parecer_md")
    minuta = tmp_path / "m.md"
    minuta.write_text("1. Os arts. 7º e 8º da Lei tratam do tema; o art. 31 também.\n", encoding="utf-8")
    fonte = tmp_path / "lei.txt"
    fonte.write_text("Art. 7º Primeiro.\nArt. 8º " + "longo " * 5000 + "\n", encoding="utf-8")
    (tmp_path / "mapa.json").write_text(json.dumps({"Lei": "lei.txt"}), encoding="utf-8")
    texto, resumo = ea.montar(pm.ler(minuta), {"Lei": "lei.txt"}, tmp_path)
    itens = {i["artigo"]: i for i in resumo["itens"]}
    assert set(itens) == {"7", "8"} and itens["7"]["integral"] and not itens["8"]["integral"]
    assert resumo["truncados"] == 1 and "TRUNCADO" in texto
    assert [c["artigo"] for c in resumo["sem_norma"]] == ["31"]
    assert ea.main([str(minuta), "--mapa", str(tmp_path / "mapa.json"), "--fontes", str(tmp_path),
                    "--saida", str(tmp_path / "ad.md")]) == 1


# ---------------------------------------------------------------- espelho e anexo

def test_espelho_exige_partes_na_mesma_linha_e_algum_bloco(tmp_path: Path) -> None:
    es = load("espelho_redacoes")
    minuta = tmp_path / "minuta.md"
    minuta.write_text("| Etapa | Responsável | Prazo |\n|---|---|---|\n| Inscrição | B | 2 dias |\n| Recurso | A | 5 dias |\n",
                      encoding="utf-8")
    anexo = tmp_path / "anexo.md"
    anexo.write_text("Inscrição. Responsável: A; Prazo: 5 dias (NR)\nRecurso. Responsável: A; Prazo: 5 dias (NR)\n",
                     encoding="utf-8")
    r = es.conferir(anexo, minuta)
    assert [b["estado"] for b in r["blocos"]] == ["divergente", "por_partes"] and "linhas" in r["blocos"][0]["motivo"]
    vazio = tmp_path / "vazio.md"
    vazio.write_text("Texto sem marca.\n", encoding="utf-8")
    r = es.conferir(vazio, minuta)
    assert r["sem_blocos"] and not r["ok"]


def test_mescla_do_anexo_refaz_classificacao_e_grupo() -> None:
    ea = load("extrair_anexo_json")
    novos = [{"item": 1, "grupo": "EDITAL", "classificacao_detalhe": "recomendação (parágrafo 80)", "blocos": []}]
    base = [{"item": 1, "grupo": "Regulamento", "classificacao": "Correção necessária",
             "classificacao_detalhe": "correção necessária (parágrafo 169, ii)", "blocos": []}]
    m, dif = ea.mesclar(novos, base)
    assert m[0]["grupo"] == "EDITAL" and m[0]["classificacao"] == "Recomendação"
    assert any("grupo mudou" in d for d in dif) and any("classificacao refeita" in d for d in dif)


# ---------------------------------------------------------------- pacote e varredura

def test_hash_citado_no_meio_da_frase_e_recusa_nao_certificam() -> None:
    pa = load("pacote_auditoria")
    h = "b" * 64
    assert not pa.verificar(f"Pedido: HASH_RECEBIDO: {h}\nFalha: não executei a auditoria.", h)[0]
    ok, msgs = pa.validar_resposta(f"HASH_RECEBIDO: {h}\nNão executei a auditoria por falta de tempo.")
    assert not ok and "falha ou recusa" in msgs[0]
    ok, msgs = pa.validar_resposta(f"HASH_RECEBIDO: {h}\nDecisão: AJUSTAR. Não foi possível localizar o art. 9º na fonte.",
                                   exigir=["Decisão:"])
    assert ok
    assert not pa.validar_resposta(f"HASH_RECEBIDO: {h}\nTudo certo.", exigir=["Decisão:"])[0]
    assert pa.verificar_comentarios("\n".join(["preâmbulo"] * 8) + "\nHASH_COMENTARIOS: " + h, h)[0] is True


def test_varredura_nao_confunde_remissao_com_cabecalho(tmp_path: Path) -> None:
    vf = load("varrer_fontes")
    (tmp_path / "estatuto.md").write_text("Art. 45. O pessoal a que se refere o Art. 22 será admitido por concurso.\n"
                                          "Art. 46. O quadro de confiança.", encoding="utf-8")
    ach = vf.varrer([tmp_path], ["concurso"])
    assert [(a["dispositivo"], a["termos"]) for a in ach] == [("Art. 45", ["concurso"])]
