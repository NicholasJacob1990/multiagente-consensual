#!/usr/bin/env python3
"""
busca_acervo.py — Entrypoint canonico do plugin legal-br para consulta ao
acervo local (Camada 1 / best-effort).

Recupera trechos relevantes de:
  - Doutrina/livros pesados via ChromaDB (busca vetorial semantica, Ollama
    nomic-embed-text)
  - Cadernos/Wiki via qmd-lexical (busca textual) — apenas no modo "hibrido"

A Camada 0 (sempre disponivel) e o MCP qmd nativo (mcp__qmd__query); este
script cobre a profundidade semantica que o MCP nao oferece e so funciona
quando o SSD esta montado e o Ollama esta rodando.

Uso:
  python3 busca_acervo.py check
  python3 busca_acervo.py search --consulta "TERMO" [--modo vetorial|hibrido]
                                  [--disciplina X] [--tema Y] [-n 5]

Saida sempre em JSON (machine-readable), para o agente parsear.
"""
import argparse
import json
import os
import sys

# Torna os modulos irmaos importaveis independentemente do cwd.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# --- servidor residente do acervo (acrescentado 2026-08-31) -------------------
# O ChromaDB carrega o HNSW inteiro (15,5 GB, 5,1 M embeddings) a cada processo
# novo. Numa máquina de 18 GB isso pagina até nunca terminar. Quando o
# acervo_server está no ar, a consulta vai por ele e o índice é carregado uma
# única vez. Sem servidor, o caminho antigo continua valendo.
ACERVO_SERVER = os.environ.get("ACERVO_SERVER", "http://127.0.0.1:8788")


def _via_servidor(consulta, n=5, modo="rrf", timeout=180):
    """Devolve a lista de resultados, ou None se o servidor não puder atender."""
    import json as _json, urllib.parse as _up, urllib.request as _ur
    try:
        u = f"{ACERVO_SERVER}/search?" + _up.urlencode(
            {"q": consulta, "n": n, "modo": modo})
        with _ur.urlopen(u, timeout=timeout) as r:
            return _json.load(r).get("resultados")
    except Exception:
        return None


def servidor_status(timeout=12):
    # 5s era pouco: sob disputa de disco o /health chegou a nao responder a tempo,
    # e o preflight lia "ausente" um minuto depois de ler "recusado". Leitura
    # instavel aqui vira decisao instavel sobre a camada inteira.
    import json as _json, urllib.request as _ur
    try:
        with _ur.urlopen(f"{ACERVO_SERVER}/health", timeout=timeout) as r:
            return _json.load(r)
    except Exception:
        return None
# -----------------------------------------------------------------------------

# --- viabilidade da camada vetorial (acrescentado 2026-08-31) ----------------
# Arquivo presente nao e o mesmo que consulta possivel: o ChromaDB carrega o
# grafo HNSW inteiro na RAM ao primeiro acesso. Sem folga, a busca pagina e nunca
# retorna -- e o aviso de degradacao do cmd_search nunca chegava a ser impresso,
# porque o preflight so media presenca de arquivo.
FOLGA_GB = 2.0


def _ram_disponivel_gb():
    """Livre + inativa + especulativa, em GB: o que o indice pode ocupar.

    Devolve -1.0 quando nao ha como medir -- e -1 significa DESCONHECIDO, nunca
    zero: quem chama so pode desligar a camada vetorial quando sabe que ela nao
    cabe, jamais por falta de medida.
    """
    import re as _re, subprocess as _sp
    # Linux: MemAvailable ja e exatamente a conta que interessa.
    try:
        with open("/proc/meminfo") as fh:
            for linha in fh:
                if linha.startswith("MemAvailable:"):
                    return int(linha.split()[1]) * 1024 / 1073741824.0
    except Exception:
        pass
    try:
        vm = _sp.run(["vm_stat"], capture_output=True, text=True, timeout=5).stdout
        pg = int(_re.search(r"page size of (\d+)", vm).group(1))

        def _pg(rot):
            m = _re.search(rot + r":\s+(\d+)", vm)
            return int(m.group(1)) if m else 0

        livres = _pg("Pages free") + _pg("Pages inactive") + _pg("Pages speculative")
        return livres * pg / 1073741824.0
    except Exception:
        return -1.0


