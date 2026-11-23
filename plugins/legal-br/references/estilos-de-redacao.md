# Estilos de redação: executivo × clássico

Arquivo idêntico em `legal-br/references/` e em `multiagente-consensual/skills/redacao-juridica-consensual/references/`. Ao alterar um, altere o outro.

O **estilo** (como o texto se dirige ao leitor) é independente do **modo** (quanto se lê e se verifica; `modos-de-execucao.md`). Os dois são escolhidos no início do trabalho.

## 1. Escolha
- **Padrão pelo destinatário:**
  - gestor, diretoria, área técnica (engenharia, patrimônio) ou governança → **executivo**;
  - Advocacia-Geral do Estado, Tribunal de Contas, juízo corregedor ou instância superior → **clássico**.
- **Em dúvida, pergunte** junto com o modo, numa só pergunta: "conciso ou profundo? executivo ou clássico?". O perfil pode fixar o padrão (GENES: `estilo_padrao: executivo`).
- **Mudar de estilo** numa versão já aprovada é reescrita, não acabamento: siga a reescrita com reestruturação (`revisao-redacional.md` §5), com mapa de origem e conferência de remissões.
- **Ferramentas:** o estilo é passado à pré-auditoria e ao `conferir_versao.py` (`--estilo executivo|classico`), que conferem: resposta objetiva (executivo) ou ementa estruturada (clássico); alvo de palavras por parágrafo e por frase; transcrições; intensificadores; rótulos da conclusão; numeração dos parágrafos; e, com `--exige-anexo`, a presença do Anexo.

## 2. Núcleo comum (vale nos dois estilos)
1. **Fidelidade aos autos.** Fatos, datas, valores, áreas, identificadores de documento e páginas conferidos na fonte primária; acréscimo de fato com página na nota de revisão (`inventario_fatos.py`).
2. **Verificação aritmética obrigatória** sempre que houver números que se relacionam: somas de áreas, proporções, percentuais, diferenças, prazos em dias, áreas geométricas. Cada conta conferida entra no registro de verificações do caso (`verificacoes.json` na pasta do caso; modelo em `verificacoes_modelo.json`). O `conferir_aritmetica.py` (também chamado por `conferir_versao.py --verificacoes`) a refaz em toda versão e confere se os números certos continuam no texto. Os números são do caso, não do plugin.
3. **Quadro de hipóteses** quando titularidade, legitimidade ou regime dependerem de fato não provado. Cada hipótese traz prova a favor, prova contra, consequência, legitimado e diligência decisiva. Nenhuma extinção ou transmissão é assumida antes da prova.
4. **Peça anexa dirigida a terceiro** (requerimento, ofício) com pedidos compatíveis com a conclusão. Para o Registro de Imóveis, `requerimento-registral.md`.
5. **Remissão rotulada, nunca cega.** Toda remissão a parágrafo traz o nome do bloco e o número ("na resposta objetiva (parágrafo 1)", "no quadro de hipóteses, alínea b", "no plano de ação (parágrafos 123 e 124)"). Remissão só por número é proibida na conclusão e nos pontos de virada. O número é conferido por script (`verificar_remissoes.py conferir`; `conferir_achados_externos.py` para auditor externo).
6. **Um parágrafo, uma função.** O tamanho se mede em palavras, não em linhas (linha depende de fonte e margem). Completude antes da extensão: limite nunca se cumpre por elipse.
7. **Datas e bibliografia uniformes.** Datas no mesmo formato ao longo do texto (por extenso no corpo, ou dd/mm/aaaa em tabelas e quadros, conforme o perfil). Data de corte declarada. Referências num só padrão (ABNT).
8. **Diligências** numeradas, com o responsável e o documento a obter, em destaque. Quantas o caso exigir, sem número fixo. **Uma lista só:** o plano de ação e a conclusão remetem a ela pelo nome da seção, sem repeti-la.
9. **Conta por extenso.** Toda conta que sustenta uma conclusão é escrita em palavras, com os valores intermediários ("o quadrado de 20,00 m de lado (400,00 m²) menos o quarto de círculo de mesmo raio (314,16 m²), isto é, 85,84 m²"). Fórmula só com símbolos (π, ÷, −, ≈) se perde na extração de texto de outros leitores e volta como "erro" na revisão.
10. **Fato decisivo primeiro.** Cada quesito ou tópico abre dizendo de que fato ou prova a resposta depende e qual é a hipótese principal; a análise vem depois. O leitor não deve descobrir a tese no último parágrafo.
11. **Julgado no corpo, julgado nas Referências.** Precedente que não foi conferido na fonte não entra; o que entra tem entrada nas Referências, com órgão, relator e data. O comentário não vai além do que a ementa decide.
12. **Premissas e validade.** A conclusão declara que a análise pressupõe a autenticidade e a integralidade dos documentos do processo e diz quando a orientação deve ser reavaliada (títulos pendentes obtidos, decisão relevante, mudança das normas).
13. **Unidades e pessoas com o nome dos autos.** Não se atribui providência a setor cujo nome não consta do processo; na falta, descreve-se a função ("área técnica de engenharia").

