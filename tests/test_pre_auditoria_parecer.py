from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "redacao-juridica-consensual" / "scripts"


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


ASSINATURA = """@DATA Belo Horizonte, 22 de outubro de 2026.

@ASS+ [Nome do(a) Advogado(a)]

@ASN OAB/MG [INFORMAR]

@ASN+ De acordo: [Gerente da GENES]

@ASS Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)
"""

CONCLUSAO = (
    "4. **Correções necessárias.** Ajustar o art. 31. **Obrigações já incidentes.** Publicar o edital. "
    "**Recomendações facultativas.** Prazo certo no art. 30. **Providências fora do regulamento.** Nenhuma."
)


def parecer(*corpo: str, conclusao: str = CONCLUSAO, fecho_n: int = 5) -> str:
    return "\n\n".join([
        "@CAB PARECER JURÍDICO CONSULTIVO",
        "## I. Relatório",
        *corpo,
        "## II. Conclusão",
        conclusao,
        f"{fecho_n}. É o parecer, sob censura.",
        ASSINATURA,
    ])


BASE = (
    "1. A consulta trata do regulamento eleitoral.",
    "2. O regulamento observa a Lei nº 13.303/2016, conforme o parágrafo 3.",
    "3. O art. 31 exige defesa, como visto no parágrafo 2.",
)


def run(tmp_path: Path, texto: str, *extra: str, anterior: str | None = None):
    mod = load("pre_auditoria_parecer")
    f = tmp_path / "v.md"
    f.write_text(texto, encoding="utf-8")
    argv = [str(f), "--perfil", "genes", "--json", str(tmp_path / "r.json"), *extra]
    if anterior is not None:
        a = tmp_path / "anterior.md"
        a.write_text(anterior, encoding="utf-8")
        argv += ["--anterior", str(a)]
    code = mod.main(argv)
    achados = json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["achados"]
    return code, achados


def regras(achados, severidade="bloqueante"):
    return sorted({a["regra"] for a in achados if a["severidade"] == severidade})


def test_parecer_limpo_aprova_e_isenta_assinatura(tmp_path: Path) -> None:
    code, achados = run(tmp_path, parecer(*BASE))
    assert code == 0
    assert regras(achados) == []


def test_numeracao_palavras_e_fecho(tmp_path: Path) -> None:
    longo = "3. " + " ".join(["palavra"] * 121)
    texto = parecer(BASE[0], BASE[1].replace("parágrafo 3", "parágrafo 1"), longo, conclusao=CONCLUSAO.replace("4.", "6."), fecho_n=7)
    code, achados = run(tmp_path, texto)
    assert code == 1
    assert {"numeracao", "palavras"} <= set(regras(achados))


def test_remissao_inexistente_e_autorremissao(tmp_path: Path) -> None:
    texto = parecer(BASE[0], "2. Ver parágrafo 9 e parágrafo 2.", BASE[2])
    _, achados = run(tmp_path, texto)
    msgs = [a["mensagem"] for a in achados if a["regra"] == "remissao"]
    assert any("não existe" in m for m in msgs)
    assert any("próprio parágrafo" in m for m in msgs)


def test_paragrafo_de_lei_nao_e_remissao(tmp_path: Path) -> None:
    pm = load("parecer_md")
    assert pm.remissoes("conforme o parágrafo 2º do art. 17 da Lei") == []
    assert pm.remissoes("nos termos do parágrafo único") == []
    assert pm.remissoes("ver parágrafos 86 a 88 e 90")[0][1] == [86, 87, 88, 90]


def test_marcador_solto_no_corpo_e_rotulo_ausente(tmp_path: Path) -> None:
    texto = parecer(BASE[0], "2. Prazo de [INFORMAR] dias, conforme o parágrafo 3.", BASE[2],
                    conclusao=CONCLUSAO.replace("**Obrigações já incidentes.**", "Obrigações já incidentes."))
    code, achados = run(tmp_path, texto)
    assert code == 1
    assert regras(achados) == ["conclusao", "marcador"]
    assert all(a["paragrafo"] == 2 for a in achados if a["regra"] == "marcador")


