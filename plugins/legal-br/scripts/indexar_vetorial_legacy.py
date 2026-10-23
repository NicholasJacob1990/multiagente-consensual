#!/usr/bin/env python3
"""
indexar_vetorial.py v2 — Indexação vetorial local do acervo PGE-RJ
===================================================================
Backend  : ChromaDB  (banco vetorial local persistente no SSD)
Embedding: nomic-embed-text via Ollama (M3 Pro com Metal, 768 dims)
Prioridade: pesquisa-web examinadores > livros edital > demais .md

Uso:
    python3 indexar_vetorial.py index            # indexa/atualiza
    python3 indexar_vetorial.py index --force    # reindexa tudo
    python3 indexar_vetorial.py index --tier 1   # só examinadores (rápido)
    python3 indexar_vetorial.py status
    python3 indexar_vetorial.py search "mutabilidade contratual PPP"
    python3 indexar_vetorial.py search "IRDR fazenda publica" --banca B3
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

warnings.filterwarnings("ignore")  # suprime urllib3/ssl warnings

# ── Configurações ─────────────────────────────────────────────────────────────
# ACERVO_RAW (markdown fonte) fica no SSD — só é necessário para REINDEXAR.
ACERVO_RAW = Path(os.environ.get("LEGALBR_ACERVO_RAW", "~/.local/share/legal-br/acervo/Raw")).expanduser()
# CHROMA_DIR (índice vetorial) migrado para o disco INTERNO → consultas não
# dependem mais do SSD montado. Override via env LEGALBR_CHROMA_DIR; se o índice
# interno não existir, cai de volta para o SSD (compat).
_CHROMA_INTERNO = Path(os.path.expanduser("~/.cache/legal-br/chroma_index"))
_CHROMA_SSD = ACERVO_RAW.parent / ".chroma_index"
CHROMA_DIR  = Path(os.environ.get(
    "LEGALBR_CHROMA_DIR",
    str(_CHROMA_INTERNO if _CHROMA_INTERNO.exists() else _CHROMA_SSD),
))
OLLAMA_URL  = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"
WORKERS     = 4      # threads paralelas de embedding
CHUNK_SIZE  = 800    # ~200 tokens por chunk (safe para nomic-embed-text)
CHUNK_OVER  = 100    # overlap
MAX_CHUNKS  = 50     # cap por arquivo (arquivos enormes)
MIN_SIZE    = 300    # bytes mínimos para indexar
MAX_CHUNK_CHARS = 900  # hard limit para evitar Ollama 500

# Arquivos a EXCLUIR — só lixo de sistema (2026-07-19: cortes de CONTEÚDO
# removidos p/ indexar TODOS os materiais, inclusive magistratura).
EXCLUDE_PATTERNS = [
    ".obsidian", ".trash", "ds_store",
]

# Prioridade de indexação (tier 1 = mais importante → indexado primeiro)
TIERS = {
    1: lambda p: p.name.startswith("pesquisa-web__"),        # examinadores
    2: lambda p: "/Livros/" in str(p) or "livros__" in p.name,  # livros edital
    3: lambda p: "concursos__" in p.name or "grupo-cereja" in p.name.lower(),
    4: lambda p: True,                                         # resto
}

# ── Helpers ───────────────────────────────────────────────────────────────────
def get_frontmatter(content: str) -> dict:
    fm = {}
    s = content.lstrip()
    if not s.startswith("---"): return fm
    body = s[3:]
    end = body.find("\n---")
    block = body[:end] if end >= 0 else body[:3000]
    for field in ("examinador", "banca", "tipo_material", "disciplina",
                  "autor", "obra", "fonte_url", "leis", "conceitos"):
        m = re.search(rf"^\s*{re.escape(field)}\s*:\s*(.+?)$", block, re.M)
        if m:
            val = m.group(1).strip().strip("'\"")
            # Limpar wikilinks dos valores
            val = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]+)?\]\]", r"\1", val)
            fm[field] = val[:300]
    return fm

def strip_frontmatter(content: str) -> str:
    s = content.lstrip()
    if not s.startswith("---"): return content
    body = s[3:]
    end = body.find("\n---")
    return body[end + 4:].lstrip() if end >= 0 else content

def chunk_text(text: str, max_chunks: int = MAX_CHUNKS) -> list[str]:
    """Divide por seções markdown, respeitando CHUNK_SIZE."""
    # Dividir em seções (##, ###)
    parts = re.split(r"(?=\n#{1,3} )", text)
    chunks, buf = [], ""
    for part in parts:
        if len(buf) + len(part) <= CHUNK_SIZE:
            buf += part
        else:
            if buf.strip():
                chunks.append(buf.strip())
            if len(part) > CHUNK_SIZE:
                # Dividir parágrafo a parágrafo
                for para in part.split("\n\n"):
                    if len(buf) + len(para) <= CHUNK_SIZE:
                        buf = buf[-CHUNK_OVER:] + para + "\n\n"
                    else:
                        if buf.strip(): chunks.append(buf.strip())
                        buf = para + "\n\n"
            else:
                buf = buf[-CHUNK_OVER:] + part if CHUNK_OVER else part
    if buf.strip():
        chunks.append(buf.strip())
    return [c for c in chunks if len(c.strip()) >= 80][:max_chunks]


def file_hash(path: Path) -> str:
    h = hashlib.md5()
    h.update(str(path.stat().st_mtime).encode())
    h.update(str(path.stat().st_size).encode())
    return h.hexdigest()

def is_relevant(path: Path) -> bool:
    if path.name.startswith("._"):
        return False
    p_lower = str(path).lower()
    return (
        path.stat().st_size >= MIN_SIZE
        and not any(pat in p_lower for pat in EXCLUDE_PATTERNS)
    )


def get_tier(path: Path) -> int:
    for t, fn in TIERS.items():
        if fn(path): return t
    return 4

def embed_one(text: str) -> list[float]:
    import requests
    # Truncar se necessário (evita Ollama 500 em textos muito longos)
    if len(text) > MAX_CHUNK_CHARS:
        text = text[:MAX_CHUNK_CHARS]
    for attempt in range(3):
        try:
            r = requests.post(
                f"{OLLAMA_URL}/api/embeddings",
                json={"model": EMBED_MODEL, "prompt": text},
                timeout=60,
            )
            r.raise_for_status()
            return r.json()["embedding"]
        except Exception as e:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)  # backoff: 1s, 2s
    raise RuntimeError("embed_one failed after 3 attempts")

# ── Coleção ChromaDB ──────────────────────────────────────────────────────────
def get_collection():
    import chromadb
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    col = client.get_or_create_collection(
        "pge_rj_acervo",
        metadata={"hnsw:space": "cosine"},
    )
    return col

# ── Processar um arquivo (usado em threads) ───────────────────────────────────
def process_file(args_tuple):
    fpath, fhash, col = args_tuple
    try:
        content = fpath.read_text(encoding="utf-8", errors="ignore")
        fm = get_frontmatter(content)
        body = strip_frontmatter(content)

        tier = get_tier(fpath)
        # Se for um livro de edital (Tier 2), permitimos até 6000 chunks para indexação completa.
        max_chunks = 6000 if tier == 2 else MAX_CHUNKS
        chunks = chunk_text(body, max_chunks)
        if not chunks:
            return fpath, fhash, 0, None

        meta_base = {
            "source_path": str(fpath),
            "filename": fpath.name,
            "examinador": fm.get("examinador", ""),
            "banca": fm.get("banca", ""),
            "tipo": fm.get("tipo_material", ""),
            "disciplina": fm.get("disciplina", ""),
            "autor": fm.get("autor", ""),
            "obra": fm.get("obra", "")[:200],
            "tier": str(get_tier(fpath)),
        }

        # Remover docs antigos deste arquivo
        try:
            col.delete(where={"source_path": str(fpath)})
        except Exception:
            pass

        # Embeddings (sequencial por arquivo, mas vários arquivos em paralelo)
        embeddings = [embed_one(c) for c in chunks]
        ids = [f"{fpath.stem[:60]}_c{j}" for j in range(len(chunks))]
        metas = [{**meta_base, "chunk_index": j, "chunk_total": len(chunks)}
                 for j in range(len(chunks))]

        col.add(documents=chunks, embeddings=embeddings, metadatas=metas, ids=ids)
        return fpath, fhash, len(chunks), None

    except Exception as e:
        return fpath, fhash, 0, str(e)

# ── Comando: index ─────────────────────────────────────────────────────────────
def cmd_index(args):
    import requests
    # Verificar Ollama
    try:
        r = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        modelos = [m["name"] for m in r.json().get("models", [])]
        if not any(EMBED_MODEL in m for m in modelos):
            print(f"⚠️  Baixando {EMBED_MODEL}...")
            import subprocess
            subprocess.run(["ollama", "pull", EMBED_MODEL], check=True)
    except Exception as e:
        print(f"❌ Ollama offline: {e}\n   Execute: brew services start ollama")
        sys.exit(1)

    col = get_collection()

    # Hashes já indexados
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    hash_file = CHROMA_DIR / "file_hashes.json"
    hash_store = json.loads(hash_file.read_text()) if hash_file.exists() else {}
    if args.force:
        print("⚠️  --force: reindexa tudo")
        hash_store = {}

    # Listar e ordenar por tier
    all_files = [f for f in ACERVO_RAW.rglob("*.md") if is_relevant(f)]

    # Filtrar tier se especificado
    if args.tier:
        tier_fn = TIERS.get(args.tier, lambda p: True)
        all_files = [f for f in all_files if tier_fn(f)]
        print(f"🎯 Modo tier {args.tier}: {len(all_files)} arquivos")

    all_files.sort(key=get_tier)  # tier 1 primeiro

    # Só os novos/modificados
    to_index = [(f, file_hash(f)) for f in all_files
                if hash_store.get(str(f)) != file_hash(f) or args.force]

    print(f"📂 Acervo total  : {len(all_files):,} arquivos")
    print(f"🔄 Para indexar  : {len(to_index):,} (novos ou modificados)")
    print(f"⚡ Workers       : {WORKERS}")
    print(f"💾 Banco em      : {CHROMA_DIR}\n")

    if not to_index:
        print("✅ Acervo já está 100% indexado!")
        return

    # Estimar tempo
    avg_chunks = 5  # média conservadora
    eta_min = len(to_index) * avg_chunks * 0.07 / 60
    print(f"⏱  ETA estimado  : {eta_min:.0f} min ({eta_min/60:.1f}h)\n")
    print("Iniciando... (Ctrl+C para pausar — progresso é salvo)\n")

    t0 = time.time()
    total_chunks = 0
    erros = 0
    SAVE_EVERY = 100

    try:
        with ThreadPoolExecutor(max_workers=WORKERS) as executor:
            futures = {
                executor.submit(process_file, (fpath, fhash, col)): i
                for i, (fpath, fhash) in enumerate(to_index)
            }

            done = 0
            for future in as_completed(futures):
                fpath, fhash, n_chunks, err = future.result()
                done += 1

                if err:
                    erros += 1
                    if erros <= 5:
                        print(f"  ⚠️  {fpath.name[:50]}: {err}")
                else:
                    hash_store[str(fpath)] = fhash
                    total_chunks += n_chunks

                # Progresso
                if done % 20 == 0 or done == len(to_index):
                    elapsed = time.time() - t0
                    rate = done / elapsed if elapsed > 0 else 1
                    eta = (len(to_index) - done) / rate
                    pct = done / len(to_index) * 100
                    tier = get_tier(fpath)
                    print(f"  [{done:>5}/{len(to_index)}] {pct:5.1f}% "
                          f"| tier{tier} | {n_chunks}ck "
                          f"| {fpath.name[:35]:<35} "
                          f"| ETA {eta/60:.0f}min")

                # Salvar hashes periodicamente
                if done % SAVE_EVERY == 0:
                    hash_file.write_text(json.dumps(hash_store, ensure_ascii=False))

    except KeyboardInterrupt:
        print("\n⚠️  Pausado. Progresso salvo.")

    # Salvar final
    hash_file.write_text(json.dumps(hash_store, ensure_ascii=False))

    elapsed = time.time() - t0
    print(f"\n{'='*55}")
    print(f"✅ Indexação concluída!")
    print(f"   Arquivos processados : {len(to_index) - erros:,}")
    print(f"   Chunks indexados     : {total_chunks:,}")
    print(f"   Erros                : {erros}")
    print(f"   Tempo                : {elapsed/60:.1f} min")
    print(f"   Banco em             : {CHROMA_DIR}")
    print(f"{'='*55}")

# ── Comando: status ────────────────────────────────────────────────────────────
def cmd_status(args):
    col = get_collection()
    count = col.count()

    hash_file = CHROMA_DIR / "file_hashes.json"
    n_idx = len(json.loads(hash_file.read_text())) if hash_file.exists() else 0
    all_files = [f for f in ACERVO_RAW.rglob("*.md") if is_relevant(f)]
    n_total = len(all_files)
    n_tier1 = sum(1 for f in all_files if get_tier(f) == 1)

    chroma_mb = sum(f.stat().st_size for f in CHROMA_DIR.rglob("*") if f.is_file()) / 1e6 \
        if CHROMA_DIR.exists() else 0

    pct = n_idx / n_total * 100 if n_total else 0

    print(f"\n{'='*50}")
    print(f"  Banco Vetorial PGE-RJ")
    print(f"{'='*50}")
    print(f"  Chunks indexados  : {count:>8,}")
    print(f"  Arquivos          : {n_idx:>8,} / {n_total:,} ({pct:.1f}%)")
    print(f"  Tier 1 (examin.)  : {n_tier1:>8,} arquivos")
    print(f"  Modelo            : {EMBED_MODEL} (768 dims)")
    print(f"  Banco em          : {CHROMA_DIR}")
    print(f"  Tamanho           : {chroma_mb:.0f} MB")
    if n_idx < n_total:
        print(f"\n  ⚠️  {n_total - n_idx} arquivos pendentes")
        print(f"     python3 indexar_vetorial.py index")
    else:
        print(f"\n  ✅ 100% indexado")
    print(f"{'='*50}\n")

# ── Comando: search ────────────────────────────────────────────────────────────
def cmd_search(args):
    import requests
    q_emb = embed_one(args.query)
    col = get_collection()

    where = {}
    if args.banca:   where["banca"]      = args.banca.upper()
    if args.tipo:    where["tipo"]        = args.tipo
    if args.tier:    where["tier"]        = str(args.tier)

    kwargs = {"query_embeddings": [q_emb], "n_results": args.n}
    if where: kwargs["where"] = where

    res = col.query(**kwargs)
    docs, metas, dists = res["documents"][0], res["metadatas"][0], res["distances"][0]

    print(f"\n🔍 '{args.query}'")
    if where: print(f"   Filtros: {where}")
    print()

    for rank, (doc, meta, dist) in enumerate(zip(docs, metas, dists), 1):
        score = 1 - dist
        parts = [f"[{rank}] {score:.3f}"]
        if meta.get("banca"):      parts.append(meta["banca"])
        if meta.get("examinador"): parts.append(meta["examinador"])
        if meta.get("tipo"):       parts.append(meta["tipo"])
        print(" | ".join(parts))
        print(f"    📄 {meta.get('filename','')}")
        print(f"    {doc[:280].strip()}...")
        print()

# ── CLI ────────────────────────────────────────────────────────────────────────
def main():
    p = argparse.ArgumentParser(description="Banco vetorial local PGE-RJ")
    sub = p.add_subparsers(dest="cmd")

    pi = sub.add_parser("index")
    pi.add_argument("--force", action="store_true")
    pi.add_argument("--tier", type=int, choices=[1,2,3,4],
                    help="Indexar apenas tier específico (1=examinadores)")
    pi.set_defaults(func=cmd_index)

    ps = sub.add_parser("status")
    ps.set_defaults(func=cmd_status)

    pr = sub.add_parser("search")
    pr.add_argument("query")
    pr.add_argument("-n", type=int, default=5)
    pr.add_argument("--banca")
    pr.add_argument("--tipo")
    pr.add_argument("--tier", type=int)
    pr.set_defaults(func=cmd_search)

    args = p.parse_args()
    if not args.cmd:
        p.print_help(); return
    args.func(args)

if __name__ == "__main__":
    main()
