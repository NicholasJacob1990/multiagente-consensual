"""Sobrepõe alterações controladas de um novo autor a um DOCX que já tem revisões de outro autor,
sem aceitar nem rejeitar as existentes. Opera sobre o texto visível (sem trechos excluídos).

Biblioteca usada por ``aplicar_overlay.py``; requer ``lxml`` (``pip install lxml``). Também gera a
visão "tudo aceito" (``aceitar_tudo``) sem Word nem LibreOffice."""
import copy, re
from difflib import SequenceMatcher
from lxml import etree

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
w = lambda t: '{%s}%s' % (W, t)
XS = '{http://www.w3.org/XML/1998/namespace}space'
TOK = re.compile(r'\w+|\s+|[^\w\s]', re.U)
TRACK = (w('ins'), w('del'), w('moveFrom'), w('moveTo'))


class Ctx:
    def __init__(self, root, author, date):
        ids = [int(e.get(w('id'))) for e in root.iter() if e.get(w('id')) and e.get(w('id')).isdigit()]
        self.next_id = max(ids + [0]) + 1000
        self.author, self.date = author, date

    def mark(self, tag):
        el = etree.Element(w(tag))
        el.set(w('id'), str(self.next_id)); self.next_id += 1
        el.set(w('author'), self.author); el.set(w('date'), self.date)
        return el


def normalize_runs(p):
    """Um filho por run (além do rPr): w:t, w:delText, w:br, w:tab ou outro.

    Os demais filhos (referência de nota ou de comentário, campo, desenho) seguem, na ordem original,
    cada um no seu run, com a mesma formatação; nada do run original se perde, e ``split_run`` não
    duplica uma referência de nota ao copiar o run."""
    for r in list(p.iter(w('r'))):
        kids = [c for c in r if c.tag != w('rPr')]
        if len(kids) <= 1:
            continue
        rpr = r.find(w('rPr'))
        parent, idx = r.getparent(), r.getparent().index(r)
        attrs = dict(r.attrib)
        for k, c in enumerate(kids):
            nr = etree.Element(w('r'), attrs)
            if rpr is not None:
                nr.append(copy.deepcopy(rpr))
            nr.append(c)
            parent.insert(idx + k, nr)
        parent.remove(r)


def is_deleted(r, p):
    a = r.getparent()
    while a is not None and a is not p:
        if a.tag in (w('del'), w('moveFrom')):
            return True
        a = a.getparent()
    return r.find(w('delText')) is not None


def run_text(r):
    """Texto do run inteiro (todos os w:t, w:br e w:tab), igual antes e depois de ``normalize_runs``."""
    out = []
    for c in r:
        if c.tag == w('t'):
            out.append(c.text or '')
        elif c.tag == w('br'):
            out.append('\n')
        elif c.tag == w('tab'):
            out.append('\t')
    return ''.join(out)


def vis_runs(p):
    out = []
    for r in p.iter(w('r')):
        if is_deleted(r, p):
            continue
        t = run_text(r)
        if t:
            out.append((r, t))
    return out


def visible(p):
    return ''.join(t for _, t in vis_runs(p))


def split_run(r, k):
    """Divide o run na posição k do seu texto; devolve o segundo run."""
    t = r.find(w('t'))
    text = t.text or ''
    if k <= 0 or k >= len(text):
        raise ValueError('split fora do intervalo')
    r2 = copy.deepcopy(r)
    t.text = text[:k]; t.set(XS, 'preserve')
    t2 = r2.find(w('t')); t2.text = text[k:]; t2.set(XS, 'preserve')
    r.addnext(r2)
    return r2


def boundary(p, pos):
    """Garante fronteira de run na posição visível pos; devolve o run que começa em pos (ou None no fim)."""
    acc = 0
    for r, t in vis_runs(p):
        if acc == pos:
            return r
        if acc < pos < acc + len(t):
            return split_run(r, pos - acc)
        acc += len(t)
    return None


def lift_point(p, r, ctx):
    """Sobe o run até ser filho direto do parágrafo, dividindo os contêineres (ins/del/hyperlink)."""
    target = r
    while target.getparent() is not p:
        parent = target.getparent()
        siblings = list(parent)
        i = siblings.index(target)
        if i > 0:
            clone = etree.Element(parent.tag, dict(parent.attrib))
            if parent.tag in TRACK:
                clone.set(w('id'), str(ctx.next_id)); ctx.next_id += 1
            for s in siblings[i:]:
                clone.append(s)
            parent.addnext(clone)
            target = clone
        else:
            target = parent
    return target