## 3. Perfil A: executivo e analítico (linguagem jurídica clara)
| Elemento | Regra |
|---|---|
| Destinatários | Diretorias, áreas técnicas, governança |
| Abertura | Ementa, seguida logo de **Resposta objetiva** (4 a 6 linhas: o que fazer e o que não fazer agora, com o grau de segurança). Posição: §1 da seção I ou entre a ementa e o Relatório. Se ficar antes do Relatório **sem número**, todos os parágrafos se deslocam em um: refaça as remissões por script (a pré-auditoria avisa) |
| Parágrafos | Alvo de até **90 palavras** (a maioria entre 40 e 75), com alternância de tamanho por função; teto duro do perfil (GENES: 120). A pré-auditoria com `--estilo executivo` alerta acima de 90 e bloqueia acima do teto |
| Frases | Ordem direta, voz ativa, uma ideia principal por frase; transição imediata do fato à consequência jurídica. Média de até 30 palavras por frase, sem contar as citações entre parênteses; a pré-auditoria alerta frase acima de 50 |
| Termos técnicos | Explicados brevemente no próprio fluxo, na primeira ocorrência do corpo (domínio útil, domínio direto, resgate, comisso, cabecel, fração ideal, consolidação, prenotação) |
| Jurisprudência e doutrina | Paráfrase analítica (o que decidiu, por que importa, o que não decidiu); sem transcrição literal longa |
| Conclusão | Síntese; um parágrafo por quesito, com o rótulo em forma de pergunta; **plano de ação** em passos numerados (1), (2)…, agrupados em etapas quando ajudar; premissas e limites; no GENES, os quatro rótulos de grupo, apresentados como índice |

## 4. Perfil B: clássico forense e discursivo

O clássico muda o **registro**, não a densidade de fontes: cada afirmação continua com dispositivo e página, como no executivo.

| Elemento | Regra |
|---|---|
| Destinatários | AGE, Tribunais de Contas, juízos corregedores, instâncias superiores |
| Cabeçalho | "PARECER JURÍDICO nº …/AAAA", processo, interessadas, unidade consulente, unidade consultada e objeto |
| Ementa | Em duas partes: verbetes em caixa alta e **ementa estruturada em quatro itens numerados**, no padrão das ementas judiciais: (1) caso sob exame; (2) questões em discussão; (3) razões conclusivas; (4) resposta objetiva aos quesitos. A resposta objetiva fica na ementa, e não em parágrafo próprio no início |
| Estrutura | Tripartite: **I. Relatório**, **II. Fundamentação**, **III. Conclusão**, com subtítulos sem número dentro da fundamentação, um por tema ou quesito ("Quesito 1 — …") |
| Parágrafos | Numeração contínua; teto do perfil (GENES: 120 palavras), com a maioria entre 50 e 100 |
| Frases | Mais longas que no executivo: média de até 45 palavras, sem contar as citações entre parênteses; a pré-auditoria alerta frase acima de 80 |
| Conectivos e léxico | Forenses, sem enchimento: "Lado outro", "Nada obstante", "Ademais", "No tocante a", "Em contrapartida", "Nesse contexto", "Disso decorre", "Impõe-se", "Cumpre", "Descabe", "refoge a", "confira-se", "higidez do fólio", "os aludidos lotes" |
| Dogmática | Linguagem técnica formal, com citação direta dos dispositivos (artigo, parágrafo, inciso e diploma por extenso na primeira vez) |
| Jurisprudência | **Transcrição literal liberada, inclusive no perfil GENES: uma por seção ou quesito.** Forma: parágrafo de introdução ("Sobre …, confira-se o entendimento firmado pelo Tribunal …:"), ementa recuada com órgão, número, relator e datas, e parágrafo de comentário que diz o que o precedente decide e o que não decide para o caso |
| Remissões | Preferencialmente por quesito, seção ou bloco ("como exposto no exame do Quesito 1"); com número, sempre rotuladas |
| Conclusão | Abertura em prosa ("Em face dos fundamentos expostos…"); resposta por quesito ("Quesito 1: …"); plano de ação em etapas; **matriz de responsabilidades** em alíneas a) a d), que cumpre os quatro grupos do perfil GENES com rótulo próprio, sem negrito ("Correções e definições prioritárias", "Obrigações jurídicas incidentes", "Recomendações facultativas", "Providências a cargo de terceiros e áreas internas"); "Restituam-se os autos…"; fecho |
| Assinatura | Bloco do perfil ou equivalente preenchido: nome, "Advogado – GENES", companhia |

