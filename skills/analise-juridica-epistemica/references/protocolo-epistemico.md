# Protocolo epistêmico para análise jurídica

Use este protocolo em análises complexas, de alto impacto, apoiadas em vários documentos ou destinadas a orientar estratégia. Ele amplia o método da skill sem criar um motor de execução.

## 1. Delimitar a pergunta real

Separar quatro objetos que frequentemente aparecem misturados:

1. **questão de direito:** qual regra, interpretação ou consequência jurídica é aplicável;
2. **questão de fato ou prova:** o que ocorreu e o que pode ser demonstrado;
3. **questão de estratégia:** que curso de ação melhor atende ao objetivo e às restrições do responsável;
4. **questão de autoridade:** quem pode decidir ou praticar o ato, em que extensão e sob quais controles.

Se a pergunta declarada pedir apenas “é possível?”, verificar se a decisão prática exige também “é aconselhável?”, “para qual finalidade?”, “com que risco?” ou “quem pode autorizar?”. Não substituir a pergunta do usuário; expor as dimensões adicionais que alteram a utilidade da resposta.

## 2. Registrar objetivo e lacuna de intenção

Usar, quando pertinente:

```text
Responsável pelo objetivo:
Objetivo principal expresso:
Objetivos secundários:
Restrições e resultados inaceitáveis:
Tolerância a risco:
Horizonte temporal:
Poderes ou autorizações já concedidos:
Contexto tácito relevante informado:
Questões de intenção ainda abertas:
Efeito de cada lacuna sobre a análise:
```

Não inferir que litigar, rescindir, recorrer, punir, obter tutela ou vencer é necessariamente o objetivo final. Esses são meios ou resultados jurídicos possíveis. O objetivo pode ser preservar relação, reduzir exposição, ganhar tempo, produzir precedente, encerrar controvérsia, obter cumprimento ou evitar publicidade.

Quando houver mais de um objetivo plausível, elaborar ramos condicionais. Exemplo abstrato: “Se a prioridade for execução imediata, a alternativa A ganha peso; se for preservar a relação, a alternativa B reduz o custo relacional, embora acrescente risco X.”

## 3. Manifesto e matriz de proposições

Para arquivos locais, preservar os originais e registrar caminho, versão, data e SHA-256. Para fontes externas, registrar URL oficial, órgão, identificação, data do conteúdo, data de acesso e nível consultado.

Usar uma linha por proposição material:

```yaml
- id: E-001
  proposicao: ""
  classe: fato_comprovado | alegacao | fonte_juridica_verificada | fonte_persuasiva | inferencia | premissa | controversia | desconhecido | objetivo
  suporte:
    - fonte_id: ""
      localizacao: ""
      alcance: ""
  contradiz:
    - ""
  jurisdicao: ""
  validade_temporal: ""
  estado: confirmado | sustentado | disputado | condicional | desconhecido
  impacto_se_falso: baixo | medio | alto | decisivo
  responsavel_por_esclarecer: ""
  observacao: ""
```

Não preencher campos com aparência de precisão quando a informação não existir. Em resposta conversacional, mostrar somente as linhas materiais e converter a matriz em prosa ou tabela legível.

## 4. Hierarquia e qualidade das fontes

Avaliar separadamente:

- autenticidade e origem;
- vigência ou atualidade;
- autoridade jurídica;
- aderência fática e processual;
- integralidade do conteúdo consultado;
- existência de divergência ou superação;
- função da fonte na conclusão.

Uma fonte pode ser autêntica e pouco aderente; oficial e superada; persuasiva e ainda útil. Não colapsar essas dimensões em “fonte boa”. Ementa não equivale ao inteiro teor; índice ou reprodução indireta não prova o conteúdo original; silêncio da busca não prova inexistência.

## 5. Cadeia de aplicação

Para cada questão, tornar auditável a sequência:

```text
questão → regra/standard → fato ou premissa → evidência → aplicação → conclusão → consequência prática
```

Se uma ligação depender de inferência, nomeá-la. Se houver uma regra alternativa ou exceção relevante, criar ramo separado. Não esconder saltos por meio de conectivos conclusivos ou redação categórica.

## 6. Testes adversariais

Aplicar os testes pertinentes:

- melhor tese contrária e melhor resposta disponível;
- fato decisivo mais vulnerável;
- fonte cujo alcance pode ter sido exagerado;
- mudança de objetivo que altera a recomendação;
- distinção processual ou temporal capaz de afastar a regra;
- dependência de ato futuro, terceiro ou prova ainda não obtida;
- custo de reversão caso a recomendação esteja errada;
- resultado se a premissa central for rejeitada;
- informação que refutaria a conclusão.

Uma tese sobrevive melhor quando mantém utilidade mesmo após a rejeição de sua premissa mais frágil. Não multiplicar teses ou pedidos como substituto de robustez.

## 7. Complementaridade concreta

Produzir, quando material, um mapa curto:

| Trabalho | Melhor alocação | Motivo e controle |
|---|---|---|
| busca, extração, cronologia, comparação | IA com verificação | escala e rastreabilidade |
| enquadramento e teste de alternativas | conjunto | exige técnica e objetivo contextual |
| credibilidade baseada em interação | humano informado | evidência tácita não representada integralmente |
| escolha de objetivo e tolerância a risco | titular humano | decisão de valor e responsabilidade |
| ato externo ou irreversível | humano autorizado e controle independente | autoridade e consequência |

Converter qualquer rótulo genérico de revisão humana em uma ação verificável. Exemplo: “confirmar se preservar o contrato prevalece sobre obter indenização” é útil; “submeter ao humano” não é suficiente.

## 8. Agência e autorização

Para cada ação recomendada que produza efeitos externos, registrar:

```text
Ação:
Titular da autoridade:
Escopo autorizado:
Alvo e ambiente:
Condições prévias:
Reversibilidade:
Segundo canal ou dupla validação, se necessário:
Mecanismo de interrupção:
Registro posterior:
Estado: apenas proposta | preparada | autorizada | executada | verificada
```

Não alterar o estado com base em inferência do modelo. “Preparada” significa que existe resultado concreto para revisão; “autorizada” exige manifestação humana ou concessão institucional verificável; “executada” e “verificada” exigem evidência correspondente.

## 9. Conclusão calibrada

Usar palavras e fundamentos, em vez de falsa precisão:

- **confirmada no escopo:** fontes e fatos decisivos foram verificados, sem bloqueio material identificado;
- **sustentada:** há base relevante, com riscos ou alternativas que não impedem posição principal;
- **controvertida:** fontes ou aplicações relevantes conduzem a resultados defensáveis distintos;
- **condicional:** depende de premissa, fato, objetivo ou evento declarado;
- **inconclusiva:** falta elemento decisivo e os ramos não permitem recomendação responsável.

Uma conclusão condicional pode ser altamente útil. Informar qual verificação, escolha ou evento a converteria em posição mais definida.

## 10. Formato sugerido para análise extensa

```text
Síntese executiva
Escopo, objetivo e data de corte
Questões apresentadas
Registro epistêmico material
Direito aplicável e fontes
Análise por questão
Teses contrárias e cenários
Riscos, dependências e reversibilidade
Conclusões calibradas
Decisões humanas pendentes
Próximos passos e limites de autoridade
Anexo de fontes, quando necessário
```

Adaptar a ordem para a finalidade. Não transformar o formato em checklist visível quando isso prejudicar a leitura.