def rpr_near(p, pos):
    runs = vis_runs(p)
    acc, prev = 0, None
    for r, t in runs:
        if acc >= pos:
            break
        prev = r; acc += len(t)
    ref = prev if prev is not None else (runs[0][0] if runs else None)
    if ref is None or ref.find(w('rPr')) is None:
        return None
    rpr = copy.deepcopy(ref.find(w('rPr')))
    for ch in list(rpr):
        if ch.tag in (w('rPrChange'), w('ins'), w('del')):
            rpr.remove(ch)
    return rpr


def make_run(text, rpr, deleted=False):
    r = etree.Element(w('r'))
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    t = etree.SubElement(r, w('delText' if deleted else 't'))
    t.text = text; t.set(XS, 'preserve')
    return r


def do_delete(p, a, b, ctx):
    if b <= a:
        return
    boundary(p, a); boundary(p, b)
    acc, targets = 0, []
    for r, t in vis_runs(p):
        if a <= acc and acc + len(t) <= b:
            targets.append(r)
        acc += len(t)
    for r in targets:
        par = r.getparent()
        if par.tag == w('ins') and par.get(w('author')) == ctx.author:
            par.remove(r)
            if len(par) == 0:
                par.getparent().remove(par)
            continue
        d = ctx.mark('del')
        par.insert(par.index(r), d)
        d.append(r)
        for c in r:
            if c.tag == w('t'):
                c.tag = w('delText')


def do_insert(p, pos, text, ctx):
    rpr = rpr_near(p, pos)
    r = boundary(p, pos)
    ins = ctx.mark('ins'); ins.append(make_run(text, rpr))
    if r is None:
        runs = vis_runs(p)
        last = lift_point(p, runs[-1][0], ctx) if runs else None
        if last is not None:
            last.addnext(ins)
        else:
            p.append(ins)
        return
    top = lift_point(p, r, ctx)
    p.insert(p.index(top), ins)


def _coalesce(ops, short=3):
    """Funde trechos iguais curtos entre duas alterações, evitando fragmentos de um ou dois caracteres."""
    out = []
    for i, op in enumerate(ops):
        tag, i1, i2, j1, j2 = op
        inner = 0 < i < len(ops) - 1
        if tag == 'equal' and inner and (i2 - i1) <= short and out and out[-1][0] != 'equal' and ops[i + 1][0] != 'equal':
            out[-1] = ('replace', out[-1][1], i2, out[-1][3], j2)
            continue
        if tag != 'equal' and out and out[-1][0] != 'equal':
            out[-1] = ('replace', out[-1][1], i2, out[-1][3], j2)
            continue
        out.append(op)
    return out


def replace(p, old, new, ctx, whole=False):
    normalize_runs(p)
    vis = visible(p)
    assert vis.count(old) == 1, (vis.count(old), old[:90])
    base = vis.index(old)
    ot, nt = TOK.findall(old), TOK.findall(new)
    sm = SequenceMatcher(None, ot, nt, autojunk=False)
    ops = [('replace', 0, len(ot), 0, len(nt))] if whole or sm.ratio() < 0.4 else _coalesce(sm.get_opcodes())
    pos = [0]
    for t in ot:
        pos.append(pos[-1] + len(t))
    for tag, i1, i2, j1, j2 in reversed(ops):
        if tag == 'equal':
            continue
        a, b = base + pos[i1], base + pos[i2]
        if j2 > j1:
            do_insert(p, b, ''.join(nt[j1:j2]), ctx)
        if i2 > i1:
            do_delete(p, a, b, ctx)
    got = visible(p)
    assert got == vis[:base] + new + vis[base + len(old):], 'resultado divergente'


def insert_paragraph_after(anchor, tpl, text, ctx):
    p = etree.Element(w('p'))
    ppr = tpl.find(w('pPr'))
    ppr = copy.deepcopy(ppr) if ppr is not None else etree.Element(w('pPr'))
    for ch in list(ppr):
        if ch.tag == w('pPrChange'):
            ppr.remove(ch)
    rpr = ppr.find(w('rPr'))
    if rpr is None:
        rpr = etree.SubElement(ppr, w('rPr'))
    for ch in list(rpr):
        if ch.tag in (w('ins'), w('del')):
            rpr.remove(ch)
    rpr.insert(0, ctx.mark('ins'))
    p.append(ppr)
    ins = ctx.mark('ins'); ins.append(make_run(text, rpr_near(tpl, 1))); p.append(ins)
    anchor.addnext(p)
    return p