def test_julgado_repetido_por_extenso_e_abreviado(tmp_path: Path) -> None:
    texto = parecer(
        "1. A competência é da Justiça comum (CC nº 164.709/MG).",
        "2. O Superior Tribunal de Justiça, no Conflito de Competência nº 164.709/MG, decidiu assim; ver parágrafo 3.",
        BASE[2],
    )
    _, achados = run(tmp_path, texto)
    rep = [a for a in achados if a["regra"] == "julgado_repetido"]
    assert rep and "CC 164709" in rep[0]["mensagem"]


def test_renumeracao_quebra_remissao(tmp_path: Path) -> None:
    anterior = parecer(*BASE)
    inserido = "2. Parágrafo novo sobre a comissão de empregados e a junta eleitoral."
    sem_atualizar = parecer(BASE[0], inserido, "3. O regulamento observa a Lei nº 13.303/2016, conforme o parágrafo 3.",
                            "4. O art. 31 exige defesa, como visto no parágrafo 2.",
                            conclusao=CONCLUSAO.replace("4.", "5."), fecho_n=6)
    code, achados = run(tmp_path, sem_atualizar, anterior=anterior)
    assert code == 1
    assert "renumeracao" in regras(achados)
    atualizado = sem_atualizar.replace("conforme o parágrafo 3.", "conforme o parágrafo 4.").replace(
        "visto no parágrafo 2.", "visto no parágrafo 3.")
    code, achados = run(tmp_path, atualizado, anterior=anterior)
    assert "renumeracao" not in regras(achados)
    assert any(a["regra"] == "rescan" and a["paragrafo"] == 2 for a in achados)


def test_trecho_travado(tmp_path: Path) -> None:
    trav = tmp_path / "travados.json"
    trav.write_text(json.dumps([{"id": "metodologia", "paragrafo": 1, "texto": "A consulta trata do regulamento eleitoral."}]),
                    encoding="utf-8")
    code, _ = run(tmp_path, parecer(*BASE), "--travados", str(trav))
    assert code == 0
    alterado = parecer("1. A consulta versa sobre o regulamento eleitoral.", *BASE[1:])
    code, achados = run(tmp_path, alterado, "--travados", str(trav))
    assert code == 1 and regras(achados) == ["travado"]


def test_previsao_sem_cautela_vira_alerta(tmp_path: Path) -> None:
    texto = parecer("1. A eleição terminará em 17 de março de 2027.", *BASE[1:])
    _, achados = run(tmp_path, texto)
    assert any(a["regra"] == "calibracao" and a["severidade"] == "alerta" for a in achados)
    texto = parecer("1. A eleição poderá terminar, por estimativa, em 17 de março de 2027.", *BASE[1:])
    _, achados = run(tmp_path, texto)
    assert not any(a["regra"] == "calibracao" and a["severidade"] == "alerta" for a in achados)


def test_remissao_revisada_de_proposito_vira_informativo(tmp_path: Path) -> None:
    anterior = parecer(*BASE)
    inserido = "2. Parágrafo novo sobre a comissão de empregados e a junta eleitoral."
    novo = parecer(BASE[0], inserido, "3. O regulamento observa a Lei nº 13.303/2016, conforme o parágrafo 2.",
                   "4. O art. 31 exige defesa, como visto no parágrafo 3.", conclusao=CONCLUSAO.replace("4.", "5."), fecho_n=6)
    code, achados = run(tmp_path, novo, anterior=anterior)
    assert "renumeracao" in regras(achados)
    code, achados = run(tmp_path, novo, "--remissoes-revisadas", "3", anterior=anterior)
    assert "renumeracao" not in regras(achados)
    assert any(a["regra"] == "renumeracao" and a["severidade"] == "info" for a in achados)
