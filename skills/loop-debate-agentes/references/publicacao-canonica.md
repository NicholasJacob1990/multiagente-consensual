# Publicação canônica controlada

O modo `parecer_apenas` permanece padrão. `publicar_candidata` cria arquivos ou branches separados.
`publicar_canonico` só é habilitado com `publicacao_compartilhada`, lista de publicadores, turno,
`controle_concorrencia = base_sha256`, `gravacao = atomica` e autorização expressa para publicação
direta.

O recibo `publicacao_canonica_v1` deve conter caminhos relativos ao root explícito:

```json
{
  "schema": "publicacao_canonica_v1",
  "autor": "codex-revisor",
  "base_sha256": "<hash do canônico corrente>",
  "canonico_corrente_sha256": "<mesmo hash>",
  "sha256": "<hash do arquivo candidato real>",
  "versao_corrente": 3,
  "nova_versao": 4,
  "versoes_maximas": 20,
  "caminho_canonico": "artefatos/minuta.docx",
  "caminho_candidato": "candidatos/minuta-codex-v4.docx",
  "chave_idempotencia": "run-123:minuta:v4:codex"
}
```

Validar sem gravar:

```bash
python3 scripts/publication_policy.py validate-receipt meta.json recibo.json \
  --root /caminho/exato/do/run
```

Publicar:

```bash
python3 scripts/publication_policy.py publish meta.json recibo.json \
  --root /caminho/exato/do/run \
  --ledger /caminho/exato/do/run/publication-ledger.json
```

O publicador abre lock exclusivo, refaz os hashes dos arquivos reais e compara a base. Antes da
troca, persiste no ledger um registro WAL `prepared`; depois copia a candidata para estágio no mesmo
filesystem, executa `fsync`, troca com `os.replace`, sincroniza o diretório, verifica o hash final e
marca o WAL como `committed` com recibo atestado. Se houver crash entre a troca e o commit, a mesma
chave recupera a transação examinando o hash real. A mesma chave com os mesmos campos é idempotente;
a mesma chave com conteúdo diferente é replay conflitante. Caminho inexistente, fora do root, com
`..` ou symlink falha fechado.

A troca publica uma nova versão, não uma aprovação. O novo hash reabre consenso, painel, gates de
domínio e auditoria. O publicador não pode atuar como auditor independente da própria versão.
