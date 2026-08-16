# Perfil jurídico `juridico_consensual_v2`

Este arquivo é uma extensão de `$loop-debate-agentes`; não é um motor paralelo. Todas as regras genéricas de execução pertencem ao contrato-base. Este perfil somente fornece defaults jurídicos, briefing, fontes, categorias de objeção e gates adicionais.

## Configuração da extensão

```json
{
  "perfil_base": "debate_agents_v1",
  "perfil_dominio": "juridico_consensual_v2",
  "extensoes_dominio": {
    "juridico": {
      "tipo_documento": "parecer",
      "subtipo": "consultivo",
      "receita": {
        "documental": "parecer_consensual",
        "origem": "automatica",
        "overrides_usuario": {
          "requested": {},
          "effective": {},
          "confirmed": false
        },
        "lentes_minimas": ["questao", "fatos", "fontes", "alternativas", "riscos", "conclusao"]
      },
      "jurisdicao": "Brasil",
      "orgao": "",
      "ramo": "",
      "instancia": "",
      "posicao_ou_funcao": "imparcial",
      "finalidade": "",
      "data_corte": "YYYY-MM-DD",
      "sigilo": "confidencial",
      "fontes": {
        "manifesto": "fontes/manifesto.json",
        "primarias_oficiais_obrigatorias": true,
        "proibir_citacao_material_nao_verificada": true
      },
      "controle_alteracoes_word": {
        "contrato": "legal_word_redline_v1",
        "modo": "auto_se_docx_existente",
        "comparador": "docxodus_wmlcomparer",
        "processamento": "local_offline",
        "incremental_por_revisao": true,
        "comparativo_final_acumulado": true,
        "base_acumulada": "primeira",
        "canonico": "limpo",
        "indisponibilidade": "pausar"
      },
      "defaults": {
        "consenso": {"modo": "estrito", "politica_por_tentativa": "sempre", "estabilidade": 2},
        "debate": {"perfil_intensidade": "comum", "rodadas_padrao": 8, "ciclos_padrao": 2, "rodadas_maximas_recomendadas": 18, "ciclos_maximos_recomendados": 6},
        "versoes": {"padrao_por_artefato": 6, "maximo_por_artefato": 20, "uma_versao_por_tentativa": true},
        "ensemble_nxn": {"herdado_do_motor": true, "profundidade_padrao": "profundo", "ciclos_padrao": 2, "rodadas_minimas": 6},
        "decisao_colegiada": {"herdada_do_motor": true, "ativacao": "somente_por_pedido", "modalidade_padrao": "opinion_of_court", "ratio_exigida_para_precedente": true, "publicar_votos_separados": true},
        "auditoria_consistencia_conjunta": true,
        "revisao_profissional_obrigatoria": true
      },
      "rubrica": "references/rubrica-juridica.md",
      "estruturas": "references/estruturas.md",
      "gates": [
        "fontes_materiais_verificadas",
        "pressupostos_juridicos_enfrentados",
        "congruencia_fatos_fundamentos_conclusao",
        "argumentos_contrarios_e_riscos_tratados",
        "auditoria_cega_do_hash",
        "revisao_profissional"
      ]
    }
  }
}
```

O executor resolve primeiro o contrato-base e depois esta extensão. Defaults explícitos do usuário prevalecem quando válidos; gates jurídicos obrigatórios não são dispensados silenciosamente. O padrão é 6 versões/tentativas completas por artefato e o usuário pode confirmar de 1 a 20; v1 conta como tentativa 1 e v20 é o teto do motor. O padrão comum é 8 rodadas globais e 2 ciclos por tentativa. No `ensemble_nxn_v1` profundo, o padrão específico é 2 ciclos completos e ao menos 6 rodadas globais. A faixa recomendada do motor termina em 18 rodadas/6 ciclos; somente uma extensão gradual, justificada e confirmada, pode alcançar o teto excepcional de 36/12, sem perder os controles de domínio.

Resolver `receita` por `references/receitas-juridicas.md`. Exigir exatamente uma receita documental
por artefato. Em pacote, persistir a receita de cada item em
`pacote.itens[].overrides.extensoes_dominio.juridico.receita`. Compilar `ensemble_juridico` e
`pacote_processual` para os campos canônicos do motor somente por opt-in explícito ou proposta
confirmada. A precedência é: campo confirmado do usuário, delta do overlay no próprio eixo, delta
documental, default jurídico e default do motor. Persistir metadados na receita e valores efetivos
somente nos campos canônicos indicados na tabela de compilação.

