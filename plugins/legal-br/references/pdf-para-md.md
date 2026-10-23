# PDF → Markdown (pdf2md / pdf-inspector) — **com OCR obrigatório**

Converter PDFs em Markdown **antes de ler, citar ou analisar** — contratos, NDAs,
íntegras de acórdãos, doutrina, materiais, anexos e processos SEI chegam em PDF.
Engine: `pdf2md` (binário Rust em `~/.local/bin/pdf2md`, biblioteca `pdf-inspector`),
com **OCR via `ocrmypdf`** embutido no pipeline.

> **Regra do plugin (sempre):** todo PDF passa por **OCR** e gera **sempre uma cópia
> `.md` citável**. Trabalhe sobre o `.md` — nunca cite trechos lidos direto do PDF
> sem antes gerar o `.md`. PDFs escaneados ou com **camada de texto ruim/garbled**
> (matrículas, contratos antigos digitalizados) são corrigidos pelo OCR e **nunca
> abortam** a conversão.

## Quando usar
- O usuário aponta um **arquivo PDF local** para análise/parecer/revisão.
- Você **baixou** um PDF (íntegra de acórdão, peça, doutrina) via firecrawl/JusBrasil.
- Antes de indexar um PDF no acervo (precisa virar `.md`).

## Wrapper (uso padrão)

```bash
# pdf2md + ocrmypdf disponíveis?
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" check

# Converter -> SEMPRE grava <pdf>.md (OCR automático) e devolve status JSON
#   (type, page_count, out, bytes, ocr.{ocr,estrategia})
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf" --out saida.md

# Ler o MD no stdout (a cópia .md é gravada do mesmo jeito)
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf" --stdout

# Só algumas páginas / com marcadores de página
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf" --select-pages 1,3,5-10 --pages

# Manter o PDF pós-OCR ao lado (auditoria): gera <pdf>.ocr.pdf
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/pdf_para_md.py" convert "ARQUIVO.pdf" --keep-ocr-pdf
```

## Como o OCR é escolhido (modo `--ocr`, default `auto`)

O `auto` **sempre aplica OCR**, escolhendo a estratégia pelo `type` detectado:

| `type` (pdf2md) | Estratégia ocrmypdf | Porquê |
|---|---|---|
| `scanned` / `image_based` | `--force-ocr` | não há texto nativo; rasteriza e OCRa tudo |
| `mixed` | `--force-ocr` | garante texto em toda página (algumas são imagem) |
| `text_based` / `desconhecido` | `--redo-ocr` (fallback `--force-ocr`) | **refaz camadas de OCR ruins/garbled e preserva o texto nativo** — corrige o caso "escaneado COM camada-lixo" (ex.: matrículas), que o pdf2md rotula como `text_based` |

- `--ocr force` → força `--force-ocr` em todo o PDF (mais lento; use se o `redo` não recuperar bem).
- `--ocr never` → desliga o OCR (apenas pdf2md). **Evite** — só para PDF sabidamente limpo.
- `--ocr-lang` → idiomas do OCR (default `por+eng`).

**Idempotência/robustez:** se o `ocrmypdf` faltar ou o OCR falhar, o wrapper **não aborta** —
converte o PDF original e registra `ocr.aviso` no status (sinal de que o texto pode estar incompleto).

## pdf2md direto (CLI, se precisar das opções cruas)
```bash
pdf2md <pdf> --raw                # markdown puro no stdout
pdf2md <pdf> --detect-only        # só tipo + nº de páginas
pdf2md <pdf> --json               # resultado em JSON
pdf2md <pdf> --analyze            # detecção + layout (tabelas/colunas), sem markdown
```

## Limitações / cuidados
- Layouts **multicoluna/boxes** (materiais de revisão) podem sair com ordem de leitura
  imperfeita; acórdãos e leis (coluna única) saem bem.
- OCR de documentos **grandes e escaneados** leva tempo (minutos) — é esperado.
- Citações extraídas de PDF (mesmo pós-OCR) são material **a conferir contra a fonte oficial**.
- O `type` do pdf2md **não é confiável** para distinguir "texto bom" de "camada-lixo";
  por isso o default `auto` roda `--redo-ocr` nos `text_based` em vez de confiar no rótulo.
