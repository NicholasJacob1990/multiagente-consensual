#!/usr/bin/env bash
# comparar-candidatos.sh — avalia consolidações finais cegamente, sem escolher vencedora.
#
# Uso:
#   comparar-candidatos.sh <run-dir>
#   comparar-candidatos.sh <run-dir> --dry-run
#
# Lê `consolidacao_final.candidatos` e `painel_avaliacao_cega` de meta.json. Cada candidata é
# copiada para um run isolado e submetida ao mesmo avaliar.sh em modo cego. O resultado preserva
# todas, produz diffs pareados e termina sempre em `aguardando_escolha_humana`.

set -euo pipefail

RUN_DIR="${1:-}"
DRY_RUN=0
AVALIADOR_BIN="${AVALIADOR_BIN:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/avaliar.sh}"

die() { echo "ERRO: $*" >&2; exit 1; }

for ARG in "${@:2}"; do
  case "$ARG" in
    --dry-run) DRY_RUN=1 ;;
    *) die "opção desconhecida: $ARG" ;;
  esac
done

[ -n "$RUN_DIR" ] || die "uso: comparar-candidatos.sh <run-dir> [--dry-run]"
[ -d "$RUN_DIR" ] || die "run-dir não existe: $RUN_DIR"
[ -f "$RUN_DIR/meta.json" ] || die "falta $RUN_DIR/meta.json"
command -v jq >/dev/null || die "jq não encontrado no PATH"
command -v python3 >/dev/null || die "python3 não encontrado no PATH"
command -v shasum >/dev/null || die "shasum não encontrado no PATH"
[ -x "$AVALIADOR_BIN" ] || die "avaliador não executável: $AVALIADOR_BIN"

RUN_DIR=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$RUN_DIR")
META="$RUN_DIR/meta.json"
MODO=$(jq -r '.consolidacao_final.modo // "redator_unico"' "$META")
case "$MODO" in
  dupla_cega|multipla_cega) ;;
  *) die "consolidacao_final.modo precisa ser dupla_cega ou multipla_cega" ;;
esac
TOTAL=$(jq -r 'if (.consolidacao_final.candidatos | type) == "array" then (.consolidacao_final.candidatos | length) else 0 end' "$META")
[ "$TOTAL" -ge 2 ] 2>/dev/null || die "a consolidação cega exige pelo menos duas candidatas finais; encontrei $TOTAL"
[ "$MODO" != "dupla_cega" ] || [ "$TOTAL" -eq 2 ] 2>/dev/null || die "dupla_cega exige exatamente duas candidatas; use multipla_cega para $TOTAL"
VISIBILIDADE=$(jq -r '.consolidacao_final.visibilidade // empty' "$META")
if [ "$TOTAL" -eq 2 ] 2>/dev/null; then
  case "$VISIBILIDADE" in
    cega_ate_ambos_concluirem|cega_ate_todos_concluirem) ;;
    *) die "consolidacao_final.visibilidade precisa garantir cegamento até as duas candidatas concluírem" ;;
  esac
else
  [ "$VISIBILIDADE" = "cega_ate_todos_concluirem" ] || die "consolidacao_final.visibilidade precisa garantir cegamento até todas as candidatas concluírem"
fi
ESCOLHA_AUTOMATICA=$(jq -r '.consolidacao_final.escolha_automatica // false' "$META")
[ "$ESCOLHA_AUTOMATICA" = "false" ] || die "escolha automática é proibida na consolidação cega"

SNAPSHOT_SHA=$(jq -r '.consolidacao_final.snapshot_sha256 // empty' "$META")
ARQUIVOS=()
CAMINHOS_RELATIVOS=()
IDS=()
SHAS=()
BASES=()
AUTORES=()
SESSOES=()
CANDIDATAS_JSON='[]'

