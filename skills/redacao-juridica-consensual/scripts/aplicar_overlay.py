#!/usr/bin/env python3
"""Aplica alterações controladas (diff por palavra) a um DOCX, a partir de um JSON, e gera a visão
"tudo aceito" (a limpa). Serve tanto ao documento limpo (caso mais comum: a versão aprovada, sem
revisões de ninguém) quanto ao DOCX já revisado por outra pessoa, cujas revisões não são aceitas nem
rejeitadas.

Substitui o bloco de código repetido a cada rodada e os montadores improvisados (localizar o
parágrafo ou o trecho, conferir que é único, aplicar o diff por palavras preservando a formatação,
contar palavras, reescrever respostas a comentários, validar, conferir a integridade e gerar a limpa).
Requer ``lxml``.

Arquivo de alterações (JSON)::

    {
      "sha256_entrada": "…",                      ← opcional: recusa se a entrada for outra
      "paragrafos": [
        {"n": 13, "atual": "texto integral de hoje", "texto": "novo texto integral do parágrafo 13"},
        {"n": 46, "acrescentar": " Frase acrescida ao fim."},
        {"n": 51, "antes": "trecho único atual", "depois": "trecho novo"},
        {"ancora": "trecho único em qualquer parágrafo", "depois": "trecho novo"},
        {"ancora_paragrafo": "Síntese. Como antecipado", "texto": "Síntese. Novo texto integral."}
      ],
      "respostas": [
        {"id": "221", "atual": "resposta de hoje", "texto": "nova resposta integral"},
        {"id": "235", "antes": "trecho da resposta", "depois": "trecho novo"}
      ]
    }

Itens por número (``n``) — comportamento inalterado:

* ``n`` é o número do parágrafo na numeração automática do Word, contado como em
  ``exportar_comentarios`` (numPr próprio no nível 0, texto visível, visão "tudo aceito");
* ``atual`` (preimagem) confere o texto antes de trocar; sem ele, o texto integral sai com aviso;
* ``texto`` troca o parágrafo inteiro, ``acrescentar`` acresce ao fim, ``antes``/``depois`` troca um
  trecho que tem de ser único no parágrafo.

Itens por âncora — alcançam QUALQUER parágrafo do corpo do documento, numerado ou não (ementa com
rótulo em negrito, linhas do quadro de hipóteses, alíneas "a) … g)" do anexo, parágrafos do anexo
numerados por outra lista, células de tabela):

* ``{"ancora": T, "depois": N}`` troca o trecho ``T`` por ``N``. ``T`` tem de ocorrer UMA vez em todo o
  documento (texto visível de cada parágrafo, sem os trechos excluídos); com 0 ou mais de uma ocorrência
  a execução é recusada e o erro lista os parágrafos em que ele aparece. O diff por palavra é feito
  dentro do(s) run(s) que contêm o trecho — que pode atravessar vários runs (negrito + texto comum,
  itálico no meio) — e cada run mantém a sua formatação: o texto igual não é tocado, o excluído sai com
  o rPr do seu run e o inserido em substituição herda o rPr do primeiro caractere substituído (a
  inserção pura herda o do caractere anterior, como no Word). ``"depois": ""`` exclui o trecho.
* ``{"ancora_paragrafo": INICIO, "texto": NOVO}`` substitui o texto integral do único parágrafo cujo
  texto visível começa por ``INICIO`` (espaços normalizados). Se o parágrafo abre com rótulo em negrito
  (runs iniciais com ``w:b``, como "Síntese." ou "a)") e ``NOVO`` começa pelo mesmo rótulo, o rótulo é
  preservado intacto e o diff corre só sobre o resto. ``atual`` (opcional) confere o texto integral.
* A âncora deve ser a menor porção que a torne única; os itens são aplicados na ordem da lista, cada um
  sobre o resultado dos anteriores. Notas de rodapé, cabeçalhos e caixas de texto ficam fora do alcance.

Limite de palavras: cada parágrafo NUMERADO alterado (por ``n`` ou por âncora) tem de ficar com até
``--max-palavras`` palavras (padrão 120), salvo ``"permitir_longo": true`` no item; os parágrafos sem
número (ementa, quadro, anexo) têm a contagem relatada, sem limite. Só se reescrevem respostas do
próprio ``--autor``.

Opções de saída e conferência (todas sobre o provisório: reprovado, nada é gravado — nem o redline
nem a limpa):

* ``--limpa LIMPA.docx`` (ou ``--aceito``): grava também a versão com tudo aceito, como DOCX;
* ``--integridade``: roda ``integridade_docx.conferir(base=ENTRADA, limpa=LIMPA, redline=SAIDA)`` —
  aceitar tudo reproduz a limpa, rejeitar tudo reproduz a entrada, notas preservadas — e recusa se
  divergir; dispensa ``--limpa`` (usa uma limpa provisória);
* ``--validador … --original …``: roda o ``validate.py`` da skill docx (só o autor alterou);
* ``--data ISO``: data das marcas (``2026-11-05`` ou ``2026-11-05T18:00:00Z``; sem fuso, UTC);
  padrão, agora. ``--autor``: nome nas marcas.

Documento limpo (caso mais comum): a entrada é a versão aprovada; o redline (SAIDA) traz só as marcas
do ``--autor``; a limpa é a nova versão. A própria entrada serve de ``--original`` do validador::

    aplicar_overlay.py v20_clean.docx v21_track.docx --alteracoes v21.json --autor "Revisão v21" \\
        --data 2026-11-05T18:00:00Z --limpa v21_clean.docx --integridade \\
        --original v20_clean.docx --validador ~/.../docx/scripts/office/validate.py

Sobre a revisão de outra pessoa::

    aplicar_overlay.py parecer_v21.docx parecer_v22.docx --alteracoes v22.json --autor "Nicholas Jacob" \\
        --aceito aceito_v22.docx --original revisao_patricia.docx --validador ~/.../docx/scripts/office/validate.py
    aplicar_overlay.py --aceitar parecer_v22.docx aceito_v22.docx

Saída: 0 gravado; 1 recusado (nada gravado); 2 erro de uso.
"""

