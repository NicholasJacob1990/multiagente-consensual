# Requerimento informativo ao Registro de Imóveis (anexo de parecer)

Modelo de requerimento administrativo de certidões, buscas e esclarecimentos ao
Ofício de Registro de Imóveis, para acompanhar parecer como anexo nomeado
(ex.: "Anexo Único: Minuta de Requerimento Administrativo de Certidões, Buscas e
Esclarecimentos"). Serve quando o parecer conclui que faltam elementos
registrais para definir a situação de um imóvel: duplicidade de descrição,
ausência de nota de transferência, cadeia de títulos interrompida ou
divergência de área.

O requerimento é **informativo**. Não é título, não pede baixa, não afirma
titularidade e não substitui a apresentação formal de título para registro ou
averbação.

## Regras

1. **Sem número de documento interno.** O destinatário é externo: não citar
   número de documento ou processo SEI, de nota técnica ou de despacho interno.
   Identificar cada documento pelo que o registrador reconhece: matrícula,
   transcrição, registro, livro, folha, protocolo, CNM, data e cartório de
   origem do título.
2. **Origem de cada dado cadastral.** CNPJ, sede, representante e dados do
   imóvel vêm de algum lugar: dossiê do caso, informação do usuário ou cadastro
   público (Receita Federal, Junta Comercial, certidão). Anotar a origem na
   nota de entrega do parecer e listar o que falta conferir (ex.: "sede
   conforme cadastro da Receita em [data]; conferir com o estatuto vigente").
   Dado sem origem fica entre colchetes.
3. **Nada que a conclusão desaconselhe.** Antes de entregar, confrontar cada
   pedido com a conclusão do parecer. Se o parecer desaconselha baixa
   patrimonial, prenotação como título ou afirmação de titularidade, o
   requerimento não pede baixa, não se apresenta como título e não diz que a
   requerente "é proprietária". Pedido incompatível com a conclusão é defeito
   bloqueante.
4. **Tabela de assentos como base.** Rodar
   `scripts/extrair_assentos.py CERTIDAO.md --md` (e `--quadra NN` quando for
   loteamento) e usar a tabela para (a) a linha de Referência (matrícula, livro,
   folha, CNM, protocolo do ato) e (b) o contraste de notas de transferência
   na seção de fatos. Toda linha usada é conferida na imagem da certidão,
   sobretudo as marcadas "ilegível (conferir imagem)", as áreas e os números
   com "[conferir nº na imagem]".
5. **Fatos, não conclusões.** Descrever o que consta de cada assento ("consta
   sem nota de transferência"), sem qualificar ("não foi alienado"). Hipótese
   (de área, de filiação, de erro) é apresentada como hipótese, com o que a
   confirmaria.
6. **Pedidos separados por natureza.** Cada alínea pede uma espécie de ato
   (certidão, esclarecimento, cópia, orientação, ato de ofício, exigência), para
   que a serventia possa atender, cobrar e recusar cada uma separadamente.
7. **Fundamentos conferidos.** Dispositivos e normas estaduais são verificados
   na fonte vigente na data do requerimento (`fontes-web.md`); o modelo indica
   onde costumam estar, não dispensa a conferência.

## Campos

`[OFÍCIO]` serventia (ex.: "2º Ofício de Registro de Imóveis"); `[COMARCA]`,
`[UF]`; `[MATRÍCULA]` nº da matrícula principal; `[LIVRO/FOLHA]`; `[CNM]`
Código Nacional de Matrícula; `[PROTOCOLO]` protocolo e data do ato
referido (ex.: R-1, loteamento); `[ATO]` (ex.: R-1); `[LOTES]`, `[QUADRA]`,
`[LOTEAMENTO]`; `[MATRÍCULA CONEXA]` outra matrícula ou transcrição em que o
imóvel figura; `[REGISTRO ANTERIOR]`; `[REQUERENTE]`, `[CNPJ]`, `[SEDE]` (com
origem anotada, regra 2); `[TITULAR INSCRITO]` quem consta no registro;
`[TÍTULOS]` títulos da cadeia (natureza, data, livro, folhas, cartório);
`[ÁREA REGISTRADA]`, `[ÁREA DO TÍTULO]`; `[NORMA ESTADUAL]` código de normas
da Corregedoria-Geral de Justiça do Estado e os artigos sobre exigências e
dúvida; `[DATA]`; `[REPRESENTANTE]`.

## Modelo

**Endereçamento**

> ILUSTRÍSSIMO(A) SENHOR(A) OFICIAL(A) DO [OFÍCIO] DA COMARCA DE [COMARCA] –
> ESTADO DE [UF]

**Referência** (montada com a tabela de `extrair_assentos.py`)

> Referência: Lotes [LOTES] da quadra [QUADRA] do loteamento "[LOTEAMENTO]".
> Matrícula nº [MATRÍCULA] ([LIVRO/FOLHA]; CNM [CNM]), [ATO] (Protocolo nº
> [PROTOCOLO]), e [MATRÍCULA CONEXA] ([LIVRO/FOLHA]).

**Qualificação e fundamento**

> [REQUERENTE], [natureza jurídica], inscrita no CNPJ sob o nº [CNPJ], com sede
> [SEDE], por seu representante legal ao final identificado, vem, respeitosamente,
> à presença de Vossa Senhoria, com fundamento nos arts. 16, 17 e 19 da Lei nº
> 6.015/1973, requerer a expedição de certidões, a realização de buscas e a
> prestação de esclarecimentos sobre os imóveis em referência, pelas razões a
> seguir expostas.

Fundamento, em uma frase cada se o caso pedir: o oficial é obrigado a lavrar
certidão do que lhe for requerido e a fornecer às partes as informações
solicitadas (art. 16); qualquer pessoa pode requerer certidão sem informar ao
oficial o motivo ou o interesse do pedido (art. 17); a certidão de inteiro teor
é extraída por meio reprográfico ou eletrônico (art. 19, § 1º).

**Interesse, sem afirmar titularidade**

> A Requerente é interessada na apuração [do acervo imobiliário / da situação
> registral] [descrição neutra da relação com o imóvel]. Este pedido não afirma
> que ela seja, hoje, titular de direito sobre [os lotes], nem contém ato de
> disposição: destina-se a reunir os elementos registrais necessários para
> definir a situação jurídica dos imóveis.

**Fatos, em ordem**

Um parágrafo por bloco, nesta sequência:

1. *O que consta na matrícula principal.* "No [ATO] da Matrícula nº [MATRÍCULA]
   (Protocolo nº [PROTOCOLO]), que registrou [o loteamento], os lotes [LOTES]
   da quadra [QUADRA] permanecem em nome de [TITULAR INSCRITO], com [ÁREA
   REGISTRADA] cada, sem nota de transferência."
2. *Contraste de notas de transferência.* "Os demais lotes da mesma quadra
   receberam remissão ao respectivo assento: os lotes [..], ao [assento de
   destino]; os lotes [..], à [assento]; …" — copiar da coluna "Nota de
   transferência" da tabela, já conferida na imagem. Linha ilegível não vira
   "sem nota": diga que a leitura é incerta e peça certidão legível.
3. *O que consta na outra matrícula ou transcrição.* "Os lotes [LOTES], no
   entanto, também estão descritos na [MATRÍCULA CONEXA], em que figuram [com
   origem distinta / em nome de …]. Essa matrícula registra [atos relevantes,
   em ordem: adjudicação, venda, transmissões, indisponibilidades averbadas sob
   os nºs AV-..]. A coexistência das duas descrições exige o confronto dos
   títulos, das áreas e dos direitos, sem que se presuma simples erro de
   escrituração."
4. *Cadeia de títulos.* "Para esse confronto, interessam, em especial: [TÍTULOS,
   em ordem cronológica, cada um com natureza, data, cartório, livro e
   folhas]." Ressalvas de leitura incerta ficam no próprio item ("segundo a data
   indicada por …").
5. *Área como hipótese.* "Há, ainda, divergência de área: os títulos de origem
   atribuem [ÁREA DO TÍTULO] a cada lote, e o loteamento, [ÁREA REGISTRADA]. A
   diferença é compatível com [hipótese], hipótese que depende de confirmação
   por títulos, planta, memorial e aprovação municipal."

**Natureza informativa**

> O requerimento é informativo. Não formaliza alienação, renúncia, resgate ou
> baixa, nem equivale à apresentação de título para registro ou averbação, que,
> se vier a ser o caso, será objeto de pedido próprio, instruído com o título e
> os documentos exigíveis. As respostas servirão à instrução interna da
> Requerente e não implicarão, por si, baixa patrimonial ou contábil.

**Pedidos** (uma alínea por natureza; suprimir as que o caso não pedir)

> Ante o exposto, observadas a atribuição da Serventia e os pressupostos de cada
> providência, a Requerente solicita:
>
> a) o recebimento deste requerimento, com a indicação prévia dos emolumentos e
> das despesas legalmente exigíveis;
>
> b) certidões de inteiro teor, atualizadas e legíveis, da Matrícula nº
> [MATRÍCULA], da [MATRÍCULA CONEXA], do [REGISTRO ANTERIOR] e de [outros
> assentos da cadeia], inclusive das fichas manuscritas, com a indicação dos
> assentos antecedentes, dos títulos aquisitivos, dos ônus e das remissões;
>
> c) esclarecimento sobre: (i) se os títulos do [REGISTRO ANTERIOR] abrangem os
> lotes [LOTES] e qual direito [TITULAR INSCRITO] adquiriu sobre eles, sem
> inferi-lo da contiguidade dos imóveis nem da ausência de remissão; (ii) a
> filiação entre a [MATRÍCULA CONEXA] e a Matrícula nº [MATRÍCULA]; (iii)
> [divergência de dado registral, ex.: data de abertura diferente entre
> reproduções]; e (iv) a razão de o [ATO] da Matrícula nº [MATRÍCULA] não trazer,
> para os lotes [LOTES], nota de transferência semelhante à dos demais lotes da
> quadra [QUADRA];
>
> d) cópia dos documentos arquivados relativos a [título] e às ordens de
> indisponibilidade ou restrições averbadas na [MATRÍCULA CONEXA] ([AV-..]),
> conforme as regras de acesso, preservados o alcance dessas restrições, seu
> transporte e as comunicações devidas, ressalvada ordem judicial contrária;
>
> e) esclarecimento escrito sobre a orientação verbal, prestada à equipe da
> Requerente, de que [providência indicada verbalmente, ex.: nova escritura],
> com a indicação da modalidade, do objeto, da causa, do direito e dos possíveis
> outorgantes. Pede-se que a resposta distinga [aquisição atual, resgate,
> alienação de direito, extinção anterior documentada, correção do título e
> saneamento do registro], para evitar a repetição de transmissão ou a cobrança
> de direito cuja aquisição ou extinção venha a ser demonstrada;
>
> f) comprovados os pressupostos, a prática das averbações de ofício previstas
> no art. 440-BF ou, havendo duplicidade com contradição ou dúvida de
> titularidade, das notícias e remissões do art. 440-BB, II, "a", do Código
> Nacional de Normas da Corregedoria Nacional de Justiça – Foro Extrajudicial
> (Provimento nº 149/2023 do Conselho Nacional de Justiça), sem baixa automática
> nem renúncia e preservados os demais imóveis, os direitos dos titulares
> inscritos e as restrições averbadas; eventual autotutela observará o art.
> 440-BG do mesmo Código;
>
> g) a indicação fundamentada dos títulos, documentos técnicos, participações e
> procedimentos necessários para eventual retificação ou averbação. Havendo
> apresentação formal e prenotação de título com qualificação negativa,
> requer-se que as exigências sejam formuladas por escrito e de uma só vez (art.
> 198 da Lei nº 6.015/1973 e [NORMA ESTADUAL]), assegurado o requerimento de
> suscitação de dúvida, quando cabível.

