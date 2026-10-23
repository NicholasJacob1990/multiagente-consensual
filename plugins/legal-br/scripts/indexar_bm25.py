#!/usr/bin/env python3
"""
indexar_bm25.py — constrói o índice léxico FTS5 (BM25) do acervo PGE-RJ a partir
dos MESMOS chunks já embutidos no ChromaDB (mesmos ids → permite RRF).

Complemento léxico do indexar_vetorial.py (vetorial). Juntos = busca híbrida.

Resumível: guarda o offset de leitura do Chroma em meta; se cair, retoma.

Uso:
    python3 indexar_bm25.py build            # constrói/retoma
    python3 indexar_bm25.py build --reset    # zera e reconstrói
    python3 indexar_bm25.py status
    python3 indexar_bm25.py search "mutabilidade contratual PPP" [-n 5]
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexar_vetorial as iv
from hibrido import Fts

FTS_DB = os.path.expanduser("~/.cache/legal-br/fts5_acervo.db")
BATCH = 10000

def _fts():
    return Fts(FTS_DB)

def cmd_build(args):
    col = iv.get_collection()
    total = col.count()
    f = _fts()
    if args.reset:
        print("--reset: zerando índice FTS5")
        f.reset()
    off = int(f.get_meta("chroma_offset", 0) or 0)
    if off >= total and f.count() > 0:
        print(f"✅ FTS5 já completo: {f.count():,} docs (chroma tem {total:,})")
        return
    print(f"chunks no Chroma: {total:,} | FTS5 atual: {f.count():,} | retomando de offset {off:,}")
    t0 = time.time()
    while off < total:
        g = col.get(limit=BATCH, offset=off, include=["documents"])
        ids = g.get("ids") or []
        docs = g.get("documents") or []
        if not ids:
            break
        f.add_many([(i, d or "") for i, d in zip(ids, docs)])
        off += len(ids)
        f.set_meta("chroma_offset", off)
        el = time.time() - t0
        rate = off / el if el else 0
        eta = (total - off) / rate / 60 if rate else 0
        print(f"  {off:,}/{total:,} ({off/total*100:4.1f}%) | {rate:,.0f}/s | "
              f"fts={f.count():,} | ETA {eta:.0f}min", flush=True)
    print(f"✅ FTS5 build OK: {f.count():,} docs em {FTS_DB} ({time.time()-t0:.0f}s)")

def cmd_status(args):
    f = _fts()
    try:
        total = iv.get_collection().count()
    except Exception:
        total = -1
    print(f"FTS5 db      : {FTS_DB}")
    print(f"docs FTS5    : {f.count():,}")
    print(f"docs Chroma  : {total:,}")
    print(f"offset lido  : {f.get_meta('chroma_offset', 0)}")
    mb = os.path.getsize(FTS_DB) / 1e6 if os.path.exists(FTS_DB) else 0
    print(f"tamanho      : {mb:.0f} MB")

def cmd_search(args):
    f = _fts()
    res = f.search(args.query, topk=args.n)
    if not res:
        print("(sem resultados BM25)")
        return
    ids = [i for i, _ in res]
    got = iv.get_collection().get(ids=ids, include=["documents", "metadatas"])
    by = {gid: (doc, meta) for gid, doc, meta in
          zip(got["ids"], got["documents"], got["metadatas"])}
    print(f"\n🔤 BM25 '{args.query}'\n")
    for rank, (i, score) in enumerate(res, 1):
        doc, meta = by.get(i, ("", {}))
        print(f"[{rank}] bm25={score:.2f} | {meta.get('examinador') or meta.get('autor','')} | {meta.get('filename','')}")
        print(f"    {doc[:220].strip()}...\n")

def main():
    p = argparse.ArgumentParser(description="Índice léxico FTS5 (BM25) do acervo PGE-RJ")
    sub = p.add_subparsers(dest="cmd", required=True)
    pb = sub.add_parser("build"); pb.add_argument("--reset", action="store_true"); pb.set_defaults(func=cmd_build)
    pss = sub.add_parser("status"); pss.set_defaults(func=cmd_status)
    pr = sub.add_parser("search"); pr.add_argument("query"); pr.add_argument("-n", type=int, default=5); pr.set_defaults(func=cmd_search)
    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