**O que o clássico não dispensa:**
- **Peça anexa:** quando a consulta pedir minuta ou peça (requerimento, ofício), o **Anexo continua obrigatório**, com as regras da peça dirigida a terceiro. Use `--exige-anexo` na pré-auditoria e no `conferir_versao.py`.
- **Quadro de hipóteses:** continua exigido quando a titularidade depender de fato não provado. Pode vir em prosa, dentro do quesito.
- **Intensificadores:** "manifesto", "inequívoco", "rigorosa", "estritamente" afirmam grau de certeza; a pré-auditoria alerta, e a ênfase só fica com fonte que a sustente.
- **Atribuição à consulente:** só com os termos da peça dela.

## 5. O que não muda entre os estilos
- **Regras duras do /parecer:** fonte para toda afirmação, precedente verificado, gradação simétrica, premissas declaradas, indício não é título.
- **Elipses:** proibidas ("Código Civil de 1916", "domínio útil", siglas definidas).
- **Atribuição à consulente:** só com os termos da peça; quesitos fiéis.
- **Absolutos:** só com prova.
- **Ferramentas:** registros de refutadas, decisões, verificações e versões; um comando por versão.

## 6. Leitor não técnico e condensação
Quando o destinatário não é da área jurídica, ou quando o usuário pede texto "menos denso", "mais enxuto" ou "mais compreensível", o trabalho tem duas frentes, e as duas se medem (`medir_densidade.py`):

| Frente | O que fazer | Medida |
|---|---|---|
| **Ritmo** | Dividir frases longas; um parágrafo, uma função; termo técnico explicado na primeira ocorrência | média de palavras por frase; frases acima de 60 e de 80; parágrafos de frase única com mais de 70 palavras |
| **Volume** | Cortar o que não muda a resposta | palavras e parágrafos do corpo, antes e depois |

**Dividir frases não reduz a densidade.** Uma reescrita pode derrubar a média por frase em 40% e manter 90% do volume. Se o pedido é reduzir, declare a meta ao usuário (por exemplo, um terço a menos) e confira com `--meta-reducao`; abaixo da meta, corte conteúdo.

**O que sai primeiro, sem mudar a resposta:**
- identificadores que já estão no anexo ou na lista de diligências (livro, folhas, protocolo, código de matrícula);
- valores e datas intermediários que não entram em nenhuma conta nem em nenhuma conclusão;
- notas de legibilidade repetidas (basta uma, onde a dúvida de leitura importa);
- exemplos de alcance limitado e dispositivos acessórios citados "para completar";
- transcrição de ementa substituível por paráfrase com a citação completa;
- o segundo e o terceiro enunciados da mesma conclusão.

**O que não sai:** fato que decide, fonte com página, ressalva que calibra a conclusão, conta do caso, hipótese contrária mais forte.

**Recursos para o leitor não técnico** (valem nos dois estilos):
- **Glossário no Relatório:** um ou dois parágrafos com os termos centrais do caso, quando houver cinco ou mais termos técnicos que o leitor terá de reter.
- **Síntese após a ementa:** quadro de quatro linhas (o que se sabe; o que ainda não se sabe; o que não fazer agora; o que fazer primeiro). No clássico, não substitui a ementa estruturada; fica logo depois dela, sem número de parágrafo.
- **Quadro de hipóteses:** tabela com hipótese, o que a sustenta, o que falta provar e consequência prática, seguida de um parágrafo curto por hipótese só para o que a tabela não comporta.

**Depois de cortar, costurar** (`conferir_orfaos.py`): verbete da ementa sem parágrafo correspondente; entrada das Referências que ninguém mais cita; faixa de artigos nas Referências que inclui dispositivo retirado; diligência ou item do anexo que pede dado que a fundamentação não menciona mais; remissão a seção que mudou de nome.

**Registro:** a nota de revisão traz a tabela de densidade (antes e depois) e a lista do que saiu, marcando o que ficou "só nesta nota". A versão completa anterior é preservada e citada.