from __future__ import annotations

import argparse
import copy
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from lxml import etree
    import overlay_docx as O  # noqa: E402
except ImportError:  # pragma: no cover - depende do ambiente
    print("aplicar_overlay.py requer lxml: pip install lxml", file=sys.stderr)
    raise


def _ler(z: zipfile.ZipFile, nome: str):
    try:
        return etree.fromstring(z.read(nome))
    except KeyError:
        return None


def _esp(s: str) -> str:
    return " ".join(s.split())


def _curto(s: str, n: int = 70) -> str:
    s = _esp(s)
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- substituição posicional

def _rpr_limpo(r):
    rpr = r.find(O.w("rPr")) if r is not None else None
    if rpr is None:
        return None
    rpr = copy.deepcopy(rpr)
    for ch in list(rpr):
        if ch.tag in (O.w("rPrChange"), O.w("ins"), O.w("del")):
            rpr.remove(ch)
    return rpr


def _rpr_em(p, pos):
    """rPr (sem marcas) do run visível que contém o caractere ``pos``."""
    acc = 0
    for r, t in O.vis_runs(p):
        if acc <= pos < acc + len(t):
            return _rpr_limpo(r)
        acc += len(t)
    return O.rpr_near(p, pos)


def _inserir(p, pos, texto, rpr, ctx):
    """Como ``overlay_docx.do_insert``, mas com o rPr escolhido por quem chama."""
    r = O.boundary(p, pos)
    ins = ctx.mark("ins")
    ins.append(O.make_run(texto, rpr))
    if r is None:
        runs = O.vis_runs(p)
        last = O.lift_point(p, runs[-1][0], ctx) if runs else None
        if last is not None:
            last.addnext(ins)
        else:
            p.append(ins)
        return
    top = O.lift_point(p, r, ctx)
    p.insert(p.index(top), ins)


