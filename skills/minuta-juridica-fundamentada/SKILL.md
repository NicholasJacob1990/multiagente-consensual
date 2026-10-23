---
name: minuta-juridica-fundamentada
description: "Produzir e reescrever minutas completas de parecer jurídico, petição e recurso no direito brasileiro, a partir dos fatos, documentos e objetivo do usuário, com fundamentação rastreável e revisão incorporada. Use quando o resultado pedido for a própria minuta. Para somente avaliar ou comparar versões, usar auditoria-juridica-de-minutas; produção por consenso pode ser composta com Redação Jurídica Consensual."
---

# Minuta jurídica fundamentada

Entregar o texto integral da minuta solicitada, adequado ao destinatário e ao efeito pretendido. Um roteiro, lista de teses, pesquisa ou relatório de auditoria não substitui a minuta. A redação direta é o padrão; a invocação desta skill não inicia chamadas a outros agentes.

## Definir o produto com o contexto disponível

Reaproveitar documentos, escolhas e autorizações da conversa. Identificar objeto, destinatário, posição representada, resultado pretendido, jurisdição, fase e formato. Havendo modelo ou minuta, respeitar sua função e suas convenções úteis. Não presumir que o nome `final` identifica a versão vigente.
- **Parecer, nota ou orientação consultiva:** ler [parecer](references/parecer.md). Responder às questões e oferecer conclusão operacional, com premissas e condições. Em parecer da GENES/DIJUR (Codemge e Codemig), ou quando o usuário pedir "o estilo do rascunho", aplicar também o [perfil GENES](references/perfil-parecer-genes.md): prosa contínua com parágrafos numerados em sequência, sem informações soltas, até 15 páginas, fecho "sob censura" e auditoria final só com o Gemini 4 Argon quando pedida.
- **Petição ou recurso de parte:** ler [petição](references/peticao.md). Definir instrumento e construir ligação entre fatos, fundamentos, provas e pedidos.
- **Consenso ou trabalho multiagente solicitado:** ler [composição](references/composicao.md) e usar o contrato da Redação Jurídica Consensual disponível. O pedido de dois documentos, por si só, não exige vários agentes.
- **Somente auditoria:** encaminhar à skill correspondente, se disponível. Minuta de decisão, sentença ou voto demanda a estrutura imparcial própria, disponível na Redação Jurídica Consensual; não adaptar automaticamente a defesa de uma parte.

Perguntar apenas por lacuna que impeça decidir matéria essencial, como qual parte representar ou qual ato impugnar quando existam alternativas incompatíveis. Continuar o trabalho independente. Dados acessórios ausentes recebem marcadores específicos, como `[INFORMAR NÚMERO DO PROCESSO]`; não bloquear toda a redação por qualificação ou assinatura incompleta. Se uma lacuna puder alterar a conclusão ou o cabimento, explicitar a dependência e produzir o trecho seguro, sem disfarçar a incompletude. Não repetir questionário já respondido.

## Construir a base verificável

Ler os documentos relevantes antes de formular a tese. Registrar, em escala proporcional ao caso, uma matriz de trabalho: questão → fato e localizador → alcance da prova → norma/fonte → objeção → conclusão ou pedido. A matriz orienta a redação; só incluí-la na entrega se for útil ou pedida.

- Distinguir relato da parte, documento, admissão limitada, inferência e premissa não confirmada. Separar emissão, envio, recebimento, publicação, juntada e produção de efeitos. Não transformar protocolo em deferimento nem silêncio em concordância sem fundamento.
- Conferir normas na fonte oficial, com redação aplicável à época e ao território. Conferir também se o dispositivo trata mesmo da matéria a que está sendo chamado: artigo inserido por lei posterior pode versar tema inteiramente diverso do que o número sugere. Examinar regras locais quando relevantes, sem transpor automaticamente precedente de outro tribunal ou regime jurídico.
- Ao pesquisar pelo Jurisbase, seguir [pesquisa no Jurisbase](references/pesquisa-jurisbase.md): conferir a cobertura da fonte antes de qualquer conclusão negativa, tratar `jurisbase_coletar` como providência e não como pré-requisito, não suspender a minuta à espera da coleta, e exigir dos subagentes linha de evidência em vez de conclusão.
- Pesquisar jurisprudência pertinente ao problema, incluindo objeções relevantes. Conferir identificação, órgão, datas, contexto fático, fundamento decisivo, resultado e força do precedente no material efetivamente acessado. Distinguir aplicação direta, analogia e distinção. Não há quantidade mínima de julgados, citações ou páginas.
- Distinguir inteiro teor, ementa/trecho oficial, registro indexado e citação indireta. Link genérico, índice ou resposta de outro agente não prova leitura do acórdão. Não reconstruir trecho, número, relator ou data a partir de memória; omitir o dado desconhecido ou marcar a verificação pendente. Uma ementa oficial pode sustentar somente o que ela efetivamente informa.
- Usar conectores e bases disponíveis conforme o pedido, preferindo fontes primárias para confirmar afirmações jurídicas. Consultar acervo pessoal ou doutrina quando acrescentarem fundamento pertinente, sem obrigar busca doutrinária em toda peça. Relatórios anexados e respostas de modelos são pistas, não autoridade jurídica.
- Se o usuário limitar as fontes ou vedar pesquisa externa, respeitar o escopo e indicar o que depende de conferência. Em exercício fictício, usar apenas as premissas fornecidas e identificar a simulação. Ausência de acesso não prova inexistência nem superação de uma tese.

