from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "redacao-juridica-consensual" / "scripts"
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml"')


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


vr = load("verificar_remissoes")


def refs(texto: str, item: bool = False):
    rems = vr.remissoes_item(texto) if item else vr.remissoes_paragrafo(texto)
    return [[(r.inicio, r.fim, r.faixa, r.romano) for r in rem.refs] for rem in rems]


PARECER = """# Parecer

## I. Relatório

1. A consulta examina o regulamento eleitoral (Anexo de Redações Sugeridas, item 5).
2. Os itens 4 e 44 do Anexo tratam do prazo de impugnação.
3. As etapas são (i) registro; (ii) votação; (iii) apuração.
4. Conforme o parágrafo 3, iii, a apuração é pública; o parágrafo 3, iv, não existe.
5. Ver parágrafos 1 a 3, 7 e 9; par. 2; pars. 4 e 5.
6. O parágrafos 2 e 3 admite a solução; nos parágrafos 4 e 5, trata-se do edital.
7. Os itens 4 a 7 e o item 54, V, ficam mantidos; o item 8.6 e o item 3 do Anexo II não contam.
8. O § 1º do art. 2º deve prever prazo. O art. 3º, parágrafo único (sugerido), resolve. O art. 2º, I, basta.
9. A lei incide (Lei nº 15.177/2025, arts. 2º, § 2º, e 3º); o prazo segue a Lei nº 15.177/2025, art. 2º, § 2º, e o art. 9º regula a posse.
10. Ver parágrafo 12 e parágrafos 8 a 6.
"""

ANEXO = """ANEXO DE REDAÇÕES SUGERIDAS
Item 4 – Prazo de impugnação
Classificação: correção necessária
Fundamento: parecer, parágrafos 2 e 3
Item 5 – Registro
Fundamento: parecer, parágrafo 15
Item 6 – Votação
Fundamento: parecer, par. 180; pars. 9 e 10
Item 7 – Apuração
Observação: ver item 9
"""

OFICIAL = """Art. 1º Este regulamento disciplina a eleição.
Art. 2º O representante será eleito por voto direto.
I – dos empregados ativos;
Art. 3º A Comissão conduz o processo.
§ 1º A Comissão tem três membros.
"""
REVISADA = OFICIAL.replace("I – dos empregados ativos;\n", "I – dos empregados ativos;\n§ 1º O prazo de impugnação é de cinco dias.\n")


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


def preparar(tmp_path: Path) -> dict:
    arquivos = {"parecer": PARECER, "anexo": ANEXO, "oficial": OFICIAL, "revisada": REVISADA}
    out = {}
    for nome, texto in arquivos.items():
        out[nome] = tmp_path / f"{nome}.{'md' if nome == 'parecer' else 'txt'}"
        out[nome].write_text(texto, encoding="utf-8")
    out["comentarios"] = docx(tmp_path / "com.docx", [("Texto.", True)],
                              [("Revisor", "Ver parágrafo 20 e itens 6 e 99."), ("Autor", "Feito, conforme parágrafo 3.")])
    return out


def achados(r: dict, regra: str, severidade: str | None = None) -> list[dict]:
    return [a for a in r["achados"] if a["regra"] == regra and (severidade is None or a["severidade"] == severidade)]


# ---------------------------------------------------------------- regressões das expressões

def test_regressoes_de_remissao_a_paragrafo() -> None:
    assert refs("parágrafos 31 a 34, 37 e 91") == [[(31, 34, True, None), (37, 37, False, None), (91, 91, False, None)]]
    assert refs("par. 180; pars. 93 e 94") == [[(180, 180, False, None)], [(93, 93, False, None), (94, 94, False, None)]]
    assert refs("conforme o parágrafo 103, iii, do parecer") == [[(103, 103, False, "iii")]]
    assert refs("parágrafo 2º do art. 17") == [] and refs("parágrafo único") == []
    assert refs("parágrafos 3 e 4 do art. 5") == [] and refs("parágrafo 4.2 do manual") == []
    assert refs("parágrafos 9 a 7") == [[(9, 7, True, None)]]


def test_regressoes_de_remissao_a_item() -> None:
    assert refs("item 5", item=True) == [[(5, 5, False, None)]]
    assert refs("itens 4 e 44", item=True) == [[(4, 4, False, None), (44, 44, False, None)]]
    assert refs("itens 4 a 7", item=True) == [[(4, 7, True, None)]]
    assert refs("item 54, V, do Anexo", item=True) == [[(54, 54, False, "V")]]
    assert refs("o item 8.6 do edital", item=True) == []
    assert refs("item 3 do Anexo II", item=True) == [] and refs("item 2 do formulário", item=True) == []
    assert refs("subitem 4", item=True) == []


