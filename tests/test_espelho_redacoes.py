from __future__ import annotations

import importlib.util
import json
import sys
import zipfile
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


MINUTA = """Art. 2º O representante será eleito por voto direto dos empregados ativos.

III. Prazos, locais e horários para:

a) Registro de candidaturas;

b) Votação;

| Etapa | Base | Responsável |
|---|---|---|
| Impugnação do Edital de Convocação | Art. 16, § 4º | ELEITOR |
| 1 a) | É empregado ativo da CODEMIG? | Sim / Não |
"""

ANEXO = """Classificação: correção necessária (NR)

Art. 2º O representante será eleito por voto direto dos empregados ativos. (NR)

III. Prazos, locais e horários para: a) Registro de candidaturas; b) Votação; (NR)

Linha "Impugnação do edital" (NR): Impugnação do Edital de Convocação. Regulamento: Art. 16, § 4º; Responsável: ELEITOR.

Item 1, a) (NR): É empregado ativo da CODEMIG? (Sim / Não)

[Edital – item a definir] Os dados pessoais serão tratados na forma da LGPD. (AC)

§ 9º Dispositivo que não está na minuta. (AC)
"""


def test_classifica_blocos_do_anexo(tmp_path: Path) -> None:
    mod = load("espelho_redacoes")
    (tmp_path / "minuta.md").write_text(MINUTA, encoding="utf-8")
    (tmp_path / "anexo.md").write_text(ANEXO, encoding="utf-8")
    r = mod.conferir(tmp_path / "anexo.md", tmp_path / "minuta.md")
    estados = [b["estado"] for b in r["blocos"]]
    assert estados == ["igual", "contido", "por_partes", "por_partes", "fora_da_minuta", "divergente"]
    assert r["ok"] is False


def test_redacao_superada_no_parecer(tmp_path: Path) -> None:
    mod = load("espelho_redacoes")
    (tmp_path / "minuta.md").write_text(MINUTA, encoding="utf-8")
    (tmp_path / "anexo.md").write_text(ANEXO.replace("§ 9º Dispositivo que não está na minuta. (AC)\n", ""), encoding="utf-8")
    antigo = "Art. 2º O representante dos empregados será eleito, excluindo os empregados com contrato suspenso, por voto direto."
    novo = "Art. 2º O representante dos empregados será eleito por voto direto, excluídos os empregados com contrato suspenso."
    (tmp_path / "parecer.md").write_text(f"10. O art. 2º diz: \"{antigo}\"\n", encoding="utf-8")
    (tmp_path / "mudancas.json").write_text(
        json.dumps([
            {"documento": "minuta", "alvo": "art2", "texto_atual": antigo, "texto_final": novo},
            {"documento": "parecer", "alvo": "10", "texto_atual": antigo, "texto_final": novo},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    r = mod.conferir(tmp_path / "anexo.md", tmp_path / "minuta.md", tmp_path / "parecer.md", tmp_path / "mudancas.json")
    assert [s["alvo"] for s in r["superadas_no_parecer"]] and {s["alvo"] for s in r["superadas_no_parecer"]} == {"art2"}
    assert r["ok"] is False
    assert mod.main(["--anexo", str(tmp_path / "anexo.md"), "--minuta", str(tmp_path / "minuta.md")]) == 0


def test_docx_usa_a_visao_com_alteracoes_aceitas(tmp_path: Path) -> None:
    mod = load("espelho_redacoes")
    w = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    doc = (
        f'<w:document {w}><w:body>'
        '<w:p><w:r><w:t xml:space="preserve">Art. 5º A Junta </w:t></w:r>'
        '<w:del w:id="1" w:author="X"><w:r><w:delText>decidirá</w:delText></w:r></w:del>'
        '<w:ins w:id="2" w:author="X"><w:r><w:t>publicará</w:t></w:r></w:ins>'
        '<w:r><w:t xml:space="preserve"> o resultado.</w:t></w:r></w:p>'
        '<w:tbl><w:tr><w:tc><w:p><w:r><w:t>Etapa</w:t></w:r></w:p></w:tc>'
        '<w:tc><w:p><w:r><w:t>JUNTA</w:t></w:r></w:p></w:tc></w:tr></w:tbl>'
        '</w:body></w:document>'
    )
    path = tmp_path / "minuta.docx"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", doc)
    unidades = mod.ler(path)
    assert "Art. 5º A Junta publicará o resultado." in unidades
    assert "Etapa || JUNTA" in unidades and "JUNTA" in unidades