Precedente adverso relevante é material de trabalho, não risco a ocultar. Quando existir e for próximo, enfrentá-lo por distinção explícita é mais forte do que esperar que a parte contrária o traga.

Quando a conferência revelar erro em documento **já protocolado**, dizer isso com a mesma clareza com que se relata erro na minuta em preparo, separando o que ainda é alcançável por peça posterior do que está consumado e só pode ser administrado. Achado inconveniente não deixa de ser achado.

Usar paráfrase fiel por padrão. Reservar transcrição literal a passagens conferidas e necessárias, com localizador adequado; nunca inventar página a partir da ordem da extração. Não colocar aspas em formulação própria.

## Redigir e incorporar a revisão

Adotar como preferência de redação o perfil [forense clássico e analítico](references/estilo-forense.md): registro culto e formal, argumentação desenvolvida por teses, referências documentais precisas e tom firme, com adjetivação calibrada. Ler o perfil antes de redigir ou reescrever; aplicar sua adaptação consultiva aos pareceres. Instrução específica do usuário ou modelo expressamente escolhido para a tarefa prevalece. Em composição multiagente, levar o perfil ao briefing de redação e revisão, sem mudar o motor, a rubrica ou seus gates.

Organizar a exposição para o leitor compreender o problema e decidir. Cada seção deve cumprir função: demonstrar fato, estabelecer regra, aplicá-la, enfrentar objeção ou justificar providência. Desenvolver o raciocínio; não preencher o corpo com instruções como “inserir jurisprudência” quando a análise já puder ser feita.

Preservar tese, fatos, condições e pedidos sustentados ao reescrever. Corrigir afirmações excessivas com a formulação mais precisa que a prova permite, mantendo a defesa útil. Não multiplicar citações e pedidos para simular robustez. Não inventar provas, valores, assinatura, OAB, poderes, confissões, renúncias ou acordos. Sendo o titular a própria parte, redigir na voz da parte: não inserir identificação de advogado, número de OAB, substabelecimento, fecho do tipo "advogado que esta subscreve" nem marcador que pressuponha patrono, porque OAB ausente não é lacuna que impeça a peça. Se o rito daquele órgão exigir capacidade postulatória, dizer isso no briefing de decisão, com o efeito de protocolar assim mesmo ou não, sem contaminar o corpo. Mudança material do objetivo ou concessão de direito exige base na instrução do usuário; escolhas rotineiras de redação e correções dentro do escopo já estão autorizadas.

**Economia de dependências.** Entre duas formulações que alcançam o mesmo resultado, preferir sempre a que depende de menos — de menos diligência futura, de menos documento a obter, de menos ato de terceiro, de menos premissa que a parte contrária controla. Calibrar uma afirmação transformando-a em condicional é ganho apenas quando a dependência criada for menor que o flanco removido: trocar tese incondicional por analogia condicionada a prova que o adversário detém é perda, ainda que a nova formulação pareça mais cautelosa. Quando a tese vencer sem diligência, dizer que vence sem ela, e deixar a diligência como pedido subsidiário — nunca como premissa da tese.

Antes de entregar, fazer revisão substantiva e incorporar as correções cabíveis. Quando disponível, aplicar o método de `$auditoria-juridica-de-minutas` à candidata; comparação detalhada depende de haver versão anterior. Sem essa dependência, conferir diretamente:

1. se toda afirmação decisiva corresponde ao alcance da fonte e se a cronologia é coerente;
2. se a norma e o precedente citados sustentam a aplicação feita, com as limitações relevantes;
3. se a melhor objeção foi enfrentada e a conclusão depende de premissa frágil;
4. se as questões foram respondidas ou os pedidos são congruentes, compatíveis e executáveis;
5. se a tese ficou dependente de evento futuro, diligência ou documento que não precisaria;
6. se a revisão preservou conteúdo necessário, remissões, notas e integridade documental.

