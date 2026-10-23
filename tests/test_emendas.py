from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "loop-debate-agentes" / "scripts" / "emendas.py"


def load():
    spec = importlib.util.spec_from_file_location("emendas", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MINUTA = (
    "## I. Relatório\n\n"
    "1. A consulta trata do regulamento eleitoral do conselho.\n\n"
    "2. A lei restringe a vedação aos conselhos de administração e fiscal (Decreto, art. 32).\n\n"
    "3. O prazo é de cinco dias úteis, e o prazo é prorrogável.\n"
)
FONTE = "Art. 20. É vedada a participação remunerada de membros da administração pública em mais de 2 (dois) conselhos."


def prop(trecho, proposta, tipo="redacao", **kw):
    return {"trecho": trecho, "proposta": proposta, "tipo": tipo, "fundamento": "melhora",
            "classificacao": "recomendacao_facultativa", "fonte_ref": "Documento sintético do teste",
            "nivel_fonte": "reproducao_literal" if "fonte_literal" in kw else "minuta_atual",
            "fonte_literal": trecho, **kw}


def lote(m, autor, *props, hash_=None):
    return {"autor": autor, "hash_minuta": hash_ or m.sha256_texto(MINUTA), "propostas": list(props)}


def votos(m, votante, **por_id):
    vs = []
    for i, v in por_id.items():
        voto, _, ajuste = v.partition(":")
        vs.append({"id": i, "voto": voto, "motivo": "ok", **({"ajuste": ajuste} if ajuste else {})})
    return {"votante": votante, "hash_minuta": m.sha256_texto(MINUTA), "votos": vs}


def test_validacao_mecanica(tmp_path: Path) -> None:
    m = load()
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    (fontes / "l13303.txt").write_text(FONTE, encoding="utf-8")
    res = m.validar(
        MINUTA,
        [
            lote(m, "gemini",
                 prop("trata do regulamento", "examina o regulamento"),
                 prop("prazo é", "prazo será"),
                 prop("(Decreto, art. 32)", "(Lei nº 13.303/2016, art. 20; Decreto, art. 32)", "fonte",
                      fonte_literal="É vedada a participação remunerada de membros da administração pública"),
                 prop("eleitoral do conselho", "eleitoral", "correcao", fonte_literal="texto inventado"),
                 prop("consulta trata", "consulta versa", paragrafo=2)),
            lote(m, "codex", prop("trata do regulamento", "examina o regulamento")),
            lote(m, "kimi", prop("prazo", "termo"), hash_="0" * 64),
        ],
        travados=[{"id": "relatorio", "texto": "regulamento eleitoral do conselho"}],
        fontes=m.corpus_fontes([fontes]),
    )
    por_trecho = {e["trecho"]: e for e in res["emendas"]}
    assert res["lotes_recusados"][0]["autor"] == "kimi"
    convergente = por_trecho["trata do regulamento"]
    assert convergente["autores"] == ["gemini", "codex"] and convergente["status"] == "invalida"  # sobrepõe o trecho travado
    assert "ambíguo" in por_trecho["prazo é"]["motivos_invalidade"][0]
    assert por_trecho["(Decreto, art. 32)"]["status"] == "valida"
    assert por_trecho["(Decreto, art. 32)"]["paragrafo"] == 2
    assert any("não localizada" in x for x in por_trecho["eleitoral do conselho"]["motivos_invalidade"])
    assert any("parágrafo 1, não no 2" in x for x in por_trecho["consulta trata"]["motivos_invalidade"])


def test_limite_de_palavras_e_conflito() -> None:
    m = load()
    res = m.validar(
        MINUTA,
        [lote(m, "a", prop("cinco dias úteis", "cinco dias úteis contados da intimação pessoal do interessado")),
         lote(m, "b", prop("cinco dias", "dez dias")),
         lote(m, "c", prop("A consulta trata", " ".join(["x"] * 20)))],
        max_palavras=20,
    )
    e1, e2, e3 = res["emendas"]
    assert e1["status"] == e2["status"] == "valida" and e1["grupo_conflito"] == e2["grupo_conflito"] == "C1"
    assert e3["status"] == "valida" and "palavras" in e3["alertas"][0]
    ap = m.apurar(res, [votos(m, "x", E03="aceitar")])
    with pytest.raises(SystemExit, match="acima do limite"):
        m.aplicar(MINUTA, [ap], max_palavras=20)
    assert m.aplicar(MINUTA, [ap])[1][0]["id"] == "E03"


def _validadas(m):
    return m.validar(MINUTA, [lote(m, "gemini",
                                   prop("A consulta trata", "A consulta versa"),
                                   prop("cinco dias úteis", "cinco dias úteis, contados da intimação"),
                                   prop("e o prazo é prorrogável", "prorrogável uma vez"),
                                   prop("restringe a vedação", "estende a vedação"))])


def test_apuracao_unanimidade_ajuste_e_dissenso() -> None:
    m = load()
    val = _validadas(m)
    ap = m.apurar(val, [
        votos(m, "gemini", E01="aceitar", E02="ajustar:cinco dias úteis da intimação", E03="aceitar", E04="aceitar"),
        votos(m, "codex", E01="aceitar", E02="ajustar:cinco dias úteis da intimação", E03="ajustar:prorrogável", E04="rejeitar"),
        votos(m, "claude", E01="aceitar", E02="ajustar:cinco dias úteis da intimação", E03="ajustar:prorrogável por igual período", E04="rejeitar"),
        {"votante": "velho", "hash_minuta": "1" * 64, "votos": []},
    ])
    d = {r["id"]: r for r in ap["emendas"]}
    assert ap["votantes"] == ["gemini", "codex", "claude"] and ap["votantes_recusados"][0]["votante"] == "velho"
    assert d["E01"]["decisao"] == "aprovada"
    assert d["E02"]["decisao"] == "aprovada_com_ajuste" and d["E02"]["texto_aprovado"] == "cinco dias úteis da intimação"
    assert d["E03"]["decisao"] == "segunda_rodada" and len(d["E03"]["variantes"]) == 3
    assert d["E04"]["decisao"] == "dissenso"
    misto = m.apurar(val, [votos(m, "a", E02="aceitar"), votos(m, "b", E02="ajustar:cinco dias úteis da intimação")])
    assert misto["emendas"][1]["decisao"] == "segunda_rodada"  # o ajuste não teve a adesão de quem aceitou a original
    assert m.apurar(val, [votos(m, "a", E04="rejeitar")])["emendas"][3]["decisao"] == "rejeitada"
    maioria = m.apurar(val, [votos(m, "a", E04="aceitar"), votos(m, "b", E04="aceitar"), votos(m, "c", E04="rejeitar")], "maioria")
    assert maioria["emendas"][3]["decisao"] == "aprovada"
    assert m.apurar(val, [votos(m, "a", E04="aceitar"), votos(m, "b", E04="aceitar"), votos(m, "c", E04="rejeitar")],
                    "qualificada:3/4")["emendas"][3]["decisao"] == "dissenso"


def test_segunda_rodada_e_aplicacao(tmp_path: Path) -> None:
    m = load()
    val = _validadas(m)
    ap1 = m.apurar(val, [
        votos(m, "gemini", E01="aceitar", E02="aceitar", E03="ajustar:prorrogável uma única vez", E04="rejeitar"),
        votos(m, "codex", E01="aceitar", E02="aceitar", E03="aceitar", E04="rejeitar"),
    ])
    val2 = m.segunda_rodada(ap1)
    assert [e["id"] for e in val2["emendas"]] == ["E03a", "E03b"]
    assert "ajustar" not in m.cedula(val2).split("## Resposta")[1].split("```")[0]
    ap2 = m.apurar(val2, [votos(m, "gemini", E03a="rejeitar", E03b="aceitar"), votos(m, "codex", E03a="aceitar", E03b="aceitar")])
    assert {r["id"]: r["decisao"] for r in ap2["emendas"]} == {"E03a": "preterida", "E03b": "aprovada"}
    with pytest.raises(SystemExit):
        m.segunda_rodada(ap2)
    texto, aplicadas = m.aplicar(MINUTA, [ap1, ap2])
    assert [r["id"] for r in aplicadas] == ["E01", "E02", "E03b"]
    assert "1. A consulta versa sobre" not in texto and "1. A consulta versa do regulamento" in texto
    assert "cinco dias úteis, contados da intimação, prorrogável uma única vez." in texto
    rel = m.relatorio("v.md", "v2.md", m.sha256_texto(MINUTA), m.sha256_texto(texto), [ap1, ap2])
    assert "## Aplicadas (3)" in rel and "## Dissenso — decisão humana (0)" in rel and "## Rejeitadas (1)" in rel


def test_cli_ponta_a_ponta_e_hash_da_minuta(tmp_path: Path) -> None:
    m = load()
    minuta = tmp_path / "v.md"
    minuta.write_text(MINUTA, encoding="utf-8")
    (tmp_path / "p.json").write_text(json.dumps(lote(m, "gemini", prop("A consulta trata", "A consulta versa"))), encoding="utf-8")
    (tmp_path / "v1.json").write_text(json.dumps(votos(m, "codex", E01="aceitar")), encoding="utf-8")
    run = lambda *a: m.main([str(x) for x in a])
    assert run("validar", "--minuta", minuta, "--propostas", tmp_path / "p.json", "--saida", tmp_path / "val.json") == 0
    assert run("cedula", "--validadas", tmp_path / "val.json", "--saida", tmp_path / "ced.md") == 0
    ced = (tmp_path / "ced.md").read_text(encoding="utf-8")
    assert m.sha256_texto(MINUTA) in ced and "gemini" not in ced
    assert run("apurar", "--validadas", tmp_path / "val.json", "--votos", tmp_path / "v1.json", "--votantes", "codex",
               "--saida", tmp_path / "ap.json") == 0
    assert run("aplicar", "--minuta", minuta, "--apuracao", tmp_path / "ap.json", "--saida", tmp_path / "v2.md",
               "--relatorio", tmp_path / "rel.md") == 0
    assert "A consulta versa" in (tmp_path / "v2.md").read_text(encoding="utf-8")
    minuta.write_text(MINUTA + "\n4. Novo.\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        run("aplicar", "--minuta", minuta, "--apuracao", tmp_path / "ap.json", "--saida", tmp_path / "v3.md",
            "--relatorio", tmp_path / "rel3.md")