A saída herda `adaptive_output_v1`: não há teto global artificial, não existe obrigação de preencher a resposta e cada modelo pode usar até o limite efetivo da rota. Metas de extensão do documento continuam sendo requisitos editoriais; metas de palavras das fases deliberativas são flexíveis. Peça ou parecer truncado não pode receber hash final, nota, consenso ou aprovação até ser completado pelo protocolo de continuação do motor.

## Controle de alterações do Word

Aplicar integralmente `references/controle-alteracoes-word.md` quando houver DOCX existente, saída DOCX iterativa ou ativação expressa. O modo `auto_se_docx_existente` pode ser desligado ou forçado pelo usuário caso a caso.

Cada tentativa conserva uma versão limpa. Após a correção do redator ou consolidador, a nova versão limpa recebe hash e o comparativo incremental mostra `anterior → corrente`. A criação de uma versão invalida consenso anterior sobre o texto e dispara os gates previstos no motor.

Conservar no máximo 20 versões limpas da cadeia canônica por `artefato_id`. Comparativos Word, pareceres e candidatas não promovidas não contam; seleção, síntese ou edição manual promovida ao canônico conta como nova versão. Ao atingir v20 sem aprovação, interromper antes de qualquer v21 e publicar somente a melhor versão com estado `não aprovada`.

Ao terminar todos os loops, o único canônico é `minuta-final-limpa.docx`. `minuta-final-com-alteracoes.docx` compara a primeira minuta — ou o original confirmado — com esse canônico e permanece derivado não canônico. Exija as provas `aceitar tudo = conteúdo final` e `rejeitar tudo = conteúdo-base`. A aprovação adere ao SHA-256 do limpo, nunca ao redline. Aceitação, rejeição ou edição manual parcial cria novo hash e reabre consenso, painel e auditoria aplicáveis.

## Modos e intensidade

Os modos `estrito`, `com_decisor`, `consultivo` e `desativado`, as frequências `sempre`, `se_necessario`, `apenas_primeira` e `nenhum`, e todos os efeitos na aprovação são herdados integralmente do motor. O default jurídico é `estrito + sempre`, não uma obrigação fixa.

Perfis recomendados, sem redefinir a regra do motor:

| Perfil | Rodadas | Ciclos | Uso indicativo |
|---|---:|---:|---|
| `simples` | 4–6 | 1 | revisão pontual |
| `comum` | 8 | 2 | parecer ou peça ordinária |
| `complexo` | 9–10 | 3 | controvérsia ou muitas fontes |
| `alto_risco` | 10–12 | 3 | impacto elevado ou pacote interdependente |

Esses perfis calibram debates jurídicos comuns. Quando `ensemble_nxn_v1` estiver ativo, sua profundidade fornece mínimos internos: `rapido` = 1 ciclo/ao menos 3 rodadas globais; `profundo` = 2/ao menos 6; `maximo_recomendado` = 6/18; extensão excepcional = até 12/36. Combinar esses mínimos com a receita documental pela regra de `references/receitas-juridicas.md`, sem reduzir valor explícito confirmado. Cada cadeira tem uma crítica, uma réplica e uma revisão por ciclo confirmado.

No ensemble jurídico, seleção, vitória ou síntese não são aprovação. O candidato escolhido ou sintetizado recebe novo hash, passa a `canonico_selecionado` e deve satisfazer consenso jurídico, painel externo, gates de fontes, rubrica e auditoria cega. Exatamente um hash por `artefato_id` pode chegar a `canonico_aprovado`; os demais permanecem candidatos auditáveis.

## Formação de decisão colegiada

Quando o pedido envolver acórdão, julgamento simulado, votos, tese colegiada ou opinião institucional, ativar a formação colegiada herdada do motor e aplicar integralmente `../loop-debate-agentes/references/decisao-colegiada.md`. Usar `global`/`decisao_colegiada_v1` por padrão. Usar `analitico` ou `hibrido`/`decisao_colegiada_v2` somente por escolha explícita para votar premissas ou questões separadamente. Esse é um eixo separado do debate, do loop, do consenso e dos métodos de escolha entre candidatos.

- `seriatim`: cada cadeira entrega voto completo e assinado; a certidão agrega resultado e fundamentos comuns sem inventar voz única.
- `per_curiam`: o colegiado publica opinião principal impessoal; votos separados continuam preservados e são publicados quando exigidos pela política confirmada.
- `opinion_of_court`: uma opinião da maioria explicita a ratio comum, acompanhada de votos concorrentes e dissidentes.