O produto principal continua sendo a minuta corrigida. Evitar auditoria avulsa que apenas devolva problemas solucionáveis já abrangidos pelo pedido de produção. Reexaminar os pontos afetados por correções materiais; não inventar contador, pontuação, aprovação ou ciclo interminável. Distinguir revisão pelo próprio redator de avaliação independente ou consenso realmente executados.

## Reversão estratégica e sua cascata

Estratégia pertence a quem responde pela causa; o redator e o revisor propõem. Quando o titular manda desfazer alteração introduzida por revisão — restaurar uma formulação, retirar um pedido, abandonar uma linha —, isso é decisão, não erro a reargumentar. Não se relitiga o mérito da escolha.

Não inferir reversão estratégica de reparo local, de desconforto com um parágrafo ou de mensagem ambígua. Sendo incerto o ato de fala, fazer uma pergunta só: correção pontual ou abandono da tese? Confirmado o abandono, listar numeradamente o que a cascata vai alterar e informar o custo uma vez, em uma frase, junto com a lista. **Não executar antes de o titular confirmar a lista** — confirmação da lista, não do mérito da escolha; frase única de custo não a substitui.

Confirmada a lista, executar tudo na rodada da execução, não na da listagem. Uma reversão raramente é local. Mapear e executar: todo trecho que passou a depender da premissa abandonada; pedidos que existiam apenas para sustentar aquela dependência, substituídos pela ressalva que ocupe o lugar deles; seções cuja função era preparar o ponto revertido, que precisam ser reenquadradas e não apenas mantidas; títulos, subtítulos e ementas que ainda anunciam o que deixou de existir; e remissões, anexos e capas que apontem para a versão anterior do argumento. Ao final, procurar no texto inteiro os termos da dependência abandonada e verificar cada ocorrência: o que deve desaparecer é a **dependência argumentativa**, não a palavra. Termo que permaneça em narrativa histórica, em transcrição ou no enfrentamento da tese adversária é legítimo e fica.

Registrar a reversão como escolha estratégica do titular, jamais como regressão de qualidade.

## Entregar a minuta efetiva

Respeitar o formato pedido: texto integral no chat quando suficiente; arquivo quando solicitado ou útil. Para DOCX, usar a skill documental disponível, preservar o contrato de revisões e conferir a renderização. Para PDF, usar leitura/OCR ou geração apropriados. Não chamar extração textual de validação visual.

Ao alterar arquivo existente, preservar base recuperável, verificar se o destino mudou e reabrir o destino efetivamente gravado. Não substituir alterações recentes do usuário nem aceitar/rejeitar revisões anteriores silenciosamente. Se o pedido especificar arquivo exato, atualizar esse arquivo; se a saída for cópia, identificar a cópia corretamente. O comparador da auditoria pode ajudar, sem exigir hash para uma simples minuta inline.

**Quando o titular é a própria parte.** Litigante em causa própria protocola o artefato, não a ressalva: pendência escrita no vocabulário da peça não é lida como decisão pendente. Abrir a entrega com um briefing separado do documento, de no máximo uma tela, em frases curtas e um item por linha, dizendo o que este arquivo produz se for protocolado como está; que decisões continuam sendo dele, cada uma com a consequência de decidir num sentido e no outro; e quais impedimentos concretos de uso foram identificados, com a providência de cada um. Protocolar, assinar ou enviar continua sendo decisão do titular: o briefing não autoriza nem proíbe — diz o efeito de fazer e o de não fazer. Na dúvida sobre se o titular é a própria parte, tratar como se fosse. Sem jargão forense, sem hash, sem ficha e sem matriz. Classificar antes os achados por reversibilidade, para não propor no briefing a correção de erro já consumado. O briefing é orientação de uso e **não integra a minuta**: não transcrevê-lo, juntá-lo nem protocolá-lo com ela. A ausência desse briefing é defeito de entrega, não preferência de estilo.

Entregar a minuta e, separadamente, apenas as pendências materiais: informação faltante, fonte não conferida, decisão estratégica necessária ou requisito de uso ainda não atendido. Usar marcadores no corpo somente onde indispensáveis; não contaminar a peça com notas sobre ferramentas, agentes ou processo interno. Em parecer, ressalvas jurídicas relevantes integram a análise. Informar o que foi efetivamente conferido, sem declarar automaticamente “pronta para protocolo/assinatura”. A produção da minuta não implica protocolar, assinar ou enviar a terceiros.