Cuidados por alínea:

- **(c)** pergunta, não afirma. Cada item é uma dúvida verificável no acervo
  da serventia.
- **(e)** só se houve orientação verbal; registrar quem a recebeu e quando, na
  nota de entrega, não no requerimento.
- **(f)** é condicional ("comprovados os pressupostos"): não pede baixa nem
  cancelamento, e os dispositivos do Código Nacional de Normas são conferidos
  no texto compilado vigente.
- **(g)** exigência escrita e de uma só vez é direito de quem **prenotou
  título**; sem título prenotado, a alínea pede só a indicação do que seria
  necessário. Não transformar o requerimento em prenotação.

**Documentos**

> Instruem o requerimento: (i) estatuto social e atos de eleição ou de
> designação de quem representa a Requerente; (ii) documento de identificação
> do representante; e (iii) cópias dos títulos e das certidões já obtidos, em
> especial [certidões com data de emissão, reproduções, títulos].
> [Relacionar apenas os documentos efetivamente anexados, distinguindo
> certidões, visualizações e cópias históricas.]

**Fecho**

> Nestes termos, pede deferimento.
>
> [CIDADE]/[UF], [DATA].
>
> [REQUERENTE]
>
> [NOME E QUALIDADE DO REPRESENTANTE HABILITADO, CONFORME A DOCUMENTAÇÃO
> EFETIVAMENTE ANEXADA]

