#!/usr/bin/env python3
"""Confere a integridade de um comparativo DOCX com alterações controladas.

Uso::

    integridade_docx.py --base BASE.docx --limpa LIMPA.docx --redline REDLINE.docx \
        [--divididos N] [--fundidos N] [--json SAIDA.json]

O comparativo (redline) é resolvido de forma determinística, sem Word:

* **aceitar** remove ``w:del``/``w:moveFrom``, desembrulha ``w:ins``/``w:moveTo``
  e une ao parágrafo seguinte todo parágrafo cuja marca de parágrafo está
  excluída (``<w:pPr><w:rPr><w:del .../></w:rPr></w:pPr>``);
* **rejeitar** faz o inverso: remove inserções, restaura ``w:delText`` e une ao
  seguinte o parágrafo cuja marca de parágrafo está inserida (é assim que uma
  DIVISÃO de parágrafo aparece no redline).

Verificações (todas sobre o texto visível, parágrafo a parágrafo):

1. aceitar todas as marcas reproduz exatamente os parágrafos da versão limpa;
2. rejeitar todas reproduz exatamente os parágrafos da base;
3. contagem esperada de parágrafos da limpa = base + divididos − fundidos
   (somente quando ``--divididos``/``--fundidos`` forem informados);
4. seção "Referências" (parágrafos após o último título iniciado por
   "Referências", até o próximo título): mesmo número de entradas e mesmo hash
   entre base, aceitar e rejeitar — salvo se base e limpa também diferirem,
   caso em que aceitar deve bater com a limpa e rejeitar com a base;
5. notas de rodapé e de fim (``word/footnotes.xml``/``endnotes.xml``):
   contagem e textos das notas referenciadas coerentes entre aceitar e limpa
   e entre rejeitar e base;
6. havendo diferença entre base e limpa, o redline precisa ter marcas.

Em caso de divergência, aponta o PRIMEIRO parágrafo divergente (índice físico,
contando do zero, e trecho de 80 caracteres de cada lado) e um resumo do
desalinhamento (por exemplo, "3 parágrafo(s) ausente(s) a partir do índice 226").

Código de saída: 0 íntegro; 1 divergência; 2 erro de uso ou de leitura.

Funções reutilizáveis: ``ler(path)``, ``aceitar(path)``, ``rejeitar(path)`` e
``conferir(base, limpa, redline, divididos=None, fundidos=None)``.
"""

from __future__ import annotations

import argparse
import dataclasses
import difflib
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{W_NS}}}"
MARCA_NOTA = "[nota]"
MARCA_NOTA_FIM = "[nota de fim]"
TRECHO = 80

_PULAR_SEMPRE = {
    "pPr",
    "rPr",
    "sectPr",
    "tblPr",
    "trPr",
    "tcPr",
    "tblGrid",
    "txbxContent",
    "Fallback",
    "instrText",
    "delInstrText",
    "rPrChange",
    "pPrChange",
    "sdtPr",
    "sdtEndPr",
    "fldData",
}
_PULAR = {"aceitar": {"del", "moveFrom"}, "rejeitar": {"ins", "moveTo"}}
_ESTILO_TITULO = re.compile(r"(?i)^(heading|t\w*tulo|title)")
_REFERENCIAS = re.compile(r"(?i)^\s*refer[eê]ncias\b")


class IntegridadeErro(RuntimeError):
    """Erro de leitura ou de uso."""


@dataclasses.dataclass
class Documento:
    """Texto visível resolvido de um DOCX."""

    caminho: str
    modo: str
    paragrafos: list[str]
    estilos: list[str]
    notas: list[str]
    notas_fim: list[str]
    marcas: int
    avisos: list[str]

    @property
    def textos(self) -> list[str]:
        return self.paragrafos


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _ler_parte(arquivo: zipfile.ZipFile, nome: str) -> ET.Element | None:
    if nome not in arquivo.namelist():
        return None
    return ET.fromstring(arquivo.read(nome))


def _marca_paragrafo(paragrafo: ET.Element) -> str | None:
    ppr = paragrafo.find(f"{W}pPr")
    if ppr is None:
        return None
    rpr = ppr.find(f"{W}rPr")
    if rpr is None:
        return None
    for filho in rpr:
        nome = _local(filho.tag)
        if nome in {"ins", "moveTo"}:
            return "ins"
        if nome in {"del", "moveFrom"}:
            return "del"
    return None


