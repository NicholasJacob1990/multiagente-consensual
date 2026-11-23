#!/usr/bin/env python3
"""Monta o pacote de auditoria travado por hash e confere a resposta do auditor.

O pacote reúne instruções, dossiê, adendo de fontes literais e minuta, cada parte
delimitada e com seu SHA-256. A resposta do auditor tem de declarar o hash da
minuta (``HASH_RECEBIDO: <hash>``) numa das 20 primeiras linhas, no começo da
linha ou logo depois do preâmbulo que alguns CLIs narram: resposta sem ele, ou com
outro, foi dada sobre outra versão (ou sobre anexo desatualizado) e é descartada.
Isso já aconteceu duas vezes no mesmo caso; o hash torna o erro detectável na hora.

``verificar`` separa três coisas: o hash (declarado e certo), a resposta (sem
declaração de falha logo no início e com os trechos de ``--exigir``) e a
cobertura (hash e resposta válidos e, se o pacote tem comentários, também o
``HASH_COMENTARIOS``). Só sai com 0 quando a cobertura é certificada.

Com ``--anterior``, monta o pacote só com as diferenças (parágrafos alterados ou
novos, com o vizinho de cada lado), para rodadas intermediárias mais baratas.

Com ``--comentarios`` (um ou mais arquivos de texto, como a saída de
``exportar_comentarios.py``), o pacote ganha a parte "COMENTÁRIOS E RESPOSTAS",
com hash próprio no cabeçalho. O auditor que certificar os comentários repete
``HASH_COMENTARIOS: <hash>``; ``verificar`` recusa a resposta que citar outro hash
ou que não o citar (salvo ``--comentarios-opcionais``).

Com ``--numerado DOCX``, o pacote ganha a parte "TEXTO NUMERADO DO DOCX (§N)": o
.docx convertido por ``docx_para_md.py --prefixo-paragrafo``, em que cada parágrafo do
corpo traz o número "§N" do Word escrito à frente e a primeira linha traz o nome e o
SHA-256 do .docx. O cabeçalho do pacote ganha ``SHA-256 do DOCX: <hash>`` e a
instrução "Cite os parágrafos pelo número §N deste arquivo e repita o SHA-256 do DOCX
auditado" (linha ``HASH_DOCX: <hash>``). Motivo: um auditor externo extraiu o texto do
.docx sem contar o §1 (que começa com rótulo em negrito), deslocou toda a numeração em
−1 e apontou como erradas remissões certas; e declarou o hash de outra cópia.
``verificar`` recusa a resposta que citar outro ``HASH_DOCX`` ("o auditor leu outra
cópia") ou que não o citar (salvo ``--docx-opcional``). Achados de remissão já
recebidos se conferem com ``conferir_achados_externos.py``. Só com ``--numerado`` (sem
``--minuta``), a minuta do pacote é o próprio texto numerado, numa cópia só; com os
dois, vão a minuta e o texto numerado (e ``montar`` avisa se o número de parágrafos
diverge). Pacotes sem ``--numerado`` ficam como antes.

Exemplos::

    pacote_auditoria.py montar --minuta v30.md --dossie dossie.md --adendo adendo.md --instrucoes prompt.md --saida pacote.md
    pacote_auditoria.py montar --minuta v31.md --anterior v30.md --instrucoes prompt.md --saida pacote_diff.md
    pacote_auditoria.py montar --minuta v31.md --comentarios comentarios.txt --saida pacote.md
    pacote_auditoria.py montar --numerado v18.docx --dossie dossie.md --saida pacote.md
    pacote_auditoria.py montar --minuta v18.md --numerado v18.docx --saida pacote.md
    pacote_auditoria.py verificar --pacote pacote.md --resposta resposta_gemini.md
"""

from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parent))
import docx_para_md as dm  # noqa: E402
import parecer_md as pm  # noqa: E402

