"""Gera o parecer no perfil GENES: cabeçalho, ementa, seções e parágrafos com
numeração automática do Word — número alinhado à margem esquerda e tabulação
até RECUO_NUM antes da primeira linha; as linhas seguintes voltam à margem.

Marcadores de linha: `@CAB [Rótulo|]texto`, `@EMENTA Rótulo|texto`, `## título`,
`@DATA texto`, `@ASS texto` (assinatura em negrito), `@ASS+ texto` (idem, presa à
linha seguinte), `@ASN texto` (assinatura sem negrito), `@ASN+ texto` (idem, presa
à seguinte), `@TXT texto` (parágrafo de corpo sem número: alínea de quadro,
fecho), `@ITEM texto` (item de lista recuado, sem número: diligências) e
`N. texto` (parágrafo numerado, em sequência). Em qualquer texto, `**trecho**`
sai em negrito (rótulos como **Síntese.** ou **Quesito 1 — …?**).

Notas de rodapé: marcador `[^id]` no texto e definição `[^id]: texto` em linha
própria, em qualquer lugar do arquivo — viram notas reais do Word (Times 10,
recuo 0, espaçamento simples). No perfil GENES a doutrina fica em autor-data
no texto; use nota só para explicação lateral ou quando outro perfil pedir.
Nada é convertido em nota automaticamente."""
import os, sys, re
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:   # notas de rodapé: motor compartilhado com parecer_docx.py (mesma pasta)
    from parecer_docx import extrair_notas_md, aplicar_notas_docx, NotaErro
except ImportError:
    extrair_notas_md = aplicar_notas_docx = None
    class NotaErro(ValueError): pass

CORPO_PT = 10.5
NOTA_PT = 10
RECUO_NUM_CM = 1.25
ESPACO_DEPOIS_PT = 3   # entre parágrafos numerados do corpo (perfil GENES: 3 pt)

src, out = sys.argv[1], sys.argv[2]
d = Document()
sec = d.sections[0]
sec.page_width, sec.page_height = Cm(21.0), Cm(29.7)
sec.left_margin = Cm(3.0); sec.right_margin = Cm(2.0); sec.top_margin = Cm(3.0); sec.bottom_margin = Cm(2.0)
st = d.styles['Normal']; st.font.name = 'Times New Roman'; st.font.size = Pt(CORPO_PT)
rpr = st.element.get_or_add_rPr(); rf = rpr.find(qn('w:rFonts'))
if rf is None:
    rf = rpr.makeelement(qn('w:rFonts'), {}); rpr.append(rf)
for a in ('w:ascii', 'w:hAnsi', 'w:cs', 'w:eastAsia'): rf.set(qn(a), 'Times New Roman')

# o modelo do python-docx traz <w:zoom> sem w:percent (atributo obrigatório no
# schema); o validador de OOXML acusa — completa com 100%
zoom = d.settings.element.find(qn('w:zoom'))
if zoom is not None and zoom.get(qn('w:percent')) is None:
    zoom.set(qn('w:percent'), '100')

TW = str(int(RECUO_NUM_CM * 567))

def garante_lista():
    numbering = d.part.numbering_part.element
    absn = OxmlElement('w:abstractNum'); absn.set(qn('w:abstractNumId'), '910')
    mlt = OxmlElement('w:multiLevelType'); mlt.set(qn('w:val'), 'singleLevel'); absn.append(mlt)
    lvl = OxmlElement('w:lvl'); lvl.set(qn('w:ilvl'), '0')
    # ordem do schema CT_Lvl: start, numFmt, suff, lvlText, lvlJc, pPr, rPr
    for tag, val in (('w:start', '1'), ('w:numFmt', 'decimal'), ('w:suff', 'tab'), ('w:lvlText', '%1.'), ('w:lvlJc', 'left')):
        e = OxmlElement(tag); e.set(qn('w:val'), val); lvl.append(e)
    pPr = OxmlElement('w:pPr')
    tabs = OxmlElement('w:tabs'); tab = OxmlElement('w:tab'); tab.set(qn('w:val'), 'num'); tab.set(qn('w:pos'), TW); tabs.append(tab); pPr.append(tabs)
    ind = OxmlElement('w:ind'); ind.set(qn('w:left'), '0'); ind.set(qn('w:firstLine'), '0'); pPr.append(ind)
    lvl.append(pPr)
    rp = OxmlElement('w:rPr'); f = OxmlElement('w:rFonts')
    for a in ('w:ascii', 'w:hAnsi', 'w:cs'): f.set(qn(a), 'Times New Roman')
    rp.append(f); sz = OxmlElement('w:sz'); sz.set(qn('w:val'), str(int(CORPO_PT * 2))); rp.append(sz); lvl.append(rp)
    absn.append(lvl)
    first_num = numbering.find(qn('w:num'))
    (first_num.addprevious(absn) if first_num is not None else numbering.append(absn))
    num = OxmlElement('w:num'); num.set(qn('w:numId'), '910')
    ref = OxmlElement('w:abstractNumId'); ref.set(qn('w:val'), '910'); num.append(ref)
    numbering.append(num)
    return '910'