def _estilo(paragrafo: ET.Element) -> str:
    estilo = paragrafo.find(f"{W}pPr/{W}pStyle")
    return estilo.get(f"{W}val", "") if estilo is not None else ""


def _texto(elemento: ET.Element, modo: str, refs: list[tuple[str, str]]) -> str:
    partes: list[str] = []
    pular = _PULAR[modo]

    def visitar(no: ET.Element) -> None:
        for filho in no:
            nome = _local(filho.tag)
            if nome in _PULAR_SEMPRE or nome in pular:
                continue
            if nome == "t":
                partes.append(filho.text or "")
            elif nome == "delText":
                if modo == "rejeitar":
                    partes.append(filho.text or "")
            elif nome == "tab":
                partes.append("\t")
            elif nome in {"br", "cr"}:
                partes.append("\n")
            elif nome == "noBreakHyphen":
                partes.append("\u2011")
            elif nome == "softHyphen":
                partes.append("\u00ad")
            elif nome == "footnoteReference":
                partes.append(MARCA_NOTA)
                refs.append(("footnote", filho.get(f"{W}id", "")))
            elif nome == "endnoteReference":
                partes.append(MARCA_NOTA_FIM)
                refs.append(("endnote", filho.get(f"{W}id", "")))
            else:
                visitar(filho)

    visitar(elemento)
    return "".join(partes)


def _linha_pulada(linha: ET.Element, modo: str) -> bool:
    trpr = linha.find(f"{W}trPr")
    if trpr is None:
        return False
    nomes = {_local(filho.tag) for filho in trpr}
    return (modo == "aceitar" and "del" in nomes) or (modo == "rejeitar" and "ins" in nomes)


def _blocos(
    container: ET.Element,
    modo: str,
    saida: list[tuple[str, str]],
    refs: list[tuple[str, str]],
    avisos: list[str],
) -> None:
    """Resolve os blocos de um contêiner (corpo, célula, nota) em parágrafos."""

    pendente: str | None = None

    def descarregar() -> None:
        nonlocal pendente
        if pendente:
            saida.append((pendente, ""))
            avisos.append(
                "parágrafo com marca de união sem parágrafo seguinte no mesmo contêiner: "
                + pendente[:60]
            )
        pendente = None

    for filho in container:
        nome = _local(filho.tag)
        if nome == "p":
            texto = _texto(filho, modo, refs)
            if pendente is not None:
                texto = pendente + texto
                pendente = None
            marca = _marca_paragrafo(filho)
            une = (modo == "aceitar" and marca == "del") or (modo == "rejeitar" and marca == "ins")
            if une:
                pendente = texto
            else:
                saida.append((texto, _estilo(filho)))
        elif nome == "tbl":
            descarregar()
            for linha in filho:
                if _local(linha.tag) != "tr" or _linha_pulada(linha, modo):
                    continue
                for celula in linha:
                    if _local(celula.tag) == "tc":
                        _blocos(celula, modo, saida, refs, avisos)
        elif nome == "sdt":
            conteudo = filho.find(f"{W}sdtContent")
            if conteudo is not None:
                _blocos(conteudo, modo, saida, refs, avisos)
        elif nome in {"customXml", "ins", "moveTo", "del", "moveFrom"}:
            if nome in _PULAR[modo]:
                continue
            _blocos(filho, modo, saida, refs, avisos)
    descarregar()


def _notas(raiz: ET.Element | None, tipo: str) -> dict[str, ET.Element]:
    if raiz is None:
        return {}
    return {
        no.get(f"{W}id", ""): no
        for no in raiz
        if _local(no.tag) == tipo
    }


