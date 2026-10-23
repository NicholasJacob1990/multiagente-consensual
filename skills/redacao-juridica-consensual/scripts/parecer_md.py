"""Leitura comum de minutas jurídicas em Markdown: parecer, petição, recurso, decisão ou outro trabalho.

Aceita dois formatos:

- Markdown simples: títulos ``#``/``##`` e parágrafos ``N. texto``;
- Markdown GENES (o de ``build_estilo_v2.py``): além dos anteriores, linhas
  ``@CAB``, ``@EMENTA``, ``@DATA``, ``@ASS``, ``@ASS+``, ``@ASN`` e ``@ASN+``.

Cada linha não vazia é um bloco. Texto sem numeração recebe IDs implícitos; texto misto
(narrativa sem número e pedidos/listas numerados) recebe IDs globais de bloco e preserva
os números escritos nos itens. ``Documento.numeracao`` é ``"implicita"`` ou ``"mista"``. Os scripts de pré-auditoria, emendas,
pacote de auditoria e redline usam este módulo para enxergar a minuta do
mesmo modo.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

PAR_RE = re.compile(r"^(\d+)\. (.*)$")
MARCA_RE = re.compile(r"^@(CAB|EMENTA|DATA|ASS\+?|ASN\+?) (.*)$")
TITULO_RE = re.compile(r"^(#{1,6}) (.*)$")
MARCAS_ASSINATURA = {"DATA", "ASS", "ASS+", "ASN", "ASN+"}

# "parágrafo 22", "parágrafos 27 e 30", "parágrafos 86 a 88", "parágrafos 12, 14 e 15".
# Não captura "parágrafo único" nem "parágrafo 2º do art. 17" (parágrafo de lei).
REMISSAO_RE = re.compile(
    r"\bpar[áa]grafos?\s+(\d+(?:\s*(?:,|\be\b|\ba\b|\bou\b)\s*\d+)*)(?![\dº°ª])",
    re.IGNORECASE,
)
_LEI_DEPOIS_RE = re.compile(r"^\s*,?\s*(?:do|da)\s+(?:art|lei|decreto|resolu|instru|in\b)", re.IGNORECASE)


@dataclass
class Bloco:
    linha: int
    tipo: str  # par | titulo | marca | texto
    texto: str
    numero: int | None = None
    marca: str | None = None
    numero_original: int | None = None


@dataclass
class Documento:
    blocos: list[Bloco] = field(default_factory=list)
    bruto: str = ""
    numeracao: str = "explicita"  # explicita | implicita | mista

    @property
    def paragrafos(self) -> list[Bloco]:
        return [b for b in self.blocos if b.tipo == "par"]

    def por_numero(self) -> dict[int, str]:
        out: dict[int, str] = {}
        for b in self.paragrafos:
            out.setdefault(b.numero, b.texto)  # type: ignore[arg-type]
        return out

    @property
    def sha256(self) -> str:
        return sha256_texto(self.bruto)


def sha256_texto(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def sha256_arquivo(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ler(path: Path | str) -> Documento:
    return parse(Path(path).read_text(encoding="utf-8"))


def parse(texto: str) -> Documento:
    doc = Documento(bruto=texto)
    for i, linha in enumerate(texto.split("\n"), start=1):
        s = linha.strip()
        if not s:
            continue
        m = PAR_RE.match(s)
        if m:
            doc.blocos.append(Bloco(i, "par", m.group(2), numero=int(m.group(1))))
            continue
        m = MARCA_RE.match(s)
        if m:
            doc.blocos.append(Bloco(i, "marca", m.group(2), marca=m.group(1)))
            continue
        m = TITULO_RE.match(s)
        if m:
            doc.blocos.append(Bloco(i, "titulo", m.group(2)))
            continue
        doc.blocos.append(Bloco(i, "texto", s))
    tem_numero = any(b.tipo == "par" for b in doc.blocos)
    tem_narrativa = any(b.tipo == "texto" for b in doc.blocos)
    if tem_narrativa:
        n = 0
        for b in doc.blocos:
            if b.tipo in ("texto", "par"):
                n += 1
                if b.tipo == "par":
                    b.numero_original = b.numero
                    b.texto = f"{b.numero}. {b.texto}"
                b.tipo, b.numero = "par", n
        doc.numeracao = "mista" if tem_numero else "implicita"
    return doc


def sem_negrito(texto: str) -> str:
    return texto.replace("**", "")


def palavras(texto: str) -> int:
    return len(sem_negrito(texto).split())


def remissoes(texto: str) -> list[tuple[str, list[int]]]:
    """Devolve (trecho, números) para cada remissão interna a parágrafos."""
    out = []
    for m in REMISSAO_RE.finditer(texto):
        if _LEI_DEPOIS_RE.match(texto[m.end():m.end() + 30]):
            continue
        out.append((m.group(0), expandir_numeros(m.group(1))))
    return out


def expandir_numeros(lista: str) -> list[int]:
    toks = re.findall(r"\d+|\ba\b", lista, re.IGNORECASE)
    nums: list[int] = []
    faixa = False
    for t in toks:
        if t.lower() == "a":
            faixa = True
            continue
        n = int(t)
        if faixa and nums:
            nums.extend(range(nums[-1] + 1, n + 1))
        else:
            nums.append(n)
        faixa = False
    return nums


def alinhar_paragrafos(antigo: Documento, novo: Documento, limiar: float = 0.6) -> dict[int, int]:
    """Mapeia número antigo -> número novo por similaridade, em ordem monotônica."""
    a = [(b.numero, b.texto) for b in antigo.paragrafos]
    n = [(b.numero, b.texto) for b in novo.paragrafos]
    sm = difflib.SequenceMatcher(None, [t for _, t in a], [t for _, t in n], autojunk=False)
    mapa: dict[int, int] = {}
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            for i, j in zip(range(i1, i2), range(j1, j2)):
                mapa[a[i][0]] = n[j][0]
            continue
        j0 = j1
        for i in range(i1, i2):
            melhor, alvo = 0.0, None
            for j in range(j0, j2):
                r = difflib.SequenceMatcher(None, a[i][1], n[j][1], autojunk=False).ratio()
                if r > melhor:
                    melhor, alvo = r, j
            if alvo is not None and melhor >= limiar:
                mapa[a[i][0]] = n[alvo][0]
                j0 = alvo + 1
    return mapa
