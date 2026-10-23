#!/usr/bin/env python3
"""Motor mecânico do modo ``emendas_consensuais_v2``.

Os agentes leem a mesma minuta congelada, propõem emendas pontuais às cegas,
votam às cegas nas emendas uns dos outros e só entram no texto as emendas
aprovadas pela regra escolhida. Votar ``aceitar`` é aderir, ao mesmo tempo, ao
diagnóstico, à redação exata e à classificação da emenda. O script não julga
mérito: valida, apura e aplica. Cada subcomando grava JSON para o seguinte e
recusa material de outra versão da minuta (hash divergente).

Fluxo::

    emendas.py validar  --minuta v.md --propostas gemini.json codex.json [--fontes fontes/] --saida validadas.json
    emendas.py cedula   --validadas validadas.json --saida cedula.md
    emendas.py apurar   --validadas validadas.json --votos voto_*.json --votantes gemini,codex,claude --saida apuracao.json
    emendas.py segunda-rodada --apuracao apuracao.json --saida validadas2.json   # debate: dissenso e ajustes divergentes
    emendas.py aplicar  --minuta v.md --apuracao apuracao.json [apuracao2.json] --saida v_next.md --relatorio emendas.md
    emendas.py conjunto --minuta-base v.md --minuta-nova v_next.md --apuracao apuracao.json --saida cedula_conjunto.md
    emendas.py confirmar --minuta-base v.md --minuta-nova v_next.md --apuracao apuracao.json --votos conj_*.json --votantes gemini,codex,claude --saida confirmacao.json

A versão nova só substitui a base depois de ``confirmar`` aprovar a adesão ao
conjunto: duas emendas aceitáveis isoladamente podem conflitar quando
combinadas. Contratos de entrada: ``emendas_schema.json``.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import sys
import unicodedata
from fractions import Fraction
from pathlib import Path
from typing import Any

CONTRATO = "emendas_consensuais_v2"
TIPOS = ("correcao", "precisao", "fonte", "remissao", "redacao", "corte", "acrescimo")
# Classificações por tipo de trabalho jurídico. "correcao_necessaria" e "redacional" existem em todos: a primeira exige
# justificativa de obrigatoriedade; a segunda não conta como melhoria material. A receita do domínio escolhe o conjunto.
CLASSIFICACOES_POR_TIPO = {
    "generico": ("correcao_necessaria", "aperfeicoamento_material", "recomendacao_facultativa", "providencia_externa", "redacional"),
    "parecer": ("correcao_necessaria", "obrigacao_incidente", "recomendacao_facultativa", "providencia_externa", "redacional"),
    "peca": ("correcao_necessaria", "reforco_argumentativo", "risco_estrategico", "providencia_externa", "redacional"),
    "decisao": ("correcao_necessaria", "aperfeicoamento_fundamentacao", "recomendacao_facultativa", "providencia_externa", "redacional"),
}
CLASSIFICACOES = CLASSIFICACOES_POR_TIPO["generico"]
NIVEIS_FONTE = ("integral_conferida", "reproducao_literal", "minuta_atual", "remissao", "ausente_no_dossie")
NIVEIS_SUFICIENTES = ("integral_conferida", "reproducao_literal", "minuta_atual")
VOTOS = ("aceitar", "ajustar", "rejeitar")
PAR_RE = re.compile(r"^(\d+)\. ", re.M)
APROVADAS = ("aprovada", "aprovada_com_ajuste")
# classificações que, mesmo aprovadas pelas cadeiras, só entram com autorização expressa do usuário (estratégia da parte)
RESERVADAS_AO_HUMANO = ("risco_estrategico",)
EFEITOS_RESERVADOS = ("renuncia_direito", "concessao_negocial", "reconhecimento_fato", "mudanca_estrategia", "acordo", "ato_externo")
CAMPOS_JUSTIFICATIVA = ("defeito", "suporte", "consequencia", "insuficiencia_aplicacao_direta")
CAMPOS_VARIANTE = ("tipo", "classificacao", "fundamento", "justificativa_obrigatoriedade",
                   "fonte_ref", "fonte_literal", "nivel_fonte", "efeitos_reservados")


# ---------------------------------------------------------------- utilidades

def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def ler_json(path: Path | str) -> Any:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def gravar_json(path: Path | str, dados: Any) -> None:
    Path(path).write_text(json.dumps(dados, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def palavras(texto: str) -> int:
    return len(texto.replace("**", "").split())


def normalizar(texto: str) -> str:
    texto = unicodedata.normalize("NFC", texto).replace("“", '"').replace("”", '"').replace("’", "'")
    return re.sub(r"\s+", " ", texto).strip().lower()


def limites_paragrafos(minuta: str) -> list[tuple[int, int, int]]:
    """(número, início, fim) de cada parágrafo, uma linha por parágrafo.

    Usa a numeração ``N. texto`` quando o documento a tem (parecer, voto, muitas petições). Sem ela, numera
    implicitamente, em ordem, as linhas de texto que não são títulos nem marcadores de cabeçalho e assinatura.
    """
    linhas = []
    pos = 0
    for linha in minuta.split("\n"):
        s = linha.strip()
        if s and not s.startswith(("#", "@")):
            ini = pos + linha.index(s[0])
            marca = PAR_RE.match(s)
            linhas.append((int(marca.group(1)) if marca else None, ini, pos + len(linha)))
        pos += len(linha) + 1
    # Numeração de pedidos/listas não transforma a narrativa em conteúdo invisível.
    explicita = bool(linhas) and all(n is not None for n, _, _ in linhas)
    return [(n if explicita else i, ini, fim) for i, (n, ini, fim) in enumerate(linhas, 1)]


def _suporte_hash(e: dict) -> str:
    return sha256_texto(json.dumps({k: e.get(k) for k in ("fonte_ref", "fonte_literal", "nivel_fonte")},
                                  sort_keys=True, ensure_ascii=False))


def _suporte_conferido(e: dict, minuta: str, fontes: str | None) -> bool:
    literal = e.get("fonte_literal")
    if not isinstance(literal, str) or not literal.strip() or not str(e.get("fonte_ref", "")).strip():
        return False
    if e.get("nivel_fonte") == "minuta_atual":
        return normalizar(literal) in normalizar(minuta)
    return e.get("nivel_fonte") in NIVEIS_SUFICIENTES and fontes is not None and normalizar(literal) in fontes


def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto.lower()) if unicodedata.category(c) != "Mn")


def _sinais_reserva(texto: str) -> set[str]:
    """Sinais conservadores de nova decisão; não pretende interpretar todo negócio jurídico."""
    texto = _sem_acentos(texto)
    padroes = {
        "renuncia_direito": r"\b(?:renunci\w*|abre mao|abrir mao|perdoa\w*)\b[^.;\n]{0,100}",
        "reconhecimento_fato": r"\b(?:confess\w*|reconhec\w*)\s+(?:o |a |os |as |um |uma )?(?:fato|divida|debito)\w*\b[^.;\n]{0,80}",
        "acordo": r"\b(?:transig\w*|transacion\w*|celebr\w*\s+(?:o |um )?acordo)\b[^.;\n]{0,80}",
    }
    sinais = set()
    for efeito, rx in padroes.items():
        for m in re.finditer(rx, texto):
            antes = texto[max(0, m.start() - 65):m.start()]
            if re.search(r"\b(?:nao|jamais|sem|vedad[ao]|proibid[ao])(?:\s+\w+){0,4}\s*$", antes):
                continue
            sinais.add(efeito + ":" + m.group(0).strip())
    return sinais


def efeitos_reservados(e: dict) -> list[str]:
    declarados = e.get("efeitos_reservados") or []
    if not isinstance(declarados, list):
        declarados = []  # O validador registra o erro; a detecção não aborta.
    efeitos = {x for x in declarados if isinstance(x, str) and x in EFEITOS_RESERVADOS}
    novos = _sinais_reserva(str(e.get("texto_aprovado", e.get("proposta", "")))) - _sinais_reserva(str(e.get("trecho", "")))
    efeitos.update(s.split(":", 1)[0] for s in novos)
    return sorted(efeitos)


def _requisitos(e: dict, tipo_documento: str, minuta: str, fontes: str | None,
                exigir_fonte: tuple[str, ...], suporte_anterior: str | None = None) -> list[str]:
    motivos = []
    for campo in ("trecho", "proposta"):
        if not isinstance(e.get(campo), str):
            motivos.append(f"{campo} deve ser texto")
    if e.get("tipo") not in TIPOS:
        motivos.append(f"tipo inválido: {e.get('tipo')!r}")
    if e.get("classificacao") not in CLASSIFICACOES_POR_TIPO[tipo_documento]:
        motivos.append(f"classificação ausente ou inválida para {tipo_documento}: {e.get('classificacao')!r}")
    if e.get("classificacao") == "correcao_necessaria":
        j = e.get("justificativa_obrigatoriedade")
        if not isinstance(j, dict) or any(not isinstance(j.get(k), str) or not j[k].strip() for k in CAMPOS_JUSTIFICATIVA):
            motivos.append("correção necessária sem justificativa de obrigatoriedade estruturada: " + ", ".join(CAMPOS_JUSTIFICATIVA))
    if not isinstance(e.get("fundamento"), str) or not e["fundamento"].strip():
        motivos.append("fundamento ausente")
    declarados = e.get("efeitos_reservados", [])
    if not isinstance(declarados, list) or any(x not in EFEITOS_RESERVADOS for x in declarados):
        motivos.append("efeitos reservados inválidos")
    nivel = e.get("nivel_fonte")
    if nivel is not None and nivel not in NIVEIS_FONTE:
        motivos.append(f"nível de fonte inválido: {nivel!r}")
    # Materialidade é transversal: chamar mérito de 'redacao' não dispensa suporte.
    precisa = e.get("classificacao") != "redacional" or e.get("tipo") in exigir_fonte or bool(efeitos_reservados(e))
    if precisa:
        literal = e.get("fonte_literal", "")
        if nivel not in NIVEIS_SUFICIENTES:
            motivos.append(f"fonte com nível '{nivel}': não sustenta emenda de mérito; conferir o suporte e repropor")
        if not isinstance(literal, str) or not literal.strip() or not str(e.get("fonte_ref", "")).strip():
            motivos.append("emenda de mérito sem fonte literal e referência específica")
        elif nivel == "minuta_atual":
            if normalizar(literal) not in normalizar(minuta):
                motivos.append("fonte literal não localizada na minuta-base")
        elif fontes is not None:
            if normalizar(literal) not in fontes:
                motivos.append("fonte literal não localizada nas fontes fornecidas")
        elif suporte_anterior != _suporte_hash(e):
            motivos.append("corpus de fontes não recebido; fornecer --fontes para conferir a fonte literal")
    return motivos


def _chave_variante(e: dict) -> str:
    # A adesão é à redação e aos metadados exatos, sem fundir variantes só por caixa/espaços.
    return json.dumps({"texto": e["proposta"], **{k: e.get(k) for k in CAMPOS_VARIANTE}}, sort_keys=True, ensure_ascii=False)


def _contexto(registro: dict) -> dict:
    ctx = registro.get("contexto_validacao")
    if registro.get("contrato") != CONTRATO or not isinstance(ctx, dict):
        raise SystemExit("recibo legado ou sem contexto: revalidar a minuta no contrato " + CONTRATO)
    if sha256_texto(ctx.get("minuta", "")) != registro["hash_minuta"]:
        raise SystemExit("contexto de validação pertence a outra minuta")
    return ctx


def corpo_paragrafo(minuta: str, ini: int, fim: int) -> str:
    return PAR_RE.sub("", minuta[ini:fim], count=1)


def paragrafo_em(limites: list[tuple[int, int, int]], pos: int) -> tuple[int, int, int] | None:
    for lim in limites:
        if lim[1] <= pos < lim[2]:
            return lim
    return None


def corpus_fontes(dirs: list[Path]) -> str:
    partes = []
    for d in dirs:
        arquivos = [d] if d.is_file() else sorted(p for p in d.rglob("*") if p.suffix.lower() in {".md", ".txt", ".html", ".htm"})
        for p in arquivos:
            try:
                txt = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if p.suffix.lower() in {".html", ".htm"}:
                txt = re.sub(r"<[^>]+>", " ", txt)
            partes.append(normalizar(txt))
    return "\n".join(partes)


def regra_atingida(sim: int, total: int, regra: str) -> bool:
    if total == 0:
        return False
    if regra == "unanimidade":
        return sim == total
    if regra == "maioria":
        return sim * 2 > total
    if regra.startswith("qualificada:"):
        return sim >= math.ceil(total * Fraction(regra.split(":", 1)[1]))
    raise SystemExit(f"regra desconhecida: {regra}")


def separar_votantes(lotes: list[dict], hash_minuta: str, exigidos: list[str] | None,
                     campo_hash: str = "hash_minuta", hash_extra: tuple[str, str] | None = None) -> tuple[list[str], dict[str, dict], list[dict]]:
    """Lotes válidos por votante, recusados e lista de votantes que contam no quórum.

    Com ``exigidos``, o quórum é a lista configurada: cadeira que não respondeu, respondeu sobre outra
    versão ou mandou lote vazio conta como abstenção, nunca como adesão.
    """
    validos: dict[str, dict] = {}
    recusados = []
    for lote in lotes:
        nome = lote.get("votante", "?")
        if lote.get(campo_hash) != hash_minuta:
            recusados.append({"votante": nome, "motivo": f"{campo_hash} divergente: voto sobre outra versão"})
        elif hash_extra and lote.get(hash_extra[0]) != hash_extra[1]:
            recusados.append({"votante": nome, "motivo": f"{hash_extra[0]} divergente: voto sobre outro resultado"})
        elif nome in validos:
            recusados.append({"votante": nome, "motivo": "votante repetido"})
        elif exigidos is not None and nome not in exigidos:
            recusados.append({"votante": nome, "motivo": "votante não previsto na configuração"})
        else:
            validos[nome] = lote
    quorum = list(exigidos) if exigidos is not None else list(validos)
    return quorum, validos, recusados


# ---------------------------------------------------------------- validar

def validar(minuta: str, lotes: list[dict], travados: list[dict] | None = None, fontes: str | None = None,
            max_palavras: int | None = None, exigir_fonte: tuple[str, ...] = ("correcao", "fonte"),
            tipo_documento: str = "generico") -> dict:
    if tipo_documento not in CLASSIFICACOES_POR_TIPO:
        raise SystemExit(f"tipo de documento desconhecido: {tipo_documento}; use {', '.join(CLASSIFICACOES_POR_TIPO)}")
    classificacoes = CLASSIFICACOES_POR_TIPO[tipo_documento]
    hash_minuta = sha256_texto(minuta)
    limites = limites_paragrafos(minuta)
    existentes = {n for n, _, _ in limites}
    travas = []
    for t in travados or []:
        i = minuta.find(t["texto"])
        if i >= 0:
            travas.append((i, i + len(t["texto"]), t.get("id") or t["texto"][:40]))

    emendas: list[dict] = []
    lotes_recusados = []
    for lote in lotes:
        autor = lote.get("autor", "?")
        if lote.get("hash_minuta") != hash_minuta:
            lotes_recusados.append({"autor": autor, "motivo": "hash_minuta divergente: propostas feitas sobre outra versão"})
            continue
        for p in lote.get("propostas", []):
            emendas.append({**p, "autores": [autor]})

    # convergência: a mesma emenda (trecho, redação e classificação) proposta por mais de um autor vira uma só
    unicas: list[dict] = []
    for e in emendas:
        igual = next((u for u in unicas if u["trecho"] == e["trecho"] and _chave_variante(u) == _chave_variante(e)), None)
        if igual:
            igual["autores"] += [a for a in e["autores"] if a not in igual["autores"]]
        else:
            unicas.append(e)

    for n, e in enumerate(unicas, start=1):
        e["id"] = f"E{n:02d}"
        motivos = _requisitos(e, tipo_documento, minuta, fontes, exigir_fonte)
        alertas = []
        trecho = e.get("trecho", "") if isinstance(e.get("trecho"), str) else ""
        ocorrencias = minuta.count(trecho) if trecho else 0
        if ocorrencias != 1:
            motivos.append("trecho não localizado literalmente na minuta" if ocorrencias == 0
                           else f"trecho ambíguo: ocorre {ocorrencias} vezes; ampliar o trecho")
        else:
            ini = minuta.index(trecho)
            e["inicio"], e["fim"] = ini, ini + len(trecho)
            lim = paragrafo_em(limites, ini)
            if lim is None:
                motivos.append("trecho fora de um parágrafo de texto; cabeçalhos e títulos exigem revisão própria")
            if lim and e["fim"] > lim[2]:
                motivos.append("trecho atravessa mais de um parágrafo")
            if lim:
                if e.get("paragrafo") not in (None, lim[0]):
                    motivos.append(f"trecho está no parágrafo {lim[0]}, não no {e['paragrafo']}")
                e["paragrafo"] = lim[0]
                novo_par = minuta[lim[1]:ini] + str(e["proposta"]) + minuta[e["fim"]:lim[2]]
                e["palavras_resultantes"] = palavras(corpo_paragrafo(novo_par, 0, len(novo_par)))
                if max_palavras and e["palavras_resultantes"] > max_palavras:
                    # outra emenda do mesmo parágrafo pode compensar; o limite é conferido de novo ao aplicar
                    alertas.append(f"isolada, deixa o parágrafo com {e['palavras_resultantes']} palavras (máximo {max_palavras})")
            for a, b, rotulo in travas:
                if ini < b and a < e["fim"]:
                    motivos.append(f'trecho travado "{rotulo}"')
        deps = e.get("dependencias") or []
        if not all(isinstance(d, int) for d in deps):
            motivos.append("dependências devem ser números de parágrafo")
        elif [d for d in deps if d not in existentes]:
            motivos.append(f"dependência em parágrafo inexistente: {[d for d in deps if d not in existentes]}")
        e["dependencias"] = [d for d in deps if isinstance(d, int) and d != e.get("paragrafo")]
        e["delta_palavras"] = palavras(str(e.get("proposta", ""))) - palavras(trecho)
        e["efeitos_reservados"] = efeitos_reservados(e)
        e["status"] = "invalida" if motivos else "valida"
        if not motivos and _suporte_conferido(e, minuta, fontes):
            e["suporte_verificado"] = _suporte_hash(e)
        e["motivos_invalidade"] = motivos
        e["alertas"] = alertas

    # emendas válidas sobre trechos sobrepostos formam um grupo de conflito: no máximo uma entra
    validas = [e for e in unicas if e["status"] == "valida"]
    grupo = 0
    for i, a in enumerate(validas):
        for b in validas[i + 1:]:
            if a["inicio"] < b["fim"] and b["inicio"] < a["fim"]:
                g = a.get("grupo_conflito") or b.get("grupo_conflito")
                if not g:
                    grupo += 1
                    g = f"C{grupo}"
                a["grupo_conflito"] = b["grupo_conflito"] = g

    return {
        "contrato": CONTRATO,
        "hash_minuta": hash_minuta,
        "rodada": 1,
        "tipo_documento": tipo_documento,
        "classificacoes": list(classificacoes),
        "contexto_validacao": {"minuta": minuta, "tipo_documento": tipo_documento,
                               "exigir_fonte": list(exigir_fonte),
                               "fontes_sha256": sha256_texto(fontes) if fontes is not None else None},
        "lotes_recusados": lotes_recusados,
        "emendas": unicas,
    }


# ---------------------------------------------------------------- cédula

def cedula(validadas: dict, semente: str | None = None, permitir_ajuste: bool | None = None) -> str:
    rodada = validadas.get("rodada", 1)
    if permitir_ajuste is None:
        permitir_ajuste = rodada < 2  # a rodada de debate só escolhe entre variantes
    emendas = [e for e in validadas["emendas"] if e["status"] == "valida"]
    ordem = list(emendas)
    random.Random(semente or validadas["hash_minuta"]).shuffle(ordem)
    ordem.sort(key=lambda e: e.get("paragrafo") or 0)  # embaralha empates e mantém a leitura em ordem de parágrafo
    votos_permitidos = " | ".join(VOTOS if permitir_ajuste else ("aceitar", "rejeitar"))
    linhas = [
        f"# Cédula de votação — {CONTRATO} — rodada {rodada}",
        "",
        f"HASH_MINUTA: {validadas['hash_minuta']}",
        "",
        "Vote em cada emenda abaixo sem saber quem a propôs. Leia a minuta integral e confira o fundamento na fonte "
        "antes de votar. \"aceitar\" significa aderir ao diagnóstico, à redação exata e à classificação; concordar só "
        "com o diagnóstico não basta. Rejeite a emenda que piore o texto, introduza erro, dependa de fonte não conferida, "
        "exceda o suporte ou esteja mal classificada. ",
    ]
    if permitir_ajuste:
        linhas[-1] += ("Use \"ajustar\" quando concordar com o diagnóstico e tiver redação ou classificação melhor: o campo "
                       "\"ajuste\" substitui integralmente o trecho atual e o campo \"classificacao\" troca a classificação. "
                       "A variante deve fornecer sua justificativa estruturada, suporte e efeitos reservados quando alterados; "
                       "todos serão revalidados antes da apuração.")
    else:
        linhas[-1] += ("Esta é a rodada de debate: abaixo de cada emenda estão os motivos da rodada anterior, sem autoria. "
                       "As variantes de um mesmo trecho concorrem entre si e entra no máximo uma. Para mudar a posição que "
                       "você tomou na rodada anterior, preencha \"razao_nova\" com o argumento ou a fonte que o convenceu; "
                       "mudança sem razão nova conta como abstenção.")
    if validadas.get("classificacoes"):
        linhas += ["", f"Classificações admitidas ({validadas.get('tipo_documento', 'generico')}): {', '.join(validadas['classificacoes'])}."]
    linhas.append("")
    for e in ordem:
        linhas += [
            f"## {e['id']} — parágrafo {e.get('paragrafo', '—')} — {e['tipo']} — {e.get('classificacao', 's/classificação')}"
            + (f" — conflita com outras do grupo {e['grupo_conflito']}" if e.get("grupo_conflito") else ""),
            "",
            f"**Trecho atual:** {e['trecho']}",
            "",
            f"**Proposta:** {e['proposta']}",
            "",
            f"**Fundamento:** {e.get('fundamento', '')}",
        ]
        if e.get("justificativa_obrigatoriedade"):
            linhas.append(f"\n**Por que é obrigatória:** {e['justificativa_obrigatoriedade']}")
        if e.get("fonte_literal"):
            linhas.append(f"\n**Fonte literal ({e.get('fonte_ref', 's/ref.')}; {e.get('nivel_fonte', 'nível não informado')}):** {e['fonte_literal']}")
        if e.get("dependencias"):
            linhas.append(f"\n**Depende de ajuste nos parágrafos:** {', '.join(map(str, e['dependencias']))}")
        if efeitos_reservados(e):
            linhas.append(f"\n**Decisões reservadas ao responsável:** {', '.join(efeitos_reservados(e))}; aprovação dos agentes não as autoriza.")
        linhas.append(f"\n**Variação de palavras:** {e['delta_palavras']:+d}")
        if e.get("motivos_anteriores"):
            linhas += ["", "**Motivos da rodada anterior:**", *[f"- {m}" for m in e["motivos_anteriores"]]]
        linhas.append("")
    extra = {"ajuste": "", "classificacao": ""} if permitir_ajuste else {"razao_nova": ""}
    modelo = {
        "votante": "<seu identificador>",
        "hash_minuta": validadas["hash_minuta"],
        "votos": [{"id": e["id"], "voto": "aceitar", "motivo": "...", **extra} for e in ordem],
    }
    linhas += [
        "## Resposta",
        "",
        f"Responda só com o JSON abaixo, com um voto por emenda ({votos_permitidos}) e motivo curto em cada um. "
        "O campo hash_minuta deve repetir exatamente o hash acima. Emenda sem voto conta como abstenção.",
        "",
        "```json",
        json.dumps(modelo, ensure_ascii=False, indent=2),
        "```",
    ]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- apurar

def _posicao(voto: str) -> str:
    return {"aceitar": "favor", "ajustar": "favor", "rejeitar": "contra"}.get(voto, "abstencao")


def apurar(validadas: dict, lotes_votos: list[dict], regra: str = "unanimidade", exigidos: list[str] | None = None,
           fontes: str | None = None) -> dict:
    ctx = _contexto(validadas)
    if fontes is not None and sha256_texto(fontes) != ctx.get("fontes_sha256"):
        raise SystemExit("fontes divergentes: revalidar e compartilhar o novo pacote antes de votar")
    hash_minuta = validadas["hash_minuta"]
    rodada = validadas.get("rodada", 1)
    quorum, validos, recusados = separar_votantes(lotes_votos, hash_minuta, exigidos)
    total = len(quorum)
    resultado = []
    for e in validadas["emendas"]:
        r = {k: e[k] for k in e if k not in ("status", "motivos_invalidade", "alertas")}
        if e["status"] != "valida":
            resultado.append({**r, "decisao": "invalida", "motivos": e["motivos_invalidade"], "votos": []})
            continue
        classe = e.get("classificacao")
        votos = []
        candidatos = {}
        for nome in quorum:
            lote = validos.get(nome)
            v = next((v for v in (lote or {}).get("votos", []) if v.get("id") == e["id"]), None)
            if lote is None:
                v = {"voto": "abstencao", "motivo": "cadeira não respondeu ou respondeu sobre outra versão"}
            elif v is None or v.get("voto") not in VOTOS:
                v = {"voto": "abstencao", "motivo": "sem voto válido"}
            elif (v["voto"] == "ajustar" and v.get("classificacao")
                  and v["classificacao"] not in (validadas.get("classificacoes") or CLASSIFICACOES)):
                v = {"voto": "abstencao", "motivo": f"classificação de ajuste inválida: {v['classificacao']!r}"}
            elif rodada >= 2 and v["voto"] == "ajustar":
                v = {"voto": "abstencao", "motivo": "ajuste não é admitido na rodada de debate"}
            elif rodada >= 2:
                antes = e.get("posicoes_anteriores", {}).get(nome)
                if antes in ("favor", "contra") and _posicao(v["voto"]) != antes and not str(v.get("razao_nova", "")).strip():
                    v = {"voto": "abstencao", "motivo": f"mudou de posição ({antes} → {_posicao(v['voto'])}) sem razão nova"}
            if v["voto"] in ("aceitar", "ajustar"):
                variante = {**e}
                if v["voto"] == "ajustar":
                    variante.update({k: v[k] for k in CAMPOS_VARIANTE if k in v
                                     and not (k in ("tipo", "classificacao") and not v[k])})
                    variante["proposta"] = v["ajuste"] if "ajuste" in v else e["proposta"]
                falhas = _requisitos(variante, ctx["tipo_documento"], ctx["minuta"], fontes,
                                      tuple(ctx["exigir_fonte"]), e.get("suporte_verificado"))
                if falhas:
                    v = {"voto": "abstencao", "motivo": "variante inválida: " + "; ".join(falhas)}
                else:
                    variante["efeitos_reservados"] = efeitos_reservados(variante)
                    if _suporte_conferido(variante, ctx["minuta"], fontes) or e.get("suporte_verificado") == _suporte_hash(variante):
                        variante["suporte_verificado"] = _suporte_hash(variante)
                    else:
                        variante.pop("suporte_verificado", None)
                    candidatos[nome] = variante
            votos.append({"votante": nome, **{k: v.get(k) for k in ("voto", "ajuste", "motivo", "razao_nova", *CAMPOS_VARIANTE)
                                              if v.get(k) not in (None, "")}})
        # cada variante (texto + classificação) precisa atingir a regra por si: quem aceitou a original não aderiu ao ajuste
        original = _chave_variante(e)
        contagem = {original: 0}
        textos = {original: {"texto": e["proposta"], **{k: e.get(k) for k in CAMPOS_VARIANTE},
                             "suporte_verificado": e.get("suporte_verificado")}}
        for v in votos:
            if v["voto"] in ("aceitar", "ajustar"):
                candidato = candidatos[v["votante"]]
                chave = _chave_variante(candidato)
                contagem[chave] = contagem.get(chave, 0) + 1
                textos.setdefault(chave, {"texto": candidato["proposta"], **{k: candidato.get(k) for k in CAMPOS_VARIANTE},
                                          "suporte_verificado": candidato.get("suporte_verificado")})
        favor = sum(v["voto"] in ("aceitar", "ajustar") for v in votos)
        r["votos"] = votos
        r["placar"] = {"aceitar": sum(v["voto"] == "aceitar" for v in votos), "ajustar": sum(v["voto"] == "ajustar" for v in votos),
                       "rejeitar": sum(v["voto"] == "rejeitar" for v in votos),
                       "abstencao": sum(v["voto"] == "abstencao" for v in votos), "votantes": total}
        vencedora = next((k for k, n in contagem.items() if regra_atingida(n, total, regra)), None)
        if vencedora is not None:
            r["decisao"] = "aprovada" if vencedora == original else "aprovada_com_ajuste"
            r["texto_aprovado"] = textos[vencedora]["texto"]
            r["classificacao_aprovada"] = textos[vencedora]["classificacao"]
            for campo in CAMPOS_VARIANTE:
                if campo != "classificacao":
                    r[campo] = textos[vencedora].get(campo)
            r["suporte_verificado"] = textos[vencedora].get("suporte_verificado")
        elif regra_atingida(favor, total, regra):
            r["decisao"] = "segunda_rodada"
        elif favor == 0:
            r["decisao"] = "rejeitada"
        else:
            r["decisao"] = "dissenso"
        if r["decisao"] in ("segunda_rodada", "dissenso"):
            r["variantes"] = list(textos.values())
        resultado.append(r)

    # no grupo de conflito, entra só a aprovada com mais aceites; empate vai ao humano
    grupos: dict[str, list[dict]] = {}
    for r in resultado:
        if r.get("grupo_conflito") and r["decisao"] in APROVADAS:
            grupos.setdefault(r["grupo_conflito"], []).append(r)
    for g, rs in grupos.items():
        if len(rs) < 2:
            continue
        rs.sort(key=lambda r: (r["placar"]["aceitar"], r["placar"]["ajustar"]), reverse=True)
        empate = (rs[0]["placar"]["aceitar"], rs[0]["placar"]["ajustar"]) == (rs[1]["placar"]["aceitar"], rs[1]["placar"]["ajustar"])
        for r in (rs if empate else rs[1:]):
            r["decisao"] = "dissenso" if empate else "preterida"
            r["motivo_decisao"] = f"conflito no grupo {g}" + (" com empate" if empate else f" com {rs[0]['id']}, mais votada")
            r.pop("texto_aprovado", None)
            r.pop("classificacao_aprovada", None)
    # sem consenso próprio e vencida por concorrente aprovada no mesmo trecho: não sobe ao humano
    vencedoras = {r["grupo_conflito"]: r["id"] for r in resultado if r.get("grupo_conflito") and r["decisao"] in APROVADAS}
    for r in resultado:
        g = r.get("grupo_conflito")
        if g in vencedoras and r["decisao"] in ("dissenso", "segunda_rodada") and "motivo_decisao" not in r:
            r["decisao"] = "preterida"
            r["motivo_decisao"] = f"conflito no grupo {g} com {vencedoras[g]}, aprovada"

    return {
        "contrato": CONTRATO,
        "hash_minuta": hash_minuta,
        "regra": regra,
        "rodada": rodada,
        "tipo_documento": validadas.get("tipo_documento", "generico"),
        "classificacoes": validadas.get("classificacoes"),
        "contexto_validacao": ctx,
        "votantes": quorum,
        "votantes_responderam": [n for n in quorum if n in validos],
        "votantes_recusados": recusados,
        "emendas": resultado,
    }


def segunda_rodada(apuracao: dict, semente: str | None = None) -> dict:
    """Rodada única de debate: dissenso e ajustes divergentes voltam como variantes concorrentes.

    Cada votante vê os motivos da rodada anterior, sem autoria, e vota só aceitar ou rejeitar. Mudar a posição
    anterior exige ``razao_nova``; sem ela, o voto conta como abstenção.
    """
    ctx = _contexto(apuracao)
    if apuracao.get("rodada", 1) >= 2:
        raise SystemExit("o modo admite uma única rodada de debate; o que não fechou vai ao humano como dissenso")
    emendas = []
    for r in apuracao["emendas"]:
        if r["decisao"] not in ("segunda_rodada", "dissenso"):
            continue
        motivos = [v["motivo"] for v in r.get("votos", []) if v.get("motivo") and v["voto"] != "abstencao"]
        random.Random(semente or apuracao["hash_minuta"] + r["id"]).shuffle(motivos)
        for k, var in enumerate(r["variantes"]):
            chave = _chave_variante({**var, "proposta": var["texto"]})
            posicoes = {}
            for v in r.get("votos", []):
                if v["voto"] == "rejeitar":
                    posicoes[v["votante"]] = "contra"
                elif v["voto"] == "aceitar" and k == 0:
                    posicoes[v["votante"]] = "favor"
                elif v["voto"] == "ajustar":
                    candidato = {**r, **{c: v[c] for c in CAMPOS_VARIANTE if c in v
                                        and not (c in ("tipo", "classificacao") and not v[c])},
                                 "proposta": v["ajuste"] if "ajuste" in v else r["proposta"]}
                    candidato["efeitos_reservados"] = efeitos_reservados(candidato)
                    if _chave_variante(candidato) == chave:
                        posicoes[v["votante"]] = "favor"
            emendas.append({
                "id": f"{r['id']}{chr(ord('a') + k)}",
                "origem": r["id"],
                "autores": r.get("autores", []) if k == 0 else ["ajuste"],
                "paragrafo": r.get("paragrafo"),
                **{c: var.get(c) for c in CAMPOS_VARIANTE},
                "trecho": r["trecho"],
                "proposta": var["texto"],
                "suporte_verificado": var.get("suporte_verificado"),
                "dependencias": r.get("dependencias", []),
                "inicio": r["inicio"],
                "fim": r["fim"],
                "delta_palavras": palavras(var["texto"]) - palavras(r["trecho"]),
                "grupo_conflito": f"R{r['id']}",
                "posicoes_anteriores": posicoes,
                "motivos_anteriores": motivos,
                "status": "valida",
                "motivos_invalidade": [],
            })
    return {"contrato": CONTRATO, "hash_minuta": apuracao["hash_minuta"], "rodada": 2, "lotes_recusados": [],
            "tipo_documento": apuracao.get("tipo_documento", "generico"), "classificacoes": apuracao.get("classificacoes"),
            "contexto_validacao": ctx,
            "emendas": emendas}


# ---------------------------------------------------------------- aplicar

def _classe(r: dict) -> str | None:
    return r.get("classificacao_aprovada") or r.get("classificacao")


def _reservada(r: dict) -> bool:
    return _classe(r) in RESERVADAS_AO_HUMANO or bool(efeitos_reservados(r))


def aprovadas_de(apuracoes: list[dict], excluir: tuple[str, ...] = (), autorizadas: tuple[str, ...] | None = ()) -> list[dict]:
    """Aprovadas a aplicar. Com ``autorizadas=None``, inclui também as reservadas ao humano."""
    out = []
    for ap in apuracoes:
        for r in ap["emendas"]:
            if r["decisao"] not in APROVADAS or r["id"] in excluir or r.get("origem") in excluir:
                continue
            if autorizadas is not None and _reservada(r) and r["id"] not in autorizadas:
                continue
            out.append(r)
    return sorted(out, key=lambda r: r["inicio"])


def aguardando_humano(apuracoes: list[dict], autorizadas: tuple[str, ...] = ()) -> list[dict]:
    return [r for ap in apuracoes for r in ap["emendas"]
            if r["decisao"] in APROVADAS and _reservada(r) and r["id"] not in autorizadas]


def aplicar(minuta: str, apuracoes: list[dict], max_palavras: int | None = None,
            excluir: tuple[str, ...] = (), autorizadas: tuple[str, ...] = ()) -> tuple[str, list[dict]]:
    hash_minuta = sha256_texto(minuta)
    for ap in apuracoes:
        ctx = _contexto(ap)
        if ap["hash_minuta"] != hash_minuta:
            raise SystemExit("a apuração foi feita sobre outra versão da minuta")
        for r in ap["emendas"]:
            if r["decisao"] in APROVADAS:
                final = {**r, "proposta": r["texto_aprovado"], "classificacao": _classe(r)}
                falhas = _requisitos(final, ctx["tipo_documento"], minuta, None,
                                      tuple(ctx["exigir_fonte"]), r.get("suporte_verificado"))
                if falhas:
                    raise SystemExit("emenda final não validada: " + "; ".join(falhas))
    aprovadas = aprovadas_de(apuracoes, excluir, autorizadas)
    for a, b in zip(aprovadas, aprovadas[1:]):
        if b["inicio"] < a["fim"]:
            raise SystemExit(f"emendas aprovadas sobrepostas: {a['id']} e {b['id']}")
    tocados = {r["paragrafo"] for r in aprovadas}
    pendentes = [(r["id"], d) for r in aprovadas for d in r.get("dependencias", []) if d not in tocados]
    if pendentes:
        raise SystemExit("aplicação recusada; dependências não atendidas: "
                         + ", ".join(f"{i} exige ajuste no parágrafo {d}" for i, d in pendentes)
                         + ". Votar a emenda dependente ou levar ao humano.")
    texto = minuta
    for r in reversed(aprovadas):
        assert texto[r["inicio"]:r["fim"]] == r["trecho"], r["id"]
        texto = texto[:r["inicio"]] + r["texto_aprovado"] + texto[r["fim"]:]
    if max_palavras:
        excesso = [(n, palavras(corpo_paragrafo(texto, i, f))) for n, i, f in limites_paragrafos(texto)
                   if palavras(corpo_paragrafo(texto, i, f)) > max_palavras]
        if excesso:
            raise SystemExit("aplicação recusada; parágrafos acima do limite: "
                             + ", ".join(f"{n} ({q} palavras)" for n, q in excesso)
                             + ". Votar uma emenda de corte no mesmo parágrafo ou levar ao humano.")
    return texto, aprovadas


def materiais(aplicadas: list[dict]) -> list[dict]:
    return [r for r in aplicadas if (r.get("classificacao_aprovada") or r.get("classificacao")) != "redacional"]


def relatorio(minuta_path: str, saida_path: str, hash_antes: str, hash_depois: str, apuracoes: list[dict],
              excluir: tuple[str, ...] = (), autorizadas: tuple[str, ...] = ()) -> str:
    def votos_txt(r: dict) -> str:
        return "; ".join(f"{v['votante']}: {v['voto']}" + (f" — {v['motivo']}" if v.get("motivo") else "")
                         + (f" (razão nova: {v['razao_nova']})" if v.get("razao_nova") else "") for v in r.get("votos", []))

    todas = {}
    for ap in apuracoes:  # a rodada de debate prevalece sobre a primeira para a mesma emenda de origem
        for r in ap["emendas"]:
            todas[r["id"]] = r
    origem_resolvida = {r.get("origem") for r in todas.values() if r.get("origem")}
    aplicadas = aprovadas_de(apuracoes, excluir, autorizadas)
    reservadas = {r["id"] for r in aguardando_humano(apuracoes, autorizadas)}
    regra = apuracoes[-1]["regra"]
    linhas = [
        f"# Relatório de emendas — {CONTRATO}",
        "",
        f"- Minuta de entrada: `{minuta_path}` (sha256 `{hash_antes}`)",
        f"- Minuta de saída: `{saida_path}` (sha256 `{hash_depois}`)",
        f"- Regra de aprovação: {regra}; cadeiras exigidas: {', '.join(apuracoes[0]['votantes'])}",
    ]
    for ap in apuracoes:
        faltaram = [n for n in ap["votantes"] if n not in ap.get("votantes_responderam", ap["votantes"])]
        if faltaram:
            linhas.append(f"- Rodada {ap.get('rodada', 1)}: sem resposta válida de {', '.join(faltaram)} (contadas como abstenção)")
        for v in ap.get("votantes_recusados", []):
            linhas.append(f"- Voto recusado de {v['votante']}: {v['motivo']}")
    if excluir:
        linhas.append(f"- Excluídas da aplicação por conflito no conjunto: {', '.join(excluir)}")
    if not materiais(aplicadas):
        linhas.append("- **Resultado: sem novas melhorias materiais consensuais.** Se os portões estiverem fechados, "
                      "encerrar sem nova versão de mérito.")
    linhas.append("- Adesão ao conjunto: pendente. Rodar `emendas.py conjunto` e `emendas.py confirmar` antes de adotar a saída.")
    secoes = [
        ("Aplicadas", APROVADAS),
        ("Aprovadas pelas cadeiras, reservadas à decisão humana", APROVADAS),
        ("Dissenso — decisão humana", ("dissenso", "segunda_rodada")),
        ("Preteridas por emenda concorrente mais votada", ("preterida",)),
        ("Rejeitadas", ("rejeitada",)),
        ("Inválidas", ("invalida",)),
    ]
    ids_aplicadas = {r["id"] for r in aplicadas}
    for titulo, decisoes in secoes:
        itens = [r for r in todas.values() if r["decisao"] in decisoes
                 and not (r["decisao"] in ("segunda_rodada", "dissenso") and r["id"] in origem_resolvida)
                 and (titulo != "Aplicadas" or r["id"] in ids_aplicadas)
                 and (not titulo.startswith("Aprovadas pelas") or r["id"] in reservadas)]
        linhas += ["", f"## {titulo} ({len(itens)})"]
        for r in sorted(itens, key=lambda r: (r.get("paragrafo") or 0, r["id"])):
            classe = r.get("classificacao_aprovada") or r.get("classificacao")
            linhas += ["", f"### {r['id']} — parágrafo {r.get('paragrafo', '—')} — {r.get('tipo')} — {classe} — proposta por {', '.join(r.get('autores', []))}"]
            linhas.append(f"- Antes: {r['trecho']}")
            if r["decisao"] in APROVADAS:
                linhas.append(f"- Depois: {r['texto_aprovado']}" + (" (com ajuste)" if r["decisao"] == "aprovada_com_ajuste" else ""))
            else:
                linhas.append(f"- Proposta: {r['proposta']}")
            if r.get("variantes") and r["decisao"] != "invalida":
                linhas += [f"- Variante {chr(ord('a') + k)} ({v['classificacao']}): {v['texto']}" for k, v in enumerate(r["variantes"])]
            if r.get("fundamento"):
                linhas.append(f"- Fundamento: {r['fundamento']}")
            if r.get("dependencias"):
                linhas.append(f"- Dependências: parágrafos {', '.join(map(str, r['dependencias']))}")
            if r.get("motivos"):
                linhas.append(f"- Motivo da invalidade: {'; '.join(r['motivos'])}")
            if r.get("motivo_decisao"):
                linhas.append(f"- Decisão: {r['motivo_decisao']}")
            if r.get("votos"):
                linhas.append(f"- Votos: {votos_txt(r)}")
    linhas += ["", "Próximos passos: adesão ao conjunto, pré-auditoria na minuta de saída com --anterior, redline contra a de "
               "entrada e auditoria cega final por outra família de modelo."]
    return "\n".join(linhas) + "\n"


# ---------------------------------------------------------------- adesão ao conjunto

def cedula_conjunto(minuta_base: str, texto_novo: str, aplicadas: list[dict]) -> str:
    hb, hn = sha256_texto(minuta_base), sha256_texto(texto_novo)
    linhas = [
        f"# Adesão ao conjunto de emendas — {CONTRATO}",
        "",
        f"HASH_MINUTA: {hb}",
        f"HASH_RESULTADO: {hn}",
        "",
        "Cada emenda abaixo já foi aprovada isoladamente. Verifique agora o conjunto aplicado: emendas aceitáveis "
        "uma a uma podem se contradizer quando combinadas, mudar o alcance de outro parágrafo ou deixar a conclusão, "
        "o formulário ou uma remissão incompatíveis. Responda \"aceito\" se subscreve o conjunto exato, ou \"conflito\" "
        "indicando as emendas envolvidas e o motivo.",
        "",
    ]
    for r in aplicadas:
        linhas += [f"## {r['id']} — parágrafo {r['paragrafo']} — {r.get('classificacao_aprovada') or r.get('classificacao')}",
                   "", f"**Antes:** {r['trecho']}", "", f"**Depois:** {r['texto_aprovado']}", ""]
    modelo = {"votante": "<seu identificador>", "hash_minuta": hb, "hash_resultado": hn, "adesao": "aceito",
              "conflitos": [{"ids": ["E01", "E02"], "motivo": "..."}]}
    linhas += ["## Resposta", "", "Responda só com o JSON abaixo; com \"aceito\", deixe \"conflitos\" vazio.", "",
               "```json", json.dumps(modelo, ensure_ascii=False, indent=2), "```"]
    return "\n".join(linhas) + "\n"


def confirmar(minuta_base: str, texto_novo: str, lotes: list[dict], regra: str = "unanimidade",
              exigidos: list[str] | None = None, apuracoes: list[dict] | None = None,
              excluir: tuple[str, ...] = (), autorizadas: tuple[str, ...] = ()) -> dict:
    if apuracoes is None:
        raise SystemExit("a confirmação exige as apurações: reconstituir o conjunto e as autorizações antes de aprovar")
    esperado, _ = aplicar(minuta_base, apuracoes, excluir=excluir, autorizadas=autorizadas)
    if esperado != texto_novo:
        raise SystemExit("resultado não corresponde às emendas aprovadas e autorizadas sobre a base")
    hb, hn = sha256_texto(minuta_base), sha256_texto(texto_novo)
    quorum, validos, recusados = separar_votantes(lotes, hb, exigidos, hash_extra=("hash_resultado", hn))
    adesoes, conflitos, abstencoes = [], [], []
    for nome in quorum:
        lote = validos.get(nome)
        if lote is None or lote.get("adesao") not in ("aceito", "conflito"):
            abstencoes.append(nome)
        elif lote["adesao"] == "aceito":
            adesoes.append(nome)
        else:
            for c in lote.get("conflitos") or [{"ids": [], "motivo": "conflito sem indicação"}]:
                conflitos.append({"votante": nome, "ids": c.get("ids", []), "motivo": c.get("motivo", "")})
    aprovado = regra_atingida(len(adesoes), len(quorum), regra) and not conflitos
    return {
        "contrato": CONTRATO,
        "hash_minuta": hb,
        "hash_resultado": hn,
        "regra": regra,
        "conjunto_aprovado": aprovado,
        "adesoes": adesoes,
        "abstencoes": abstencoes,
        "conflitos": conflitos,
        "votantes_recusados": recusados,
        "ids_em_conflito": sorted({i for c in conflitos for i in c["ids"]}),
    }


# ---------------------------------------------------------------- CLI

def _lista(valor: str | None) -> list[str] | None:
    return [v.strip() for v in valor.split(",") if v.strip()] if valor else None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validar")
    v.add_argument("--minuta", type=Path, required=True)
    v.add_argument("--propostas", type=Path, nargs="+", required=True)
    v.add_argument("--travados", type=Path)
    v.add_argument("--fontes", type=Path, nargs="*", help="pastas ou arquivos onde conferir a fonte literal")
    v.add_argument("--max-palavras", type=int)
    v.add_argument("--exigir-fonte", default="correcao,fonte", help="tipos adicionais que exigem fonte; toda emenda material exige suporte")
    v.add_argument("--tipo-documento", default="generico", choices=sorted(CLASSIFICACOES_POR_TIPO),
                   help="define o conjunto de classificações: parecer, peca (petição, recurso), decisao ou generico")
    v.add_argument("--saida", type=Path, required=True)

    c = sub.add_parser("cedula")
    c.add_argument("--validadas", type=Path, required=True)
    c.add_argument("--saida", type=Path, required=True)
    c.add_argument("--semente")

    a = sub.add_parser("apurar")
    a.add_argument("--validadas", type=Path, required=True)
    a.add_argument("--votos", type=Path, nargs="*", default=[])
    a.add_argument("--votantes", required=True, help="cadeiras exigidas, separadas por vírgula; quem não votar conta como abstenção")
    a.add_argument("--regra", default="unanimidade", help="unanimidade | maioria | qualificada:2/3")
    a.add_argument("--fontes", type=Path, nargs="*", help="mesmo corpus validado, para conferir suporte novo de variantes")
    a.add_argument("--saida", type=Path, required=True)

    s = sub.add_parser("segunda-rodada")
    s.add_argument("--apuracao", type=Path, required=True)
    s.add_argument("--saida", type=Path, required=True)

    ap = sub.add_parser("aplicar")
    ap.add_argument("--minuta", type=Path, required=True)
    ap.add_argument("--apuracao", type=Path, nargs="+", required=True, help="primeira rodada e, se houver, a de debate")
    ap.add_argument("--saida", type=Path, required=True)
    ap.add_argument("--relatorio", type=Path, required=True)
    ap.add_argument("--max-palavras", type=int, help="limite por parágrafo, conferido no texto final")
    ap.add_argument("--excluir", help="ids a deixar de fora (conflito apontado na adesão ao conjunto)")
    ap.add_argument("--autorizadas", help="ids cujos efeitos reservados ou risco estratégico o usuário autorizou, em qualquer tipo")

    cj = sub.add_parser("conjunto")
    cj.add_argument("--minuta-base", type=Path, required=True)
    cj.add_argument("--minuta-nova", type=Path, required=True)
    cj.add_argument("--apuracao", type=Path, nargs="+", required=True)
    cj.add_argument("--excluir")
    cj.add_argument("--autorizadas")
    cj.add_argument("--saida", type=Path, required=True)

    cf = sub.add_parser("confirmar")
    cf.add_argument("--minuta-base", type=Path, required=True)
    cf.add_argument("--minuta-nova", type=Path, required=True)
    cf.add_argument("--apuracao", type=Path, nargs="+", required=True)
    cf.add_argument("--excluir")
    cf.add_argument("--autorizadas")
    cf.add_argument("--votos", type=Path, nargs="*", default=[])
    cf.add_argument("--votantes", required=True)
    cf.add_argument("--regra", default="unanimidade")
    cf.add_argument("--saida", type=Path, required=True)

    args = p.parse_args(argv)

    if args.cmd == "validar":
        minuta = args.minuta.read_text(encoding="utf-8")
        travados = ler_json(args.travados) if args.travados else None
        fontes = corpus_fontes(args.fontes) if args.fontes else None
        exigir = tuple(t for t in args.exigir_fonte.split(",") if t)
        res = validar(minuta, [ler_json(f) for f in args.propostas], travados, fontes, args.max_palavras, exigir, args.tipo_documento)
        gravar_json(args.saida, res)
        n_val = sum(e["status"] == "valida" for e in res["emendas"])
        print(f"{n_val} válidas, {len(res['emendas']) - n_val} inválidas, {len(res['lotes_recusados'])} lotes recusados")
        for e in res["emendas"]:
            if e["status"] == "invalida":
                print(f"  {e['id']} inválida: {'; '.join(e['motivos_invalidade'])}")
            for al in e.get("alertas", []):
                print(f"  {e['id']} alerta: {al}")
        return 0
    if args.cmd == "cedula":
        args.saida.write_text(cedula(ler_json(args.validadas), args.semente), encoding="utf-8")
        print(f"cédula gravada em {args.saida}")
        return 0
    if args.cmd == "apurar":
        res = apurar(ler_json(args.validadas), [ler_json(f) for f in args.votos], args.regra, _lista(args.votantes),
                     corpus_fontes(args.fontes) if args.fontes else None)
        gravar_json(args.saida, res)
        cont: dict[str, int] = {}
        for r in res["emendas"]:
            cont[r["decisao"]] = cont.get(r["decisao"], 0) + 1
        print(", ".join(f"{k}: {n}" for k, n in sorted(cont.items())), "| responderam:",
              ", ".join(res["votantes_responderam"]) or "nenhum", "de", ", ".join(res["votantes"]))
        for rv in res["votantes_recusados"]:
            print(f"  voto recusado de {rv['votante']}: {rv['motivo']}")
        return 0
    if args.cmd == "segunda-rodada":
        res = segunda_rodada(ler_json(args.apuracao))
        gravar_json(args.saida, res)
        print(f"{len(res['emendas'])} variantes para a rodada de debate")
        return 0
    if args.cmd == "aplicar":
        minuta = args.minuta.read_text(encoding="utf-8")
        apuracoes = [ler_json(f) for f in args.apuracao]
        excluir = tuple(_lista(args.excluir) or ())
        autorizadas = tuple(_lista(args.autorizadas) or ())
        texto, aplicadas = aplicar(minuta, apuracoes, args.max_palavras, excluir, autorizadas)
        args.saida.write_text(texto, encoding="utf-8")
        args.relatorio.write_text(relatorio(str(args.minuta), str(args.saida), sha256_texto(minuta), sha256_texto(texto),
                                            apuracoes, excluir, autorizadas), encoding="utf-8")
        for r in aguardando_humano(apuracoes, autorizadas):
            print(f"  {r['id']} aprovada pelas cadeiras, mas reservada à decisão do usuário ({_classe(r)}); use --autorizadas")
        print(f"{len(aplicadas)} emendas aplicadas ({len(materiais(aplicadas))} materiais); sha256 da saída: {sha256_texto(texto)}")
        if not materiais(aplicadas):
            print("sem novas melhorias materiais consensuais")
        return 0
    if args.cmd == "conjunto":
        base = args.minuta_base.read_text(encoding="utf-8")
        nova = args.minuta_nova.read_text(encoding="utf-8")
        texto, aplicadas = aplicar(base, [ler_json(f) for f in args.apuracao], excluir=tuple(_lista(args.excluir) or ()),
                                   autorizadas=tuple(_lista(args.autorizadas) or ()))
        if texto != nova:
            raise SystemExit("a minuta nova não corresponde à aplicação das emendas aprovadas sobre a base")
        args.saida.write_text(cedula_conjunto(base, nova, aplicadas), encoding="utf-8")
        print(f"cédula do conjunto gravada em {args.saida}")
        return 0
    if args.cmd == "confirmar":
        res = confirmar(args.minuta_base.read_text(encoding="utf-8"), args.minuta_nova.read_text(encoding="utf-8"),
                        [ler_json(f) for f in args.votos], args.regra, _lista(args.votantes),
                        [ler_json(f) for f in args.apuracao], tuple(_lista(args.excluir) or ()),
                        tuple(_lista(args.autorizadas) or ()))
        gravar_json(args.saida, res)
        if res["conjunto_aprovado"]:
            print("conjunto aprovado: a minuta nova pode substituir a base e seguir para a auditoria final")
            return 0
        print("conjunto não aprovado:", f"abstenções {res['abstencoes']}" if res["abstencoes"] else "",
              f"conflitos em {res['ids_em_conflito']}" if res["conflitos"] else "")
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
