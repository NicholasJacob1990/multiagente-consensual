#!/usr/bin/env python3
import argparse
import json
import subprocess
import sys
import os
from pathlib import Path

# Garante que `indexar_vetorial` (no mesmo diretorio) seja importavel
# independentemente do cwd de onde o script e chamado.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indexar_vetorial
from hibrido import Fts, rrf

# índice léxico FTS5 (BM25) do MESMO corpus vetorial (construído por indexar_bm25.py)
FTS_DB = os.path.expanduser("~/.cache/legal-br/fts5_acervo.db")

# Resolve a versao MAIS RECENTE de PGE-Skills-v* no SSD (evita quebrar a cada
# bump de versao). Fallback para string vazia se o SSD nao estiver montado.
def _resolver_pesquisar_materiais():
    base = Path("/Volumes/SSD NICK")
    if not base.exists():
        return ""
    candidatos = sorted(
        base.glob("PGE-Skills-v*/scripts/pesquisar_materiais.py"),
        key=lambda p: p.parent.parent.name,
    )
    return str(candidatos[-1]) if candidatos else ""

PESQUISAR_MATERIAIS_PATH = _resolver_pesquisar_materiais()

def buscar_lexico(disciplina, tema, consulta, limite=5):
    try:
        cmd = [
            "python3", PESQUISAR_MATERIAIS_PATH, "query",
            "--limite", str(limite)
        ]
        if disciplina: cmd.extend(["--disciplina", disciplina])
        if tema: cmd.extend(["--tema", tema])
        if consulta: cmd.extend(["--consulta", consulta])

        out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
        return json.loads(out).get("encontrados", [])
    except Exception as e:
        print(f"Erro na busca léxica: {e}")
        return []

def buscar_vetorial(query, n=5):
    try:
        emb = indexar_vetorial.embed_one(query)
        col = indexar_vetorial.get_collection()
        res = col.query(query_embeddings=[emb], n_results=n)

        encontrados = []
        if not res["documents"]: return encontrados
        docs = res["documents"][0]
        metas = res["metadatas"][0]
        dists = res["distances"][0]

        for doc, meta, dist in zip(docs, metas, dists):
            score = 1 - dist
            encontrados.append({
                "score": score,
                "fonte": "Doutrina/Acervo (ChromaDB)",
                "arquivo": meta.get("source_path", ""),
                "titulo": meta.get("filename", ""),
                "autor": meta.get("autor", "") or meta.get("examinador", ""),
                "nota_md": meta.get("source_path", ""),
                "trecho": doc
            })
        return encontrados
    except Exception as e:
        print(f"Erro na busca vetorial: {e}")
        return []

def buscar_bm25(query, n=5, topk=50):
    """Só léxico (FTS5/BM25), hidratando metadados do Chroma."""
    col = indexar_vetorial.get_collection()
    lex = Fts(FTS_DB).search(query, topk=topk) if os.path.exists(FTS_DB) else []
    score = dict(lex)
    ids = [i for i, _ in lex][:n]
    got = (col.get(ids=ids, include=["documents", "metadatas"])
           if ids else {"ids": [], "documents": [], "metadatas": []})
    by = {gid: (doc, meta) for gid, doc, meta in
          zip(got["ids"], got["documents"], got["metadatas"])}
    out = []
    for i in ids:
        doc, meta = by.get(i, ("", {}))
        out.append({
            "score": round(score.get(i, 0.0), 3),
            "score_bm25": round(score.get(i, 0.0), 3), "score_vetorial": 0.0,
            "retrievers": ["bm25"], "fonte": "Acervo (BM25)",
            "arquivo": meta.get("source_path", ""), "titulo": meta.get("filename", ""),
            "autor": meta.get("autor", "") or meta.get("examinador", ""),
            "nota_md": meta.get("source_path", ""), "trecho": doc,
        })
    return out