CONTRATO = "pacote_auditoria_v1"
CHARS_POR_TOKEN = 3.5
ALERTA_TOKENS = 120_000
HASH_RE = re.compile(r"HASH(?:_RECEBIDO)?:\s*`?([0-9a-f]{64})`?", re.IGNORECASE)
LINHAS_PREAMBULO = 20
REF_CORRECAO_RE = re.compile(r"corre[çc][ãa]o\s*\((?P<rom>[ivx]{1,5})\)[^§\n]{0,30}?(?:§|par[áa]grafo)\s*(?P<n>\d+)", re.IGNORECASE)
REF_PAR_INSTR_RE = re.compile(r"(?:§§?|par[áa]grafos?)\s*(\d+)(?:\s*(?:a|e)\s*(\d+))?", re.IGNORECASE)
CAB_RE = re.compile(r"^SHA-256 da minuta: ([0-9a-f]{64})$", re.M)
HASH_COMENTARIOS_RE = re.compile(r"HASH_COMENTARIOS:\s*`?([0-9a-f]{64})`?", re.IGNORECASE)
CAB_COMENTARIOS_RE = re.compile(r"^SHA-256 dos comentários: ([0-9a-f]{64})$", re.M)
HASH_DOCX_RE = re.compile(r"HASH_DOCX:\s*`?([0-9a-f]{64})`?", re.IGNORECASE)
CAB_DOCX_RE = re.compile(r"^SHA-256 do DOCX: ([0-9a-f]{64})$", re.M)
INSTRUCAO_NUMERADO = "Cite os parágrafos pelo número §N deste arquivo e repita o SHA-256 do DOCX auditado"

INSTRUCOES_PADRAO = """Você é auditor jurídico independente. Leia integralmente a minuta e confira cada afirmação
de direito no adendo de fontes literais; o que não estiver no adendo, trate como não verificado
e diga isso, em vez de presumir. Não afirme que um dispositivo não existe, não tem incisos ou não
alcança um caso sem ter lido o texto integral dele no adendo. Separe certeza de estimativa."""


def parte(nome: str, texto: str) -> str:
    sha = pm.sha256_texto(texto)
    return f"===== INÍCIO: {nome} (sha256 {sha}) =====\n{texto.rstrip()}\n===== FIM: {nome} =====\n"


def diferencas(anterior: pm.Documento, atual: pm.Documento, palavras_indice: int = 14) -> str:
    mapa = pm.alinhar_paragrafos(anterior, atual)
    inverso = {v: k for k, v in mapa.items()}
    antigos, novos = anterior.por_numero(), atual.por_numero()
    alterados = [n for n in novos if n not in inverso or antigos[inverso[n]] != novos[n]]
    removidos = [n for n in antigos if n not in mapa]
    mostrar = sorted({v for n in alterados for v in (n - 1, n, n + 1) if v in novos})
    linhas = [
        f"Versão anterior: sha256 {anterior.sha256}. Parágrafos alterados ou novos: "
        + (", ".join(map(str, alterados)) or "nenhum")
        + (f". Parágrafos suprimidos da anterior: {', '.join(map(str, removidos))}" if removidos else "")
        + ". Os demais parágrafos estão idênticos aos da versão anterior; a versão integral está disponível a pedido.",
        "",
    ]
    for n in mostrar:
        if n in alterados:
            if n in inverso:
                linhas += [f"[{n} — ALTERADO; era o {inverso[n]}] ANTES: {antigos[inverso[n]]}", f"[{n}] DEPOIS: {novos[n]}", ""]
            else:
                linhas += [f"[{n} — NOVO] {novos[n]}", ""]
        else:
            linhas += [f"[{n} — contexto, sem alteração] {novos[n]}", ""]
    for n in removidos:  # reescritos a ponto de não alinhar, ou suprimidos: o auditor precisa do texto anterior
        linhas += [f"[{n} da versão anterior — SUPRIMIDO OU REESCRITO EM OUTRO PARÁGRAFO] {antigos[n]}", ""]
    # índice da versão integral: permite conferir remissões a parágrafos que não vieram no pacote
    linhas += ["ÍNDICE DA VERSÃO INTEGRAL (primeiras palavras de cada parágrafo, para conferir remissões):", ""]
    for n, t in novos.items():
        ws = pm.sem_negrito(t).split()
        linhas.append(f"[{n}] {' '.join(ws[:palavras_indice])}{' …' if len(ws) > palavras_indice else ''}")
    return "\n".join(linhas)


