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
      'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
      'xmlns:w15="http://schemas.microsoft.com/office/word/2012/wordml"')


def load(name: str):
    sys.path.insert(0, str(SCRIPTS))
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def r(texto: str) -> str:
    return f'<w:r><w:t xml:space="preserve">{escape(texto)}</w:t></w:r>'


def par(*conteudo: str, num: str | None = "1") -> str:
    ppr = f'<w:pPr><w:numPr><w:ilvl w:val="0"/><w:numId w:val="{num}"/></w:numPr></w:pPr>' if num else ""
    return f"<w:p>{ppr}{''.join(conteudo)}</w:p>"


def ref(cid: str) -> str:
    return f'<w:r><w:commentReference w:id="{cid}"/></w:r>'


def comentario(cid: str, autor: str, texto: str, para_id: str) -> str:
    return (f'<w:comment w:id="{cid}" w:author="{autor}" w:date="2026-11-0{int(cid) + 1}T10:00:00Z">'
            f'<w:p w14:paraId="{para_id}">{r(texto)}</w:p></w:comment>')


def gravar_docx(path: Path, corpo: list[str], comentarios: list[str] = (), extendidos: list[str] = ()) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", f"<w:document {NS}><w:body>{''.join(corpo)}</w:body></w:document>")
        if comentarios:
            z.writestr("word/comments.xml", f"<w:comments {NS}>{''.join(comentarios)}</w:comments>")
        if extendidos:
            z.writestr("word/commentsExtended.xml", f"<w15:commentsEx {NS}>{''.join(extendidos)}</w15:commentsEx>")
    return path


def docx_com_resposta(path: Path) -> Path:
    """Dois comentários no mesmo trecho (o 1 responde ao 0), com inserção e exclusão no trecho ancorado."""
    corpo = [
        par(r("Primeiro parágrafo do parecer.")),
        par('<w:commentRangeStart w:id="0"/><w:commentRangeStart w:id="1"/>', r("O prazo é de "),
            '<w:del w:id="10" w:author="Autor"><w:r><w:delText>dez</w:delText></w:r></w:del>',
            '<w:ins w:id="11" w:author="Autor">' + r("cinco") + "</w:ins>",
            r(" dias úteis."), '<w:commentRangeEnd w:id="0"/><w:commentRangeEnd w:id="1"/>', ref("0"), ref("1"),
            r(" Fora do trecho.")),
        par(r("Conclusão"), ref("2"), num=None),
        par(r("Parágrafo com numeração removida."), num="0"),
        par('<w:del w:id="12" w:author="Autor"><w:r><w:t>todo excluído</w:t></w:r></w:del>'),
        par(r("Terceiro parágrafo numerado.")),
    ]
    coms = [
        comentario("0", "Revisor", "Conferir o prazo; ver parágrafo 9 e item 99.", "AAA1"),
        comentario("1", "Autor", "Ajustado para cinco dias.", "AAA2"),
        comentario("2", "Revisor", "Título sem número?", "AAA3"),
    ]
    ext = [
        '<w15:commentEx w15:paraId="AAA1" w15:done="0"/>',
        '<w15:commentEx w15:paraId="AAA2" w15:paraIdParent="AAA1" w15:done="1"/>',
        '<w15:commentEx w15:paraId="AAA3" w15:done="0"/>',
    ]
    return gravar_docx(path, corpo, coms, ext)


def test_paragrafos_numerados_como_o_word(tmp_path: Path) -> None:
    ec = load("exportar_comentarios")
    pars = ec.ler_paragrafos(docx_com_resposta(tmp_path / "m.docx"))
    numeros = [(p["numero"], p["texto"][:20]) for p in pars]
    assert [n for n, _ in numeros] == [1, 2, None, None, None, 3]  # numId 0 e parágrafo todo excluído não contam
    assert pars[1]["texto"] == "O prazo é de cinco dias úteis. Fora do trecho."


def test_comentarios_com_trecho_resposta_e_paragrafo(tmp_path: Path) -> None:
    ec = load("exportar_comentarios")
    cs = {c["id"]: c for c in ec.ler_comentarios(docx_com_resposta(tmp_path / "m.docx"))}
    assert cs["0"]["trecho"] == "O prazo é de cinco dias úteis."  # inserção entra, exclusão sai, fim do intervalo respeitado
    assert cs["0"]["paragrafos"] == [2] and cs["0"]["autor"] == "Revisor" and cs["0"]["responde_a"] == ""
    assert cs["1"]["responde_a"] == "0" and cs["1"]["resolvido"] is True and cs["1"]["trecho"] == cs["0"]["trecho"]
    assert cs["2"]["trecho"] == "Conclusão" and cs["2"]["paragrafos"] == [] and cs["2"]["depois_do_paragrafo"] == 2
    assert cs["0"]["data"] == "2026-11-01T10:00:00Z"


def test_trecho_em_varios_paragrafos(tmp_path: Path) -> None:
    ec = load("exportar_comentarios")
    corpo = [par('<w:commentRangeStart w:id="5"/>', r("Início do trecho.")),
             par(r("Fim do trecho."), '<w:commentRangeEnd w:id="5"/>', ref("5"), r(" Resto."))]
    path = gravar_docx(tmp_path / "v.docx", corpo, [comentario("5", "X", "Unir?", "B1")])
    c = ec.ler_comentarios(path)[0]
    assert c["trecho"] == "Início do trecho. ¶ Fim do trecho." and c["paragrafos"] == [1, 2] and c["responde_a"] == ""


def test_cli_texto_json_e_filtro_de_autor(tmp_path: Path, capsys) -> None:
    ec = load("exportar_comentarios")
    path = docx_com_resposta(tmp_path / "m.docx")
    assert ec.main([str(path), "--saida", str(tmp_path / "c.txt"), "--json", str(tmp_path / "c.json"), "--autor", "revisor"]) == 0
    texto = (tmp_path / "c.txt").read_text(encoding="utf-8")
    assert "[0] Revisor" in texto and "Trecho: «O prazo é de cinco dias úteis.»" in texto and "Onde: § 2" in texto
    assert "[1] Autor" not in texto and "depois do § 2" in texto
    dados = json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))
    assert [c["id"] for c in dados["comentarios"]] == ["0", "2"]
    assert ec.main([str(path)]) == 0
    assert "responde ao [0]" in capsys.readouterr().out
    assert ec.main([str(tmp_path / "nao_existe.docx")]) == 2
    sem = gravar_docx(tmp_path / "sem.docx", [par(r("Sem comentários."))])
    assert ec.ler_comentarios(sem) == []