NUM_ID = garante_lista()

def numerar(p):
    pPr = p._p.get_or_add_pPr()
    numPr = OxmlElement('w:numPr')
    il = OxmlElement('w:ilvl'); il.set(qn('w:val'), '0'); numPr.append(il)
    ni = OxmlElement('w:numId'); ni.set(qn('w:val'), NUM_ID); numPr.append(ni)
    pStyle = pPr.find(qn('w:pStyle'))
    (pStyle.addnext(numPr) if pStyle is not None else pPr.insert(0, numPr))
    tabs = OxmlElement('w:tabs'); tab = OxmlElement('w:tab'); tab.set(qn('w:val'), 'left'); tab.set(qn('w:pos'), TW); tabs.append(tab)
    numPr.addnext(tabs)

def para(text='', bold_label=None, bold_all=False, align=WD_ALIGN_PARAGRAPH.JUSTIFY, spacing=1.5, before=0, after=6, keep=False, num=False):
    p = d.add_paragraph()
    pf = p.paragraph_format; pf.alignment = align; pf.line_spacing = spacing
    pf.space_before = Pt(before); pf.space_after = Pt(after)
    if keep: pf.keep_with_next = True
    if num:
        numerar(p); pf.left_indent = Cm(0); pf.first_line_indent = Cm(0)
    if bold_label:
        r = p.add_run(bold_label + ' '); r.bold = True
    if text:
        add_runs(p, text, bold_all)
    return p

def add_runs(p, text, bold_all=False):
    """Escreve `text` convertendo `**trecho**` em negrito."""
    partes = re.split(r'(\*\*[^*]+\*\*)', text)
    for parte in partes:
        if not parte:
            continue
        if parte.startswith('**') and parte.endswith('**') and len(parte) > 4:
            r = p.add_run(parte[2:-2]); r.bold = True
        else:
            r = p.add_run(parte); r.bold = bold_all
    if '**' in ''.join(x for x in partes if not (x.startswith('**') and x.endswith('**'))):
        raise SystemExit(f'negrito sem fechamento: {text[:60]}')

texto_md, NOTAS = open(src, encoding='utf-8').read(), []
if re.search(r'\[\^[^\]\s]+\]', texto_md) and extrair_notas_md is None:
    raise SystemExit('nota de rodapé [^id] exige parecer_docx.py na mesma pasta deste script')
try:
    if extrair_notas_md is not None:
        texto_md, NOTAS = extrair_notas_md(texto_md)
except NotaErro as e:
    raise SystemExit(f'nota de rodapé: {e}')

esperado = 0
for raw in texto_md.split('\n'):
    line = raw.strip()
    if not line: continue
    if line.startswith('@CAB '):
        body = line[5:]
        if '|' in body:
            lab, txt = body.split('|', 1); para(txt.strip(), bold_label=lab.strip(), spacing=1.15, after=4)
        else:
            para(body, bold_all=True, spacing=1.15, after=8)
    elif line.startswith('@EMENTA '):
        lab, txt = line[8:].split('|', 1); para(txt.strip(), bold_label=lab.strip(), spacing=1.15, before=4, after=10)
    elif line.startswith('## '):
        para(line[3:], bold_all=True, align=WD_ALIGN_PARAGRAPH.LEFT, spacing=1.15, before=8, after=4, keep=True)
    elif line.startswith('@DATA '):
        para(line[6:], align=WD_ALIGN_PARAGRAPH.LEFT, before=6, after=10)
    elif line.startswith(('@ASS+ ', '@ASS ', '@ASN+ ', '@ASN ')):
        tag, txt = line.split(' ', 1)
        para(txt, bold_all=tag.startswith('@ASS'), align=WD_ALIGN_PARAGRAPH.LEFT, spacing=1.15, after=2,
             keep=tag.endswith('+'))
    elif line.startswith('@TXT '):
        para(line[5:], after=ESPACO_DEPOIS_PT)
    elif line.startswith('@ITEM '):
        p = para(line[6:], after=ESPACO_DEPOIS_PT); p.paragraph_format.left_indent = Cm(RECUO_NUM_CM)
    else:
        m = re.match(r'^(\d+)\. (.*)$', line)
        if not m:
            raise SystemExit(f'linha de corpo sem número: {line[:60]}')
        esperado += 1
        if int(m.group(1)) != esperado:
            raise SystemExit(f'numeração fora de sequência: {m.group(1)} (esperado {esperado})')
        para(m.group(2), num=True, after=ESPACO_DEPOIS_PT)
d.save(out)
if NOTAS:
    try:
        aplicar_notas_docx(out, NOTAS, fonte='Times New Roman', tamanho_pt=NOTA_PT)
    except NotaErro as e:
        raise SystemExit(f'nota de rodapé: {e}')
print('ok', esperado, 'parágrafos numerados automaticamente'
      + (f'; {len(NOTAS)} nota(s) de rodapé' if NOTAS else ''))
