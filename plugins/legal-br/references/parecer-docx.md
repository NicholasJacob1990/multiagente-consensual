# Entrega do parecer em `.docx` — padrão institucional

O parecer raramente é entregue em Markdown. Ele é juntado ao processo (SEI) como
**documento formatado**, e a formatação é conferida por quem recebe. Esta
referência fixa o padrão e o caminho para produzi-lo sem trabalho manual.

> **Regra do plugin:** parecer destinado a juntada sai em `.docx` formatado e com
> **numeração automática de parágrafos** — a do Word (campo de lista), nunca
> "1." digitado no texto. Numeração digitada quebra assim que se insere ou
> remove um parágrafo, e revisão de parecer é feita inserindo parágrafos.

## Padrão de página (GENSU/GENES — CODEMGE)

| Item | Valor |
|---|---|
| Fonte do corpo | Times New Roman 12 |
| Fonte das notas | Times New Roman 10 |
| Entrelinha | 1,5 |
| Espaço depois | 6 pt |
| Margens (sup./dir./inf./esq.) | 3 / 2 / 3 / 2 cm |
| Alinhamento | justificado |
| Numeração | automática, número na margem e texto recuado 1,25 cm (tab) |

Perfil de redação e estrutura da GENES: `references/perfil-parecer-genes.md`. O parecer
modelo de formatação consultiva usou corpo 10,5, entrelinha 1,5,
recuo de 2 cm e numeração digitada, espelhando o rascunho do usuário, e foi gerado por
`scripts/parecer_genes_estilo.py`. A tabela acima continua sendo o padrão do plugin;
confirme com o usuário qual adotar antes de formatar.

Outra instituição: ajuste o dicionário `PADRAO` no topo de
`scripts/parecer_docx.py`. **Antes de formatar, peça ao usuário um parecer
anterior aprovado e espelhe a formatação dele** — o padrão da casa é o que já
foi aceito, não o que está escrito em manual.

## Estrutura que a numeração automática pressupõe

```
PARECER <ÓRGÃO> Nº ___/AAAA          ]
Processo nº ...                      ]  cabeçalho — sem número
Interessada: ... · Origem: ...       ]
EMENTA: ...                          ]  sem número
I — RELATÓRIO                        ]  títulos de seção — sem número
   <parágrafos numerados>
...
X — CONCLUSÃO
   Primeiro. ...  Segundo. ...        <- conclusões numeradas como parágrafos
É o parecer, salvo melhor juízo.     ]
<assinatura / cargo / gerência>      ]  fecho — sem número
REFERÊNCIAS                          ]  título — sem número
   <cada referência é um parágrafo numerado, uma por número>
```

O script reconhece esses marcadores pela regex `NAO_NUMERA`. Se a casa usa outros
rótulos ("PARECER Nº", "É o que me parece"), acrescente-os lá.

## Comandos

```bash
S="${CLAUDE_PLUGIN_ROOT}/scripts/parecer_docx.py"

python3 "$S" check                        # python-docx + pandoc + padrão vigente
python3 "$S" converter parecer.md parecer.docx   # pandoc + formatar + numerar
python3 "$S" formatar parecer.docx        # só fonte/margens/espaçamento
python3 "$S" numerar  parecer.docx        # só numeração automática (idempotente)
python3 "$S" ementa   parecer.docx --max 80          # confere o tamanho
python3 "$S" ementa   parecer.docx --nova "EMENTA: ..."   # troca preservando o negrito
python3 "$S" nota     parecer.docx --par 137 --texto "TCE-MG, ... Disponível em: ..."
python3 "$S" auditar  parecer.docx        # relatório JSON — rode antes de entregar
```

Toda escrita gera `parecer.bak-AAAAMMDD-HHMM.docx` ao lado. `numerar` e
`formatar` são idempotentes: rodar de novo não duplica nada.

## O que `auditar` pega

Os defeitos que revisor humano cobra e que passam despercebidos na leitura:

- **ementa acima do teto** (padrão 80 palavras)
- **citação de precedente sem relator, órgão julgador ou data** — o defeito nº 1
  das listas de referências
- **typos** de troca de teclado e francesismos (`Entranto`, `relative`,
  `a confirmer`, `hiposuficiente`)
- **frase truncada** (parágrafo terminado em vírgula)
- **parágrafos de corpo sem numeração** — tipicamente os que o usuário
  acrescentou depois, editando o arquivo por fora
- **contagem de notas de rodapé no corpo**, para conferir que uma edição em
  massa não apagou nenhuma

## Armadilhas de OOXML (custaram tempo; não repita)

1. **`numPr` mora dentro de `pPr`.** `paragrafo._p.find(qn('w:numPr'))` devolve
   `None` sempre e faz a auditoria mentir "0 numerados". Use `.//w:numPr`.
2. **Ordem do `CT_PPr` é fixa:** `pStyle` → `numPr` → `tabs` → `spacing` → `ind`.
   Inserir `numPr` fora de ordem gera arquivo que o Word recusa.
3. **NBSP (`\xa0`)** aparece no texto vindo do Word e quebra qualquer
   `str.replace` que você escreveu com espaço normal. Normalize antes de casar.
4. **Nota de rodapé não persiste** se você editar o objeto XML da part em
   memória: `save()` não regrava `footnotes.xml`. É preciso reescrever o zip.
5. **Ao reescrever um parágrafo**, preserve o `rPr` do primeiro run — é o que
   segura o negrito da ementa e a fonte herdada.
6. **Ao inserir parágrafo**, clone o `pPr` do vizinho (herda numeração e
   espaçamento) e remova `w14:paraId`/`w14:textId`, que devem ser únicos.

## Edição concorrente

O usuário costuma abrir o `.docx` no Word e editar **entre** duas chamadas suas.
Portanto:

- **releia o arquivo antes de cada edição** — nunca edite com base no que você
  gravou da última vez;
- **faça backup a cada rodada**, com hora no nome;
- índice de parágrafo do `python-docx` **não é** o número que o Word mostra
  (títulos e ementa não contam). Ao receber "o parágrafo 144 fala de X", localize
  **pelo texto**, não pelo índice.

## macOS: `Interrupted system call` em `~/Documents`

Se `stat` funciona mas `cp`/`unzip`/`open` falham com `Interrupted system call`
em `~/Documents`, `~/Desktop` ou `~/Downloads`, é **TCC** (permissão de pastas
protegidas), não nuvem nem lock do Word. Diagnóstico em uma linha:

```bash
head -c 20 ~/Aplicativos/QUALQUER.txt   # fora do TCC: funciona
head -c 20 ~/Documents/QUALQUER.txt     # dentro do TCC: Interrupted system call
```

Correção: Ajustes do Sistema › Privacidade e Segurança › **Acesso Total ao Disco**
→ ativar o app hospedeiro (Terminal, iTerm, VS Code) e **reiniciá-lo**.
Contorno imediato: trabalhar com uma cópia fora dessas pastas.
