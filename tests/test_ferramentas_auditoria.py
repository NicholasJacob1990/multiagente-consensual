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


BASE = """@CAB PARECER JURÍDICO CONSULTIVO

@CAB PROCESSO SEI Nº:| 5030.01.0001906/2026-15

## I. Relatório

1. A consulta trata do regulamento eleitoral (Lei nº 13.303/2016, art. 20; Estatuto, art. 22).

2. O art. 17, § 2º, I, da Lei nº 13.303/2016 veda a indicação, e os arts. 22 e 23 do Estatuto tratam do Conselho.

3. **Correções necessárias.** Ajustar o art. 31 do regulamento.

4. É o parecer, sob censura.

@ASS+ [Nome do(a) Advogado(a)]
"""
ALVO = BASE.replace("A consulta trata do", "A consulta examina o").replace(
    "3. **Correções", "3. Parágrafo novo sobre a junta eleitoral e a comissão.\n\n4. **Correções").replace(
    "4. É o parecer", "5. É o parecer")

LEI = """Art. 17. Os membros do Conselho de Administração serão escolhidos entre cidadãos de reputação ilibada.
§ 2º É vedada a indicação, para o Conselho de Administração:
I - de representante do órgão regulador;
II - de pessoa que atuou em partido político.
Art. 18. Sem prejuízo das competências previstas no art. 142 da Lei nº 6.404, de 15 de dezembro de 1976.
Art. 20. É vedada a participação remunerada de membros da administração pública em mais de 2 (dois) conselhos.
Art. 21. (VETADO).
"""
ESTATUTO = "Disposições iniciais. Art.21. A administração cabe ao Conselho. **Art. 22º** O Conselho é composto por sete membros. Art.23. Compete ao Conselho deliberar.\n"


def test_md_redline_valida_nos_dois_sentidos(tmp_path: Path) -> None:
    mod = load("md_redline")
    (tmp_path / "a.md").write_text(BASE, encoding="utf-8")
    (tmp_path / "b.md").write_text(ALVO, encoding="utf-8")
    out = tmp_path / "r.docx"
    stats = mod.gerar(tmp_path / "a.md", tmp_path / "b.md", out, "Nicholas", "2026-10-23T12:00:00Z")
    assert stats["ins"] == 1 and stats["par"] >= 1 and stats["revisoes"] > 0
    assert mod.validar(out, tmp_path / "a.md", tmp_path / "b.md") == {"aceitar_reproduz_alvo": True, "rejeitar_reproduz_base": True}
    import zipfile
    xml = zipfile.ZipFile(out).read("word/document.xml").decode()
    assert 'w:author="Nicholas"' in xml and "w:trackRevisions" in zipfile.ZipFile(out).read("word/settings.xml").decode()
    assert mod.main([str(tmp_path / "a.md"), str(tmp_path / "b.md"), str(tmp_path / "r2.docx"), "--autor", "Revisor", "--funde-iguais", "0"]) == 0


def test_extrair_adendo_artigo_integral_e_ausente(tmp_path: Path) -> None:
    mod = load("extrair_adendo")
    pm = load("parecer_md")
    fontes = tmp_path / "fontes"
    fontes.mkdir()
    (fontes / "l13303.txt").write_text(LEI, encoding="utf-8")
    (fontes / "estatuto.md").write_text(ESTATUTO, encoding="utf-8")
    mapa = {"Lei nº 13.303/2016": "l13303.txt", "Estatuto": "estatuto.md", "Decreto": "inexistente.txt"}
    doc = pm.parse(BASE + "\n5. Ver o art. 99 da Lei nº 13.303/2016 e o art. 4º do Decreto.\n")
    texto, resumo = mod.montar(doc, mapa, fontes)
    itens = {(i["normas"][0], i["artigo"]): i for i in resumo["itens"]}
    assert itens[("Lei nº 13.303/2016", "17")]["paragrafos"] == [2]
    assert {("Estatuto", "22"), ("Estatuto", "23"), ("Lei nº 13.303/2016", "20")} <= set(itens)
    assert "II - de pessoa que atuou em partido político." in texto  # artigo inteiro, com incisos
    assert "Art. 18" not in texto.split("### Art. 17")[1].split("###")[0]  # para no artigo seguinte
    assert "O Conselho é composto por sete membros." in texto and "Compete ao Conselho" not in texto.split("### Art. 22")[1].split("###")[0]
    assert not itens[("Lei nº 13.303/2016", "99")]["localizado"]
    assert not itens[("Decreto", "4")]["localizado"]
    assert "Citações não localizadas" in texto
    assert ("Lei nº 13.303/2016", "142") not in itens  # remissão a outra lei dentro da fonte não conta


def test_pacote_hash_e_diferencas(tmp_path: Path) -> None:
    mod = load("pacote_auditoria")
    (tmp_path / "a.md").write_text(BASE, encoding="utf-8")
    (tmp_path / "b.md").write_text(ALVO, encoding="utf-8")
    pac = mod.montar(tmp_path / "b.md", "Audite.")
    h = mod.hash_do_pacote(pac)
    assert h and f"HASH_RECEBIDO: {h}" in pac and "===== INÍCIO: MINUTA" in pac
    assert mod.verificar(f"HASH_RECEBIDO: {h}\nDecisão: aprovar", h)[0]
    assert not mod.verificar("Decisão: aprovar", h)[0]
    assert not mod.verificar("HASH_RECEBIDO: " + "0" * 64, h)[0]
    diff = mod.montar(tmp_path / "b.md", "Audite.", anterior=tmp_path / "a.md")
    corpo = diff.split("MINUTA — SÓ AS DIFERENÇAS")[1]
    assert "[1 — ALTERADO; era o 1]" in corpo and "[3 — NOVO]" in corpo
    assert "[4 — contexto, sem alteração]" in corpo and "[5 —" not in corpo
    assert "ÍNDICE DA VERSÃO INTEGRAL" in corpo and "[5] É o parecer, sob censura." in corpo
    sem_p2 = mod.montar(tmp_path / "a.md", "Audite.", anterior=tmp_path / "b.md")
    assert "SUPRIMIDO OU REESCRITO" in sem_p2 and "Parágrafo novo sobre a junta eleitoral" in sem_p2
    assert len(diff) < len(mod.montar(tmp_path / "b.md", "Audite.")) + 2000
