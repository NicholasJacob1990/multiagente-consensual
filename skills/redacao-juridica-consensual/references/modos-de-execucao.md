# Modos de execução: profundo × conciso

Arquivo idêntico em `legal-br/references/` e em `multiagente-consensual/skills/redacao-juridica-consensual/references/`. Ao alterar um, altere o outro.

## 1. Perguntar sempre

No início de cada trabalho jurídico (minuta nova, nova rodada, revisão, acabamento, anexo), **pergunte ao usuário qual modo usar**, com a recomendação e a estimativa de custo, e, na mesma pergunta, qual **estilo de redação** (executivo ou clássico; `estilos-de-redacao.md`), com a recomendação pelo destinatário. O padrão do perfil GENES é `modo_padrao: perguntar`. Só dispense a pergunta quando o próprio pedido já declarar o modo: "modo conciso", "rápido" ou "enxuto" equivalem a conciso; "modo profundo", "completo" ou "auditoria completa" equivalem a profundo.

Modelo de pergunta (uma linha por opção):

- **Conciso**: 1 redator e verificação só determinística; minutos; ~0–0,4 M tokens de subagentes. Recomendado para acabamento, ajuste de redação ou rodada sobre texto já verificado.
- **Profundo**: leitura integral ou releitura dirigida, redatores por seção com revisor de fidelidade, verificadores com contraprova adversarial; 30–60 min; ~3–6 M tokens. Recomendado para a 1ª versão, dossiê novo, mudança de mérito ou de conclusão.

O modo escolhido aparece na primeira linha da nota de revisão.

## 2. O que muda em cada modo

| Etapa | Conciso | Profundo |
|---|---|---|
| Leitura do dossiê | Reaproveita índice, achados e registros da pasta do caso; lê só as páginas citadas em trecho alterado | Etapa 0.5 completa: leitura integral em blocos, índice, páginas ilegíveis, achados com contraprova |
| Pesquisa | Confere as fontes já citadas; nada novo sem pedido | Legislação, jurisprudência verificada em fonte primária e doutrina, com nível de acesso (L1–L4) |
| Redação | 1 redator; meta de 70–85 % da versão anterior (vinculante); parágrafos de 40–90 palavras | Redator por seção + revisor de fidelidade por seção; meta de 85–95 % (indicativa); parágrafos de até ~110 palavras; quadro de hipóteses |
| Verificação | Só a caixa de ferramentas (seção 4) | Caixa de ferramentas + verificadores especializados (remissões, fatos contra o dossiê, ressalvas, leitor leigo, coerência corpo × conclusão × anexo), cada um com contraprova adversarial; painel cego quando houver versões concorrentes |
| Peça anexa (requerimento, ofício) | Modelo curto, pedidos numerados | Completa, pela referência `requerimento-registral.md` quando for ao Registro de Imóveis |
| Entregas | Limpa + comparativo + nota curta (5–10 linhas) | Limpa + comparativo + nota detalhada (tabela de acréscimos com fonte, correções acolhidas e recusadas, pendências) |

## 3. Escalonamento
- **Conciso → profundo** (pare e pergunte) quando surgir: fato, número, data ou página novo sem fonte já verificada; mudança na resposta a quesito ou na conclusão; contradição entre corpo, conclusão e anexo; mais de 5 remissões quebradas; dossiê sem índice ou com leitura parcial; afirmação do registro de refutadas (seção 5.3).
- **Profundo**: antes de lançar subagentes, informe a estimativa (agentes e tokens). O usuário pode pedir "profundo, só verificação" para pular a reescrita.

## 4. Invariantes e caixa de ferramentas (valem nos dois modos)

**Um comando por versão.** Em toda versão entregue, nos dois modos, rode `conferir_versao.py --anterior APROVADA.docx --nova NOVA.docx [--redline] [--mapa-origem] [--refutadas] [--decisoes] --perfil genes --max-paginas N --registro versoes.json --nota-saida conferencias.md`. Ele roda as ferramentas da tabela abaixo, mede as páginas no PDF, atualiza o registro de versões e gera a seção "Conferências automáticas" da nota de revisão. Correção pontual se aplica com `aplicar_overlay.py` (por número de parágrafo ou por âncora de texto, inclusive em ementa, quadro e anexo, com `--limpa` e `--integridade`), nunca com montador improvisado.

