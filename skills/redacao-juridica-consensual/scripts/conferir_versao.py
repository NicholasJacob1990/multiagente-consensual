#!/usr/bin/env python3
"""Um comando por versão: roda a caixa de ferramentas da skill sobre a versão nova e monta a seção "Conferências automáticas" da nota de revisão.

A caixa de ferramentas só protege a versão em que roda. Um parágrafo de 127 palavras
(teto do perfil: 120) atravessou da v18 à v20 sem alerta, e o parecer chegou a 31
páginas contra o limite de 15 do perfil porque a pré-auditoria nunca rodou com
``--pdf``. Este orquestrador roda tudo, sempre, na mesma ordem, e entrega o
resultado pronto para colar na nota de revisão (``references/nota-de-revisao.md``).

Passos (cada script irmão é chamado por subprocesso, com ``sys.executable`` e o
caminho desta pasta, depois de ler o ``--help`` dele para só passar opções que ele
aceita):

1. ``docx_para_md.py`` nas duas versões (Markdown em pasta temporária);
2. PDF da nova com ``soffice --headless --convert-to pdf`` (perfil do LibreOffice
   próprio, na pasta temporária), salvo ``--sem-pdf``; páginas contadas com
   ``pdfinfo`` ou, sem ele, pelo ``/Count`` da árvore de páginas do PDF;
3. ``pre_auditoria_parecer.py`` na nova, com ``--anterior``, ``--perfil``,
   ``--max-palavras``, ``--mapa-origem`` e ``--refutadas`` quando dados, e
   ``--pdf``/``--max-paginas`` quando houver PDF e limite;
4. ``inventario_fatos.py ANTERIOR NOVA --md`` (tabela de acréscimos, com a coluna
   «Fonte (página)» em branco para preencher, e de supressões);
5. ``verificar_remissoes.py conferir --parecer NOVA.docx``;
6. ``checar_refutadas.py`` se ``--refutadas``;
7. ``checar_decisoes.py`` se ``--decisoes`` (e se o script existir);
8. ``integridade_docx.py --base ANTERIOR --limpa NOVA --redline R`` se ``--redline``
   (com ``--divididos``/``--fundidos``).

Bloqueantes são os que cada ferramenta marca como tais (pré-auditoria e remissões,
pela severidade; refutadas, cada acerto; integridade, cada verificação que falha).
Supressões do inventário e decisões acusadas por ``checar_decisoes.py`` entram como
alerta (decisão só bloqueia se a ferramenta lhe der severidade ``bloqueante``): o
padrão de uma decisão também casa com o texto que a cumpre, e cabe ao revisor
confirmar se ela foi reaberta.

Script ausente, ``--help`` que falha, erro de uso (código 2) ou erro interno
(traceback) viram "não executado", com o motivo, e o orquestrador segue.

Limite de páginas: ``--max-paginas`` ou, sem ele, o do perfil (``genes``: 15,
``references/perfil-parecer-genes.md``). Acima do limite é bloqueante: enxugar ou
registrar a ampliação em ``decisoes.json`` e repassar o novo valor.

A seção gerada traz: hashes SHA-256 da anterior, da nova e do comparativo; páginas;
uma linha por ferramenta (resultado, número de bloqueantes e alertas e a lista de
bloqueantes; no modo ``profundo``, também os alertas); a tabela do inventário de
fatos; refutadas e decisões acusadas; integridade do comparativo. Sem
``--nota-saida``, o Markdown vai ao stdout antes do resumo.

Registro de versões (``--registro versoes.json``; modelo vazio em
``versoes_modelo.json``)::

    {"caso": "...", "versoes": [{"versao": "v21", "base_sha256": "...",
      "limpa_sha256": "...", "redline_sha256": "... ou null", "data": "2026-11-04",
      "modo": "conciso", "resumo": "...", "resultado": "reprovada",
      "bloqueantes": ["pre_auditoria_parecer: [palavras] § 166: ..."]}]}

A entrada da mesma ``versao`` é substituída; as demais são preservadas. ``caso`` vem
de ``--caso`` ou, se o registro ainda não tiver, do campo ``caso`` das refutadas ou
das decisões. ``resultado``: ``reprovada`` (há bloqueante), ``incompleta`` (sem
bloqueante, mas alguma ferramenta não foi executada) ou ``aprovada``.

Uso::

    conferir_versao.py --anterior v20.docx --nova v21.docx --redline v21_track.docx \\
        --refutadas refutadas.json --decisoes decisoes.json --perfil genes \\
        --max-paginas 15 --versao v21 --modo conciso --resumo "enxugamento do Anexo" \\
        --registro versoes.json --nota-saida conferencias.md --json conferencia_v21.json

Código de saída: 1 se houver bloqueante (de qualquer ferramenta), afirmação refutada,
falha de integridade ou páginas acima do limite; 0 caso contrário; 2 em erro de uso.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

PASTA = Path(__file__).resolve().parent
LIMITE_PAGINAS_PERFIL = {"genes": 15}
TIMEOUT = 900
TIMEOUT_PDF = 300


@dataclass
class Execucao:
    ferramenta: str
    status: str = "não executado"  # ok | achados | não executado | dispensado
    motivo: str = ""
    comando: list[str] = field(default_factory=list)
    codigo: int | None = None
    bloqueantes: list[str] = field(default_factory=list)
    alertas: list[str] = field(default_factory=list)
    resumo: str = ""
    stdout: str = ""
    dados: object = None

    @property
    def executado(self) -> bool:
        return self.status in ("ok", "achados")


# --------------------------------------------------------------------------- utilidades


def sha256(path: Path | None) -> str | None:
    if path is None:
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for bloco in iter(lambda: f.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


_AJUDA: dict[tuple, tuple[int, str] | None] = {}


def ajuda(script: str, *sub: str, pasta: Path = PASTA) -> str | None:
    """Texto do ``--help`` do script irmão (``None`` se ausente ou se o ``--help`` falhar)."""
    caminho = pasta / script
    chave = (str(caminho), sub)
    if chave not in _AJUDA:
        if not caminho.exists():
            _AJUDA[chave] = None
        else:
            try:
                r = subprocess.run([sys.executable, str(caminho), *sub, "--help"], capture_output=True,
                                   text=True, timeout=120)
                _AJUDA[chave] = (r.returncode, r.stdout + r.stderr)
            except (OSError, subprocess.TimeoutExpired) as e:
                _AJUDA[chave] = (-1, str(e))
    v = _AJUDA[chave]
    if v is None or v[0] != 0:
        return None
    return v[1]


def tem_opcao(texto_ajuda: str, opcao: str) -> bool:
    return re.search(rf"(?<![\w-]){re.escape(opcao)}(?![\w-])", texto_ajuda) is not None


def _ultima_linha(texto: str) -> str:
    linhas = [l.strip() for l in texto.strip().splitlines() if l.strip()]
    return linhas[-1][:300] if linhas else ""


def rodar(ex: Execucao, script: str, args: list[str], *, sub: tuple[str, ...] = (), pasta: Path = PASTA,
          json_saida: Path | None = None, cwd: Path | None = None) -> bool:
    """Roda o script; preenche status/código/saída. Devolve True se a ferramenta rodou (0 ou 1)."""
    caminho = pasta / script
    if not caminho.exists():
        ex.motivo = f"{script} não existe nesta pasta"
        return False
    if ajuda(script, *sub, pasta=pasta) is None:
        ex.motivo = f"{script} --help falhou"
        return False
    ex.comando = [sys.executable, str(caminho), *sub, *args]
    try:
        r = subprocess.run(ex.comando, capture_output=True, text=True, timeout=TIMEOUT, cwd=cwd)
    except subprocess.TimeoutExpired:
        ex.motivo = f"tempo esgotado ({TIMEOUT} s)"
        return False
    except OSError as e:
        ex.motivo = f"falha ao executar: {e}"
        return False
    ex.codigo, ex.stdout = r.returncode, r.stdout
    if "Traceback (most recent call last)" in r.stderr:
        ex.motivo = f"erro interno (código {r.returncode}): {_ultima_linha(r.stderr)}"
        return False
    if r.returncode == 2:
        ex.motivo = f"erro de uso (código 2): {_ultima_linha(r.stderr) or _ultima_linha(r.stdout)}"
        return False
    if r.returncode not in (0, 1):
        ex.motivo = f"código {r.returncode}: {_ultima_linha(r.stderr)}"
        return False
    ex.status = "ok" if r.returncode == 0 else "achados"
    if json_saida is not None and json_saida.exists():
        try:
            ex.dados = json.loads(json_saida.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            ex.dados = None
    return True


# --------------------------------------------------------------------------- páginas


def contar_paginas(pdf: Path) -> tuple[int | None, str]:
    """Número de páginas do PDF: ``pdfinfo`` se houver; senão o ``/Count`` da árvore de páginas."""
    if shutil.which("pdfinfo"):
        try:
            r = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True, timeout=60)
            m = re.search(r"^Pages:\s+(\d+)", r.stdout, re.MULTILINE)
            if m:
                return int(m.group(1)), "pdfinfo"
        except (OSError, subprocess.TimeoutExpired):
            pass
    n = contar_paginas_bytes(pdf.read_bytes())
    return n, "/Count do PDF"


def contar_paginas_bytes(dados: bytes) -> int | None:
    """``/Count`` do nó ``/Type /Pages`` raiz (o maior); sem ele, conta os objetos ``/Type /Page``."""
    contagens = []
    for m in re.finditer(rb"/Type\s*/Pages(?![A-Za-z])", dados):
        ini = dados.rfind(b"<<", 0, m.start())
        fim = dados.find(b"endobj", m.end())
        trecho = dados[ini if ini >= 0 else m.start(): fim if fim >= 0 else m.end() + 400]
        c = re.search(rb"/Count\s+(\d+)", trecho)
        if c:
            contagens.append(int(c.group(1)))
    if contagens:
        return max(contagens)
    n = len(re.findall(rb"/Type\s*/Page(?![A-Za-z])", dados))
    return n or None


def gerar_pdf(docx: Path, saida: Path) -> tuple[Path | None, str]:
    office = shutil.which("soffice") or shutil.which("libreoffice")
    if not office:
        return None, "soffice não encontrado"
    saida.mkdir(parents=True, exist_ok=True)
    perfil = (saida / "perfil_lo").resolve()
    cmd = [office, f"-env:UserInstallation={perfil.as_uri()}", "--headless", "--convert-to", "pdf",
           "--outdir", str(saida), str(docx)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_PDF)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, f"soffice falhou: {e}"
    pdf = saida / (docx.stem + ".pdf")
    if not pdf.exists():
        return None, f"soffice não gerou o PDF (código {r.returncode}): {_ultima_linha(r.stderr)}"
    return pdf, "soffice --headless --convert-to pdf"


# --------------------------------------------------------------------------- leitura dos resultados


def _localizador(md: Path | None):
    """Função ``numero -> descrição curta`` (título da seção, número escrito e início do parágrafo)."""
    if md is None or not md.exists():
        return lambda n: ""
    try:
        sys.path.insert(0, str(PASTA))
        import parecer_md as pm  # leitura apenas; não é um dos scripts chamados por subprocesso

        doc = pm.ler(md)
    except Exception:  # noqa: BLE001 — enriquecimento opcional
        return lambda n: ""
    finally:
        if sys.path and sys.path[0] == str(PASTA):
            sys.path.pop(0)
    info: dict[int, str] = {}
    titulo = ""
    for b in doc.blocos:
        if b.tipo == "titulo":
            titulo = re.sub(r"[*_#]", "", b.texto).strip()
        elif b.tipo == "par" and b.numero is not None:
            texto = re.sub(r"\*\*", "", b.texto).strip()
            palavras = texto.split()
            inicio = " ".join(palavras[:10]) + ("…" if len(palavras) > 10 else "")
            partes = []
            if titulo:
                partes.append(titulo[:70] + ("…" if len(titulo) > 70 else ""))
            partes.append(f"«{inicio}»")
            info[b.numero] = "; ".join(partes)
    return lambda n: info.get(n, "") if n is not None else ""


def ler_pre_auditoria(ex: Execucao, localizar) -> None:
    dados = ex.dados if isinstance(ex.dados, dict) else {}
    for a in dados.get("achados", []):
        onde = f" § {a['paragrafo']}" if a.get("paragrafo") else ""
        local = localizar(a.get("paragrafo"))
        txt = f"[{a.get('regra')}]{onde}{f' ({local})' if local else ''}: {a.get('mensagem')}"
        if a.get("severidade") == "bloqueante":
            ex.bloqueantes.append(txt)
        elif a.get("severidade") == "alerta":
            ex.alertas.append(txt)
    if not dados:
        m = re.search(r"\((\d+) bloqueantes, (\d+) alertas", ex.stdout)
        if m:
            ex.bloqueantes += [f"(ver relatório: {m.group(1)} bloqueante(s))"] if int(m.group(1)) else []
    ex.resumo = _ultima_linha(ex.stdout)


def ler_generico(ex: Execucao) -> None:
    """Achados de ferramenta sem formato fixo conhecido (``checar_decisoes.py``)."""
    dados = ex.dados
    itens: list = []
    if isinstance(dados, list):
        itens = dados
    elif isinstance(dados, dict):
        for chave in ("acertos", "acusacoes", "acusadas", "conflitos", "violacoes", "achados", "decisoes_acusadas"):
            if isinstance(dados.get(chave), list):
                itens = dados[chave]
                break
    for it in itens:
        if isinstance(it, dict):
            ident = it.get("id") or it.get("decisao_id") or ""
            local = it.get("local") or it.get("arquivo") or ""
            if it.get("linha") is not None:
                local = f"{local}:{it['linha']}" if local else f"linha {it['linha']}"
            trecho = it.get("trecho") or it.get("mensagem") or it.get("texto") or ""
            dec = it.get("decisao") or it.get("tema") or ""
            txt = " ".join(x for x in (f"[{ident}]" if ident else "", local, f"«{trecho}»" if trecho else "",
                                       f"— decisão: {dec}" if dec else "") if x)
            (ex.bloqueantes if it.get("severidade") == "bloqueante" else ex.alertas).append(txt or json.dumps(it, ensure_ascii=False)[:200])
        else:
            ex.alertas.append(str(it)[:200])
    if not itens and ex.codigo == 1:
        ex.alertas.append(f"acusou conflito (ver saída): {_ultima_linha(ex.stdout)}")
    ex.resumo = _ultima_linha(ex.stdout)


# --------------------------------------------------------------------------- orquestração


def conferir(args: argparse.Namespace, pasta: Path = PASTA) -> dict:
    anterior, nova, redline = args.anterior, args.nova, args.redline
    perfil = args.perfil
    limite_pag = args.max_paginas if args.max_paginas is not None else LIMITE_PAGINAS_PERFIL.get(perfil or "")
    execs: list[Execucao] = []
    tmp = Path(tempfile.mkdtemp(prefix="conferir_versao_"))
    try:
        # 1. Markdown das duas versões
        conv = Execucao("docx_para_md.py")
        md: dict[str, Path | None] = {"anterior": None, "nova": None}
        metricas: dict[str, dict] = {}
        motivos = []
        for rot, path in (("anterior", anterior), ("nova", nova)):
            alvo = tmp / f"{rot}_{path.stem}.md"
            e = Execucao("docx_para_md.py")
            if rodar(e, "docx_para_md.py", [str(path), str(alvo)], pasta=pasta) and alvo.exists():
                md[rot] = alvo
                m = re.search(r"(\d+) blocos, (\d+) parágrafos numerados", e.stdout)
                metricas[rot] = {"numerados": int(m.group(2)) if m else None,
                                 "palavras": len(re.sub(r"[*#_]", " ", alvo.read_text(encoding="utf-8")).split())}
            else:
                motivos.append(f"{rot}: {e.motivo or 'Markdown não gerado'}")
            conv.comando = e.comando
        if md["anterior"] and md["nova"]:
            conv.status = "ok"
            conv.resumo = "; ".join(f"{r}: {metricas[r]['numerados']} parágrafos numerados" for r in metricas)
        else:
            conv.motivo = "; ".join(motivos)
        execs.append(conv)

        # 2. PDF e páginas
        paginas = {"conferidas": False, "n": None, "limite": limite_pag, "metodo": "", "motivo": "", "acima": False}
        pdf = None
        if args.sem_pdf:
            paginas["motivo"] = "não conferidas (--sem-pdf)"
        else:
            pdf, como = gerar_pdf(nova, tmp / "pdf")
            if pdf is None:
                paginas["motivo"] = f"não conferidas: {como}"
            else:
                n, metodo = contar_paginas(pdf)
                if n is None:
                    paginas["motivo"] = "não conferidas: contagem de páginas falhou"
                else:
                    paginas.update(conferidas=True, n=n, metodo=metodo,
                                   acima=bool(limite_pag and n > limite_pag))

        # 3. pré-auditoria
        pre = Execucao("pre_auditoria_parecer.py")
        if md["nova"] is None or md["anterior"] is None:
            pre.motivo = "sem Markdown da nova ou da anterior (docx_para_md.py não executado)"
        else:
            h = ajuda("pre_auditoria_parecer.py", pasta=pasta) or ""
            jpre = tmp / "pre_auditoria.json"
            a = [str(md["nova"]), "--anterior", str(md["anterior"])]
            if perfil:
                a += ["--perfil", perfil]
            if args.max_palavras is not None:
                a += ["--max-palavras", str(args.max_palavras)]
            if args.estilo and tem_opcao(h, "--estilo"):
                a += ["--estilo", args.estilo]
            if args.exige_anexo and tem_opcao(h, "--exige-anexo"):
                a += ["--exige-anexo"]
            if args.mapa_origem:
                a += ["--mapa-origem", str(args.mapa_origem)]
            if args.refutadas:
                a += ["--refutadas", str(args.refutadas)]
            if pdf is not None and limite_pag and tem_opcao(h, "--pdf"):
                a += ["--pdf", str(pdf), "--max-paginas", str(limite_pag)]
            if tem_opcao(h, "--sem-info"):
                a += ["--sem-info"]
            a += ["--json", str(jpre)]
            if rodar(pre, "pre_auditoria_parecer.py", a, pasta=pasta, json_saida=jpre):
                ler_pre_auditoria(pre, _localizador(md["nova"]))
        execs.append(pre)

        # 4. inventário de fatos
        inv = Execucao("inventario_fatos.py")
        jinv = tmp / "inventario.json"
        h = ajuda("inventario_fatos.py", pasta=pasta) or ""
        a = [str(anterior), str(nova), "--md"] + (["--json", str(jinv)] if tem_opcao(h, "--json") else [])
        if rodar(inv, "inventario_fatos.py", a, pasta=pasta, json_saida=jinv):
            d = inv.dados if isinstance(inv.dados, dict) else {}
            acr, sup = d.get("acrescimos", []), d.get("supressoes", [])
            inv.resumo = f"{len(acr)} acréscimo(s), {len(sup)} supressão(ões)"
            inv.alertas = [f"supressão [{s.get('categoria')}] {s.get('literal')}" for s in sup]
        execs.append(inv)

        # 5. remissões
        rem = Execucao("verificar_remissoes.py conferir")
        jrem = tmp / "remissoes.json"
        h = ajuda("verificar_remissoes.py", "conferir", pasta=pasta) or ""
        a = ["--parecer", str(nova)] + (["--json", str(jrem)] if tem_opcao(h, "--json") else [])
        if rodar(rem, "verificar_remissoes.py", a, sub=("conferir",), pasta=pasta, json_saida=jrem):
            d = rem.dados if isinstance(rem.dados, dict) else {}
            for x in d.get("achados", []):
                txt = f"[{x.get('regra')}] {x.get('local')}: {x.get('mensagem')}"
                if x.get("severidade") == "bloqueante":
                    rem.bloqueantes.append(txt)
                elif x.get("severidade") == "alerta":
                    rem.alertas.append(txt)
            rem.resumo = _ultima_linha(rem.stdout)
        execs.append(rem)

        # 6. refutadas
        ref = Execucao("checar_refutadas.py")
        refutadas_acusadas: list[str] = []
        if not args.refutadas:
            ref.status, ref.motivo = "dispensado", "sem --refutadas"
        else:
            jref = tmp / "refutadas.json"
            h = ajuda("checar_refutadas.py", pasta=pasta) or ""
            a = ["--refutadas", str(args.refutadas), str(nova)] + (["--json", str(jref)] if tem_opcao(h, "--json") else [])
            if rodar(ref, "checar_refutadas.py", a, pasta=pasta, json_saida=jref):
                d = ref.dados if isinstance(ref.dados, dict) else {}
                for x in d.get("acertos", []):
                    local = x.get("local") or f"linha {x.get('linha')}"
                    txt = (f"[{x.get('id')}] {local}: «{x.get('trecho')}» — {x.get('por_que', '')}"
                           + (f"; correto: {x['correto']}" if x.get("correto") else "")
                           + (f" ({x['fonte']})" if x.get("fonte") else ""))
                    refutadas_acusadas.append(txt)
                if ref.codigo == 1 and not refutadas_acusadas:
                    refutadas_acusadas.append(f"(ver saída) {_ultima_linha(ref.stdout)}")
                ref.bloqueantes = list(refutadas_acusadas)
                ref.resumo = _ultima_linha(ref.stdout)
        execs.append(ref)

        # 6-A. verificações aritméticas do caso
        ari = Execucao("conferir_aritmetica.py")
        aritmetica: list[str] = []
        if not args.verificacoes:
            ari.status, ari.motivo = "dispensado", "sem --verificacoes"
        elif not (pasta / "conferir_aritmetica.py").exists():
            ari.motivo = "conferir_aritmetica.py não existe nesta pasta"
        else:
            jari = tmp / "aritmetica.json"
            if rodar(ari, "conferir_aritmetica.py", ["--verificacoes", str(args.verificacoes), str(nova), "--json", str(jari)],
                     pasta=pasta, json_saida=jari):
                d = ari.dados if isinstance(ari.dados, dict) else {}
                for it in d.get("itens", []):
                    if it.get("ok"):
                        continue
                    motivo = []
                    if "erro" in it:
                        motivo.append(f"erro: {it['erro']}")
                    elif not it.get("fecha"):
                        motivo.append(f"não fecha ({it.get('esquerda')} × {it.get('direita')})")
                    for f in (it.get("faltando_no_texto") or {}).values():
                        motivo.append("faltam no texto: " + ", ".join(f))
                    for f in (it.get("proibidos_no_texto") or {}).values():
                        motivo.append("proibido no texto: " + ", ".join(f))
                    aritmetica.append(f"[{it.get('id')}] {it.get('descricao', '')}: {'; '.join(motivo)}")
                ari.bloqueantes = list(aritmetica)
                ari.resumo = _ultima_linha(ari.stdout)
        execs.append(ari)

        # 6-B. densidade: volume e ritmo, contra a versão anterior
        den = Execucao("medir_densidade.py")
        densidade: dict = {}
        if not (pasta / "medir_densidade.py").exists():
            den.status, den.motivo = "dispensado", "medir_densidade.py não existe nesta pasta"
        else:
            jden = tmp / "densidade.json"
            a = [str(nova), "--anterior", str(anterior), "--json", str(jden)]
            if getattr(args, "meta_reducao", None) is not None:
                a += ["--meta-reducao", str(args.meta_reducao)]
            if rodar(den, "medir_densidade.py", a, pasta=pasta, json_saida=jden):
                densidade = den.dados if isinstance(den.dados, dict) else {}
                if densidade.get("aviso"):
                    (den.alertas if densidade.get("ok", True) else den.bloqueantes).append(densidade["aviso"])
                den.resumo = _ultima_linha(den.stdout)
        execs.append(den)

        # 6-C. pontas soltas: julgado sem referência, referência sem citação, verbete órfão, colchetes editoriais
        orf = Execucao("conferir_orfaos.py")
        if not (pasta / "conferir_orfaos.py").exists():
            orf.status, orf.motivo = "dispensado", "conferir_orfaos.py não existe nesta pasta"
        else:
            jorf = tmp / "orfaos.json"
            if rodar(orf, "conferir_orfaos.py", [str(nova), "--json", str(jorf)], pasta=pasta, json_saida=jorf):
                d = orf.dados if isinstance(orf.dados, dict) else {}
                for it in d.get("achados", []):
                    linha = f"[{it.get('tipo')}] {it.get('mensagem', '')}" + (f" — «{it['trecho']}»" if it.get("trecho") else "")
                    if it.get("gravidade") == "bloqueante":
                        orf.bloqueantes.append(linha)
                    elif it.get("gravidade") == "alerta":
                        orf.alertas.append(linha)
                orf.resumo = _ultima_linha(orf.stdout)
        execs.append(orf)

        # 7. decisões
        dec = Execucao("checar_decisoes.py")
        if not args.decisoes:
            dec.status, dec.motivo = "dispensado", "sem --decisoes"
        elif not (pasta / "checar_decisoes.py").exists():
            dec.motivo = "checar_decisoes.py não existe nesta pasta"
        else:
            h = ajuda("checar_decisoes.py", pasta=pasta)
            if h is None:
                dec.motivo = "checar_decisoes.py --help falhou"
            else:
                jdec = tmp / "decisoes.json"
                a = ["--decisoes", str(args.decisoes)] if tem_opcao(h, "--decisoes") else [str(args.decisoes)]
                opc_texto = next((o for o in ("--minuta", "--parecer", "--texto", "--textos", "--documento")
                                  if tem_opcao(h, o)), None)
                a += [opc_texto, str(nova)] if opc_texto else [str(nova)]
                if tem_opcao(h, "--json"):
                    a += ["--json", str(jdec)]
                if rodar(dec, "checar_decisoes.py", a, pasta=pasta, json_saida=jdec):
                    ler_generico(dec)
        execs.append(dec)

        # 8. integridade
        integ = Execucao("integridade_docx.py")
        integridade = {"conferida": False, "ok": None, "falhas": []}
        if not redline:
            integ.status, integ.motivo = "dispensado", "sem --redline"
        else:
            jint = tmp / "integridade.json"
            h = ajuda("integridade_docx.py", pasta=pasta) or ""
            a = ["--base", str(anterior), "--limpa", str(nova), "--redline", str(redline)]
            if args.divididos is not None:
                a += ["--divididos", str(args.divididos)]
            if args.fundidos is not None:
                a += ["--fundidos", str(args.fundidos)]
            if tem_opcao(h, "--json"):
                a += ["--json", str(jint)]
            if rodar(integ, "integridade_docx.py", a, pasta=pasta, json_saida=jint):
                d = integ.dados if isinstance(integ.dados, dict) else {}
                ok = d.get("ok", integ.codigo == 0)
                integridade.update(conferida=True, ok=bool(ok))
                for v in d.get("verificacoes", []):
                    if not v.get("ok"):
                        div = v.get("divergencia") or {}
                        extra = f" — {div.get('resumo')}" if isinstance(div, dict) and div.get("resumo") else ""
                        integridade["falhas"].append(f"{v.get('descricao') or v.get('nome')}{extra}")
                if not ok and not integridade["falhas"]:
                    integridade["falhas"].append(_ultima_linha(integ.stdout) or "divergência")
                integ.bloqueantes = list(integridade["falhas"])
                integ.resumo = _ultima_linha(integ.stdout.splitlines()[0] if integ.stdout else "")
        execs.append(integ)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # consolidação
    bloqueantes = [f"{e.ferramenta}: {b}" for e in execs for b in e.bloqueantes]
    if paginas["acima"] and not any(b.startswith("[paginas]") for b in pre.bloqueantes):
        bloqueantes.append(f"páginas: {paginas['n']} (limite {limite_pag})")
    nao_exec = [e for e in execs if e.status == "não executado"]
    reprova = (bool(bloqueantes) or bool(refutadas_acusadas) or bool(aritmetica)
               or integridade["ok"] is False or paginas["acima"])
    resultado = "reprovada" if reprova else ("incompleta" if nao_exec else "aprovada")
    return {
        "versao": args.versao or nova.stem,
        "data": args.data or _dt.date.today().isoformat(),
        "modo": args.modo,
        "resumo": args.resumo or "",
        "perfil": perfil,
        "arquivos": {"anterior": str(anterior), "nova": str(nova), "redline": str(redline) if redline else None},
        "sha256": {"anterior": sha256(anterior), "nova": sha256(nova), "redline": sha256(redline)},
        "paginas": paginas,
        "metricas": metricas,
        "ferramentas": [{k: v for k, v in asdict(e).items() if k not in ("stdout", "dados")} for e in execs],
        "inventario_md": inv.stdout if inv.executado else "",
        "refutadas": refutadas_acusadas,
        "aritmetica": aritmetica,
        "densidade": densidade,
        "orfaos": orf.bloqueantes + orf.alertas,
        "estilo": args.estilo,
        "decisoes": dec.bloqueantes + dec.alertas if dec.executado else [],
        "integridade": integridade,
        "bloqueantes": bloqueantes,
        "nao_executados": [f"{e.ferramenta}: {e.motivo}" for e in nao_exec],
        "resultado": resultado,
        "codigo_saida": 1 if reprova else 0,
    }


# --------------------------------------------------------------------------- saída


def _celula(t: str) -> str:
    return t.replace("|", "\\|").replace("\n", " ")


def montar_nota(r: dict) -> str:
    profundo = r.get("modo") == "profundo"
    arq = r["arquivos"]
    L = ["## Conferências automáticas", ""]
    L.append(f"Gerada por `conferir_versao.py` em {r['data']} — versão **{r['versao']}**"
             f" (modo {r['modo']}; perfil {r.get('perfil') or 'genérico'}): "
             f"`{Path(arq['anterior']).name}` → `{Path(arq['nova']).name}`.")
    L.append("")
    nb = len(r["bloqueantes"])
    L.append(f"**Resultado:** {r['resultado'].upper()} — {nb} bloqueante(s)"
             + (f"; {len(r['nao_executados'])} ferramenta(s) não executada(s)" if r["nao_executados"] else "") + ".")
    L.append("")
    L += ["**Hashes (SHA-256)**", "", "| Arquivo | SHA-256 |", "|---|---|"]
    L.append(f"| anterior (base) `{Path(arq['anterior']).name}` | `{r['sha256']['anterior']}` |")
    L.append(f"| nova (limpa) `{Path(arq['nova']).name}` | `{r['sha256']['nova']}` |")
    if arq.get("redline"):
        L.append(f"| comparativo `{Path(arq['redline']).name}` | `{r['sha256']['redline']}` |")
    else:
        L.append("| comparativo | — (sem --redline) |")
    L.append("")
    p = r["paginas"]
    if p["conferidas"]:
        lim = f" (limite: {p['limite']})" if p["limite"] else " (sem limite definido)"
        alerta = (f" — **ACIMA DO LIMITE ({p['n']} > {p['limite']})**: enxugar ou registrar a ampliação em "
                  "`decisoes.json`" if p["acima"] else "")
        L.append(f"**Páginas:** {p['n']}{lim}, medidas no PDF da nova ({p['metodo']}){alerta}.")
    else:
        L.append(f"**Páginas:** {p['motivo']}" + (f" (limite: {p['limite']})" if p["limite"] else "") + ".")
    m = r.get("metricas") or {}
    if "anterior" in m and "nova" in m:
        pa, pn = m["anterior"]["palavras"], m["nova"]["palavras"]
        var = f" ({(pn - pa) / pa * 100:+.1f} %)" if pa else ""
        L.append(f"**Métricas:** palavras {pa} → {pn}{var}; parágrafos numerados "
                 f"{m['anterior']['numerados']} → {m['nova']['numerados']}.")
    L += ["", "**Ferramentas**", ""]
    for f in r["ferramentas"]:
        nome = f"`{f['ferramenta']}`"
        if f["status"] in ("ok", "achados"):
            rot = "ok" if not f["bloqueantes"] else "BLOQUEANTE"
            extra = f" — {f['resumo']}" if f["resumo"] else ""
            L.append(f"- {nome}: {rot}; {len(f['bloqueantes'])} bloqueante(s), {len(f['alertas'])} alerta(s){extra}")
            for b in f["bloqueantes"]:
                L.append(f"  - **bloqueante** {b}")
            if profundo:
                for a in f["alertas"]:
                    L.append(f"  - alerta {a}")
        elif f["status"] == "dispensado":
            L.append(f"- {nome}: dispensado ({f['motivo']})")
        else:
            L.append(f"- {nome}: **não executado** — {f['motivo']}")
    L += ["", "**Inventário de fatos**", ""]
    inv = r.get("inventario_md", "").strip()
    if inv:
        linhas = inv.splitlines()
        if linhas and linhas[0].startswith("## "):
            linhas = linhas[1:]
        while linhas and not linhas[0].strip():
            linhas = linhas[1:]
        L += [re.sub(r"^### ", "#### ", l) for l in linhas]
    else:
        L.append("não executado.")
    L += ["", "**Refutadas**", ""]
    ferr = {f["ferramenta"]: f for f in r["ferramentas"]}
    fr = ferr.get("checar_refutadas.py", {})
    if fr.get("status") == "dispensado":
        L.append("não conferidas (sem `--refutadas`).")
    elif fr.get("status") not in ("ok", "achados"):
        L.append(f"não executado — {fr.get('motivo', '')}.")
    elif r["refutadas"]:
        L += [f"- {x}" for x in r["refutadas"]]
    else:
        L.append("nenhuma afirmação refutada reaparece.")
    L += ["", "**Verificações aritméticas do caso**", ""]
    fa = ferr.get("conferir_aritmetica.py", {})
    if fa.get("status") == "dispensado":
        L.append("não conferidas (sem `--verificacoes`).")
    elif fa.get("status") not in ("ok", "achados"):
        L.append(f"não executado — {fa.get('motivo', '')}.")
    elif r.get("aritmetica"):
        L += [f"- {x}" for x in r["aritmetica"]]
    else:
        L.append("todas as contas registradas fecham e os números exigidos estão no texto.")
    dn = r.get("densidade") or {}
    if dn.get("nova"):
        L += ["", "**Densidade (corpo do texto)**", ""]
        ant_, nov_ = dn.get("anterior") or {}, dn["nova"]
        L.append(f"- palavras: {ant_.get('palavras', '—')} → {nov_.get('palavras')}"
                 + (f" (redução de {dn['reducao_palavras_pct']}%)" if dn.get("reducao_palavras_pct") is not None else ""))
        L.append(f"- parágrafos: {ant_.get('paragrafos', '—')} → {nov_.get('paragrafos')}; "
                 f"média de palavras por frase: {ant_.get('media_frase', '—')} → {nov_.get('media_frase')}; "
                 f"frases acima de 60 palavras: {ant_.get('frases_acima_60', '—')} → {nov_.get('frases_acima_60')}")
        if dn.get("aviso"):
            L.append(f"- {'**meta não atingida:** ' if not dn.get('ok', True) else ''}{dn['aviso']}")
    fo = ferr.get("conferir_orfaos.py", {})
    if fo.get("status") in ("ok", "achados"):
        L += ["", "**Pontas soltas**", ""]
        L += [f"- {x}" for x in r.get("orfaos", [])] or ["nenhuma: julgados e referências batem, sem verbete órfão nem instrução editorial no texto."]
    L += ["", "**Decisões**", ""]
    fd = ferr.get("checar_decisoes.py", {})
    if fd.get("status") == "dispensado":
        L.append("não conferidas (sem `--decisoes`).")
    elif fd.get("status") not in ("ok", "achados"):
        L.append(f"não executado — {fd.get('motivo', '')}.")
    elif r["decisoes"]:
        L += [f"- {x} — decisão já tomada: reabrir?" for x in r["decisoes"]]
    else:
        L.append("nenhuma decisão contrariada.")
    L += ["", "**Integridade do comparativo**", ""]
    i = r["integridade"]
    fi = ferr.get("integridade_docx.py", {})
    if fi.get("status") == "dispensado":
        L.append("não conferida (sem `--redline`).")
    elif not i["conferida"]:
        L.append(f"não executado — {fi.get('motivo', '')}.")
    elif i["ok"]:
        L.append(f"ok — {fi.get('resumo') or 'aceitar reproduz a limpa e rejeitar reproduz a base'}.")
    else:
        L.append("**FALHA**:")
        L += [f"- {x}" for x in i["falhas"]]
    if r["nao_executados"]:
        L += ["", "**Não executado:** " + "; ".join(r["nao_executados"]) + "."]
    return "\n".join(L).rstrip() + "\n"


def resumo_curto(r: dict) -> str:
    p = r["paginas"]
    pag = (f"{p['n']} páginas" + (f" (limite {p['limite']}{', ACIMA' if p['acima'] else ''})" if p["limite"] else "")
           if p["conferidas"] else p["motivo"])
    L = [f"conferir_versao: {r['versao']} — {r['resultado'].upper()} ({len(r['bloqueantes'])} bloqueante(s)); {pag}"]
    for f in r["ferramentas"]:
        if f["status"] in ("ok", "achados"):
            L.append(f"  {f['ferramenta']}: {len(f['bloqueantes'])} bloqueante(s), {len(f['alertas'])} alerta(s)")
        else:
            L.append(f"  {f['ferramenta']}: {f['status']} ({f['motivo']})")
    for b in r["bloqueantes"]:
        L.append(f"  - {b[:220]}")
    return "\n".join(L)


def atualizar_registro(path: Path, r: dict, caso: str | None) -> dict:
    if path.exists():
        reg = json.loads(path.read_text(encoding="utf-8"))
    else:
        reg = {"caso": "", "versoes": []}
    if caso:
        reg["caso"] = caso
    entrada = {
        "versao": r["versao"],
        "base_sha256": r["sha256"]["anterior"],
        "limpa_sha256": r["sha256"]["nova"],
        "redline_sha256": r["sha256"]["redline"],
        "data": r["data"],
        "modo": r["modo"],
        "resumo": r["resumo"],
        "resultado": r["resultado"],
        "bloqueantes": r["bloqueantes"],
    }
    versoes = reg.setdefault("versoes", [])
    for k, v in enumerate(versoes):
        if isinstance(v, dict) and v.get("versao") == entrada["versao"]:
            versoes[k] = entrada
            break
    else:
        versoes.append(entrada)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)
    return reg


def _caso_de(*paths: Path | None) -> str:
    for p in paths:
        if p is None:
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(d, dict) and d.get("caso"):
            return str(d["caso"])
    return ""


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--anterior", type=Path, required=True, help="última versão aprovada (.docx), base do comparativo")
    ap.add_argument("--nova", type=Path, required=True, help="versão nova, limpa (.docx)")
    ap.add_argument("--redline", type=Path, help="comparativo anterior → nova com alterações controladas (.docx)")
    ap.add_argument("--mapa-origem", type=Path, help="mapa de origem para a pré-auditoria")
    ap.add_argument("--refutadas", type=Path, help="registro de afirmações refutadas do caso")
    ap.add_argument("--decisoes", type=Path, help="registro de decisões do caso")
    ap.add_argument("--verificacoes", type=Path, help="registro de verificações aritméticas do caso (conferir_aritmetica.py)")
    ap.add_argument("--meta-reducao", type=float,
                    help="redução mínima de palavras do corpo, em %% (quando o pedido é condensar); abaixo disso, reprova")
    ap.add_argument("--estilo", choices=("executivo", "classico"), help="estilo de redação, repassado à pré-auditoria")
    ap.add_argument("--exige-anexo", action="store_true",
                    help="a consulta pede minuta ou peça anexa: bloqueia a versão sem seção de Anexo")
    ap.add_argument("--perfil", help="perfil da pré-auditoria (ex.: genes)")
    ap.add_argument("--max-palavras", type=int, help="teto de palavras por parágrafo (sobrepõe o perfil)")
    ap.add_argument("--max-paginas", type=int, help="limite de páginas (sobrepõe o do perfil; genes: 15)")
    ap.add_argument("--divididos", type=int, help="parágrafos acrescidos por divisão (integridade)")
    ap.add_argument("--fundidos", type=int, help="parágrafos absorvidos por fusão (integridade)")
    ap.add_argument("--versao", help="rótulo da versão (padrão: nome do arquivo novo)")
    ap.add_argument("--modo", choices=("conciso", "profundo"), default="conciso")
    ap.add_argument("--resumo", help="resumo da versão para o registro")
    ap.add_argument("--data", help="data ISO (padrão: hoje)")
    ap.add_argument("--caso", help="nome do caso no registro (padrão: o das refutadas ou decisões)")
    ap.add_argument("--registro", type=Path, help="registro de versões (JSON) a criar ou atualizar")
    ap.add_argument("--nota-saida", type=Path, help="grava a seção «Conferências automáticas» (Markdown)")
    ap.add_argument("--json", type=Path, help="grava o resultado completo em JSON")
    ap.add_argument("--sem-pdf", action="store_true", help="não gera o PDF nem conta páginas")
    return ap


def main(argv: list[str] | None = None, pasta: Path = PASTA) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    for nome in ("anterior", "nova", "redline", "mapa_origem", "refutadas", "decisoes", "verificacoes"):
        p = getattr(args, nome)
        if p is not None and not p.is_file():
            print(f"arquivo não encontrado (--{nome.replace('_', '-')}): {p}", file=sys.stderr)
            return 2
    for nome in ("max_palavras", "max_paginas"):
        v = getattr(args, nome)
        if v is not None and v <= 0:
            print(f"--{nome.replace('_', '-')} deve ser positivo", file=sys.stderr)
            return 2
    for nome in ("divididos", "fundidos"):
        v = getattr(args, nome)
        if v is not None and v < 0:
            print(f"--{nome} não pode ser negativo", file=sys.stderr)
            return 2
    if args.data:
        try:
            _dt.date.fromisoformat(args.data[:10])
        except ValueError:
            print(f"--data não é ISO (AAAA-MM-DD): {args.data}", file=sys.stderr)
            return 2
    if args.registro and args.registro.exists():
        try:
            reg = json.loads(args.registro.read_text(encoding="utf-8"))
            if not isinstance(reg, dict) or not isinstance(reg.get("versoes", []), list):
                raise ValueError('esperado {"caso": ..., "versoes": [...]}')
        except (OSError, ValueError) as e:
            print(f"registro inválido ({args.registro}): {e}", file=sys.stderr)
            return 2
    args.anterior, args.nova = args.anterior.resolve(), args.nova.resolve()
    args.redline = args.redline.resolve() if args.redline else None

    r = conferir(args, pasta)
    nota = montar_nota(r)
    if args.nota_saida:
        args.nota_saida.write_text(nota, encoding="utf-8")
    else:
        print(nota)
    if args.registro:
        caso = args.caso
        if not caso:
            atual = json.loads(args.registro.read_text(encoding="utf-8")) if args.registro.exists() else {}
            if not atual.get("caso"):
                caso = _caso_de(args.refutadas, args.decisoes)
        atualizar_registro(args.registro, r, caso)
    if args.json:
        args.json.write_text(json.dumps({**r, "nota_md": nota}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(resumo_curto(r))
    if args.nota_saida:
        print(f"  nota: {args.nota_saida}")
    if args.registro:
        print(f"  registro: {args.registro}")
    return r["codigo_saida"]


if __name__ == "__main__":
    sys.exit(main())