def substituir_em(p, base: int, old: str, new: str, ctx, inteiro: bool = False) -> None:
    """Troca ``old`` (que começa na posição visível ``base`` de ``p``) por ``new`` em controle de
    alterações, com diff por palavra; o trecho pode atravessar vários runs, e cada run conserva o
    seu rPr. Confere o resultado."""
    O.normalize_runs(p)
    vis = O.visible(p)
    if vis[base: base + len(old)] != old:
        raise ValueError(f"posição {base} não contém «{_curto(old)}»")
    if old == new:
        return
    ot, nt = O.TOK.findall(old), O.TOK.findall(new)
    sm = SequenceMatcher(None, ot, nt, autojunk=False)
    if inteiro or not ot or sm.ratio() < 0.4:
        ops = [("replace", 0, len(ot), 0, len(nt))]
    else:
        ops = O._coalesce(sm.get_opcodes())
    pos = [0]
    for t in ot:
        pos.append(pos[-1] + len(t))
    for tag, i1, i2, j1, j2 in reversed(ops):
        if tag == "equal":
            continue
        a, b = base + pos[i1], base + pos[i2]
        if j2 > j1:
            # substituição: herda o rPr do primeiro caractere substituído; inserção pura: o do anterior
            rpr = _rpr_em(p, a) if i2 > i1 else O.rpr_near(p, b)
            _inserir(p, b, "".join(nt[j1:j2]), rpr, ctx)
        if i2 > i1:
            O.do_delete(p, a, b, ctx)
    got = O.visible(p)
    if got != vis[:base] + new + vis[base + len(old):]:
        raise ValueError(f"resultado divergente ao trocar «{_curto(old)}»")


# ---------------------------------------------------------------- localização por âncora

def _todos_paragrafos(body) -> list:
    return list(body.iter(O.w("p")))


def _tem_aninhado(p) -> bool:
    return any(True for _ in p.iter(O.w("p")) if _ is not p)


def _na_tabela(p) -> bool:
    a = p.getparent()
    while a is not None:
        if a.tag == O.w("tc"):
            return True
        a = a.getparent()
    return False


class Mapa:
    """Rótulos legíveis dos parágrafos do corpo: "§ 13" para os numerados, "parágrafo sem número"
    (com a posição física, contada do 1, e o início do texto) para os demais."""

    def __init__(self, body, grupos):
        self.body = body
        self.num = {}
        for n, g in grupos.items():
            for q in g:
                self.num[q] = n
        self.ordem = {p: k for k, p in enumerate(_todos_paragrafos(body), 1)}

    def numerado(self, p) -> bool:
        return p in self.num

    def rotulo(self, p, com_texto: bool = True) -> str:
        if p in self.num:
            s = f"§ {self.num[p]}"
        else:
            s = f"parágrafo sem número (posição {self.ordem.get(p, '?')}"
            s += ", tabela)" if _na_tabela(p) else ")"
        if com_texto:
            s += f" «{_curto(O.visible(p), 50)}»"
        return s


def localizar(body, ancora: str, mapa: Mapa):
    """Devolve ``(p, posição)`` da única ocorrência de ``ancora``; senão, ValueError com os locais."""
    if not ancora:
        raise ValueError("âncora vazia")
    achados, fora = [], []
    for p in _todos_paragrafos(body):
        vis = O.visible(p)
        if ancora not in vis:
            continue
        if _tem_aninhado(p):  # caixa de texto: o texto conta no parágrafo interno
            fora.append(p)
            continue
        k = vis.find(ancora)
        while k >= 0:
            achados.append((p, k))
            k = vis.find(ancora, k + 1)
    if len(achados) == 1:
        return achados[0]
    if not achados:
        if fora:
            raise ValueError(f"âncora «{_curto(ancora)}» só aparece em parágrafo com caixa de texto "
                             f"({mapa.rotulo(fora[0])}): altere-o à mão")
        alvo = _esp(ancora)
        quase = [p for p in _todos_paragrafos(body) if alvo and alvo in _esp(O.visible(p))]
        dica = ""
        if quase:
            dica = "; com espaços normalizados aparece em: " + "; ".join(mapa.rotulo(p) for p in quase[:5])
        raise ValueError(f"âncora «{_curto(ancora)}» não encontrada em nenhum parágrafo{dica}")
    locais = []
    for p, _ in achados:
        r = mapa.rotulo(p)
        if not locais or locais[-1][0] != r:
            locais.append([r, 1])
        else:
            locais[-1][1] += 1
    lista = "; ".join(r + (f" ({c}×)" if c > 1 else "") for r, c in locais)
    raise ValueError(f"âncora «{_curto(ancora)}» aparece {len(achados)} vezes — torne-a única: {lista}")


def _negrito(r) -> bool:
    rpr = r.find(O.w("rPr"))
    b = rpr.find(O.w("b")) if rpr is not None else None
    if b is None:
        return False
    return (b.get(O.w("val")) or "true").lower() not in ("0", "false", "off")