def texto_comentarios(arquivos: list[Path]) -> str:
    """Junta os arquivos de comentários; com mais de um, cada um vem sob o próprio nome."""
    if len(arquivos) == 1:
        return arquivos[0].read_text(encoding="utf-8")
    return "\n".join(f"### {a.name}\n\n{a.read_text(encoding='utf-8').rstrip()}\n" for a in arquivos)


def texto_numerado(docx: Path) -> tuple[str, str]:
    """(SHA-256 do .docx, texto com "§N" explícito) para a parte TEXTO NUMERADO DO DOCX."""
    return dm.sha256_arquivo(docx), dm.converter(docx, prefixo_paragrafo=True)


def conferir_numerado(minuta: pm.Documento, docx: Path) -> list[str]:
    """Avisa quando a minuta .md e o .docx numerado não têm o mesmo número de parágrafos (outra versão?)."""
    if minuta.numeracao == "implicita" or not minuta.paragrafos:
        return []
    nums = [b.numero_original if minuta.numeracao == "mista" else b.numero for b in minuta.paragrafos]
    n_md = max((n for n in nums if n), default=0)  # o maior número escrito (listas anexas recomeçam em 1)
    n_docx = sum(1 for p in dm.paragrafos(docx) if p.corpo)
    if n_md != n_docx:
        return [f"a minuta tem {n_md} parágrafos numerados e o corpo do DOCX numerado tem {n_docx}; "
                "confira se são a mesma versão"]
    return []


def documento_base(minuta: Path | None, numerado: Path | None) -> pm.Documento:
    """A minuta lida pelo ``parecer_md``: o .md dado ou, sem ele, a conversão padrão ("N.") do DOCX numerado."""
    if minuta is not None:
        return pm.ler(minuta)
    if numerado is None:
        raise ValueError("informe --minuta ou --numerado")
    return pm.parse(dm.converter(numerado))


def montar(minuta: Path | None, instrucoes: str, dossie: Path | None = None, adendo: Path | None = None,
           anterior: Path | None = None, formato_resposta: str | None = None,
           comentarios: list[Path] | None = None, numerado: Path | None = None) -> str:
    """Sem ``minuta`` e com ``numerado``, a minuta do pacote é o próprio texto numerado (uma cópia só, com o
    hash dele como ``SHA-256 da minuta``); com os dois, vão a minuta e, depois, o texto numerado."""
    doc = documento_base(minuta, numerado)
    coment = texto_comentarios(comentarios) if comentarios else None
    sha_docx, txt_numerado = texto_numerado(numerado) if numerado else (None, None)
    so_numerado = minuta is None and txt_numerado is not None
    corpo_numerado = f"{INSTRUCAO_NUMERADO} (`HASH_DOCX: {sha_docx}`).\n\n{txt_numerado}" if txt_numerado else None
    sha_minuta = pm.sha256_texto(corpo_numerado) if so_numerado else doc.sha256  # = sha256 da parte MINUTA
    blocos = [
        f"# Pacote de auditoria — {CONTRATO}",
        "",
        f"SHA-256 da minuta: {sha_minuta}",
    ]
    if coment is not None:
        blocos.append(f"SHA-256 dos comentários: {pm.sha256_texto(coment)}")
    if sha_docx:
        blocos.append(f"SHA-256 do DOCX: {sha_docx}")
    blocos += [
        "",
        "Regra de recebimento: a primeira linha da sua resposta deve ser exatamente",
        f"`HASH_RECEBIDO: {sha_minuta}`",
        "Resposta sem essa linha, ou com outro hash, será descartada como feita sobre outra versão.",
    ]
    if coment is not None:
        blocos += [
            "Se você certificar os comentários e respostas, inclua também, logo abaixo, a linha",
            f"`HASH_COMENTARIOS: {pm.sha256_texto(coment)}`",
        ]
    if sha_docx:
        blocos += [
            f"{INSTRUCAO_NUMERADO} ({numerado.name}), em linha própria logo abaixo:",
            f"`HASH_DOCX: {sha_docx}`",
            "A numeração §N é a do Word no corpo do parecer; não reconte os parágrafos a partir de outra extração.",
        ]
    blocos += ["", parte("INSTRUÇÕES", instrucoes)]
    if formato_resposta:
        blocos.append(parte("FORMATO DA RESPOSTA", formato_resposta))
    if dossie:
        blocos.append(parte("DOSSIÊ", dossie.read_text(encoding="utf-8")))
    if adendo:
        blocos.append(parte("ADENDO DE FONTES LITERAIS", adendo.read_text(encoding="utf-8")))
    if anterior:
        blocos.append(parte("MINUTA — SÓ AS DIFERENÇAS", diferencas(pm.ler(anterior), doc)))
    elif so_numerado:
        blocos.append(parte("MINUTA — TEXTO NUMERADO DO DOCX (§N)", corpo_numerado))
    else:
        blocos.append(parte("MINUTA", doc.bruto))
    if corpo_numerado is not None and not (so_numerado and not anterior):
        blocos.append(parte("TEXTO NUMERADO DO DOCX (§N)", corpo_numerado))
    if coment is not None:
        blocos.append(parte("COMENTÁRIOS E RESPOSTAS", coment))
    return "\n".join(blocos)