def _hnsw_gb(chroma_dir):
    """Quanta RAM uma consulta a este store exige.

    Num store MONOLITICO e o maior (unico) grafo: nao ha como consultar sem
    carrega-lo. Num store FATIADO a busca escolhe fatias por materia dentro de um
    orcamento, entao o limiar e a MENOR fatia -- se nem ela couber, nada responde;
    exigir a maior desligaria a camada inteira por causa de uma fatia que a
    consulta talvez nunca abra.
    """
    tamanhos = []
    try:
        for raiz, _d, arqs in os.walk(str(chroma_dir)):
            if "data_level0.bin" in arqs:
                tamanhos.append(os.path.getsize(os.path.join(raiz, "data_level0.bin")))
    except Exception:
        return -1.0
    if not tamanhos:
        return 0.0
    fatiado = os.path.exists(os.path.join(str(chroma_dir), "_MANIFESTO.json"))
    escolhido = min(tamanhos) if fatiado else max(tamanhos)
    return escolhido / 1073741824.0
# -----------------------------------------------------------------------------

def preflight():
    """Verifica disponibilidade da Camada 1 sem lancar excecao."""
    status = {
        "chromadb_instalado": False,
        "ssd_montado": False,
        "chroma_store": False,
        "ollama_up": False,
        "qmd_lexical": False,
        "pronto_vetorial": False,
        "pronto_hibrido": False,
        "detalhes": {},
    }
    _srv = servidor_status()
    # Responder nao e o mesmo que estar pronto: o servidor tambem atende quando
    # RECUSOU carregar o indice por falta de memoria. So a fase "pronto" torna a
    # camada vetorial viavel -- tratar qualquer resposta como sucesso reabriria
    # exatamente o travamento que este preflight existe para evitar.
    # "recusado" e o unico estado que desqualifica. Exigir "pronto" criava um
    # impasse: o servidor so aquece quando alguem o consulta, e ninguem o
    # consultava porque ele nao estava quente. Com fatias a carga e barata
    # (0,06 GB no minimo, ~3 s), entao acordar o servidor e o certo a fazer.
    _fase = (_srv or {}).get("fase")
    status["servidor_residente"] = bool(_srv) and _fase != "recusado"
    status["servidor_fase"] = _fase or "ausente"
    if _srv:
        status["detalhes"]["servidor"] = {k: _srv.get(k) for k in
            ("fase", "colecao", "carregado_em", "ram_disponivel_gb", "erro")}
    # chromadb instalado?
    try:
        import chromadb  # noqa: F401
        status["chromadb_instalado"] = True
    except Exception as e:
        status["detalhes"]["chromadb"] = str(e)

    try:
        import indexar_vetorial as iv
        chroma_dir = iv.CHROMA_DIR
        ollama_url = iv.OLLAMA_URL
        status["detalhes"]["chroma_dir"] = str(chroma_dir)
        # SSD só é necessário para REINDEXAR (lê o RAW); consulta usa o índice
        # interno. ssd_montado vira informativo, não bloqueia pronto_vetorial.
        status["ssd_montado"] = iv.ACERVO_RAW.exists()
        status["chroma_store"] = chroma_dir.exists()
        # Ollama up?
        try:
            import requests
            r = requests.get(f"{ollama_url}/api/tags", timeout=10)
            status["ollama_up"] = r.status_code == 200
        except Exception as e:
            status["detalhes"]["ollama"] = str(e)
    except Exception as e:
        status["detalhes"]["indexar_vetorial"] = str(e)

    # qmd-lexical (pesquisar_materiais.py no SSD) + FTS5/BM25 (híbrido RRF)
    try:
        import busca_hibrida as bh
        status["qmd_lexical"] = os.path.exists(bh.PESQUISAR_MATERIAIS_PATH)
        status["fts_bm25"] = os.path.exists(bh.FTS_DB)
        status["detalhes"]["fts_db"] = bh.FTS_DB
    except Exception as e:
        status["detalhes"]["busca_hibrida"] = str(e)

    status["ram_disponivel_gb"] = round(_ram_disponivel_gb(), 1)
    status["hnsw_gb"] = round(_hnsw_gb(status["detalhes"].get("chroma_dir", "")), 2)
    if status["hnsw_gb"] <= 0 or status["ram_disponivel_gb"] < 0:
        _cabe = True   # sem medida confiavel, nao se desliga nada
    else:
        _cabe = status["ram_disponivel_gb"] >= status["hnsw_gb"] + FOLGA_GB
    status["vetorial_viavel"] = bool(status["servidor_residente"] or _cabe)
    if not status["vetorial_viavel"]:
        status["detalhes"]["viabilidade"] = (
            "indice de %s GB contra %s GB disponiveis: a consulta paginaria e nao "
            "retornaria. Suba o acervo_server (~/.local/bin/acervo_server.py) ou "
            "aponte CHROMA_DIR para uma fatia."
            % (status["hnsw_gb"], status["ram_disponivel_gb"]))

    status["pronto_vetorial"] = (
        status["chromadb_instalado"]
        and status["chroma_store"]
        and status["ollama_up"]
        and status["vetorial_viavel"]
    )
    status["pronto_hibrido"] = status["pronto_vetorial"] and status["qmd_lexical"]
    # RRF real = vetor + BM25 (FTS5) sobre o mesmo corpus
    status["pronto_rrf"] = status["pronto_vetorial"] and status.get("fts_bm25", False)
    return status


