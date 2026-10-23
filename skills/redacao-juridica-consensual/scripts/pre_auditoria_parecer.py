#!/usr/bin/env python3
"""Pré-auditoria determinística de qualquer trabalho jurídico em Markdown: parecer, petição, recurso, decisão.

Roda antes de qualquer auditoria por modelo e depois de cada rodada de
emendas. Pega o que é mecânico — numeração, tamanho dos parágrafos, fecho,
remissões internas, marcadores soltos, assinatura, repetição de precedente,
frases quase iguais, trechos travados e remissões quebradas por renumeração —
para que os auditores gastem a atenção no mérito. Com ``--anterior``, aponta ainda
palavras de alcance acrescentadas ou retiradas ("até", "sempre", "somente", "deverá"...),
ressalvas que sumiram e frases da versão anterior sem correspondente na nova.

Documento sem parágrafos numerados (comum em petições) é lido com numeração
implícita; nesse caso a sequência numérica e as remissões internas não são
cobradas. Requisitos de forma de uma casa (fecho, rótulos, assinatura) entram
como perfil em ``PERFIS``.

Saída: relatório em texto (stdout) e, opcionalmente, JSON. Código de saída 1
quando houver achado bloqueante, 0 quando não houver e 2 em erro de uso.

Exemplos::

    pre_auditoria_parecer.py parecer_v30.md --perfil genes
    pre_auditoria_parecer.py parecer_v31.md --perfil genes --anterior parecer_v30.md \\
        --travados travados.json --pdf parecer_v31.pdf --max-paginas 17 --json pre.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402

PERFIS = {
    "generico": {
        "max_palavras": None,
        "fecho": None,
        "rotulos_conclusao": [],
        "assinatura": [],
    },
    "genes": {
        "max_palavras": 120,
        "fecho": "É o parecer, sob censura.",
        "rotulos_conclusao": [
            "Correções necessárias",
            "Obrigações já incidentes",
            "Recomendações facultativas",
            "Providências fora do regulamento",
        ],
        "assinatura": [
            "[Nome do(a) Advogado(a)]",
            "OAB/MG",
            "De acordo:",
            "Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)",
        ],
    },
}

MARCADORES_RE = re.compile(
    r"\[(?:INFORMAR|CONFIRMAR|NÃO CONSTA|NAO CONSTA|NÃO VERIFICADO[^\]]*|PENDENTE[^\]]*|VERIFICAR[^\]]*|TODO)\]"
    r"|\bTODO\b|\bXXX\b|\?\?",
)
CLASSES_LONGAS = {
    "conflito de competência": "CC",
    "ação direta de inconstitucionalidade": "ADI",
    "ação declaratória de constitucionalidade": "ADC",
    "arguição de descumprimento de preceito fundamental": "ADPF",
    "recurso extraordinário": "RE",
    "recurso especial": "REsp",
    "mandado de segurança": "MS",
    "reclamação": "Rcl",
}
JULGADO_RE = re.compile(
    r"\b(?P<classe>ADI|ADC|ADPF|ADO|RE|ARE|REsp|AREsp|RMS|MS|HC|Rcl|CC|ACO|MI|Pet|Tema|S[úu]mula(?:\s+Vinculante)?|Ac[óo]rd[ãa]o"
    r"|" + "|".join(k.replace("ç", "[çc]").replace("ê", "[êe]").replace("ã", "[ãa]").replace("ú", "[úu]").replace("ó", "[óo]")
                   for k in CLASSES_LONGAS) +
    r")\s+(?:n\.?\s*[º°]\s*|n[º°.]?\s+)?(?P<numero>\d+(?:\.\d{3})*(?:/\d{4})?)(?:/[A-Z]{2})?",
    re.IGNORECASE,
)


def chave_julgado(m: re.Match) -> str:
    classe = re.sub(r"\s+", " ", m.group("classe")).lower()
    classe = CLASSES_LONGAS.get(classe, classe).upper()
    return f"{classe} {m.group('numero').replace('.', '')}"


NAO_VERIFICADO_RE = re.compile(
    r"n[ãa]o verificad|n[ãa]o foi poss[íi]vel (?:verificar|confirmar|localizar)|n[ãa]o localizad"
    r"|pendente de (?:confer|verifica)|\ba confirmar\b|sem acesso ao texto",
    re.IGNORECASE,
)
INEXISTENCIA_RE = re.compile(
    r"\bn[ãa]o (?:prev[êe]|h[áa]\b|cont[ée]m|possui|exige|traz|menciona|disciplina|estabelece|tem)"
    r"|\bsilencia|\bnenhum(?:a)? (?:dispositivo|norma|regra|inciso)|\bomiss[oa]\b",
    re.IGNORECASE,
)
CERTEZA_RE = re.compile(
    r"\b(certamente|inequivocamente|sem d[úu]vida|indiscutivelmente|evidentemente|obviamente|incontestavelmente)\b",
    re.IGNORECASE,
)
PREVISAO_RE = re.compile(r"\b\d+\s+dias|\b\d{1,2} de [a-zç]+ de \d{4}", re.IGNORECASE)
PREVISAO_VERBO_RE = re.compile(r"\b(ser[áa]|ocorrer[áa]|terminar[áa]|ultrapassar[áa]|exigir[áa]|levar[áa])\b", re.IGNORECASE)
CAUTELA_RE = re.compile(r"estimativ|cerca de|aproximad|\bpode\b|\bpoder[áa]\b|tende|provável|a depender|se executad", re.IGNORECASE)
ALCANCE_TERMOS = (
    "até", "sempre", "nunca", "exclusivamente", "somente", "apenas", "necessariamente", "obrigatoriamente",
    "não pode", "não poderá", "deve", "devem", "deverá", "deverão", "pode", "podem", "poderá", "poderão",
    "vedado", "vedada", "facultativo", "facultativa", "no mínimo", "no máximo", "todos", "todas", "qualquer",
    "nenhum", "nenhuma", "cerca de", "aproximadamente", "estimativa", "em regra", "imediatamente",
)
RESSALVA_TERMOS = ("salvo", "exceto", "ressalvad", "desde que", "sem prejuízo", "a menos que", "quando couber",
                   "observad", "se houver", "no que couber")
FRASE_RE = re.compile(r"(?<=[.;])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ\"“(])")


@dataclass
class Achado:
    severidade: str  # bloqueante | alerta | info
    regra: str
    paragrafo: int | None
    mensagem: str


def _frases(texto: str) -> list[str]:
    return [f.strip() for f in FRASE_RE.split(pm.sem_negrito(texto)) if f.strip()]


def _blocos_assinatura(doc: pm.Documento, fecho: str | None) -> set[int]:
    """Índices de bloco isentos de marcadores: bloco de assinatura e o que vier depois do fecho."""
    isentos = {i for i, b in enumerate(doc.blocos) if b.tipo == "marca" and b.marca in pm.MARCAS_ASSINATURA}
    if fecho:
        for i, b in enumerate(doc.blocos):
            if b.tipo == "par" and b.texto.strip() == fecho:
                isentos.update(range(i + 1, len(doc.blocos)))
                break
    return isentos


def checar_numeracao(doc: pm.Documento) -> list[Achado]:
    if doc.numeracao != "explicita":
        return [Achado("info", "numeracao", None,
                       f"numeração {doc.numeracao}: IDs globais usados para localizar; números de listas/pedidos preservados")]
    nums = [b.numero for b in doc.paragrafos]
    if not nums:
        return [Achado("bloqueante", "numeracao", None, "nenhum parágrafo numerado encontrado")]
    out = []
    vistos: set[int] = set()
    anterior = 0
    for n in nums:
        if n in vistos:
            out.append(Achado("bloqueante", "numeracao", n, f"número {n} repetido"))
        elif n != anterior + 1:
            out.append(Achado("bloqueante", "numeracao", n, f"esperado {anterior + 1}, encontrado {n}"))
        vistos.add(n)
        anterior = n
    return out


def checar_palavras(doc: pm.Documento, maximo: int | None) -> list[Achado]:
    if not maximo:
        return []
    return [
        Achado("bloqueante", "palavras", b.numero, f"{pm.palavras(b.texto)} palavras (máximo {maximo})")
        for b in doc.paragrafos
        if pm.palavras(b.texto) > maximo
    ]


def checar_fecho(doc: pm.Documento, fecho: str | None) -> list[Achado]:
    if not fecho:
        return []
    pars = doc.paragrafos
    achados = [b for b in pars if b.texto.strip() == fecho]
    if not achados:
        return [Achado("bloqueante", "fecho", None, f'fecho "{fecho}" ausente')]
    if pars[-1].texto.strip() != fecho:
        return [Achado("alerta", "fecho", achados[0].numero, "o fecho não é o último parágrafo numerado")]
    return []


def checar_remissoes(doc: pm.Documento) -> list[Achado]:
    if doc.numeracao != "explicita":
        return []  # IDs de bloco não são números de parágrafo exibidos no documento.
    existentes = {b.numero for b in doc.paragrafos}
    out = []
    for b in doc.paragrafos:
        for trecho, nums in pm.remissoes(b.texto):
            for n in nums:
                if n not in existentes:
                    out.append(Achado("bloqueante", "remissao", b.numero, f'"{trecho}" aponta para parágrafo {n}, que não existe'))
                elif n == b.numero:
                    out.append(Achado("bloqueante", "remissao", b.numero, f'"{trecho}" remete ao próprio parágrafo'))
    return out


def checar_marcadores(doc: pm.Documento, fecho: str | None, proibidos: list[str]) -> list[Achado]:
    isentos = _blocos_assinatura(doc, fecho)
    out = []
    for i, b in enumerate(doc.blocos):
        if i in isentos:
            continue
        for m in MARCADORES_RE.finditer(b.texto):
            onde = f"linha {b.linha}"
            out.append(Achado("bloqueante", "marcador", b.numero, f'marcador solto "{m.group(0)}" ({onde})'))
        for termo in proibidos:
            if termo and termo.lower() in b.texto.lower():
                out.append(Achado("alerta", "termo_proibido", b.numero, f'termo proibido "{termo}" (linha {b.linha})'))
    return out


def checar_conclusao(doc: pm.Documento, rotulos: list[str]) -> list[Achado]:
    if not rotulos:
        return []
    inicio = None
    for i, b in enumerate(doc.blocos):
        if b.tipo == "titulo" and "conclus" in b.texto.lower():
            inicio = i
    if inicio is None:
        return [Achado("bloqueante", "conclusao", None, "seção de conclusão não encontrada")]
    texto = "\n".join(b.texto for b in doc.blocos[inicio + 1:] if b.tipo == "par")
    return [
        Achado("bloqueante", "conclusao", None, f'rótulo em negrito "**{r}**" ausente da conclusão')
        for r in rotulos
        if f"**{r}" not in texto
    ]


def checar_assinatura(doc: pm.Documento, fecho: str | None, linhas: list[str]) -> list[Achado]:
    if not linhas:
        return []
    isentos = _blocos_assinatura(doc, fecho)
    texto = "\n".join(doc.blocos[i].texto for i in sorted(isentos))
    return [Achado("bloqueante", "assinatura", None, f'linha de assinatura ausente: "{l}"') for l in linhas if l not in texto]


def checar_julgados_repetidos(doc: pm.Documento) -> list[Achado]:
    onde: dict[str, list[int]] = {}
    for b in doc.paragrafos:
        for m in JULGADO_RE.finditer(b.texto):
            chave = chave_julgado(m)
            if b.numero not in onde.setdefault(chave, []):
                onde[chave].append(b.numero)  # type: ignore[arg-type]
    return [
        Achado("alerta", "julgado_repetido", ps[0], f"{k} citado nos parágrafos {', '.join(map(str, ps))}: confirmar que não há fundamentação duplicada")
        for k, ps in onde.items()
        if len(ps) > 1
    ]


def checar_frases_repetidas(doc: pm.Documento, limiar: float = 0.8, minimo_palavras: int = 12) -> list[Achado]:
    frases = [(b.numero, f) for b in doc.paragrafos for f in _frases(b.texto) if len(f.split()) >= minimo_palavras]
    out = []
    for i in range(len(frases)):
        for j in range(i + 1, len(frases)):
            (pa, fa), (pb, fb) = frases[i], frases[j]
            if pa == pb:
                continue
            sm = difflib.SequenceMatcher(None, fa, fb, autojunk=False)
            if sm.real_quick_ratio() < limiar or sm.quick_ratio() < limiar:
                continue
            r = sm.ratio()
            if r >= limiar:
                out.append(Achado("alerta", "frase_repetida", pb, f"frase {r:.0%} igual a uma do parágrafo {pa}: «{fb[:90]}…»"))
    return out


def checar_epistemico(doc: pm.Documento) -> list[Achado]:
    out = []
    for b in doc.paragrafos:
        for f in _frases(b.texto):
            if NAO_VERIFICADO_RE.search(f):
                out.append(Achado("alerta", "nao_verificado", b.numero, f"afirmação de não verificação: conferir se ainda é verdade: «{f[:90]}…»"))
            if INEXISTENCIA_RE.search(f) and re.search(r"\barts?\.", f):
                out.append(Achado("info", "inexistencia", b.numero, f"afirma inexistência ou alcance de dispositivo: conferir no texto integral: «{f[:90]}…»"))
            if CERTEZA_RE.search(f):
                out.append(Achado("info", "calibracao", b.numero, f"certeza enfática: conferir se o suporte basta: «{f[:90]}…»"))
            if PREVISAO_RE.search(f) and PREVISAO_VERBO_RE.search(f) and not CAUTELA_RE.search(f):
                out.append(Achado("alerta", "calibracao", b.numero, f"previsão de prazo afirmada como certa: rotular como estimativa: «{f[:90]}…»"))
    return out


def checar_travados(doc: pm.Documento, travados: list[dict]) -> list[Achado]:
    out = []
    numeros = doc.por_numero()
    for t in travados:
        texto = t["texto"]
        rotulo = t.get("id") or texto[:40]
        if texto not in doc.bruto:
            out.append(Achado("bloqueante", "travado", t.get("paragrafo"), f'trecho travado "{rotulo}" foi alterado ou removido'))
        elif t.get("paragrafo") and texto not in numeros.get(t["paragrafo"], ""):
            out.append(Achado("alerta", "travado", t.get("paragrafo"), f'trecho travado "{rotulo}" mudou de parágrafo'))
    return out


def _conta(termo: str, texto: str) -> int:
    t = re.escape(termo)
    padrao = rf"(?<!\w){t}\w*" if termo.endswith("ad") else rf"(?<!\w){t}(?!\w)"
    return len(re.findall(padrao, texto.lower()))


def _ngramas(palavras_: list[str], n: int = 4) -> set[tuple[str, ...]]:
    return {tuple(palavras_[i:i + n]) for i in range(len(palavras_) - n + 1)}


def _palavras_norm(texto: str) -> list[str]:
    return re.findall(r"\w+", pm.sem_negrito(texto).lower())


CITACAO_SIMBOLOS = {"§§": r"§§", "§": r"(?<!§)§(?!§)", "nº": r"\bn[º°]", "art.": r"\bart\.", "arts.": r"\barts\.", "inciso romano": r"\b[IVXL]+\b(?=,| e |\))"}


def checar_simbolos(antigo: str, novo: str, numero: int) -> list[Achado]:
    """Símbolos de citação que somem sem a citação sumir: ex.: "art. 25, §§ 2º e 3º" virar "art. 25, 2º e 3º"."""
    perdas = []
    for nome, rx in CITACAO_SIMBOLOS.items():
        a, b = len(re.findall(rx, antigo)), len(re.findall(rx, novo))
        if b < a:
            perdas.append(f"«{nome}» {a}→{b}")
    if perdas:
        return [Achado("alerta", "citacao", numero, "símbolos de citação a menos na nova versão: " + ", ".join(perdas)
                       + " — conferir se a citação legal ficou íntegra")]
    return []


def checar_alcance(antigo: str, novo: str, numero: int) -> list[Achado]:
    out = []
    mudancas = []
    for termo in ALCANCE_TERMOS:
        a, b = _conta(termo, antigo), _conta(termo, novo)
        if a != b:
            mudancas.append(f"«{termo}» {'acrescentado' if b > a else 'retirado'}")
    if mudancas:
        out.append(Achado("alerta", "alcance", numero, "mudança de alcance a conferir no mérito: " + ", ".join(mudancas)))
    perdidas = [t for t in RESSALVA_TERMOS if _conta(t, novo) < _conta(t, antigo)]
    if perdidas:
        out.append(Achado("alerta", "ressalva", numero, f"ressalva possivelmente perdida ({', '.join(perdidas)}): conferir se a "
                                                        "reescrita manteve a condição ou exceção"))
    return out


def checar_cobertura(anterior: pm.Documento, doc: pm.Documento, numeros_antigos: list[int], limiar: float = 0.5) -> list[Achado]:
    """Frases da versão anterior cujo conteúdo não reaparece na nova (4-gramas): reformuladas ou evaporadas."""
    novos = _ngramas(_palavras_norm(" ".join(b.texto for b in doc.paragrafos)))
    antigos = anterior.por_numero()
    out = []
    for n in numeros_antigos:
        for f in _frases(antigos.get(n, "")):
            ws = _palavras_norm(f)
            if len(ws) < 8:
                continue
            gs = _ngramas(ws)
            cobertura = len(gs & novos) / len(gs)
            if cobertura < limiar:
                out.append(Achado("alerta", "cobertura", n, f"frase do antigo parágrafo {n} com {cobertura:.0%} de correspondência "
                                                            f"na nova versão — reformulada ou evaporou: «{f[:90]}…»"))
    return out


def checar_renumeracao(doc: pm.Documento, anterior: pm.Documento, revisadas: set[int] | None = None) -> list[Achado]:
    mapa = pm.alinhar_paragrafos(anterior, doc)
    inverso = {v: k for k, v in mapa.items()}
    antigos = anterior.por_numero()
    out = []
    alterados_antigos: list[int] = []
    mudou = any(k != v for k, v in mapa.items())
    for b in doc.paragrafos:
        velho = inverso.get(b.numero)
        if velho is None:
            out.append(Achado("info", "rescan", b.numero, "parágrafo novo: varrer contra repetição e contradição"))
            continue
        if antigos[velho] != b.texto:
            out.append(Achado("info", "rescan", b.numero, f"parágrafo alterado (era o {velho}): varrer contra repetição e contradição"))
            out += checar_alcance(antigos[velho], b.texto, b.numero)
            out += checar_simbolos(antigos[velho], b.texto, b.numero)
            alterados_antigos.append(velho)
        if not mudou or doc.numeracao != "explicita" or anterior.numeracao != "explicita":
            continue
        rem_velhas = [n for _, ns in pm.remissoes(antigos[velho]) for n in ns]
        rem_novas = [n for _, ns in pm.remissoes(b.texto) for n in ns]
        esperadas = [mapa.get(n, n) for n in rem_velhas]
        if rem_velhas and len(rem_velhas) == len(rem_novas) and esperadas != rem_novas and b.numero in (revisadas or set()):
            out.append(Achado("info", "renumeracao", b.numero,
                              f"remissões {rem_novas} revisadas manualmente (o mapa automático daria {esperadas})"))
        elif rem_velhas and len(rem_velhas) == len(rem_novas) and esperadas != rem_novas:
            out.append(Achado(
                "bloqueante", "renumeracao", b.numero,
                f"remissões {rem_novas} deveriam ser {esperadas} após a renumeração (eram {rem_velhas} no parágrafo {velho})",
            ))
    suprimidos = [n for n in antigos if n not in mapa]
    for n in suprimidos:
        out.append(Achado("info", "rescan", None, f"parágrafo {n} da versão anterior sem correspondente na nova"))
    out += checar_cobertura(anterior, doc, alterados_antigos + suprimidos)
    return out


def contar_paginas_pdf(path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page(?!s)", path.read_bytes()))


def auditar(doc: pm.Documento, cfg: dict, anterior: pm.Documento | None = None, travados: list[dict] | None = None,
            proibidos: list[str] | None = None, pdf: Path | None = None, max_paginas: int | None = None,
            revisadas: set[int] | None = None) -> list[Achado]:
    fecho = cfg.get("fecho")
    achados = []
    achados += checar_numeracao(doc)
    achados += checar_palavras(doc, cfg.get("max_palavras"))
    achados += checar_fecho(doc, fecho)
    achados += checar_remissoes(doc)
    achados += checar_marcadores(doc, fecho, proibidos or [])
    achados += checar_conclusao(doc, cfg.get("rotulos_conclusao", []))
    achados += checar_assinatura(doc, fecho, cfg.get("assinatura", []))
    achados += checar_julgados_repetidos(doc)
    achados += checar_frases_repetidas(doc)
    achados += checar_epistemico(doc)
    if travados:
        achados += checar_travados(doc, travados)
    if anterior is not None:
        achados += checar_renumeracao(doc, anterior, revisadas)
    if pdf is not None and max_paginas:
        n = contar_paginas_pdf(pdf)
        if n > max_paginas:
            achados.append(Achado("bloqueante", "paginas", None, f"{n} páginas (máximo {max_paginas})"))
    return achados


ORDEM = {"bloqueante": 0, "alerta": 1, "info": 2}


def relatorio(path: Path, doc: pm.Documento, achados: list[Achado]) -> str:
    pars = doc.paragrafos
    maior = max(pars, key=lambda b: pm.palavras(b.texto)) if pars else None
    linhas = [
        f"PRÉ-AUDITORIA — {path.name}",
        f"sha256: {doc.sha256}",
        f"parágrafos: {len(pars)} | remissões internas: {sum(len(pm.remissoes(b.texto)) for b in pars)}"
        + (f" | maior: {maior.numero} ({pm.palavras(maior.texto)} palavras)" if maior else ""),
        "",
    ]
    for a in sorted(achados, key=lambda a: (ORDEM[a.severidade], a.paragrafo or 0)):
        onde = f"§ {a.paragrafo}" if a.paragrafo else "—"
        linhas.append(f"[{a.severidade.upper()}] {a.regra} {onde}: {a.mensagem}")
    b = sum(a.severidade == "bloqueante" for a in achados)
    al = sum(a.severidade == "alerta" for a in achados)
    linhas += ["", f"Resultado: {'REPROVADA' if b else 'APROVADA'} ({b} bloqueantes, {al} alertas, {len(achados) - b - al} informativos)"]
    return "\n".join(linhas)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("minuta", type=Path)
    p.add_argument("--perfil", choices=sorted(PERFIS), default="generico")
    p.add_argument("--max-palavras", type=int, help="sobrepõe o limite do perfil")
    p.add_argument("--fecho", help="sobrepõe o fecho do perfil")
    p.add_argument("--anterior", type=Path, help="versão anterior, para checar renumeração e listar o que varrer")
    p.add_argument("--remissoes-revisadas", default="",
                   help="parágrafos (na numeração nova) cujas remissões foram alteradas de propósito, além da renumeração")
    p.add_argument("--travados", type=Path, help='JSON: [{"id": ..., "paragrafo": N, "texto": "..."}]')
    p.add_argument("--proibido", action="append", default=[], help="termo proibido (repetível)")
    p.add_argument("--pdf", type=Path)
    p.add_argument("--max-paginas", type=int)
    p.add_argument("--json", type=Path, help="grava os achados em JSON")
    p.add_argument("--sem-info", action="store_true", help="omite os achados informativos do relatório")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.minuta.exists():
        print(f"arquivo não encontrado: {args.minuta}", file=sys.stderr)
        return 2
    cfg = dict(PERFIS[args.perfil])
    if args.max_palavras is not None:
        cfg["max_palavras"] = args.max_palavras
    if args.fecho is not None:
        cfg["fecho"] = args.fecho
    doc = pm.ler(args.minuta)
    anterior = pm.ler(args.anterior) if args.anterior else None
    travados = json.loads(args.travados.read_text(encoding="utf-8")) if args.travados else None
    revisadas = {int(x) for x in args.remissoes_revisadas.split(",") if x.strip()}
    achados = auditar(doc, cfg, anterior, travados, args.proibido, args.pdf, args.max_paginas, revisadas)
    mostrar = [a for a in achados if not (args.sem_info and a.severidade == "info")]
    print(relatorio(args.minuta, doc, mostrar))
    if args.json:
        args.json.write_text(json.dumps({
            "arquivo": str(args.minuta),
            "sha256": doc.sha256,
            "perfil": args.perfil,
            "aprovada": not any(a.severidade == "bloqueante" for a in achados),
            "achados": [asdict(a) for a in achados],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if any(a.severidade == "bloqueante" for a in achados) else 0


if __name__ == "__main__":
    sys.exit(main())
