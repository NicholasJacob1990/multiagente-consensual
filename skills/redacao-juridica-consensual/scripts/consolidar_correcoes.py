#!/usr/bin/env python3
"""Consolida as correções de vários verificadores e contraprovas: sem duplicata e sem conflito silencioso.

Cada verificador (remissões, fatos, ressalvas, leitor leigo...) devolve uma lista de
correções; cada contraprova aceita, ajusta ou rejeita as de um arquivo. Aplicar tudo
em sequência duplica trechos e deixa a última proposta vencer um conflito sem que
ninguém decida — foi assim que "(parágrafos 90, 105 e 105)" recebeu duas correções
diferentes no mesmo parecer.

Entradas (JSON, em qualquer ordem):

- correções: lista ``[{paragrafo, trecho_atual, trecho_novo, tipo, justificativa,
  fonte?, origem?, remissao_original?}]`` ou ``{"correcoes": [...]}``. Aceita os
  sinônimos ``local`` (paragrafo), ``texto_novo`` (trecho_novo) e ``motivo``
  (justificativa);
- decisões de contraprova: ``{"arquivo"?: "correcoes_X.json", "decisoes": [{"indice",
  "veredito", "trecho_atual"?, "trecho_novo"?}]}``. Pareamento por arquivo: o de
  ``"arquivo"`` (pelo nome) ou, sem ele, o arquivo de correções imediatamente anterior
  na linha de comando. ``indice`` é a posição na lista pareada (a partir de 1; se
  alguma decisão usar 0, a contagem é a partir de 0); se ``trecho_atual`` vier e não
  bater com a correção daquela posição, vale a correção com aquele trecho. Vereditos:
  aceita (aceita/aprovada/confirmada/mantida), ajustada (ajustada/parcial/modificada:
  vale o ``trecho_novo`` da decisão) e rejeitada (rejeitada/refutada/recusada/
  descartada). Em arquivo com contraprova, correção sem decisão não entra.

Consolidação:

1. **Duplicatas**: mesmo ``trecho_atual`` e mesmo ``trecho_novo`` (espaços
   normalizados) viram uma só correção, com as origens somadas.
2. **Conflitos**: mesmo ``trecho_atual`` com ``trecho_novo`` diferentes. Se o conflito é
   de remissão a parágrafo e há ``--mapa`` (saída de ``verificar_remissoes.py mapear``,
   ``{"mapa": {"antigo": [novos]}}``, ou ``{"novo_para_antigos": {"novo": [antigos]}}``),
   procura-se a remissão original da versão anterior: o campo ``remissao_original``
   ou, na justificativa/fonte, a remissão precedida de "v15", "versão anterior",
   "original", "antigo", "era(m)"... Convertida pelo mapa, ela dá o conjunto esperado de
   parágrafos novos; vence a única variante com exatamente esse conjunto. Sem mapa,
   sem remissão original ou sem variante única coerente, o conflito fica
   ``conflito_pendente`` e nenhuma das variantes entra na saída final.

Decisões já tomadas (``--decisoes DECISOES.json``, formato de ``checar_decisoes.py``;
modelo em ``decisoes_modelo.json``): proposta cujo ``trecho_novo`` ou ``justificativa``
casa com padrão de decisão registrada (e não apenas reproduz a forma adotada) sai da
lista final antes da deduplicação, com status ``decisao_ja_tomada``; vai para a chave
``decisao_ja_tomada`` do JSON de saída e para seção própria do relatório, com a decisão
vigente, para o usuário dizer se quer reabri-la. O registro (reconhecido pelos
``padroes``) não confunde com o arquivo de contraprova, que também tem ``decisoes``:
passado como entrada posicional, é recusado com aviso para usar ``--decisoes``.

Saída: ``--saida FINAL.json`` (``{"correcoes": [...]}``, só o que deve ser aplicado) e,
com ``--relatorio REL.md``, o relatório com aplicadas, duplicadas, rejeitadas, conflitos
e a decisão de cada um.

Uso::

    consolidar_correcoes.py verif_remissoes.json contraprova_remissoes.json verif_fatos.json \\
        --mapa mapa.json --decisoes decisoes.json --saida correcoes_final.json --relatorio consolidacao.md

Código de saída: 0 sem conflito pendente, 1 com conflito pendente (ou correção de
arquivo com contraprova sem decisão) e 2 em erro de uso ou de leitura.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import checar_decisoes as cd  # noqa: E402
import parecer_md as pm  # noqa: E402

ACEITA = {"aceita", "aceito", "aprovada", "aprovado", "confirmada", "confirmado", "mantida", "mantido", "procedente", "ok"}
AJUSTADA = {"ajustada", "ajustado", "ajuste", "parcial", "parcialmente", "modificada", "modificado", "aceita_com_ajuste",
            "aceita com ajuste", "reformulada"}
REJEITADA = {"rejeitada", "rejeitado", "refutada", "refutado", "recusada", "recusado", "descartada", "descartado",
             "improcedente"}
MARCA_ANTERIOR_RE = re.compile(
    r"(?:\bv\d+\b|vers[ãa]o anterior|original(?:mente)?|antig[oa]s?|\beram?\b|anterior(?:mente)?|na reda[çc][ãa]o anterior)",
    re.IGNORECASE,
)


@dataclass
class Correcao:
    paragrafo: object
    trecho_atual: str
    trecho_novo: str
    tipo: str = ""
    justificativa: str = ""
    fonte: str = ""
    origem: list[str] = field(default_factory=list)
    remissao_original: object = None
    extra: dict = field(default_factory=dict)

    @property
    def chave(self) -> tuple[str, str]:
        return norm(self.trecho_atual), norm(self.trecho_novo)

    def saida(self) -> dict:
        d = {"paragrafo": self.paragrafo, "trecho_atual": self.trecho_atual, "trecho_novo": self.trecho_novo,
             "tipo": self.tipo, "justificativa": self.justificativa}
        if self.fonte:
            d["fonte"] = self.fonte
        d["origem"] = self.origem if len(self.origem) > 1 else (self.origem[0] if self.origem else "")
        d.update(self.extra)
        return d


def norm(t: str) -> str:
    return re.sub(r"\s+", " ", (t or "").replace("\u00a0", " ")).strip()


def _correcao(d: dict, origem_padrao: str) -> Correcao:
    if not isinstance(d, dict):
        raise ValueError(f"{origem_padrao}: correção não é objeto JSON")
    atual = d.get("trecho_atual")
    novo = d.get("trecho_novo", d.get("texto_novo"))
    if atual is None or novo is None:
        raise ValueError(f"{origem_padrao}: correção sem trecho_atual/trecho_novo: {json.dumps(d, ensure_ascii=False)[:120]}")
    conhecidos = {"paragrafo", "local", "trecho_atual", "trecho_novo", "texto_novo", "tipo", "justificativa", "motivo",
                  "fonte", "origem", "remissao_original"}
    origem = d.get("origem") or origem_padrao
    return Correcao(
        paragrafo=d.get("paragrafo", d.get("local")),
        trecho_atual=atual,
        trecho_novo=novo,
        tipo=d.get("tipo", ""),
        justificativa=d.get("justificativa", d.get("motivo", "")),
        fonte=d.get("fonte", ""),
        origem=origem if isinstance(origem, list) else [origem],
        remissao_original=d.get("remissao_original"),
        extra={k: v for k, v in d.items() if k not in conhecidos},
    )


@dataclass
class Registro:
    """O que aconteceu com cada correção, para o relatório."""
    aplicadas: list[Correcao] = field(default_factory=list)
    duplicadas: list[tuple[Correcao, Correcao]] = field(default_factory=list)  # (descartada, mantida)
    rejeitadas: list[tuple[Correcao, str]] = field(default_factory=list)
    sem_decisao: list[Correcao] = field(default_factory=list)
    conflitos: list[dict] = field(default_factory=list)
    decisao_ja_tomada: list[tuple[Correcao, list[dict]]] = field(default_factory=list)  # (proposta, decisões casadas)


def _veredito(v: str) -> str:
    v = norm(str(v)).lower()
    if v in ACEITA:
        return "aceita"
    if v in AJUSTADA or v.startswith("ajust") or "com ajuste" in v:
        return "ajustada"
    if v in REJEITADA or v.startswith(("rejeit", "refut", "recus", "descart")):
        return "rejeitada"
    return "pendente"


def carregar(paths: list[Path], reg: Registro) -> list[Correcao]:
    """Lê as entradas, aplica as decisões de contraprova e devolve as correções que seguem."""
    arquivos: list[tuple[str, list[Correcao]]] = []
    decisoes: list[tuple[str, dict, str | None]] = []  # (nome, dados, arquivo pareado)
    for p in paths:
        dados = json.loads(p.read_text(encoding="utf-8"))
        if isinstance(dados, dict) and _e_registro_de_decisoes(dados):
            raise ValueError(f"{p.name}: é registro de decisões do caso (padroes); passe-o com --decisoes")
        if isinstance(dados, dict) and "decisoes" in dados:
            alvo = dados.get("arquivo")
            if alvo:
                alvo = Path(alvo).name
            elif arquivos:
                alvo = arquivos[-1][0]
            else:
                raise ValueError(f"{p.name}: decisões sem arquivo de correções antes nem campo 'arquivo'")
            decisoes.append((p.name, dados, alvo))
            continue
        lista = dados.get("correcoes") if isinstance(dados, dict) else dados
        if not isinstance(lista, list):
            raise ValueError(f"{p.name}: esperado lista de correções ou {{\"correcoes\": [...]}}")
        arquivos.append((p.name, [_correcao(d, p.name) for d in lista]))
    por_nome = {n: cs for n, cs in arquivos}
    resultado: dict[str, list[Correcao | None]] = {n: list(cs) for n, cs in arquivos}
    com_contraprova: dict[str, set[int]] = {}
    for nome, dados, alvo in decisoes:
        if alvo not in por_nome:
            raise ValueError(f"{nome}: arquivo pareado {alvo!r} não está entre as entradas")
        cs = por_nome[alvo]
        decididas = com_contraprova.setdefault(alvo, set())
        lista = dados.get("decisoes") or []
        base = 0 if any(isinstance(d.get("indice"), int) and d.get("indice") == 0 for d in lista) else 1
        for d in lista:
            i = d.get("indice")
            pos = i - base if isinstance(i, int) else None
            if d.get("trecho_atual") and (pos is None or not (0 <= pos < len(cs)) or norm(cs[pos].trecho_atual) != norm(d["trecho_atual"])):
                pos = next((k for k, c in enumerate(cs) if norm(c.trecho_atual) == norm(d["trecho_atual"])), None)
            if pos is None or not (0 <= pos < len(cs)):
                raise ValueError(f"{nome}: decisão {d!r} não corresponde a correção de {alvo}")
            decididas.add(pos)
            v = _veredito(d.get("veredito", ""))
            c = cs[pos]
            if v == "rejeitada":
                reg.rejeitadas.append((c, f"contraprova ({nome}): {d.get('veredito')}" + (f" — {d['motivo']}" if d.get("motivo") else "")))
                resultado[alvo][pos] = None
            elif v == "ajustada":
                if d.get("trecho_novo") is None:
                    raise ValueError(f"{nome}: decisão ajustada sem trecho_novo (índice {i})")
                c.trecho_novo = d["trecho_novo"]
                if d.get("trecho_atual"):
                    c.trecho_atual = d["trecho_atual"]
                c.origem.append(f"{nome} (ajustada)")
            elif v == "pendente":
                reg.rejeitadas.append((c, f"contraprova ({nome}): veredito não reconhecido {d.get('veredito')!r}"))
                resultado[alvo][pos] = None
            else:
                if d.get("trecho_novo") and norm(d["trecho_novo"]) != norm(c.trecho_novo):
                    c.trecho_novo = d["trecho_novo"]
                c.origem.append(f"{nome} (aceita)")
    out = []
    for nome, cs in resultado.items():
        for k, c in enumerate(cs):
            if c is None:
                continue
            if nome in com_contraprova and k not in com_contraprova[nome]:
                reg.sem_decisao.append(c)
                continue
            out.append(c)
    return out


def _e_registro_de_decisoes(dados: dict) -> bool:
    ds = dados.get("decisoes")
    return isinstance(ds, list) and any(isinstance(d, dict) and "padroes" in d for d in ds)


def filtrar_decisoes(correcoes: list[Correcao], registro: dict, reg: Registro) -> list[Correcao]:
    """Tira as propostas que reabrem decisão já tomada (``trecho_novo`` ou ``justificativa``)."""
    out = []
    for c in correcoes:
        casadas: dict[str, dict] = {}
        for campo, texto in (("trecho_novo", c.trecho_novo), ("justificativa", c.justificativa)):
            for d, trecho in cd.casar_texto(registro, texto or ""):
                casadas.setdefault(str(d["id"]), {"id": str(d["id"]), "tema": d.get("tema", ""), "decisao": d["decisao"],
                                                  "data": d.get("data", ""), "origem": d.get("origem", ""),
                                                  "campo": campo, "trecho": trecho})
        if casadas:
            reg.decisao_ja_tomada.append((c, list(casadas.values())))
        else:
            out.append(c)
    return out


# ---------------------------------------------------------------- mapa e remissões

def ler_mapa(path: Path) -> dict[int, list[int]]:
    """Mapa antigo -> novos, a partir de ``{"mapa": {...}}`` ou ``{"novo_para_antigos": {...}}``."""
    dados = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(dados, dict) and isinstance(dados.get("mapa"), dict):
        return {int(k): [int(x) for x in (v or [])] for k, v in dados["mapa"].items()}
    bruto = dados.get("novo_para_antigos") if isinstance(dados, dict) and "novo_para_antigos" in dados else dados
    if not isinstance(bruto, dict):
        raise ValueError(f"{path.name}: mapa em formato desconhecido")
    out: dict[int, list[int]] = {}
    for novo, antigos in bruto.items():
        if not re.fullmatch(r"\d+", str(novo)):
            continue
        for a in antigos if isinstance(antigos, list) else [antigos]:
            out.setdefault(int(a), []).append(int(novo))
    return {k: sorted(set(v)) for k, v in out.items()}


def numeros_remissao(texto: str) -> list[int]:
    return [n for _, ns in pm.remissoes(texto) for n in ns]


def remissao_original(c: Correcao) -> list[int] | None:
    """Números da remissão na versão anterior: campo próprio ou remissão marcada na justificativa/fonte."""
    r = c.remissao_original
    if isinstance(r, list):
        return [int(x) for x in r]
    if isinstance(r, (int, str)) and str(r).strip():
        nums = numeros_remissao(str(r)) or [int(x) for x in re.findall(r"\d+", str(r))]
        return nums or None
    for texto in (c.justificativa, c.fonte):
        for m in pm.REMISSAO_RE.finditer(texto or ""):
            antes = texto[max(0, m.start() - 60):m.start()]
            if MARCA_ANTERIOR_RE.search(antes):
                return pm.expandir_numeros(m.group(1))
    return None


def decidir_conflito(variantes: list[Correcao], mapa: dict[int, list[int]] | None) -> tuple[Correcao | None, str]:
    """Escolhe a variante coerente com o mapa, ou explica por que o conflito fica pendente."""
    remissao = any(numeros_remissao(v.trecho_atual) or numeros_remissao(v.trecho_novo) for v in variantes)
    if not remissao:
        return None, "conflito de redação (não é de remissão): decidir manualmente"
    if mapa is None:
        return None, "conflito de remissão sem --mapa: decidir manualmente"
    originais = [o for o in (remissao_original(v) for v in variantes) if o]
    if not originais:
        return None, "conflito de remissão sem a remissão original da versão anterior na justificativa/fonte"
    esperados = []
    for orig in originais:
        sem_destino = [n for n in orig if not mapa.get(n)]
        if sem_destino:
            return None, f"remissão original {orig} tem parágrafo sem destino no mapa ({sem_destino}): decidir manualmente"
        esperados.append(sorted({x for n in orig for x in mapa[n]}))
    if any(e != esperados[0] for e in esperados):
        return None, f"as variantes indicam remissões originais diferentes ({originais}): decidir manualmente"
    esperado = esperados[0]
    coerentes = [v for v in variantes if sorted(set(numeros_remissao(v.trecho_novo))) == esperado]
    if len(coerentes) == 1:
        return coerentes[0], (f"remissão original {originais[0]} → pelo mapa, parágrafos {esperado}: "
                              f"vence «{coerentes[0].trecho_novo}»")
    if not coerentes:
        return None, f"nenhuma variante cita exatamente os parágrafos {esperado} que o mapa dá para {originais[0]}"
    return None, f"mais de uma variante coerente com o mapa ({esperado})"


def consolidar(correcoes: list[Correcao], mapa: dict[int, list[int]] | None, reg: Registro) -> list[Correcao]:
    unicas: dict[tuple[str, str], Correcao] = {}
    for c in correcoes:
        if c.chave in unicas:
            mantida = unicas[c.chave]
            reg.duplicadas.append((c, mantida))
            for o in c.origem:
                if o not in mantida.origem:
                    mantida.origem.append(o)
            if c.fonte and c.fonte not in mantida.fonte:
                mantida.fonte = "; ".join(x for x in (mantida.fonte, c.fonte) if x)
            continue
        unicas[c.chave] = c
    grupos: dict[str, list[Correcao]] = {}
    for c in unicas.values():
        grupos.setdefault(norm(c.trecho_atual), []).append(c)
    final = []
    for atual, vs in grupos.items():
        if len(vs) == 1:
            final.append(vs[0])
            continue
        escolhida, motivo = decidir_conflito(vs, mapa)
        reg.conflitos.append({
            "trecho_atual": vs[0].trecho_atual,
            "paragrafos": sorted({str(v.paragrafo) for v in vs if v.paragrafo is not None}),
            "variantes": [{"trecho_novo": v.trecho_novo, "origem": v.origem, "justificativa": v.justificativa} for v in vs],
            "decisao": "escolhida" if escolhida else "conflito_pendente",
            "escolhida": escolhida.trecho_novo if escolhida else None,
            "motivo": motivo,
        })
        if escolhida:
            escolhida.extra["conflito_resolvido"] = motivo
            final.append(escolhida)
    reg.aplicadas = final
    return final


# ---------------------------------------------------------------- relatório

def _c(s: object) -> str:
    return str(s if s is not None else "").replace("|", "\\|").replace("\n", " ")


def relatorio(reg: Registro, entradas: list[Path], mapa: Path | None, decisoes: Path | None = None) -> str:
    pend = [c for c in reg.conflitos if c["decisao"] == "conflito_pendente"]
    linhas = ["# Consolidação de correções", "",
              f"Entradas: {', '.join(p.name for p in entradas)}" + (f" | mapa: {mapa.name}" if mapa else "")
              + (f" | decisões: {decisoes.name}" if decisoes else ""), "",
              f"Aplicadas: {len(reg.aplicadas)} | duplicadas removidas: {len(reg.duplicadas)} | rejeitadas: {len(reg.rejeitadas)} | "
              f"sem decisão da contraprova: {len(reg.sem_decisao)} | conflitos: {len(reg.conflitos)} "
              f"({len(pend)} pendentes)" + (f" | decisão já tomada: {len(reg.decisao_ja_tomada)}" if decisoes else ""), ""]
    linhas += ["## Aplicadas", ""]
    if reg.aplicadas:
        linhas += ["| # | § | Trecho atual | Trecho novo | Tipo | Origem |", "|---:|---|---|---|---|---|"]
        for i, c in enumerate(reg.aplicadas, start=1):
            linhas.append(f"| {i} | {_c(c.paragrafo)} | {_c(c.trecho_atual)} | {_c(c.trecho_novo)} | {_c(c.tipo)} | {_c(', '.join(c.origem))} |")
    else:
        linhas.append("Nenhuma.")
    linhas += ["", "## Duplicadas", ""]
    linhas += [f"- «{_c(d.trecho_atual)}» → «{_c(d.trecho_novo)}» ({_c(', '.join(d.origem))}), igual à de {_c(', '.join(m.origem[:1]))}"
               for d, m in reg.duplicadas] or ["Nenhuma."]
    linhas += ["", "## Conflitos", ""]
    if reg.conflitos:
        for k, cf in enumerate(reg.conflitos, start=1):
            linhas.append(f"### {k}. «{_c(cf['trecho_atual'])}»" + (f" (§ {', '.join(cf['paragrafos'])})" if cf["paragrafos"] else ""))
            linhas.append("")
            for v in cf["variantes"]:
                marca = " ✔" if cf["escolhida"] == v["trecho_novo"] else ""
                linhas.append(f"- «{_c(v['trecho_novo'])}»{marca} — {_c(', '.join(v['origem']))}: {_c(v['justificativa'])}")
            linhas += ["", f"**Decisão:** {'escolhida' if cf['escolhida'] else 'CONFLITO PENDENTE (fora da saída final)'} — {cf['motivo']}", ""]
    else:
        linhas.append("Nenhum.")
    if reg.rejeitadas or reg.sem_decisao:
        linhas += ["", "## Fora da saída por contraprova", ""]
        linhas += [f"- «{_c(c.trecho_atual)}» → «{_c(c.trecho_novo)}»: {_c(m)}" for c, m in reg.rejeitadas]
        linhas += [f"- «{_c(c.trecho_atual)}» → «{_c(c.trecho_novo)}»: sem decisão da contraprova pareada" for c in reg.sem_decisao]
    if decisoes:
        linhas += ["", "## Decisão já tomada (fora da saída — reabrir?)", ""]
        if not reg.decisao_ja_tomada:
            linhas.append("Nenhuma proposta reabre decisão registrada.")
        for c, ds in reg.decisao_ja_tomada:
            linhas.append(f"- § {_c(c.paragrafo)}: «{_c(c.trecho_atual)}» → «{_c(c.trecho_novo)}» ({_c(', '.join(c.origem))})")
            for d in ds:
                quando = ", ".join(x for x in (d["data"], d["origem"]) if x)
                linhas.append(f"  - [{_c(d['id'])}] {_c(d['tema'] + ': ' if d['tema'] else '')}{_c(d['decisao'])}"
                              + (f" ({_c(quando)})" if quando else "") + f" — casou «{_c(d['trecho'])}» em {d['campo']}")
    return "\n".join(linhas) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entradas", type=Path, nargs="+", help="listas de correções e decisões de contraprova (JSON)")
    ap.add_argument("--mapa", type=Path, help="mapa de origem (verificar_remissoes mapear ou novo_para_antigos)")
    ap.add_argument("--decisoes", type=Path, help="registro das decisões do caso (formato de checar_decisoes.py)")
    ap.add_argument("--saida", type=Path, required=True, help="JSON final com as correções a aplicar")
    ap.add_argument("--relatorio", type=Path, help="relatório Markdown")
    args = ap.parse_args(argv)
    reg = Registro()
    try:
        for p in args.entradas + [x for x in (args.mapa, args.decisoes) if x]:
            if not p.exists():
                raise OSError(f"arquivo não encontrado: {p}")
        mapa = ler_mapa(args.mapa) if args.mapa else None
        registro = cd.carregar(args.decisoes) if args.decisoes else None
        correcoes = carregar(args.entradas, reg)
        if registro is not None:
            correcoes = filtrar_decisoes(correcoes, registro, reg)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    final = consolidar(correcoes, mapa, reg)
    saida = {"correcoes": [c.saida() for c in final]}
    if reg.decisao_ja_tomada:
        saida["decisao_ja_tomada"] = [c.saida() | {"status": "decisao_ja_tomada", "decisoes": ds} for c, ds in reg.decisao_ja_tomada]
    args.saida.write_text(json.dumps(saida, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rel = relatorio(reg, args.entradas, args.mapa, args.decisoes)
    if args.relatorio:
        args.relatorio.write_text(rel, encoding="utf-8")
    pend = sum(1 for c in reg.conflitos if c["decisao"] == "conflito_pendente")
    print(f"aplicadas: {len(final)} | duplicadas: {len(reg.duplicadas)} | rejeitadas: {len(reg.rejeitadas)} | "
          f"sem decisão: {len(reg.sem_decisao)} | conflitos: {len(reg.conflitos)} ({pend} pendentes)"
          + (f" | decisão já tomada: {len(reg.decisao_ja_tomada)}" if args.decisoes else "") + f" → {args.saida}")
    return 1 if pend or reg.sem_decisao else 0


if __name__ == "__main__":
    sys.exit(main())
