#!/usr/bin/env python3
"""
hibrido.py — motor de busca HÍBRIDA (BM25 léxico + vetorial), fundido por RRF.

- Léxico: SQLite FTS5 (BM25 nativo, em disco, escala p/ milhões de docs; stdlib).
- Vetorial: fornecido pelo chamador (ChromaDB/Ollama) — este módulo só funde.
- Fusão: Reciprocal Rank Fusion (RRF) sobre os MESMOS ids nas duas listas.

Sem dependências externas (só stdlib). Usado por legal-br (acervo/ChromaDB) e
por ficha-informativos (cards.json). Cópia idêntica nos dois repositórios.
"""
import os
import re
import sqlite3
import unicodedata

# ── normalização de consulta ─────────────────────────────────────────────────
def strip_accents(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")

def normalize(s: str) -> str:
    return strip_accents(s).lower()

# stopwords PT curtas (não discriminam) — evitam poluir o OR do BM25
_STOP = set(
    "a o e de da do das dos ou no na nos nas em um uma uns umas que se por com para "
    "ao aos as os pelo pela pelos pelas sobre sob ser sao seu sua seus suas este esta "
    "isso essa esse aquilo qual quais como onde quando entre ate apos".split()
)

def query_terms(q: str, minlen: int = 2):
    toks = re.findall(r"[a-z0-9]{%d,}" % minlen, normalize(q))
    return [t for t in toks if t not in _STOP]

def match_expr(q: str):
    """Monta uma expressão FTS5 MATCH segura: cada termo como literal entre aspas,
    unidos por OR (recall alto; o BM25 ranqueia)."""
    terms = query_terms(q)
    if not terms:
        return None
    return " OR ".join('"%s"' % t.replace('"', "") for t in terms)

# ── índice FTS5 (BM25) ───────────────────────────────────────────────────────
class Fts:
    """Índice léxico FTS5 persistente. Linhas = (id, content). O `id` casa com o
    id do vetor (ChromaDB) para permitir RRF sobre a mesma unidade."""

    def __init__(self, path: str):
        self.path = path
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        self.con = sqlite3.connect(path)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS fts USING "
            "fts5(id UNINDEXED, content, tokenize='unicode61 remove_diacritics 2')"
        )
        self.con.execute("CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT)")
        self.con.commit()

    def count(self) -> int:
        return self.con.execute("SELECT count(*) FROM fts").fetchone()[0]

    def get_meta(self, k, default=None):
        r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r[0] if r else default

    def set_meta(self, k, v):
        self.con.execute("INSERT OR REPLACE INTO meta VALUES(?,?)", (k, str(v)))
        self.con.commit()

    def add_many(self, rows):
        """rows: iterável de (id, content)."""
        self.con.executemany("INSERT INTO fts(id, content) VALUES(?,?)", rows)
        self.con.commit()

    def reset(self):
        self.con.execute("DELETE FROM fts")
        self.con.execute("DELETE FROM meta")
        self.con.commit()

    def search(self, query: str, topk: int = 50):
        """Retorna [(id, score)] ordenado best-first. Score = -bm25 (bm25 do FTS5
        é mais negativo quanto melhor; invertemos p/ maior=melhor)."""
        expr = match_expr(query)
        if not expr:
            return []
        try:
            rows = self.con.execute(
                "SELECT id, bm25(fts) FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT ?",
                (expr, topk),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        return [(r[0], -float(r[1])) for r in rows]

# ── fusão RRF ────────────────────────────────────────────────────────────────
def rrf(ranked_lists, k: int = 60, weights=None):
    """Reciprocal Rank Fusion. ranked_lists: lista de listas de ids (best-first).
    Retorna [(id, score_fundido)] ordenado. k amortece o peso das posições baixas."""
    agg = {}
    hits = {}
    for i, ids in enumerate(ranked_lists):
        w = weights[i] if weights else 1.0
        for rank, _id in enumerate(ids):
            agg[_id] = agg.get(_id, 0.0) + w / (k + rank + 1)
            hits.setdefault(_id, set()).add(i)
    fused = sorted(agg.items(), key=lambda x: -x[1])
    return [(i, s, sorted(hits[i])) for i, s in fused]
