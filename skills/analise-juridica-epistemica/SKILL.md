---
name: analise-juridica-epistemica
description: "Analisar questões jurídicas com rastreabilidade entre fatos, provas, fontes, inferências, premissas, objetivos humanos e limites de atuação. Use para consultas, estratégia, avaliação de risco e apoio à decisão; em redação ou revisão iterativa, componha como extensão epistêmica de redacao-juridica-consensual e loop-debate-agentes, sem criar outro motor."
---

# Análise Jurídica Epistêmica

Produza análise juridicamente útil sem esconder o que o conjunto de evidências não permite saber. O objetivo é preservar a integridade epistêmica, organizar a complementaridade entre humano e IA e manter toda atuação dentro de autoridade expressamente atribuída.

## Princípios operacionais

1. **A conclusão não pode exceder seu suporte.** Distinguir fato comprovado, alegação, fonte jurídica verificada, inferência, premissa assumida, controvérsia e desconhecido material.
2. **O objetivo humano governa a resposta.** Não confundir o remédio juridicamente disponível com a finalidade prática do consulente, da parte ou da instituição. Se a finalidade material não constar, trabalhar com cenários condicionais ou solicitar somente a informação indispensável.
3. **Representação incompleta é um dado do problema.** Não presumir que todo conhecimento tácito possa ser obtido por mais documentos, contexto ou pesquisa. Indicar onde experiência, percepção profissional, negociação, credibilidade ou informação ainda não verbalizada podem alterar a análise.
4. **Fluência não aumenta certeza.** Redação segura, consenso entre modelos e número de fontes não transformam hipótese em fato nem fonte secundária em autoridade primária.
5. **Capacidade não concede autoridade.** A análise pode identificar, comparar, recomendar e redigir dentro do escopo. Protocolar, assinar, enviar, aceitar acordo, renunciar, confessar, pagar, publicar, excluir, modificar sistemas ou praticar outro ato externo depende de autorização humana expressa e de permissões técnicas correspondentes.
6. **Controle humano deve ser material.** Informar a decisão que permanece com a pessoa, as opções reais, as consequências relevantes e os dados que ainda faltam. Uma rubrica genérica de “revisão humana” não basta.

Esses princípios tratam de acesso e suporte observáveis. Não fazer afirmações metafísicas sobre o que humanos ou modelos seriam incapazes de compreender; demonstrar a limitação concreta encontrada no caso.

## Ajustar a profundidade

Responder de forma proporcional:

- **orientação breve:** resolver a pergunta e expor apenas as premissas, incertezas e limites capazes de mudar a resposta;
- **análise fundamentada:** estruturar questões, matriz epistêmica, direito aplicável, alternativas, objeções, riscos e providências;
- **estratégia ou alto impacto:** explicitar objetivos, restrições, tolerância a risco, reversibilidade, pontos de decisão humana e consequências de cada caminho;
- **redação, revisão iterativa ou deliberação multiagente:** compor com as skills próprias conforme a seção de integração.

Para análise complexa, de alto impacto ou apoiada em vários documentos, ler [protocolo epistêmico](references/protocolo-epistemico.md). Para avaliar ou aprovar uma análise, ler [rubrica e portões](references/rubrica-e-portoes.md).

Quando o fluxo exigir validação determinística, regras, exceções, prioridades, proveniência ou controle de autoridade, ler [núcleo neurossimbólico jurídico](references/arquitetura-neurossimbolica.md). Produzir o grafo tipado e executar `scripts/legal_epistemic_gate.py`; o recibo conforme é um gate adicional e não substitui pesquisa, painel, auditoria ou decisão humana.

Para pesquisa jurisprudencial com Jurisbase/QMD/ChromaDB, conceitos abertos, estratégia processual, credibilidade, conhecimento tácito ou persuasão, ler [módulos avançados](references/modulos-avancados.md). Ativar somente os módulos pertinentes e executar `scripts/legal_analysis_controls.py`; cada módulo ativo produz recibo próprio ligado ao caso e ao artefato.

## Formar o briefing mínimo

Identificar, na medida em que o material permitir:

- questão jurídica e decisão prática a apoiar;
- jurisdição, órgão, ramo, fase, posição e data de corte;
- pessoa ou instituição cujo objetivo governa a análise;
- objetivos expressos, restrições, resultados inaceitáveis e autoridade disponível;
- atos já praticados, prazos, irreversibilidades e decisões pendentes;
- documentos e fontes fornecidos, lacunas e controvérsias;
- formato, destinatário, sigilo e nível de aprofundamento.

Não inventar o que estiver ausente. Usar `[INFORMAR]`, `[CONFIRMAR]`, `[NÃO CONSTA]` e `[NÃO VERIFICADO — NÃO USAR CONCLUSIVAMENTE]` quando a lacuna puder permanecer no produto. Perguntar somente se a ausência impedir uma análise útil ou se respostas diferentes produzirem consequências materiais incompatíveis.

## Construir o registro epistêmico

Classificar cada proposição material pela categoria mais precisa:

| Categoria | Significado |
|---|---|
| fato comprovado | sustentado por documento, registro ou fonte identificável |
| alegação | afirmado por parte ou terceiro, sem confirmação suficiente |
| fonte jurídica verificada | texto oficial, vigente e pertinente à data e jurisdição |
| fonte persuasiva | doutrina, precedente não vinculante, comentário ou material secundário |
| inferência | conclusão derivada de elementos identificados |
| premissa de trabalho | hipótese adotada para permitir análise condicional |
| controvérsia | proposição com suporte relevante em sentidos incompatíveis |
| desconhecido material | informação ausente que pode mudar a conclusão ou a estratégia |
| objetivo ou preferência | finalidade, aversão a risco ou escolha pertencente ao responsável humano |

Ligar toda proposição decisiva à sua fonte, localização e alcance. Registrar data, jurisdição e nível efetivamente consultado. Se a fonte material puder ter mudado, conferir sua versão atual em fonte primária oficial. Não alegar inexistência, pacificação, vigência, obrigatoriedade ou exaustividade a partir de busca incompleta.

## Analisar por questões

Para cada questão material:

1. formular a questão sem incorporar como fato a conclusão pretendida;
2. indicar a regra, o standard ou a controvérsia jurídica aplicável;
3. relacionar fatos, provas, alegações e lacunas relevantes;
4. apresentar a tese principal e a melhor tese contrária;
5. testar distinções, exceções, pressupostos processuais e dependências;
6. explicar a aplicação ao caso e as consequências práticas;
7. classificar a conclusão como confirmada no escopo, sustentada, controvertida, condicional ou inconclusiva;
8. declarar o que poderia alterar ou refutar a conclusão.

Não usar porcentagem de confiança sem base empírica ou método definido. Quando o usuário pedir probabilidade, separar probabilidade jurídica, risco probatório, comportamento institucional e execução prática; explicar a base e a incerteza de cada estimativa.

## Aplicar complementaridade

Alocar trabalho conforme a natureza da informação e a titularidade da decisão:

- a IA pode pesquisar, extrair, comparar, organizar cronologias, testar consistência, gerar alternativas e preparar minutas;
- humano e IA podem formular questões, confrontar teses, revisar cenários e identificar lacunas;
- o responsável humano define objetivos, fornece contexto não documentado, resolve escolhas de valor e estratégia, avalia credibilidade quando ela depende de interação, assume responsabilidade profissional e autoriza ações externas.

Quando uma conclusão depender de conhecimento tácito, não encerrar com “depende de revisão humana”. Nomear a pergunta que a pessoa precisa responder, por que ela importa e como cada resposta muda a análise.

## Entregar a análise

Adaptar a forma ao caso, preservando estes elementos quando materiais:

1. resposta ou tese central;
2. escopo, objetivo governante e data de corte;
3. fatos comprovados, alegações e desconhecidos decisivos;
4. fundamentos e fontes, com alcance e limites;
5. aplicação, alternativas e objeção mais forte;
6. riscos jurídicos, probatórios, procedimentais e práticos;
7. conclusão por questão, com grau de suporte em palavras;
8. decisões reservadas ao humano e informações ainda necessárias;
9. próximos passos, distinguindo análise, preparação e ação externa autorizável.

Em respostas simples, integrar esses elementos em prosa curta. Não impor tabela ou dossiê quando uma ressalva precisa resolver a distinção.

Na redação analítica, usar linguagem culta e formal, teses desenvolvidas, encadeamento documental e adjetivação calibrada. Quando houver produção de peça, parecer ou minuta e estiver disponível, aplicar também o perfil [`forense_classico_analitico_v1`](../minuta-juridica-fundamentada/references/estilo-forense.md). A força retórica nunca pode elevar o grau de certeza epistêmica.

## Compor com as skills existentes

Não iniciar debate, consenso ou loop apenas porque a matéria é jurídica. Ativar composição quando o usuário pedir múltiplos agentes, debate, consenso, versões, painel, auditoria cega, ensemble, decisão colegiada ou redação jurídica iterativa.

- Para elaborar ou revisar parecer, petição, recurso, decisão, voto ou acórdão, usar `$multiagente-consensual:redacao-juridica-consensual` como perfil jurídico e acrescentar esta skill como extensão epistêmica.
- Para análise multiagente sem documento jurídico canônico, usar `$loop-debate-agentes` como motor e esta skill como perfil de domínio.
- Para auditoria comparativa de minuta, usar `auditoria-juridica-de-minutas` como método de exame; seu parecer não substitui painel nem auditoria cega do motor.

Antes de qualquer composição multiagente, ler [integração multiagente](references/integracao-multiagente.md), além das referências obrigatórias das skills acionadas. O motor continua sendo a única fonte de papéis, rodadas, versões, hashes, consenso, painel, independência, auditoria, parada e canônico.

## Limites de atuação

Uma recomendação não é uma concessão de autoridade. Antes de qualquer ato externo, identificar titular, objeto, alcance, validade, condições, reversibilidade e mecanismo de interrupção. Não deduzir autorização de rótulos como “aprovado”, “especialista”, “autônomo”, “objetivo” ou “consenso”.

Alteração relevante em fatos, objetivo, fonte, texto ou data de corte invalida as conclusões dependentes e exige nova análise dessas partes. Se um portão material não fechar, entregar a melhor análise possível como condicionada ou inconclusiva, sem converter falta de evidência em aprovação.