def split_before(p, marker, ctx):
    """Divide o parágrafo antes de `marker` com marca de parágrafo inserida (controlada)."""
    vis = visible(p)
    k = vis.index(marker)
    assert vis.count(marker) == 1 and vis[k - 1] == ' ', marker
    do_delete(p, k - 1, k, ctx)
    r = boundary(p, k - 1)
    top = lift_point(p, r, ctx)
    np_ = etree.Element(w('p'))
    ppr = p.find(w('pPr'))
    np_.append(copy.deepcopy(ppr))
    sib = list(p)[list(p).index(top):]
    for s in sib:
        np_.append(s)
    rpr = ppr.find(w('rPr'))
    if rpr is None:
        rpr = etree.SubElement(ppr, w('rPr'))
    for ch in list(rpr):
        if ch.tag in (w('ins'), w('del')):
            rpr.remove(ch)
    rpr.insert(0, ctx.mark('ins'))
    p.addnext(np_)
    return np_


BLOCK_PPR = ('<w:pPr xmlns:w="%s"><w:pStyle w:val="Citao"/><w:spacing w:after="80" w:line="276" w:lineRule="auto"/>'
             '<w:ind w:left="1134" w:right="567"/><w:jc w:val="both"/></w:pPr>' % W)


def _block_ppr(ctx):
    ppr = etree.fromstring(BLOCK_PPR)
    rpr = etree.SubElement(ppr, w('rPr'))
    rpr.append(ctx.mark('ins'))
    return ppr


def insert_block_after(anchor, tpl, text, ctx):
    """Parágrafo novo, não numerado, em estilo de citação recuada (inserção controlada)."""
    p = etree.Element(w('p'))
    p.append(_block_ppr(ctx))
    ins = ctx.mark('ins'); ins.append(make_run(text, rpr_near(tpl, 1))); p.append(ins)
    anchor.addnext(p)
    return p


def to_block(p, ctx):
    """Converte parágrafo numerado em bloco de citação recuado, com alteração de formatação controlada."""
    old = p.find(w('pPr'))
    new = etree.fromstring(BLOCK_PPR)
    if old is not None:
        orpr = old.find(w('rPr'))
        if orpr is not None:
            new.append(copy.deepcopy(orpr))
        ch = ctx.mark('pPrChange')
        prev = etree.SubElement(ch, w('pPr'))
        for c in old:
            if c.tag not in (w('rPr'), w('pPrChange'), w('sectPr')):
                prev.append(copy.deepcopy(c))
        new.append(ch)
        p.replace(old, new)
    else:
        p.insert(0, new)
    return p


def split_at(p, k, ctx):
    """Divide o parágrafo na posição visível k (precedida de espaço, que é excluído)."""
    vis = visible(p)
    assert 0 < k < len(vis) and vis[k - 1] == ' ', (k, vis[max(0, k - 20):k + 20])
    marker = vis[k:k + 60]
    assert vis.count(marker) == 1, marker
    return split_before(p, marker, ctx)


HEAD_PPR = ('<w:pPr xmlns:w="%s"><w:keepNext/><w:spacing w:before="60" w:after="40"/>'
            '<w:ind w:left="1134" w:right="567"/><w:jc w:val="both"/></w:pPr>' % W)


def insert_head_after(anchor, tpl, text, ctx):
    """Rótulo não numerado (negrito) que abre um conjunto de redações sugeridas."""
    p = etree.Element(w('p'))
    ppr = etree.fromstring(HEAD_PPR)
    rpr = etree.SubElement(ppr, w('rPr')); rpr.append(ctx.mark('ins'))
    p.append(ppr)
    base = rpr_near(tpl, 1)
    base = copy.deepcopy(base) if base is not None else etree.Element(w('rPr'))
    if base.find(w('b')) is None:
        b = etree.Element(w('b'))
        pos = sum(1 for c in base if c.tag in (w('rStyle'), w('rFonts')))
        base.insert(pos, b)
    ins = ctx.mark('ins'); ins.append(make_run(text, base)); p.append(ins)
    anchor.addnext(p)
    return p


# ---------------------------------------------------------------- utilidades de documento

def grupos_numerados(body):
    """{número: [w:p, …]} dos parágrafos numerados na visão "tudo aceito", com a contagem de
    ``exportar_comentarios`` (numPr próprio no nível 0, numId diferente de 0, texto visível; marca de
    parágrafo excluída junta o parágrafo ao seguinte; linhas excluídas e caixas de texto ficam fora)."""
    import exportar_comentarios as ec
    num, k = {}, 0
    for g in ec.paragrafos_aceitos(body):
        if ec.numerado(g[-1]) and ''.join(visible(p) for p in g).strip():
            k += 1
            num[k] = g
    return num


def paragrafos_numerados(body):
    """{número: w:p}; o w:p é o último do grupo (o que leva a numeração). Ver ``grupos_numerados``."""
    return {n: g[-1] for n, g in grupos_numerados(body).items()}


