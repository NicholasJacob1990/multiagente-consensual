"""Casos adversariais sintéticos: validade mecânica não substitui revisão jurídica."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def m():
    return load("emendas_regressoes", "skills/loop-debate-agentes/scripts/emendas.py")


M = "1. A parte preserva seus direitos de cobrança.\n"
J = {
    "defeito": "A conclusão contradiz a premissa expressa no mesmo documento.",
    "suporte": "A premissa consta do primeiro parágrafo da minuta.",
    "consequencia": "O destinatário não consegue executar a orientação de forma coerente.",
    "insuficiencia_aplicacao_direta": "A aplicação da norma não elimina dois comandos textuais incompatíveis.",
}


def proposal(**kw):
    return {"trecho": "preserva seus direitos de cobrança", "proposta": "mantém seus direitos de cobrança",
            "tipo": "redacao", "classificacao": "redacional", "fundamento": "Precisão do texto.",
            "nivel_fonte": "minuta_atual", "fonte_ref": "Minuta-base, parágrafo 1",
            "fonte_literal": "preserva seus direitos de cobrança", **kw}


def validated(m, p, text=M, **kw):
    return m.validar(text, [{"autor": "a", "hash_minuta": m.sha256_texto(text), "propostas": [p]}], **kw)


def vote(m, v, who, **kw):
    return {"votante": who, "hash_minuta": v["hash_minuta"],
            "votos": [{"id": "E01", "voto": "aceitar", "motivo": "Conferido no teste.", **kw}]}


def test_concessao_contratual_exige_autorizacao_em_qualquer_classificacao(m):
    v = validated(m, proposal(proposta="renuncia definitivamente a todos os créditos",
                              classificacao="aperfeicoamento_material"), tipo_documento="generico")
    assert v["emendas"][0]["status"] == "valida"
    ap = m.apurar(v, [vote(m, v, n) for n in ["a", "b"]], exigidos=["a", "b"])
    text, applied = m.aplicar(M, [ap])
    assert text == M and applied == []
    assert [r["id"] for r in m.aguardando_humano([ap])] == ["E01"]
    text, applied = m.aplicar(M, [ap], autorizadas=("E01",))
    assert "renuncia" in text and len(applied) == 1


def test_reserva_declarada_independe_de_palavra_chave_e_tipo(m):
    v = validated(m, proposal(proposta="aceita o valor final oferecido pela contraparte",
                              efeitos_reservados=["concessao_negocial"]), tipo_documento="generico")
    ap = m.apurar(v, [vote(m, v, "a")], exigidos=["a"])
    assert m.aplicar(M, [ap])[1] == []


@pytest.mark.parametrize("tipo", ["acrescimo", "precisao", "redacao", "corte", "remissao"])
def test_merito_sem_suporte_nao_e_dispensado_pelo_tipo(m, tipo):
    v = validated(m, proposal(tipo=tipo, classificacao="aperfeicoamento_material",
                              nivel_fonte="ausente_no_dossie", fonte_literal=""), fontes="")
    assert v["emendas"][0]["status"] == "invalida"


def test_fonte_literal_externa_exige_corpus_real(m):
    v = validated(m, proposal(tipo="fonte", fonte_ref="Norma sintética", nivel_fonte="reproducao_literal",
                              fonte_literal="Texto que não foi recebido."))
    assert v["emendas"][0]["status"] == "invalida"


@pytest.mark.parametrize("bad", ["porque sim", {}, {"defeito": "há um erro"}, {**J, "suporte": ""}])
def test_correcao_necessaria_exige_quatro_componentes(m, bad):
    v = validated(m, proposal(classificacao="correcao_necessaria", justificativa_obrigatoriedade=bad))
    assert v["emendas"][0]["status"] == "invalida"
    assert any("justificativa de obrigatoriedade" in s for s in v["emendas"][0]["motivos_invalidade"])


def test_correcao_interna_estruturada_tem_suporte_na_minuta(m):
    v = validated(m, proposal(classificacao="correcao_necessaria", justificativa_obrigatoriedade=J))
    assert v["emendas"][0]["status"] == "valida"


def test_reclassificacao_no_voto_nao_contorna_requisitos(m):
    v = validated(m, proposal())
    ap = m.apurar(v, [vote(m, v, n, voto="ajustar", classificacao="correcao_necessaria")
                      for n in ["a", "b"]], exigidos=["a", "b"])
    assert ap["emendas"][0]["decisao"] not in m.APROVADAS
    assert m.aplicar(M, [ap])[1] == []


def test_variante_valida_conserva_justificativa_e_reserva(m):
    v = validated(m, proposal())
    ap = m.apurar(v, [vote(m, v, n, voto="ajustar", classificacao="correcao_necessaria",
                           justificativa_obrigatoriedade=J, efeitos_reservados=["mudanca_estrategia"])
                      for n in ["a", "b"]], exigidos=["a", "b"])
    r = ap["emendas"][0]
    assert r["decisao"] == "aprovada_com_ajuste"
    assert r["justificativa_obrigatoriedade"] == J
    assert m.aplicar(M, [ap])[1] == []


MIXED = "O autor apresenta os fatos.\n\nOs fundamentos exigem análise.\n\n## Pedidos\n\n1. Concessão da tutela.\n\n2. Citação da parte ré.\n"


def test_documento_misto_preserva_todas_as_unidades(m):
    limits = m.limites_paragrafos(MIXED)
    assert len(limits) == 4
    assert any(start <= MIXED.index("Os fundamentos") < end for _, start, end in limits)
    pm = load("parecer_md_misto", "skills/redacao-juridica-consensual/scripts/parecer_md.py")
    doc = pm.parse(MIXED)
    assert doc.numeracao == "mista" and len(doc.paragrafos) == 4
    assert [p.numero for p in doc.paragrafos] == [n for n, _, _ in limits]


def test_edita_narrativa_mista_sem_alterar_pedidos(m):
    p = proposal(trecho="Os fundamentos exigem análise.", proposta="Os fundamentos demonstram o pedido.", paragrafo=2)
    v = validated(m, p, MIXED)
    assert v["emendas"][0]["status"] == "valida"
    ap = m.apurar(v, [vote(m, v, "a")], exigidos=["a"])
    text, _ = m.aplicar(MIXED, [ap])
    assert "demonstram o pedido" in text and "1. Concessão da tutela." in text


def test_negacao_de_renuncia_nao_e_concessao(m):
    v = validated(m, proposal(proposta="não renuncia aos seus direitos de cobrança"))
    ap = m.apurar(v, [vote(m, v, "a")], exigidos=["a"])
    assert len(m.aplicar(M, [ap])[1]) == 1


def test_confirmacao_nao_adota_renuncia_fora_das_emendas_autorizadas(m):
    v = validated(m, proposal(proposta="renuncia aos créditos", classificacao="aperfeicoamento_material"))
    ap = m.apurar(v, [vote(m, v, "a")], exigidos=["a"])
    text, _ = m.aplicar(M, [ap], autorizadas=("E01",))
    lotes = [{"votante": "a", "hash_minuta": m.sha256_texto(M), "hash_resultado": m.sha256_texto(text),
              "adesao": "aceito", "conflitos": []}]
    with pytest.raises(SystemExit, match="autorizadas"):
        m.confirmar(M, text, lotes, exigidos=["a"], apuracoes=[ap])
    assert m.confirmar(M, text, lotes, exigidos=["a"], apuracoes=[ap], autorizadas=("E01",))["conjunto_aprovado"]


def test_recibo_v1_nao_recebe_aprovacao_por_v2(m):
    v = validated(m, proposal())
    v["contrato"] = "emendas_consensuais_v1"
    with pytest.raises(SystemExit, match="legado"):
        m.apurar(v, [vote(m, v, "a")], exigidos=["a"])


def test_variante_com_novo_suporte_precisa_mesmo_corpus(m):
    corpus = m.normalizar("Documento de teste: o texto é substituível. Outra passagem permite corrigir a instrução.")
    v = validated(m, proposal(), fontes=corpus)
    votes = [vote(m, v, "a", voto="ajustar", classificacao="aperfeicoamento_material",
                  nivel_fonte="reproducao_literal", fonte_ref="Documento de teste",
                  fonte_literal="Outra passagem permite corrigir a instrução.")]
    assert m.apurar(v, votes, exigidos=["a"])["emendas"][0]["decisao"] not in m.APROVADAS
    ap = m.apurar(v, votes, exigidos=["a"], fontes=corpus)
    assert ap["emendas"][0]["decisao"] in m.APROVADAS
    assert m.aplicar(M, [ap])[1]
    with pytest.raises(SystemExit, match="fontes divergentes"):
        m.apurar(v, votes, exigidos=["a"], fontes="outro corpus")


def test_caixa_diferente_nao_e_redacao_exata_unanime(m):
    v = validated(m, proposal())
    ap = m.apurar(v, [vote(m, v, "a", voto="ajustar", ajuste="Texto Definido"),
                      vote(m, v, "b", voto="ajustar", ajuste="texto definido")], exigidos=["a", "b"])
    assert ap["emendas"][0]["decisao"] == "segunda_rodada"


def test_debate_conserva_metadados_da_variante_final(m):
    v = validated(m, proposal())
    ap1 = m.apurar(v, [vote(m, v, "a", voto="ajustar", classificacao="correcao_necessaria",
                            justificativa_obrigatoriedade=J, efeitos_reservados=["concessao_negocial"]),
                       vote(m, v, "b", voto="rejeitar")], exigidos=["a", "b"])
    second = m.segunda_rodada(ap1)
    variant = next(e for e in second["emendas"] if e["classificacao"] == "correcao_necessaria")
    votes = [{"votante": n, "hash_minuta": second["hash_minuta"], "votos": [
        {"id": variant["id"], "voto": "aceitar", "motivo": "Conferi os quatro fundamentos.",
         "razao_nova": "A variante explicita a consequência e a reserva do responsável."}]} for n in ["a", "b"]]
    ap2 = m.apurar(second, votes, exigidos=["a", "b"])
    r = next(r for r in ap2["emendas"] if r["decisao"] in m.APROVADAS)
    assert r["justificativa_obrigatoriedade"] == J
    assert m.aplicar(M, [ap1, ap2])[1] == []


def test_metadado_de_reserva_malformado_e_rejeitado_sem_abort(m):
    v = validated(m, proposal(efeitos_reservados=True))
    assert v["emendas"][0]["status"] == "invalida"


def test_variante_com_ajuste_nao_textual_nao_recebe_voto(m):
    v = validated(m, proposal())
    ap = m.apurar(v, [vote(m, v, "a", voto="ajustar", ajuste=123)], exigidos=["a"])
    assert ap["emendas"][0]["decisao"] not in m.APROVADAS
