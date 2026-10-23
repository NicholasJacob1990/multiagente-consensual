# Integração com redação e deliberação multiagente

Esta skill é uma extensão de domínio. Ela não implementa papéis, chamadas, consenso, versões, canônicos ou auditoria.

## Roteamento

### Análise jurídica sem artefato canônico

Quando o usuário pedir debate, consenso, painel ou melhoria multiagente de uma análise:

```yaml
perfil_base: debate_agents_v1
perfil_dominio: analise_juridica_epistemica_v1
extensoes_dominio:
  epistemico:
    protocolo: epistemic_legal_analysis_v1
    objetivo_governante: ""
    data_corte: ""
    registro_proposicoes: true
    complementaridade: true
    agencia_delimitada: true
```

Ler integralmente `$loop-debate-agentes` e suas referências obrigatórias. Usar sua prévia **Entendi assim** e acrescentar somente os campos epistêmicos necessários. Aguardar a confirmação exigida pelo motor antes de chamadas externas.

### Redação ou revisão de documento jurídico

Quando o produto for parecer, petição, recurso, decisão, voto, acórdão ou pacote documental:

```yaml
perfil_base: debate_agents_v1
perfil_dominio: juridico_consensual_v2
extensoes_dominio:
  juridico: "configuração governada por redacao-juridica-consensual"
  epistemico:
    protocolo: epistemic_legal_analysis_v1
    registro_proposicoes: true
    gate_objetivo_governante: true
    gate_premissas_materiais: true
    gate_limites_autoridade: true
    symbolic_gate:
      modo: assistido
      representacao: legal_epistemic_graph_v1
      executor: scripts/legal_epistemic_gate.py
      recibo_obrigatorio: true
    advanced_controls:
      modo: proporcional
      executor: scripts/legal_analysis_controls.py
      modulos: [research_fusion, precedent_factors, strategy_tree, credibility_matrix, elicitation_queue, persuasion_gate]
      recibos_obrigatorios_para_modulos_ativos: true
```

Ler integralmente `$multiagente-consensual:redacao-juridica-consensual`, `$loop-debate-agentes` e as referências que seus contratos exigirem. Manter `juridico_consensual_v2` como perfil de domínio; esta skill entra em `extensoes_dominio.epistemico`, sem substituir o perfil jurídico.

## Lentes adicionais

Distribuir estas lentes entre as cadeiras já configuradas, sem criar participantes extras por conveniência:

- **guardião do objetivo:** verifica se a análise ou minuta responde à finalidade humana declarada e detecta substituição do objetivo por um remédio jurídico;
- **verificador epistêmico:** audita classificação, proveniência, inferências, premissas, desconhecidos e data de corte;
- **oponente:** formula a melhor tese contrária e identifica a premissa mais vulnerável;
- **revisor de agência:** confere se recomendações, permissões e ações externas permanecem separadas;
- **integrador:** preserva dissensos e converte achados aceitos em nova versão, se tiver autoria autorizada pelo motor.

Uma lente não cria independência. Registrar sempre agente, papel, CLI, modelo, provedor e sessão conforme o motor.

## Pacote entregue a todas as cadeiras

Além do snapshot jurídico comum, fornecer:

```text
questões jurídicas congeladas
objetivo governante e objetivos alternativos declarados
restrições e resultados inaceitáveis
registro epistêmico material
manifesto de fontes e data de corte
desconhecidos e controvérsias
limites de autoridade e ações vedadas sem autorização
rubrica jurídica e portões epistêmicos
hash do artefato, quando existir
```

Nenhuma cadeira pode preencher lacuna de intenção ou evidência como se fosse fato. Ela pode sugerir perguntas, hipóteses e ramos condicionais.

## Deliberação

O debate deve separar quatro tipos de desacordo:

1. **factual ou probatório:** resolver por fonte, ressalva ou desconhecido aberto;
2. **jurídico interpretativo:** preservar alternativas defensáveis e indicar autoridade;
3. **estratégico:** submeter ao objetivo, tolerância a risco e responsável humano;
4. **valorativo ou de autoridade:** não resolver por maioria de modelos; devolver ao titular competente.

Consenso de agentes não corrige ausência de evidência, não fornece intenção humana e não concede autoridade. O decisor do motor pode resolver matéria julgável dentro de seu contrato, mas não transformar escolha reservada ao titular em conclusão técnica.

## Gates adicionais

Aplicar, no mesmo hash e sem substituir os gates jurídicos ou do motor:

- `objetivo_governante_explicito_ou_cenarios_condicionais`;
- `proposicoes_decisivas_classificadas_e_rastreadas`;
- `premissas_materiais_visiveis`;
- `desconhecidos_decisivos_expostos`;
- `melhor_objecao_enfrentada`;
- `conclusao_compativel_com_suporte`;
- `decisoes_humanas_concretas`;
- `limites_de_autoridade_preservados`.

Falha em qualquer gate material abre objeção no ledger e impede aprovação. Correção gera novo hash e reabre somente os gates afetados conforme o motor; aprovação de outro hash nunca é herdada.

Quando `symbolic_gate` estiver ativo, aplicar também [arquitetura neurossimbólica](arquitetura-neurossimbolica.md). Congelar o grafo e executar o validador sobre o mesmo artefato antes do painel. Persistir o recibo em caminho próprio do `artefato_id`. O painel e o auditor recebem o recibo como evidência de consistência, sem tratá-lo como prova de correção jurídica. Qualquer alteração do grafo, das fontes, do objetivo, do grant ou do artefato invalida o recibo anterior.

Quando algum controle avançado estiver ativo, aplicar [módulos avançados](modulos-avancados.md). Os agentes consultam Jurisbase, QMD e ChromaDB conforme disponibilidade, normalizam os resultados e executam o comando determinístico correspondente. Ausência de provedor primário bloqueia verificação jurisprudencial, mas não elimina achados independentes nem impede que o acervo local seja usado como pista expressamente não verificada.

## Prévia única

Acrescentar à prévia do motor ou do perfil jurídico, sem criar segunda confirmação:

```text
Extensão epistêmica: epistemic_legal_analysis_v1
Objetivo governante: confirmado | [CONFIRMAR] | análise por cenários
Registro de proposições: ativo
Conhecimento tácito relevante: informado | pontos de consulta identificados | não material
Lentes adicionais: guardião do objetivo, verificador epistêmico, oponente e agência, distribuídas nas cadeiras confirmadas
Portões epistêmicos: ativos
Atos externos: nenhum | lista que exigirá autorização humana específica
```

Não realizar chamada externa antes da confirmação exigida pelas skills compostas.

## Entrega

Além do recibo do motor, informar:

- objetivo usado e qualquer alternativa preservada;
- proposições decisivas por categoria;
- premissas e desconhecidos remanescentes;
- dissensos factuais, jurídicos, estratégicos e valorativos separados;
- conclusões que permaneceram condicionais;
- decisões humanas ainda necessárias;
- ações apenas propostas, preparadas, autorizadas, executadas e verificadas, sem misturar estados.

Um artefato pode satisfazer notas e consenso e ainda reprovar por premissa oculta, fonte material não verificada ou extrapolação de autoridade. Nessa hipótese, entregar a melhor versão como não aprovada e identificar o portão aberto.