def hash_do_pacote(texto: str) -> str | None:
    m = CAB_RE.search(texto)
    return m.group(1) if m else None


def hash_comentarios_do_pacote(texto: str) -> str | None:
    m = CAB_COMENTARIOS_RE.search(texto)
    return m.group(1) if m else None


def hash_docx_do_pacote(texto: str) -> str | None:
    m = CAB_DOCX_RE.search(texto)
    return m.group(1) if m else None


# A linha do hash é uma declaração do auditor: começa nela (depois de marcação como "> ", "**", "`") ou vem
# grudada no fim de uma frase de preâmbulo ("…a contagem.HASH: …", como o CLI do Grok narra). Citada no
# meio de outra frase ("Pedido: HASH_RECEBIDO: …"), não vale.
_INICIO_DECLARACAO = r"(?:^[\s>*_`#-]*|(?<=[.!?])\s*)"
# recusa do próprio trabalho (não achado de auditoria, como "não foi possível localizar o art. 9º na fonte")
RECUSA_RE = re.compile(
    r"\bn[ãa]o\s+(?:executei|realizei|fiz|consegui|pude|foi\s+poss[íi]vel)(?:\s+\w+){0,2}?\s+"
    r"(?:a\s+auditoria|auditar|a\s+an[áa]lise|analisar|ler\s+(?:o\s+pacote|a\s+minuta|os\s+arquivos)|acessar|abrir)\b"
    r"|\b(?:unable\s+to|could\s+not|cannot|can't)\s+(?:complete|perform|read|access|open)\b", re.IGNORECASE)
PALAVRAS_MINIMAS = 30


def _declaracao(resposta: str, rx: re.Pattern) -> tuple[int, re.Match] | None:
    primeiras = [l for l in resposta.strip().split("\n") if l.strip()][:LINHAS_PREAMBULO]
    for k, l in enumerate(primeiras):
        for m in rx.finditer(l):
            if re.search(_INICIO_DECLARACAO + r"$", l[:m.start()]):
                return k, m
    return None


def verificar_comentarios(resposta: str, esperado: str) -> tuple[bool | None, str]:
    """True: certificou os comentários enviados; False: citou outro hash; None: não certificou."""
    achado = _declaracao(resposta, HASH_COMENTARIOS_RE)
    if achado:
        m = achado[1]
        if m.group(1).lower() == esperado:
            return True, "hash dos comentários confere"
        return False, f"hash dos comentários divergente: a resposta cita {m.group(1)[:16]}…, esperado {esperado[:16]}…"
    return None, "a resposta não certifica os comentários (sem HASH_COMENTARIOS)"


def verificar_docx(resposta: str, esperado: str) -> tuple[bool | None, str]:
    """True: repetiu o SHA-256 do DOCX numerado; False: citou outro (leu outra cópia); None: não citou."""
    achado = _declaracao(resposta, HASH_DOCX_RE)
    if achado:
        m = achado[1]
        if m.group(1).lower() == esperado:
            return True, "hash do DOCX confere"
        return False, (f"hash do DOCX divergente: a resposta cita {m.group(1)[:16]}…, esperado {esperado[:16]}… "
                       "(o auditor leu outra cópia; a numeração §N dele pode não ser a deste DOCX)")
    return None, "a resposta não repete o SHA-256 do DOCX numerado (sem HASH_DOCX)"


