# Custo, créditos e esforço das cadeiras

Rodadas com pacotes grandes e raciocínio alto esgotam créditos rápido: dezessete chamadas de cerca de 160 mil caracteres em esforço alto passam de um milhão de tokens. A cadeira não avisa antes; ela devolve 429 no meio do run. Esta política é do motor e vale para qualquer perfil de domínio.

## Antes de cada rodada

1. **Estimar.** Calcular o tamanho do pacote (caracteres ÷ 3,5 ≈ tokens em português) e multiplicar pelo número de cadeiras e de chamadas previstas. Registrar a estimativa no `meta.json` da rodada e mostrá-la na prévia quando passar de 500 mil tokens.
2. **Sondar.** Antes de enviar um pacote grande a uma cadeira com créditos incertos, mandar um prompt mínimo pela mesma rota e com o mesmo modelo. Erro de cota, 429 ou "balance is too low" encerra a tentativa antes de gastar o pacote.
3. **Escolher o esforço.** As rodadas intermediárias (propostas, votos, rechecagens) usam `medium`. O esforço `high` fica para a auditoria cega final e para a primeira leitura integral de um caso novo. Se a rota não oferecer o esforço pedido (por exemplo, `xhigh` no Argon pelo `agy`), usar o maior disponível e avisar.
4. **Reduzir o pacote.** A partir da segunda rodada sobre o mesmo texto, enviar só as diferenças: os parágrafos alterados com os vizinhos, a lista de números e o hash da versão integral, que fica disponível se o auditor pedir. O dossiê e o adendo de fontes só voltam inteiros quando mudarem.

## Quando a cadeira falhar por crédito

- Não repetir a mesma chamada em laço.
- Registrar a falha e o horário no run.
- Oferecer as alternativas na seguinte ordem:
  1. a mesma família por outra rota, como o app web, para o usuário colar o pacote;
  2. outra cadeira da mesma família;
  3. outra família, avisando que a independência da auditoria muda.
- Pacote para colar no app vai em um único arquivo, com instruções, hash e o formato de resposta exigido.

## Diagnóstico até a nota-alvo

Quando o usuário fixar uma nota-alvo (por exemplo, média 9,8), não basta pedir mais uma auditoria. Antes, pedir a um auditor o diagnóstico do que separa a versão atual da nota: para cada critério abaixo do alvo, o trecho, o defeito e a correção mínima. Filtrar o diagnóstico contra as fontes e as decisões já tomadas pelo usuário, aplicar o que sobreviver e só então reauditar. Cada reauditoria sem diagnóstico custa uma rodada inteira e tende a devolver a mesma nota.