def responder(comments_root, cid, ctx=None, texto=None, antes=None, depois=None, atual=None):
    """Reescreve (texto) ou corrige um trecho (antes → depois) do comentário ``cid``; devolve o novo texto.

    Com ``ctx``, só reescreve comentário do próprio autor (``ctx.author``): a resposta de outra pessoa
    não se altera. Com ``atual``, confere antes o texto inteiro do comentário."""
    alvo = [c for c in comments_root.iter(w('comment')) if c.get(w('id')) == str(cid)]
    if len(alvo) != 1:
        raise ValueError(f"comentário {cid} não encontrado (ou repetido)")
    c = alvo[0]
    if ctx is not None and (c.get(w('author')) or '') != ctx.author:
        raise ValueError(f"comentário {cid} é de «{c.get(w('author')) or 'sem autor'}», não de «{ctx.author}»: não reescrevo")
    if atual is not None:
        corpo = '\n'.join(''.join(x.text or '' for x in p.iter(w('t'))) for p in c.iter(w('p')))
        if ' '.join(corpo.split()) != ' '.join(atual.split()):
            raise ValueError(f"comentário {cid} mudou desde a leitura: «{corpo[:70]}»")
    if texto is not None:
        ts = list(c.iter(w('t')))
        if not ts:
            raise ValueError(f"comentário {cid} sem texto")
        ts[0].text = texto; ts[0].set(XS, 'preserve')
        for x in ts[1:]:
            x.text = ''
        return texto
    hits = 0
    for p in c.iter(w('p')):
        ts = list(p.iter(w('t')))
        s = ''.join(x.text or '' for x in ts)
        if antes in s:
            if s.count(antes) != 1:
                raise ValueError(f"trecho repetido no comentário {cid}: {antes[:60]}")
            ts[0].text = s.replace(antes, depois); ts[0].set(XS, 'preserve')
            for x in ts[1:]:
                x.text = ''
            hits += 1
    if hits != 1:
        raise ValueError(f"trecho não encontrado no comentário {cid}: {antes[:60]}")
    return ''.join(x.text or '' for x in c.iter(w('t')))


_MUDANCAS = ('rPrChange', 'pPrChange', 'sectPrChange', 'tblPrChange', 'trPrChange', 'tcPrChange', 'tblGridChange',
             'numberingChange')


def aceitar_xml(root):
    """Aceita todas as revisões de uma parte XML (corpo, notas, comentários), como o Word faria."""
    P = w('p')
    # linha de tabela excluída sai inteira (a marca fica no trPr, não em volta das células)
    for tr in list(root.iter(w('tr'))):
        trpr = tr.find(w('trPr'))
        if trpr is not None and trpr.find(w('del')) is not None and tr.getparent() is not None:
            tr.getparent().remove(tr)
    # parágrafo com marca excluída: o conteúdo passa ao parágrafo seguinte
    for p in list(root.iter(P)):
        ppr = p.find(w('pPr'))
        rpr = ppr.find(w('rPr')) if ppr is not None else None
        if rpr is None or rpr.find(w('del')) is None:
            continue
        nx = p.getnext()
        if nx is None or nx.tag != P:
            continue
        kids = [c for c in p if c.tag != w('pPr')]
        npr = nx.find(w('pPr'))
        pos = 1 if npr is not None else 0
        for c in reversed(kids):
            nx.insert(pos, c)
        p.getparent().remove(p)
    for tag in ('del', 'moveFrom'):
        for el in list(root.iter(w(tag))):
            if el.getparent() is not None:
                el.getparent().remove(el)  # conteúdo excluído ou marca de parágrafo já fundida
    for tag in ('ins', 'moveTo'):
        for el in list(root.iter(w(tag))):
            par = el.getparent()
            if par is None:
                continue
            if par.tag == w('rPr'):
                par.remove(el)
                continue
            i = par.index(el)
            for c in list(el):
                par.insert(i, c); i += 1
            par.remove(el)
    for tag in ('moveFromRangeStart', 'moveFromRangeEnd', 'moveToRangeStart', 'moveToRangeEnd'):
        for el in list(root.iter(w(tag))):
            el.getparent().remove(el)
    for tag in _MUDANCAS:
        for el in list(root.iter(w(tag))):
            el.getparent().remove(el)
    return root


def aceitar_tudo(entrada, saida):
    """Grava em ``saida`` a visão "tudo aceito" do DOCX ``entrada``, preservando os comentários."""
    import zipfile
    partes = ('word/document.xml', 'word/footnotes.xml', 'word/endnotes.xml', 'word/comments.xml')
    with zipfile.ZipFile(entrada) as zin, zipfile.ZipFile(saida, 'w', zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            dados = zin.read(info.filename)
            if info.filename in partes or info.filename.startswith('word/header') or info.filename.startswith('word/footer'):
                root = etree.fromstring(dados)
                aceitar_xml(root)
                dados = etree.tostring(root, xml_declaration=True, encoding='UTF-8', standalone=True)
            zout.writestr(info, dados)