Use as ferramentas do plugin, nunca scripts improvisados, salvo para o que nenhuma delas cobre (e então registre na nota). Scripts sem prefixo são de `multiagente-consensual/skills/redacao-juridica-consensual/scripts/`; `legal-br:` indica `legal-br/scripts/`.

| Invariante | Ferramenta |
|---|---|
| Nenhum número, data, página, valor, área, dispositivo, matrícula ou registro some entre versões sem registro; todo acréscimo tem fonte com página | `inventario_fatos.py ANTERIOR NOVA --md` → tabela na nota de revisão |
| Remissões conferidas pelo conteúdo; mapas de divisão **e fusão** aplicados por script; sem número repetido nem "N a N+1" | `verificar_remissoes.py mapear --origem origem.json` → `renumerar` → `conferir` |
| Aceitar todas as marcas reproduz a limpa; rejeitar reproduz a base; nenhum parágrafo, referência ou nota perdido | `integridade_docx.py --base --limpa --redline` (também chamado por `word_redline.py`) |
| Comparativo contra a **última versão aprovada pelo usuário**, por palavra quando houver correspondência entre parágrafos | `word_redline.py --base APROVADA.docx --motor auto` (sem Docxodus, usa o motor nativo) |
| Pré-auditoria sem ruído de reescrita | `docx_para_md.py` → `pre_auditoria_parecer.py --perfil genes --anterior ANT.md --mapa-origem origem.json --refutadas refutadas.json` |
| Sem absolutos sem prova ("nunca", "sempre", "jamais", "todos", "nenhum", "integralmente", "exclusivamente") | check `absolutos` da pré-auditoria; preferir "nada nos autos indica", "não há documento que" |
| Afirmações já refutadas no caso não voltam (nem em texto colado pelo usuário ou vindo de outro modelo) | `checar_refutadas.py --refutadas refutadas.json TEXTO` |
| Correções de vários verificadores sem duplicata nem conflito silencioso | `consolidar_correcoes.py ... --mapa mapa.json --relatorio` |
| Dados de matrícula extraídos da certidão, não digitados | `legal-br: extrair_assentos.py CERTIDAO.md --md` |
| Termos completos (sem elipse), siglas definidas, partes com nome único | regras do /parecer, Etapa 6, e da pré-auditoria |
| O que se atribui à consulente está na peça dela; quesitos fiéis, sem acréscimo nem omissão de alternativa | `conferir_atribuicao.py --fonte CI.md MINUTA.md` |
| Sugestão de revisor que contraria decisão já tomada não é aplicada nem relitigada | `checar_decisoes.py --decisoes decisoes.json`; `consolidar_correcoes.py --decisoes` |
| Achados de remissão de auditor externo conferidos antes de corrigir (deslocamento de numeração, cópia com outro hash) | `pacote_auditoria.py montar --numerado PARECER.docx`; `conferir_achados_externos.py --documento --achados --sha256-entregue` |
| Correção pontual com diff por palavra e integridade | `aplicar_overlay.py` (itens `n`, `ancora`, `ancora_paragrafo`; `--limpa`, `--integridade`) |
| Páginas dentro do limite do perfil (ou ampliação registrada) | `conferir_versao.py --max-paginas N` |
| Contas do caso (somas, proporções, áreas, prazos) continuam fechando e os números certos continuam no texto | `conferir_aritmetica.py --verificacoes verificacoes.json` (ou `conferir_versao.py --verificacoes`) |
| Estilo escolhido aplicado (resposta objetiva ou ementa estruturada; alvo de palavras por parágrafo e por frase; transcrições; intensificadores; rótulos da conclusão) | `pre_auditoria_parecer.py --estilo executivo|classico` (ou `conferir_versao.py --estilo`) |
| Anexo presente quando a consulta pede minuta ou peça | `--exige-anexo` na pré-auditoria e no `conferir_versao.py` |
| Parágrafos com numeração automática (perfil GENES) | pré-auditoria: documento sem nenhum parágrafo numerado é bloqueado |
| Pedido de condensação cumprido no volume, não só no tamanho das frases | `medir_densidade.py NOVA --anterior ANT --meta-reducao N` (ou `conferir_versao.py --meta-reducao N`) |
| Sem pontas soltas depois de corte ou reescrita: julgado sem referência, referência sem citação, verbete órfão, instrução editorial no texto, conta só com símbolos | `conferir_orfaos.py NOVA` (também chamado por `conferir_versao.py`) |
| Reescrita com reestruturação sem perder bloco por descuido | `reescrever_docx.py listar` e `montar` (relatório dos blocos não mantidos) → `word_redline.py compare` |
| Base limpa quando o arquivo recebido tem marcas pendentes; comparativo desde o original | `resolver_revisoes.py --modo rejeitar\|aceitar` → `word_redline.py compare` |

