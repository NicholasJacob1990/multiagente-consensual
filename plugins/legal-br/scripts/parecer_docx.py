#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parecer_docx.py — entrega de parecer em .docx no padrão institucional.

Resolve o que o Markdown não resolve: fonte/margens/espaçamento da casa,
numeração AUTOMÁTICA de parágrafos (a do Word, não "1." digitado), notas de
rodapé e uma auditoria que pega os defeitos que revisor humano cobra.

Subcomandos
-----------
  check                        dependências
  converter  ENTRADA.md SAIDA.docx     markdown -> docx já no padrão
  formatar   ARQ.docx          fonte, margens, espaçamento, justificado
  numerar    ARQ.docx          numeração automática dos parágrafos de corpo
  nota       ARQ.docx --par N --texto "..."      nota de rodapé avulsa

Notas de rodapé no .md (converter): marcador `[^id]` no texto e definição
`[^id]: texto` em linha própria, em qualquer lugar do arquivo. Viram notas
reais do Word (Times 10, recuo 0, espaçamento simples). Nada é convertido em
nota automaticamente: no perfil GENES a doutrina fica em autor-data no texto.
  auditar    ARQ.docx          relatório JSON dos defeitos típicos
  ementa     ARQ.docx [--max 80] [--nova "..."]  confere/substitui a ementa