def buscar_hibrido_rrf(query, n=5, topk=50, k_rrf=60):
    """Híbrido REAL: vetor (ChromaDB) + BM25 (FTS5) sobre o MESMO corpus/ids,
    fundidos por Reciprocal Rank Fusion. Ordena por score fundido."""
    col = indexar_vetorial.get_collection()
    # vetorial (semântico)
    vec_ids, vec_score = [], {}
    try:
        emb = indexar_vetorial.embed_one(query)
        vres = col.query(query_embeddings=[emb], n_results=topk)
        vec_ids = (vres.get("ids") or [[]])[0]
        dists = (vres.get("distances") or [[]])[0]
        vec_score = {i: 1 - d for i, d in zip(vec_ids, dists)}
    except Exception as e:
        print(f"Erro vetorial: {e}")
    # léxico (BM25/FTS5)
    lex = []
    try:
        if os.path.exists(FTS_DB):
            lex = Fts(FTS_DB).search(query, topk=topk)
        else:
            print(f"Aviso: índice BM25 ausente ({FTS_DB}) — rode indexar_bm25.py build")
    except Exception as e:
        print(f"Erro BM25: {e}")
    lex_ids = [i for i, _ in lex]
    lex_score = dict(lex)
    # fusão RRF
    fused = rrf([vec_ids, lex_ids], k=k_rrf)[:n]
    ids = [i for i, _, _ in fused]
    got = (col.get(ids=ids, include=["documents", "metadatas"])
           if ids else {"ids": [], "documents": [], "metadatas": []})
    by = {gid: (doc, meta) for gid, doc, meta in
          zip(got["ids"], got["documents"], got["metadatas"])}
    out = []
    for _id, fscore, srcs in fused:
        doc, meta = by.get(_id, ("", {}))
        retr = (["vetorial"] if 0 in srcs else []) + (["bm25"] if 1 in srcs else [])
        out.append({
            "score": round(fscore, 5),
            "score_vetorial": round(vec_score.get(_id, 0.0), 3),
            "score_bm25": round(lex_score.get(_id, 0.0), 3),
            "retrievers": retr,
            "fonte": "Acervo (híbrido RRF: vetor+BM25)",
            "arquivo": meta.get("source_path", ""),
            "titulo": meta.get("filename", ""),
            "autor": meta.get("autor", "") or meta.get("examinador", ""),
            "nota_md": meta.get("source_path", ""),
            "trecho": doc,
        })
    return out

def main():
    p = argparse.ArgumentParser(description="Busca Híbrida: Léxica (Cadernos) + Semântica (Doutrina)")
    p.add_argument("--disciplina", default="")
    p.add_argument("--tema", default="")
    p.add_argument("--consulta", default="")
    p.add_argument("--limite-lexico", type=int, default=3)
    p.add_argument("--limite-vetorial", type=int, default=3)
    args = p.parse_args()

    query_str = " ".join(filter(None, [args.disciplina, args.tema, args.consulta]))
    if not query_str:
        print("Forneça algum termo de busca.")
        sys.exit(1)

    print(f"🔍 Busca Híbrida: '{query_str}'\n")

    print("📚 Consultando Acervo Lexical...")
    res_lexico = buscar_lexico(args.disciplina, args.tema, args.consulta, args.limite_lexico)

    print("🧠 Consultando Doutrina Vetorial...")
    res_vetorial = buscar_vetorial(query_str, args.limite_vetorial)

    print("="*60)
    print(" RESULTADOS ".center(60, "="))
    print("="*60 + "\n")

    def print_result(rank, r, tipo):
        score = r.get("score", 0)
        score_str = f"{score:.2f}" if isinstance(score, float) else str(score)
        print(f"[{rank}] {tipo} | Score: {score_str}")
        print(f"📄 Título: {r.get('titulo')}")
        if r.get("autor"):
            print(f"👤 Autor: {r.get('autor')}")
        print(f"📁 Arquivo: {r.get('arquivo')}")
        trecho = r.get("trecho", "").strip().replace("\n", " ")[:300]
        print(f"📝 Trecho: {trecho}...\n")

    idx = 1
    if res_lexico:
        print("🔹 MELHORES RESULTADOS LÉXICOS (Cadernos/Wiki):")
        for r in res_lexico:
            print_result(idx, r, "LÉXICO")
            idx += 1
    else:
        print("🔹 Nenhum resultado léxico encontrado.\n")

    if res_vetorial:
        print("🔸 MELHORES RESULTADOS SEMÂNTICOS (Doutrina/Livros):")
        for r in res_vetorial:
            print_result(idx, r, "VETORIAL")
            idx += 1
    else:
        print("🔸 Nenhum resultado semântico encontrado.\n")

if __name__ == "__main__":
    main()
