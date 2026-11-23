#!/usr/bin/env python3
"""Acusa afirmações já refutadas que reaparecem numa minuta (ou em qualquer texto do caso).

Em reescritas sucessivas, um erro de fato corrigido numa rodada volta na seguinte
("66%/34%" na adjudicação, a compradora errada num ano, "reuniu em si o
senhorio", "mera omissão material"). O caso guarda um registro das afirmações
refutadas, com o porquê, a forma correta e a fonte; este script procura cada uma
nos textos e acusa linha e trecho.

Formato do registro (``refutadas.json``; há um modelo vazio em
``refutadas_modelo.json`` nesta pasta)::

    {
      "caso": "Lotes 01 e 10 — quadra 04",
      "refutadas": [
        {
          "id": "R1",
          "padrao": "66\\\\s*%\\\\s*/\\\\s*34\\\\s*%",
          "regex": true,
          "por_que": "66%/34% é a divisão do preço da venda de 1986, não a da adjudicação de 1982",
          "correto": "cerca de 64,73% e 35,27%, pela proporção dos créditos adjudicados",
          "fonte": "SEI 100000001, pp. 100–106"
        },
        {
          "id": "R2",
          "padrao": "delta[^.]{0,80}\\\\b1986\\\\b|\\\\b1986\\\\b[^.]{0,80}delta",
          "regex": true,
          "ignorar_se": "nao adquiriu|diversamente do que",
          "por_que": "a Delta só entra na cadeia dominial em 2001 (R-11)",
          "correto": "em 1986 a venda foi à Alfa",
          "fonte": "SEI 100000002, p. 486"
        },
        {
          "id": "R3",
          "padrao": "reuniu em si o senhorio",
          "regex": false,
          "por_que": "a consolidação não está provada",
          "correto": "pode ter reunido, a depender da prova do domínio direto",
          "fonte": "SEI 100000002, p. 486"
        }
      ]
    }

``ignorar_se`` (opcional, regex sobre o texto normalizado) descarta o acerto quando a
mesma frase traz a forma correta ou a negação ("não adquiriu", "diversamente do que").

Normalização: acentos, caixa e espaços são ignorados nos dois lados (``senhório`` acha
``senhorio``; ``Mera  Omissão`` acha ``mera omissão``). Padrão de texto (``"regex":
false``) casa por palavra inteira, com espaço flexível em volta de ``/``, ``%`` e
pontuação; padrão ``regex`` usa a sintaxe do módulo ``re`` do Python (sem
diferença de caixa) e é aplicado ao texto já normalizado — escreva-o sem acento.

Textos: ``.md``/``.txt`` (linha a linha) e ``.docx`` (parágrafos, na visão com
alterações aceitas, e notas de rodapé; o local traz o índice do parágrafo e, quando
houver, o número da contagem de ``exportar_comentarios``).

Uso::

    checar_refutadas.py --refutadas refutadas.json parecer_v17.md anexo.docx [--json acertos.json]

Código de saída: 1 quando há acerto, 0 quando não há e 2 em erro de uso ou de leitura.
``pre_auditoria_parecer.py --refutadas`` usa ``checar_linhas`` e transforma cada acerto
em bloqueante.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

CAMPOS = ("id", "padrao")
ESPACOS = "       "


@dataclass
class Acerto:
    arquivo: str
    linha: int
    id: str
    trecho: str
    por_que: str = ""
    correto: str = ""
    fonte: str = ""
    local: str = ""


def normalizar_com_indices(texto: str) -> tuple[str, list[int]]:
    """Texto sem acentos, em minúsculas, com espaços colapsados, e o índice original de cada caractere."""
    chars: list[str] = []
    idx: list[int] = []
    for i, c in enumerate(texto):
        if c in ESPACOS or c.isspace():
            if chars and chars[-1] == " ":
                continue
            chars.append(" ")
            idx.append(i)
            continue
        c = {"“": '"', "”": '"', "‘": "'", "’": "'", "—": "-", "–": "-", "‐": "-", "‑": "-"}.get(c, c)
        for d in unicodedata.normalize("NFKD", c):
            if unicodedata.combining(d):
                continue
            chars.append(d.lower())
            idx.append(i)
    return "".join(chars), idx


def normalizar(texto: str) -> str:
    return normalizar_com_indices(texto)[0].strip()


def _regex_de_texto(padrao: str) -> str:
    """Padrão literal -> regex: espaço flexível, e opcional em volta de pontuação; palavra inteira nas pontas."""
    p = normalizar(padrao)
    partes = []
    for tok in re.findall(r"\s+|[^\w\s]|\w+", p):
        if tok.isspace():
            partes.append(r"\s+")
        elif re.fullmatch(r"\w+", tok):
            partes.append(re.escape(tok))
        else:
            partes.append(r"\s*" + re.escape(tok) + r"\s*")
    rx = "".join(partes)
    anterior = None
    while anterior != rx:  # espaço literal ao lado de pontuação vira opcional
        anterior = rx
        rx = rx.replace(r"\s+\s*", r"\s*").replace(r"\s*\s+", r"\s*").replace(r"\s*\s*", r"\s*")
    rx = rx.removeprefix(r"\s*").removesuffix(r"\s*")
    if p[:1].isalnum():
        rx = r"(?<!\w)" + rx
    if p[-1:].isalnum():
        rx += r"(?!\w)"
    return rx


def carregar(path: Path | str) -> dict:
    """Lê e valida o registro; compila os padrões (``_rx`` em cada item)."""
    dados = json.loads(Path(path).read_text(encoding="utf-8"))
    return preparar(dados)


def preparar(dados: dict) -> dict:
    """Valida e compila. Item com ``padrao`` vazio (o do modelo) é ignorado."""
    if not isinstance(dados, dict) or not isinstance(dados.get("refutadas"), list):
        raise ValueError('registro de refutadas: esperado {"caso": ..., "refutadas": [...]}')
    dados["refutadas"] = [r for r in dados["refutadas"] if not (isinstance(r, dict) and not str(r.get("padrao", "")).strip())]
    for i, r in enumerate(dados["refutadas"]):
        if not isinstance(r, dict) or any(not r.get(c) for c in CAMPOS):
            raise ValueError(f"refutada {i + 1}: campos obrigatórios {', '.join(CAMPOS)}")
        try:
            fonte_rx = normalizar(r["padrao"]) if r.get("regex") else _regex_de_texto(r["padrao"])
            r["_rx"] = re.compile(fonte_rx, re.IGNORECASE)
            r["_ignorar"] = re.compile(normalizar(r["ignorar_se"]), re.IGNORECASE) if r.get("ignorar_se") else None
        except re.error as e:
            raise ValueError(f"refutada {r['id']}: regex inválida ({e})") from e
    dados["_preparado"] = True
    return dados


def _frase(texto: str, ini: int, fim: int) -> str:
    """A frase (entre pontos finais ou ponto e vírgula) que contém o trecho."""
    a = max(texto.rfind(".", 0, ini), texto.rfind(";", 0, ini)) + 1
    b = min([x for x in (texto.find(".", fim), texto.find(";", fim)) if x != -1] or [len(texto)])
    return texto[a:b]


def checar_linhas(refutadas: dict, linhas: list[tuple[int, str]], arquivo: str,
                  locais: dict[int, str] | None = None) -> list[Acerto]:
    """Procura cada refutada em cada linha; ``linhas`` = [(número da linha, texto)]."""
    if not refutadas.get("_preparado"):
        preparar(refutadas)
    out = []
    for n, texto in linhas:
        norm, idx = normalizar_com_indices(texto)
        for r in refutadas["refutadas"]:
            for m in r["_rx"].finditer(norm):
                if m.end() <= m.start():
                    continue
                if r.get("_ignorar") is not None and r["_ignorar"].search(_frase(norm, m.start(), m.end())):
                    continue
                ini, fim = idx[m.start()], idx[m.end() - 1] + 1
                antes = texto[max(0, ini - 50):ini]
                depois = texto[fim:fim + 50]
                trecho = ("…" if ini > 50 else "") + antes + "[" + texto[ini:fim] + "]" + depois + ("…" if fim + 50 < len(texto) else "")
                out.append(Acerto(arquivo, n, r["id"], " ".join(trecho.split()), r.get("por_que", ""),
                                  r.get("correto", ""), r.get("fonte", ""), (locais or {}).get(n, f"linha {n}")))
    return out


def ler_linhas(path: Path) -> tuple[list[tuple[int, str]], dict[int, str]]:
    """Linhas de .md/.txt ou parágrafos de .docx (índice 1-based e rótulo com o § numerado)."""
    if path.suffix.lower() == ".docx":
        import exportar_comentarios as ec

        import docx_para_md

        linhas, locais = [], {}
        i = 0
        for p in ec.ler_paragrafos(path):
            i = p["indice"] + 1
            if p["texto"]:
                linhas.append((i, p["texto"]))
                locais[i] = f"parágrafo {i}" + (f" (numerado {p['numero']})" if p["numero"] else "")
        for marca, texto in docx_para_md.notas(path):  # notas de rodapé, depois do corpo
            i += 1
            linhas.append((i, texto))
            locais[i] = f"nota {marca}"
        return linhas, locais
    texto = path.read_text(encoding="utf-8")
    return [(i, l) for i, l in enumerate(texto.splitlines(), start=1) if l.strip()], {}


def checar_arquivos(refutadas: dict, paths: list[Path]) -> list[Acerto]:
    out = []
    for p in paths:
        linhas, locais = ler_linhas(p)
        out += checar_linhas(refutadas, linhas, p.name, locais)
    return out


def relatorio(refutadas: dict, acertos: list[Acerto], paths: list[Path]) -> str:
    linhas = [f"REFUTADAS — {refutadas.get('caso', '')}".rstrip(" —"),
              f"padrões: {len(refutadas['refutadas'])} | textos: {', '.join(p.name for p in paths)}", ""]
    for a in acertos:
        linhas.append(f"[{a.id}] {a.arquivo}:{a.linha} ({a.local}): {a.trecho}")
        if a.por_que:
            linhas.append(f"    por quê: {a.por_que}")
        if a.correto:
            linhas.append(f"    correto: {a.correto}" + (f" ({a.fonte})" if a.fonte else ""))
        elif a.fonte:
            linhas.append(f"    fonte: {a.fonte}")
    linhas += ["", f"Resultado: {len(acertos)} ocorrência(s) de afirmação refutada" if acertos else "Resultado: nenhuma afirmação refutada"]
    return "\n".join(linhas)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refutadas", type=Path, required=True, help="registro JSON das afirmações refutadas")
    ap.add_argument("textos", type=Path, nargs="+", help=".md, .txt ou .docx")
    ap.add_argument("--json", type=Path, help="grava os acertos em JSON")
    args = ap.parse_args(argv)
    try:
        refutadas = carregar(args.refutadas)
        for p in args.textos:
            if not p.exists():
                raise OSError(f"arquivo não encontrado: {p}")
        acertos = checar_arquivos(refutadas, args.textos)
    except (OSError, ValueError, KeyError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    print(relatorio(refutadas, acertos, args.textos))
    if args.json:
        args.json.write_text(json.dumps({"caso": refutadas.get("caso", ""), "acertos": [asdict(a) for a in acertos]},
                                        ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if acertos else 0


if __name__ == "__main__":
    sys.exit(main())
