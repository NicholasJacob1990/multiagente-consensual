# Controle de alterações do Word — `legal_word_redline_v1`

Este contrato acrescenta rastreabilidade editorial ao loop jurídico. Ele não cria
outro redator, outro consenso nem outro artefato canônico.

## Resultado após debate e loops

Quando o modo estiver ativo, cada revisão substantiva parte de duas versões DOCX
limpas e congeladas:

```text
minuta-v01-limpa.docx
  → crítica, réplica e revisão
minuta-v02-limpa.docx
  → comparador local
minuta-v02-alteracoes-v01-v02.docx
```

Após o encerramento de todas as tentativas, publique:

| Arquivo | Estado | Relação |
|---|---|---|
| `minuta-final-limpa.docx` | único canônico aprovado | versão exata submetida a consenso, painel e auditoria |
| `minuta-final-com-alteracoes.docx` | derivado não canônico | primeira versão, ou original escolhido, → canônico final |
| `minuta-final-alteracoes-ultima-versao.docx` | derivado não canônico, se houver versão anterior | penúltima versão → canônico final |
| `manifesto-controle-alteracoes.json` | recibo | caminhos, hashes, base, motor e verificações |
| `relatorio-de-alteracoes.md` | recibo legível | resumo do pacote e regra de governança |

Assim, há uma minuta final após todos os debates e loops. A limpa é a versão
juridicamente aprovada; a cópia com alterações mostra como se chegou a ela.
O run pode manter de `minuta-v01-limpa.docx` até `minuta-v20-limpa.docx`.
Como v1 já é a primeira tentativa, isso permite no máximo 19 comparativos
incrementais. Os comparativos não são versões adicionais.

## Configuração

```yaml
controle_alteracoes_word:
  contrato: legal_word_redline_v1
  modo: auto_se_docx_existente   # ativo | auto_se_docx_existente | desativado
  comparador: docxodus_wmlcomparer
  processamento: local_offline
  incremental_por_revisao: true
  comparativo_final_acumulado: true
  base_acumulada: primeira       # primeira | original
  autor_revisoes: consolidador_responsavel
  canonico: limpo
  versoes_maximas_por_artefato: 20
  indisponibilidade: pausar      # nunca simular controle nativo
```

- `primeira`: compara a primeira minuta criada no run com a final aprovada.
- `original`: compara o documento que o usuário forneceu antes do run com a final.
- O comparativo incremental sempre usa a versão limpa imediatamente anterior.
- Se o documento nasceu no run, o primeiro comparativo aparece a partir da v2.
- Detectar alterações de formatação é opt-in; o default concentra-se no conteúdo.

## Motor e validação

O comparador Docxodus roda localmente e grava revisões OOXML nativas (`w:ins`,
`w:del` e equivalentes) reconhecidas pelo Microsoft Word. Os documentos não são
enviados a um serviço externo por essa etapa.

Antes de publicar, o script verifica:

1. as duas entradas são DOCX limpos, sem revisões pendentes;
2. o comparativo não substitui a base nem o canônico;
3. aceitar todas as revisões reproduz o conteúdo visível do canônico limpo;
4. rejeitar todas as revisões reproduz o conteúdo visível da base;
5. uma mudança textual gerou ao menos uma marca de revisão;
6. os hashes e o número de revisões foram gravados no manifesto.

A verificação cobre corpo, tabelas, cabeçalhos, rodapés, notas de rodapé e notas
de fim representadas nas histórias OOXML. Imagens, campos complexos, objetos
incorporados e alterações estruturais incomuns exigem inspeção visual no Word.

## Governança

- Consenso, notas, painel e auditoria aderem somente ao SHA-256 de
  `minuta-final-limpa.docx`.
- A cópia com alterações não recebe aprovação por herança nem pode substituir o
  canônico silenciosamente.
- O nome do autor das revisões identifica o redator ou consolidador responsável.
  Críticos, fontes e decisões permanecem identificados no ledger.
- Aceitação, rejeição ou edição manual parcial no Word cria uma nova versão
  limpa, com novo hash; reexecute os gates aplicáveis e gere novo comparativo.
- O novo hash também consome a próxima versão canônica. Se a cadeia já estiver
  em v20, não criar v21; encerrar como não aprovada ou iniciar outro run somente
  após uma nova configuração explícita, sem reutilizar aprovações anteriores.
- Se não houver aprovação, use `minuta-melhor-versao-nao-aprovada.docx` e não a
  denomine `final`, `aprovada` ou `consensual`.
- Se o runtime estiver indisponível, pause e explique. Não produza destaque,
  cor, tachado ou comentário fingindo ser alteração controlada nativa.

## Comandos do utilitário

O script fica em `scripts/word_redline.py`.

```bash
python3 scripts/word_redline.py doctor --deep
```

```bash
python3 scripts/word_redline.py compare \
  --base minuta-v01-limpa.docx \
  --current minuta-v02-limpa.docx \
  --out minuta-v02-alteracoes-v01-v02.docx \
  --author "Redator Claude"
```

```bash
python3 scripts/word_redline.py finalize \
  --first minuta-v01-limpa.docx \
  --previous minuta-v05-limpa.docx \
  --final minuta-v06-limpa.docx \
  --out-dir entrega \
  --stem minuta \
  --author "Redator Claude"
```

Para usar a base documental fornecida pelo usuário, acrescente `--original` e
`--base-policy original`. Use `--force` somente quando a substituição exata das
saídas do mesmo run for intencional.

## Pedido natural

```text
Ative o controle de alterações do Word. Depois de cada revisão do redator, gere
uma versão limpa e um comparativo incremental com a versão anterior. Ao final de
todos os debates e loops, publique minuta-final-limpa.docx como único canônico e
minuta-final-com-alteracoes.docx comparando a primeira minuta com a versão final
aprovada. A aprovação deve aderir ao hash da limpa. Se eu aceitar, rejeitar ou
editar alterações manualmente, trate o resultado como nova versão e repita os
gates.
```
