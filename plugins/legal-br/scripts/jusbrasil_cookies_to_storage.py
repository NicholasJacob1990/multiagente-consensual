#!/usr/bin/env python3
"""
jusbrasil_cookies_to_storage.py — converte um cookies.txt (formato Netscape,
exportado do browser) no storageState do Playwright que o jusbrasil_search.py
espera. Abordagem cookie-first: dispensa o login OAuth interativo.

Uso:
    python3 jusbrasil_cookies_to_storage.py \\
        --cookies "~/Downloads/www.jusbrasil.com.br_cookies.txt" \\
        [--out ~/.jusbrasil/storage_state.json]

Depois: rode o jusbrasil_search.py normalmente (ele lê JB_STORAGE_STATE).
Reexporte e rode de novo quando os cookies expirarem (cf_clearance/__cf_bm
duram pouco; a sessao 'user' dura mais).
"""
import argparse
import json
import os
import sys
from pathlib import Path


def parse_netscape(path: Path):
    cookies = []
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.rstrip("\n")
        if not line.strip():
            continue
        http_only = False
        # Alguns exportadores marcam HttpOnly com prefixo no domínio
        if line.startswith("#HttpOnly_"):
            http_only = True
            line = line[len("#HttpOnly_"):]
        elif line.lstrip().startswith("#"):
            continue  # comentário
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _include_sub, cpath, secure, expiry, name, value = parts[:7]
        try:
            expires = int(expiry)
        except ValueError:
            expires = 0
        cookies.append({
            "name": name,
            "value": value,
            "domain": domain,
            "path": cpath or "/",
            "expires": expires if expires > 0 else -1,  # -1 = sessão
            "httpOnly": http_only,
            "secure": str(secure).upper() == "TRUE",
            "sameSite": "Lax",
        })
    return cookies


def main():
    ap = argparse.ArgumentParser(description="cookies.txt (Netscape) -> Playwright storageState")
    ap.add_argument("--cookies", required=True, help="caminho do cookies.txt")
    ap.add_argument("--out", default="~/.jusbrasil/storage_state.json",
                    help="saída storageState (default: ~/.jusbrasil/storage_state.json)")
    args = ap.parse_args()

    src = Path(os.path.expanduser(args.cookies))
    if not src.exists():
        print(json.dumps({"erro": f"cookies.txt não encontrado: {src}"}, ensure_ascii=False))
        return 2

    cookies = parse_netscape(src)
    if not cookies:
        print(json.dumps({"erro": "nenhum cookie parseado (formato inesperado?)"}, ensure_ascii=False))
        return 2

    out = Path(os.path.expanduser(args.out))
    out.parent.mkdir(parents=True, exist_ok=True)
    storage = {"cookies": cookies, "origins": []}
    out.write_text(json.dumps(storage, ensure_ascii=False, indent=2), encoding="utf-8")

    # Diagnóstico (sem expor valores): sinais de sessão/Cloudflare
    names = {c["name"] for c in cookies}
    sinais = {
        "cf_clearance": "cf_clearance" in names,
        "__cf_bm": "__cf_bm" in names,
        "sessao_user": "user" in names,
        "advogado_verificado": "user_is_verified_lawyer" in names,
        "csrf": any(n.startswith("_csrf") for n in names),
    }
    print(json.dumps({
        "ok": True, "out": str(out), "total_cookies": len(cookies),
        "dominios": sorted({c["domain"] for c in cookies}), "sinais": sinais,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