def verificar(resposta: str, esperado: str) -> tuple[bool, str]:
    """Procura a declaração do hash nas primeiras linhas; tolera o preâmbulo que alguns CLIs narram antes dele.
    Só confere o hash: se a resposta é uma auditoria de fato, diz ``validar_resposta``."""
    achado = _declaracao(resposta, HASH_RE)
    if not achado:
        return False, f"a resposta não declara o hash nas primeiras {LINHAS_PREAMBULO} linhas"
    k, m = achado
    if m.group(1).lower() != esperado:
        return False, f"hash divergente: a resposta cita {m.group(1)[:16]}…, esperado {esperado[:16]}…"
    aviso = " (precedido de preâmbulo do CLI; descartá-lo antes de usar a resposta)" if k or m.start() > 0 else ""
    return True, "hash confere" + aviso


def validar_resposta(resposta: str, exigir: list[str] | None = None) -> tuple[bool, list[str]]:
    """Hash certo não prova auditoria feita: recusa a resposta que declara falha logo depois do hash ou
    não traz os trechos exigidos (por exemplo, "Decisão:"); avisa quando o corpo é curto demais."""
    corpo = HASH_DOCX_RE.sub("", HASH_COMENTARIOS_RE.sub("", HASH_RE.sub("", resposta)))
    msgs, ok = [], True
    inicio = " ".join(corpo.split()[:80])
    if RECUSA_RE.search(inicio):
        ok = False
        msgs.append(f"a resposta declara falha ou recusa logo no início: «{RECUSA_RE.search(inicio).group(0)}»")
    for t in exigir or []:
        if t.casefold() not in resposta.casefold():
            ok = False
            msgs.append(f"a resposta não traz «{t}», exigido nesta auditoria")
    if len(corpo.split()) < PALAVRAS_MINIMAS:
        msgs.append(f"atenção: corpo com menos de {PALAVRAS_MINIMAS} palavras; conferir se a auditoria foi feita")
    return ok, msgs


