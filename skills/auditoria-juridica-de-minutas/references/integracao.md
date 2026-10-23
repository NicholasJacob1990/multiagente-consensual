# Integração com redação jurídica e loop

## Fronteiras

| Componente | Responsabilidade |
|---|---|
| Auditoria jurídica de minutas | Comparação, evidências, resistência estratégica, congruência e relatório |
| Redação Jurídica Consensual | Briefing, receita, rubrica, fontes e portões jurídicos |
| Loop Debate de Agentes | Participantes, rotas, autoria, versões, publicação, consenso, painel, auditoria cega, parada e recibos |

Resolver as skills pelas localizações efetivamente disponibilizadas, inclusive nomes de plugin. Não presumir cópia local idêntica ao plugin nem editar cache para ativar composição. Registrar o contrato lido. A auditoria avulsa funciona sem essas dependências; composição só pode alegar gates efetivamente executados.

Quando usada com a redação jurídica, conservar:

```yaml
perfil_base: debate_agents_v1
perfil_dominio: juridico_consensual_v2
extensoes_dominio:
  juridico:
    auditoria_comparativa:
      contrato: auditoria_juridica_minutas_v1
      ativa: true
      modalidade: consultivo # ou contencioso; resolver pelo caso
      escopo: conforme_pedido
      base: null # caminho e sha256, se houver
      candidata: null # caminho e sha256 efetivamente lidos
      manifesto_fontes: null # usar o manifesto já governado pelo run
      parecer_comparativo: null # preencher com a saída gerada
```

É metadado de domínio a integrar à configuração existente, não configuração executável completa nem prova de avaliação. Em pacote, usar escopo por `artefato_id` do contrato jurídico. Não criar outro `meta.json`, ledger concorrente, canônico ou contador.

Em run já congelado, não mudar a configuração ou os gates silenciosamente: registrar a análise
avulsa como anexo ou seguir a política do motor para mudanças autorizadas, preservando o histórico.

## Posição no fluxo

1. Receber hash candidato congelado e base disponível. Usar o conjunto de evidências autorizado.
2. Gerar parecer e objeções, examinando perdas e ganhos por questão.
3. Entregar ao crítico, painel ou consolidador configurado. Ele responde no ledger e corrige quando autorizado. A auditoria não adquire poder de publicar por ser revisora.
4. Incorporação material cria próximo hash canônico segundo o motor e exige os gates aplicáveis. Rótulos históricos como `v21` não reiniciam nem consomem por si o contador do run; importa a promoção à cadeia governada pelo motor.
5. Conferir o arquivo efetivamente entregue. Hash de candidata em outra pasta não certifica o documento que o usuário abrirá.

A prévia é única: acrescentar modalidade, base/candidata, cobertura e método à prévia do motor. Honrar autorização existente, sem confirmar por achado ou correção já incluída no escopo. Aplicar exigências do contrato somente às ações que governam. Criar esta skill, testá-la localmente ou fazer conferência avulsa não inicia automaticamente um loop externo.

## Comparador e auditor cego

O **comparador** conhece versões, críticas e histórico necessários para localizar regressões. Anonimização de autoria não o torna auditor cego final.

O **auditor final do motor** usa sessão nova e recebe somente artefato final, briefing, fontes e critérios admitidos. Não receberá parecer comparativo, placar, elogios, ranking ou identidade dos redatores. Se o mesmo modelo exercer funções diferentes, registrar independência real, sem criar diversidade por nome de persona.

Comparação, seleção, nota ou recomendação isolada não satisfaz consenso nem autoriza `canonico_aprovado`. O parecer alimenta gates de domínio, mas não substitui painel, deliberação, auditoria cega ou revisão profissional exigidos. Na auditoria avulsa, declarar apenas seu próprio resultado.

## Objeções e cobertura

Usar categorias e severidades do perfil jurídico. Nas cinco dimensões do motor:

- clareza: precisão, legibilidade e referências;
- profundidade: alternativas, objeções e efeitos;
- coerência: cadeia de sustentação e regressões;
- precisão conceitual: fidelidade factual, normativa e jurisprudencial;
- qualidade da explicação: condições, providências e risco residual.

**Economia de dependências é portão, não sexta nota.** O motor fixa cinco dimensões e o perfil jurídico pode acrescentar gate, não redefinir a escala. Reportar como objeção bloqueante, e não como pontuação, a tese que passou a depender de diligência futura, documento a obter, ato de terceiro ou premissa que a parte contrária controla, quando havia formulação de igual alcance sem essa dependência. A razão de ser gate é que as cinco dimensões, sozinhas, premiam o movimento errado: condicionar uma afirmação eleva a precisão conceitual e parece ganho, mas só é ganho se a dependência criada for menor que o flanco removido — e nota média absorve essa perda, portão não. Pelo mesmo motivo são gates, e não notas, o rótulo da peça que não entrega o efeito processual pretendido, a duplicação de pedido pendente sem função processual e a conclusão negativa assentada em fonte não coberta. Decisão estratégica do titular da causa não é pontuada nem bloqueada como defeito.

Um limite conhecido do método, a registrar quando a cobertura for alegada: a auditoria controla melhor a **rastreabilidade do material selecionado** do que a **suficiência da seleção**. Todos podem conferir corretamente os mesmos documentos e concordar sobre tese cuja premissa foi omitida do briefing; hash, sessão cega e consenso preservam independência operacional, não corrigem omissão compartilhada.

Não criar segunda média, piso ou aprovação compensatória. Perda material não autorizada, falso fato decisivo, fonte atribuída incorretamente, conclusão sem suporte e entrega divergente permanecem bloqueadores nos gates pertinentes.

Alertas instrumentais não são bloqueadores jurídicos automáticos. Repetição pode ser legítima numa citação; nota sem chamada pode ser residual. Confirmar contexto e impacto e procurar falhas substantivas que o script não examina.

## Invocações

```text
Use $auditoria-juridica-de-minutas para comparar este parecer com a versão anterior. Não edite; destaque premissas, riscos e condições de execução.

Use $auditoria-juridica-de-minutas junto com $multiagente-consensual:redacao-juridica-consensual para revisar o recurso. Aproveite a configuração autorizada e leve as objeções ao ledger existente.

Use $auditoria-juridica-de-minutas no $loop-debate-agentes. Compare cada nova minuta com a anterior antes de consolidar; mantenha a auditoria cega final separada.
```

Se a dependência estiver indisponível, executar somente auditoria avulsa autorizada e útil; informar o componente não executado. Não simular modelo, debate, painel, fonte ou aprovação.
