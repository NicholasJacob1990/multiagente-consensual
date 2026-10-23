# Pesquisa de jurisprudência, legislação e pareceres no Jurisbase

Protocolo para delegar busca a subagentes sem delegar julgamento. Vale para a produção da
minuta e para a conferência de fontes na auditoria.

## Conhecer o acervo antes de perguntar a ele

Rodar `jurisbase_status` no início. Ele informa o volume por tipo, o estado do índice de texto e
se o **gold semântico** está no ar. A
diferença é decisiva: com o gold de pé a busca casa sentido; sem ele, o índice léxico casa
palavra, e o recall passa a depender inteiramente de quantas formulações diferentes forem
tentadas.

A cobertura é desigual por desenho. Os superiores são densos — centenas de milhares de decisões
do STJ e do STF. Vários tribunais estaduais estão representados por amostra, e alguns dos mais
citados na prática têm poucos milhares de decisões, o que é pouco para quem julga isso em dias.
`jurisbase_listar_fontes` dá a contagem por tribunal. **Verificar essa contagem antes de
qualquer conclusão negativa**: silêncio de fonte rasa não é inexistência de precedente.

## Passo zero — cobertura da fonte e vedação da negativa

Contagem zerada ou irrisória para o órgão ou ente de que a tese depende **veda afirmar
inexistência**. A vedação dura enquanto a contagem permanecer zerada ou irrisória; coleta bem-sucedida só a levanta depois de nova verificação da contagem. Registrar `fonte_nao_coberta`
com o órgão, a consulta literal e o recorte temporal; concluir, no máximo, "não localizado no
escopo pesquisado". Se a tese depender da negativa, bloquear a conclusão dependente e dizer qual
é — os achados independentes permanecem válidos. Afirmação negativa sobre fonte não coberta é
erro de método, não achado.

`jurisbase_coletar`, acompanhado por `jurisbase_coleta_status`, é **providência, não
pré-requisito**. Só acioná-lo se for razoável que a coleta daquela fonte **termine nesta
sessão**, ou se o titular autorizar a espera; fora disso, não iniciar coleta, seguir com a
minuta ou a auditoria e entregar o resto. Coleta não iniciada, em curso, concluída ou frustrada
não autoriza tratar o acervo como completo nem dispensa a re-verificação da contagem. A regra vale
igualmente para os três: jurisprudência, legislação e parecer.

## Três papéis, não oito

**Varredor** — barato, replicado, uma tese por instância. Roda a mesma tese em várias
formulações: sinônimos, o termo como aparece em ementa, o número do dispositivo, a expressão do
edital ou do contrato, grafias com e sem acento, o latinismo e o equivalente vernáculo. Com o
gold no ar, combinar consulta semântica e léxica; sem ele, multiplicar formulações é o único
recall disponível. Devolve linhas de evidência, nunca conclusões.

**Adversarial** — barato, mas com briefing invertido: procura o que derruba a tese, o julgado
que nega, a corrente contrária, a norma que excepciona. Sem esse papel, todos os agentes
encontram o que a causa quer, e o precedente adverso só aparece na contrarrazão do adversário.

**Leitor** — modelo forte, poucas instâncias, apenas sobre a lista curta. Abre o inteiro teor
por `jurisbase_ler_decisao` ou `jurisbase_ler_precedente`, extrai a questão decidida, os fatos,
o fundamento determinante, o resultado e a distinção pertinente. É aqui que se concentra o custo
e é aqui que não se economiza.

## Contrato de retorno dos subagentes

Cada achado volta como linha de evidência, com: a ferramenta e a consulta literal usadas; o
identificador tal como retornado; tribunal, órgão, relatoria e datas sem reformulação; o nível
de acesso efetivo — inteiro teor no acervo, ementa ou trecho oficial, espelho indexado,
reprodução indireta, não conferido; e o trecho literal que sustenta a pertinência.

**É vedado ao varredor resumir, qualificar, classificar como favorável ou adverso, afirmar ratio
decidendi ou declarar ausência de resultado como inexistência.** Quem qualifica é o leitor,
depois, sobre as linhas. Um retorno do tipo "encontrei três precedentes favoráveis" deve ser
recusado e refeito: não é verificável e carrega a conclusão que o modelo barato não tem
competência para tirar.

O varredor faz triagem de **pertinência**, não de mérito: pode reter ou descartar item por não
tratar da questão, desde que sustente a decisão no trecho literal e registre, entre os
resultados examinados, o identificador e o motivo de cada descarte. Permanece vedado classificar
como favorável ou adverso, afirmar ratio decidendi e declarar inexistência.

## Triagem e custo

O gasto não está nas buscas, que retornam pouco, e sim na leitura de acórdão inteiro. O varredor
tria sobre ementa; cinco a oito itens por tese sobem para leitura integral, mais os adversos
relevantes. Esse número é lote inicial, não teto nem meta: ampliar quando restar questão
decisiva sem cobertura ou quando aparecer divergência relevante entre os já lidos. Cabe ao
leitor rever os descartes que possam ser decisivos.

## Onde o subagente roda

**Regra de preferência: a varredura roda nos subagentes da própria CLI que conduz a análise.**
Quem trabalha no Claude usa os subagentes do Claude; quem trabalha no Codex usa os subagentes do
Codex. O motivo não é conveniência: o subagente da própria sessão herda as ferramentas já
autenticadas, enxerga o Jurisbase sem configuração adicional, devolve a linha de evidência no
mesmo formato e fica sujeito ao mesmo contrato de retorno. Encaminhar a busca para outra CLI
acrescenta uma fronteira — de credencial, de formato e de verificação — sem acrescentar recall.

Recorrer ao mesh a2a é exceção justificada, não padrão. Justifica-se quando se quer **diversidade
de leitura** sobre a mesma lista curta, quando o papel adversarial deve ser exercido por modelo
que não participou da formulação da tese, ou quando o volume de varredura excede o que a sessão
corrente comporta. Nesses casos, registrar qual motor executou cada varredura, porque a
qualificação do achado depende de quem o leu.

Antes de distribuir papéis a agente externo, confirmar naquele agente que o servidor MCP do
Jurisbase está configurado e responde; sem isso a busca falha em silêncio ou o agente inventa o
resultado. Reinstalação ou atualização de CLI costuma reescrever essa configuração, de modo que
a conferência é por sessão, não por memória.