def _ler(path: Path | str, modo: str) -> Documento:
    caminho = Path(path)
    if not caminho.is_file():
        raise IntegridadeErro(f"arquivo não encontrado: {caminho}")
    try:
        with zipfile.ZipFile(caminho) as arquivo:
            documento = _ler_parte(arquivo, "word/document.xml")
            rodape = _ler_parte(arquivo, "word/footnotes.xml")
            fim = _ler_parte(arquivo, "word/endnotes.xml")
    except zipfile.BadZipFile as exc:
        raise IntegridadeErro(f"DOCX inválido: {caminho}") from exc
    except ET.ParseError as exc:
        raise IntegridadeErro(f"XML inválido em {caminho}: {exc}") from exc
    if documento is None:
        raise IntegridadeErro(f"pacote sem word/document.xml: {caminho}")
    corpo = documento.find(f"{W}body")
    if corpo is None:
        raise IntegridadeErro(f"documento sem w:body: {caminho}")

    marcas = 0
    for raiz in (documento, rodape, fim):
        if raiz is None:
            continue
        for no in raiz.iter():
            nome = _local(no.tag)
            if nome in {"ins", "del", "moveFrom", "moveTo"} or nome.endswith("PrChange"):
                marcas += 1

    avisos: list[str] = []
    refs: list[tuple[str, str]] = []
    saida: list[tuple[str, str]] = []
    _blocos(corpo, modo, saida, refs, avisos)

    tabela = {"footnote": _notas(rodape, "footnote"), "endnote": _notas(fim, "endnote")}
    textos_notas: dict[str, list[str]] = {"footnote": [], "endnote": []}
    for tipo, ident in refs:
        no = tabela[tipo].get(ident)
        if no is None:
            textos_notas[tipo].append(f"<nota ausente id={ident}>")
            avisos.append(f"referência a {tipo} inexistente: id={ident}")
            continue
        paragrafos: list[tuple[str, str]] = []
        _blocos(no, modo, paragrafos, [], avisos)
        textos_notas[tipo].append("\n".join(texto for texto, _ in paragrafos))

    return Documento(
        caminho=str(caminho),
        modo=modo,
        paragrafos=[texto for texto, _ in saida],
        estilos=[estilo for _, estilo in saida],
        notas=textos_notas["footnote"],
        notas_fim=textos_notas["endnote"],
        marcas=marcas,
        avisos=avisos,
    )


def aceitar(path: Path | str) -> Documento:
    """Texto visível do DOCX com todas as alterações aceitas."""

    return _ler(path, "aceitar")


def rejeitar(path: Path | str) -> Documento:
    """Texto visível do DOCX com todas as alterações rejeitadas."""

    return _ler(path, "rejeitar")


def ler(path: Path | str) -> Documento:
    """Lê um DOCX limpo (equivale a aceitar; marcas residuais geram aviso)."""

    documento = _ler(path, "aceitar")
    if documento.marcas:
        documento.avisos.append(f"documento supostamente limpo contém {documento.marcas} marca(s) de revisão")
    return documento


# --------------------------------------------------------------------------- verificações


def _hash(textos: list[str]) -> str:
    return hashlib.sha256("\n".join(textos).encode("utf-8")).hexdigest()


def referencias(documento: Documento) -> list[str] | None:
    """Entradas não vazias após o último título iniciado por "Referências"."""

    inicio = None
    for indice, (texto, estilo) in enumerate(zip(documento.paragrafos, documento.estilos)):
        if _REFERENCIAS.match(texto) and (_ESTILO_TITULO.match(estilo) or len(texto.strip()) <= 100):
            inicio = indice
    if inicio is None:
        return None
    entradas: list[str] = []
    for texto, estilo in zip(documento.paragrafos[inicio + 1 :], documento.estilos[inicio + 1 :]):
        if _ESTILO_TITULO.match(estilo):
            break
        if texto.strip():
            entradas.append(texto)
    return entradas


def _trecho(texto: str | None, inicio: int) -> str:
    if texto is None:
        return "(ausente)"
    return texto[inicio : inicio + TRECHO]


def _resumo_alinhamento(esperado: list[str], obtido: list[str]) -> str:
    partes: list[str] = []
    matcher = difflib.SequenceMatcher(None, esperado, obtido, autojunk=False)
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == "equal":
            continue
        if op == "delete":
            partes.append(f"{i2 - i1} parágrafo(s) esperado(s) ausente(s) a partir do índice {i1}")
        elif op == "insert":
            partes.append(f"{j2 - j1} parágrafo(s) a mais no obtido a partir do índice {j1}")
        else:
            partes.append(f"esperado[{i1}:{i2}] ≠ obtido[{j1}:{j2}]")
        if len(partes) >= 5:
            partes.append("…")
            break
    return "; ".join(partes)


def primeira_divergencia(esperado: list[str], obtido: list[str]) -> dict[str, object] | None:
    """Primeiro índice em que as listas divergem, com 80 caracteres de cada lado."""

    for indice in range(max(len(esperado), len(obtido))):
        a = esperado[indice] if indice < len(esperado) else None
        b = obtido[indice] if indice < len(obtido) else None
        if a == b:
            continue
        caractere = 0
        if a is not None and b is not None:
            while caractere < min(len(a), len(b)) and a[caractere] == b[caractere]:
                caractere += 1
        inicio = max(0, caractere - 20)
        return {
            "indice": indice,
            "paragrafo": indice + 1,
            "caractere": caractere,
            "esperado": _trecho(a, inicio),
            "obtido": _trecho(b, inicio),
            "resumo": _resumo_alinhamento(esperado, obtido),
        }
    return None


