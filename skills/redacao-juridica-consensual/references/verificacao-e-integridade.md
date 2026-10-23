# Verificação de precedentes e integridade do documento

Referência de domínio da `redacao-juridica-consensual`. Dois portões que reprovam versão jurídica
independentemente de nota: **precedente não verificado** e **conteúdo perdido na edição**.

## 1. Portão de verificação de precedentes

Nenhuma citação de julgado entra no canônico sem conferência em **fonte primária**. Modelo que
cita de memória inventa relator, turma e data com fluência — e o erro só aparece no controle
externo.

O que conferir, para cada julgado citado: classe, número e UF; relator; órgão julgador; data de
julgamento; data e veículo de publicação (**DJe e DJEN não são a mesma coisa**); e, sobretudo, se
a ementa diz o que o texto lhe atribui.

**STJ.** O SCON é protegido por Cloudflare *Managed Challenge* — não é captcha, não há desafio a
resolver, e serviço de resolução não ajuda. Um navegador real passa em segundos. Query direta:

```
https://scon.stj.jus.br/SCON/pesquisar.jsp?b=ACOR&livre=((RESP.clas.)+e+@num%3D"NUMERO")+ou+(RESP+adj+"NUMERO").suce.&O=JT
```

Se a classe não for `RESP` (AgInt, AREsp, EDcl), a query por classe falha: buscar só
`livre="NUMERO"`. Súmulas: trocar `b=ACOR` por `b=SUMU` e usar `livre=@num="619"`.

**STF.** Pede apenas User-Agent. Processo por classe e número em
`portal.stf.jus.br/processos/listarProcessos.asp?classe=ADPF&numeroProcesso=828`; súmula em
`jurisprudencia.stf.jus.br/pages/search/seq-sumulaNNN/false`.

**Pareceres da AGE/MG.** Padrão de URL previsível:
`advocaciageral.mg.gov.br/wp-content/uploads/<ano>/<mês>/Parecer-Juridico-<numero>.pdf`.

**Armadilhas medidas em uso real.** Um precedente pode enunciar a tese favorável no item 1 e, no
caso concreto, **decidir em sentido contrário** — cite pela tese, jamais como se o resultado
tivesse sido favorável. Um acórdão citado por dois agentes "em sentidos opostos" costuma significar
que nenhum dos dois o leu. E vale conferir a **natureza jurídica das partes** antes de acusar erro:
num caso, quatro de cinco cadeiras afirmaram que a consulente era sociedade de economia mista; o
cadastro da Receita dizia empresa pública, e o texto original estava certo.

Registre no dossiê o que foi **conferido em fonte primária** e o que é apenas **pista a verificar**.
Cadeira que cita pista sem confirmar tem a citação rejeitada, não o parecer inteiro.

## 2. Portão de integridade — o conteúdo não pode evaporar

Edição em série sobre DOCX perde texto sem avisar. Depois de qualquer rodada de cortes, movimentação
entre seções ou rebaixamento de parágrafos para nota, **auditar o documento contra a versão
anterior** antes de declarar a versão pronta.

Método que funciona: extrair os parágrafos das duas versões (corpo **e** notas, com as exclusões já
aplicadas) e, para cada parágrafo da versão antiga, medir a fração de seus 4-gramas presente na
versão nova. Cobertura baixa é candidata a perda. Classifique cada achado em três categorias e
relate ao usuário: **saiu por decisão dele**, **foi reformulado** (mesma substância, outras
palavras), **evaporou**.

Causas recorrentes, todas observadas:

- **Rebaixar parágrafo para nota** deixando no corpo uma frase-resumo que não cobre tudo o que o
  parágrafo dizia. Perde-se argumento, ressalva e dispositivo.
- **Excluir o trecho que ancorava uma nota** deixa a nota **órfã**: definida no arquivo, sem chamada
  no corpo. O Word simplesmente não a mostra. Auditar sempre `notas definidas` × `chamadas vivas`.
- **Remover o parágrafo que citava uma obra** derruba a entrada correspondente da bibliografia.
- **Consolidar notas em série** produz o oposto do problema: uma nota de 800 palavras, que ocupa
  páginas. Nenhuma nota deveria passar de ~150 palavras; acima disso, o conteúdo volta ao corpo ou
  se divide.
- **Substituir um parágrafo cujo texto está partido em vários runs** falha em silêncio quando a
  busca é por string exata.

Verificações baratas ao fim de cada versão: parágrafos duplicados (uma substituição malfeita deixa
a versão antiga viva); notas órfãs e chamadas sem nota; parágrafos que perderam a numeração ao
serem movidos; e mais de uma chamada de nota no mesmo parágrafo, que aparece ao leitor como uma
fileira de números soltos.

## 3. Gotchas do OOXML com controle de alterações

Colhidos em produção, todos já causaram documento corrompido:

- **`<w:pPr>` aninhado.** Um `<w:pPrChange>` contém outro `<w:pPr>` dentro. Regex não guloso
  `<w:pPr>.*?</w:pPr>` casa o fechamento **interno** e trunca o parágrafo. Extrair contando
  aninhamento.
- **Espaço antes da barra.** A referência de nota é `<w:footnoteReference w:id="34" />`, com espaço.
  Padrão `w:id="34"/>` não casa e a remoção falha calada.
- **Buscar parágrafo pelo texto bruto** encontra o que já está excluído (`<w:delText>`) e a operação
  vira no-op. Buscar pelo **texto vivo**: remover os blocos `<w:del>` antes de comparar.