def test_regressoes_de_concordancia() -> None:
    msgs = [m for _, m in vr.problemas_concordancia("O parágrafos 185 e 186 admite a solução.")]
    assert any("artigo singular" in m for m in msgs) and any("«admite»" in m for m in msgs)
    assert vr.problemas_concordancia("do parágrafos 4 e 5") and vr.problemas_concordancia("os parágrafo 5 diz")
    assert vr.problemas_concordancia("Os parágrafos 3 e 4 cita o edital.")
    assert vr.problemas_concordancia("nos parágrafos 3 e 4, trata-se do edital") == []
    assert vr.problemas_concordancia("os parágrafos 3 e 4 admitem a solução") == []


# ---------------------------------------------------------------- conferir

def test_conferir_remissoes_itens_e_dispositivos(tmp_path: Path) -> None:
    f = preparar(tmp_path)
    r = vr.conferir(f["parecer"], f["anexo"], f["oficial"], f["revisada"], [f["comentarios"]])
    assert r["paragrafos_numerados"] == 10 and r["itens_anexo"] == [4, 5, 6, 7] and r["ok"] is False

    par = {(a["local"], a["mensagem"].split("»")[0]) for a in achados(r, "remissao_paragrafo")}
    assert any(l == "parecer § 10" and "parágrafo 12" in m for l, m in par)
    assert any("Anexo, item 5 (Fundamento)" in l for l, _ in par)  # "parágrafo 15" no Fundamento
    assert any("Anexo, item 6 (Fundamento)" in l and "par. 180" in m for l, m in par)
    assert any(l.startswith("comentário 0 (Revisor)") for l, _ in par)
    assert not any(l.startswith("comentário 1") for l, _ in par)
    assert not any(l == "parecer § 5" for l, _ in par)  # 1 a 3, 7, 9, par. 2 e pars. 4 e 5 existem
    assert [a["local"] for a in achados(r, "intervalo_invertido")] == ["parecer § 10"]
    romanos = achados(r, "numeral_romano")
    assert len(romanos) == 1 and "(iv)" in romanos[0]["mensagem"]  # "parágrafo 3, iii" existe; "3, iv" não

    itens = {(a["local"], a["mensagem"]) for a in achados(r, "remissao_item")}
    assert any(l == "parecer § 2" and "item 44" in m for l, m in itens)
    assert any(l == "parecer § 7" and "item 54" in m for l, m in itens)
    assert any("Anexo, item 7 (Observação)" in l and "item 9" in m for l, m in itens)
    assert any(l.startswith("comentário 0") and "item 99" in m for l, m in itens)
    assert not any(l in ("parecer § 1", "parecer § 7") and ("8" in m.split("item")[-1][:3]) for l, m in itens)
    assert sum(l == "parecer § 7" for l, _ in itens) == 1  # 4 a 7 existem; 8.6 e Anexo II ignorados

    conc = achados(r, "concordancia", "alerta")
    assert {a["local"] for a in conc} == {"parecer § 6"} and len(conc) == 2

    disp = achados(r, "dispositivo", "alerta")
    msgs = {a["mensagem"] for a in disp if a["local"] == "parecer § 8"}
    assert msgs == {"«art. 2º, § 1º»: dispositivo inexistente na minuta oficial sem a marca 'sugerido' (existe só na minuta revisada)"}
    assert not any("§ 2º" in a["mensagem"] for a in disp)  # citações da Lei nº 15.177/2025 ficam de fora
    assert not any(a["local"] == "parecer § 9" for a in disp)  # a oração do art. 9º menciona a Lei: fica de fora
    impl = achados(r, "diploma_implicito", "info")
    assert len(impl) == 1 and impl[0]["local"] == "parecer § 9" and "Lei nº 15.177/2025" in impl[0]["mensagem"]