## Conferência antes de entregar

- [ ] Nenhum número SEI ou de documento interno no texto do requerimento.
- [ ] Referência e contraste de notas batem com a tabela de
      `extrair_assentos.py` **e** com a imagem da certidão.
- [ ] Cada dado cadastral tem origem anotada na nota de entrega; os sem origem
      seguem entre colchetes.
- [ ] Nenhum pedido contraria a conclusão do parecer (baixa, prenotação como
      título, afirmação de titularidade).
- [ ] Alíneas sem objeto no caso foram suprimidas e as restantes, renumeradas.
- [ ] Dispositivos (Lei nº 6.015/1973, Código Nacional de Normas, norma
      estadual) conferidos na redação vigente.
- [ ] Lista de documentos corresponde ao que de fato será anexado.
- [ ] **Sem instrução editorial na peça.** Nada de "[Relacionar apenas os documentos efetivamente anexados]" dentro do requerimento: a conferência pré-protocolo vai ao plano de ação do parecer. `conferir_orfaos.py` bloqueia colchetes com instrução; "[data]" e a identificação do representante são só informados.
- [ ] **Cada pedido tem lastro no parecer.** Dado específico pedido ao cartório (divergência de data, livro, inscrição) precisa aparecer, ao menos em uma linha, na fundamentação ou na lista de diligências; depois de condensar o parecer, confira item por item.