def _check(nome: str, descricao: str, ok: bool, **extra: object) -> dict[str, object]:
    return {"nome": nome, "descricao": descricao, "ok": ok, **extra}


def conferir(
    base: Path | str,
    limpa: Path | str,
    redline: Path | str,
    divididos: int | None = None,
    fundidos: int | None = None,
) -> dict[str, object]:
    """Executa todas as verificações e devolve um dicionário serializável.

    Chave ``ok`` indica o resultado global; ``verificacoes`` traz cada teste;
    ``primeira_divergencia`` aponta o primeiro parágrafo divergente.
    """

    doc_base = ler(base)
    doc_limpa = ler(limpa)
    doc_aceito = aceitar(redline)
    doc_rejeitado = rejeitar(redline)
    verificacoes: list[dict[str, object]] = []
    avisos: list[str] = []
    for rotulo, doc in (("base", doc_base), ("limpa", doc_limpa), ("aceitar", doc_aceito), ("rejeitar", doc_rejeitado)):
        avisos.extend(f"{rotulo}: {aviso}" for aviso in doc.avisos)

    div_aceitar = primeira_divergencia(doc_limpa.paragrafos, doc_aceito.paragrafos)
    verificacoes.append(
        _check(
            "aceitar_reproduz_limpa",
            "aceitar todas as marcas reproduz os parágrafos da limpa",
            div_aceitar is None,
            divergencia=div_aceitar,
        )
    )
    div_rejeitar = primeira_divergencia(doc_base.paragrafos, doc_rejeitado.paragrafos)
    verificacoes.append(
        _check(
            "rejeitar_reproduz_base",
            "rejeitar todas as marcas reproduz os parágrafos da base",
            div_rejeitar is None,
            divergencia=div_rejeitar,
        )
    )

    if divididos is not None or fundidos is not None:
        esperado = len(doc_base.paragrafos) + (divididos or 0) - (fundidos or 0)
        verificacoes.append(
            _check(
                "contagem_paragrafos",
                f"limpa tem base ({len(doc_base.paragrafos)}) + divididos ({divididos or 0}) "
                f"− fundidos ({fundidos or 0}) = {esperado} parágrafos",
                len(doc_limpa.paragrafos) == esperado and len(doc_aceito.paragrafos) == esperado,
                esperado=esperado,
                limpa=len(doc_limpa.paragrafos),
                aceitar=len(doc_aceito.paragrafos),
            )
        )

    ref_base, ref_limpa = referencias(doc_base), referencias(doc_limpa)
    ref_aceito, ref_rejeitado = referencias(doc_aceito), referencias(doc_rejeitado)
    if ref_base is None and ref_limpa is None:
        verificacoes.append(
            _check("referencias", "seção Referências (não encontrada; não se aplica)", True, aplicavel=False)
        )
    else:
        def resumo(ref: list[str] | None) -> dict[str, object]:
            return {"entradas": None if ref is None else len(ref), "sha256": None if ref is None else _hash(ref)}

        alteradas = ref_base != ref_limpa
        if alteradas:
            avisos.append(
                "a seção Referências difere entre base e limpa "
                f"({resumo(ref_base)['entradas']} → {resumo(ref_limpa)['entradas']} entradas); "
                "confira se a alteração é intencional"
            )
        ok = ref_aceito == ref_limpa and ref_rejeitado == ref_base
        detalhe: dict[str, object] = {
            "base": resumo(ref_base),
            "limpa": resumo(ref_limpa),
            "aceitar": resumo(ref_aceito),
            "rejeitar": resumo(ref_rejeitado),
            "alteradas_entre_base_e_limpa": alteradas,
        }
        if ref_aceito != ref_limpa:
            detalhe["divergencia"] = primeira_divergencia(ref_limpa or [], ref_aceito or [])
        elif ref_rejeitado != ref_base:
            detalhe["divergencia"] = primeira_divergencia(ref_base or [], ref_rejeitado or [])
        verificacoes.append(
            _check("referencias", "seção Referências: mesmas entradas e hash", ok, **detalhe)
        )

    notas_limpa = doc_limpa.notas + doc_limpa.notas_fim
    notas_base = doc_base.notas + doc_base.notas_fim
    notas_aceito = doc_aceito.notas + doc_aceito.notas_fim
    notas_rejeitado = doc_rejeitado.notas + doc_rejeitado.notas_fim
    verificacoes.append(
        _check(
            "notas_aceitar",
            f"notas referenciadas ao aceitar ({len(notas_aceito)}) = limpa ({len(notas_limpa)})",
            notas_aceito == notas_limpa,
            divergencia=primeira_divergencia(notas_limpa, notas_aceito),
        )
    )
    verificacoes.append(
        _check(
            "notas_rejeitar",
            f"notas referenciadas ao rejeitar ({len(notas_rejeitado)}) = base ({len(notas_base)})",
            notas_rejeitado == notas_base,
            divergencia=primeira_divergencia(notas_base, notas_rejeitado),
        )
    )

    mudou = doc_base.paragrafos != doc_limpa.paragrafos or notas_base != notas_limpa
    verificacoes.append(
        _check(
            "marcas_presentes",
            f"redline tem {doc_aceito.marcas} marca(s); base e limpa {'diferem' if mudou else 'são iguais'}",
            doc_aceito.marcas > 0 or not mudou,
        )
    )

    ok = all(item["ok"] for item in verificacoes)
    primeira = None
    for item in verificacoes:
        if not item["ok"] and item.get("divergencia"):
            primeira = {"verificacao": item["nome"], **item["divergencia"]}  # type: ignore[arg-type]
            break
    return {
        "contrato": "integridade_docx_v1",
        "ok": ok,
        "arquivos": {"base": str(base), "limpa": str(limpa), "redline": str(redline)},
        "contagens": {
            "base": len(doc_base.paragrafos),
            "limpa": len(doc_limpa.paragrafos),
            "aceitar": len(doc_aceito.paragrafos),
            "rejeitar": len(doc_rejeitado.paragrafos),
            "notas_base": len(notas_base),
            "notas_limpa": len(notas_limpa),
            "marcas_redline": doc_aceito.marcas,
        },
        "verificacoes": verificacoes,
        "primeira_divergencia": primeira,
        "avisos": avisos,
    }