def cmd_check(_args):
    print(json.dumps(preflight(), ensure_ascii=False, indent=2))
    return 0


def cmd_search(args):
    query = " ".join(filter(None, [args.disciplina, args.tema, args.consulta])).strip()
    if not query:
        print(json.dumps({"erro": "Forneca --consulta (e/ou --disciplina/--tema)."},
                         ensure_ascii=False))
        return 2

    pf = preflight()
    # rrf é o padrão; se o índice BM25 (FTS5) não existir, degrada p/ vetorial sem erro
    _fallback = None
    if args.modo == "rrf" and not pf.get("pronto_rrf") and pf.get("pronto_vetorial"):
        _fallback = "RRF indisponível (índice BM25 ausente — rode indexar_bm25.py build); usando vetorial."
        args.modo = "vetorial"
    _disp = {
        "vetorial": pf["pronto_vetorial"],
        "hibrido": pf["pronto_hibrido"],
        "rrf": pf.get("pronto_rrf", False),
    }
    out = {
        "consulta": query,
        "modo": args.modo,
        "disponivel": _disp.get(args.modo, pf["pronto_vetorial"]),
        "preflight": pf,
        "resultados": [],
    }
    if _fallback:
        out["aviso_fallback"] = _fallback

    if not out["disponivel"]:
        out["aviso"] = (
            "Camada 1 (acervo local via script) indisponivel — siga apenas com o "
            "MCP qmd nativo (mcp__qmd__query) e as fontes externas. "
            "Cheque SSD montado / Ollama rodando."
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    # Servidor residente primeiro: ele mantem o indice ja carregado, entao responde
    # em decimos de segundo onde um processo novo levaria minutos -- ou nunca.
    if pf.get("servidor_residente"):
        _res = _via_servidor(query, n=args.n, modo=args.modo)
        if _res is not None:
            out["resultados"] = _res
            out["via"] = "servidor_residente"
            print(json.dumps(out, ensure_ascii=False, indent=2))
            return 0

    import busca_hibrida as bh
    import contextlib

    resultados = []
    # Os helpers de busca imprimem eventuais erros em stdout; redireciona para
    # stderr para manter o stdout como JSON puro (machine-readable).
    with contextlib.redirect_stdout(sys.stderr):
        if args.modo == "rrf":
            # Híbrido REAL: vetor + BM25 sobre o MESMO corpus, fundidos por RRF.
            resultados = bh.buscar_hibrido_rrf(query, n=args.n)
        else:
            # Vetorial (ChromaDB) — sempre no modo vetorial e hibrido
            resultados.extend(bh.buscar_vetorial(query, n=args.n))
            # Lexical (qmd/cadernos) — apenas no modo hibrido (corpora distintos)
            if args.modo == "hibrido":
                lex = bh.buscar_lexico(args.disciplina, args.tema, args.consulta, limite=args.n)
                for r in lex:
                    r.setdefault("fonte", "Cadernos/Wiki (qmd-lexical)")
                resultados = lex + resultados

    # Normaliza e trunca trechos
    for r in resultados:
        if isinstance(r.get("trecho"), str):
            r["trecho"] = r["trecho"].strip()
    out["resultados"] = resultados
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(description="Consulta ao acervo local (plugin legal-br)")
    sub = p.add_subparsers(dest="cmd", required=True)

    pc = sub.add_parser("check", help="Preflight: reporta disponibilidade da Camada 1")
    pc.set_defaults(func=cmd_check)

    ps = sub.add_parser("search", help="Busca no acervo local")
    ps.add_argument("--consulta", default="")
    ps.add_argument("--disciplina", default="")
    ps.add_argument("--tema", default="")
    ps.add_argument("--modo", choices=["vetorial", "hibrido", "rrf"], default="rrf")
    ps.add_argument("-n", type=int, default=5)
    ps.set_defaults(func=cmd_search)

    args = p.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
