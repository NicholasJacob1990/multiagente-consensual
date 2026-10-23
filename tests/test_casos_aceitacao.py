"""Casos de aceitação da revisão por alterações consensuais (proposta de 23/10/2026).

Exemplos mínimos e anônimos, de parecer, petição e decisão. A numeração segue a
proposta; o caso 5 (vista atual de DOCX com revisões) fica para a leitura de DOCX.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MOTOR = ROOT / "skills" / "loop-debate-agentes" / "scripts"
JURIDICO = ROOT / "skills" / "redacao-juridica-consensual" / "scripts"


def load(pasta: Path, nome: str):
    sys.path.insert(0, str(pasta))
    spec = importlib.util.spec_from_file_location(nome, pasta / f"{nome}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


em = load(MOTOR, "emendas")
ac = load(MOTOR, "achados")
pa = load(JURIDICO, "pre_auditoria_parecer")
pm = load(JURIDICO, "parecer_md")
pk = load(JURIDICO, "pacote_auditoria")

PARECER = (
    "## I. Análise\n\n"
    "1. Compete à Comissão decidir as impugnações, e compete à Junta decidir as mesmas impugnações.\n\n"
    "2. O prazo de defesa é de cinco dias úteis, salvo motivo justificado.\n\n"
    "3. A votação pode levar cerca de dez dias úteis.\n\n"
    "## II. Conclusão\n\n"
    "4. Recomenda-se ajustar o art. 31 (parágrafo 1).\n\n"
    "5. É o parecer.\n"
)
PETICAO = (
    "# Contestação\n\n"
    "A autora alega dano moral sem demonstrar o fato constitutivo.\n\n"
    "O pedido é improcedente porque não houve conduta ilícita da ré.\n\n"
    "Requer a improcedência do pedido.\n"
)


def prop(trecho, proposta, classificacao="recomendacao_facultativa", tipo="redacao", **kw):
    return {"trecho": trecho, "proposta": proposta, "tipo": tipo, "classificacao": classificacao,
            "fundamento": "melhora a precisão", "nivel_fonte": "minuta_atual",
            "fonte_ref": "Minuta sintética do teste", "fonte_literal": trecho, **kw}


def obrigatoriedade(defeito):
    return {"defeito": defeito, "suporte": "Comando expressamente transcrito no material do teste.",
            "consequencia": "Incoerência na orientação que o destinatário deve executar.",
            "insuficiencia_aplicacao_direta": "A contradição entre comandos da minuta precisa de correção textual."}


def lote(minuta, autor, *props):
    return {"autor": autor, "hash_minuta": em.sha256_texto(minuta), "propostas": list(props)}


def votos(minuta, votante, **por_id):
    vs = []
    for i, v in por_id.items():
        if isinstance(v, dict):
            vs.append({"id": i, "motivo": "ok", **v})
        else:
            vs.append({"id": i, "voto": v, "motivo": "ok"})
    return {"votante": votante, "hash_minuta": em.sha256_texto(minuta), "votos": vs}


TRES = ["gemini", "codex", "claude"]


def unanimes(minuta, val, voto="aceitar"):
    ids = {e["id"]: voto for e in val["emendas"] if e["status"] == "valida"}
    return [votos(minuta, n, **ids) for n in TRES]


# 1 ---------------------------------------------------------------------------

def test_caso_01_achado_resolvido_nao_reaparece_sem_razao_nova() -> None:
    reg = ac.novo_registro()
    trecho = "compete à Junta decidir as mesmas impugnações"
    achado = {"descricao": "atribuições contraditórias entre Comissão e Junta", "trecho": trecho, "paragrafo": 1, "por": "codex"}
    assert ac.registrar(reg, [achado], em.sha256_texto(PARECER), 1)[0]["evento"] == "novo"
    corrigido = PARECER.replace(", e compete à Junta decidir as mesmas impugnações", "")
    ac.atualizar(reg, "A01", "resolvido", em.sha256_texto(corrigido), "§ 1 passou a atribuir só à Comissão")
    assert ac.verificar(reg, corrigido) == []
    assert ac.registrar(reg, [{**achado, "por": "gemini"}], em.sha256_texto(corrigido), 2)[0]["evento"] == "reabertura_recusada"
    assert reg["achados"][0]["estado"] == "resolvido"
    reab = {**achado, "reabertura": {"motivo": "regressao", "explicacao": "o trecho voltou na v3"}}
    assert ac.registrar(reg, [reab], em.sha256_texto(PARECER), 3)[0]["evento"] == "reaberto"
    assert ac.verificar(reg, corrigido)[0]["id"] == "A01"  # aberto, mas o trecho já não está no texto


# 2 ---------------------------------------------------------------------------

def test_caso_02_diagnostico_aceito_com_redacao_ou_classificacao_rejeitada_nao_e_consenso() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini", prop("cinco dias úteis", "dez dias úteis", "correcao_necessaria",
                                                            justificativa_obrigatoriedade=obrigatoriedade("prazo legal é de dez dias")))],
                     tipo_documento="parecer")
    ap = em.apurar(val, [
        votos(PARECER, "gemini", E01="aceitar"),
        votos(PARECER, "codex", E01={"voto": "rejeitar", "motivo": "concordo com o diagnóstico, não com a redação"}),
        votos(PARECER, "claude", E01="aceitar"),
    ], exigidos=TRES)
    assert ap["emendas"][0]["decisao"] == "dissenso"
    ap = em.apurar(val, [
        votos(PARECER, "gemini", E01="aceitar"),
        votos(PARECER, "codex", E01={"voto": "ajustar", "classificacao": "recomendacao_facultativa"}),
        votos(PARECER, "claude", E01="aceitar"),
    ], exigidos=TRES)
    r = ap["emendas"][0]
    assert r["decisao"] == "segunda_rodada" and {v["classificacao"] for v in r["variantes"]} == {"correcao_necessaria", "recomendacao_facultativa"}


def test_caso_02b_correcao_necessaria_exige_justificativa() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini", prop("cinco dias úteis", "dez dias úteis", "correcao_necessaria"))],
                     tipo_documento="parecer")
    assert "justificativa de obrigatoriedade" in val["emendas"][0]["motivos_invalidade"][0]


# 3 ---------------------------------------------------------------------------

def test_caso_03_cadeira_sem_resposta_nao_conta_como_adesao() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini", prop("É o parecer.", "É o parecer, sob censura."))])
    ap = em.apurar(val, [votos(PARECER, "gemini", E01="aceitar"), votos(PARECER, "codex", E01="aceitar")], exigidos=TRES)
    r = ap["emendas"][0]
    assert r["decisao"] == "dissenso" and r["placar"]["abstencao"] == 1
    assert ap["votantes_responderam"] == ["gemini", "codex"]
    vazio = {"votante": "claude", "hash_minuta": em.sha256_texto(PARECER), "votos": []}
    assert em.apurar(val, [votos(PARECER, "gemini", E01="aceitar"), votos(PARECER, "codex", E01="aceitar"), vazio],
                     exigidos=TRES)["emendas"][0]["decisao"] == "dissenso"
    rel = em.relatorio("v", "v2", "a", "b", [ap])
    assert "sem resposta válida de claude" in rel and "unanimidade" in rel


# 4 ---------------------------------------------------------------------------

def test_caso_04_mesmo_arquivo_com_outro_conteudo_invalida_vinculacao(tmp_path: Path) -> None:
    f = tmp_path / "minuta.md"
    f.write_text(PARECER, encoding="utf-8")
    val = em.validar(f.read_text(encoding="utf-8"), [lote(PARECER, "gemini", prop("É o parecer.", "É o parecer, sob censura."))])
    ap = em.apurar(val, unanimes(PARECER, val), exigidos=TRES)
    pacote = pk.montar(f, "Audite.")
    f.write_text(PARECER.replace("cinco", "seis"), encoding="utf-8")
    with pytest.raises(SystemExit, match="outra versão"):
        em.aplicar(f.read_text(encoding="utf-8"), [ap])
    novo_hash = pm.sha256_texto(f.read_text(encoding="utf-8"))
    assert not pk.verificar(f"HASH_RECEBIDO: {novo_hash}", pk.hash_do_pacote(pacote))[0]
    assert em.validar(f.read_text(encoding="utf-8"), [lote(PARECER, "gemini", prop("É o parecer.", "x"))])["lotes_recusados"]


# 6 ---------------------------------------------------------------------------

def test_caso_06_fonte_so_por_remissao_nao_sustenta_merito_nem_prova_invencao() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini",
                                    prop("cinco dias úteis", "dez dias úteis", "correcao_necessaria", tipo="correcao",
                                         justificativa_obrigatoriedade=obrigatoriedade("lei fixa dez dias"), fonte_literal="dez dias",
                                         nivel_fonte="remissao"))], tipo_documento="parecer")
    motivo = val["emendas"][0]["motivos_invalidade"][0]
    assert "remissao" in motivo and "não sustenta" in motivo and "invent" not in motivo


# 7 ---------------------------------------------------------------------------

def test_caso_07_emendas_isoladas_que_conflitam_no_conjunto_nao_entram() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini",
                                    prop("compete à Junta decidir as mesmas impugnações", "compete à Junta homologar o resultado"),
                                    prop("Recomenda-se ajustar o art. 31", "Recomenda-se atribuir à Junta as impugnações no art. 31"))])
    ap = em.apurar(val, unanimes(PARECER, val), exigidos=TRES)
    novo, aplicadas = em.aplicar(PARECER, [ap])
    assert len(aplicadas) == 2
    assert "## E01" in em.cedula_conjunto(PARECER, novo, aplicadas)
    hb, hn = em.sha256_texto(PARECER), em.sha256_texto(novo)
    conj = [{"votante": n, "hash_minuta": hb, "hash_resultado": hn, "adesao": "aceito"} for n in ("gemini", "claude")]
    conj.append({"votante": "codex", "hash_minuta": hb, "hash_resultado": hn, "adesao": "conflito",
                 "conflitos": [{"ids": ["E01", "E02"], "motivo": "o § 1 tira da Junta o que a conclusão lhe atribui"}]})
    res = em.confirmar(PARECER, novo, conj, exigidos=TRES, apuracoes=[ap])
    assert not res["conjunto_aprovado"] and res["ids_em_conflito"] == ["E01", "E02"]
    sem, _ = em.aplicar(PARECER, [ap], excluir=("E01", "E02"))
    assert sem == PARECER
    ok = [{"votante": n, "hash_minuta": hb, "hash_resultado": hn, "adesao": "aceito"} for n in TRES]
    assert em.confirmar(PARECER, novo, ok, exigidos=TRES, apuracoes=[ap])["conjunto_aprovado"]
    assert not em.confirmar(PARECER, novo, ok[:2], exigidos=TRES, apuracoes=[ap])["conjunto_aprovado"]  # silêncio não é adesão


# 8 e 9 -----------------------------------------------------------------------

def _pre(tmp_path: Path, anterior: str, atual: str, *extra: str) -> list[dict]:
    (tmp_path / "a.md").write_text(anterior, encoding="utf-8")
    (tmp_path / "b.md").write_text(atual, encoding="utf-8")
    pa.main([str(tmp_path / "b.md"), "--anterior", str(tmp_path / "a.md"), "--json", str(tmp_path / "r.json"), *extra])
    return json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["achados"]


def test_caso_08_reescrita_que_perde_a_ressalva(tmp_path: Path) -> None:
    achados = _pre(tmp_path, PARECER, PARECER.replace(", salvo motivo justificado.", "."))
    assert any(a["regra"] == "ressalva" and a["paragrafo"] == 2 for a in achados)


def test_caso_09_estimativa_vira_teto(tmp_path: Path) -> None:
    achados = _pre(tmp_path, PARECER, PARECER.replace("pode levar cerca de dez dias úteis", "leva até dez dias úteis"))
    msg = next(a["mensagem"] for a in achados if a["regra"] == "alcance")
    assert "«até» acrescentado" in msg and "«pode» retirado" in msg and "«cerca de» retirado" in msg


def test_caso_08b_frase_que_evaporou(tmp_path: Path) -> None:
    longo = PARECER.replace("salvo motivo justificado.", "salvo motivo justificado. A defesa será apresentada por escrito "
                            "perante a Comissão, que dará ciência ao impugnante no mesmo dia.")
    achados = _pre(tmp_path, longo, PARECER.replace("salvo motivo justificado.", "salvo motivo justificado. Há defesa."))
    assert any(a["regra"] == "cobertura" for a in achados)


# 10 --------------------------------------------------------------------------

def test_caso_10_dependencia_nao_atendida() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini",
                                    prop("compete à Junta decidir as mesmas impugnações", "compete à Junta homologar o resultado",
                                         dependencias=[4]),
                                    prop("Recomenda-se ajustar o art. 31 (parágrafo 1)", "Recomenda-se ajustar o art. 31 quanto à "
                                         "homologação (parágrafo 1)"))])
    so_e01 = em.apurar(val, [votos(PARECER, n, E01="aceitar", E02="rejeitar") for n in TRES], exigidos=TRES)
    with pytest.raises(SystemExit, match="dependências não atendidas"):
        em.aplicar(PARECER, [so_e01])
    ambas = em.apurar(val, unanimes(PARECER, val), exigidos=TRES)
    assert len(em.aplicar(PARECER, [ambas])[1]) == 2
    assert em.validar(PARECER, [lote(PARECER, "g", prop("É o parecer.", "x", dependencias=[99]))])["emendas"][0]["status"] == "invalida"


# 11 --------------------------------------------------------------------------

def test_caso_11_limite_afastado_pelo_usuario_nao_volta_por_padrao(tmp_path: Path) -> None:
    longo = "1. " + " ".join(["palavra"] * 130) + "\n\n2. É o parecer, sob censura.\n"
    f = tmp_path / "v.md"
    f.write_text(longo, encoding="utf-8")
    cfg = dict(pa.PERFIS["genes"], max_palavras=150, rotulos_conclusao=[], assinatura=[])
    achados = pa.auditar(pm.ler(f), cfg)
    assert not [a for a in achados if a.regra in ("palavras", "paginas")]


# 12 --------------------------------------------------------------------------

def test_caso_12_so_restam_preferencias_e_a_revisao_encerra() -> None:
    reg = ac.novo_registro()
    ac.registrar(reg, [{"descricao": "contradição", "trecho": "x", "material": True},
                       {"descricao": "preferir 'consoante'", "trecho": "y", "material": False}], "h", 1)
    assert not ac.resumo(reg)["pode_encerrar"]
    ac.atualizar(reg, "A01", "resolvido", "h2", "corrigido")
    assert ac.resumo(reg)["pode_encerrar"]
    val = em.validar(PARECER, [lote(PARECER, "gemini", prop("É o parecer.", "É o parecer, sob censura.", "redacional"))])
    ap = em.apurar(val, unanimes(PARECER, val), exigidos=TRES)
    assert "sem novas melhorias materiais consensuais" in em.relatorio("v", "v2", "a", "b", [ap])


# rodada de debate e outros trabalhos jurídicos --------------------------------

def test_debate_mudanca_de_posicao_exige_razao_nova() -> None:
    val = em.validar(PARECER, [lote(PARECER, "gemini", prop("É o parecer.", "É o parecer, sob censura."))])
    ap1 = em.apurar(val, [votos(PARECER, "gemini", E01="aceitar"), votos(PARECER, "codex", E01="aceitar"),
                          votos(PARECER, "claude", E01={"voto": "rejeitar", "motivo": "fecho não exigido"})], exigidos=TRES)
    assert ap1["emendas"][0]["decisao"] == "dissenso"
    val2 = em.segunda_rodada(ap1)
    assert "fecho não exigido" in em.cedula(val2) and "razao_nova" in em.cedula(val2)
    sem_razao = em.apurar(val2, [votos(PARECER, "gemini", E01a="aceitar"), votos(PARECER, "codex", E01a="aceitar"),
                                 votos(PARECER, "claude", E01a="aceitar")], exigidos=TRES)
    r = sem_razao["emendas"][0]
    assert r["decisao"] == "dissenso" and "sem razão nova" in r["votos"][2]["motivo"]
    com_razao = em.apurar(val2, [votos(PARECER, "gemini", E01a="aceitar"), votos(PARECER, "codex", E01a="aceitar"),
                                 votos(PARECER, "claude", E01a={"voto": "aceitar", "razao_nova": "o perfil da casa exige o fecho"})],
                          exigidos=TRES)
    assert com_razao["emendas"][0]["decisao"] == "aprovada"
    texto, _ = em.aplicar(PARECER, [ap1, com_razao])
    assert texto.endswith("É o parecer, sob censura.\n")


def test_peticao_sem_numeracao_e_classificacoes_de_peca(tmp_path: Path) -> None:
    lim = em.limites_paragrafos(PETICAO)
    assert [n for n, _, _ in lim] == [1, 2, 3]
    val = em.validar(PETICAO, [lote(PETICAO, "gemini",
                                    prop("sem demonstrar o fato constitutivo", "sem demonstrar o fato constitutivo do direito "
                                         "(CPC, art. 373, I)", "reforco_argumentativo"),
                                    prop("Requer a improcedência", "Requer a total improcedência", "obrigacao_incidente"))],
                     tipo_documento="peca")
    e1, e2 = val["emendas"]
    assert e1["status"] == "valida" and e1["paragrafo"] == 1
    assert e2["status"] == "invalida" and "peca" in e2["motivos_invalidade"][0]
    f = tmp_path / "p.md"
    f.write_text(PETICAO, encoding="utf-8")
    achados = pa.auditar(pm.ler(f), pa.PERFIS["generico"])
    assert not [a for a in achados if a.severidade == "bloqueante"]


def test_decisao_tem_conjunto_proprio() -> None:
    decisao = "1. Rejeito a preliminar.\n\n2. Julgo procedente o pedido.\n"
    val = em.validar(decisao, [lote(decisao, "g", prop("Julgo procedente o pedido.",
                                                       "Julgo procedente o pedido, nos termos do art. 487, I, do CPC.",
                                                       "aperfeicoamento_fundamentacao"))], tipo_documento="decisao")
    assert val["emendas"][0]["status"] == "valida" and "aperfeicoamento_fundamentacao" in val["classificacoes"]


def test_risco_estrategico_da_peca_so_entra_com_autorizacao_do_usuario() -> None:
    val = em.validar(PETICAO, [lote(PETICAO, "gemini", prop("Requer a improcedência do pedido.",
                                                            "Requer a improcedência do pedido e a condenação da autora por litigância de má-fé.",
                                                            "risco_estrategico"))], tipo_documento="peca")
    ap = em.apurar(val, unanimes(PETICAO, val), exigidos=TRES)
    assert ap["emendas"][0]["decisao"] == "aprovada"
    texto, aplicadas = em.aplicar(PETICAO, [ap])
    assert texto == PETICAO and aplicadas == []
    assert "reservadas à decisão humana (1)" in em.relatorio("v", "v2", "a", "b", [ap])
    texto, _ = em.aplicar(PETICAO, [ap], autorizadas=("E01",))
    assert "litigância de má-fé" in texto


def test_simbolo_de_citacao_perdido_na_renumeracao(tmp_path: Path) -> None:
    antes = PARECER.replace("salvo motivo justificado.", "salvo motivo justificado (Decreto, art. 25, §§ 2º e 3º).")
    achados = _pre(tmp_path, antes, antes.replace("§§ 2º e 3º", "2º e 3º"))
    assert any(a["regra"] == "citacao" and "§§" in a["mensagem"] for a in achados)