def conferir_instrucoes(instrucoes: str, doc: pm.Documento) -> list[str]:
    """Remissões a parágrafos escritas à mão nas instruções: existem e apontam o grupo certo da conclusão?"""
    pars = doc.por_numero()
    if doc.numeracao == "mista":  # o parser renumera tudo quando há linhas sem número; vale a numeração escrita
        pars = {b.numero_original: b.texto for b in doc.paragrafos if getattr(b, "numero_original", None)}
    maior = max(pars) if pars else 0
    avisos = []
    for m in REF_PAR_INSTR_RE.finditer(instrucoes):
        for g in m.groups():
            if g and int(g) > maior:
                avisos.append(f"instruções citam «{m.group(0)}», mas a minuta tem {maior} parágrafos")
    for m in REF_CORRECAO_RE.finditer(instrucoes):
        n, rom = int(m.group("n")), m.group("rom").lower()
        if n in pars and f"({rom})" not in pars[n].lower():
            marca = f"({rom}) "

            def peso(t: str) -> int:  # a lista da conclusão ("impõe-se: (i) …") pesa mais que a menção avulsa
                return 2 * bool(re.search(r"impõe-se|necessárias?\s+(?:no|na|ainda)|^\d+\.\s*Corre", t, re.I)) + ("necessári" in t)
            onde = sorted((k for k, t in pars.items() if marca in t.lower()), key=lambda k: -peso(pars[k]))
            dica = f"; o ({rom}) está no § {onde[0]}" if onde else ""
            avisos.append(f"instruções põem a correção ({rom}) no § {n}, que não a contém{dica}")
    return avisos


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("montar")
    m.add_argument("--minuta", type=Path,
                   help="minuta em Markdown; dispensável com --numerado (a minuta passa a ser o texto numerado do DOCX)")
    m.add_argument("--instrucoes", type=Path, help="prompt do auditor; padrão: instruções mínimas de auditoria cega")
    m.add_argument("--formato-resposta", type=Path)
    m.add_argument("--dossie", type=Path)
    m.add_argument("--adendo", type=Path)
    m.add_argument("--anterior", type=Path, help="monta só com as diferenças em relação a esta versão")
    m.add_argument("--comentarios", type=Path, nargs="+",
                   help="arquivos de texto com comentários e respostas (ex.: saída de exportar_comentarios.py)")
    m.add_argument("--numerado", type=Path, metavar="DOCX",
                   help='inclui o texto do .docx com "§N" explícito e exige do auditor o SHA-256 do DOCX (HASH_DOCX)')
    m.add_argument("--saida", type=Path, required=True)
    v = sub.add_parser("verificar")
    g = v.add_mutually_exclusive_group(required=True)
    g.add_argument("--pacote", type=Path)
    g.add_argument("--hash")
    v.add_argument("--resposta", type=Path, required=True)
    v.add_argument("--exigir", action="append", default=[], metavar="TRECHO",
                   help="trecho que a resposta tem de trazer (repetível), ex.: --exigir 'Decisão:'")
    v.add_argument("--comentarios-opcionais", action="store_true",
                   help="não reprova a resposta que deixa de certificar os comentários do pacote")
    v.add_argument("--docx-opcional", action="store_true",
                   help="não reprova a resposta que deixa de repetir o SHA-256 do DOCX numerado (HASH_DOCX)")
    args = ap.parse_args(argv)

    if args.cmd == "montar":
        instr = args.instrucoes.read_text(encoding="utf-8") if args.instrucoes else INSTRUCOES_PADRAO
        fmt = args.formato_resposta.read_text(encoding="utf-8") if args.formato_resposta else None
        if not args.minuta and not args.numerado:
            print("informe --minuta ou --numerado", file=sys.stderr)
            return 2
        if args.numerado and not args.numerado.exists():
            print(f"arquivo não encontrado: {args.numerado}", file=sys.stderr)
            return 2
        try:
            base = documento_base(args.minuta, args.numerado)
            avisos = conferir_instrucoes(instr, base)
            if args.numerado and args.minuta:
                avisos += conferir_numerado(base, args.numerado)
            texto = montar(args.minuta, instr, args.dossie, args.adendo, args.anterior, fmt, args.comentarios, args.numerado)
        except (zipfile.BadZipFile, KeyError, ET.ParseError) as e:
            print(f"erro de leitura do .docx numerado: {e}", file=sys.stderr)
            return 2
        for aviso in avisos:
            print(f"atenção: {aviso}")
        args.saida.write_text(texto, encoding="utf-8")
        tokens = int(len(texto) / CHARS_POR_TOKEN)
        print(f"pacote gravado em {args.saida}: {len(texto):,} caracteres, ~{tokens:,} tokens; hash da minuta {hash_do_pacote(texto)}"
              + (f"; hash do DOCX numerado {hash_docx_do_pacote(texto)}" if args.numerado else ""))
        if tokens > ALERTA_TOKENS:
            print(f"atenção: acima de {ALERTA_TOKENS:,} tokens; sondar créditos antes, usar esforço medium em rodada "
                  "intermediária ou montar só as diferenças com --anterior")
        return 0
    esperado = args.hash or hash_do_pacote(args.pacote.read_text(encoding="utf-8"))
    if not esperado:
        print("pacote sem linha 'SHA-256 da minuta'", file=sys.stderr)
        return 2
    resposta = args.resposta.read_text(encoding="utf-8")
    ok, msg = verificar(resposta, esperado.lower())
    print(f"hash: {msg}")
    valida, msgs = validar_resposta(resposta, args.exigir)
    print("resposta: " + ("válida" if valida else "INVÁLIDA"))
    for m in msgs:
        print(f"  {m}")
    ok = ok and valida
    h_com = hash_comentarios_do_pacote(args.pacote.read_text(encoding="utf-8")) if args.pacote else None
    if h_com:
        ok_com, msg_com = verificar_comentarios(resposta, h_com)
        print(f"comentários: {msg_com}")
        if ok_com is False or (ok_com is None and not args.comentarios_opcionais):
            ok = False
    h_docx = hash_docx_do_pacote(args.pacote.read_text(encoding="utf-8")) if args.pacote else None
    if h_docx:
        ok_docx, msg_docx = verificar_docx(resposta, h_docx)
        print(f"DOCX numerado: {msg_docx}")
        if ok_docx is False or (ok_docx is None and not args.docx_opcional):
            ok = False
    print("cobertura: " + ("certificada" if ok else "NÃO certificada"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
