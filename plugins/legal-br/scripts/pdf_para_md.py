#!/usr/bin/env python3
"""
pdf_para_md.py — wrapper do `pdf2md` (engine pdf-inspector) para o plugin legal-br.

Pipeline PADRÃO: OCR (ocrmypdf) -> pdf2md -> grava SEMPRE uma cópia .md citável.
Garante texto utilizável mesmo em PDFs escaneados OU com camada de texto ruim/garbled
(caso típico de matrículas e contratos antigos digitalizados no SEI) — nunca aborta.

Estratégia de OCR (modo `auto`, default):
  - scanned / image_based / mixed -> `--force-ocr`  (não há texto nativo a preservar)
  - text_based / desconhecido     -> `--redo-ocr`  (refaz camadas de OCR ruins/garbled
    e preserva o texto nativo; cobre o caso "escaneado COM camada-lixo" que o pdf2md
    classifica como text_based). Fallback automático para `--force-ocr` se o redo falhar.

Uso:
  python3 pdf_para_md.py check
  python3 pdf_para_md.py convert <arquivo.pdf> [--out saida.md] [--pages]
                                  [--select-pages 1,3,5-10] [--stdout]
                                  [--ocr auto|force|never] [--ocr-lang por+eng]
                                  [--keep-ocr-pdf]

Modos de OCR (--ocr):
  auto   -> escolhe a estratégia pelo tipo (acima). É o padrão e SEMPRE aplica OCR.
  force  -> força `--force-ocr` em todo o PDF (rasteriza tudo; mais lento).
  never  -> não aplica OCR (apenas pdf2md).

Saída:
  - `check`: JSON com disponibilidade de pdf2md e ocrmypdf.
  - `convert`: grava <pdf>.md SEMPRE e imprime JSON de status; --stdout também
    ecoa o markdown no stdout (a cópia .md continua sendo gravada).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# Tipos (campo Type: do pdf2md) sem camada de texto nativa utilizável.
OCR_TYPES = {"scanned", "image_based", "mixed"}
DEFAULT_LANG = "por+eng"


# Caminhos comuns (Homebrew/instalações manuais) usados como fallback quando o
# PATH do agente sobe mínimo — caso típico do Claude Desktop/Cowork em modo
# agente local, que pode não herdar /opt/homebrew/bin.
EXTRA_PATHS = ["/opt/homebrew/bin", "/usr/local/bin", str(Path.home() / ".local/bin")]


def _which(name):
    """shutil.which + fallback nos EXTRA_PATHS. Retorna caminho absoluto ou ''."""
    p = shutil.which(name)
    if p:
        return p
    for d in EXTRA_PATHS:
        cand = os.path.join(d, name)
        if os.path.exists(cand) and os.access(cand, os.X_OK):
            return cand
    return ""


def _aug_env():
    """Env para os subprocessos de OCR: garante PATH (com EXTRA_PATHS) para achar
    tesseract/ghostscript e defaults sãos (HOME/TMPDIR/locale) caso o agente suba
    com ambiente mínimo (ex.: Claude Desktop/Cowork)."""
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join(EXTRA_PATHS) + os.pathsep + env.get("PATH", "")
    env.setdefault("HOME", str(Path.home()))
    env.setdefault("TMPDIR", "/tmp")
    env.setdefault("LANG", "en_US.UTF-8")
    env.setdefault("LC_ALL", "en_US.UTF-8")
    return env


def pdf2md_bin():
    return _which("pdf2md") or str(Path.home() / ".local/bin/pdf2md")


def ocrmypdf_bin():
    return _which("ocrmypdf")


def _run(args, **kw):
    return subprocess.run(args, capture_output=True, text=True, **kw)


def detectar(binp, pdf):
    """Retorna (tipo, page_count) via --detect-only (Type:/Pages: vão p/ stderr)."""
    p = _run([binp, pdf, "--detect-only"])
    out = (p.stderr or "") + (p.stdout or "")
    tipo, pages = "desconhecido", None
    for line in out.splitlines():
        s = line.strip()
        if s.lower().startswith("type:"):
            tipo = s.split(":", 1)[1].strip()
        elif s.lower().startswith("pages:"):
            try:
                pages = int(s.split(":", 1)[1].strip())
            except ValueError:
                pass
    return tipo, pages


def _ocrmypdf(obin, flag, lang, src, dst):
    # env aumentado: garante que o ocrmypdf ache tesseract/ghostscript no Desktop.
    return _run([obin, "-l", lang, flag, "--output-type", "pdf", "--quiet", src, dst],
                env=_aug_env())


def aplicar_ocr(src, tipo, modo, lang, keep):
    """Aplica OCR (ocrmypdf) garantindo texto em páginas escaneadas/garbled.

    Devolve (pdf_para_converter, info). info: ocr (bool), estrategia, ocr_pdf
    (se --keep-ocr-pdf) e eventual aviso. Nunca aborta: tenta as estratégias da
    "escada" e, se todas falharem, devolve o PDF original com aviso.
    """
    info = {"ocr": False, "estrategia": None}
    obin = ocrmypdf_bin()
    if modo == "never":
        return src, info
    if not obin:
        info["aviso"] = "ocrmypdf indisponível — seguindo sem OCR."
        return src, info

    # Escada de estratégias (a primeira que retornar rc=0 vence).
    if modo == "force":
        estrategias = ["--force-ocr"]
    elif tipo in OCR_TYPES:                 # scanned/image_based/mixed: sem texto nativo
        estrategias = ["--force-ocr"]
    else:                                    # text_based/desconhecido: refaz camada ruim
        estrategias = ["--redo-ocr", "--force-ocr"]

    if keep:
        dst = str(Path(src).with_suffix(".ocr.pdf"))
    else:
        fd, dst = tempfile.mkstemp(suffix=".ocr.pdf")
        os.close(fd)

    last_err = ""
    for flag in estrategias:
        p = _ocrmypdf(obin, flag, lang, src, dst)
        if p.returncode == 0:
            info["ocr"] = True
            info["estrategia"] = flag
            if keep:
                info["ocr_pdf"] = dst
            return dst, info
        last_err = (p.stderr or "").strip()[:200]

    if not keep and os.path.exists(dst):
        try:
            os.remove(dst)
        except OSError:
            pass
    info["aviso"] = f"OCR falhou ({last_err}) — convertendo o PDF original."
    return src, info


def cmd_check(_args):
    binp = pdf2md_bin()
    obin = ocrmypdf_bin()
    tess = _which("tesseract")
    gs = _which("gs")
    env = _aug_env()
    ocr_ver = None
    if obin:
        pv = _run([obin, "--version"], env=env)
        raw = (pv.stdout or pv.stderr or "").strip()
        ocr_ver = raw.splitlines()[0] if raw else None
    langs = None
    if tess:
        lv = _run([tess, "--list-langs"], env=env)
        out = (lv.stdout or lv.stderr or "")
        langs = [s.strip() for s in out.splitlines() if s.strip() in ("por", "eng")]
    print(json.dumps({
        "pdf2md": binp,
        "disponivel": os.path.exists(binp),
        "engine": "pdf-inspector",
        "ocrmypdf": obin or None,
        "ocr_disponivel": bool(obin),
        "ocr_versao": ocr_ver,
        "tesseract": tess or None,
        "tesseract_langs": langs,
        "ghostscript": gs or None,
        "ocr_pronto": bool(obin and tess and gs),
        "ocr_lang_default": DEFAULT_LANG,
        "extra_paths": EXTRA_PATHS,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_convert(args):
    binp = pdf2md_bin()
    pdf = os.path.expanduser(args.pdf)
    if not os.path.exists(binp):
        print(json.dumps({"ok": False, "erro": f"pdf2md não encontrado em {binp}"}, ensure_ascii=False))
        return 2
    if not os.path.exists(pdf):
        print(json.dumps({"ok": False, "erro": f"PDF não encontrado: {pdf}"}, ensure_ascii=False))
        return 2

    tipo, pages = detectar(binp, pdf)

    # OCR (default auto): garante texto em páginas escaneadas/garbled; nunca aborta.
    src_md, ocr_info = aplicar_ocr(pdf, tipo, args.ocr, args.ocr_lang, args.keep_ocr_pdf)

    cmd = [binp, src_md, "--raw"]
    if args.pages:
        cmd.append("--pages")
    if args.select_pages:
        cmd.extend(["--select-pages", args.select_pages])
    proc = _run(cmd)

    # Limpa o PDF temporário de OCR (quando não foi pedido --keep-ocr-pdf).
    if ocr_info.get("ocr") and not args.keep_ocr_pdf and src_md != pdf:
        try:
            os.remove(src_md)
        except OSError:
            pass

    if proc.returncode != 0:
        print(json.dumps({"ok": False, "pdf": pdf, "type": tipo,
                          "ocr": ocr_info,
                          "erro": (proc.stderr or "")[:400]}, ensure_ascii=False))
        return 1
    md = proc.stdout or ""

    # SEMPRE grava a cópia .md citável (mesmo com --stdout).
    out = Path(os.path.expanduser(args.out)) if args.out else Path(pdf).with_suffix(".md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")

    if args.stdout:
        sys.stdout.write(md)
        return 0

    status = {
        "ok": True, "pdf": pdf, "type": tipo, "page_count": pages,
        "out": str(out), "bytes": len(md.encode("utf-8")),
        "ocr": ocr_info,
    }
    print(json.dumps(status, ensure_ascii=False, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description="PDF->Markdown via pdf2md/pdf-inspector com OCR (legal-br)")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check", help="pdf2md/ocrmypdf disponíveis?").set_defaults(func=cmd_check)
    pc = sub.add_parser("convert", help="Converte um PDF para Markdown (com OCR)")
    pc.add_argument("pdf")
    pc.add_argument("--out", help="arquivo .md de saída (default: <pdf>.md)")
    pc.add_argument("--pages", action="store_true", help="inserir marcadores <!-- Page N -->")
    pc.add_argument("--select-pages", help="apenas estas páginas (ex.: 1,3,5-10)")
    pc.add_argument("--stdout", action="store_true", help="ecoar o MD no stdout (a cópia .md é gravada do mesmo jeito)")
    pc.add_argument("--ocr", choices=["auto", "force", "never"], default="auto",
                    help="modo de OCR (default: auto — força em scanned/mixed, redo em text_based)")
    pc.add_argument("--ocr-lang", default=DEFAULT_LANG, help=f"idiomas do OCR (default: {DEFAULT_LANG})")
    pc.add_argument("--keep-ocr-pdf", action="store_true", help="manter o PDF pós-OCR em <pdf>.ocr.pdf")
    pc.set_defaults(func=cmd_convert)
    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