def formatar(resultado: dict[str, object]) -> str:
    """Resumo legível do resultado de :func:`conferir`."""

    verificacoes = resultado["verificacoes"]  # type: ignore[assignment]
    falhas = [item for item in verificacoes if not item["ok"]]  # type: ignore[union-attr]
    contagens = resultado["contagens"]
    linhas = [
        f"integridade_docx: {'OK' if resultado['ok'] else 'DIVERGÊNCIA'} "
        f"({len(verificacoes) - len(falhas)}/{len(verificacoes)} verificações)",  # type: ignore[arg-type]
        "parágrafos: base {base}, limpa {limpa}, aceitar {aceitar}, rejeitar {rejeitar}; "
        "notas: base {notas_base}, limpa {notas_limpa}; marcas no redline: {marcas_redline}".format(**contagens),  # type: ignore[arg-type]
    ]
    for item in verificacoes:  # type: ignore[union-attr]
        linhas.append(f"  [{'ok' if item['ok'] else 'FALHA'}] {item['descricao']}")
        divergencia = item.get("divergencia")
        if not item["ok"] and divergencia:
            linhas.append(
                f"      primeiro divergente: parágrafo #{divergencia['paragrafo']} "
                f"(índice {divergencia['indice']}), caractere {divergencia['caractere']}"
            )
            linhas.append(f"      esperado: «{divergencia['esperado']}»")
            linhas.append(f"      obtido:   «{divergencia['obtido']}»")
            if divergencia.get("resumo"):
                linhas.append(f"      alinhamento: {divergencia['resumo']}")
    for aviso in resultado.get("avisos", []):  # type: ignore[union-attr]
        linhas.append(f"  aviso: {aviso}")
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--base", required=True, help="versão aprovada usada como base do redline")
    parser.add_argument("--limpa", required=True, help="versão limpa corrente (canônica)")
    parser.add_argument("--redline", required=True, help="DOCX com alterações controladas")
    parser.add_argument("--divididos", type=int, help="nº de parágrafos acrescidos por divisão")
    parser.add_argument("--fundidos", type=int, help="nº de parágrafos absorvidos por fusão")
    parser.add_argument("--json", help="grava o resultado completo em JSON")
    args = parser.parse_args(argv)
    try:
        resultado = conferir(args.base, args.limpa, args.redline, args.divididos, args.fundidos)
    except IntegridadeErro as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2
    print(formatar(resultado))
    if args.json:
        Path(args.json).write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if resultado["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