## 5. Pasta do caso e retomada
1. **Registros persistentes** (Etapa 0.5 do /parecer): índice, achados, cronologia, páginas ilegíveis, conferência da origem, registro de correções, **registro de refutadas** e mapas de origem de cada rodada. Grave-os na pasta do projeto, não em diretório temporário.
2. **Checkpoint por fase**: no modo profundo, grave o resultado de cada fase (trechos, ajustes, reescrita, correções propostas e consolidadas) antes de iniciar a seguinte. Se o ambiente reiniciar, retome do último checkpoint ou com `resumeFromRunId` do workflow.
3. **Registro de refutadas** (`refutadas.json`; modelo em `refutadas_modelo.json`): toda afirmação refutada numa rodada (por auditor, usuário ou verificação) entra com padrão, motivo, forma correta e fonte. A pré-auditoria passa a bloqueá-la.
4. **Registro de decisões** (`decisoes.json`; modelo em `decisoes_modelo.json`): toda escolha do usuário sobre requerente, forma, estilo, limites (páginas, palavras) e estratégia, com data e origem. Antes de aplicar sugestão de revisor, confira com `checar_decisoes.py`; a que reabrir decisão vai à nota como "decisão já tomada — reabrir?".
5. **Registro de verificações aritméticas** (`verificacoes.json`; modelo em `verificacoes_modelo.json`): cada conta conferida do caso, com a expressão, a tolerância e os números que precisam continuar no texto.
6. **Registro de versões** (`versoes.json`, mantido por `conferir_versao.py --registro`): versão, base, hashes da limpa e do comparativo, data, modo, resumo e resultado das conferências. O comparativo acumulado (primeira → atual) sai sob pedido.

## 6. Orquestração (modo profundo)
- **Prazo por agente.** Ao lançar painel ou verificadores, informe o prazo esperado. Se um agente não retornar no dobro do prazo, avise o usuário e ofereça retomar ou cancelar. Nunca deixe um painel "pendente" sem prazo nem relate como concluído o que não retornou.
- **Contraprova.** Toda correção proposta por verificador passa por um segundo agente instruído a refutá-la. Entram só as aceitas ou ajustadas, consolidadas por `consolidar_correcoes.py`.
- **Achados de auditor externo** (outro modelo, outro pipeline, nota do usuário): cada ponto vira item com veredito (acolhido, parcial, recusado ou decisão já tomada) e fonte, no formato de `nota-de-revisao.md`. Nada entra sem verificação, e o que for refutado vai para o registro de refutadas. Entregue ao auditor o texto com "§N" explícito e peça o SHA-256; tabela de remissões do auditor passa por `conferir_achados_externos.py` antes de qualquer correção.
- **Texto sugerido por terceiro** (minuta antiga, relatório de outro modelo, trecho colado): antes de aproveitar, `checar_refutadas.py` e `conferir_atribuicao.py` contra a peça da consulente; aproveite a forma (ordem, fluidez, siglas por extenso) e confira cada fato.

## 7. Métricas da nota de revisão
Informe sempre três métricas: palavras (antes → depois, %), parágrafos numerados (antes → depois) e faixa de extensão dos parágrafos (mínimo–máximo). No conciso, a meta de palavras é vinculante; no profundo, é indicativa. Quando o ganho vier da organização e não do corte, diga isso.
