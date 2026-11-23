#!/usr/bin/env python3
"""Confere, em toda versão, as verificações aritméticas registradas para o caso.

Pareceres patrimoniais e registrais vivem de contas: soma das áreas excluídas de
uma matrícula, proporção dos créditos de uma adjudicação, área perdida num canto
arredondado, prazo em dias. A conta é feita uma vez, conferida, e depois tem de
continuar fechando — e os números certos têm de continuar no texto, sem que a
reescrita troque um pelo outro. Os números são do caso, não do plugin: ficam num
registro na pasta do caso (``verificacoes.json``; modelo vazio em
``verificacoes_modelo.json``).

Formato::

    {
      "caso": "…",
      "verificacoes": [
        {"id": "A1",
         "descricao": "exclusões da Matrícula nº 12.345 + remanescente = total do loteamento",
         "expressao": "422.167,00 + 552.188,00 = 974.355,00",
         "tolerancia": 0.01,
         "no_texto": ["552.188", "974.355"]},
        {"id": "A2", "descricao": "proporção dos créditos da adjudicação",
         "expressao": "64,73 + 35,27 = 100", "no_texto": ["64,73", "35,27"]},
        {"id": "A3", "descricao": "área perdida no canto arredondado (raio 20 m)",
         "expressao": "20^2 - pi*20^2/4 = 85,84", "tolerancia": 0.01}
      ]
    }

``expressao``: dois lados separados por ``=`` (ou ``≈``), com números no formato
brasileiro (``422.167,00``) ou com ponto decimal (``85.84``), os operadores
``+ - * / ^ ( )``, a constante ``pi`` e as funções ``sqrt`` e ``round``. Avaliada
sem ``eval``. ``tolerancia`` (padrão 0,005) é a diferença absoluta admitida.

``no_texto`` (opcional): números ou trechos que precisam aparecer no texto
conferido (normalização de espaços; número comparado também sem os decimais
",00"). ``nao_no_texto`` (opcional): trechos que não podem aparecer.

Uso::

    conferir_aritmetica.py --verificacoes verificacoes.json [TEXTO.(md|txt|docx) ...] [--json SAIDA] [--md]

Sem texto, confere só as contas. Código de saída: 0 tudo fecha; 1 conta que não
fecha ou trecho exigido ausente (ou proibido presente); 2 erro de uso.
"""
from __future__ import annotations

import argparse
import ast
import json
import math
import operator
import re
import sys
from pathlib import Path

NUM_BR = re.compile(r"(?<![\w.,])(\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+(?:\.\d+)?)(?![\w])")


def _num_py(token: str) -> str:
    """Converte número no formato brasileiro para literal Python."""
    if "," in token:
        return token.replace(".", "").replace(",", ".")
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return token.replace(".", "")
    return token


def _normalizar_expressao(lado: str) -> str:
    lado = lado.replace("×", "*").replace("÷", "/").replace("π", "pi").replace("^", "**")
    lado = lado.replace("−", "-").replace("–", "-")
    return NUM_BR.sub(lambda m: _num_py(m.group(1)), lado)


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.Pow: operator.pow, ast.USub: operator.neg, ast.UAdd: operator.pos}
_FUNCS = {"sqrt": math.sqrt, "round": round}
_CONST = {"pi": math.pi}


def avaliar(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Name) and n.id in _CONST:
            return _CONST[n.id]
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS and not n.keywords:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError(f"elemento não permitido na expressão: {ast.dump(n)[:60]}")
    return float(ev(ast.parse(_normalizar_expressao(expr), mode="eval")))


def conferir_conta(v: dict) -> dict:
    expr = v.get("expressao", "")
    partes = re.split(r"\s*(?:=|≈)\s*", expr)
    if len(partes) != 2:
        raise ValueError(f"{v.get('id')}: a expressão precisa de exatamente um '=' ou '≈': {expr!r}")
    esq, dir_ = avaliar(partes[0]), avaliar(partes[1])
    tol = float(v.get("tolerancia", 0.005))
    return {"esquerda": esq, "direita": dir_, "diferenca": abs(esq - dir_), "tolerancia": tol,
            "fecha": abs(esq - dir_) <= tol}


def ler_texto(path: Path) -> str:
    if path.suffix.lower() == ".docx":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import docx_para_md  # noqa: E402
        return docx_para_md.converter(path)
    return path.read_text(encoding="utf-8")


def _norm(t: str) -> str:
    return re.sub(r"\s+", " ", t.replace(" ", " ")).strip()


def presente(trecho: str, texto: str) -> bool:
    t, x = _norm(trecho), _norm(texto)
    if t in x:
        return True
    if re.fullmatch(r"[\d.,]+", t):
        base = re.sub(r",0+$", "", t)
        return re.search(r"(?<![\d.,])" + re.escape(base) + r"(?:,0+)?(?![\d])", x) is not None
    return False


def conferir(registro: dict, textos: dict[str, str]) -> dict:
    itens = []
    for v in registro.get("verificacoes", []):
        r = {"id": v.get("id"), "descricao": v.get("descricao", ""), "expressao": v.get("expressao", "")}
        try:
            r.update(conferir_conta(v))
        except (ValueError, SyntaxError, ZeroDivisionError, TypeError) as e:
            r.update({"fecha": False, "erro": str(e)})
        faltando, proibidos = {}, {}
        for nome, texto in textos.items():
            f = [t for t in v.get("no_texto", []) if not presente(t, texto)]
            p = [t for t in v.get("nao_no_texto", []) if _norm(t) in _norm(texto)]
            if f:
                faltando[nome] = f
            if p:
                proibidos[nome] = p
        r["faltando_no_texto"], r["proibidos_no_texto"] = faltando, proibidos
        r["ok"] = bool(r.get("fecha")) and not faltando and not proibidos
        itens.append(r)
    return {"caso": registro.get("caso", ""), "itens": itens, "ok": all(i["ok"] for i in itens)}


def relatorio_md(res: dict) -> str:
    L = [f"## Verificações aritméticas — {res['caso'] or 'caso'}", "",
         "| id | descrição | expressão | resultado | no texto |", "|---|---|---|---|---|"]
    for i in res["itens"]:
        if "erro" in i:
            conta = f"erro: {i['erro']}"
        else:
            conta = (f"fecha (dif. {i['diferenca']:.4g})" if i["fecha"]
                     else f"**NÃO FECHA**: {i['esquerda']:.6g} × {i['direita']:.6g}")
        txt = []
        for nome, f in i["faltando_no_texto"].items():
            txt.append(f"faltam em {nome}: {', '.join(f)}")
        for nome, p in i["proibidos_no_texto"].items():
            txt.append(f"proibido em {nome}: {', '.join(p)}")
        L.append(f"| {i['id']} | {i['descricao']} | `{i['expressao']}` | {conta} | {'; '.join(txt) or 'ok'} |")
    L += ["", "Resultado: " + ("todas as verificações fecham." if res["ok"] else "há verificação que não fecha.")]
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--verificacoes", type=Path, required=True)
    ap.add_argument("textos", nargs="*", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--md", action="store_true", help="relatório em Markdown (padrão)")
    a = ap.parse_args(argv)
    try:
        registro = json.loads(a.verificacoes.read_text(encoding="utf-8"))
        textos = {p.name: ler_texto(p) for p in a.textos}
    except (OSError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    res = conferir(registro, textos)
    print(relatorio_md(res))
    if a.json:
        a.json.write_text(json.dumps(res, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if res["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