def test_conferir_parecer_docx_conta_numpr_e_cli(tmp_path: Path, capsys) -> None:
    path = docx(tmp_path / "p.docx", [
        ("I. RELATÓRIO", False),
        ("A consulta trata do regulamento.", True),
        ("", True),  # numerado sem texto não conta
        ("Ver parágrafo 1 e parágrafo 3.", True),
    ])
    r = vr.conferir(path)
    assert r["paragrafos_numerados"] == 2
    assert [a["mensagem"][:18] for a in achados(r, "remissao_paragrafo")] == ["«parágrafo 3» apon"]
    assert vr.main(["conferir", "--parecer", str(path), "--json", str(tmp_path / "r.json")]) == 1
    assert "PENDÊNCIAS" in capsys.readouterr().out
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["contagem"]["bloqueante"] == 1
    limpo = tmp_path / "limpo.md"
    limpo.write_text("1. Texto.\n2. Ver parágrafo 1.\n", encoding="utf-8")
    assert vr.main(["conferir", "--parecer", str(limpo)]) == 0
    assert vr.main(["conferir", "--parecer", str(tmp_path / "nao_existe.md")]) == 2


# ---------------------------------------------------------------- mapear e renumerar

ANTIGO = """1. A consulta trata do regulamento eleitoral da empresa estatal e de seus prazos.
2. O prazo de impugnação é curto e prejudica (i) a defesa e (ii) o recurso dos candidatos. A comissão deve publicar (iii) o edital com antecedência mínima de dez dias.
3. Conforme o parágrafo 2, o prazo é curto.
4. É o parecer.
"""
NOVO = """1. A consulta trata do regulamento eleitoral da empresa estatal e de seus prazos.
2. O prazo de impugnação é curto e prejudica (i) a defesa e (ii) o recurso dos candidatos.
3. A comissão deve publicar (iii) o edital com antecedência mínima de dez dias.
4. Conforme o parágrafo 2, o prazo é curto; ver também parágrafos 1 a 3; e o parágrafo 2, iii, trata do edital.
5. É o parecer.
"""
ANEXO_JSON = {"itens": [{"item": 4, "fundamento": "parecer, parágrafo 2", "paragrafos_parecer": [2, 3]}]}


def mapa(tmp_path: Path) -> tuple[dict, Path, Path]:
    (tmp_path / "antigo.md").write_text(ANTIGO, encoding="utf-8")
    novo = tmp_path / "novo.md"
    novo.write_text(NOVO, encoding="utf-8")
    anexo = tmp_path / "anexo.json"
    anexo.write_text(json.dumps(ANEXO_JSON, ensure_ascii=False), encoding="utf-8")
    assert vr.main(["mapear", "--antigo", str(tmp_path / "antigo.md"), "--novo", str(novo), "--em", str(anexo),
                    "--saida", str(tmp_path / "mapa.json")]) == 0
    return json.loads((tmp_path / "mapa.json").read_text(encoding="utf-8")), novo, anexo


def test_mapear_divisao_e_decisoes(tmp_path: Path) -> None:
    m, _, _ = mapa(tmp_path)
    assert m["mapa"] == {"1": [1], "2": [2, 3], "3": [4], "4": [5]} and m["divididos"] == [2]
    ds = m["decisoes"]
    assert len(ds) == 4 and all(d["escolha"] is None and d["antigo"] == 2 for d in ds)
    assert [p["numero"] for p in ds[0]["partes"]] == [2, 3] and ds[0]["partes"][1]["inicio"].startswith("A comissão deve publicar")
    assert ds[0]["contexto"] == "Conforme o parágrafo 2, o prazo é curto;"
    assert ds[1]["romano"] == "iii" and ds[1]["sugestao"] == "b"  # "(iii)" só está na segunda parte
    assert {d["local"].split(":")[0] for d in ds[2:]} == {"anexo.json"}
    assert ds[3]["contexto"] == "paragrafos_parecer = [2, 3]"


def test_alinhar_tolera_pequena_edicao_e_fusao() -> None:
    antigos = [(1, "A consulta trata do regulamento eleitoral da empresa estatal."),
               (2, "O prazo é curto e prejudica a defesa dos candidatos inscritos."),
               (3, "A comissão publica o edital com antecedência mínima de dez dias úteis.")]
    novos = [(1, "A consulta examina o regulamento eleitoral da empresa estatal."),
             (2, "O prazo é curto e prejudica a defesa dos candidatos inscritos. A comissão publica o edital com "
                 "antecedência mínima de dez dias úteis.")]
    assert vr.alinhar(antigos, novos) == {1: [1], 2: [2], 3: [2]}