- **Offsets calculados antes de modificar a string.** Fazer numa passada só:
  `doc[:m.start()] + novo + doc[m.end():]`.
- **`<w:del>` dentro de `<w:ins>`** é normal em documento já revisado. Excluir texto inserido exige
  `<w:ins><w:del><w:r><w:delText>`, não substituir o `<w:ins>`.
- **`<w:r>` com atributos** (`<w:r w:rsidRPr="...">`): usar `<w:r[ >]` no padrão.
- **`numPr` vive dentro de `pPr`**: procurar `.//w:numPr`, nunca no filho direto.
- **Parágrafo novo herda o `pPr` do antigo**, mas sem `pPrChange` e sem `rPr` — do contrário
  carrega a marcação de revisão anterior e perde a numeração.

Valide o XML **após cada operação**, não ao final: `xml.dom.minidom.parseString`. Item que quebre o
XML é descartado e o documento segue íntegro. Faça backup antes de cada lote e restaure do backup
ao primeiro sinal de corrupção — reparar XML quebrado à mão custa mais que refazer.

**Peso do arquivo.** Marcações acumuladas travam o Word: mil e duzentas revisões em quatrocentos
parágrafos levaram o `document.xml` a 489 KB e o editor a engasgar. Entregue sempre **duas** saídas —
a versão com marcas, para conferência, e a limpa, para trabalhar. Assine as revisões com autor
distinto por origem (`"<Modelo> (revisão de redação)"`), para que o usuário saiba de quem é cada
alteração ao aceitar ou rejeitar.

## 4. Portão de texto integral, varredura e trechos travados

**Texto integral antes de afirmar ausência ou alcance.** Não afirmar que um dispositivo não existe,
não tem parágrafos ou incisos, não alcança certo caso ou "nada diz" sobre um tema com base em
resumo, ementa, dossiê ou memória. Ler o artigo inteiro na fonte primária; o adendo gerado por
`scripts/extrair_adendo.py` traz o texto integral de cada artigo citado justamente para isso. Já
ocorreu de o dossiê resumir um parágrafo sem os incisos e de a minuta afirmar, por isso, que ele não
os tinha. Afirmação de inexistência que o texto integral desmente reprova a versão.

**Níveis de acesso à fonte.** Distinguir: fonte integral conferida; reprodução literal recebida
(permite conferir a fidelidade da afirmação, não declarar acesso atual ao original); mera remissão; e
ausência no material recebido. Nenhuma das três últimas prova, sozinha, que o dispositivo foi
inventado; nenhuma sustenta, sozinha, emenda de mérito. Quando o usuário fechar as fontes, respeitar o
fechamento e dizer o que ficou sem conferência. A identificação é específica: nome do documento e/ou ID
SEI ou folha dos autos, versão ou data e dispositivo ou localizador. Quando o conteúdo de uma fonte
mudar sem mudar o nome do arquivo, o hash muda, e todo auditor recebe o adendo atualizado.

**Vista atual do documento.** Em DOCX com controle de alterações, avaliar o texto com as alterações
aceitas; texto excluído é histórico, não cláusula vigente. Crítica que depende de trecho excluído é
rejeitada contra a vista atual e preservada só como histórico. Conferir que o derivado (DOCX, PDF)
corresponde ao canônico; igualdade de texto não prova a renderização.

**Pré-auditoria antes de cada auditoria por modelo.** Rodar `scripts/pre_auditoria_parecer.py`
(com `--perfil` quando houver). Ele bloqueia numeração quebrada, parágrafo acima do limite, fecho
ausente, remissão a parágrafo inexistente ou ao próprio parágrafo, marcador solto fora da
assinatura, rótulos da conclusão e linhas de assinatura ausentes; e alerta para julgado citado em
mais de um parágrafo, frases quase iguais, afirmações de não verificação possivelmente superadas
e previsões sem cautela. Corrigir os bloqueantes antes de gastar a auditoria.

**Varredura depois de inserções e renumeração.** Todo acréscimo tardio — vindo de auditor, de
minuta concorrente ou do usuário — é varrido contra repetição (o mesmo precedente ou a mesma
norma com a mesma função em outro parágrafo) e contradição (outro parágrafo que diga o
contrário, ou dê a mesma consequência a hipóteses que o texto distingue). Rodar a pré-auditoria com
`--anterior <versão anterior>`: ela lista os parágrafos novos e alterados, que são os que exigem
leitura, e acusa remissões que deixaram de apontar para o parágrafo certo depois da renumeração.
Renumerar sempre por script, com o mapa antigo → novo aplicado às remissões, e nunca à mão. Com
`--anterior`, a pré-auditoria aponta também palavras de alcance acrescentadas ou retiradas, ressalvas
perdidas e frases da versão anterior sem correspondente: reformulação legítima ou conteúdo que
evaporou, a classificar no portão de integridade.

**Achados entre rodadas.** Registrar os achados de cada auditoria em `achados.py` (motor). Achado
resolvido não é reaberto pela mera repetição da crítica: exige regressão, fonte nova ou falha
identificada na solução. "Sem novas melhorias materiais" é resultado válido de uma auditoria.

**Trechos travados.** Texto ditado ou aprovado expressamente pelo usuário (metodologia,
conclusões que ele fixou, fecho, assinatura) vai para um `travados.json`
(`[{"id": ..., "paragrafo": N, "texto": "..."}]`). A pré-auditoria reprova a versão em que um trecho
travado mudou, e o modo de emendas recusa emenda sobre ele. Se um auditor objetar a trecho travado,
a objeção é levada ao usuário como dissenso; o texto só muda com nova autorização dele.