Toda escrita cria backup `<arquivo>.bak-<AAAAMMDD-HHMM>.docx` ao lado.
"""
from __future__ import annotations

import argparse, copy, json, re, shutil, subprocess, sys, zipfile
from datetime import datetime
from pathlib import Path

try:
    import docx
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    from docx.shared import Cm, Pt
except ImportError:
    docx = None

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
W14 = "{http://schemas.microsoft.com/office/word/2010/wordml}"

# Padrão da casa (GENSU/GENES - CODEMGE). Ajuste aqui para outra instituição.
PADRAO = dict(fonte="Times New Roman", corpo=12, nota=10, entrelinha=1.5,
              margens=(3.0, 2.0, 3.0, 2.0), espaco_depois=6, recuo_num=1.25)

# Parágrafos que NUNCA recebem número: cabeçalho, ementa, títulos e fecho.
NAO_NUMERA = re.compile(
    r"^(PARECER\b|Processo\s+n|Interessad|EMENTA:|REFER[ÊE]NCIAS\b"
    r"|[IVXLC]+\s*[—\-–]\s*\S"                    # "IV — DA NATUREZA..."
    r"|É o parecer|É o que me parece|Ante o exposto|Antes da celebra"
    r"|Advogad|Ger[êe]ncia\b"
    # cabeçalho, seções e fecho do perfil GENES (references/perfil-parecer-genes.md)
    r"|PROCESSO\s+SEI|ASSUNTO:|CONSULENTE:|[ÓO]RG[ÃA]O\s+CONSULTIVO|EMENTA\s+CONSULTIVA"
    r"|[IVXLC]+\.\s+[A-ZÁÉÍÓÚÂÊÔÃÕÇ]|Belo\s+Horizonte,|Diretoria\s+Jur[íi]dica)", re.I)

FECHO = re.compile(r"^(É o parecer|É o que me parece|S\.M\.J\.)", re.I)

TYPOS = {  # colhidos em revisão real; francesismos e trocas de teclado
    "Entranto": "Entretanto", "eventualemnte": "eventualmente",
    "relative ": "relativo ", "a confirmer": "a confirmar",
    "hiposuficiente": "hipossuficiente", "atravez": "através",
    "excessão": "exceção", "previlégio": "privilégio",
}

# Citação de precedente sem relator/órgão/data — o defeito nº 1 de referências.
PRECEDENTE = re.compile(r"\b(REsp|AREsp|AgInt|RE|ARE|ADI|ADC|ADPF|RMS|HC|MS)\b[^.;)]*?"
                        r"n?[ºo]?\s*[\d][\d.\-/]{4,}", re.I)
TEM_AUTORIA = re.compile(r"\b(Rel\.|Relator|Relatora|Turma|Plen[áa]rio|Se[çc][ãa]o|"
                         r"DJe|DJEN|julgad|j\.\s*\d)", re.I)


def _agora() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M")


def _backup(p: Path) -> Path:
    b = p.with_suffix(f".bak-{_agora()}.docx")
    shutil.copy2(p, b)
    return b


def _norm(s: str) -> str:
    """NBSP quebra qualquer match de texto vindo do Word."""
    return s.replace("\xa0", " ").replace("‑", "-")


def _rpr(par):
    if not par.runs:
        return None
    r = par.runs[0]._r.find(qn("w:rPr"))
    return copy.deepcopy(r) if r is not None else None


def _mk_run(rPr, texto):
    r = OxmlElement("w:r")
    if rPr is not None:
        r.append(copy.deepcopy(rPr))
    t = OxmlElement("w:t")
    t.set(qn("xml:space"), "preserve")
    t.text = texto
    r.append(t)
    return r


def set_texto(par, texto):
    """Reescreve o parágrafo num único run, preservando o rPr do primeiro
    (é o que mantém o negrito da ementa e a fonte herdada)."""
    rPr = _rpr(par)
    el = par._p
    for c in list(el):
        if c.tag != qn("w:pPr"):
            el.remove(c)
    el.append(_mk_run(rPr, texto))


def inserir_depois(par, textos):
    """Insere parágrafos clonando o pPr do de referência (herda numeração,
    estilo e espaçamento). Sem isso o parágrafo novo sai fora do padrão."""
    ref, rPr, ancora = par._p, _rpr(par), par._p
    for txt in textos:
        novo = copy.deepcopy(ref)
        for a in (W14 + "paraId", W14 + "textId"):
            novo.attrib.pop(a, None)
        for c in list(novo):
            if c.tag != qn("w:pPr"):
                novo.remove(c)
        novo.append(_mk_run(rPr, txt))
        ancora.addnext(novo)
        ancora = novo


def tem_numeracao(par) -> bool:
    # ARMADILHA: numPr fica dentro de pPr. find() direto no w:p devolve None
    # sempre e faz a auditoria mentir "0 numerados".
    return par._p.find(".//" + W + "numPr") is not None


# ---------------------------------------------------------------- numeração

def _garante_lista(doc, num_id="900") -> str:
    """Cria abstractNum+num em numbering.xml (decimal, número na margem e tab)."""
    numbering = doc.part.numbering_part.element
    for n in numbering.findall(qn("w:num")):
        if n.get(qn("w:numId")) == num_id:
            return num_id
    aid = "900"
    absn = OxmlElement("w:abstractNum")
    absn.set(qn("w:abstractNumId"), aid)
    mlt = OxmlElement("w:multiLevelType"); mlt.set(qn("w:val"), "singleLevel")
    absn.append(mlt)
    lvl = OxmlElement("w:lvl"); lvl.set(qn("w:ilvl"), "0")
    start = OxmlElement("w:start"); start.set(qn("w:val"), "1"); lvl.append(start)
    fmt = OxmlElement("w:numFmt"); fmt.set(qn("w:val"), "decimal"); lvl.append(fmt)
    # ordem do schema CT_Lvl: start, numFmt, suff, lvlText, lvlJc, pPr
    suff = OxmlElement("w:suff"); suff.set(qn("w:val"), "tab"); lvl.append(suff)
    txt = OxmlElement("w:lvlText"); txt.set(qn("w:val"), "%1."); lvl.append(txt)
    jc = OxmlElement("w:lvlJc"); jc.set(qn("w:val"), "left"); lvl.append(jc)
    pPr = OxmlElement("w:pPr")
    ind = OxmlElement("w:ind")
    ind.set(qn("w:left"), "0")                                   # número na margem
    ind.set(qn("w:firstLine"), str(int(PADRAO["recuo_num"] * 567)))  # texto recuado
    pPr.append(ind); lvl.append(pPr)
    absn.append(lvl)
    numbering.insert(0, absn)
    num = OxmlElement("w:num"); num.set(qn("w:numId"), num_id)
    ref = OxmlElement("w:abstractNumId"); ref.set(qn("w:val"), aid)
    num.append(ref); numbering.append(num)
    return num_id


def aplicar_numeracao(par, num_id="900"):
    pPr = par._p.get_or_add_pPr()
    if pPr.find(qn("w:numPr")) is not None:
        return False
    numPr = OxmlElement("w:numPr")
    ilvl = OxmlElement("w:ilvl"); ilvl.set(qn("w:val"), "0")
    nid = OxmlElement("w:numId"); nid.set(qn("w:val"), num_id)
    numPr.append(ilvl); numPr.append(nid)
    # ordem do schema CT_PPr: pStyle vem antes de numPr, tabs depois
    pStyle = pPr.find(qn("w:pStyle"))
    (pStyle.addnext(numPr) if pStyle is not None else pPr.insert(0, numPr))
    if pPr.find(qn("w:tabs")) is None:
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab"); tab.set(qn("w:val"), "left")
        tab.set(qn("w:pos"), str(int(PADRAO["recuo_num"] * 567)))
        tabs.append(tab); numPr.addnext(tabs)
    return True


def cmd_numerar(a):
    doc = docx.Document(a.arquivo)
    num_id = _garante_lista(doc)
    n, no_fecho = 0, False
    for p in doc.paragraphs:
        t = _norm(p.text).strip()
        # entre "É o parecer" e "REFERÊNCIAS" só há assinatura, cargo e unidade
        if FECHO.match(t):
            no_fecho = True
        elif t.upper().startswith("REFER"):
            no_fecho = False
        if not t or no_fecho or NAO_NUMERA.match(t) or tem_numeracao(p):
            continue
        if aplicar_numeracao(p, num_id):
            n += 1
    bkp = _backup(Path(a.arquivo)); doc.save(a.arquivo)
    print(json.dumps({"numerados_agora": n, "backup": bkp.name}, ensure_ascii=False))


# ---------------------------------------------------------------- formatação

def cmd_formatar(a):
    doc = docx.Document(a.arquivo)
    for s in doc.sections:
        t, r, b, l = PADRAO["margens"]
        s.top_margin, s.right_margin = Cm(t), Cm(r)
        s.bottom_margin, s.left_margin = Cm(b), Cm(l)
    normal = doc.styles["Normal"]
    normal.font.name = PADRAO["fonte"]
    normal.font.size = Pt(PADRAO["corpo"])
    rpr = normal.element.get_or_add_rPr().get_or_add_rFonts()
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        rpr.set(qn(attr), PADRAO["fonte"])
    for p in doc.paragraphs:
        if not _norm(p.text).strip():
            continue
        pf = p.paragraph_format
        pf.line_spacing = PADRAO["entrelinha"]
        pf.space_after = Pt(PADRAO["espaco_depois"])
        if p.alignment is None:
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
        for r in p.runs:
            r.font.name = PADRAO["fonte"]
            if r.font.size is None:
                r.font.size = Pt(PADRAO["corpo"])
    bkp = _backup(Path(a.arquivo)); doc.save(a.arquivo)
    print(json.dumps({"formatado": True, "padrao": PADRAO["fonte"],
                      "backup": bkp.name}, ensure_ascii=False))


# ---------------------------------------------------------------- notas de rodapé
#
# Sintaxe Markdown: marcador `[^id]` no texto e definição `[^id]: texto` em
# linha própria, em qualquer lugar do .md (linhas seguintes recuadas com 4
# espaços ou tab continuam a nota). As notas são numeradas pela ordem do
# primeiro marcador. Política: nada é convertido em nota automaticamente — no
# perfil GENES a doutrina fica em autor-data no texto; só vira nota o que o .md
# marcar com [^id] (outros perfis ou explicações laterais).
#
# Mecânica (vale para converter, parecer_genes_estilo.py e o subcomando nota):
# o marcador vira um token alfanumérico (sobrevive ao pandoc e ao python-docx
# num único run); depois de salvo o .docx, `aplicar_notas_docx` reescreve o
# pacote: troca cada token por <w:footnoteReference> sobrescrito, cria ou
# completa word/footnotes.xml (separadores -1 e 0), a relação no
# document.xml.rels, o Override no [Content_Types].xml e o <w:footnotePr> no
# settings.xml (antes de <w:compat>). Ver armadilha 4 em references/parecer-docx.md.

NOTA_DEF = re.compile(r"^ {0,3}\[\^([^\]\s]+)\]:[ \t]*(.*)$")
NOTA_REF = re.compile(r"\[\^([^\]\s]+)\](?!:)")
NOTA_TOKEN = re.compile(r"ZQNOTA(\d+)QZ")
_CERCA = re.compile(r"^ {0,3}(```|~~~)")

_NS_W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
_REL_FN = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/footnotes"
_CT_FN = "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml"
# elementos de CT_RPr que vêm DEPOIS de vertAlign (ordem do schema)
_RPR_DEPOIS_VERT = ("rtl", "cs", "em", "lang", "eastAsianLayout", "specVanish", "oMath")
# elementos de CT_Settings que vêm DEPOIS de footnotePr
_SET_DEPOIS_FN = ("endnotePr", "compat", "docVars", "rsids", "mathPr", "attachedSchema",
                  "themeFontLang", "clrSchemeMapping", "doNotIncludeSubdocsInStats",
                  "doNotAutoCompressPictures", "forceUpgrade", "captions",
                  "readModeInkLockDown", "smartTagType", "schemaLibrary", "shapeDefaults",
                  "doNotEmbedSmartTags", "decimalSymbol", "listSeparator")


class NotaErro(ValueError):
    """Marcador sem definição, definição duplicada ou nota reutilizada."""


def token_nota(n: int) -> str:
    return f"ZQNOTA{n}QZ"


def extrair_notas_md(texto: str):
    """Separa as definições `[^id]: ...` e troca cada marcador `[^id]` por um
    token. Devolve (texto_sem_definicoes, [texto da nota 1, nota 2, ...]).
    Ignora blocos de código cercados. Erro se marcador não tiver definição,
    se a definição repetir ou se o mesmo marcador aparecer duas vezes (o Word
    não reaproveita nota: escreva "v. nota N" ou crie outra)."""
    defs, ordem, linhas, cerca = {}, [], [], False
    brutas = texto.split("\n")
    i = 0
    while i < len(brutas):
        ln = brutas[i]
        if _CERCA.match(ln):
            cerca = not cerca
        m = None if cerca else NOTA_DEF.match(ln)
        if m:
            nid, corpo = m.group(1), [m.group(2).strip()]
            i += 1
            while i < len(brutas) and re.match(r"^(\t| {4})\S", brutas[i]):
                corpo.append(brutas[i].strip()); i += 1
            if nid in defs:
                raise NotaErro(f"nota [^{nid}] definida mais de uma vez")
            defs[nid] = " ".join(c for c in corpo if c)
            continue
        linhas.append(ln); i += 1

    usados, saida, cerca = {}, [], False
    for ln in linhas:
        if _CERCA.match(ln):
            cerca = not cerca
        if cerca:
            saida.append(ln); continue

        def troca(m):
            nid = m.group(1)
            if nid not in defs:
                raise NotaErro(f"marcador [^{nid}] sem definição '[^{nid}]: texto'")
            if nid in usados:
                raise NotaErro(f"marcador [^{nid}] usado mais de uma vez")
            ordem.append(nid); usados[nid] = len(ordem)
            return token_nota(len(ordem))
        saida.append(NOTA_REF.sub(troca, ln))
    sobras = [k for k in defs if k not in usados]
    if sobras:
        print(f"aviso: nota(s) definida(s) e não usada(s): {', '.join(sobras)}",
              file=sys.stderr)
    return "\n".join(saida), [defs[k] for k in ordem]


def _w(tag):
    return f"{{{_NS_W}}}{tag}"


def _el(tag, **attrs):
    from lxml import etree
    e = etree.Element(_w(tag))
    for k, v in attrs.items():
        e.set(_w(k), str(v))
    return e


def _insere_ordenado(pai, filho, depois_de_mim):
    """Insere `filho` antes do primeiro irmão cujo localname esteja em
    `depois_de_mim` (respeita a ordem do schema); senão, no fim."""
    for c in pai:
        if isinstance(c.tag, str) and c.tag.split("}")[-1] in depois_de_mim:
            c.addprevious(filho); return
    pai.append(filho)


def _rpr_nota(fonte, meio_pontos, b=False, i=False, sobrescrito=False):
    rpr = _el("rPr")
    rpr.append(_el("rFonts", ascii=fonte, hAnsi=fonte, cs=fonte, eastAsia=fonte))
    if b:
        rpr.append(_el("b")); rpr.append(_el("bCs"))
    if i:
        rpr.append(_el("i")); rpr.append(_el("iCs"))
    rpr.append(_el("sz", val=meio_pontos)); rpr.append(_el("szCs", val=meio_pontos))
    if sobrescrito:
        rpr.append(_el("vertAlign", val="superscript"))
    return rpr


def _runs_inline(texto, fonte, meio_pontos):
    """Texto da nota com **negrito** e *itálico* simples."""
    runs = []
    for parte in re.split(r"(\*\*[^*]+\*\*|\*[^*\s][^*]*\*)", texto):
        if not parte:
            continue
        b = parte.startswith("**") and parte.endswith("**") and len(parte) > 4
        i = not b and parte.startswith("*") and parte.endswith("*") and len(parte) > 2
        txt = parte[2:-2] if b else parte[1:-1] if i else parte
        r = _el("r"); r.append(_rpr_nota(fonte, meio_pontos, b=b, i=i))
        t = _el("t"); t.text = txt
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        r.append(t); runs.append(r)
    return runs


def _footnote(fid, texto, fonte, meio_pontos):
    fn = _el("footnote", id=fid)
    p = _el("p"); fn.append(p)
    ppr = _el("pPr")
    ppr.append(_el("spacing", before=0, after=0, line=240, lineRule="auto"))
    ppr.append(_el("ind", left=0, right=0, firstLine=0))
    ppr.append(_el("jc", val="both"))
    p.append(ppr)
    r = _el("r"); r.append(_rpr_nota(fonte, meio_pontos, sobrescrito=True))
    r.append(_el("footnoteRef")); p.append(r)
    for run in _runs_inline(" " + texto, fonte, meio_pontos):
        p.append(run)
    return fn


def _separadores(raiz):
    tem = {c.get(_w("id")) for c in raiz.findall(_w("footnote"))}
    for fid, tipo in (("0", "continuationSeparator"), ("-1", "separator")):
        if fid in tem:
            continue
        fn = _el("footnote", type=tipo, id=fid)
        p = _el("p"); ppr = _el("pPr")
        ppr.append(_el("spacing", after=0, line=240, lineRule="auto")); p.append(ppr)
        r = _el("r"); r.append(_el(tipo)); p.append(r); fn.append(p)
        raiz.insert(0, fn)


def _troca_tokens(doc_raiz, mapa_ids):
    """Divide cada run que contém token em: antes | referência | depois."""
    import copy as _copy
    achados = []
    while True:
        alvo = next((t for t in doc_raiz.iter(_w("t"))
                     if t.text and NOTA_TOKEN.search(t.text)), None)
        if alvo is None:
            break
        run = alvo.getparent()
        m = NOTA_TOKEN.search(alvo.text)
        n = int(m.group(1)); achados.append(n)
        antes, depois = alvo.text[:m.start()], alvo.text[m.end():]
        rpr = run.find(_w("rPr"))
        # referência: rPr do run hospedeiro + vertAlign sobrescrito
        ref = _el("r")
        rr = _copy.deepcopy(rpr) if rpr is not None else _el("rPr")
        # sobrescrito sem itálico/sublinhado herdados do trecho anotado
        for tag in ("vertAlign", "i", "iCs", "u"):
            for v in rr.findall(_w(tag)):
                rr.remove(v)
        _insere_ordenado(rr, _el("vertAlign", val="superscript"), _RPR_DEPOIS_VERT)
        ref.append(rr); ref.append(_el("footnoteReference", id=mapa_ids[n]))
        # run "depois": mesmo rPr, texto restante e irmãos que vinham após o w:t
        pos = _el("r")
        if rpr is not None:
            pos.append(_copy.deepcopy(rpr))
        if depois:
            t2 = _el("t"); t2.text = depois
            t2.set("{http://www.w3.org/XML/1998/namespace}space", "preserve"); pos.append(t2)
        seguinte = alvo.getnext()
        while seguinte is not None:
            prox = seguinte.getnext(); pos.append(seguinte); seguinte = prox
        if antes:
            alvo.text = antes
            alvo.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
        else:
            run.remove(alvo)
        run.addnext(ref); ref.addnext(pos)
        if not any(c.tag != _w("rPr") for c in run):
            run.getparent().remove(run)
        if not any(c.tag != _w("rPr") for c in pos):
            pos.getparent().remove(pos)
    return achados


def aplicar_notas_docx(caminho, notas, fonte=None, tamanho_pt=None):
    """Transforma os tokens de `extrair_notas_md` em notas de rodapé reais no
    .docx já salvo em `caminho`. `notas[k]` é o texto da nota k+1. Devolve
    {"notas": n, "ids": [...]}. Erro (nada gravado) se faltar token no corpo."""
    from lxml import etree
    fonte = fonte or PADRAO["fonte"]
    meio_pontos = int(round((tamanho_pt or PADRAO["nota"]) * 2))
    caminho = Path(caminho)
    with zipfile.ZipFile(caminho) as z:
        infos = z.infolist()
        partes = {i.filename: z.read(i.filename) for i in infos}

    rels_nome = "word/_rels/document.xml.rels"
    rels = etree.fromstring(partes[rels_nome])
    rel_fn = next((r for r in rels if r.get("Type") == _REL_FN), None)
    if rel_fn is None:
        usados = {r.get("Id") for r in rels}
        rid = next(f"rIdNotas{k}" for k in range(1, 999) if f"rIdNotas{k}" not in usados)
        rel_fn = etree.SubElement(rels, f"{{{_NS_REL}}}Relationship")
        rel_fn.set("Id", rid); rel_fn.set("Type", _REL_FN); rel_fn.set("Target", "footnotes.xml")
    alvo_fn = rel_fn.get("Target").lstrip("/")
    fn_nome = alvo_fn if alvo_fn.startswith("word/") else "word/" + alvo_fn

    if fn_nome in partes:
        fn_raiz = etree.fromstring(partes[fn_nome])
    else:
        fn_raiz = etree.Element(_w("footnotes"), nsmap={"w": _NS_W})
    _separadores(fn_raiz)
    existentes = [int(c.get(_w("id"))) for c in fn_raiz.findall(_w("footnote"))]
    prox = max([0] + existentes) + 1
    mapa = {k + 1: str(prox + k) for k in range(len(notas))}

    doc_raiz = etree.fromstring(partes["word/document.xml"])
    achados = _troca_tokens(doc_raiz, mapa)
    faltam = sorted(set(mapa) - set(achados))
    if faltam or len(achados) != len(set(achados)):
        raise NotaErro(f"marcador(es) de nota não localizados no corpo: {faltam} "
                       "(o token foi partido ou removido na conversão)")
    for k, texto in enumerate(notas, 1):
        fn_raiz.append(_footnote(mapa[k], texto, fonte, meio_pontos))

    ct = etree.fromstring(partes["[Content_Types].xml"])
    pn = "/" + fn_nome
    if not any(o.get("PartName") == pn for o in ct.findall(f"{{{_NS_CT}}}Override")):
        o = etree.SubElement(ct, f"{{{_NS_CT}}}Override")
        o.set("PartName", pn); o.set("ContentType", _CT_FN)

    st = etree.fromstring(partes["word/settings.xml"])
    fpr = st.find(_w("footnotePr"))
    if fpr is None:
        fpr = _el("footnotePr")
        _insere_ordenado(st, fpr, _SET_DEPOIS_FN)
    tem = {c.get(_w("id")) for c in fpr.findall(_w("footnote"))}
    for fid in ("-1", "0"):
        if fid not in tem:
            fpr.append(_el("footnote", id=fid))

    ser = lambda r: etree.tostring(r, xml_declaration=True, encoding="UTF-8", standalone=True)
    partes.update({"word/document.xml": ser(doc_raiz), fn_nome: ser(fn_raiz),
                   rels_nome: ser(rels), "[Content_Types].xml": ser(ct),
                   "word/settings.xml": ser(st)})
    nomes = [i.filename for i in infos] + ([fn_nome] if fn_nome not in
                                           {i.filename for i in infos} else [])
    tmp = caminho.with_suffix(".notas-tmp.docx")
    with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
        for nome in nomes:
            z.writestr(nome, partes[nome])
    tmp.replace(caminho)
    return {"notas": len(notas), "ids": [int(mapa[k]) for k in sorted(mapa)]}


def cmd_nota(a):
    """Acrescenta UMA nota de rodapé ao fim do parágrafo de índice --par
    (índice do python-docx, não o número que o Word mostra). Cria a part
    footnotes.xml se o documento ainda não tiver notas."""
    p = Path(a.arquivo)
    bkp = _backup(p)
    doc = docx.Document(str(p))
    try:
        alvo = doc.paragraphs[a.par]
    except IndexError:
        sys.exit(f"parágrafo {a.par} não existe (documento tem {len(doc.paragraphs)})")
    # run novo com o rPr do último run: não reescreve o parágrafo (preserva
    # negrito/itálico internos) e ancora a referência logo após o texto
    rPr = None
    if alvo.runs:
        r = alvo.runs[-1]._r.find(qn("w:rPr"))
        rPr = copy.deepcopy(r) if r is not None else None
    alvo._p.append(_mk_run(rPr, token_nota(1)))
    doc.save(str(p))
    try:
        res = aplicar_notas_docx(p, [a.texto])
    except NotaErro as e:
        shutil.copy2(bkp, p)
        sys.exit(f"{e} — nada alterado (backup restaurado)")
    print(json.dumps({"nota_id": res["ids"][0], "paragrafo": a.par,
                      "backup": bkp.name}, ensure_ascii=False))


# ---------------------------------------------------------------- auditoria

def cmd_auditar(a):
    doc = docx.Document(a.arquivo)
    pars = doc.paragraphs
    achados, sem_num, refs_incompletas = [], [], []
    ementa = None
    for i, p in enumerate(pars):
        t = _norm(p.text).strip()
        if not t:
            continue
        if t.startswith("EMENTA:") and ementa is None:
            ementa = (i, t)
        for errado, certo in TYPOS.items():
            if errado in t:
                achados.append({"tipo": "typo", "par": i,
                                "achado": errado, "sugestao": certo})
        if t.endswith(","):
            achados.append({"tipo": "frase_truncada", "par": i, "trecho": t[-60:]})
        if not tem_numeracao(p) and not NAO_NUMERA.match(t):
            sem_num.append({"par": i, "trecho": t[:70]})
        if PRECEDENTE.search(t) and not TEM_AUTORIA.search(t) and len(t) < 200:
            refs_incompletas.append({"par": i, "trecho": t[:110]})

    with zipfile.ZipFile(a.arquivo) as z:
        dx = z.read("word/document.xml").decode("utf-8")
    notas_corpo = len(re.findall(r"<w:footnoteReference", dx))

    rel = {
        "paragrafos": len(pars),
        "numerados": sum(1 for p in pars if tem_numeracao(p)),
        "sem_numeracao_suspeitos": sem_num,
        "ementa_palavras": len(ementa[1].split()) if ementa else None,
        "ementa_excede": bool(ementa and len(ementa[1].split()) > a.max_ementa),
        "notas_rodape_no_corpo": notas_corpo,
        "citacoes_sem_relator_ou_data": refs_incompletas,
        "defeitos_texto": achados,
    }
    rel["ok"] = not (rel["ementa_excede"] or achados or refs_incompletas or sem_num)
    print(json.dumps(rel, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------- ementa

def cmd_ementa(a):
    doc = docx.Document(a.arquivo)
    alvo = next((p for p in doc.paragraphs[:15]
                 if _norm(p.text).strip().startswith("EMENTA:")), None)
    if alvo is None:
        sys.exit("ementa não localizada (procure um parágrafo iniciado por 'EMENTA:')")
    atual = _norm(alvo.text).strip()
    if not a.nova:
        print(json.dumps({"palavras": len(atual.split()), "max": a.max,
                          "excede": len(atual.split()) > a.max, "texto": atual},
                         ensure_ascii=False, indent=2))
        return
    if len(a.nova.split()) > a.max:
        sys.exit(f"a nova ementa tem {len(a.nova.split())} palavras (máx {a.max})")
    bkp = _backup(Path(a.arquivo))
    set_texto(alvo, a.nova)            # preserva o negrito
    doc.save(a.arquivo)
    print(json.dumps({"antes": len(atual.split()), "depois": len(a.nova.split()),
                      "backup": bkp.name}, ensure_ascii=False))


# ---------------------------------------------------------------- converter

def cmd_converter(a):
    if not shutil.which("pandoc"):
        sys.exit("pandoc não encontrado: brew install pandoc")
    entrada = Path(a.entrada)
    bruto = entrada.read_text(encoding="utf-8")
    try:
        texto, notas = extrair_notas_md(bruto)
    except NotaErro as e:
        sys.exit(f"nota de rodapé: {e}")
    if notas:
        # notas saem do .md antes do pandoc (que faria notas no estilo dele);
        # os tokens voltam como notas reais no padrão da casa depois de
        # formatar e numerar
        subprocess.run(["pandoc", "-f", "markdown", "-o", a.saida,
                        "--resource-path", str(entrada.resolve().parent)],
                       input=texto.encode("utf-8"), check=True)
    else:
        subprocess.run(["pandoc", a.entrada, "-o", a.saida], check=True)
    for fn, args in ((cmd_formatar, {"arquivo": a.saida}),
                     (cmd_numerar, {"arquivo": a.saida})):
        fn(argparse.Namespace(**args))
    res = {"gerado": a.saida}
    if notas:
        try:
            res["notas_rodape"] = aplicar_notas_docx(a.saida, notas)["notas"]
        except NotaErro as e:
            sys.exit(f"nota de rodapé: {e}")
    print(json.dumps(res, ensure_ascii=False))


def cmd_check(_):
    print(json.dumps({
        "python_docx": docx is not None,
        "pandoc": bool(shutil.which("pandoc")),
        "padrao": PADRAO,
    }, ensure_ascii=False, indent=2))


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check").set_defaults(func=cmd_check)

    c = sub.add_parser("converter"); c.add_argument("entrada"); c.add_argument("saida")
    c.set_defaults(func=cmd_converter)

    for nome, fn in (("formatar", cmd_formatar), ("numerar", cmd_numerar)):
        s = sub.add_parser(nome); s.add_argument("arquivo"); s.set_defaults(func=fn)

    n = sub.add_parser("nota"); n.add_argument("arquivo")
    n.add_argument("--par", type=int, required=True, help="índice do parágrafo")
    n.add_argument("--texto", required=True); n.set_defaults(func=cmd_nota)

    au = sub.add_parser("auditar"); au.add_argument("arquivo")
    au.add_argument("--max-ementa", type=int, default=80, dest="max_ementa")
    au.set_defaults(func=cmd_auditar)

    e = sub.add_parser("ementa"); e.add_argument("arquivo")
    e.add_argument("--max", type=int, default=80); e.add_argument("--nova")
    e.set_defaults(func=cmd_ementa)

    a = ap.parse_args()
    if docx is None and a.cmd != "check":
        sys.exit("instale python-docx: python3 -m pip install --user python-docx")
    a.func(a)


if __name__ == "__main__":
    main()