def test_renumerar_recusa_sem_escolha_e_aplica_escolhas(tmp_path: Path, capsys) -> None:
    m, novo, anexo = mapa(tmp_path)
    saida = tmp_path / "novo_renum.md"
    assert vr.main(["renumerar", "--mapa", str(tmp_path / "mapa.json"), "--entrada", str(novo), "--saida", str(saida)]) == 1
    out = capsys.readouterr().out
    assert "RECUSADO" in out and "parágrafo antigo 2 (partes novas: 2, 3)" in out and not saida.exists()

    escolhas = {0: "todas", 1: "b", 2: "b", 3: "a"}
    for i, d in enumerate(m["decisoes"]):
        d["escolha"] = escolhas[i]
    (tmp_path / "mapa.json").write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    assert vr.main(["renumerar", "--mapa", str(tmp_path / "mapa.json"), "--entrada", str(novo), "--saida", str(saida)]) == 0
    out = capsys.readouterr().out
    linha = saida.read_text(encoding="utf-8").split("\n")[3]
    assert linha == ("4. Conforme os parágrafos 2 e 3, o prazo é curto; ver também parágrafos 1 a 4; "
                     "e o parágrafo 3, iii, trata do edital.")
    assert "conferir a concordância do verbo" in out and "«o parágrafo 2» → «os parágrafos 2 e 3»" in out

    saida_json = tmp_path / "anexo_renum.json"
    assert vr.main(["renumerar", "--mapa", str(tmp_path / "mapa.json"), "--entrada", str(anexo), "--saida", str(saida_json)]) == 0
    item = json.loads(saida_json.read_text(encoding="utf-8"))["itens"][0]
    assert item == {"item": 4, "fundamento": "parecer, parágrafo 3", "paragrafos_parecer": [2, 4]}


def test_renumerar_flexiona_e_rejeita_escolha_invalida() -> None:
    dados = {"mapa": {"5": [6, 7], "6": [8], "7": [9]},
             "decisoes": [{"id": "d1", "local": "x:linha 1", "contexto": "Ver o parágrafo 5.", "antigo": 5, "ordem": 0,
                           "partes": [], "escolha": "c"}]}
    rn = vr.Renumerador(dados)
    rn.texto("Ver o parágrafo 5.", "x:linha 1")
    assert rn.pendencias and "escolha inválida" in rn.pendencias[0]["motivo"]
    dados["decisoes"][0]["escolha"] = "a e b"
    rn = vr.Renumerador(dados)
    assert rn.texto("Ver o parágrafo 5.", "x:linha 1") == "Ver os parágrafos 6 e 7."
    rn = vr.Renumerador(dados)
    assert rn.texto("Do parágrafos 6 e 7 decorre; pars. 6 a 7.", "x:linha 2") == "Do parágrafos 8 e 9 decorre; pars. 8 a 9."


def test_dispositivo_de_outra_norma_nao_vira_alerta() -> None:
    """Falsos positivos do caso real: diploma antes do parêntese, depois de aposto, "ambos da Lei" e frase anterior."""
    oficial = vr.estrutura_minuta([vr.Unidade("minuta", "Art. 22 Texto."), vr.Unidade("minuta", "§ 3º Texto.")])
    casos = {
        "a": "A ação teve base no art. 140, § 1º (à época, parágrafo único), da Lei nº 6.404/1976, por ser societária.",
        "b": 'A restrição não decorre do Estatuto Social da Codemig (art. 22, § 1º), que menciona "empregados".',
        "c": "O texto reproduz a vedação do art. 17, § 2º, V (conflito de interesses), e a garantia do art. 19, ambos da Lei nº 13.303/2016.",
        "d": "A Lei Complementar nº 64/1990 (art. 1º, I, \"g\") rege a inelegibilidade.",
    }
    for k, t in casos.items():
        u = vr.Unidade(f"parecer § {k}", t, 1)
        assert [a for a in vr._conferir_dispositivos(u, oficial, None) if a.severidade == "alerta"] == [], k
    u = vr.Unidade("parecer § e", "A IN nº 076/2026 prevê a diligência. Contudo, o art. 12, § 1º, V, trata da eleição.", 1)
    r = vr._conferir_dispositivos(u, oficial, None)
    assert [a.severidade for a in r if a.regra == "dispositivo"] == ["info"]
    u = vr.Unidade("parecer § f", "Sugere-se acrescer o art. 22, § 4º, com nova regra.", 1)
    assert [a.severidade for a in vr._conferir_dispositivos(u, oficial, None) if a.regra == "dispositivo"] == ["alerta"]
    u = vr.Unidade("parecer § g", 'No Anexo I, o item 3 remete ao inexistente "art. 22, § 4º", que deve ser corrigido.', 1)
    assert [a for a in vr._conferir_dispositivos(u, oficial, None) if a.regra == "dispositivo"] == []
