#!/usr/bin/env python3
"""Pré-auditoria determinística de qualquer trabalho jurídico em Markdown: parecer, petição, recurso, decisão.

Roda antes de qualquer auditoria por modelo e depois de cada rodada de
emendas. Pega o que é mecânico — numeração, tamanho dos parágrafos, ritmo
(parágrafos demais encostados no teto), fecho, remissões internas e sua
concordância ("O parágrafos 185 e 186 admite"), remissão genérica ao Anexo sem
nome, marcadores soltos, assinatura, repetição de precedente, frases quase
iguais, trechos travados, afirmações absolutas de fato sem citação na mesma frase
(``absolutos``: "nunca", "sempre", "todos", "nenhum", "integralmente"...; não conta o
juízo normativo ou de suficiência — "Nenhum indício basta sozinho", "Nenhuma dessas
vias autoriza" — nem a frase de escopo restrito — "nas passagens examinadas") e
remissões quebradas por renumeração — para que os auditores gastem a atenção no
mérito. Com ``--anterior``, aponta ainda palavras de alcance acrescentadas ou
retiradas ("até", "somente", "deverá"...), ressalvas que sumiram, itens de citação
que sumiram ("§§ 2º", "nº 5.827/1972") e frases da versão anterior sem
correspondente na nova.

Para não acusar a mera troca de forma: os termos de alcance contam por família
("deve"/"deverá"/"caberá"/"cumpre"; "apenas"/"somente"/"só") e as construções
equivalentes se normalizam antes ("deve ser X" ≈ "a X"/"X-se"/"depende da Xção";
"não se pode" ≈ "sem que se possa"/"não basta para"; "devem ser observados" ≈
"observam-se"/"observados"); o termo ou a ressalva "perdidos" são procurados também
nos parágrafos vizinhos (±1) da nova versão; e a frase da anterior que reaparece com
60% ou mais de correspondência em algum parágrafo novo vira INFO, não alerta.

``--mapa-origem ARQ.json`` (``{"novo_para_antigos": {"<novo>": [antigos]}}``, números
do corpo numerado, ou a saída de ``verificar_remissoes.py mapear``) faz a comparação
com ``--anterior`` usar a UNIÃO dos parágrafos antigos que cada novo incorpora, em vez
do alinhamento por posição; em fusão ou divisão, conta-se presença e não número de
ocorrências. Em documento de numeração mista (preâmbulo sem número), o corpo numerado
é a primeira sequência "1.", "2."... e a ponte para os IDs globais é automática.
``--refutadas ARQ.json`` (formato de ``checar_refutadas.py``) transforma cada afirmação
refutada que reaparece em BLOQUEANTE.

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
    pre_auditoria_parecer.py v16.md --perfil genes --anterior v15.md \\
        --mapa-origem origem_v15_v16.json --refutadas refutadas.json
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parecer_md as pm  # noqa: E402
import checar_refutadas as cr  # noqa: E402
import verificar_remissoes as vr  # noqa: E402

PERFIS = {
    "generico": {
        "max_palavras": None,
        "fecho": None,
        "rotulos_conclusao": [],
        "assinatura": [],
        "anexos_nomeados": False,
    },
    "genes": {
        "max_palavras": 120,
        "fecho": "É o parecer, sob censura.",
        "rotulos_conclusao": [
            "Correções necessárias|Correções e definições prioritárias",
            "Obrigações já incidentes|Obrigações jurídicas incidentes",
            "Recomendações facultativas",
            "Providências fora do regulamento|Providências a cargo de outros órgãos|Providências a cargo de terceiros",
        ],
        "exige_numeracao": True,
        "assinatura": [
            "[Nome do(a) Advogado(a)]",
            "OAB/MG",
            "De acordo:",
            "Gerência de Negócios Jurídicos e Demandas Estratégicas (GENES) / Diretoria Jurídica (DIJUR)",
        ],
        # bloco equivalente ao modelo: nome do subscritor, cargo e unidade ("Advogado – GENES")
        "assinatura_alternativa": [r"Advogad[oa]\b.{0,80}\bGENES\b"],
        "anexos_nomeados": True,
        "veda_transcricao": True,
    },
}

# Estilos de redação (references/estilos-de-redacao.md). O perfil fixa o teto duro de
# palavras; o estilo fixa o alvo (alerta acima dele), a exigência da resposta objetiva no
# início e o número de transcrições literais admitidas por seção.
ESTILOS = {
    # teto_alvo: alerta acima dele (o teto duro é o do perfil). frase_media/frase_max: palavras por frase.
    # transcricoes_por_secao: transcrições literais longas admitidas por seção ou subtítulo de quesito.
    # ementa_estruturada: ementa em quatro itens (caso, questões, razões, resposta), que pode trazer a resposta objetiva.
    "executivo": {"teto_alvo": 90, "resposta_objetiva": True, "transcricoes_por_secao": 0,
                  "frase_media": 30, "frase_max": 50, "ementa_estruturada": False, "rotulo_sem_negrito": False},
    "classico": {"teto_alvo": None, "resposta_objetiva": False, "transcricoes_por_secao": 1,
                 "frase_media": 45, "frase_max": 80, "ementa_estruturada": True, "rotulo_sem_negrito": True},
}
TRANSCRICAO_MIN_PALAVRAS = 40
_ASPAS_RE = re.compile(r"[“\"]([^”\"]{40,})[”\"]")
_RESPOSTA_OBJETIVA_RE = re.compile(r"^(?:\d+\.\s*)?(?:\*\*)?\s*Resposta objetiva", re.I)
_EMENTA_TRANSCRITA_RE = re.compile(r"^(?:>\s*)?(?:\*\*)?EMENTA\s*:", re.I)
EMENTA_ITENS = [
    ("caso", re.compile(r"caso (?:sob|em) exame", re.I)),
    ("questões", re.compile(r"quest(?:ão|ões) em discuss", re.I)),
    ("razões", re.compile(r"raz(?:ões|ão) (?:conclusivas|de decidir|do parecer)", re.I)),
    ("resposta", re.compile(r"resposta objetiva|conclus(?:ão|ões) e resposta|dispositivo e tese", re.I)),
]
INTENSIFICADORES_RE = re.compile(
    r"\b(rigoros[ao]s?|rigorosamente|estrit[ao]s?|estritamente|absolut[ao]s?|absolutamente|manifest[ao]s?|manifestamente|"
    r"inequ[ií]voc[ao]s?|inequivocamente|cabal|cabalmente|indubit[áa]vel|indubitavelmente|n[ií]tid[ao]s?|nitidamente|"
    r"flagrante|flagrantemente|patente|induvidos[ao]|inafast[áa]vel|imprescind[ií]vel|imprescind[ií]veis)\b", re.I)
_FRASE_ESTILO_RE = re.compile(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÂÊÔÃÕÇ“(])")


def _num_visivel(b) -> int | None:
    return getattr(b, "numero_original", None) or b.numero


def _limpo(texto: str) -> str:
    """Texto do bloco sem negrito e sem o número de parágrafo que o documento misto prefixa."""
    return re.sub(r"^\d+\.\s*", "", pm.sem_negrito(texto).strip())


def _antes_do_primeiro_titulo(doc: pm.Documento) -> list:
    """Blocos que precedem o primeiro título (cabeçalho e ementa). Vazio se o documento não tem título."""
    out = []
    for b in doc.blocos:
        if b.tipo == "titulo":
            return out
        out.append(b)
    return []


def checar_teto_estilo(doc: pm.Documento, alvo: int | None, maximo: int | None, estilo: str) -> list[Achado]:
    if not alvo:
        return []
    out = []
    for b in doc.paragrafos:
        n = pm.palavras(b.texto)
        if n > alvo and (not maximo or n <= maximo):
            out.append(Achado("alerta", "estilo", b.numero,
                              f"{n} palavras: acima do alvo do estilo {estilo} ({alvo}); dividir por função ou enxugar"))
    return out


def checar_resposta_objetiva(doc: pm.Documento, exigir: bool, estilo: str) -> list[Achado]:
    """Executivo: exige a resposta objetiva no §1, logo depois do primeiro título ou entre a ementa e o Relatório.
    Em qualquer estilo, avisa quando ela está sem número num documento de parágrafos numerados: cópia em que a
    resposta perde a numeração desloca todos os parágrafos e quebra as remissões."""
    out = []
    numerado = any(getattr(b, "numero_original", None) for b in doc.paragrafos)
    achadas = [b for b in doc.blocos if b.tipo in ("par", "texto") and _RESPOSTA_OBJETIVA_RE.match(b.texto.strip())]
    for b in achadas:
        if numerado and getattr(b, "numero_original", None) is None:
            antes = _antes_do_primeiro_titulo(doc)
            if b in antes:
                out.append(Achado("alerta", "estilo", b.numero,
                                  "«Resposta objetiva» sem número antes do Relatório: confira se as remissões a "
                                  "parágrafo foram refeitas (a perda do número desloca todos os parágrafos em um)"))
    if not exigir:
        return out
    primeiros = [b for b in doc.paragrafos if getattr(b, "numero_original", None) == 1]
    depois_titulo, viu = [], False
    for b in doc.blocos:
        if b.tipo == "titulo":
            viu = True
        elif viu and b.tipo == "par":
            depois_titulo.append(b)
    candidatos = primeiros + depois_titulo[:3] + [b for b in _antes_do_primeiro_titulo(doc) if b.tipo in ("par", "texto")]
    if not candidatos:
        candidatos = doc.paragrafos[:3]
    if any(_RESPOSTA_OBJETIVA_RE.match(b.texto.strip()) for b in candidatos):
        return out
    return out + [Achado("bloqueante", "estilo", None,
                         f'estilo {estilo}: falta o parágrafo "Resposta objetiva." no início do parecer')]


def checar_ementa_estruturada(doc: pm.Documento, esperada: bool, estilo: str) -> list[Achado]:
    """Clássico: ementa em quatro itens (caso sob exame; questões em discussão; razões conclusivas; resposta
    objetiva aos quesitos), no padrão das ementas judiciais. Alerta os itens que faltam."""
    if not esperada:
        return []
    inicio = [b for b in doc.blocos if b.tipo in ("par", "texto")][:14]
    texto = "\n".join(b.texto for b in inicio)
    faltam = [nome for nome, rx in EMENTA_ITENS if not rx.search(texto)]
    if not faltam:
        return []
    if len(faltam) == len(EMENTA_ITENS):
        return [Achado("alerta", "estilo", None,
                       f"estilo {estilo}: ementa sem os quatro itens estruturados (caso sob exame; questões em "
                       "discussão; razões conclusivas; resposta objetiva aos quesitos)")]
    return [Achado("alerta", "estilo", None,
                   f"estilo {estilo}: ementa estruturada incompleta; falta(m): {', '.join(faltam)}")]


def checar_transcricoes(doc: pm.Documento, por_secao: int | None, vedada: bool, estilo: str | None) -> list[Achado]:
    """Transcrição literal longa: bloco iniciado por ">" ou "EMENTA:", com os blocos sem número que o seguem
    (uma só transcrição), ou trecho entre aspas com 40 palavras ou mais. A ementa do próprio parecer, antes do
    primeiro título, não conta. `vedada` só se aplica quando o estilo não admite nenhuma (por_secao == 0)."""
    if por_secao is None and not vedada:
        return []
    out, secao, conta, titulo = [], 0, {}, {0: "início"}
    viu_titulo, em_transcricao = False, False
    for b in doc.blocos:
        if b.tipo == "titulo":
            viu_titulo, em_transcricao = True, False
            secao += 1
            titulo[secao] = b.texto[:40]
            continue
        if b.tipo not in ("par", "texto") or not viu_titulo:
            continue
        t = b.texto.strip()
        sem_numero = getattr(b, "numero_original", None) is None and doc.numeracao == "mista"
        if em_transcricao and sem_numero:
            continue  # continuação da mesma transcrição
        em_transcricao = False
        inicio_ementa = bool(_EMENTA_TRANSCRITA_RE.match(_limpo(t))) or t.startswith(">")
        longa = inicio_ementa or any(len(m.group(1).split()) >= TRANSCRICAO_MIN_PALAVRAS for m in _ASPAS_RE.finditer(t))
        if not longa:
            continue
        em_transcricao = inicio_ementa
        conta[secao] = conta.get(secao, 0) + 1
        if por_secao == 0:
            msg = ("transcrição literal longa: o perfil veda transcrever ementa ou acórdão neste estilo; parafrasear"
                   if vedada else f"transcrição literal longa: o estilo {estilo} pede paráfrase analítica")
            out.append(Achado("alerta", "transcricao", b.numero, msg))
        elif por_secao is not None and conta[secao] > por_secao:
            out.append(Achado("alerta", "transcricao", b.numero,
                              f"transcrição literal longa além do admitido no estilo {estilo} "
                              f"({por_secao} por seção ou quesito; seção «{titulo[secao]}»)"))
    return out


def checar_frases_estilo(doc: pm.Documento, media_alvo: int | None, maximo: int | None, estilo: str) -> list[Achado]:
    """Tamanho da frase, a diferença mais visível entre os estilos. Mede só parágrafos numerados do corpo
    (transcrições e referências ficam de fora)."""
    if not media_alvo and not maximo:
        return []
    pars = [b for b in doc.paragrafos if getattr(b, "numero_original", None) or doc.numeracao == "explicita"]
    if not pars:
        pars = doc.paragrafos
    tamanhos, out = [], []
    for b in pars:
        longas = 0
        # citações e remissões entre parênteses não contam para o tamanho da frase
        corpo = re.sub(r"\([^()]*\)", " ", re.sub(r"\([^()]*\([^()]*\)[^()]*\)", " ", _limpo(b.texto)))
        for f in _FRASE_ESTILO_RE.split(corpo):
            n = len(f.split())
            if n < 4:
                continue
            tamanhos.append(n)
            if maximo and n > maximo:
                longas += 1
        if longas:
            out.append(Achado("alerta", "frase", b.numero,
                              f"{longas} frase(s) acima de {maximo} palavras (estilo {estilo}): dividir ou tirar a "
                              "citação do meio da frase"))
    if tamanhos and media_alvo:
        media = sum(tamanhos) / len(tamanhos)
        if media > media_alvo:
            out.insert(0, Achado("alerta", "frase", None,
                                 f"média de {media:.0f} palavras por frase, acima do alvo do estilo {estilo} ({media_alvo})"))
        else:
            out.insert(0, Achado("info", "frase", None, f"média de {media:.0f} palavras por frase (alvo do estilo {estilo}: {media_alvo})"))
    return out


def checar_intensificadores(doc: pm.Documento) -> list[Achado]:
    """Ênfase não é estilo: «manifesto», «inequívoco», «rigorosamente» afirmam um grau de certeza. Alerta por
    parágrafo, fora de aspas, para retirar ou citar a fonte que sustente a ênfase."""
    out = []
    for b in doc.paragrafos:
        if getattr(b, "numero_original", None) is None and doc.numeracao == "mista":
            continue
        t = re.sub(r"[“\"][^”\"]*[”\"]", " ", _limpo(b.texto))
        achados = sorted({m.group(1).lower() for m in INTENSIFICADORES_RE.finditer(t)})
        if achados:
            out.append(Achado("alerta", "enfase", b.numero,
                              "intensificador(es) " + ", ".join(f"«{a}»" for a in achados)
                              + ": retirar ou citar a fonte que sustente a ênfase"))
    return out


def checar_anexo_exigido(doc: pm.Documento, exigir: bool) -> list[Achado]:
    if not exigir:
        return []
    if any(b.tipo == "titulo" and re.search(r"\banexo\b", b.texto, re.I) for b in doc.blocos):
        return []
    return [Achado("bloqueante", "anexo", None,
                   "a consulta pede minuta ou peça anexa (--exige-anexo), e o parecer não traz seção de Anexo")]

MARCADORES_RE = re.compile(
    r"\[(?:INFORMAR|CONFIRMAR|NÃO CONSTA|NAO CONSTA|NÃO VERIFICADO[^\]]*|PENDENTE[^\]]*|VERIFICAR[^\]]*|TODO)\]"
    r"|\bTODO\b|\bXXX\b|\?\?"
    r"|\[\[§\s*\d+\]\]",  # remissão provisória da reescrita com reestruturação (revisao-redacional.md, seção 5)
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
# Famílias de termos de alcance: trocar "deve" por "deverá" ou "apenas" por "somente" não muda o alcance.
FAMILIAS_ALCANCE = {
    "deve": "dever", "devem": "dever", "deverá": "dever", "deverão": "dever",
    "pode": "poder", "podem": "poder", "poderá": "poder", "poderão": "poder",
    "não pode": "não pode", "não poderá": "não pode",
    "somente": "apenas", "apenas": "apenas",
    "vedado": "vedado", "vedada": "vedado", "facultativo": "facultativo", "facultativa": "facultativo",
    "todos": "todos", "todas": "todos", "nenhum": "nenhum", "nenhuma": "nenhum",
}
# Equivalentes que só compensam: "caberá"/"cumpre" no lugar de "deverá", "só" no lugar de "apenas",
# "possa" no lugar de "pode". Explicam a troca, mas nunca geram alerta por si.
EQUIVALENTES_ALCANCE = {
    "dever": ("cumpre", "cumprirá", "cabe", "caberá", "caberão", "é preciso", "é necessário", "impõe-se"),
    "poder": ("possa", "possam", "poderia", "poderiam", "é possível", "admite-se"),
    "apenas": ("só", "unicamente", "tão somente"),
    "nenhum": ("nem", "não"),
    "até": ("antes de", "antes da", "antes do", "antes das", "antes dos", "antes dessa", "antes dessas",
            "antes desse", "antes desses", "enquanto não"),
}
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
            if b.tipo == "par" and _limpo(b.texto) == fecho:
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
    # cabeçalho e ementa (blocos sem número antes do primeiro título) e transcrições não entram no teto
    isentos = {id(b) for b in _antes_do_primeiro_titulo(doc) if getattr(b, "numero_original", None) is None}
    return [
        Achado("bloqueante", "palavras", b.numero, f"{pm.palavras(b.texto)} palavras (máximo {maximo})")
        for b in doc.paragrafos
        if pm.palavras(b.texto) > maximo and id(b) not in isentos
        and not _EMENTA_TRANSCRITA_RE.match(_limpo(b.texto))
    ]


RITMO_FAIXA = 0.10  # "perto do teto": a menos de 10% do máximo de palavras
RITMO_PROPORCAO = 0.30


def checar_ritmo(doc: pm.Documento, maximo: int | None) -> list[Achado]:
    """Parágrafos demais encostados no teto: o texto fica monótono e cada emenda estoura o limite."""
    pars = doc.paragrafos
    if not maximo or not pars:
        return []
    piso = maximo * (1 - RITMO_FAIXA)
    perto = [b.numero for b in pars if pm.palavras(b.texto) >= piso]
    proporcao = len(perto) / len(pars)
    if proporcao <= RITMO_PROPORCAO:
        return []
    return [Achado("alerta", "ritmo", None,
                   f"{len(perto)} de {len(pars)} parágrafos ({proporcao:.0%}) têm {math.ceil(piso)} palavras ou mais, a menos de "
                   f"10% do teto de {maximo}: variar o tamanho, com a maioria entre 40 e 90 palavras "
                   f"(parágrafos: {', '.join(map(str, perto[:20]))}{' …' if len(perto) > 20 else ''})")]


ANEXO_RE = re.compile(r"\bAnexo\b")
ANEXO_NOMEADO_RE = re.compile(r"^\s+(?:[IVXLC]+\b|\d+\b|[A-Z]\b|d[eaos]{1,2}\s|[–—-]|[“\"«])")
ANEXO_ID_RE = re.compile(r"\b(?:Anexo|ANEXO)\s+([IVXLC]+|\d+|[A-Z])\b")
ANEXO_TITULO_RE = re.compile(r"^\s*(?:Anexo|ANEXO)\b")


def contar_anexos(doc: pm.Documento) -> int:
    """Anexos distintos: identificadores ("Anexo I", "Anexo 2") e títulos que começam por "Anexo"."""
    ids = set(ANEXO_ID_RE.findall(doc.bruto))
    titulos = {b.texto.strip() for b in doc.blocos if b.tipo in ("titulo", "marca") and ANEXO_TITULO_RE.match(b.texto)}
    return max(len(ids), len(titulos))


def checar_anexos_nomeados(doc: pm.Documento, exigir: bool = False) -> list[Achado]:
    """Remissão genérica ao Anexo ("Anexo, item 5", "(Anexo, itens 3 e 4)", "conforme Anexo") sem dizer qual."""
    n_anexos = contar_anexos(doc)
    if not exigir and n_anexos < 2:
        return []
    motivo = "o perfil exige" if exigir else f"o documento tem {n_anexos} anexos"
    out = []
    for b in doc.paragrafos:
        for m in ANEXO_RE.finditer(b.texto):
            if ANEXO_NOMEADO_RE.match(b.texto[m.end():m.end() + 8]):
                continue
            trecho = b.texto[max(0, m.start() - 12):m.end() + 14].strip()
            out.append(Achado("alerta", "anexo_generico", b.numero,
                              f"remissão genérica ao Anexo («…{trecho}…»): {motivo} nomear o anexo em toda remissão "
                              "(ex.: «Anexo de Redações Sugeridas, item 5»)"))
    return out


def checar_concordancia_remissoes(doc: pm.Documento) -> list[Achado]:
    """Mesma regra de ``verificar_remissoes.py``: "O parágrafos 185 e 186 admite" e afins."""
    return [Achado("alerta", "concordancia", b.numero, f"{msg}: «{trecho}»")
            for b in doc.paragrafos for trecho, msg in vr.problemas_concordancia(pm.sem_negrito(b.texto))]


def checar_fecho(doc: pm.Documento, fecho: str | None) -> list[Achado]:
    if not fecho:
        return []
    pars = doc.paragrafos
    achados = [b for b in pars if _limpo(b.texto) == fecho]
    if not achados:
        return [Achado("bloqueante", "fecho", None, f'fecho "{fecho}" ausente')]
    numerados = [b for b in pars if getattr(b, "numero_original", None)] or pars
    if _limpo(numerados[-1].texto) != fecho:
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


def checar_conclusao(doc: pm.Documento, rotulos: list[str], sem_negrito: bool = False) -> list[Achado]:
    """Rótulos de grupo da conclusão. Cada rótulo admite variantes separadas por "|". Com `sem_negrito`
    (estilo clássico), vale também o rótulo no início de alínea ou de parágrafo, sem negrito
    ("a) Correções e definições prioritárias: …")."""
    if not rotulos:
        return []
    inicio = None
    for i, b in enumerate(doc.blocos):
        if b.tipo == "titulo" and "conclus" in b.texto.lower():
            inicio = i
    if inicio is None:
        return [Achado("bloqueante", "conclusao", None, "seção de conclusão não encontrada")]
    blocos = [b for b in doc.blocos[inicio + 1:] if b.tipo == "par"]
    texto = "\n".join(b.texto for b in blocos)

    def presente(a: str) -> bool:
        if f"**{a}" in texto:
            return True
        if not sem_negrito:
            return False
        rx = re.compile(r"^(?:[a-z]\)|\(?[ivx]+\)|[-–•])?\s*" + re.escape(a), re.I)
        return any(rx.match(_limpo(b.texto)) for b in blocos)

    return [
        Achado("bloqueante", "conclusao", None,
               ("rótulo " if sem_negrito else "rótulo em negrito ")
               + " ou ".join(f'"{a}"' if sem_negrito else f'"**{a}**"' for a in r.split("|")) + " ausente da conclusão")
        for r in rotulos
        if not any(presente(a) for a in r.split("|"))
    ]


def checar_assinatura(doc: pm.Documento, fecho: str | None, linhas: list[str],
                      alternativa: list[str] | None = None) -> list[Achado]:
    """Linhas do bloco de assinatura do perfil. `alternativa` são expressões regulares de um bloco
    equivalente já preenchido (ex.: "Advogado – … GENES"): se todas aparecerem depois do fecho, o bloco vale."""
    if not linhas:
        return []
    isentos = _blocos_assinatura(doc, fecho)
    texto = "\n".join(_limpo(doc.blocos[i].texto) for i in sorted(isentos))
    if alternativa and all(re.search(rx, texto, re.I | re.S) for rx in alternativa):
        return []
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


ABSOLUTOS_RE = re.compile(
    r"\b(nunca|jamais|sempre|todos|todas|nenhum|nenhuma|integralmente|absolutamente|inequivocamente"
    r"|exclusivamente|indubitavelmente)\b",
    re.IGNORECASE,
)
# Parêntese de citação na mesma frase: (SEI 123, p. 4), (pp. 10–12), (fls. 3), (art. 5º da Lei ...).
CITACAO_FRASE_RE = re.compile(r"\([^()]*?(?:\bpp?\.\s*\d|\bSEIs?\b|\bfls?\.\s*\d|\barts?\.\s*\d)[^()]*\)", re.IGNORECASE)
# Absoluto negado por verbo epistêmico antes dele: "sem presumir que todos", "não se pode presumir",
# "não se pode inferir que abranja exclusivamente", "não demonstra que seja exclusivamente".
PRESUNCAO_NEGADA_RE = re.compile(
    r"\b(?:sem|n[ãa]o|nem|tampouco)\s+(?:se\s+)?(?:(?:pode|deve|permite|autoriza|basta)\w*\s+(?:para\s+)?(?:se\s+)?)?"
    r"(?:presum|infer|deduz|conclu|afirm|demonstr|prov|comprov|atest)\w*",
    re.IGNORECASE,
)
# Frase prescritiva ("nenhum ato deve ser praticado"): recomendação, não afirmação de fato.
PRESCRICAO_RE = re.compile(r"\b(?:deve|devem|dever[áa]|dever[ãa]o)\b", re.IGNORECASE)
# "..., todos de 1982": aposto que resume a enumeração anterior, não generalização.
APOSTO_TODOS_RE = re.compile(r",\s*(todos|todas)\b", re.IGNORECASE)
# Juízo normativo ou de suficiência negado: "Nenhum indício basta sozinho", "nenhum deles resolve",
# "Nenhuma dessas vias autoriza a baixa", "jamais pode ser presumido". O absoluto qualifica o que basta,
# autoriza ou se exige — não afirma fato. Até quatro palavras entre o absoluto e o verbo, sem pontuação forte.
VERBOS_SUFICIENCIA = (
    r"autorizam?|bastam?|permitem?|dispensam?|imp[õo]em?|exigem?|pode|podem|deve|devem|cabem?|substituem?|substitui"
    r"|provam?|resolvem?|suprem?|legitimam?|justificam?"
)
SUFICIENCIA_NEGADA_RE = re.compile(
    r"\b(nenhum|nenhuma)\b(?:\s+[\w\-]+,?){0,4}?\s+(?:sozinh[oa]s?\s+|isoladamente\s+|por\s+si\s+(?:s[óo]\s+)?)?"
    r"(?:" + VERBOS_SUFICIENCIA + r")\b"
    r"|\b(nunca|jamais)\s+(?:\w+\s+)?(?:" + VERBOS_SUFICIENCIA + r")\b",
    re.IGNORECASE,
)
# Escopo restrito explícito: a frase limita o que afirma ao material examinado.
ESCOPO_RESTRITO_RE = re.compile(
    r"\b(?:n[ao]s?\s+(?:passagens|trechos|documentos|elementos|pe[çc]as|folhas|p[áa]ginas|registros|certid[õo]es|t[íi]tulos"
    r"|fontes|obras|autos|materiais?|c[óo]pias)\s+(?:\w+\s+)?(?:examinad|analisad|consultad|juntad|dispon[íi]ve|localizad|lid|obtid)\w*"
    r"|nest[ea]\s+(?:exame|an[áa]lise|leitura|confronto|levantamento)"
    r"|at[ée]\s+(?:o\s+momento|aqui|agora|a\s+data\s+deste\s+parecer)"
    r"|n[ao]\s+documenta[çc][ãa]o\s+(?:analisada|examinada|dispon[íi]vel|juntada|consultada)"
    r"|no\s+material\s+(?:examinado|dispon[íi]vel|consultado|analisado))",
    re.IGNORECASE,
)
# "nos autos" como limite do absoluto: "nenhum documento nos autos", "nos autos, nenhum registro".
_AUTOS = r"(?:n[oa]s?\s+autos|no\s+processo|no\s+dossi[êe])"
_ABS = r"(nenhum|nenhuma|nunca|jamais|todos|todas)"
NOS_AUTOS_LIMITE_RE = re.compile(
    r"\b" + _ABS + r"\b(?:\s+[\w\-]+){0,3}?\s+" + _AUTOS + r"\b"
    r"|\b" + _AUTOS + r"\s*,?\s+(?:[\w\-]+\s+){0,2}?" + _ABS + r"\b",
    re.IGNORECASE,
)
ASPAS_RE = re.compile(r"“[^”]*”|\"[^\"]*\"|«[^»]*»|‘[^’]*’")
REFERENCIAS_TITULO_RE = re.compile(r"refer[êe]ncias|bibliografia", re.IGNORECASE)


def _blocos_de_analise(doc: pm.Documento) -> list[pm.Bloco]:
    """Parágrafos fora da lista de referências bibliográficas."""
    out = []
    em_referencias = False
    for b in doc.blocos:
        if b.tipo == "titulo":
            em_referencias = bool(REFERENCIAS_TITULO_RE.search(b.texto))
        elif b.tipo == "par" and not em_referencias:
            out.append(b)
    return out


def checar_absolutos(doc: pm.Documento) -> list[Achado]:
    """Afirmação absoluta ("nunca", "sempre", "todos", "nenhum", "integralmente"...) sem citação na mesma frase.

    Ficam de fora: a palavra dentro de citação literal entre aspas; o absoluto negado por
    verbo epistêmico antes dele ("sem presumir", "não se pode presumir", "não se pode
    inferir que… exclusivamente", "não demonstra que… exclusivamente"); a frase prescritiva
    ("nenhum ato deve ser praticado"); o juízo normativo ou de suficiência negado, em que o
    absoluto rege autoriza/basta/permite/dispensa/impõe/exige/pode/deve/cabe/substitui/
    prova/resolve ("Nenhum indício basta sozinho", "Nenhuma dessas vias autoriza a baixa",
    "jamais pode ser presumido"); a frase de escopo restrito explícito ("nas passagens
    examinadas", "neste exame", "até o momento", "na documentação analisada") e o absoluto
    limitado por "nos autos"/"no processo" ("nenhum documento nos autos", "nos autos,
    nenhum registro"); o
    aposto que resume enumeração (", todos de 1982"); a frase com parêntese de citação
    (p./pp./SEI/fls./art.), que tem suporte declarado; e a lista de referências
    bibliográficas. Continua acusada a afirmação de fato absoluta ("O BDX nunca foi
    senhorio", "todos os lotes foram transmitidos", "a CDI jamais cobrou foros")."""
    out = []
    for b in _blocos_de_analise(doc):
        for f in _frases(b.texto):
            if CITACAO_FRASE_RE.search(f) or PRESCRICAO_RE.search(f) or ESCOPO_RESTRITO_RE.search(f):
                continue
            g = ASPAS_RE.sub(lambda m: " " * len(m.group(0)), f)
            negacoes = [m.end() for m in PRESUNCAO_NEGADA_RE.finditer(g)]
            apostos = {m.start(1) for m in APOSTO_TODOS_RE.finditer(g)}
            suficiencia = {m.start(1) if m.group(1) else m.start(2) for m in SUFICIENCIA_NEGADA_RE.finditer(g)}
            autos = {m.start(1) if m.group(1) else m.start(2) for m in NOS_AUTOS_LIMITE_RE.finditer(g)}
            achados = sorted({m.group(1).lower() for m in ABSOLUTOS_RE.finditer(g)
                              if m.start() not in apostos and m.start() not in suficiencia
                              and m.start() not in autos
                              and not any(n <= m.start() for n in negacoes)})
            if not achados:
                continue
            out.append(Achado("alerta", "absolutos", b.numero,
                              f"afirmação absoluta ({', '.join(achados)}) sem citação na mesma frase: citar a fonte ou "
                              f"calibrar («nada nos autos indica…», «não há documento que…»): «{f[:90]}…»"))
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


# ---------------------------------------------------------------- equivalências de alcance

# Construções que a reescrita troca sem mudar o alcance; aplicadas aos dois lados antes de contar.
EQUIVALENCIAS = [
    # "devem ser observados" ≈ "observam-se" ≈ "observados"
    (re.compile(r"\b(?:deve|devem|dever[áa]|dever[ãa]o)\s+ser\s+(observad[oa]s?)\b", re.IGNORECASE), r"\1"),
    (re.compile(r"\bobserva(?:m)?-se\b", re.IGNORECASE), "observados"),
    # "não se pode" ≈ "não se deve" ≈ "não deve" + infinitivo ≈ "sem que se possa" ≈ "sem" + infinitivo
    (re.compile(r"\b(?:n[ãa]o|tampouco|nem) se deve\b", re.IGNORECASE), "não se pode"),
    (re.compile(r"\b(?:tampouco|nem) se pode\b", re.IGNORECASE), "não se pode"),
    (re.compile(r"\bn[ãa]o (?:deve|devem|dever[áa]|dever[ãa]o)\s+(?=\w+(?:ar|er|ir)\b)", re.IGNORECASE), "não se pode "),
    (re.compile(r"\bsem que se possa\b", re.IGNORECASE), "não se pode"),
    # "se houver" ≈ "havendo"
    (re.compile(r"\bhavendo\b", re.IGNORECASE), "se houver"),
    # "em qualquer caso" ≈ "seja como for" ≈ "de todo modo" ≈ "em todo caso"
    (re.compile(r"\b(?:seja como for|de todo modo|em todo caso|de qualquer (?:forma|modo))\b", re.IGNORECASE), "em qualquer caso"),
]
NAO_BASTA_RE = re.compile(r"\bn[ãa]o (?:bastam?|bastar[áa]|bastaria) para\b", re.IGNORECASE)
NAO_SE_PODE_RE = re.compile(r"\bn[ãa]o se pode\b", re.IGNORECASE)
# "não se pode deduzir X apenas de Y" ≈ "Y não basta para deduzir X": a restrição está embutida em "não basta".
NAO_SE_PODE_APENAS_RE = re.compile(r"\b(n[ãa]o se pode\b[^.;:]{0,80}?)\s(?:apenas|somente|s[óo])\b", re.IGNORECASE)
# "deve ser averbada" ≈ "a averbar" ≈ "averba-se" ≈ "se averba" ≈ "averbando" ≈ "depende da averbação";
# "deve-se distinguir" ≈ "distingue-se"; "deve permitir verificar" ≈ "para verificar":
# o modal sai quando o outro lado traz a forma equivalente do mesmo verbo.
MODAL_PASSIVA_RE = re.compile(r"\b(deve|devem|dever[áa]|dever[ãa]o)\s+ser\s+(\w{3,}?)(?:ad|id)[oa]s?\b", re.IGNORECASE)
MODAL_SE_RE = re.compile(r"\b(deve|devem|dever[áa]|dever[ãa]o)-se\s+(\w{3,}?)(?:ar|er|ir)\b", re.IGNORECASE)
MODAL_PERMITIR_RE = re.compile(r"\b(deve|devem|dever[áa]|dever[ãa]o)\s+permitir\s+(\w{3,}?)(?:ar|er|ir)\b", re.IGNORECASE)


def _forma_equivalente(radical: str, outro: str, finalidade: bool = False) -> bool:
    r = re.escape(radical)
    if finalidade:
        return bool(re.search(rf"\bpara\s+{r}\w*r\b", outro, re.IGNORECASE))
    return bool(re.search(
        rf"(?<!\w){r}\w*-se\b|\ba\s+{r}\w*r\b|(?<!\w){r}\w*r-se\b|(?<![-\w])se\s+{r}\w*|(?<!\w){r}\w*ndo\b"
        rf"|(?<!\w){r}\w*(?:çã|çõ|ment)\w*|(?<!ser )(?<!\w){r}(?:ad|id)[oa]s?\b",
        outro, re.IGNORECASE))


def normalizar_alcance(texto: str, outro: str = "") -> str:
    """Reescreve as construções equivalentes para que a contagem de termos de alcance não acuse troca de forma.

    ``outro`` é o texto do outro lado da comparação: algumas equivalências só valem quando ele
    traz a forma correspondente do mesmo verbo ("deve ser averbada" × "averba-se")."""
    t = pm.sem_negrito(texto)
    o = pm.sem_negrito(outro)
    for rx, rep in EQUIVALENCIAS:
        t = rx.sub(rep, t)
        o = rx.sub(rep, o)
    if NAO_BASTA_RE.search(o) and not NAO_BASTA_RE.search(t):
        t = NAO_SE_PODE_APENAS_RE.sub(r"\1", t)

    def tirar_modal(m: re.Match) -> str:
        if _forma_equivalente(m.group(2), o, m.re is MODAL_PERMITIR_RE):
            return m.group(0)[len(m.group(1)):].lstrip(" -")
        return m.group(0)

    for rx in (MODAL_PASSIVA_RE, MODAL_SE_RE, MODAL_PERMITIR_RE):
        t = rx.sub(tirar_modal, t)
    # forma canônica da negação de inferência: "não se pode deduzir" ≈ "não basta para deduzir" ≈ "sem deduzir"
    t = NAO_BASTA_RE.sub("sem", NAO_SE_PODE_RE.sub("sem", t))
    return t


# ---------------------------------------------------------------- corpo numerado e mapa de origem

def corpo_numerado(doc: pm.Documento) -> dict[int, pm.Bloco]:
    """Número exibido no corpo ("N.") -> bloco. Ponte entre o mapa de origem (números do corpo)
    e os IDs globais que ``parecer_md`` dá em documento de numeração mista ou implícita.

    O corpo é a primeira sequência de parágrafos "N." que começa em 1; uma lista que
    recomeça em 1 depois dela (anexo, itens da conclusão) fica de fora."""
    if doc.numeracao == "explicita":
        return {b.numero: b for b in doc.paragrafos}  # type: ignore[misc]
    out: dict[int, pm.Bloco] = {}
    esperado = 1
    for b in doc.paragrafos:
        n = b.numero_original
        if n is None:
            continue
        if n < esperado:
            break  # outra lista recomeçou
        out[n] = b
        esperado = n + 1
    return out


def texto_proprio(b: pm.Bloco) -> str:
    """Texto do parágrafo sem o "N. " que ``parecer_md`` prefixa em numeração mista."""
    if b.numero_original is not None:
        return re.sub(r"^\d+\.\s+", "", b.texto, count=1)
    return b.texto


def ler_mapa_origem(path: Path) -> dict[int, list[int]]:
    """Lê ``{"novo_para_antigos": {"novo": [antigos]}}``, ``{"novo": [antigos]}`` ou a saída de
    ``verificar_remissoes.py mapear`` (``{"mapa": {"antigo": [novos]}}``, invertida)."""
    dados = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(dados, dict) and "novo_para_antigos" in dados:
        bruto = dados["novo_para_antigos"]
    elif isinstance(dados, dict) and isinstance(dados.get("mapa"), dict):
        bruto = {}
        for antigo, novos in dados["mapa"].items():
            for n in novos or []:
                bruto.setdefault(str(n), []).append(int(antigo))
    elif isinstance(dados, dict):
        bruto = {k: v for k, v in dados.items() if re.fullmatch(r"\d+", str(k))}
    else:
        raise ValueError("mapa de origem: esperado objeto JSON")
    out: dict[int, list[int]] = {}
    for k, v in bruto.items():
        lista = v if isinstance(v, list) else [v]
        out[int(k)] = [int(x) for x in lista]
    return out


@dataclass
class Par:
    """Parágrafo novo e os antigos que ele incorpora (por mapa de origem ou por alinhamento)."""
    novo: pm.Bloco
    rotulo: str
    texto: str
    antigos: list[tuple[pm.Bloco, str]]  # (bloco antigo, rótulo)
    corpo: bool = False

    @property
    def texto_antigo(self) -> str:
        return " ".join(texto_proprio(b) for b, _ in self.antigos)


def pares_por_mapa(doc: pm.Documento, anterior: pm.Documento, mapa: dict[int, list[int]]) -> tuple[list[Par], list[pm.Bloco]]:
    """Pares (novo, antigos de origem) na ordem da nova versão e os blocos antigos sem destino.

    Corpo numerado: pelo mapa. Fora do corpo (título, preâmbulo, referências, anexo):
    por alinhamento de texto, só entre blocos de fora do corpo."""
    cn, ca = corpo_numerado(doc), corpo_numerado(anterior)
    num_n = {id(b): n for n, b in cn.items()}
    num_a = {id(b): n for n, b in ca.items()}
    fora_n = pm.Documento([b for b in doc.paragrafos if id(b) not in num_n])
    fora_a = pm.Documento([b for b in anterior.paragrafos if id(b) not in num_a])
    alinh = pm.alinhar_paragrafos(fora_a, fora_n)
    inv_fora = {v: k for k, v in alinh.items()}
    por_id_a = {b.numero: b for b in fora_a.paragrafos}
    usados: set[int] = set()
    pares = []
    for b in doc.paragrafos:
        if id(b) in num_n:
            n = num_n[id(b)]
            antigos = [(ca[k], f"{k}") for k in mapa.get(n, []) if k in ca]
            pares.append(Par(b, f"{n}", texto_proprio(b), antigos, corpo=True))
        else:
            velho = inv_fora.get(b.numero)
            antigos = [(por_id_a[velho], f"bloco {velho}")] if velho is not None else []
            pares.append(Par(b, f"bloco {b.numero}", b.texto, antigos))
        usados.update(id(x) for x, _ in antigos)
    sem_destino = [b for b in anterior.paragrafos if id(b) not in usados]
    return pares, sem_destino


def pares_por_alinhamento(doc: pm.Documento, anterior: pm.Documento) -> tuple[list[Par], list[pm.Bloco], dict[int, int]]:
    mapa = pm.alinhar_paragrafos(anterior, doc)
    inverso = {v: k for k, v in mapa.items()}
    por_id = {b.numero: b for b in anterior.paragrafos}
    pares = []
    for b in doc.paragrafos:
        velho = inverso.get(b.numero)
        antigos = [(por_id[velho], f"{velho}")] if velho is not None else []
        pares.append(Par(b, f"{b.numero}", b.texto, antigos))
    sem_destino = [b for b in anterior.paragrafos if b.numero not in mapa]
    return pares, sem_destino, mapa


# ---------------------------------------------------------------- comparações com a versão anterior

# Item citado: o símbolo e o que ele identifica. Comparar conjuntos (e não contagens) evita
# alerta quando a fusão de parágrafos elimina a segunda menção da mesma "Matrícula nº 9.876".
_ORD = r"\d+(?:[.,]\d+)*[º°ª]?(?:-[A-Z]{1,3})?"
CITACAO_ITENS = {
    "§§": re.compile(rf"§§\s*({_ORD}(?:\s*(?:,|e|a|[–—-])\s*{_ORD})*)"),
    "§": re.compile(rf"(?<!§)§\s*({_ORD})"),
    "nº": re.compile(r"\bn[º°]\.?\s*(\d[\d./\-]*\d|\d)"),
    "art.": re.compile(rf"\barts?\.\s*({_ORD}(?:\s*(?:,|e|a|[–—-])\s*{_ORD})*)"),
    "inciso romano": re.compile(r"(?<![\w.])([IVXL]+)\b(?=,| e |\))"),
}


def itens_citados(texto: str) -> set[str]:
    out = set()
    for nome, rx in CITACAO_ITENS.items():
        for m in rx.finditer(texto):
            if nome == "art.":
                for x in re.findall(_ORD, m.group(1)):
                    out.add(f"art. {x}")
            elif nome == "§§":
                for x in re.findall(_ORD, m.group(1)):
                    out.add(f"§§ {x}")
            else:
                out.add(f"{nome} {m.group(1)}" if nome != "inciso romano" else f"inciso {m.group(1)}")
    return out


def _vizinhos(pares: list[Par], i: int) -> list[int]:
    """Índices comparados em conjunto com o par i: ±1 e os pares que partilham algum parágrafo de origem
    (divisão: o mesmo antigo alimenta dois novos)."""
    idx = {j for j in (i - 1, i, i + 1) if 0 <= j < len(pares)}
    origem = {id(b) for b, _ in pares[i].antigos}
    if origem:
        idx.update(j for j, p in enumerate(pares) if origem & {id(b) for b, _ in p.antigos})
    return sorted(idx)


def _janela(pares: list[Par], i: int) -> tuple[str, str]:
    """Textos novo e antigo da vizinhança do par i: termo que só mudou de parágrafo não é perda."""
    viz = _vizinhos(pares, i)
    antigos: dict[int, pm.Bloco] = {}
    for j in viz:
        for b, _ in pares[j].antigos:
            antigos.setdefault(id(b), b)
    return " ".join(pares[j].texto for j in viz), " ".join(texto_proprio(b) for b in antigos.values())


def _fusao(pares: list[Par], i: int) -> bool:
    """O par junta dois ou mais antigos, ou o seu antigo foi dividido entre dois ou mais novos."""
    if len(pares[i].antigos) >= 2:
        return True
    origem = {id(b) for b, _ in pares[i].antigos}
    return bool(origem) and sum(1 for p in pares if origem & {id(b) for b, _ in p.antigos}) > 1


def checar_simbolos(antigo: str, novo: str, numero: int | None, janela: tuple[str, str] | None = None,
                    rotulo: str = "") -> list[Achado]:
    """Itens de citação que somem: ex.: "art. 25, §§ 2º e 3º" virar "art. 25, 2º e 3º" (some "§§ 2º"),
    ou "Lei nº 5.827/1972" virar "nessa redação" (some "nº 5.827/1972").

    Compara o conjunto de itens citados (símbolo + número), não a contagem de símbolos:
    a menção repetida que a reescrita elimina não alerta. Com ``janela`` (vizinhos e
    parágrafos que partilham a origem), item que só mudou de parágrafo também não."""
    novos = itens_citados(novo) | (itens_citados(janela[0]) if janela is not None else set())
    perdas = sorted(itens_citados(antigo) - novos)
    if perdas:
        return [Achado("alerta", "citacao", numero, rotulo + "itens de citação ausentes na nova versão: "
                       + ", ".join(f"«{x}»" for x in perdas) + " — conferir se a citação legal ficou íntegra")]
    return []


def _familias() -> dict[str, list[str]]:
    fam: dict[str, list[str]] = {}
    for t in ALCANCE_TERMOS:
        fam.setdefault(FAMILIAS_ALCANCE.get(t, t), []).append(t)
    return fam


def _conta_familia(termos: list[str] | tuple[str, ...], texto: str) -> int:
    return sum(_conta(t, texto) for t in termos)


def checar_alcance(antigo: str, novo: str, numero: int | None, janela: tuple[str, str] | None = None,
                   rotulo: str = "", presenca: bool = False) -> list[Achado]:
    """Termos de alcance e ressalvas que mudam entre o antigo (ou a união dos antigos) e o novo.

    Antes de contar, as construções equivalentes são normalizadas (``normalizar_alcance``) e
    os termos são agrupados em famílias (``FAMILIAS_ALCANCE``: "deve"/"deverá"/"cabe"…).
    Com ``janela``, termo retirado que reaparece nos vizinhos (±1, ou parágrafo que partilha a
    origem) da nova versão, ou acrescentado que veio de um vizinho, é deslocamento e não alerta.
    Com ``presenca`` (fusão ou divisão), conta-se presença e ausência, não o número de
    ocorrências: a fusão elimina a repetição do mesmo modal sem mudar o alcance."""
    a_txt, n_txt = normalizar_alcance(antigo, novo), normalizar_alcance(novo, antigo)
    if janela is not None:
        jn, ja = normalizar_alcance(janela[0], janela[1]), normalizar_alcance(janela[1], janela[0])

    def mudou(termos: list[str], equiv: tuple[str, ...] = ()) -> int:
        def medir(antigo_: str, novo_: str) -> tuple[int, int, int, int]:
            a, b = _conta_familia(termos, antigo_), _conta_familia(termos, novo_)
            ea, eb = _conta_familia(list(equiv), antigo_), _conta_familia(list(equiv), novo_)
            if presenca:
                a, b, ea, eb = min(a, 1), min(b, 1), min(ea, 1), min(eb, 1)
            return a, b, ea, eb

        def saldo(antigo_: str, novo_: str) -> int:
            a, b, ea, eb = medir(antigo_, novo_)
            if b < a and b + eb >= a:  # retirado, mas há equivalente no novo
                return 0
            if b > a and a + ea >= b:  # acrescentado no lugar de um equivalente do antigo
                return 0
            return (b > a) - (b < a)

        d = saldo(a_txt, n_txt)
        if d and janela is not None:
            dj = saldo(ja, jn)
            if dj == 0 or (dj > 0) != (d > 0):
                return 0
        return d

    out = []
    mudancas = []
    for familia, termos in _familias().items():
        d = mudou(termos, EQUIVALENTES_ALCANCE.get(familia, ()))
        if d:
            rot = "/".join(t for t in termos if t in ALCANCE_TERMOS) or termos[0]
            mudancas.append(f"«{rot}» {'acrescentado' if d > 0 else 'retirado'}")
    if mudancas:
        out.append(Achado("alerta", "alcance", numero, rotulo + "mudança de alcance a conferir no mérito: " + ", ".join(mudancas)))
    perdidas = [t for t in RESSALVA_TERMOS if mudou([t]) < 0]
    if perdidas:
        out.append(Achado("alerta", "ressalva", numero, rotulo + f"ressalva possivelmente perdida ({', '.join(perdidas)}): conferir se a "
                                                                 "reescrita manteve a condição ou exceção"))
    return out


STOP = set(
    "a o as os de da do das dos e em no na nos nas que se por para com um uma uns umas ao aos à às é ser "
    "foi não ou mais como sua seu suas seus esse essa este esta isso isto pelo pela pelos pelas já sem há "
    "ela ele elas eles lhe nem mas porém também".split()
)


def _radicais(texto: str) -> list[str]:
    """Palavras de conteúdo reduzidas aos cinco primeiros caracteres (tolera flexão e troca de classe)."""
    return [w[:5] for w in _palavras_norm(texto) if w not in STOP]


def correspondencia_frase(frase: str, paragrafo_ws: list[str], radicais_destino: set[str] | None = None,
                          piso: float = 0.0) -> float:
    """Quanto da frase reaparece no parágrafo: palavras na mesma ordem (difflib); no parágrafo
    de destino indicado pelo mapa (``radicais_destino``), também a fração de radicais presentes.
    ``piso``: abaixo dele o valor exato não interessa (atalho pelo limite superior)."""
    ws = _palavras_norm(frase)
    if not ws:
        return 1.0
    presentes = set(paragrafo_ws)
    teto = sum(w in presentes for w in ws) / len(ws)  # nenhuma subsequência comum passa disto
    if teto > piso:
        sm = difflib.SequenceMatcher(None, ws, paragrafo_ws, autojunk=False)
        c = sum(bl.size for bl in sm.get_matching_blocks()) / len(ws)
    else:
        c = teto
    if radicais_destino is not None:
        rs = _radicais(frase)
        if rs:
            c = max(c, sum(r in radicais_destino for r in rs) / len(rs))
    return c


COBERTURA_INFO = 0.6


def checar_cobertura(anterior: pm.Documento, doc: pm.Documento, numeros_antigos: list[int], limiar: float = 0.5,
                     destinos: dict[int, list[pm.Bloco]] | None = None, rotulos: dict[int, str] | None = None) -> list[Achado]:
    """Frases da versão anterior cujo conteúdo não reaparece na nova (4-gramas): reformuladas ou evaporadas.

    A frase abaixo do limiar vira INFO quando reaparece com 60% ou mais de correspondência
    em algum parágrafo novo (``correspondencia_frase``): palavras na mesma ordem em qualquer
    parágrafo; radicais no destino que o mapa ou o alinhamento indica e nos vizinhos dele."""
    pars_novos = doc.paragrafos
    novos = _ngramas(_palavras_norm(" ".join(b.texto for b in pars_novos)))
    ws_novos = [_palavras_norm(b.texto) for b in pars_novos]
    pos = {id(b): i for i, b in enumerate(pars_novos)}
    antigos = anterior.por_numero()
    out = []
    for n in numeros_antigos:
        rot = (rotulos or {}).get(n, str(n))
        dest_idx: set[int] = set()
        for b in (destinos or {}).get(n, []):
            i = pos.get(id(b))
            if i is not None:
                dest_idx.update(range(max(0, i - 1), min(len(pars_novos), i + 2)))
        rad_dest = {i: set(_radicais(pars_novos[i].texto)) for i in dest_idx}
        for f in _frases(antigos.get(n, "")):
            ws = _palavras_norm(f)
            if len(ws) < 8:
                continue
            gs = _ngramas(ws)
            cobertura = len(gs & novos) / len(gs)
            if cobertura >= limiar:
                continue
            melhor, onde = 0.0, None
            for i, pw in enumerate(ws_novos):
                c = correspondencia_frase(f, pw, rad_dest.get(i), piso=melhor)
                if c > melhor:
                    melhor, onde = c, i
            destino = (destinos or {}).get(n)
            local = destino[0].numero if destino else (n if destinos is None else None)
            if melhor >= COBERTURA_INFO and onde is not None:
                out.append(Achado("info", "cobertura", local, f"frase do antigo parágrafo {rot} reformulada: {melhor:.0%} de "
                                                              f"correspondência no novo {_rot_novo(pars_novos[onde], doc)}: «{f[:90]}…»"))
            else:
                perto = f" (no máximo {melhor:.0%} em um só parágrafo)" if onde is not None else ""
                out.append(Achado("alerta", "cobertura", local, f"frase do antigo parágrafo {rot} com {cobertura:.0%} de correspondência "
                                                                f"na nova versão{perto} — reformulada ou evaporou: «{f[:90]}…»"))
    return out


def _rot_novo(b: pm.Bloco, doc: pm.Documento) -> str:
    return f"{b.numero_original} (bloco {b.numero})" if b.numero_original is not None and doc.numeracao != "explicita" else f"{b.numero}"


def checar_renumeracao(doc: pm.Documento, anterior: pm.Documento, revisadas: set[int] | None = None,
                       mapa_origem: dict[int, list[int]] | None = None) -> list[Achado]:
    """Comparação com a versão anterior: rescan, alcance, ressalva, símbolos de citação, remissões e cobertura.

    Sem ``mapa_origem``, cada parágrafo novo é comparado ao antigo alinhado por texto. Com ele
    (números do corpo numerado), o novo é comparado à UNIÃO dos antigos de origem — o que evita
    alertas falsos quando a reescrita funde ou divide parágrafos."""
    if mapa_origem is not None:
        pares, sem_destino = pares_por_mapa(doc, anterior, mapa_origem)
        mapa_alinh: dict[int, int] = {}
    else:
        pares, sem_destino, mapa_alinh = pares_por_alinhamento(doc, anterior)
    ca = corpo_numerado(anterior)
    num_a = {id(b): n for n, b in ca.items()}
    if mapa_origem is not None:
        rot_a = {b.numero: (f"{num_a[id(b)]}" if id(b) in num_a else f"bloco {b.numero}") for b in anterior.paragrafos}
    else:
        rot_a = {b.numero: f"{b.numero}" for b in anterior.paragrafos}
    antigos_txt = anterior.por_numero()
    out: list[Achado] = []
    alterados_antigos: list[int] = []
    destinos: dict[int, list[pm.Bloco]] = {}
    mudou = any(k != v for k, v in mapa_alinh.items())
    for i, p in enumerate(pares):
        b = p.novo
        for velho, _ in p.antigos:
            destinos.setdefault(velho.numero, []).append(b)  # type: ignore[arg-type]
        if not p.antigos:
            msg = "parágrafo novo: varrer contra repetição e contradição"
            if mapa_origem is not None and p.corpo:
                msg = f"parágrafo {p.rotulo} sem origem no mapa: varrer contra repetição e contradição"
            out.append(Achado("info", "rescan", b.numero, msg))
            continue
        velho_txt = p.texto_antigo if mapa_origem is not None else antigos_txt[p.antigos[0][0].numero]
        novo_txt = p.texto if mapa_origem is not None else b.texto
        if velho_txt != novo_txt:
            origem = "+".join(r for _, r in p.antigos)
            rotulo = f"[novo {p.rotulo} ← {origem}] " if mapa_origem is not None else ""
            out.append(Achado("info", "rescan", b.numero, f"parágrafo alterado (era o {origem}): varrer contra repetição e contradição"))
            janela = _janela(pares, i)
            out += checar_alcance(velho_txt, novo_txt, b.numero, janela, rotulo, _fusao(pares, i))
            out += checar_simbolos(velho_txt, novo_txt, b.numero, janela, rotulo)
            alterados_antigos.extend(v.numero for v, _ in p.antigos)  # type: ignore[misc]
        if mapa_origem is not None:
            if p.corpo:
                out += _remissoes_por_mapa(p, mapa_origem, revisadas)
            continue
        if not mudou or doc.numeracao != "explicita" or anterior.numeracao != "explicita":
            continue
        velho = p.antigos[0][0].numero
        rem_velhas = [n for _, ns in pm.remissoes(antigos_txt[velho]) for n in ns]
        rem_novas = [n for _, ns in pm.remissoes(b.texto) for n in ns]
        esperadas = [mapa_alinh.get(n, n) for n in rem_velhas]
        if rem_velhas and len(rem_velhas) == len(rem_novas) and esperadas != rem_novas and b.numero in (revisadas or set()):
            out.append(Achado("info", "renumeracao", b.numero,
                              f"remissões {rem_novas} revisadas manualmente (o mapa automático daria {esperadas})"))
        elif rem_velhas and len(rem_velhas) == len(rem_novas) and esperadas != rem_novas:
            out.append(Achado(
                "bloqueante", "renumeracao", b.numero,
                f"remissões {rem_novas} deveriam ser {esperadas} após a renumeração (eram {rem_velhas} no parágrafo {velho})",
            ))
    suprimidos = [b.numero for b in sem_destino]
    for n in suprimidos:
        out.append(Achado("info", "rescan", None, f"parágrafo {rot_a.get(n, n)} da versão anterior sem correspondente na nova"))
    alvo = list(dict.fromkeys(alterados_antigos + suprimidos))
    out += checar_cobertura(anterior, doc, alvo, destinos=destinos, rotulos=rot_a)  # type: ignore[arg-type]
    return out


def _remissoes_por_mapa(p: Par, mapa: dict[int, list[int]], revisadas: set[int] | None) -> list[Achado]:
    """Remissões do parágrafo novo contra as da união dos antigos, convertidas pelo mapa (informativo).

    Com fusão e divisão, a matéria remetida pode ter ido para parágrafo diferente do destino
    do antigo citado; por isso a divergência é só INFO, para conferir com
    ``verificar_remissoes.py conferir``/``mapear``. Antigo citado que foi dividido não é comparado."""
    antigo_para_novos: dict[int, list[int]] = {}
    for novo, antigos in mapa.items():
        for a in antigos:
            antigo_para_novos.setdefault(a, []).append(novo)
    rem_velhas = [n for _, ns in pm.remissoes(p.texto_antigo) for n in ns]
    rem_novas = [n for _, ns in pm.remissoes(p.texto) for n in ns]
    if not rem_velhas or any(len(antigo_para_novos.get(n, [])) != 1 for n in rem_velhas):
        return []
    esperadas = list(dict.fromkeys(antigo_para_novos[n][0] for n in rem_velhas))
    novas = list(dict.fromkeys(rem_novas))
    if set(esperadas) == set(novas) or len(esperadas) != len(novas) or int(p.rotulo) in (revisadas or set()):
        return []
    return [Achado("info", "renumeracao", p.novo.numero,
                   f"[novo {p.rotulo}] remissões {novas}; pelo destino de cada antigo citado seriam {esperadas} "
                   f"(eram {list(dict.fromkeys(rem_velhas))} nos antigos {'+'.join(r for _, r in p.antigos)}): "
                   "conferir com verificar_remissoes.py se a matéria remetida foi para outro parágrafo")]


def contar_paginas_pdf(path: Path) -> int:
    try:
        from pypdf import PdfReader  # type: ignore

        return len(PdfReader(str(path)).pages)
    except ImportError:
        return len(re.findall(rb"/Type\s*/Page(?!s)", path.read_bytes()))


def checar_refutadas_doc(doc: pm.Documento, refutadas: dict) -> list[Achado]:
    """Afirmação já refutada (``checar_refutadas.py``) que reaparece na minuta: bloqueante."""
    linhas = [(b.linha, b.texto, b.numero) for b in doc.blocos]
    out = []
    for a in cr.checar_linhas(refutadas, [(lin, txt) for lin, txt, _ in linhas], "minuta"):
        numero = next((n for lin, _, n in linhas if lin == a.linha), None)
        out.append(Achado("bloqueante", "refutada", numero,
                          f"[{a.id}] afirmação refutada reaparece (linha {a.linha}): «{a.trecho}» — {a.por_que}"
                          + (f"; correto: {a.correto}" if a.correto else "") + (f" ({a.fonte})" if a.fonte else "")))
    return out


def auditar(doc: pm.Documento, cfg: dict, anterior: pm.Documento | None = None, travados: list[dict] | None = None,
            proibidos: list[str] | None = None, pdf: Path | None = None, max_paginas: int | None = None,
            revisadas: set[int] | None = None, mapa_origem: dict[int, list[int]] | None = None,
            refutadas: dict | None = None) -> list[Achado]:
    fecho = cfg.get("fecho")
    estilo = cfg.get("estilo")
    est = ESTILOS.get(estilo or "", {})
    achados = []
    achados += checar_numeracao(doc)
    achados += checar_palavras(doc, cfg.get("max_palavras"))
    achados += checar_ritmo(doc, est.get("teto_alvo") or cfg.get("max_palavras"))
    if cfg.get("exige_numeracao") and doc.numeracao == "implicita":
        achados.append(Achado("bloqueante", "numeracao", None,
                              "o perfil exige parágrafos numerados (numeração automática), e o documento não tem nenhum"))
    achados += checar_resposta_objetiva(doc, bool(est.get("resposta_objetiva")), estilo or "")
    achados += checar_anexo_exigido(doc, bool(cfg.get("exige_anexo")))
    if estilo:
        achados += checar_teto_estilo(doc, est.get("teto_alvo"), cfg.get("max_palavras"), estilo)
        achados += checar_ementa_estruturada(doc, bool(est.get("ementa_estruturada")), estilo)
        achados += checar_transcricoes(doc, est.get("transcricoes_por_secao"), bool(cfg.get("veda_transcricao")), estilo)
        achados += checar_frases_estilo(doc, est.get("frase_media"), est.get("frase_max"), estilo)
        achados += checar_intensificadores(doc)
    achados += checar_fecho(doc, fecho)
    achados += checar_remissoes(doc)
    achados += checar_concordancia_remissoes(doc)
    achados += checar_anexos_nomeados(doc, bool(cfg.get("anexos_nomeados")))
    achados += checar_marcadores(doc, fecho, proibidos or [])
    achados += checar_conclusao(doc, cfg.get("rotulos_conclusao", []), bool(est.get("rotulo_sem_negrito")))
    achados += checar_assinatura(doc, fecho, cfg.get("assinatura", []), cfg.get("assinatura_alternativa"))
    achados += checar_julgados_repetidos(doc)
    achados += checar_frases_repetidas(doc)
    achados += checar_epistemico(doc)
    achados += checar_absolutos(doc)
    if refutadas:
        achados += checar_refutadas_doc(doc, refutadas)
    if travados:
        achados += checar_travados(doc, travados)
    if anterior is not None:
        achados += checar_renumeracao(doc, anterior, revisadas, mapa_origem)
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
    p.add_argument("--exige-anexo", action="store_true",
                   help="a consulta pede minuta ou peça anexa: bloqueia o parecer sem seção de Anexo")
    p.add_argument("--estilo", choices=sorted(ESTILOS),
                   help="estilo de redação (estilos-de-redacao.md): executivo exige resposta objetiva no início e "
                        "alerta parágrafo acima de 90 palavras; clássico admite uma transcrição curta por seção, "
                        "salvo perfil que a vede")
    p.add_argument("--fecho", help="sobrepõe o fecho do perfil")
    p.add_argument("--anterior", type=Path, help="versão anterior, para checar renumeração e listar o que varrer")
    p.add_argument("--mapa-origem", type=Path,
                   help='JSON {"novo_para_antigos": {"novo": [antigos]}} (números do corpo numerado) ou saída de '
                        "verificar_remissoes.py mapear: compara o parágrafo novo com a união dos antigos de origem")
    p.add_argument("--refutadas", type=Path,
                   help="registro de afirmações refutadas (formato de checar_refutadas.py): acerto vira bloqueante")
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
    if args.estilo:
        cfg["estilo"] = args.estilo
    if args.exige_anexo:
        cfg["exige_anexo"] = True
    doc = pm.ler(args.minuta)
    anterior = pm.ler(args.anterior) if args.anterior else None
    travados = json.loads(args.travados.read_text(encoding="utf-8")) if args.travados else None
    revisadas = {int(x) for x in args.remissoes_revisadas.split(",") if x.strip()}
    if args.mapa_origem and anterior is None:
        print("--mapa-origem exige --anterior", file=sys.stderr)
        return 2
    try:
        mapa_origem = ler_mapa_origem(args.mapa_origem) if args.mapa_origem else None
        refutadas = cr.carregar(args.refutadas) if args.refutadas else None
    except (OSError, ValueError) as e:
        print(f"erro: {e}", file=sys.stderr)
        return 2
    achados = auditar(doc, cfg, anterior, travados, args.proibido, args.pdf, args.max_paginas, revisadas,
                      mapa_origem, refutadas)
    mostrar = [a for a in achados if not (args.sem_info and a.severidade == "info")]
    print(relatorio(args.minuta, doc, mostrar))
    if args.json:
        args.json.write_text(json.dumps({
            "arquivo": str(args.minuta),
            "sha256": doc.sha256,
            "perfil": args.perfil,
            "estilo": args.estilo,
            "aprovada": not any(a.severidade == "bloqueante" for a in achados),
            "achados": [asdict(a) for a in achados],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if any(a.severidade == "bloqueante" for a in achados) else 0


if __name__ == "__main__":
    sys.exit(main())