for ((IDX=0; IDX<TOTAL; IDX++)); do
  OBJ=$(jq -c ".consolidacao_final.candidatos[$IDX]" "$META")
  ID=$(jq -r '.id // empty' <<<"$OBJ")
  REL=$(jq -r '.arquivo // empty' <<<"$OBJ")
  AUTOR=$(jq -c '.autor // {}' <<<"$OBJ")
  CLI=$(jq -r '.cli // empty' <<<"$AUTOR")
  SESSAO=$(jq -r '.sessao // empty' <<<"$AUTOR")
  ESPERADO=$(jq -r '.sha256 // empty' <<<"$OBJ")
  BASE=$(jq -r '.base_sha256 // empty' <<<"$OBJ")
  [ -n "$BASE" ] || BASE="$SNAPSHOT_SHA"

  [[ "$ID" =~ ^[A-Za-z0-9._-]+$ ]] || die "id de candidata inválido: $ID"
  [ -n "$REL" ] || die "candidata $ID não informa arquivo"
  [ -n "$CLI" ] || die "candidata $ID não informa autor.cli"
  [ -n "$SESSAO" ] || die "candidata $ID não informa autor.sessao"
  case "$CLI" in
    codex|claude|gemini|antigravity|grok|kimi|opencode) ;;
    *) die "candidata $ID usa CLI desconhecido: $CLI" ;;
  esac
  case "$REL" in
    /*|..|../*|*/../*|*/..) die "caminho inseguro na candidata $ID: $REL" ;;
  esac
  [[ "$BASE" =~ ^[0-9a-fA-F]{64}$ ]] || die "candidata $ID não tem base_sha256/snapshot_sha256 congelado"

  for EXISTENTE in "${IDS[@]:-}"; do
    [ "$EXISTENTE" != "$ID" ] || die "id de candidata duplicado: $ID"
  done
  for EXISTENTE in "${SESSOES[@]:-}"; do
    [ "$EXISTENTE" != "$SESSAO" ] || die "sessão de autora duplicada na candidata $ID"
  done

  ALVO="$RUN_DIR/$REL"
  [ -f "$ALVO" ] || die "arquivo da candidata $ID não existe: $REL"
  REAL=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$ALVO")
  case "$REAL" in
    "$RUN_DIR"/*) ;;
    *) die "candidata $ID resolve para fora do run-dir" ;;
  esac

  SHA=$(shasum -a 256 "$REAL" | awk '{print $1}')
  if [ -n "$ESPERADO" ] && [ "$ESPERADO" != "$SHA" ]; then
    die "hash divergente na candidata $ID: meta=$ESPERADO arquivo=$SHA"
  fi

  IDS+=("$ID")
  CAMINHOS_RELATIVOS+=("$REL")
  ARQUIVOS+=("$REAL")
  SHAS+=("$SHA")
  BASES+=("$BASE")
  AUTORES+=("$AUTOR")
  SESSOES+=("$SESSAO")
  CANDIDATAS_JSON=$(jq -c \
    --arg id "$ID" --arg arquivo "$REL" --arg sha256 "$SHA" --arg base_sha256 "$BASE" \
    --argjson autor "$AUTOR" '. + [{id:$id,arquivo:$arquivo,sha256:$sha256,base_sha256:$base_sha256,autor:$autor}]' \
    <<<"$CANDIDATAS_JSON")
done

for ((IDX=1; IDX<TOTAL; IDX++)); do
  [ "${BASES[0]}" = "${BASES[$IDX]}" ] || die "as candidatas não usam o mesmo snapshot/base_sha256"
done
for ((A=0; A<TOTAL; A++)); do
  for ((B=A+1; B<TOTAL; B++)); do
    [ "${SHAS[$A]}" != "${SHAS[$B]}" ] || die "candidatas ${IDS[$A]} e ${IDS[$B]} são byte-idênticas"
  done
done

if [ "$DRY_RUN" -eq 1 ]; then
  jq -n --arg modo "$MODO" --arg visibilidade "$VISIBILIDADE" --arg avaliador "$AVALIADOR_BIN" --arg snapshot_sha256 "${BASES[0]}" \
    --argjson candidatas "$CANDIDATAS_JSON" \
    '{dry_run:true,modo:$modo,visibilidade:$visibilidade,avaliador:$avaliador,snapshot_sha256:$snapshot_sha256,candidatas:$candidatas,
      avaliacao:"cega e separada, com a mesma rubrica",escolha_automatica:false,
      proximo_estado:"AGUARDANDO_ESCOLHA_HUMANA"}'
  exit 0
fi

DESTINO="$RUN_DIR/comparacao-final"
[ ! -e "$DESTINO" ] || die "comparação final já existe: $DESTINO"
TEMP=$(mktemp -d "$RUN_DIR/.comparacao-final.tmp.XXXXXX") || die "não foi possível criar diretório temporário"
LIMPAR=1
limpa_temp() {
  if [ "$LIMPAR" -eq 1 ] && [ -d "$TEMP" ]; then
    find "$TEMP" -depth -delete
  fi
}
trap limpa_temp EXIT

REGISTROS="$TEMP/candidatas.jsonl"
: > "$REGISTROS"

for ((IDX=0; IDX<TOTAL; IDX++)); do
  ID="${IDS[$IDX]}"
  AVALIACAO_DIR="$TEMP/$ID"
  mkdir -p "$AVALIACAO_DIR"
  cp -- "${ARQUIVOS[$IDX]}" "$AVALIACAO_DIR/texto.md"
  SHA_COPIADO=$(shasum -a 256 "$AVALIACAO_DIR/texto.md" | awk '{print $1}')
  [ "$SHA_COPIADO" = "${SHAS[$IDX]}" ] || die "candidata $ID mudou durante o congelamento"

  jq --argjson autor "${AUTORES[$IDX]}" '
    {
      perfil: (.perfil // "debate_agents_v1"),
      tema: (.tema // "não declarado"),
      publico: (.publico // "leitor geral"),
      formato: (.formato // "texto explicativo"),
      extensao: (.extensao // "não declarada"),
      alvo: (.alvo // .loop.alvo // 8.5),
      piso: (.piso // .loop.piso // 7.0),
      painel_auditoria: (.painel_auditoria // .auditoria.painel // 1),
      redator: $autor,
      escritor: ($autor.cli // "desconhecido"),
      auditor: (.auditor // .avaliador // {cli:"codex"}),
      painel_avaliacao_cega: (.painel_avaliacao_cega // []),
      independencia: (.independencia // {politica:"automatico",falha_de_independencia:"pausar",quorum_minimo_auditoria:1})
    }
  ' "$META" > "$AVALIACAO_DIR/meta.json"

  set +e
  "$AVALIADOR_BIN" "$AVALIACAO_DIR" --cego > "$AVALIACAO_DIR/resumo-cego.json"
  RC=$?
  set -e
  case "$RC" in
    0|10) ;;
    *) die "avaliação cega da candidata $ID falhou com código $RC" ;;
  esac

  VEREDITO="$AVALIACAO_DIR/veredito-cego.json"
  [ -s "$VEREDITO" ] || die "avaliador não gerou veredito cego para $ID"
  jq -e . "$VEREDITO" >/dev/null || die "veredito cego inválido para $ID"

  jq -n --arg id "$ID" --arg arquivo "${CAMINHOS_RELATIVOS[$IDX]}" \
    --arg sha256 "${SHAS[$IDX]}" --arg base_sha256 "${BASES[$IDX]}" \
    --argjson autor "${AUTORES[$IDX]}" --slurpfile avaliacao "$VEREDITO" \
    '{id:$id,arquivo:$arquivo,sha256:$sha256,base_sha256:$base_sha256,autor:$autor,
      estado:"candidato_final",avaliacao_cega:$avaliacao[0]}' >> "$REGISTROS"
done

mkdir -p "$TEMP/diffs"
DIFFS_REGISTROS="$TEMP/diffs.jsonl"
: > "$DIFFS_REGISTROS"
for ((A=0; A<TOTAL; A++)); do
  for ((B=A+1; B<TOTAL; B++)); do
    REL_DIFF="diffs/${IDS[$A]}--${IDS[$B]}.patch"
    DIFF_RC=0
    diff -u "${ARQUIVOS[$A]}" "${ARQUIVOS[$B]}" > "$TEMP/$REL_DIFF" || DIFF_RC=$?
    [ "$DIFF_RC" -le 1 ] || die "falha ao gerar diff entre ${IDS[$A]} e ${IDS[$B]}"
    jq -n --arg candidata_a "${IDS[$A]}" --arg candidata_b "${IDS[$B]}" --arg arquivo "$REL_DIFF" \
      '{candidata_a:$candidata_a,candidata_b:$candidata_b,arquivo:$arquivo}' >> "$DIFFS_REGISTROS"
  done
done
DIFFS_JSON=$(jq -s -c '.' "$DIFFS_REGISTROS")
DIFF_LEGADO=""
if [ "$TOTAL" -eq 2 ] 2>/dev/null; then
  cp "$TEMP/diffs/${IDS[0]}--${IDS[1]}.patch" "$TEMP/diff.patch"
  DIFF_LEGADO="diff.patch"
fi

jq -s --arg modo "$MODO" --arg snapshot_sha256 "${BASES[0]}" --arg visibilidade "$VISIBILIDADE" \
  --arg diff_legado "$DIFF_LEGADO" --argjson diffs "$DIFFS_JSON" '
  {
    modo:$modo,
    visibilidade:$visibilidade,
    status:"aguardando_escolha_humana",
    snapshot_sha256:$snapshot_sha256,
    candidatas:.,
    comparacao: ({diffs:$diffs,mesma_rubrica:true,avaliacoes_cegas:true}
      + (if $diff_legado == "" then {} else {diff:$diff_legado} end)),
    escolha_automatica:false,
    sintese_automatica:false,
    aviso:"Nenhuma candidata é canônica ou aprovada até escolha humana e gates finais do hash selecionado ou sintetizado."
  }
' "$REGISTROS" > "$TEMP/comparativo-final.json"

{
  echo "# Comparação final cega"
  echo
  echo "Estado: aguardando escolha humana. Nenhuma candidata foi escolhida ou mesclada automaticamente."
  echo
  jq -r '.candidatas[] | "- \(.id): nota \(.avaliacao_cega.nota), menor critério \(.avaliacao_cega.menor_subnota), veredito \(.avaliacao_cega.veredito), SHA-256 \(.sha256)"' "$TEMP/comparativo-final.json"
  echo
  echo "Diffs pareados:"
  jq -r '.comparacao.diffs[] | "- \(.candidata_a) × \(.candidata_b): \(.arquivo)"' "$TEMP/comparativo-final.json"
  echo
  echo "A candidata escolhida ou uma síntese solicitada ainda deve passar pelo consenso, avaliação e auditoria do hash final exato."
} > "$TEMP/comparativo-final.md"

mv "$TEMP" "$DESTINO"
LIMPAR=0
trap - EXIT
jq '{status,escolha_automatica,sintese_automatica,snapshot_sha256,candidatas:[.candidatas[]|{id,sha256,nota:.avaliacao_cega.nota,menor_subnota:.avaliacao_cega.menor_subnota,veredito:.avaliacao_cega.veredito}]}' "$DESTINO/comparativo-final.json"
echo "# comparação completa: $DESTINO/comparativo-final.json" >&2