def rotulo_negrito(p) -> tuple[int, int]:
    """Posições visíveis ``(início, fim)`` dos runs iniciais em negrito (ex.: "Síntese. ", "a) "),
    saltados os runs só de espaço do começo; ``(0, 0)`` se o parágrafo não abre em negrito."""
    acc, ini, fim = 0, None, None
    for r, t in O.vis_runs(p):
        if ini is None and not t.strip() and not _negrito(r):
            acc += len(t)
            continue
        if not _negrito(r):
            break
        if ini is None:
            ini = acc
        acc += len(t)
        fim = acc
    return (ini, fim) if ini is not None else (0, 0)


def localizar_paragrafo(body, inicio: str, mapa: Mapa):
    alvo = _esp(inicio)
    if not alvo:
        raise ValueError("ancora_paragrafo vazia")
    achados = [p for p in _todos_paragrafos(body)
               if not _tem_aninhado(p) and _esp(O.visible(p)).startswith(alvo)]
    if len(achados) == 1:
        return achados[0]
    if not achados:
        raise ValueError(f"nenhum parágrafo começa por «{_curto(inicio)}»")
    raise ValueError(f"{len(achados)} parágrafos começam por «{_curto(inicio)}» — alongue o início: "
                     + "; ".join(mapa.rotulo(p) for p in achados))


def substituir_paragrafo(p, novo: str, ctx) -> bool:
    """Troca o texto integral de ``p`` por ``novo``; preserva o rótulo inicial em negrito quando
    ``novo`` começa por ele. Devolve True se o rótulo foi preservado."""
    O.normalize_runs(p)
    vis = O.visible(p)
    s = len(vis) - len(vis.lstrip())
    e = len(vis.rstrip())
    old = vis[s:e]
    novo = novo.strip()
    ini, fim = rotulo_negrito(p)
    rot = vis[s:fim].rstrip() if fim > s and ini <= s else ""
    if rot and novo.startswith(rot):
        k = len(rot)
        while k < min(len(old), len(novo)) and old[k] == novo[k] and old[k].isspace():
            k += 1  # o espaço depois do rótulo também fica (não herda o negrito no texto novo)
        substituir_em(p, s + k, old[k:], novo[k:], ctx)
        return True
    substituir_em(p, s, old, novo, ctx)
    return False


# ---------------------------------------------------------------- aplicação