Em decisão destinada a orientar precedente, usar `ratio_exigida = true`. Cada julgador deve aderir ou não aderir a cada proposição essencial; concordância apenas no dispositivo produz `ratio_status = somente_resultado`. No modo analítico, publicar também as coalizões por questão, a coalizão do pacote, o dispositivo por cadeira e eventual `paradoxo_doutrinario`; sem maioria aderente ao pacote, não alegar ratio comum. No híbrido, rejeição na confirmação impede proclamação e devolve a questão ao loop. Em simulação brasileira, publicar voto vencido no pacote, mesmo quando houver opinião principal única. Maioria não é consenso, e nenhuma decisão colegiada formada substitui painel, fontes, auditoria ou revisão profissional.

Overrides podem ser feitos por run ou `artefato_id`. O motor valida `rodadas >= 3 × ciclos`, deriva somente o limite omitido e pausa diante de dois valores explícitos incompatíveis.

## Manifesto jurídico de fontes

Cada fonte registra, quando aplicável:

```json
{
  "id": "F-001",
  "tipo": "legislacao|precedente|ato|documento_do_caso|doutrina",
  "status": "verificada|nao_verificada|superada|divergente",
  "titulo": "",
  "orgao": "",
  "identificacao": "",
  "processo": "",
  "relator": "",
  "data_julgamento": "",
  "data_publicacao": "",
  "url_ou_caminho": "",
  "trecho_relevante": "",
  "data_acesso": "",
  "sha256": "",
  "observacao": ""
}
```

Guarde original e extração. Alteração de fonte cria nova entrada; não reescreva o registro anterior.

## Extensão do ledger

O ledger e sua transição de estados são herdados. Acrescente:

```json
{
  "artefato_id": "parecer-principal",
  "categoria_juridica": "fato|prova|fonte|vigencia|precedente|competencia|cabimento|tempestividade|preparo|legitimidade|interesse|dialeticidade|prequestionamento|efeitos|limites_devolutivos|nulidade|tese|contraditorio|congruencia|pedido_dispositivo|risco|redacao",
  "severidade": "bloqueante|alta|media|baixa",
  "local": "seção ou parágrafo",
  "condicao_juridica_para_aprovacao": ""
}
```

Bloqueio jurídico só é resolvido por correção verificável ou rejeição sustentada por evidência. Um problema transversal gera objeções relacionadas em cada item afetado; não transfira a objeção entre hashes ou documentos.

## Gates por artefato

Além dos gates do motor, reprove se houver fato ou prova material inventados, fonte ou citação decisiva não verificada, pressuposto pertinente omitido, conclusão sem suporte, pedido ou dispositivo incongruente, argumento contrário material não enfrentado, dado sigiloso exposto sem necessidade ou objeção jurídica bloqueante aberta.

Quando `controle_alteracoes_word` estiver ativo, também bloqueie a entrega se o comparativo contiver revisões prévias não resolvidas na entrada, se a verificação bidirecional falhar, se a base não estiver identificada ou se o arquivo com alterações for apresentado como canônico.

Use `references/rubrica-juridica.md` para critérios e controles próprios de parecer, peça de parte ou minuta decisória. A auditoria jurídica recebe o hash exato, briefing, estrutura, rubrica e snapshot de fontes, sem histórico decisório.

## Gate jurídico do pacote

O motor cria e governa o pacote. Este perfil exige `auditoria_consistencia_conjunta = true` por default e acrescenta a verificação de partes, fatos, datas, provas, fontes, premissas, teses, pedidos, conclusões, providências e dispositivos compartilhados.

O recibo conjunto contém `pacote_id`, manifesto exato de hashes, dependências, estados individuais, inconsistências e decisão `PACOTE_APROVADO | REABRIR_ITENS | PACOTE_NAO_APROVADO`. Não use nota compensatória. Alteração de premissa compartilhada reabre somente os itens materialmente afetados, conforme o DAG do motor.

## Compatibilidade

Runs congelados com `perfil = juridico_consensual_v1` não são reescritos. Na leitura de configuração antiga não congelada, mapear:

```text
perfil juridico_consensual_v1
  -> perfil_base debate_agents_v1
  -> perfil_dominio juridico_consensual_v2
modo_execucao -> modo_artefatos
pacote -> pacote do motor
juridico, fontes -> extensoes_dominio.juridico
configuracao sem receita declarada -> receita.origem = legado, sem aplicar novos deltas
```

Campos genéricos antigos (`redator`, `avaliador`, `consolidacao_iterativa`, `consenso`, `debate`, `ciclo_de_melhoria`, `artefatos`) continuam sendo lidos pelo motor, não por este perfil. Preserve aliases antigos do ledger, como `resposta_redator`, apenas para replay; grave o formato novo em runs novos.