def aplicar(entrada: Path, saida: Path, alteracoes: dict, autor: str, data: str, max_palavras: int = 120) -> list[str]:
    """Aplica as alterações e grava ``saida``; devolve o relatório, uma linha por alteração."""
    rel: list[str] = []
    with zipfile.ZipFile(entrada) as z:
        doc = _ler(z, "word/document.xml")
        com = _ler(z, "word/comments.xml")
        infos = z.infolist()
        dados = {i.filename: z.read(i.filename) for i in infos}
    ctx = O.Ctx(doc, autor, data)
    body = doc.find(O.w("body"))
    grupos = O.grupos_numerados(body)
    mapa = Mapa(body, grupos)
    longos = []
    tocados: dict = {}  # parágrafo alterado por âncora → permitir_longo; o limite vale para a contagem final

    def contar(p, rotulo, alt):
        palavras = len(O.visible(p).split())
        rel.append(f"{rotulo}: {palavras} palavras")
        tocados[p] = tocados.get(p, False) or bool(alt.get("permitir_longo"))

    for alt in alteracoes.get("paragrafos", []):
        if "ancora" in alt:
            if "depois" not in alt:
                raise ValueError(f"item com 'ancora' sem 'depois': «{_curto(alt['ancora'])}»")
            p, k = localizar(body, alt["ancora"], mapa)
            substituir_em(p, k, alt["ancora"], alt["depois"], ctx)
            contar(p, f"âncora «{_curto(alt['ancora'], 40)}» → {mapa.rotulo(p, False)}", alt)
            continue
        if "ancora_paragrafo" in alt:
            if "texto" not in alt:
                raise ValueError(f"item com 'ancora_paragrafo' sem 'texto': «{_curto(alt['ancora_paragrafo'])}»")
            p = localizar_paragrafo(body, alt["ancora_paragrafo"], mapa)
            atual = O.visible(p)
            if "atual" in alt and _esp(atual) != _esp(alt["atual"]):
                raise ValueError(f"{mapa.rotulo(p, False)} mudou desde a leitura (campo 'atual' não confere): "
                                 f"«{_curto(atual)}»")
            preservou = substituir_paragrafo(p, alt["texto"], ctx)
            nota = ", rótulo em negrito preservado" if preservou else ""
            contar(p, f"parágrafo «{_curto(alt['ancora_paragrafo'], 40)}» → {mapa.rotulo(p, False)}{nota}", alt)
            continue
        if "n" not in alt:
            raise ValueError(f"item sem 'n', 'ancora' nem 'ancora_paragrafo': {_curto(json.dumps(alt, ensure_ascii=False))}")
        n = int(alt["n"])
        if n not in grupos:
            raise ValueError(f"parágrafo {n} não existe (o documento tem {len(grupos)} parágrafos numerados)")
        com_texto = [q for q in grupos[n] if O.visible(q).strip()]
        if len(com_texto) != 1:  # marca de parágrafo excluída juntando dois textos: o trecho pode cruzar a junção
            raise ValueError(f"§ {n} junta {len(com_texto)} parágrafos com texto (marca excluída): altere-o à mão")
        p = com_texto[0]
        O.normalize_runs(p)
        atual = O.visible(p)
        if "atual" in alt and " ".join(atual.split()) != " ".join(alt["atual"].split()):
            raise ValueError(f"§ {n} mudou desde a leitura (campo 'atual' não confere): «{atual[:70]}»")
        if "texto" in alt:
            if "atual" not in alt:
                rel.append(f"§ {n}: aviso — texto integral sem 'atual' (preimagem) para conferir")
            antes, depois = atual.strip(), alt["texto"]
        elif "acrescentar" in alt:
            antes = atual.rstrip()[-60:]
            depois = antes + alt["acrescentar"]
        else:
            antes, depois = alt["antes"], alt["depois"]
        if atual.count(antes) != 1:
            raise ValueError(f"§ {n}: o trecho aparece {atual.count(antes)} vezes: «{antes[:70]}»")
        O.replace(p, antes, depois, ctx)
        palavras = len(O.visible(p).split())
        rel.append(f"§ {n}: {palavras} palavras")
        if palavras > max_palavras and not alt.get("permitir_longo"):
            longos.append(f"§ {n} ({palavras})")
    for p, permitir in tocados.items():
        palavras = len(O.visible(p).split())
        rot = mapa.rotulo(p, False)
        if mapa.numerado(p) and palavras > max_palavras and not permitir and not any(x.startswith(rot + " (") for x in longos):
            longos.append(f"{rot} ({palavras})")
    if longos:
        raise ValueError(f"acima de {max_palavras} palavras: {', '.join(longos)}; enxugue ou marque permitir_longo")
    for r in alteracoes.get("respostas", []):
        if com is None:
            raise ValueError("o documento não tem comentários")
        O.responder(com, r["id"], ctx, texto=r.get("texto"), antes=r.get("antes"), depois=r.get("depois"),
                    atual=r.get("atual"))
        rel.append(f"resposta {r['id']}: reescrita" if "texto" in r else f"resposta {r['id']}: trecho substituído")
    dados["word/document.xml"] = etree.tostring(doc, xml_declaration=True, encoding="UTF-8", standalone=True)
    if com is not None:
        dados["word/comments.xml"] = etree.tostring(com, xml_declaration=True, encoding="UTF-8", standalone=True)
    with zipfile.ZipFile(saida, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in infos:
            zout.writestr(i, dados[i.filename])
    return rel


def validar(validador: Path, docx: Path, original: Path, autor: str) -> tuple[bool, str]:
    proc = subprocess.run([sys.executable, str(validador), str(docx), "--original", str(original), "--author", autor],
                          capture_output=True, text=True)
    ultima = (proc.stdout.strip().splitlines() or proc.stderr.strip().splitlines() or [""])[-1]
    return proc.returncode == 0 and "PASSED" in proc.stdout, ultima


def pdf(docx: Path, pasta: Path) -> Path | None:
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    subprocess.run([soffice, "--headless", "--convert-to", "pdf", "--outdir", str(pasta), str(docx)],
                   capture_output=True, text=True)
    alvo = pasta / (docx.stem + ".pdf")
    return alvo if alvo.exists() else None


def data_iso(valor: str) -> str:
    """Normaliza a data das marcas para ``AAAA-MM-DDTHH:MM:SSZ`` (sem fuso: UTC)."""
    try:
        d = dt.datetime.fromisoformat(valor.strip().replace("Z", "+00:00").replace("z", "+00:00"))
    except ValueError:
        raise argparse.ArgumentTypeError(f"data ISO inválida: {valor!r} (ex.: 2026-11-05 ou 2026-11-05T18:00:00Z)")
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("entrada", type=Path)
    ap.add_argument("saida", type=Path)
    ap.add_argument("--aceitar", action="store_true", help="só gera a visão tudo aceito de ENTRADA em SAIDA")
    ap.add_argument("--alteracoes", type=Path, help="JSON com as alterações (ver o cabeçalho)")
    ap.add_argument("--autor", default="Nicholas Jacob")
    ap.add_argument("--data", type=data_iso, default=dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    help="data ISO das marcas (padrão: agora, UTC)")
    ap.add_argument("--max-palavras", type=int, default=120)
    ap.add_argument("--aceito", type=Path, help="grava também a visão tudo aceito")
    ap.add_argument("--limpa", type=Path, help="grava também a versão limpa (tudo aceito), como DOCX")
    ap.add_argument("--integridade", action="store_true",
                    help="confere com integridade_docx (base=ENTRADA, limpa, redline=SAIDA); divergente, nada é gravado")
    ap.add_argument("--pdf", action="store_true", help="com --aceito/--limpa, converte a limpa em PDF (LibreOffice)")
    ap.add_argument("--original", type=Path, help="DOCX de referência para o validador")
    ap.add_argument("--validador", type=Path, help="validate.py da skill docx (confere que só o autor alterou)")
    ap.add_argument("--sha256", help="sha256 esperado da entrada (ou 'sha256_entrada' no JSON); diferente, recusa")
    args = ap.parse_args(argv)

    if not args.entrada.exists():
        print(f"arquivo não encontrado: {args.entrada}", file=sys.stderr)
        return 2
    if args.aceitar:
        O.aceitar_tudo(args.entrada, args.saida)
        print(f"tudo aceito: {args.saida}")
        return 0
    if not args.alteracoes:
        print("informe --alteracoes (ou --aceitar)", file=sys.stderr)
        return 2
    alteracoes = json.loads(args.alteracoes.read_text(encoding="utf-8"))
    esperado = args.sha256 or alteracoes.get("sha256_entrada")
    if esperado:
        real = hashlib.sha256(args.entrada.read_bytes()).hexdigest()
        if real != esperado.lower():
            print(f"RECUSADO: a entrada mudou (sha256 {real[:16]}…, esperado {esperado[:16]}…); nada foi gravado.")
            return 1
    destinos_limpa = [d for d in (args.limpa, args.aceito) if d is not None]
    with tempfile.TemporaryDirectory() as tmp:
        provisorio = Path(tmp) / args.saida.name
        try:
            rel = aplicar(args.entrada, provisorio, alteracoes, args.autor, args.data, args.max_palavras)
        except (ValueError, AssertionError) as e:
            print(f"RECUSADO: {e}; nada foi gravado.")
            return 1
        for linha in rel:
            print(linha)
        if args.validador and args.original:  # valida o provisório: reprovado, o destino fica como estava
            ok, msg = validar(args.validador, provisorio, args.original, args.autor)
            print(f"validação: {msg}")
            if not ok:
                print("RECUSADO: a validação reprovou; nada foi gravado.")
                return 1
        limpa_prov = None
        if destinos_limpa or args.integridade:
            limpa_prov = Path(tmp) / "limpa_provisoria.docx"
            O.aceitar_tudo(provisorio, limpa_prov)
        if args.integridade:
            import integridade_docx as I  # noqa: E402

            try:
                res = I.conferir(args.entrada, limpa_prov, provisorio)
            except I.IntegridadeErro as e:
                print(f"RECUSADO: integridade não conferida ({e}); nada foi gravado.")
                return 1
            print(I.formatar(res))
            if not res["ok"]:
                print("RECUSADO: a integridade divergiu; nada foi gravado.")
                return 1
        shutil.copy(provisorio, args.saida)
        for destino in destinos_limpa:
            shutil.copy(limpa_prov, destino)
            print(f"tudo aceito: {destino}")
    if args.pdf and destinos_limpa:
        alvo = pdf(destinos_limpa[0], destinos_limpa[0].parent)
        print(f"PDF: {alvo}" if alvo else "PDF: LibreOffice não encontrado")
    return 0


if __name__ == "__main__":
    sys.exit(main())
